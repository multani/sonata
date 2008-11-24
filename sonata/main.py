# coding=utf-8
# $HeadURL: http://svn.berlios.de/svnroot/repos/sonata/trunk/main.py $
# $Id: main.py 141 2006-09-11 04:51:07Z stonecrest $

__version__ = "1.5.3"

__license__ = """
Sonata, an elegant GTK+ client for the Music Player Daemon
Copyright 2006-2008 Scott Horowitz <stonecrest@gmail.com>

This file is part of Sonata.

Sonata is free software; you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation; either version 3 of the License, or
(at your option) any later version.

Sonata is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with this program.  If not, see <http://www.gnu.org/licenses/>.
"""

import getopt, sys, gettext, os, misc, platform

# let gettext install _ as a built-in for all modules to see
try:
    gettext.install('sonata', os.path.join(__file__.split('/lib')[0], 'share', 'locale'), unicode=1)
except:
    gettext.install('sonata', '/usr/share/locale', unicode=1)
gettext.textdomain('sonata')

import mpdhelper as mpdh
from socket import getdefaulttimeout as socketgettimeout
from socket import setdefaulttimeout as socketsettimeout

import consts, config, preferences, tagedit, artwork

ElementTree = None
ServiceProxy = None
audioscrobbler = None

all_args = ["toggle", "version", "status", "info", "play", "pause",
            "stop", "next", "prev", "pp", "random", "repeat", "hidden",
            "visible", "profile=", "popup"]
cli_args = ("play", "pause", "stop", "next", "prev", "pp", "info",
            "status", "repeat", "random", "popup")
short_args = "tpv"

# Check if we have a cli arg passed.. if so, skip importing all
# gui-related modules
skip_gui = False
try:
    opts, args = getopt.getopt(sys.argv[1:], short_args, all_args)
    if args != []:
        for a in args:
            if a in cli_args:
                skip_gui = True
except getopt.GetoptError:
    pass

try:
    import mpd
except:
    sys.stderr.write("Sonata requires python-mpd. Aborting...\n")
    sys.exit(1)

# Test python version (note that python 2.5 returns a list of
# strings while python 2.6 returns a tuple of ints):
if tuple(map(int,platform.python_version_tuple())) < (2, 5, 0):
    sys.stderr.write("Sonata requires Python 2.5 or newer. Aborting...\n")
    sys.exit(1)

try:
    import dbus, dbus.service
    if getattr(dbus, "version", (0,0,0)) >= (0,41,0):
        import dbus.glib
    if getattr(dbus, "version", (0,0,0)) >= (0,80,0):
        import _dbus_bindings as dbus_bindings
        NEW_DBUS = True
    else:
        import dbus.dbus_bindings as dbus_bindings
        NEW_DBUS = False
    HAVE_DBUS = True
except:
    HAVE_DBUS = False

if not skip_gui:
    import warnings, gobject, urllib, urllib2, re, gc, locale, shutil
    import gtk, pango, threading, time, ui, img, tray

    # Test pygtk version
    if gtk.pygtk_version < (2, 12, 0):
        sys.stderr.write("Sonata requires PyGTK 2.12.0 or newer. Aborting...\n")
        sys.exit(1)

    # Prevent deprecation warning for egg:
    warnings.simplefilter('ignore', DeprecationWarning)
    try:
        import egg.trayicon
        HAVE_EGG = True
        HAVE_STATUS_ICON = False
    except ImportError:
        HAVE_EGG = False
        HAVE_STATUS_ICON = True
    # Reset so that we can see any other deprecation warnings
    warnings.simplefilter('default', DeprecationWarning)

    HAVE_GNOME_MMKEYS = False
    if HAVE_DBUS:
        try:
            bus = dbus.SessionBus()
            dbusObj = bus.get_object('org.freedesktop.DBus', '/org/freedesktop/DBus')
            dbusInterface = dbus.Interface(dbusObj, 'org.freedesktop.DBus')
            if dbusInterface.NameHasOwner('org.gnome.SettingsDaemon'):
                try:
                    # mmkeys for gnome 2.22+
                    settingsDaemonObj = bus.get_object('org.gnome.SettingsDaemon', '/org/gnome/SettingsDaemon/MediaKeys')
                    settingsDaemonInterface = dbus.Interface(settingsDaemonObj, 'org.gnome.SettingsDaemon.MediaKeys')
                    settingsDaemonInterface.GrabMediaPlayerKeys('Sonata', 0)
                except:
                    # mmkeys for gnome 2.18+
                    settingsDaemonObj = bus.get_object('org.gnome.SettingsDaemon', '/org/gnome/SettingsDaemon')
                    settingsDaemonInterface = dbus.Interface(settingsDaemonObj, 'org.gnome.SettingsDaemon')
                    settingsDaemonInterface.GrabMediaPlayerKeys('Sonata', 0)
                HAVE_GNOME_MMKEYS = True
                HAVE_MMKEYS = False
        except:
            pass

    if not HAVE_GNOME_MMKEYS:
        try:
            # if not gnome 2.18+, mmkeys for everyone else
            import mmkeys
            HAVE_MMKEYS = True
        except:
            HAVE_MMKEYS = False

    # Default to no sugar, then test...
    HAVE_SUGAR = False
    VOLUME_ICON_SIZE = 4
    if 'SUGAR_BUNDLE_PATH' in os.environ:
        try:
            from sugar.activity import activity
            HAVE_STATUS_ICON = False
            HAVE_SUGAR = True
            VOLUME_ICON_SIZE = 3
        except:
            pass

# FIXME Constants, Config and Preferences should not be inherited from
class Base(object, consts.Constants, preferences.Preferences):
    def __init__(self, window=None, sugar=False):
        consts.Constants.__init__(self)

        # This is needed so that python-mpd correctly returns lowercase
        # keys for, e.g., playlistinfo() with a turkish locale
        try:
            locale.setlocale(locale.LC_CTYPE, "C")
        except:
            pass

        # The following attributes were used but not defined here before:
        self.about_dialog = None
        self.album_current_artist = None
        self.albumText = None
        self.allow_art_search = None
        self.choose_dialog = None
        self.chooseimage_visible = None
        self.columnformat = None
        self.columns = None
        self.currentdata = None
        self.current_songs = None
        self.filterbox_cmd_buf = None
        self.filterbox_cond = None
        self.filterbox_source = None
        self.imagelist = None
        self.info_boxes_in_more = None
        self.info_editlabel = None
        self.info_editlyricslabel = None
        self.info_imagebox = None
        self.info_image = None
        self.info_labels = None
        self.info_left_label = None
        self.info_lyrics = None
        self.info_morelabel = None
        self.info_searchlabel = None
        self.info_tagbox = None
        self.info_type = None
        self.iterate_handler = None
        self.libfilterbox_cmd_buf = None
        self.libfilterbox_cond = None
        self.libfilterbox_source = None
        self.linkcolor = None
        self.local_dest_filename = None
        self.lyricsText = None
        self.notification_width = None
        self.playlist_pos_before_filter = None

        self.prevlibtodo_base = None
        self.prevlibtodo_base_results = None
        self.prevlibtodo = None

        self.prevtodo = None
        self.remote_albumentry = None
        self.remote_artistentry = None
        self.remote_dest_filename = None
        self.remotefilelist = None
        self.resizing_columns = None
        self.save_timeout = None
        self.seekidle = None
        self.statusicon = None
        self.trayeventbox = None
        self.trayicon = None
        self.trayimage = None
        self.artwork = None

        self.library_view_caches_reset()

        # Initialize vars (these can be needed if we have a cli argument, e.g., "sonata play")
        socketsettimeout(5)
        self.profile_num = 0
        self.profile_names = [_('Default Profile')]
        self.musicdir = [misc.sanitize_musicdir("~/music")]
        self.host = ['localhost']
        self.port = [6600]
        self.password = ['']
        self.client = mpd.MPDClient()
        self.conn = False

        # Constants
        self.TAB_CURRENT = _("Current")
        self.TAB_LIBRARY = _("Library")
        self.TAB_PLAYLISTS = _("Playlists")
        self.TAB_STREAMS = _("Streams")
        self.TAB_INFO = _("Info")
        self.NOTAG = _("Untagged")
        self.VAstr = _("Various Artists")

        # If the connection to MPD times out, this will cause the interface to freeze while
        # the socket.connect() calls are repeatedly executed. Therefore, if we were not
        # able to make a connection, slow down the iteration check to once every 15 seconds.
        self.iterate_time_when_connected = 500
        self.iterate_time_when_disconnected_or_stopped = 1000 # Slow down polling when disconnected stopped

        # FIXME Don't subclass
        self.config = self
        config.Config.__init__(self, _('Default Profile'), _("by") + " %A " + _("from") + " %B")

        self.trying_connection = False
        toggle_arg = False
        popup_arg = False
        start_hidden = False
        start_visible = False
        arg_profile = False

        # Read any passed options/arguments:
        if not sugar:
            try:
                opts, args = getopt.getopt(sys.argv[1:], short_args, all_args)
            except getopt.GetoptError:
                # print help information and exit:
                self.print_usage()
                sys.exit()
            # If options were passed, perform action on them.
            if opts != []:
                for o, a in opts:
                    if o in ("-t", "--toggle"):
                        toggle_arg = True
                        if not HAVE_DBUS:
                            print _("The toggle argument requires D-Bus. Aborting.")
                            self.print_usage()
                            sys.exit()
                    elif o in ("-p", "--popup"):
                        popup_arg = True
                        if not HAVE_DBUS:
                            print _("The popup argument requires D-Bus. Aborting.")
                            self.print_usage()
                            sys.exit()
                    elif o in ("-v", "--version"):
                        self.print_version()
                        sys.exit()
                    elif o in ("--visible"):
                        start_visible = True
                    elif o in ("--hidden"):
                        start_hidden = True
                    elif o in ("--profile"):
                        arg_profile = True
                    else:
                        self.print_usage()
                        sys.exit()
            if args != []:
                for a in args:
                    if a in cli_args:
                        self.single_connect_for_passed_arg(a)
                    else:
                        self.print_usage()
                    sys.exit()

        gtk.gdk.threads_init()

        self.traytips = tray.TrayIconTips()

        start_dbus_interface(toggle_arg, popup_arg)

        self.gnome_session_management()

        misc.create_dir('~/.covers/')

        # Initialize vars for GUI
        self.current_tab = self.TAB_CURRENT

        self.prevconn = []
        self.prevstatus = None
        self.prevsonginfo = None

        self.lyricServer = None

        self.popuptimes = ['2', '3', '5', '10', '15', '30', _('Entire song')]

        self.exit_now = False
        self.ignore_toggle_signal = False

        self.user_connect = False

        self.search_terms = [_('Artist'), _('Title'), _('Album'), _('Genre'), _('Filename'), _('Everything')]
        self.search_terms_mpd = ['artist', 'title', 'album', 'genre', 'file', 'any']

        self.sonata_loaded = False
        self.call_gc_collect = False
        self.total_time = 0
        self.prev_boldrow = -1

        self.filterbox_visible = False
        self.edit_style_orig = None
        self.album_reset_artist()

        show_prefs = False
        self.updating_nameentry = False
        self.merge_id = None
        self.mergepl_id = None
        self.actionGroupProfiles = None
        self.actionGroupPlaylists = None
        self.skip_on_profiles_click = False
        self.last_repeat = None
        self.last_random = None
        self.last_title = None
        self.last_progress_frac = None
        self.last_progress_text = None
        self.last_info_bitrate = None
        self.column_sorted = (None, gtk.SORT_DESCENDING)				# TreeViewColumn, order

        self.filter_row_mapping = [] # Mapping between filter rows and self.currentdata rows
        self.plpos = None

        self.last_status_text = ""

        self.eggtrayfile = None
        self.eggtrayheight = None
        self.scrob = None
        self.scrob_post = None
        self.scrob_start_time = ""
        self.scrob_playing_duration = 0
        self.scrob_last_prepared = ""
        self.scrob_time_now = None
        self.sel_rows = None
        self.img_clicked = False

        self.elapsed_now = None
        self.current_update_skip = False
        self.libsearch_last_tooltip = None

        try:
            self.enc = locale.getpreferredencoding()
        except:
            print "Locale cannot be found; please set your system's locale. Aborting..."
            sys.exit(1)

        self.all_tab_names = [self.TAB_CURRENT, self.TAB_LIBRARY, self.TAB_PLAYLISTS, self.TAB_STREAMS, self.TAB_INFO]

        # FIXME Don't subclass
        self.preferences = self
        preferences.Preferences.__init__(self)
        self.settings_load()

        if start_hidden:
            self.withdrawn = True
        if start_visible:
            self.withdrawn = False
        if self.autoconnect:
            self.user_connect = True
        if arg_profile:
            try:
                if int(a) > 0 and int(a) <= len(self.profile_names):
                    self.profile_num = int(a)-1
                    print _("Starting Sonata with profile"), self.profile_names[self.profile_num]
                else:
                    print _("Not a valid profile number. Profile number must be between 1 and"), str(len(self.profile_names)) + "."
            except:
                print _("Not a valid profile number. Profile number must be between 1 and"), str(len(self.profile_names)) + "."
                pass

        # Add some icons, assign pixbufs:
        self.iconfactory = gtk.IconFactory()
        ui.icon(self.iconfactory, 'sonata', self.find_path('sonata.png'))
        ui.icon(self.iconfactory, 'artist', self.find_path('sonata-artist.png'))
        ui.icon(self.iconfactory, 'album', self.find_path('sonata-album.png'))
        icon_theme = gtk.icon_theme_get_default()
        if HAVE_SUGAR:
            activity_root = activity.get_bundle_path()
            icon_theme.append_search_path(os.path.join(activity_root, 'share'))
        (img_width, img_height) = gtk.icon_size_lookup(VOLUME_ICON_SIZE)
        for iconname in ('stock_volume-mute', 'stock_volume-min', 'stock_volume-med', 'stock_volume-max'):
            try:
                ui.icon(self.iconfactory, iconname, icon_theme.lookup_icon(iconname, img_width, gtk.ICON_LOOKUP_USE_BUILTIN).get_filename())
            except:
                # Fallback to Sonata-included icons:
                ui.icon(self.iconfactory, iconname, self.find_path('sonata-'+iconname+'.png'))

        # Main window
        if window is None:
            self.window = gtk.Window(gtk.WINDOW_TOPLEVEL)
            self.window_owner = True
        else:
            self.window = window
            self.window_owner = False

        if self.window_owner:
            self.window.set_title('Sonata')
            self.window.set_role('mainWindow')
            self.window.set_resizable(True)
            if self.ontop:
                self.window.set_keep_above(True)
            if self.sticky:
                self.window.stick()

        self.notebook = gtk.Notebook()

        # Artwork
        if self.info_art_enlarged:
            self.info_imagebox = ui.eventbox()
        else:
            self.info_imagebox = ui.eventbox(w=152)

        self.sonatacd = self.find_path('sonatacd.png')
        self.sonatacd_large = self.find_path('sonatacd_large.png')
        self.artwork = artwork.Artwork(self.config, misc.is_lang_rtl(self.window), self.sonatacd, self.sonatacd_large, self.find_path('sonata-case.png'), self.library_browse_update, self.info_imagebox.get_size_request, self.schedule_gc_collect, self.target_image_filename, self.imagelist_append, self.remotefilelist_append, self.notebook.get_allocation, self.set_allow_art_search, self.status_is_play_or_pause)

        # Popup menus:
        actions = (
            ('sortmenu', None, _('_Sort List')),
            ('plmenu', None, _('Sa_ve List to')),
            ('profilesmenu', None, _('_Connection')),
            ('playaftermenu', None, _('P_lay after')),
            ('filesystemview', gtk.STOCK_HARDDISK, _('Filesystem'), None, None, self.on_libraryview_chosen),
            ('artistview', 'artist', _('Artist'), None, None, self.on_libraryview_chosen),
            ('genreview', gtk.STOCK_ORIENTATION_PORTRAIT, _('Genre'), None, None, self.on_libraryview_chosen),
            ('albumview', 'album', _('Album'), None, None, self.on_libraryview_chosen),
            ('chooseimage_menu', gtk.STOCK_CONVERT, _('Use _Remote Image...'), None, None, self.image_remote),
            ('localimage_menu', gtk.STOCK_OPEN, _('Use _Local Image...'), None, None, self.image_local),
            ('fullscreencoverart_menu', gtk.STOCK_FULLSCREEN, _('_Fullscreen Mode'), 'F11', None, self.fullscreen_cover_art),
            ('resetimage_menu', gtk.STOCK_CLEAR, _('Reset Image'), None, None, self.artwork.on_reset_image),
            ('playmenu', gtk.STOCK_MEDIA_PLAY, _('_Play'), None, None, self.mpd_pp),
            ('pausemenu', gtk.STOCK_MEDIA_PAUSE, _('_Pause'), None, None, self.mpd_pp),
            ('stopmenu', gtk.STOCK_MEDIA_STOP, _('_Stop'), None, None, self.mpd_stop),
            ('prevmenu', gtk.STOCK_MEDIA_PREVIOUS, _('_Previous'), None, None, self.mpd_prev),
            ('nextmenu', gtk.STOCK_MEDIA_NEXT, _('_Next'), None, None, self.mpd_next),
            ('quitmenu', gtk.STOCK_QUIT, _('_Quit'), None, None, self.on_delete_event_yes),
            ('removemenu', gtk.STOCK_REMOVE, _('_Remove'), None, None, self.on_remove),
            ('clearmenu', gtk.STOCK_CLEAR, _('_Clear'), '<Ctrl>Delete', None, self.mpd_clear),
            ('savemenu', None, _('_New...'), '<Ctrl><Shift>s', None, self.on_playlist_save),
            ('updatemenu', None, _('_Update Library'), None, None, self.on_updatedb),
            ('preferencemenu', gtk.STOCK_PREFERENCES, _('_Preferences...'), 'F5', None, self.on_prefs),
            ('aboutmenu', None, _('_About...'), 'F1', None, self.on_about),
            ('newmenu', None, _('_New...'), '<Ctrl>n', None, self.on_streams_new),
            ('editmenu', None, _('_Edit...'), None, None, self.on_streams_edit),
            ('renamemenu', None, _('_Rename...'), None, None, self.on_playlist_rename),
            ('tagmenu', None, _('_Edit Tags...'), '<Ctrl>t', None, self.on_tags_edit),
            ('addmenu', gtk.STOCK_ADD, _('_Add'), '<Ctrl>d', None, self.on_add_item),
            ('replacemenu', gtk.STOCK_REDO, _('_Replace'), '<Ctrl>r', None, self.on_replace_item),
            ('add2menu', None, _('Add'), '<Shift><Ctrl>d', None, self.on_add_item_play),
            ('replace2menu', None, _('Replace'), '<Shift><Ctrl>r', None, self.on_replace_item_play),
            ('rmmenu', None, _('_Delete...'), None, None, self.on_remove),
            ('sortbyartist', None, _('By Artist'), None, None, self.on_sort_by_artist),
            ('sortbyalbum', None, _('By Album'), None, None, self.on_sort_by_album),
            ('sortbytitle', None, _('By Song Title'), None, None, self.on_sort_by_title),
            ('sortbyfile', None, _('By File Name'), None, None, self.on_sort_by_file),
            ('sortbydirfile', None, _('By Dir & File Name'), None, None, self.on_sort_by_dirfile),
            ('sortreverse', None, _('Reverse List'), None, None, self.on_sort_reverse),
            ('sortshuffle', None, _('Shuffle'), '<Alt>r', None, self.mpd_shuffle),
            ('tab1key', None, 'Tab1 Key', '<Alt>1', None, self.on_switch_to_tab1),
            ('tab2key', None, 'Tab2 Key', '<Alt>2', None, self.on_switch_to_tab2),
            ('tab3key', None, 'Tab3 Key', '<Alt>3', None, self.on_switch_to_tab3),
            ('tab4key', None, 'Tab4 Key', '<Alt>4', None, self.on_switch_to_tab4),
            ('tab5key', None, 'Tab5 Key', '<Alt>5', None, self.on_switch_to_tab5),
            ('nexttab', None, 'Next Tab Key', '<Alt>Right', None, self.switch_to_next_tab),
            ('prevtab', None, 'Prev Tab Key', '<Alt>Left', None, self.switch_to_prev_tab),
            ('expandkey', None, 'Expand Key', '<Alt>Down', None, self.on_expand),
            ('collapsekey', None, 'Collapse Key', '<Alt>Up', None, self.on_collapse),
            ('ppkey', None, 'Play/Pause Key', '<Ctrl>p', None, self.mpd_pp),
            ('stopkey', None, 'Stop Key', '<Ctrl>s', None, self.mpd_stop),
            ('prevkey', None, 'Previous Key', '<Ctrl>Left', None, self.mpd_prev),
            ('nextkey', None, 'Next Key', '<Ctrl>Right', None, self.mpd_next),
            ('lowerkey', None, 'Lower Volume Key', '<Ctrl>minus', None, self.on_volume_lower),
            ('raisekey', None, 'Raise Volume Key', '<Ctrl>plus', None, self.on_volume_raise),
            ('raisekey2', None, 'Raise Volume Key 2', '<Ctrl>equal', None, self.on_volume_raise),
            ('quitkey', None, 'Quit Key', '<Ctrl>q', None, self.on_delete_event_yes),
            ('quitkey2', None, 'Quit Key 2', '<Ctrl>w', None, self.on_delete_event_yes),
            ('updatekey', None, 'Update Key', '<Ctrl>u', None, self.on_updatedb),
            ('updatekey2', None, 'Update Key 2', '<Ctrl><Shift>u', None, self.on_updatedb_path),
            ('connectkey', None, 'Connect Key', '<Alt>c', None, self.on_connectkey_pressed),
            ('disconnectkey', None, 'Disconnect Key', '<Alt>d', None, self.on_disconnectkey_pressed),
            ('centerplaylistkey', None, 'Center Playlist Key', '<Ctrl>i', None, self.current_center_song_in_list),
            ('searchkey', None, 'Search Key', '<Ctrl>h', None, self.on_library_search_shortcut),
            )

        toggle_actions = (
            ('showmenu', None, _('_Show Sonata'), None, None, self.on_withdraw_app_toggle, not self.withdrawn),
            ('repeatmenu', None, _('_Repeat'), None, None, self.on_repeat_clicked, False),
            ('randommenu', None, _('Rando_m'), None, None, self.on_random_clicked, False),
            (self.TAB_CURRENT, None, self.TAB_CURRENT, None, None, self.on_tab_toggle, self.current_tab_visible),
            (self.TAB_LIBRARY, None, self.TAB_LIBRARY, None, None, self.on_tab_toggle, self.library_tab_visible),
            (self.TAB_PLAYLISTS, None, self.TAB_PLAYLISTS, None, None, self.on_tab_toggle, self.playlists_tab_visible),
            (self.TAB_STREAMS, None, self.TAB_STREAMS, None, None, self.on_tab_toggle, self.streams_tab_visible),
            (self.TAB_INFO, None, self.TAB_INFO, None, None, self.on_tab_toggle, self.info_tab_visible),
            )

        uiDescription = """
            <ui>
              <popup name="imagemenu">
                <menuitem action="chooseimage_menu"/>
                <menuitem action="localimage_menu"/>
                <menuitem action="fullscreencoverart_menu"/>
                <separator name="FM1"/>
                <menuitem action="resetimage_menu"/>
              </popup>
              <popup name="traymenu">
                <menuitem action="showmenu"/>
                <separator name="FM1"/>
                <menuitem action="playmenu"/>
                <menuitem action="pausemenu"/>
                <menuitem action="stopmenu"/>
                <menuitem action="prevmenu"/>
                <menuitem action="nextmenu"/>
                <separator name="FM2"/>
                <menuitem action="quitmenu"/>
              </popup>
              <popup name="mainmenu">
                <menuitem action="addmenu"/>
                <menuitem action="replacemenu"/>
                <menu action="playaftermenu">
                  <menuitem action="add2menu"/>
                  <menuitem action="replace2menu"/>
                </menu>
                <menuitem action="newmenu"/>
                <menuitem action="editmenu"/>
                <menuitem action="removemenu"/>
                <menuitem action="clearmenu"/>
                <menuitem action="tagmenu"/>
                <menuitem action="renamemenu"/>
                <menuitem action="rmmenu"/>
                <menu action="sortmenu">
                  <menuitem action="sortbytitle"/>
                  <menuitem action="sortbyartist"/>
                  <menuitem action="sortbyalbum"/>
                  <menuitem action="sortbyfile"/>
                  <menuitem action="sortbydirfile"/>
                  <separator name="FM3"/>
                  <menuitem action="sortshuffle"/>
                  <menuitem action="sortreverse"/>
                </menu>
                <menu action="plmenu">
                  <menuitem action="savemenu"/>
                  <separator name="FM4"/>
                </menu>
                <separator name="FM1"/>
                <menuitem action="updatemenu"/>
                <menuitem action="repeatmenu"/>
                <menuitem action="randommenu"/>
                <separator name="FM2"/>
                <menu action="profilesmenu">
                </menu>
                <menuitem action="preferencemenu"/>
                <menuitem action="aboutmenu"/>
                <menuitem action="quitmenu"/>
              </popup>
              <popup name="librarymenu">
                <menuitem action="filesystemview"/>
                <menuitem action="artistview"/>
                <menuitem action="genreview"/>
                <menuitem action="albumview"/>
              </popup>
              <popup name="hidden">
                <menuitem action="quitkey"/>
                <menuitem action="quitkey2"/>
                <menuitem action="tab1key"/>
                <menuitem action="tab2key"/>
                <menuitem action="tab3key"/>
                <menuitem action="tab4key"/>
                <menuitem action="tab5key"/>
                <menuitem action="nexttab"/>
                <menuitem action="prevtab"/>
                <menuitem action="nexttab"/>
                <menuitem action="prevtab"/>
                <menuitem action="expandkey"/>
                <menuitem action="collapsekey"/>
                <menuitem action="ppkey"/>
                <menuitem action="stopkey"/>
                <menuitem action="nextkey"/>
                <menuitem action="prevkey"/>
                <menuitem action="lowerkey"/>
                <menuitem action="raisekey"/>
                <menuitem action="raisekey2"/>
                <menuitem action="updatekey"/>
                <menuitem action="updatekey2"/>
                <menuitem action="connectkey"/>
                <menuitem action="disconnectkey"/>
                <menuitem action="centerplaylistkey"/>
                <menuitem action="searchkey"/>
              </popup>
              <popup name="notebookmenu">
            """

        for tab in self.all_tab_names:
            uiDescription = uiDescription + "<menuitem action=\"" + tab + "\"/>"
        uiDescription = uiDescription + "</popup></ui>"

        # Try to connect to MPD:
        self.mpd_connect(blocking=True)
        if self.conn:
            self.status = mpdh.status(self.client)
            self.iterate_time = self.iterate_time_when_connected
            self.songinfo = mpdh.currsong(self.client)
            self.artwork.update_songinfo(self.songinfo)
        elif self.initial_run:
            show_prefs = True

        # Audioscrobbler
        self.scrobbler_import()
        self.scrobbler_init()

        # Main app:
        self.UIManager = gtk.UIManager()
        actionGroup = gtk.ActionGroup('Actions')
        actionGroup.add_actions(actions)
        actionGroup.add_toggle_actions(toggle_actions)
        self.UIManager.insert_action_group(actionGroup, 0)
        self.UIManager.add_ui_from_string(uiDescription)
        self.populate_profiles_for_menu()
        self.window.add_accel_group(self.UIManager.get_accel_group())
        self.mainmenu = self.UIManager.get_widget('/mainmenu')
        self.randommenu = self.UIManager.get_widget('/mainmenu/randommenu')
        self.repeatmenu = self.UIManager.get_widget('/mainmenu/repeatmenu')
        self.imagemenu = self.UIManager.get_widget('/imagemenu')
        self.traymenu = self.UIManager.get_widget('/traymenu')
        self.librarymenu = self.UIManager.get_widget('/librarymenu')
        self.notebookmenu = self.UIManager.get_widget('/notebookmenu')
        mainhbox = gtk.HBox()
        mainvbox = gtk.VBox()
        tophbox = gtk.HBox()

        self.albumimage = self.artwork.get_albumimage()

        self.imageeventbox = ui.eventbox(add=self.albumimage)
        self.imageeventbox.drag_dest_set(gtk.DEST_DEFAULT_HIGHLIGHT | gtk.DEST_DEFAULT_DROP, [("text/uri-list", 0, 80), ("text/plain", 0, 80)], gtk.gdk.ACTION_DEFAULT)
        if not self.show_covers:
            ui.hide(self.imageeventbox)
        tophbox.pack_start(self.imageeventbox, False, False, 5)
        topvbox = gtk.VBox()
        toptophbox = gtk.HBox()
        self.prevbutton = ui.button(stock=gtk.STOCK_MEDIA_PREVIOUS, relief=gtk.RELIEF_NONE, focus=False, hidetxt=True)
        self.ppbutton = ui.button(stock=gtk.STOCK_MEDIA_PLAY, relief=gtk.RELIEF_NONE, focus=False, hidetxt=True)
        self.stopbutton = ui.button(stock=gtk.STOCK_MEDIA_STOP, relief=gtk.RELIEF_NONE, focus=False, hidetxt=True)
        self.nextbutton = ui.button(stock=gtk.STOCK_MEDIA_NEXT, relief=gtk.RELIEF_NONE, focus=False, hidetxt=True)
        for mediabutton in (self.prevbutton, self.ppbutton, self.stopbutton, self.nextbutton):
            toptophbox.pack_start(mediabutton, False, False, 0)
            if not self.show_playback:
                ui.hide(mediabutton)
        self.progressbox = gtk.VBox()
        self.progresslabel = ui.label(w=-1, h=6)
        self.progressbox.pack_start(self.progresslabel)
        self.progressbar = ui.progressbar(orient=gtk.PROGRESS_LEFT_TO_RIGHT, frac=0, step=0.05, ellipsize=pango.ELLIPSIZE_END)
        self.progresseventbox = ui.eventbox(add=self.progressbar, visible=True)
        self.progressbox.pack_start(self.progresseventbox, False, False, 0)
        self.progresslabel2 = ui.label(w=-1, h=6)
        self.progressbox.pack_start(self.progresslabel2)
        toptophbox.pack_start(self.progressbox, True, True, 0)
        if not self.show_progress:
            ui.hide(self.progressbox)
        self.volumebutton = ui.togglebutton(relief=gtk.RELIEF_NONE, focus=False)
        self.volume_set_image("stock_volume-med")
        if not self.show_playback:
            ui.hide(self.volumebutton)
        toptophbox.pack_start(self.volumebutton, False, False, 0)
        topvbox.pack_start(toptophbox, False, False, 2)
        self.expander = ui.expander(text=_("Playlist"), expand=self.expanded, focus=False)
        expanderbox = gtk.VBox()
        self.cursonglabel1 = ui.label(y=0)
        self.cursonglabel2 = ui.label(y=0)
        expanderbox.pack_start(self.cursonglabel1, True, True, 0)
        expanderbox.pack_start(self.cursonglabel2, True, True, 0)
        self.expander.set_label_widget(expanderbox)
        topvbox.pack_start(self.expander, False, False, 2)
        tophbox.pack_start(topvbox, True, True, 3)
        mainvbox.pack_start(tophbox, False, False, 5)
        self.notebook.set_tab_pos(gtk.POS_TOP)
        self.notebook.set_scrollable(True)
        # Current tab
        self.current = ui.treeview(reorder=True, search=False, headers=True)
        self.current_selection = self.current.get_selection()
        self.expanderwindow = ui.scrollwindow(shadow=gtk.SHADOW_IN, add=self.current)
        self.filterpattern = ui.entry()
        self.filterbox = gtk.HBox()
        self.filterbox.pack_start(ui.label(text=_("Filter") + ":"), False, False, 5)
        self.filterbox.pack_start(self.filterpattern, True, True, 5)
        filterclosebutton = ui.button(img=ui.image(stock=gtk.STOCK_CLOSE), relief=gtk.RELIEF_NONE)
        self.filterbox.pack_start(filterclosebutton, False, False, 0)
        self.filterbox.set_no_show_all(True)
        vbox_current = gtk.VBox()
        vbox_current.pack_start(self.expanderwindow, True, True)
        vbox_current.pack_start(self.filterbox, False, False, 5)
        playlisthbox = gtk.HBox()
        playlisthbox.pack_start(ui.image(stock=gtk.STOCK_CDROM), False, False, 2)
        playlisthbox.pack_start(ui.label(text=self.TAB_CURRENT), False, False, 2)
        playlistevbox = ui.eventbox(add=playlisthbox)
        playlistevbox.show_all()
        playlistevbox.connect("button_press_event", self.on_tab_click)
        self.notebook.append_page(vbox_current, playlistevbox)
        current_tab = self.notebook.get_children()[0]
        if not self.current_tab_visible:
            ui.hide(current_tab)
        # Library tab
        libraryvbox = gtk.VBox()
        self.library = ui.treeview()
        self.library_selection = self.library.get_selection()
        expanderwindow2 = ui.scrollwindow(add=self.library)
        self.searchbox = gtk.HBox()
        self.searchcombo = ui.combo(list=self.search_terms)
        self.searchtext = ui.entry()
        self.searchbutton = ui.button(text=_('_End Search'), img=ui.image(stock=gtk.STOCK_CLOSE), h=self.searchcombo.size_request()[1])
        self.searchbutton.set_no_show_all(True)
        self.searchbutton.hide()
        self.libraryview = ui.button(relief=gtk.RELIEF_NONE)
        self.libraryview.set_tooltip_text(_("Library browsing view"))
        self.library_view_assign_image()
        self.librarymenu.attach_to_widget(self.libraryview, None)
        self.searchbox.pack_start(self.libraryview, False, False, 1)
        self.searchbox.pack_start(gtk.VSeparator(), False, False, 0)
        self.searchbox.pack_start(self.searchcombo, False, False, 2)
        self.searchbox.pack_start(self.searchtext, True, True, 2)
        self.searchbox.pack_start(self.searchbutton, False, False, 2)
        libraryvbox.pack_start(expanderwindow2, True, True, 2)
        libraryvbox.pack_start(self.searchbox, False, False, 2)
        libraryhbox = gtk.HBox()
        libraryhbox.pack_start(ui.image(stock=gtk.STOCK_HARDDISK), False, False, 2)
        libraryhbox.pack_start(ui.label(text=self.TAB_LIBRARY), False, False, 2)
        libraryevbox = ui.eventbox(add=libraryhbox)
        libraryevbox.show_all()
        libraryevbox.connect("button_press_event", self.on_tab_click)
        self.notebook.append_page(libraryvbox, libraryevbox)
        library_tab = self.notebook.get_children()[1]
        if not self.library_tab_visible:
            ui.hide(library_tab)
        # Playlists tab
        self.playlists = ui.treeview()
        self.playlists_selection = self.playlists.get_selection()
        expanderwindow3 = ui.scrollwindow(add=self.playlists)
        playlistshbox = gtk.HBox()
        playlistshbox.pack_start(ui.image(stock=gtk.STOCK_JUSTIFY_CENTER), False, False, 2)
        playlistshbox.pack_start(ui.label(text=self.TAB_PLAYLISTS), False, False, 2)
        playlistsevbox = ui.eventbox(add=playlistshbox)
        playlistsevbox.show_all()
        playlistsevbox.connect("button_press_event", self.on_tab_click)
        self.notebook.append_page(expanderwindow3, playlistsevbox)
        playlists_tab = self.notebook.get_children()[2]
        if not self.playlists_tab_visible:
            ui.hide(playlists_tab)
        # Streams tab
        self.streams = ui.treeview()
        self.streams_selection = self.streams.get_selection()
        expanderwindow4 = ui.scrollwindow(add=self.streams)
        streamshbox = gtk.HBox()
        streamshbox.pack_start(ui.image(stock=gtk.STOCK_NETWORK), False, False, 2)
        streamshbox.pack_start(ui.label(text=self.TAB_STREAMS), False, False, 2)
        streamsevbox = ui.eventbox(add=streamshbox)
        streamsevbox.show_all()
        streamsevbox.connect("button_press_event", self.on_tab_click)
        self.notebook.append_page(expanderwindow4, streamsevbox)
        streams_tab = self.notebook.get_children()[3]
        if not self.streams_tab_visible:
            ui.hide(streams_tab)
        # Info tab
        self.info = ui.scrollwindow()
        infohbox = gtk.HBox()
        infohbox.pack_start(ui.image(stock=gtk.STOCK_JUSTIFY_FILL), False, False, 2)
        infohbox.pack_start(ui.label(text=self.TAB_INFO), False, False, 2)
        infoevbox = ui.eventbox(add=infohbox)
        infoevbox.show_all()
        infoevbox.connect("button_press_event", self.on_tab_click)
        self.info_widgets_initialize(self.info)
        self.notebook.append_page(self.info, infoevbox)
        mainvbox.pack_start(self.notebook, True, True, 5)
        info_tab = self.notebook.get_children()[4]
        if not self.info_tab_visible:
            ui.hide(info_tab)
        self.statusbar = gtk.Statusbar()
        self.statusbar.set_has_resize_grip(True)
        if not self.show_statusbar or not self.expanded:
            ui.hide(self.statusbar)
        mainvbox.pack_start(self.statusbar, False, False, 0)
        mainhbox.pack_start(mainvbox, True, True, 3)
        if self.window_owner:
            self.window.add(mainhbox)
            self.window.move(self.x, self.y)
            self.window.set_size_request(270, -1)
        elif HAVE_SUGAR:
            self.window.set_canvas(mainhbox)
        if not self.expanded:
            ui.hide(self.notebook)
            self.cursonglabel1.set_markup('<big><b>' + _('Stopped') + '</b></big>')
            self.cursonglabel2.set_markup('<small>' + _('Click to expand') + '</small>')
            if self.window_owner:
                self.window.set_default_size(self.w, 1)
        else:
            self.cursonglabel1.set_markup('<big><b>' + _('Stopped') + '</b></big>')
            self.cursonglabel2.set_markup('<small>' + _('Click to collapse') + '</small>')
            if self.window_owner:
                self.window.set_default_size(self.w, self.h)
        self.expander.set_tooltip_text(self.cursonglabel1.get_text())
        if not self.conn:
            self.progressbar.set_text(_('Not Connected'))
        elif not self.status:
            self.progressbar.set_text(_('No Read Permission'))
        self.libraryview.set_tooltip_text(_("Library browsing view"))
        for child in self.notebook.get_children():
            self.notebook.set_tab_reorderable(child, True)
            if self.tabs_expanded:
                self.notebook.set_tab_label_packing(child, True, True, gtk.PACK_START)
        # Update tab positions:
        self.notebook.reorder_child(current_tab, self.current_tab_pos)
        self.notebook.reorder_child(library_tab, self.library_tab_pos)
        self.notebook.reorder_child(playlists_tab, self.playlists_tab_pos)
        self.notebook.reorder_child(streams_tab, self.streams_tab_pos)
        self.notebook.reorder_child(info_tab, self.info_tab_pos)
        self.last_tab = self.notebook_get_tab_text(self.notebook, 0)

        # Song notification window:
        outtertipbox = gtk.VBox()
        tipbox = gtk.HBox()

        self.trayalbumeventbox, self.trayalbumimage2 = self.artwork.get_trayalbum()

        hiddenlbl = ui.label(w=2, h=-1)
        tipbox.pack_start(hiddenlbl, False, False, 0)
        tipbox.pack_start(self.trayalbumeventbox, False, False, 0)

        tipbox.pack_start(self.trayalbumimage2, False, False, 0)
        if not self.show_covers:
            ui.hide(self.trayalbumeventbox)
            ui.hide(self.trayalbumimage2)
        innerbox = gtk.VBox()
        self.traycursonglabel1 = ui.label(markup=_("Playlist"), y=1)
        self.traycursonglabel2 = ui.label(markup=_("Playlist"), y=0)
        label1 = ui.label(markup='<span size="10"> </span>')
        innerbox.pack_start(label1)
        innerbox.pack_start(self.traycursonglabel1, True, True, 0)
        innerbox.pack_start(self.traycursonglabel2, True, True, 0)
        self.trayprogressbar = ui.progressbar(orient=gtk.PROGRESS_LEFT_TO_RIGHT, frac=0, step=0.05, ellipsize=pango.ELLIPSIZE_NONE)
        label2 = ui.label(markup='<span size="10"> </span>')
        innerbox.pack_start(label2)
        innerbox.pack_start(self.trayprogressbar, False, False, 0)
        if not self.show_progress:
            ui.hide(self.trayprogressbar)
        label3 = ui.label(markup='<span size="10"> </span>')
        innerbox.pack_start(label3)
        tipbox.pack_start(innerbox, True, True, 6)
        outtertipbox.pack_start(tipbox, False, False, 2)
        outtertipbox.show_all()
        self.traytips.add_widget(outtertipbox)
        self.tooltip_set_window_width()

        # Volumescale window
        self.volumewindow = gtk.Window(gtk.WINDOW_POPUP)
        self.volumewindow.set_skip_taskbar_hint(True)
        self.volumewindow.set_skip_pager_hint(True)
        self.volumewindow.set_decorated(False)
        frame = gtk.Frame()
        frame.set_shadow_type(gtk.SHADOW_ETCHED_IN)
        self.volumewindow.add(frame)
        volbox = gtk.VBox()
        volbox.pack_start(ui.label(text="+"), False, False, 0)
        self.volumescale = gtk.VScale()
        self.volumescale.set_draw_value(True)
        self.volumescale.set_value_pos(gtk.POS_TOP)
        self.volumescale.set_digits(0)
        self.volumescale.set_update_policy(gtk.UPDATE_CONTINUOUS)
        self.volumescale.set_inverted(True)
        self.volumescale.set_adjustment(gtk.Adjustment(0, 0, 100, 0, 0, 0))
        if HAVE_SUGAR:
            self.volumescale.set_size_request(-1, 203)
        else:
            self.volumescale.set_size_request(-1, 103)
        volbox.pack_start(self.volumescale, True, True, 0)
        volbox.pack_start(ui.label(text="-"), False, False, 0)
        frame.add(volbox)
        ui.show(frame)

        # Fullscreen cover art window
        self.fullscreencoverart = gtk.Window()
        self.fullscreencoverart.set_title(_("Cover Art"))
        self.fullscreencoverart.set_decorated(True)
        self.fullscreencoverart.fullscreen()
        self.fullscreencoverart.modify_bg(gtk.STATE_NORMAL, gtk.gdk.color_parse("black"))
        self.fullscreencoverart.add_accel_group(self.UIManager.get_accel_group())
        fscavbox = gtk.VBox()
        fscahbox = gtk.HBox()
        self.fullscreenalbumimage = self.artwork.get_fullscreenalbumimage()
        fscahbox.pack_start(self.fullscreenalbumimage, True, False, 0)
        fscavbox.pack_start(fscahbox, True, False, 0)
        if not self.show_covers:
            ui.hide(self.fullscreenalbumimage)
        self.fullscreencoverart.add(fscavbox)

        # Connect to signals
        self.window.add_events(gtk.gdk.BUTTON_PRESS_MASK)
        self.traytips.add_events(gtk.gdk.BUTTON_PRESS_MASK)
        self.traytips.connect('button_press_event', self.on_traytips_press)
        self.window.connect('delete_event', self.on_delete_event)
        self.window.connect('window_state_event', self.on_window_state_change)
        self.window.connect('configure_event', self.on_window_configure)
        self.window.connect('key-press-event', self.on_topwindow_keypress)
        self.window.connect('focus-out-event', self.on_window_lost_focus)
        self.imageeventbox.connect('button_press_event', self.on_image_activate)
        self.imageeventbox.connect('drag_motion', self.on_image_motion_cb)
        self.imageeventbox.connect('drag_data_received', self.on_image_drop_cb)
        self.ppbutton.connect('clicked', self.mpd_pp)
        self.stopbutton.connect('clicked', self.mpd_stop)
        self.prevbutton.connect('clicked', self.mpd_prev)
        self.nextbutton.connect('clicked', self.mpd_next)
        self.progresseventbox.connect('button_press_event', self.on_progressbar_press)
        self.progresseventbox.connect('scroll_event', self.on_progressbar_scroll)
        self.volumebutton.connect('clicked', self.on_volumebutton_clicked)
        self.volumebutton.connect('scroll-event', self.on_volumebutton_scroll)
        self.expander.connect('activate', self.on_expander_activate)
        self.current.connect('drag_data_received', self.on_dnd)
        self.current.connect('row_activated', self.on_current_click)
        self.current.connect('button_press_event', self.on_current_button_press)
        self.current.connect('drag-begin', self.on_current_drag_begin)
        self.current.connect_after('drag-begin', self.dnd_after_current_drag_begin)
        self.current.connect('button_release_event', self.on_current_button_release)
        self.randommenu.connect('toggled', self.on_random_clicked)
        self.repeatmenu.connect('toggled', self.on_repeat_clicked)
        self.volumescale.connect('change_value', self.on_volumescale_change)
        self.volumescale.connect('scroll-event', self.on_volumescale_scroll)
        self.cursonglabel1.connect('notify::label', self.on_currsong_notify)
        self.progressbar.connect('notify::fraction', self.on_progressbar_notify_fraction)
        self.progressbar.connect('notify::text', self.on_progressbar_notify_text)
        self.library.connect('row_activated', self.on_library_row_activated)
        self.library.connect('button_press_event', self.on_library_button_press)
        self.library.connect('key-press-event', self.on_library_key_press)
        self.library.connect('query-tooltip', self.on_library_query_tooltip)
        self.libraryview.connect('clicked', self.library_view_popup)
        self.playlists.connect('button_press_event', self.on_playlists_button_press)
        self.playlists.connect('row_activated', self.playlists_activated)
        self.playlists.connect('key-press-event', self.playlists_key_press)
        self.streams.connect('button_press_event', self.on_streams_button_press)
        self.streams.connect('row_activated', self.on_streams_activated)
        self.streams.connect('key-press-event', self.on_streams_key_press)
        self.mainwinhandler = self.window.connect('button_press_event', self.on_window_click)
        self.notebook.connect('button_press_event', self.on_notebook_click)
        self.notebook.connect('size-allocate', self.on_notebook_resize)
        self.notebook.connect('switch-page', self.on_notebook_page_change)
        self.searchtext.connect('button_press_event', self.on_library_search_text_click)
        self.searchtext.connect('key-press-event', self.libsearchfilter_key_pressed)
        self.searchtext.connect('activate', self.libsearchfilter_on_enter)
        self.libfilter_changed_handler = self.searchtext.connect('changed', self.libsearchfilter_feed_loop)
        searchcombo_changed_handler = self.searchcombo.connect('changed', self.on_library_search_combo_change)
        self.searchbutton.connect('clicked', self.on_library_search_end)
        self.filter_changed_handler = self.filterpattern.connect('changed', self.searchfilter_feed_loop)
        self.filterpattern.connect('activate', self.searchfilter_on_enter)
        self.filterpattern.connect('key-press-event', self.searchfilter_key_pressed)
        filterclosebutton.connect('clicked', self.searchfilter_toggle)
        self.fullscreencoverart.add_events(gtk.gdk.BUTTON_PRESS_MASK | gtk.gdk.BUTTON_PRESS_MASK)
        self.fullscreencoverart.connect("button-press-event", self.fullscreen_cover_art_close, False)
        self.fullscreencoverart.connect("key-press-event", self.fullscreen_cover_art_close, True)
        for treeview in [self.current, self.library, self.playlists, self.streams]:
            treeview.connect('popup_menu', self.on_menu_popup)
        for treeviewsel in [self.current_selection, self.library_selection, self.playlists_selection, self.streams_selection]:
            treeviewsel.connect('changed', self.on_treeview_selection_changed)
        for widget in [self.ppbutton, self.prevbutton, self.stopbutton, self.nextbutton, self.progresseventbox, self.expander, self.volumebutton]:
            widget.connect('button_press_event', self.menu_popup)

        self.systemtray_initialize()

        # This will ensure that "Not connected" is shown in the systray tooltip
        if not self.conn:
            self.update_cursong()

        # Ensure that the systemtray icon is added here. This is really only
        # important if we're starting in hidden (minimized-to-tray) mode:
        if self.window_owner and self.withdrawn:
            while gtk.events_pending():
                gtk.main_iteration()

        # Connect to mmkeys signals
        if HAVE_MMKEYS:
            self.keys = mmkeys.MmKeys()
            self.keys.connect("mm_prev", self.mpd_prev)
            self.keys.connect("mm_next", self.mpd_next)
            self.keys.connect("mm_playpause", self.mpd_pp)
            self.keys.connect("mm_stop", self.mpd_stop)

        # Set up current view
        self.current_initialize_columns()
        self.current_selection.set_mode(gtk.SELECTION_MULTIPLE)
        target_reorder = ('MY_TREE_MODEL_ROW', gtk.TARGET_SAME_WIDGET, 0)
        target_file_managers = ('text/uri-list', 0, 0)
        self.current.enable_model_drag_source(gtk.gdk.BUTTON1_MASK, [target_reorder, target_file_managers], gtk.gdk.ACTION_COPY | gtk.gdk.ACTION_DEFAULT)
        self.current.enable_model_drag_dest([target_reorder, target_file_managers], gtk.gdk.ACTION_MOVE | gtk.gdk.ACTION_DEFAULT)
        self.current.connect('drag-data-get', self.dnd_get_data_for_file_managers)

        # Initialize playlist data and widget
        self.playlistsdata = gtk.ListStore(str, str)
        self.playlists.set_model(self.playlistsdata)
        self.playlists.set_search_column(1)
        self.playlistsimg = gtk.CellRendererPixbuf()
        self.playlistscell = gtk.CellRendererText()
        self.playlistscell.set_property("ellipsize", pango.ELLIPSIZE_END)
        self.playlistscolumn = gtk.TreeViewColumn()
        self.playlistscolumn.pack_start(self.playlistsimg, False)
        self.playlistscolumn.pack_start(self.playlistscell, True)
        self.playlistscolumn.set_attributes(self.playlistsimg, stock_id=0)
        self.playlistscolumn.set_attributes(self.playlistscell, markup=1)
        self.playlists.append_column(self.playlistscolumn)
        self.playlists_selection.set_mode(gtk.SELECTION_MULTIPLE)

        # Initialize streams data and widget
        self.streamsdata = gtk.ListStore(str, str, str)
        self.streams.set_model(self.streamsdata)
        self.streams.set_search_column(1)
        self.streamsimg = gtk.CellRendererPixbuf()
        self.streamscell = gtk.CellRendererText()
        self.streamscell.set_property("ellipsize", pango.ELLIPSIZE_END)
        self.streamscolumn = gtk.TreeViewColumn()
        self.streamscolumn.pack_start(self.streamsimg, False)
        self.streamscolumn.pack_start(self.streamscell, True)
        self.streamscolumn.set_attributes(self.streamsimg, stock_id=0)
        self.streamscolumn.set_attributes(self.streamscell, markup=1)
        self.streams.append_column(self.streamscolumn)
        self.streams_selection.set_mode(gtk.SELECTION_MULTIPLE)

        # Initialize library data and widget
        self.libraryposition = {}
        self.libraryselectedpath = {}
        self.searchcombo.handler_block(searchcombo_changed_handler)
        self.searchcombo.set_active(self.last_search_num)
        self.searchcombo.handler_unblock(searchcombo_changed_handler)
        self.prevstatus = None
        self.librarydata = gtk.ListStore(gtk.gdk.Pixbuf, str, str)
        self.library.set_model(self.librarydata)
        self.library.set_search_column(2)
        self.librarycell = gtk.CellRendererText()
        self.librarycell.set_property("ellipsize", pango.ELLIPSIZE_END)
        self.libraryimg = gtk.CellRendererPixbuf()
        self.librarycolumn = gtk.TreeViewColumn()
        self.librarycolumn.pack_start(self.libraryimg, False)
        self.librarycolumn.pack_start(self.librarycell, True)
        self.librarycolumn.set_attributes(self.libraryimg, pixbuf=0)
        self.librarycolumn.set_attributes(self.librarycell, markup=2)
        self.librarycolumn.set_sizing(gtk.TREE_VIEW_COLUMN_AUTOSIZE)
        self.library.append_column(self.librarycolumn)
        self.library_selection.set_mode(gtk.SELECTION_MULTIPLE)

        # Assign some pixbufs for use in self.library
        self.openpb = self.library.render_icon(gtk.STOCK_OPEN, gtk.ICON_SIZE_LARGE_TOOLBAR)
        self.harddiskpb = self.library.render_icon(gtk.STOCK_HARDDISK, gtk.ICON_SIZE_LARGE_TOOLBAR)
        self.albumpb = gtk.gdk.pixbuf_new_from_file_at_size(self.find_path('sonata-album.png'), self.LIB_COVER_SIZE, self.LIB_COVER_SIZE)
        self.genrepb = self.library.render_icon('gtk-orientation-portrait', gtk.ICON_SIZE_LARGE_TOOLBAR)
        self.artistpb = self.library.render_icon('artist', gtk.ICON_SIZE_LARGE_TOOLBAR)
        self.sonatapb = self.library.render_icon('sonata', gtk.ICON_SIZE_MENU)

        if self.window_owner:
            icon = self.window.render_icon('sonata', gtk.ICON_SIZE_DIALOG)
            self.window.set_icon(icon)

        self.streams_populate()

        self.iterate_now()
        if self.window_owner:
            if self.withdrawn:
                if (HAVE_EGG and self.trayicon.get_property('visible')) or (HAVE_STATUS_ICON and self.statusicon.is_embedded() and self.statusicon.get_visible()):
                    ui.hide(self.window)
        self.window.show_all()

        # Ensure that button images are displayed despite GTK+ theme
        self.window.get_settings().set_property("gtk-button-images", True)

        if self.update_on_start:
            self.on_updatedb(None)

        self.notebook.set_no_show_all(False)
        self.window.set_no_show_all(False)

        if show_prefs:
            self.on_prefs(None)

        self.initial_run = False

        # Ensure that sonata is loaded before we display the notif window
        self.sonata_loaded = True
        self.on_currsong_notify()
        self.current_center_song_in_list()

        if HAVE_STATUS_ICON:
            gobject.timeout_add(250, self.iterate_status_icon)

        gc.disable()

        gobject.idle_add(self.header_save_column_widths)

    def dnd_get_data_for_file_managers(self, treeview, context, selection, info, timestamp):

        if not os.path.isdir(self.musicdir[self.profile_num]):
            # Prevent the DND mouse cursor from looking like we can DND
            # when we clearly can't.
            return

        context.drag_status(gtk.gdk.ACTION_COPY, context.start_time)

        filenames = self.current_get_selected_filenames(True)

        uris = []
        for file in filenames:
            uris.append("file://" + urllib.quote(file))

        selection.set_uris(uris)
        return

    def current_get_selected_filenames(self, return_abs_paths):
        model, selected = self.current_selection.get_selected_rows()
        filenames = []

        for path in selected:
            if not self.filterbox_visible:
                item = mpdh.get(self.current_songs[path[0]], 'file')
            else:
                item = mpdh.get(self.current_songs[self.filter_row_mapping[path[0]]], 'file')
            if return_abs_paths:
                filenames.append(self.musicdir[self.profile_num] + item)
            else:
                filenames.append(item)
        return filenames

    def print_version(self):
        print _("Version: Sonata"), __version__
        print _("Website: http://sonata.berlios.de/")

    def print_usage(self):
        self.print_version()
        print ""
        print _("Usage: sonata [OPTION]")
        print ""
        print _("Options") + ":"
        print "  -h, --help           " + _("Show this help and exit")
        print "  -p, --popup          " + _("Popup song notification (requires DBus)")
        print "  -t, --toggle         " + _("Toggles whether the app is minimized")
        print "                       " + _("to tray or visible (requires D-Bus)")
        print "  -v, --version        " + _("Show version information and exit")
        print "  --hidden             " + _("Start app hidden (requires systray)")
        print "  --visible            " + _("Start app visible (requires systray)")
        print "  --profile=[NUM]      " + _("Start with profile [NUM]")
        print "  play                 " + _("Play song in playlist")
        print "  pause                " + _("Pause currently playing song")
        print "  stop                 " + _("Stop currently playing song")
        print "  next                 " + _("Play next song in playlist")
        print "  prev                 " + _("Play previous song in playlist")
        print "  pp                   " + _("Toggle play/pause; plays if stopped")
        print "  repeat               " + _("Toggle repeat mode")
        print "  random               " + _("Toggle random mode")
        print "  info                 " + _("Display current song info")
        print "  status               " + _("Display MPD status")

    def info_widgets_initialize(self, info_scrollwindow):
        vert_spacing = 1
        horiz_spacing = 2
        margin = 5
        outter_hbox = gtk.HBox()
        outter_vbox = gtk.VBox()

        # Realizing self.window will allow us to retrieve the theme's
        # link-color; we can then apply to it various widgets:
        try:
            self.window.realize()
            self.linkcolor = self.window.style_get_property("link-color").to_string()
        except:
            self.linkcolor = None

        # Song info
        info_song = ui.expander(markup="<b>" + _("Song Info") + "</b>", expand=self.info_song_expanded, focus=False)
        info_song.connect("activate", self.info_expanded, "song")
        inner_hbox = gtk.HBox()

        self.info_image = self.artwork.get_info_image()

        self.info_imagebox.add(self.info_image)

        self.info_imagebox.drag_dest_set(gtk.DEST_DEFAULT_HIGHLIGHT | gtk.DEST_DEFAULT_DROP, [("text/uri-list", 0, 80), ("text/plain", 0, 80)], gtk.gdk.ACTION_DEFAULT)
        self.info_imagebox.connect('button_press_event', self.on_image_activate)
        self.info_imagebox.connect('drag_motion', self.on_image_motion_cb)
        self.info_imagebox.connect('drag_data_received', self.on_image_drop_cb)
        inner_hbox.pack_start(self.info_imagebox, False, False, horiz_spacing)
        gobject.idle_add(self.info_image.set_from_file, self.sonatacd_large)

        self.info_tagbox = gtk.VBox()

        labels_left = []
        self.info_type = {}
        self.info_labels = []
        self.info_boxes_in_more = []
        labels_type = ['title', 'artist', 'album', 'date', 'track', 'genre', 'file', 'bitrate']
        labels_text = [_("Title"), _("Artist"), _("Album"), _("Date"), _("Track"), _("Genre"), _("File"), _("Bitrate")]
        labels_link = [False, True, True, False, False, False, False, False]
        labels_tooltip = ["", _("Launch artist in Wikipedia"), _("Launch album in Wikipedia"), "", "", "", "", ""]
        labels_in_more = [False, False, False, False, False, False, True, True]
        for i in range(len(labels_text)):
            self.info_type[labels_text[i]] = i
            tmphbox = gtk.HBox()
            if labels_in_more[i]:
                self.info_boxes_in_more += [tmphbox]
            tmplabel = ui.label(markup="<b>" + labels_text[i] + ":</b>", y=0)
            if i == 0:
                self.info_left_label = tmplabel
            if not labels_link[i]:
                tmplabel2 = ui.label(wrap=True, y=0, select=True)
            else:
                # Using set_selectable overrides the hover cursor that sonata
                # tries to set for the links, and I can't figure out how to
                # stop that. So we'll disable set_selectable for these two
                # labels until it's figured out.
                tmplabel2 = ui.label(wrap=True, y=0, select=False)
            if labels_link[i]:
                tmpevbox = ui.eventbox(add=tmplabel2)
                self.info_apply_link_signals(tmpevbox, labels_type[i], labels_tooltip[i])
            tmphbox.pack_start(tmplabel, False, False, horiz_spacing)
            if labels_link[i]:
                tmphbox.pack_start(tmpevbox, False, False, horiz_spacing)
            else:
                tmphbox.pack_start(tmplabel2, False, False, horiz_spacing)
            self.info_labels += [tmplabel2]
            labels_left += [tmplabel]
            self.info_tagbox.pack_start(tmphbox, False, False, vert_spacing)
        ui.set_widths_equal(labels_left)

        mischbox = gtk.HBox()
        self.info_morelabel = ui.label(y=0)
        moreevbox = ui.eventbox(add=self.info_morelabel)
        self.info_apply_link_signals(moreevbox, 'more', _("Toggle extra tags"))
        self.info_editlabel = ui.label(y=0)
        editevbox = ui.eventbox(add=self.info_editlabel)
        self.info_apply_link_signals(editevbox, 'edit', _("Edit song tags"))
        mischbox.pack_start(moreevbox, False, False, horiz_spacing)
        mischbox.pack_start(editevbox, False, False, horiz_spacing)

        self.info_tagbox.pack_start(mischbox, False, False, vert_spacing)
        inner_hbox.pack_start(self.info_tagbox, False, False, horiz_spacing)
        info_song.add(inner_hbox)
        outter_vbox.pack_start(info_song, False, False, margin)

        # Lyrics
        self.info_lyrics = ui.expander(markup="<b>" + _("Lyrics") + "</b>", expand=self.info_lyrics_expanded, focus=False)
        self.info_lyrics.connect("activate", self.info_expanded, "lyrics")
        lyricsbox = gtk.VBox()
        lyricsbox_top = gtk.HBox()
        self.lyricsText = ui.label(markup=" ", y=0, select=True, wrap=True)
        lyricsbox_top.pack_start(self.lyricsText, True, True, horiz_spacing)
        lyricsbox.pack_start(lyricsbox_top, True, True, vert_spacing)
        lyricsbox_bottom = gtk.HBox()
        self.info_searchlabel = ui.label(y=0)
        self.info_editlyricslabel = ui.label(y=0)
        searchevbox = ui.eventbox(add=self.info_searchlabel)
        editlyricsevbox = ui.eventbox(add=self.info_editlyricslabel)
        self.info_apply_link_signals(searchevbox, 'search', _("Search Lyricwiki.org for lyrics"))
        self.info_apply_link_signals(editlyricsevbox, 'editlyrics', _("Edit lyrics at Lyricwiki.org"))
        lyricsbox_bottom.pack_start(searchevbox, False, False, horiz_spacing)
        lyricsbox_bottom.pack_start(editlyricsevbox, False, False, horiz_spacing)
        lyricsbox.pack_start(lyricsbox_bottom, False, False, vert_spacing)
        self.info_lyrics.add(lyricsbox)
        outter_vbox.pack_start(self.info_lyrics, False, False, margin)

        # Album info
        info_album = ui.expander(markup="<b>" + _("Album Info") + "</b>", expand=self.info_album_expanded, focus=False)
        info_album.connect("activate", self.info_expanded, "album")
        albumbox = gtk.VBox()
        albumbox_top = gtk.HBox()
        self.albumText = ui.label(markup=" ", y=0, select=True, wrap=True)
        albumbox_top.pack_start(self.albumText, False, False, horiz_spacing)
        albumbox.pack_start(albumbox_top, False, False, vert_spacing)
        info_album.add(albumbox)
        outter_vbox.pack_start(info_album, False, False, margin)

        # Finish..
        if not self.show_lyrics:
            ui.hide(self.info_lyrics)
        if not self.show_covers:
            ui.hide(self.info_imagebox)
        # self.info_song_more will be overridden on on_link_click, so
        # store it in a temporary var..
        temp = self.info_song_more
        self.on_link_click(moreevbox, None, 'more')
        self.info_song_more = temp
        if self.info_song_more:
            self.on_link_click(moreevbox, None, 'more')
        outter_hbox.pack_start(outter_vbox, False, False, margin)
        info_scrollwindow.add_with_viewport(outter_hbox)

    def info_expanded(self, expander, type):
        expanded = not expander.get_expanded()
        if type == "song":
            self.info_song_expanded = expanded
        elif type == "lyrics":
            self.info_lyrics_expanded = expanded
        elif type == "album":
            self.info_album_expanded = expanded

    def info_apply_link_signals(self, widget, type, tooltip):
        widget.connect("enter-notify-event", self.on_link_enter)
        widget.connect("leave-notify-event", self.on_link_leave)
        widget.connect("button-press-event", self.on_link_click, type)
        widget.set_tooltip_text(tooltip)

    def current_initialize_columns(self):
        # Initialize current playlist data and widget
        self.resizing_columns = False
        self.columnformat = self.currentformat.split("|")
        self.currentdata = gtk.ListStore(*([int] + [str] * len(self.columnformat)))
        self.current.set_model(self.currentdata)
        cellrenderer = gtk.CellRendererText()
        cellrenderer.set_property("ellipsize", pango.ELLIPSIZE_END)
        self.columns = []
        colnames = self.parse_formatting_colnames(self.currentformat)
        if len(self.columnformat) != len(self.columnwidths):
            # Number of columns changed, set columns equally spaced:
            self.columnwidths = []
            for i in range(len(self.columnformat)):
                self.columnwidths.append(int(self.current.allocation.width/len(self.columnformat)))
        for i in range(len(self.columnformat)):
            column = gtk.TreeViewColumn(colnames[i], cellrenderer, markup=(i+1))
            self.columns += [column]
            column.set_sizing(gtk.TREE_VIEW_COLUMN_FIXED)
            # If just one column, we want it to expand with the tree, so don't set a
            # fixed_width; if multiple columns, size accordingly:
            if len(self.columnformat) > 1:
                column.set_resizable(True)
                try:
                    column.set_fixed_width(max(self.columnwidths[i], 10))
                except:
                    column.set_fixed_width(150)
            column.connect('clicked', self.on_current_column_click)
            self.current.append_column(column)
        self.current.set_fixed_height_mode(True)
        self.current.set_headers_visible(len(self.columnformat) > 1 and self.show_header)
        self.current.set_headers_clickable(not self.filterbox_visible)

    def gnome_session_management(self):
        try:
            import gnome, gnome.ui
            # Code thanks to quodlibet:
            gnome.init("sonata", __version__)
            client = gnome.ui.master_client()
            client.set_restart_style(gnome.ui.RESTART_IF_RUNNING)
            command = os.path.normpath(os.path.join(os.getcwd(), sys.argv[0]))
            try:
                client.set_restart_command([command] + sys.argv[1:])
            except TypeError:
                # Fedora systems have a broken gnome-python wrapper for this function.
                # http://www.sacredchao.net/quodlibet/ticket/591
                # http://trac.gajim.org/ticket/929
                client.set_restart_command(len(sys.argv), [command] + sys.argv[1:])
            client.connect('die', gtk.main_quit)
        except:
            pass

    def single_connect_for_passed_arg(self, type):
        self.user_connect = True
        self.settings_load()
        self.mpd_connect(blocking=True, force=True)
        if self.conn:
            self.status = mpdh.status(self.client)
            self.songinfo = mpdh.currsong(self.client)
            if type == "play":
                mpdh.call(self.client, 'play')
            elif type == "pause":
                mpdh.call(self.client, 'pause', 1)
            elif type == "stop":
                mpdh.call(self.client, 'stop')
            elif type == "next":
                mpdh.call(self.client, 'next')
            elif type == "prev":
                mpdh.call(self.client, 'previous')
            elif type == "random":
                if self.status:
                    if self.status['random'] == '0':
                        mpdh.call(self.client, 'random', 1)
                    else:
                        mpdh.call(self.client, 'random', 0)
            elif type == "repeat":
                if self.status:
                    if self.status['repeat'] == '0':
                        mpdh.call(self.client, 'repeat', 1)
                    else:
                        mpdh.call(self.client, 'repeat', 0)
            elif type == "pp":
                self.status = mpdh.status(self.client)
                if self.status:
                    if self.status['state'] in ['play']:
                        mpdh.call(self.client, 'pause', 1)
                    elif self.status['state'] in ['pause', 'stop']:
                        mpdh.call(self.client, 'play')
            elif type == "info":
                if self.status and self.status['state'] in ['play', 'pause']:
                    mpdh.conout (_("Title") + ": " + mpdh.get(self.songinfo, 'title'))
                    mpdh.conout (_("Artist") + ": " + mpdh.get(self.songinfo, 'artist'))
                    mpdh.conout (_("Album") + ": " + mpdh.get(self.songinfo, 'album'))
                    mpdh.conout (_("Date") + ": " + mpdh.get(self.songinfo, 'date'))
                    mpdh.conout (_("Track") + ": " + mpdh.getnum(self.songinfo, 'track', '0', False, 2))
                    mpdh.conout (_("Genre") + ": " + mpdh.get(self.songinfo, 'genre'))
                    mpdh.conout (_("File") + ": " + os.path.basename(mpdh.get(self.songinfo, 'file')))
                    at, length = [int(c) for c in self.status['time'].split(':')]
                    at_time = misc.convert_time(at)
                    try:
                        time = misc.convert_time(int(mpdh.get(self.songinfo, 'time')))
                        print _("Time") + ": " + at_time + " / " + time
                    except:
                        print _("Time") + ": " + at_time
                    print _("Bitrate") + ": " + self.status.get('bitrate', '')
                else:
                    print _("MPD stopped")
            elif type == "status":
                if self.status:
                    try:
                        if self.status['state'] == 'play':
                            print _("State") + ": " + _("Playing")
                        elif self.status['state'] == 'pause':
                            print _("State") + ": " + _("Paused")
                        elif self.status['state'] == 'stop':
                            print _("State") + ": " + _("Stopped")
                        if self.status['repeat'] == '0':
                            print _("Repeat") + ": " + _("Off")
                        else:
                            print _("Repeat") + ": " + _("On")
                        if self.status['random'] == '0':
                            print _("Random") + ": " + _("Off")
                        else:
                            print _("Random") + ": " + _("On")
                        print _("Volume") + ": " + self.status['volume'] + "/100"
                        print _('Crossfade') + ": " + self.status['xfade'] + ' ' + gettext.ngettext('second', 'seconds', int(self.status['xfade']))
                    except:
                        pass
        else:
            print _("Unable to connect to MPD.\nPlease check your Sonata preferences or MPD_HOST/MPD_PORT environment variables.")

    def populate_playlists_for_menu(self, playlistinfo):
        if self.mergepl_id:
            self.UIManager.remove_ui(self.mergepl_id)
        if self.actionGroupPlaylists:
            self.UIManager.remove_action_group(self.actionGroupPlaylists)
            self.actionGroupPlaylists = None
        self.actionGroupPlaylists = gtk.ActionGroup('MPDPlaylists')
        self.UIManager.ensure_update()
        actions = []
        for i in range(len(playlistinfo)):
            action_name = "Playlist: " + playlistinfo[i].replace("&", "")
            actions.append((action_name, gtk.STOCK_JUSTIFY_CENTER, misc.unescape_html(playlistinfo[i]), None, None, self.on_playlist_menu_click))
        self.actionGroupPlaylists.add_actions(actions)
        uiDescription = """
            <ui>
              <popup name="mainmenu">
                  <menu action="plmenu">
            """
        for i in range(len(playlistinfo)):
            action_name = "Playlist: " + playlistinfo[i].replace("&", "")
            uiDescription = uiDescription + """<menuitem action=\"""" + action_name + """\" position="bottom"/>"""
        uiDescription = uiDescription + """</menu></popup></ui>"""
        self.mergepl_id = self.UIManager.add_ui_from_string(uiDescription)
        self.UIManager.insert_action_group(self.actionGroupPlaylists, 0)
        self.UIManager.get_widget('/hidden').set_property('visible', False)
        # If we're not on the Current tab, prevent additional menu items
        # from displaying:
        self.update_menu_visibility()

    def profile_menu_name(self, profile_num):
        return _("Profile") + ": " + self.profile_names[profile_num].replace("&", "")

    def populate_profiles_for_menu(self):
        host, port, password = misc.mpd_env_vars()
        if self.merge_id:
            self.UIManager.remove_ui(self.merge_id)
        if self.actionGroupProfiles:
            self.UIManager.remove_action_group(self.actionGroupProfiles)
            self.actionGroupProfiles = None
        self.actionGroupProfiles = gtk.ActionGroup('MPDProfiles')
        self.UIManager.ensure_update()
        actions = []
        if host or port:
            action_name = _("Profile") + ": " + _("MPD_HOST/PORT")
            actions.append((action_name, None, _("MPD_HOST/PORT").replace("_", "__"), None, None, 0))
            actions.append(('disconnect', None, _('Disconnect'), None, None, 1))
            active_radio = 0
        else:
            for i in range(len(self.profile_names)):
                action_name = self.profile_menu_name(i)
                actions.append((action_name, None, "[" + str(i+1) + "] " + self.profile_names[i].replace("_", "__"), None, None, i))
            actions.append(('disconnect', None, _('Disconnect'), None, None, len(self.profile_names)))
            active_radio = self.profile_num
        if not self.conn:
            active_radio = len(self.profile_names)
        self.actionGroupProfiles.add_radio_actions(actions, active_radio, self.on_profiles_click)
        uiDescription = """
            <ui>
              <popup name="mainmenu">
                  <menu action="profilesmenu">
            """
        uiDescription = uiDescription + """<menuitem action=\"""" + 'disconnect' + """\" position="top"/>"""
        if host or port:
            for i in range(len(self.profile_names)):
                action_name = _("Profile") + ": " + _("MPD_HOST/PORT")
                uiDescription = uiDescription + """<menuitem action=\"""" + action_name + """\" position="top"/>"""
        else:
            for i in range(len(self.profile_names)):
                action_name = self.profile_menu_name(len(self.profile_names)-i-1)
                uiDescription = uiDescription + """<menuitem action=\"""" + action_name + """\" position="top"/>"""
        uiDescription = uiDescription + """</menu></popup></ui>"""
        self.merge_id = self.UIManager.add_ui_from_string(uiDescription)
        self.UIManager.insert_action_group(self.actionGroupProfiles, 0)
        self.UIManager.get_widget('/hidden').set_property('visible', False)

    def on_profiles_click(self, radioaction, current):
        if self.skip_on_profiles_click:
            return
        if current.get_name() == 'disconnect':
            self.on_disconnectkey_pressed(None)
        else:
            self.profile_num = current.get_current_value()
            self.on_connectkey_pressed(None)

    def mpd_connect(self, blocking=False, force=False):
        if blocking:
            self._mpd_connect(blocking, force)
        else:
            thread = threading.Thread(target=self._mpd_connect, args=(blocking, force))
            thread.setDaemon(True)
            thread.start()

    def _mpd_connect(self, blocking, force):
        if self.trying_connection:
            return
        self.trying_connection = True
        if self.user_connect or force:
            mpdh.call(self.client, 'disconnect')
            host, port, password = misc.mpd_env_vars()
            if not host: host = self.host[self.profile_num]
            if not port: port = self.port[self.profile_num]
            if not password: password = self.password[self.profile_num]
            mpdh.call(self.client, 'connect', host, port)
            if len(password) > 0:
                mpdh.call(self.client, 'password', password)
            test = mpdh.status(self.client)
            if test:
                self.conn = True
            else:
                self.conn = False
        else:
            self.conn = False
        if not self.conn:
            self.status = None
            self.songinfo = None
            if self.artwork is not None:
                self.artwork.update_songinfo(self.songinfo)
            self.iterate_time = self.iterate_time_when_disconnected_or_stopped
        self.trying_connection = False

    def mpd_disconnect(self):
        if self.conn:
            mpdh.call(self.client, 'close')
            mpdh.call(self.client, 'disconnect')
            self.conn = False

    def on_connectkey_pressed(self, event):
        self.user_connect = True
        # Update selected radio button in menu:
        self.skip_on_profiles_click = True
        host, port, password = misc.mpd_env_vars()
        if host or port:
            self.actionGroupProfiles.list_actions()[0].activate()
        else:
            for gtkAction in self.actionGroupProfiles.list_actions():
                if gtkAction.get_name() == self.profile_menu_name(self.profile_num):
                    gtkAction.activate()
                    break
        self.skip_on_profiles_click = False
        # Connect:
        self.mpd_connect(force=True)
        self.iterate_now()

    def on_disconnectkey_pressed(self, event):
        self.user_connect = False
        # Update selected radio button in menu:
        self.skip_on_profiles_click = True
        for gtkAction in self.actionGroupProfiles.list_actions():
            if gtkAction.get_name() == 'disconnect':
                gtkAction.activate()
                break
        self.skip_on_profiles_click = False
        # Disconnect:
        self.mpd_disconnect()

    def update_status(self):
        try:
            if not self.conn:
                self.mpd_connect()
            if self.conn:
                self.iterate_time = self.iterate_time_when_connected
                self.status = mpdh.status(self.client)
                if self.status:
                    if self.status['state'] == 'stop':
                        self.iterate_time = self.iterate_time_when_disconnected_or_stopped
                    self.songinfo = mpdh.currsong(self.client)
                    self.artwork.update_songinfo(self.songinfo)
                    if not self.last_repeat or self.last_repeat != self.status['repeat']:
                        self.repeatmenu.set_active(self.status['repeat'] == '1')
                    if not self.last_random or self.last_random != self.status['random']:
                        self.randommenu.set_active(self.status['random'] == '1')
                    if self.status['xfade'] == '0':
                        self.xfade_enabled = False
                    else:
                        self.xfade_enabled = True
                        self.xfade = int(self.status['xfade'])
                        if self.xfade > 30: self.xfade = 30
                    self.last_repeat = self.status['repeat']
                    self.last_random = self.status['random']
                    return
        except:
            pass
        self.prevconn = self.client
        self.prevstatus = self.status
        self.prevsonginfo = self.songinfo
        self.conn = False
        self.status = None
        self.songinfo = None
        self.artwork.update_songinfo(self.songinfo)

    def iterate(self):
        self.update_status()
        self.info_update(False)

        if self.conn != self.prevconn:
            self.handle_change_conn()
        if self.status != self.prevstatus:
            self.handle_change_status()
        if self.as_enabled:
            # We update this here because self.handle_change_status() won't be
            # called while the client is paused.
            self.scrob_time_now = time.time()
        if self.songinfo != self.prevsonginfo:
            self.handle_change_song()

        self.prevconn = self.conn
        self.prevstatus = self.status
        self.prevsonginfo = self.songinfo

        self.iterate_handler = gobject.timeout_add(self.iterate_time, self.iterate) # Repeat ad infitum..

        if self.show_trayicon:
            if HAVE_STATUS_ICON:
                if self.statusicon.is_embedded() and not self.statusicon.get_visible():
                    # Systemtray appears, add icon:
                    self.systemtray_initialize()
                elif not self.statusicon.is_embedded() and self.withdrawn:
                    # Systemtray gone, unwithdraw app:
                    self.withdraw_app_undo()
            elif HAVE_EGG:
                if not self.trayicon.get_property('visible'):
                    # Systemtray appears, add icon:
                    self.systemtray_initialize()

        if self.call_gc_collect:
            gc.collect()
            self.call_gc_collect = False

    def schedule_gc_collect(self):
        self.call_gc_collect = True

    def iterate_stop(self):
        try:
            gobject.source_remove(self.iterate_handler)
        except:
            pass

    def iterate_now(self):
        # Since self.iterate_time_when_connected has been
        # slowed down to 500ms, we'll call self.iterate_now()
        # whenever the user performs an action that requires
        # updating the client
        self.iterate_stop()
        self.iterate()

    def iterate_status_icon(self):
        # Polls for the users' cursor position to display the custom tooltip window when over the
        # gtk.StatusIcon. We use this instead of self.iterate() in order to poll more often and
        # increase responsiveness.
        if self.show_trayicon:
            if self.statusicon.is_embedded() and self.statusicon.get_visible():
                self.tooltip_show_manually()
        gobject.timeout_add(250, self.iterate_status_icon)

    def on_topwindow_keypress(self, widget, event):
        shortcut = gtk.accelerator_name(event.keyval, event.state)
        shortcut = shortcut.replace("<Mod2>", "")
        # These shortcuts were moved here so that they don't interfere with searching the library
        if shortcut == 'BackSpace':
            self.library_browse_parent(None)
        elif shortcut == 'Escape':
            if self.volumewindow.get_property('visible'):
                self.volume_hide()
            elif self.current_tab == self.TAB_LIBRARY and self.library_search_visible():
                self.on_library_search_end(None)
            elif self.current_tab == self.TAB_CURRENT and self.filterbox_visible:
                self.searchfilter_toggle(None)
            elif self.minimize_to_systray:
                if HAVE_STATUS_ICON and self.statusicon.is_embedded() and self.statusicon.get_visible():
                    self.withdraw_app()
                elif HAVE_EGG and self.trayicon.get_property('visible'):
                    self.withdraw_app()
            return
        elif shortcut == 'Delete':
            self.on_remove(None)
        elif self.volumewindow.get_property('visible') and (shortcut == 'Up' or shortcut == 'Down'):
            if shortcut == 'Up':
                self.on_volume_raise(None)
            else:
                self.on_volume_lower(None)
            return True
        if self.current_tab == self.TAB_CURRENT:
            if event.state & (gtk.gdk.CONTROL_MASK | gtk.gdk.MOD1_MASK):
                return
            # We only want to toggle open the filterbar if the key press is actual text! This
            # will ensure that we skip, e.g., F5, Alt, Ctrl, ...
            if len(event.string.strip()) > 0:
                if not self.filterbox_visible:
                    if event.string != "/":
                        self.searchfilter_toggle(None, event.string)
                    else:
                        self.searchfilter_toggle(None)

    def settings_load(self):
        self.config.settings_load_real()

    def settings_save(self):
        self.header_save_column_widths()

        self.config.current_tab_pos = self.notebook_get_tab_num(self.notebook, self.TAB_CURRENT)
        self.config.library_tab_pos = self.notebook_get_tab_num(self.notebook, self.TAB_LIBRARY)
        self.config.playlists_tab_pos = self.notebook_get_tab_num(self.notebook, self.TAB_PLAYLISTS)
        self.config.streams_tab_pos = self.notebook_get_tab_num(self.notebook, self.TAB_STREAMS)
        self.config.info_tab_pos = self.notebook_get_tab_num(self.notebook, self.TAB_INFO)

        self.config.settings_save_real()

    def handle_change_conn(self):
        if not self.conn:
            for mediabutton in (self.ppbutton, self.stopbutton, self.prevbutton, self.nextbutton, self.volumebutton):
                mediabutton.set_property('sensitive', False)
            self.currentdata.clear()
            if self.current.get_model():
                self.current.get_model().clear()
            if HAVE_STATUS_ICON:
                self.statusicon.set_from_file(self.find_path('sonata_disconnect.png'))
            elif HAVE_EGG and self.eggtrayheight:
                self.eggtrayfile = self.find_path('sonata_disconnect.png')
                self.trayimage.set_from_pixbuf(img.get_pixbuf_of_size(gtk.gdk.pixbuf_new_from_file(self.eggtrayfile), self.eggtrayheight)[0])
            self.info_update(True)
            if self.filterbox_visible:
                gobject.idle_add(self.searchfilter_toggle, None)
            if self.library_search_visible():
                self.on_library_search_end(None)
            self.handle_change_song()
            self.handle_change_status()
        else:
            for mediabutton in (self.ppbutton, self.stopbutton, self.prevbutton, self.nextbutton, self.volumebutton):
                mediabutton.set_property('sensitive', True)
            if self.sonata_loaded:
                self.library_browse(root='/')
            self.playlists_populate()
            self.on_notebook_page_change(self.notebook, 0, self.notebook.get_current_page())

    def on_streams_edit(self, action):
        model, selected = self.streams_selection.get_selected_rows()
        try:
            streamname = model.get_value(model.get_iter(selected[0]), 1)
            for i in range(len(self.stream_names)):
                if self.stream_names[i] == streamname:
                    self.on_streams_new(action, i)
                    return
        except:
            pass

    def on_streams_new(self, action, stream_num=-1):
        if stream_num > -1:
            edit_mode = True
        else:
            edit_mode = False
        # Prompt user for playlist name:
        dialog = ui.dialog(title=None, parent=self.window, flags=gtk.DIALOG_MODAL | gtk.DIALOG_DESTROY_WITH_PARENT, buttons=(gtk.STOCK_CANCEL, gtk.RESPONSE_REJECT, gtk.STOCK_OK, gtk.RESPONSE_ACCEPT), role="streamsNew")
        if edit_mode:
            dialog.set_title(_("Edit Stream"))
        else:
            dialog.set_title(_("New Stream"))
        hbox = gtk.HBox()
        namelabel = ui.label(text=_('Stream name') + ':')
        hbox.pack_start(namelabel, False, False, 5)
        nameentry = ui.entry()
        if edit_mode:
            nameentry.set_text(self.stream_names[stream_num])
        hbox.pack_start(nameentry, True, True, 5)
        hbox2 = gtk.HBox()
        urllabel = ui.label(text=_('Stream URL') + ':')
        hbox2.pack_start(urllabel, False, False, 5)
        urlentry = ui.entry()
        if edit_mode:
            urlentry.set_text(self.stream_uris[stream_num])
        hbox2.pack_start(urlentry, True, True, 5)
        ui.set_widths_equal([namelabel, urllabel])
        dialog.vbox.pack_start(hbox)
        dialog.vbox.pack_start(hbox2)
        ui.show(dialog.vbox)
        response = dialog.run()
        if response == gtk.RESPONSE_ACCEPT:
            name = nameentry.get_text()
            uri = urlentry.get_text()
            if len(name.decode('utf-8')) > 0 and len(uri.decode('utf-8')) > 0:
                # Make sure this stream name doesn't already exit:
                i = 0
                for item in self.stream_names:
                    # Prevent a name collision in edit_mode..
                    if not edit_mode or (edit_mode and i != stream_num):
                        if item == name:
                            dialog.destroy()
                            if ui.show_msg(self.window, _("A stream with this name already exists. Would you like to replace it?"), _("New Stream"), 'newStreamError', gtk.BUTTONS_YES_NO) == gtk.RESPONSE_YES:
                                # Pop existing stream:
                                self.stream_names.pop(i)
                                self.stream_uris.pop(i)
                            else:
                                return
                    i = i + 1
                if edit_mode:
                    self.stream_names.pop(stream_num)
                    self.stream_uris.pop(stream_num)
                self.stream_names.append(name)
                self.stream_uris.append(uri)
                self.streams_populate()
                self.settings_save()
        dialog.destroy()
        self.iterate_now()

    def on_playlist_save(self, action):
        plname = self.prompt_for_playlist_name(_("Save Playlist"), 'savePlaylist')
        if plname:
            if self.playlist_name_exists(_("Save Playlist"), 'savePlaylistError', plname):
                return
            self.playlist_create(plname)

    def playlist_create(self, playlistname, oldname=None):
        mpdh.call(self.client, 'rm', playlistname)
        if oldname is not None:
            mpdh.call(self.client, 'rename', oldname, playlistname)
        else:
            mpdh.call(self.client, 'save', playlistname)
        self.playlists_populate()
        self.iterate_now()

    def on_playlist_menu_click(self, action):
        plname = misc.unescape_html(action.get_name().replace("Playlist: ", ""))
        response = ui.show_msg(self.window, _("Would you like to replace the existing playlist or append these songs?"), _("Existing Playlist"), "existingPlaylist", (_("Replace playlist"), 1, _("Append songs"), 2), default=self.existing_playlist_option)
        if response == 1: # Overwrite
            self.existing_playlist_option = response
            self.playlist_create(plname)
        elif response == 2: # Append songs:
            self.existing_playlist_option = response
            mpdh.call(self.client, 'command_list_ok_begin')
            for song in self.current_songs:
                mpdh.call(self.client, 'playlistadd', plname, mpdh.get(song, 'file'))
            mpdh.call(self.client, 'command_list_end')
        return

    def playlist_name_exists(self, title, role, plname, skip_plname=""):
        # If the playlist already exists, and the user does not want to replace it, return True; In
        # all other cases, return False
        playlists = mpdh.call(self.client, 'listplaylists')
        if playlists is None:
            playlists = mpdh.call(self.client, 'lsinfo')
        for item in playlists:
            if item.has_key('playlist'):
                if mpdh.get(item, 'playlist') == plname and plname != skip_plname:
                    if ui.show_msg(self.window, _("A playlist with this name already exists. Would you like to replace it?"), title, role, gtk.BUTTONS_YES_NO) == gtk.RESPONSE_YES:
                        return False
                    else:
                        return True
        return False

    def prompt_for_playlist_name(self, title, role):
        plname = None
        if self.conn:
            # Prompt user for playlist name:
            dialog = ui.dialog(title=title, parent=self.window, flags=gtk.DIALOG_MODAL | gtk.DIALOG_DESTROY_WITH_PARENT, buttons=(gtk.STOCK_CANCEL, gtk.RESPONSE_REJECT, gtk.STOCK_SAVE, gtk.RESPONSE_ACCEPT), role=role, default=gtk.RESPONSE_ACCEPT)
            hbox = gtk.HBox()
            hbox.pack_start(ui.label(text=_('Playlist name') + ':'), False, False, 5)
            entry = ui.entry()
            entry.set_activates_default(True)
            hbox.pack_start(entry, True, True, 5)
            dialog.vbox.pack_start(hbox)
            ui.show(dialog.vbox)
            response = dialog.run()
            if response == gtk.RESPONSE_ACCEPT:
                plname = misc.strip_all_slashes(entry.get_text())
            dialog.destroy()
        return plname

    def playlists_populate(self):
        if self.conn:
            self.playlistsdata.clear()
            playlistinfo = []
            playlists = mpdh.call(self.client, 'listplaylists')
            if playlists is None:
                playlists = mpdh.call(self.client, 'lsinfo')
            for item in playlists:
                if item.has_key('playlist'):
                    playlistinfo.append(misc.escape_html(mpdh.get(item, 'playlist')))
            playlistinfo.sort(key=lambda x: x.lower()) # Remove case sensitivity
            for item in playlistinfo:
                self.playlistsdata.append([gtk.STOCK_JUSTIFY_FILL, item])
            if self.mpd_major_version() >= 0.13:
                self.populate_playlists_for_menu(playlistinfo)

    def on_playlist_rename(self, action):
        plname = self.prompt_for_playlist_name(_("Rename Playlist"), 'renamePlaylist')
        if plname:
            model, selected = self.playlists_selection.get_selected_rows()
            oldname = misc.unescape_html(model.get_value(model.get_iter(selected[0]), 1))
            if self.playlist_name_exists(_("Rename Playlist"), 'renamePlaylistError', plname, oldname):
                return
            self.playlist_create(plname, oldname)
            # Re-select item:
            row = 0
            for pl in self.playlistsdata:
                if pl[1] == plname:
                    self.playlists_selection.select_path((row,))
                    return
                row = row + 1

    def streams_populate(self):
        self.streamsdata.clear()
        streamsinfo = []
        for i in range(len(self.stream_names)):
            dict = {}
            dict["name"] = misc.escape_html(self.stream_names[i])
            dict["uri"] = misc.escape_html(self.stream_uris[i])
            streamsinfo.append(dict)
        streamsinfo.sort(key=lambda x: x["name"].lower()) # Remove case sensitivity
        for item in streamsinfo:
            self.streamsdata.append([gtk.STOCK_NETWORK, item["name"], item["uri"]])

    def playlists_key_press(self, widget, event):
        if event.keyval == gtk.gdk.keyval_from_name('Return'):
            self.playlists_activated(widget, widget.get_cursor()[0])
            return True

    def playlists_activated(self, treeview, path, column=0):
        self.on_add_item(None)

    def on_streams_key_press(self, widget, event):
        if event.keyval == gtk.gdk.keyval_from_name('Return'):
            self.on_streams_activated(widget, widget.get_cursor()[0])
            return True

    def on_streams_activated(self, treeview, path, column=0):
        self.on_add_item(None)

    def library_view_popup(self, button):
        self.librarymenu.popup(None, None, self.library_view_position_menu, 1, 0)

    def on_libraryview_chosen(self, action):
        if self.library_search_visible():
            self.on_library_search_end(None)
        if action.get_name() == 'filesystemview':
            self.lib_view = self.VIEW_FILESYSTEM
        elif action.get_name() == 'artistview':
            self.lib_view = self.VIEW_ARTIST
        elif action.get_name() == 'genreview':
            self.lib_view = self.VIEW_GENRE
        elif action.get_name() == 'albumview':
            self.lib_view = self.VIEW_ALBUM
        self.library.grab_focus()
        self.library_view_assign_image()
        # Go to highest level for artist/genre views:
        if self.lib_view == self.VIEW_ARTIST:
            self.lib_level = self.LIB_LEVEL_ARTIST
        elif self.lib_view == self.VIEW_GENRE:
            self.lib_level = self.LIB_LEVEL_GENRE
        elif self.lib_view == self.VIEW_ALBUM:
            self.lib_level = self.LIB_LEVEL_ALBUM
        self.libraryposition = {}
        self.libraryselectedpath = {}
        self.library_browse()
        try:
            if len(self.librarydata) > 0:
                self.library_selection.unselect_range((0,), (len(self.librarydata)-1,))
        except:
            pass
        gobject.idle_add(self.library.scroll_to_point, 0, 0)

    def library_view_assign_image(self):
        if self.lib_view == self.VIEW_FILESYSTEM:
            self.libraryview.set_image(ui.image(stock=gtk.STOCK_HARDDISK))
        elif self.lib_view == self.VIEW_ARTIST:
            self.libraryview.set_image(ui.image(stock='artist'))
        elif self.lib_view == self.VIEW_GENRE:
            self.libraryview.set_image(ui.image(stock='gtk-orientation-portrait'))
        elif self.lib_view == self.VIEW_ALBUM:
            self.libraryview.set_image(ui.image(stock='album'))

    def library_view_caches_reset(self):
        # We should call this on first load and whenever mpd is
        # updated.
        self.lib_view_filesystem_cache = None
        self.lib_view_artist_cache = None
        self.lib_view_genre_cache = None
        self.lib_view_album_cache = None
        self.lib_list_genres = None
        self.lib_list_artists = None
        self.lib_list_albums = None

    def library_browse_update(self):
        # Artwork for albums in the library tab
        if not self.library_search_visible():
            if self.lib_level == self.LIB_LEVEL_ALBUM:
                if self.lib_view == self.VIEW_ARTIST or self.lib_view == self.VIEW_GENRE:
                    if self.songinfo and self.songinfo.has_key('artist'):
                        if self.wd == mpdh.get(self.songinfo, 'artist'):
                            self.library_browse(root=self.wd)

    def library_browse(self, widget=None, root=None):
        # Populates the library list with entries
        if not self.conn:
            return

        if root is None or (self.lib_view == self.VIEW_FILESYSTEM and self.library_get_data(root, 'file') is None):
            root = self.library_set_data(file="/")
        if self.wd is None or (self.lib_view == self.VIEW_FILESYSTEM and self.library_get_data(self.wd, 'file') is None):
            self.wd = self.library_set_data(file="/")

        prev_selection = []
        prev_selection_root = False
        prev_selection_parent = False
        if root == self.wd:
            # This will happen when the database is updated. So, lets save
            # the current selection in order to try to re-select it after
            # the update is over.
            model, selected = self.library_selection.get_selected_rows()
            for path in selected:
                if model.get_value(model.get_iter(path), 2) == "/":
                    prev_selection_root = True
                elif model.get_value(model.get_iter(path), 2) == "..":
                    prev_selection_parent = True
                else:
                    prev_selection.append(model.get_value(model.get_iter(path), 1))
            self.libraryposition[self.wd] = self.library.get_visible_rect()[1]
            path_updated = True
        else:
            path_updated = False

        # The logic below is more consistent with, e.g., thunar.
        if (self.lib_view == self.VIEW_FILESYSTEM and len(self.library_get_data(root, 'file')) > len(self.library_get_data(self.wd, 'file'))) \
        or (self.lib_view != self.VIEW_FILESYSTEM and self.lib_level > self.lib_level_prev):
            # Save position and row for where we just were if we've
            # navigated into a sub-directory:
            self.libraryposition[self.wd] = self.library.get_visible_rect()[1]
            model, rows = self.library_selection.get_selected_rows()
            if len(rows) > 0:
                data = self.librarydata.get_value(self.librarydata.get_iter(rows[0]), 2)
                if not data in ("..", "/"):
                    self.libraryselectedpath[self.wd] = rows[0]
        elif (self.lib_view == self.VIEW_FILESYSTEM and root != self.wd) \
        or (self.lib_view != self.VIEW_FILESYSTEM and self.lib_level != self.lib_level_prev):
            # If we've navigated to a parent directory, don't save
            # anything so that the user will enter that subdirectory
            # again at the top position with nothing selected
            self.libraryposition[self.wd] = 0
            self.libraryselectedpath[self.wd] = None

        # In case sonata is killed or crashes, we'll save the library state
        # in 5 seconds (first removing any current settings_save timeouts)
        if self.wd != root:
            try:
                gobject.source_remove(self.save_timeout)
            except:
                pass
            self.save_timeout = gobject.timeout_add(5000, self.settings_save)

        self.wd = root
        self.library.freeze_child_notify()
        self.librarydata.clear()

        # Populate treeview with data:
        if self.lib_view == self.VIEW_FILESYSTEM:
            bd = self.library_populate_filesystem_data(self.library_get_data(self.wd, 'file'))
        elif self.lib_view == self.VIEW_ALBUM:
            if self.lib_level == self.LIB_LEVEL_SONG:
                bd = self.library_populate_data(artist=self.library_get_data(self.wd, 'artist'), album=self.library_get_data(self.wd, 'album'), year=self.library_get_data(self.wd, 'year'))
            else:
                bd = self.library_populate_toplevel_data(albumview=True)
        elif self.lib_view == self.VIEW_ARTIST:
            if self.lib_level == self.LIB_LEVEL_ARTIST:
                bd = self.library_populate_toplevel_data(artistview=True)
            elif self.lib_level == self.LIB_LEVEL_ALBUM:
                bd = self.library_populate_data(artist=self.library_get_data(self.wd, 'artist'))
            else:
                bd = self.library_populate_data(artist=self.library_get_data(self.wd, 'artist'), album=self.library_get_data(self.wd, 'album'), year=self.library_get_data(self.wd, 'year'))
        elif self.lib_view == self.VIEW_GENRE:
            if self.lib_level == self.LIB_LEVEL_GENRE:
                bd = self.library_populate_toplevel_data(genreview=True)
            elif self.lib_level == self.LIB_LEVEL_ARTIST:
                bd = self.library_populate_data(genre=self.library_get_data(self.wd, 'genre'))
            elif self.lib_level == self.LIB_LEVEL_ALBUM:
                bd = self.library_populate_data(genre=self.library_get_data(self.wd, 'genre'), artist=self.library_get_data(self.wd, 'artist'))
            else:
                bd = self.library_populate_data(genre=self.library_get_data(self.wd, 'genre'), artist=self.library_get_data(self.wd, 'artist'), album=self.library_get_data(self.wd, 'album'), year=self.library_get_data(self.wd, 'year'))
        for sort, list in bd:
            self.librarydata.append(list)

        self.library.thaw_child_notify()

        # Scroll back to set view for current dir:
        self.library.realize()
        gobject.idle_add(self.library_set_view, not path_updated)
        if len(prev_selection) > 0 or prev_selection_root or prev_selection_parent:
            # Retain pre-update selection:
            self.library_retain_selection(prev_selection, prev_selection_root, prev_selection_parent)

        self.lib_level_prev = self.lib_level

    def library_populate_add_parent_rows(self):
        bd = [('0', [self.harddiskpb, self.library_set_data(file='/'), '/'])]
        bd += [('1', [self.openpb, self.library_set_data(file='..'), '..'])]
        return bd

    def library_populate_filesystem_data(self, path):
        # List all dirs/files at path
        bd = []
        if path != '/':
            bd += self.library_populate_add_parent_rows()
        if path == '/' and self.lib_view_filesystem_cache is not None:
            # Use cache if possible...
            bd = self.lib_view_filesystem_cache
        else:
            for item in mpdh.call(self.client, 'lsinfo', path):
                if item.has_key('directory'):
                    name = mpdh.get(item, 'directory').split('/')[-1]
                    data = self.library_set_data(file=mpdh.get(item, 'directory'))
                    bd += [('d' + name.lower(), [self.openpb, data, misc.escape_html(name)])]
                elif item.has_key('file'):
                    data = self.library_set_data(file=mpdh.get(item, 'file'))
                    bd += [('f' + mpdh.get(item, 'file').lower(), [self.sonatapb, data, self.parse_formatting(self.libraryformat, item, True)])]
            bd.sort(key=misc.first_of_2tuple)
            if path == '/':
                self.lib_view_filesystem_cache = bd
        return bd

    def library_populate_toplevel_data(self, genreview=False, artistview=False, albumview=False):
        if genreview and self.lib_view_genre_cache is not None:
            return self.lib_view_genre_cache
        elif artistview and self.lib_view_artist_cache is not None:
            return self.lib_view_artist_cache
        elif albumview and self.lib_view_album_cache is not None:
            return self.lib_view_album_cache
        bd = []
        if genreview or artistview:
            # Only for artist/genre views, album view is handled differently
            # since multiple artists can have the same album name
            if genreview:
                items = self.library_return_list_items('genre')
                pb = self.genrepb
            else:
                items = self.library_return_list_items('artist')
                pb = self.artistpb
            untagged_found = False
            for item in items:
                if genreview:
                    playtime, num_songs = self.library_return_count(genre=item)
                    data = self.library_set_data(genre=item)
                else:
                    playtime, num_songs = self.library_return_count(artist=item)
                    data = self.library_set_data(artist=item)
                display = misc.escape_html(item)
                display += self.add_display_info(num_songs, int(playtime)/60)
                bd += [(misc.lower_no_the(item), [pb, data, display])]
        elif albumview:
            list = []
            for item in mpdh.call(self.client, 'listallinfo', '/'):
                if item.has_key('file') and item.has_key('album'):
                    album = mpdh.get(item, 'album')
                    artist = mpdh.get(item, 'artist', '')
                    year = mpdh.get(item, 'date', '')
                    data = self.library_set_data(album=album, artist=artist, year=year)
                    list.append(data)
            list = misc.remove_list_duplicates(list, case=False)
            list = self.list_identify_VA_albums(list)
            for item in list:
                album = self.library_get_data(item, 'album')
                artist = self.library_get_data(item, 'artist')
                year = self.library_get_data(item, 'year')
                playtime, num_songs = self.library_return_count(artist=artist, album=album, year=year)
                if num_songs > 0:
                    data = self.library_set_data(artist=artist, album=album, year=year)
                    display = misc.escape_html(album)
                    if artist and year and len(artist) > 0 and len(year) > 0:
                        display += " <span weight='light'>(" + misc.escape_html(artist) + ", " + misc.escape_html(year) + ")</span>"
                    elif artist and len(artist) > 0:
                        display += " <span weight='light'>(" + misc.escape_html(artist) + ")</span>"
                    elif year and len(year) > 0:
                        display += " <span weight='light'>(" + misc.escape_html(year) + ")</span>"
                    display += self.add_display_info(num_songs, int(playtime)/60)
                    bd += [(misc.lower_no_the(album), [self.albumpb, data, display])]
        bd.sort(locale.strcoll, key=misc.first_of_2tuple)
        if genreview:
            self.lib_view_genre_cache = bd
        elif artistview:
            self.lib_view_artist_cache = bd
        elif albumview:
            self.lib_view_album_cache = bd
        return bd

    def list_identify_VA_albums(self, list):
        for i in range(len(list)-1):
            if i + self.NUM_ARTISTS_FOR_VA > len(list)-1:
                break
            VA = False
            for j in range(1, self.NUM_ARTISTS_FOR_VA + 1):
                if self.library_get_data(list[i], 'album').lower() != self.library_get_data(list[i+j], 'album').lower() \
                or self.library_get_data(list[i], 'year') != self.library_get_data(list[i+j], 'year'):
                    break
                if j == self.NUM_ARTISTS_FOR_VA - 1:
                    VA = True
            if VA == True:
                album = self.library_get_data(list[i], 'album')
                artist = self.VAstr
                year = self.library_get_data(list[i], 'year')
                list[i] = self.library_set_data(album=album, artist=artist, year=year)
                j = 1
                while i+j <= len(list)-1:
                    if self.library_get_data(list[i], 'album').lower() == self.library_get_data(list[i+j], 'album').lower() \
                    and self.library_get_data(list[i], 'year') == self.library_get_data(list[i+j], 'year'):
                        list.pop(i+j)
                    else:

                        break
        return list

    def library_populate_data(self, genre=None, artist=None, album=None, year=None):
        # Create treeview model info
        bd = []
        bd = self.library_populate_add_parent_rows()
        if genre is not None and artist is None and album is None:
            # Artists within a genre
            for artist in self.library_return_list_items('artist', genre=genre):
                playtime, num_songs = self.library_return_count(genre=genre, artist=artist)
                display = misc.escape_html(artist)
                display += self.add_display_info(num_songs, int(playtime)/60)
                data = self.library_set_data(genre=genre, artist=artist)
                bd += [(misc.lower_no_the(artist), [self.artistpb, data, display])]
        elif artist is not None and album is None:
            # Albums/songs within an artist and possibly genre
            # Albums first:
            if genre is not None:
                albums = self.library_return_list_items('album', genre=genre, artist=artist)
            else:
                albums = self.library_return_list_items('album', artist=artist)
            for album in albums:
                if genre is not None:
                    years = self.library_return_list_items('date', genre=genre, artist=artist, album=album)
                else:
                    years = self.library_return_list_items('date', artist=artist, album=album)
                if not '' in years: years.append('') # check for album with no years tag too
                for year in years:
                    if genre is not None:
                        playtime, num_songs = self.library_return_count(genre=genre, artist=artist, album=album, year=year)
                        data = self.library_set_data(genre=genre, artist=artist, album=album, year=year)
                    else:
                        playtime, num_songs = self.library_return_count(artist=artist, album=album, year=year)
                        data = self.library_set_data(artist=artist, album=album, year=year)
                    if num_songs > 0:
                        display = misc.escape_html(album)
                        if year and len(year) > 0:
                            display += " <span weight='light'>(" + misc.escape_html(year) + ")</span>"
                        display += self.add_display_info(num_songs, int(playtime)/60)
                        bd += [(misc.lower_no_the(album), [self.albumpb, data, display])]
            # Now, songs not in albums:
            if genre:
                songs, playtime, num_songs = self.library_return_search_items(genre=genre, artist=artist, album='')
            else:
                songs, playtime, num_songs = self.library_return_search_items(artist=artist, album='')
            for song in songs:
                data = self.library_set_data(file=mpdh.get(song, 'file'))
                try:
                    bd += [('f' + misc.lower_no_the(mpdh.get(song, 'title')), [self.sonatapb, data, self.parse_formatting(self.libraryformat, song, True)])]
                except:
                    bd += [('f' + mpdh.get(song, 'file').lower(), [self.sonatapb, data, self.parse_formatting(self.libraryformat, song, True)])]
        else:
            # Songs within an album, artist, year, and possibly genre
            if genre is not None:
                songs, playtime, num_songs = self.library_return_search_items(genre=genre, artist=artist, album=album, year=year)
            else:
                songs, playtime, num_songs = self.library_return_search_items(artist=artist, album=album, year=year)
            for song in songs:
                data = self.library_set_data(file=mpdh.get(song, 'file'))
                try:
                    bd += [('f' + misc.lower_no_the(mpdh.get(song, 'title')), [self.sonatapb, data, self.parse_formatting(self.libraryformat, song, True)])]
                except:
                    bd += [('f' + mpdh.get(song, 'file').lower(), [self.sonatapb, data, self.parse_formatting(self.libraryformat, song, True)])]
        return bd

    def library_return_list_items(self, type, genre=None, artist=None, album=None, year=None, ignore_case=True):
        # Returns all items of tag 'type', in alphabetical order,
        # using mpd's 'list'. If searchtype is passed, use
        # a case insensitive search, via additional 'list'
        # queries, since using a single 'list' call will be
        # case sensitive.
        list = []
        searches = self.library_compose_searchlist(genre, artist, album, year)
        if len(searches) > 0:
            for s in searches:
                for item in mpdh.call(self.client, 'list', type, *s):
                    if len(item) > 0:
                        list.append(item)
        else:
            for item in mpdh.call(self.client, 'list', type):
                if len(item) > 0:
                    list.append(item)
        if ignore_case:
            list = misc.remove_list_duplicates(list, case=False)
        list.sort(locale.strcoll)
        return list

    def library_return_count(self, genre=None, artist=None, album=None, year=None):
        # Because mpd's 'count' is case sensitive, we have to
        # determine all equivalent items (case insensitive) and
        # call 'count' for each of them. Using 'list' + 'count'
        # involves much less data to be transferred back and
        # forth than to use 'search' and count manually.
        searches = self.library_compose_searchlist(genre, artist, album, year)
        playtime = 0
        num_songs = 0
        for s in searches:
            count = mpdh.call(self.client, 'count', *s)
            playtime += int(mpdh.get(count, 'playtime'))
            num_songs += int(mpdh.get(count, 'songs'))
        return (playtime, num_songs)

    def library_compose_searchlist(self, genre=None, artist=None, album=None, year=None):
        s1 = []
        if genre is not None:
            if self.lib_list_genres is None:
                self.lib_list_genres = self.library_return_list_items('genre', ignore_case=False)
            for item in self.lib_list_genres:
                if item.lower() == genre.lower():
                    s1.append(('genre', item))
        s2 = []
        if artist is not None:
            if self.lib_list_artists is None:
                self.lib_list_artists = self.library_return_list_items('artist', ignore_case=False)
            for item in self.lib_list_artists:
                if item.lower() == artist.lower():
                    if len(s1) > 0:
                        for s in s1:
                            s2.append(s + ('artist', item))
                    else:
                        s2.append(('artist', item))
        else:
            s2 = s1
        s3 = []
        if album is not None:
            if self.lib_list_albums is None:
                self.lib_list_albums = self.library_return_list_items('album', ignore_case=False)
            for item in self.lib_list_albums:
                if item.lower() == album.lower():
                    if len(s2) > 0:
                        for s in s2:
                            s3.append(s + ('album', item))
                    else:
                        s3.append(('album', item))
        else:
            s3 = s2
        s4 = []
        if year is not None:
            for s in s3:
                s4.append(s + ('date', year))
        else:
            s4 = s3
        return s4

    def library_return_search_items(self, genre=None, artist=None, album=None, year=None):
        # Returns all mpd items, using mpd's 'search', along with
        # playtime and num_songs
        args = []
        if genre is not None:
            args += ['genre', genre]
        if album is not None:
            args += ['album', album]
        if artist is not None and artist != self.VAstr:
            args += ['artist', artist]
        if year is not None:
            args += ['date', year]
        args_tuple = tuple(map(str, args))
        playtime = 0
        num_songs = 0
        list = []
        items = mpdh.call(self.client, 'search', *args_tuple)
        for item in items:
            list.append(item)
            num_songs += 1
            playtime += int(mpdh.get(item, 'time', '0'))
        return (list, int(playtime), num_songs)

    def add_display_info(self, num_songs, playtime):
        return "\n<small><span weight='light'>" + str(num_songs) + " " + gettext.ngettext('song', 'songs', num_songs) + ", " + str(playtime) + " " + gettext.ngettext('minute', 'minutes', playtime) + "</span></small>"

    def library_get_album_cover(self, dir, artist, album):
        tmp, coverfile = self.artwork.artwork_get_local_image(dir, artist, album)
        if coverfile:
            try:
                coverfile = gtk.gdk.pixbuf_new_from_file_at_size(coverfile, self.LIB_COVER_SIZE, self.LIB_COVER_SIZE)
                w = coverfile.get_width()
                h = coverfile.get_height()
                coverfile = self.artwork.artwork_apply_composite_case(coverfile, w, h)
            except:
                # Delete bad image:
                misc.remove_file(coverfile)
                # Revert to standard album cover:
                coverfile = self.albumpb
        else:
            # Revert to standard album cover:
            coverfile = self.albumpb
        return coverfile

    def library_retain_selection(self, prev_selection, prev_selection_root, prev_selection_parent):
        # Unselect everything:
        if len(self.librarydata) > 0:
            self.library_selection.unselect_range((0,), (len(self.librarydata)-1,))
        # Now attempt to retain the selection from before the update:
        for value in prev_selection:
            for rownum in range(len(self.librarydata)):
                if value == self.librarydata.get_value(self.librarydata.get_iter((rownum,)), 1):
                    self.library_selection.select_path((rownum,))
                    break
        if prev_selection_root:
            self.library_selection.select_path((0,))
        if prev_selection_parent:
            self.library_selection.select_path((1,))

    def library_set_view(self, select_items=True):
        # select_items should be false if the same directory has merely
        # been refreshed (updated)
        try:
            if self.wd in self.libraryposition:
                self.library.scroll_to_point(-1, self.libraryposition[self.wd])
            else:
                self.library.scroll_to_point(0, 0)
        except:
            self.library.scroll_to_point(0, 0)

        # Select and focus previously selected item
        if select_items:
            if self.wd in self.libraryselectedpath:
                try:
                    if self.libraryselectedpath[self.wd]:
                        self.library_selection.select_path(self.libraryselectedpath[self.wd])
                        self.library.grab_focus()
                except:
                    pass

    def library_set_data(self, album=None, artist=None, genre=None, year=None, file=None):
        d = self.LIB_DELIM
        nd = self.LIB_NODATA
        if album is not None:
            ret = album
        else:
            ret = nd
        if artist is not None:
            ret += d + artist
        else:
            ret += d + nd
        if genre is not None:
            ret += d + genre
        else:
            ret += d + nd
        if year is not None:
            ret += d + year
        else:
            ret += d + nd
        if file is not None:
            ret += d + file
        else:
            ret += d + nd
        return ret

    def library_get_data(self, data, item):
        map = {'album':0, 'artist':1, 'genre':2, 'year':3, 'file':4}
        dl = data.split(self.LIB_DELIM)
        ret = dl[map[item]]
        if ret == self.LIB_NODATA:
            return None
        else:
            return ret

    def _parse_formatting_return_substrings(self, format):
        substrings = []
        begin_pos = format.find("{")
        end_pos = -1
        while begin_pos > -1:
            if begin_pos > end_pos + 1:
                substrings.append(format[end_pos+1:begin_pos])
            end_pos = format.find("}", begin_pos)
            substrings.append(format[begin_pos:end_pos+1])
            begin_pos = format.find("{", end_pos)
        substrings.append(format[end_pos+1:])
        return substrings

    def parse_formatting_colnames(self, format):
        text = format.split("|")
        for i in range(len(text)):
            text[i] = text[i].replace("%A", _("Artist"))
            text[i] = text[i].replace("%B", _("Album"))
            text[i] = text[i].replace("%T", _("Track"))
            text[i] = text[i].replace("%N", _("#"))
            text[i] = text[i].replace("%Y", _("Year"))
            text[i] = text[i].replace("%G", _("Genre"))
            text[i] = text[i].replace("%F", _("File"))
            text[i] = text[i].replace("%S", _("Stream"))
            text[i] = text[i].replace("%L", _("Len"))
            text[i] = text[i].replace("%D", _("#"))
            if text[i].count("{") == text[i].count("}"):
                text[i] = text[i].replace("{","").replace("}","")
            # If the user wants the format of, e.g., "#%N", we'll
            # ensure the # doesn't show up twice in a row.
            text[i] = text[i].replace("##", "#")
        return text

    def _parse_formatting_substrings(self, subformat, item, wintitle):
        text = subformat
        if subformat.startswith("{") and subformat.endswith("}"):
            has_brackets = True
        else:
            has_brackets = False
        flag = "89syufd8sdhf9hsdf"
        if "%A" in text:
            artist = mpdh.get(item, 'artist', flag)
            if artist != flag:
                text = text.replace("%A", artist)
            else:
                if not has_brackets: text = text.replace("%A", _('Unknown'))
                else: return ""
        if "%B" in text:
            album = mpdh.get(item, 'album', flag)
            if album != flag:
                text = text.replace("%B", album)
            else:
                if not has_brackets: text = text.replace("%B", _('Unknown'))
                else: return ""
        if "%T" in text:
            title = mpdh.get(item, 'title', flag)
            if title != flag:
                text = text.replace("%T", title)
            else:
                if not has_brackets:
                    if len(item['file'].split('/')[-1]) == 0 or item['file'][:7] == 'http://' or item['file'][:6] == 'ftp://':
                        # Use path and file name:
                        text = misc.escape_html(item['file'])
                    else:
                        # Use file name only:
                        text = misc.escape_html(item['file'].split('/')[-1])
                    if wintitle:
                        return "[Sonata] " + text
                    else:
                        return text
                else:
                    return ""
        if "%N" in text:
            track = mpdh.get(item, 'track', flag)
            if track != flag:
                track = mpdh.getnum(item, 'track', flag, False, 2)
                text = text.replace("%N", track)
            else:
                if not has_brackets: text = text.replace("%N", "00")
                else: return ""
        if "%D" in text:
            disc = mpdh.get(item, 'disc', flag)
            if disc != flag:
                disc = mpdh.getnum(item, 'disc', flag, False, 0)
                text = text.replace("%D", disc)
            else:
                if not has_brackets: text = text.replace("%D", "0")
                else: return ""
        if "%S" in text:
            name = mpdh.get(item, 'name', flag)
            if name != flag:
                text = text.replace("%S", name)
            else:
                if not has_brackets: text = text.replace("%S", _('Unknown'))
                else: return ""
        if "%G" in text:
            genre = mpdh.get(item, 'genre', flag)
            if genre != flag:
                text = text.replace("%G", genre)
            else:
                if not has_brackets: text = text.replace("%G", _('Unknown'))
                else: return ""
        if "%Y" in text:
            date = mpdh.get(item, 'date', flag)
            if date != flag:
                text = text.replace("%Y", item['date'])
            else:
                if not has_brackets: text = text.replace("%Y", "?")
                else: return ""
        if "%F" in text:
            text = text.replace("%F", mpdh.get(item, 'file'))
        if "%P" in text:
            text = text.replace("%P", mpdh.get(item, 'file').split('/')[-1])
        if "%L" in text:
            time = mpdh.get(item, 'time', flag)
            if time != flag:
                time = misc.convert_time(int(time))
                text = text.replace("%L", time)
            else:
                if not has_brackets: text = text.replace("%L", "?")
                else: return ""
        if wintitle:
            if "%E" in text:
                try:
                    at, length = [int(c) for c in self.status['time'].split(':')]
                    at_time = misc.convert_time(at)
                    text = text.replace("%E", at_time)
                except:
                    if not has_brackets: text = text.replace("%E", "?")
                    else: return ""
        if text.startswith("{") and text.endswith("}"):
            return text[1:-1]
        else:
            return text

    def parse_formatting(self, format, item, use_escape_html, wintitle=False):
        substrings = self._parse_formatting_return_substrings(format)
        text = ""
        for sub in substrings:
            text = text + str(self._parse_formatting_substrings(sub, item, wintitle))
        if use_escape_html:
            return misc.escape_html(text)
        else:
            return text

    def info_update(self, update_all, blank_window=False, skip_lyrics=False):
        # update_all = True means that every tag should update. This is
        # only the case on song and status changes. Otherwise we only
        # want to update the minimum number of widgets so the user can
        # do things like select label text.
        if self.conn:
            if self.status and self.status['state'] in ['play', 'pause']:
                bitratelabel = self.info_labels[self.info_type[_("Bitrate")]]
                titlelabel = self.info_labels[self.info_type[_("Title")]]
                artistlabel = self.info_labels[self.info_type[_("Artist")]]
                albumlabel = self.info_labels[self.info_type[_("Album")]]
                datelabel = self.info_labels[self.info_type[_("Date")]]
                genrelabel = self.info_labels[self.info_type[_("Genre")]]
                tracklabel = self.info_labels[self.info_type[_("Track")]]
                filelabel = self.info_labels[self.info_type[_("File")]]
                try:
                    newbitrate = self.status['bitrate'] + " kbps"
                except:
                    newbitrate = ''
                if not self.last_info_bitrate or self.last_info_bitrate != newbitrate:
                    bitratelabel.set_text(newbitrate)
                self.last_info_bitrate = newbitrate
                if update_all:
                    # Use artist/album Wikipedia links?
                    artist_use_link = False
                    if self.songinfo.has_key('artist'):
                        artist_use_link = True
                    album_use_link = False
                    if self.songinfo.has_key('album'):
                        album_use_link = True
                    titlelabel.set_text(mpdh.get(self.songinfo, 'title'))
                    if artist_use_link:
                        artistlabel.set_markup(misc.link_markup(misc.escape_html(mpdh.get(self.songinfo, 'artist')), False, False, self.linkcolor))
                    else:
                        artistlabel.set_text(mpdh.get(self.songinfo, 'artist'))
                    if album_use_link:
                        albumlabel.set_markup(misc.link_markup(misc.escape_html(mpdh.get(self.songinfo, 'album')), False, False, self.linkcolor))
                    else:
                        albumlabel.set_text(mpdh.get(self.songinfo, 'album'))
                    datelabel.set_text(mpdh.get(self.songinfo, 'date'))
                    genrelabel.set_text(mpdh.get(self.songinfo, 'genre'))
                    if self.songinfo.has_key('track'):
                        tracklabel.set_text(mpdh.getnum(self.songinfo, 'track', '0', False, 0))
                    else:
                        tracklabel.set_text("")
                    path = misc.file_from_utf8(self.musicdir[self.profile_num] + os.path.dirname(mpdh.get(self.songinfo, 'file')))
                    if os.path.exists(path):
                        filelabel.set_text(self.musicdir[self.profile_num] + mpdh.get(self.songinfo, 'file'))
                        self.info_editlabel.set_markup(misc.link_markup(_("edit tags"), True, True, self.linkcolor))
                    else:
                        filelabel.set_text(mpdh.get(self.songinfo, 'file'))
                        self.info_editlabel.set_text("")
                    if self.songinfo.has_key('album'):
                        # Update album info:
                        trackinfo = ""
                        album = mpdh.get(self.songinfo, 'album')
                        artist = mpdh.get(self.songinfo, 'artist', None)
                        year = mpdh.get(self.songinfo, 'date', None)
                        albuminfo = album + "\n"
                        tracks, playtime, num_songs = self.library_return_search_items(album=album, artist=artist, year=year)
                        if len(tracks) > 0:
                            for track in tracks:
                                if track.has_key('title'):
                                    trackinfo = trackinfo + mpdh.getnum(track, 'track', '0', False, 2) + '. ' + mpdh.get(track, 'title') + '\n'
                                else:
                                    trackinfo = trackinfo + mpdh.getnum(track, 'track', '0', False, 2) + '. ' + mpdh.get(track, 'file').split('/')[-1] + '\n'
                            artist = self.album_current_artist[1]
                            if artist is not None: albuminfo += artist + "\n"
                            if year is not None: albuminfo += year + "\n"
                            albuminfo += misc.convert_time(playtime) + "\n"
                            albuminfo += "\n" + trackinfo
                        else:
                            albuminfo = _("Album info not found.")
                        self.albumText.set_markup(misc.escape_html(albuminfo))
                    else:
                        self.albumText.set_text(_("Album name not set."))
                    # Update lyrics:
                    if self.show_lyrics and not skip_lyrics:
                        global ServiceProxy
                        if ServiceProxy is None:
                            try:
                                from ZSI import ServiceProxy
                                # Make sure we have the right version..
                                test = ServiceProxy.ServiceProxy
                            except:
                                ServiceProxy = None
                        if ServiceProxy is None:
                            self.info_searchlabel.set_text("")
                            self.info_show_lyrics(_("ZSI not found, fetching lyrics support disabled."), "", "", True)
                        elif self.songinfo.has_key('artist') and self.songinfo.has_key('title'):
                            lyricThread = threading.Thread(target=self.info_get_lyrics, args=(mpdh.get(self.songinfo, 'artist'), mpdh.get(self.songinfo, 'title'), mpdh.get(self.songinfo, 'artist'), mpdh.get(self.songinfo, 'title')))
                            lyricThread.setDaemon(True)
                            lyricThread.start()
                        else:
                            self.info_searchlabel.set_text("")
                            self.info_show_lyrics(_("Artist or song title not set."), "", "", True)
            else:
                blank_window = True
        else:
            blank_window = True
        if blank_window:
            for label in self.info_labels:
                label.set_text("")
            self.info_editlabel.set_text("")
            if self.show_lyrics:
                self.info_searchlabel.set_text("")
                self.info_editlyricslabel.set_text("")
                self.info_show_lyrics("", "", "", True)
            self.albumText.set_text("")
            self.last_info_bitrate = ""

    def info_check_for_local_lyrics(self, artist, title):
        if os.path.exists(self.target_lyrics_filename(artist, title, self.LYRICS_LOCATION_HOME)):
            return self.target_lyrics_filename(artist, title, self.LYRICS_LOCATION_HOME)
        elif os.path.exists(self.target_lyrics_filename(artist, title, self.LYRICS_LOCATION_PATH)):
            return self.target_lyrics_filename(artist, title, self.LYRICS_LOCATION_PATH)
        return None

    def info_get_lyrics(self, search_artist, search_title, filename_artist, filename_title):
        filename_artist = misc.strip_all_slashes(filename_artist)
        filename_title = misc.strip_all_slashes(filename_title)
        filename = self.info_check_for_local_lyrics(filename_artist, filename_title)
        search_str = misc.link_markup(_("search"), True, True, self.linkcolor)
        edit_str = misc.link_markup(_("edit"), True, True, self.linkcolor)
        if filename:
            # If the lyrics only contain "not found", delete the file and try to
            # fetch new lyrics. If there is a bug in Sonata/SZI/LyricWiki that
            # prevents lyrics from being found, storing the "not found" will
            # prevent a future release from correctly fetching the lyrics.
            f = open(filename, 'r')
            lyrics = f.read()
            f.close()
            if lyrics == _("Lyrics not found"):
                misc.remove_file(filename)
                filename = self.info_check_for_local_lyrics(filename_artist, filename_title)
        if filename:
            # Re-use lyrics from file:
            f = open(filename, 'r')
            lyrics = f.read()
            f.close()
            # Strip artist - title line from file if it exists, since we
            # now have that information visible elsewhere.
            header = filename_artist + " - " + filename_title + "\n\n"
            if lyrics[:len(header)] == header:
                lyrics = lyrics[len(header):]
            gobject.idle_add(self.info_show_lyrics, lyrics, filename_artist, filename_title)
            gobject.idle_add(self.info_searchlabel.set_markup, search_str)
            gobject.idle_add(self.info_editlyricslabel.set_markup, edit_str)
        else:
            # Use default filename:
            filename = self.target_lyrics_filename(filename_artist, filename_title)
            # Fetch lyrics from lyricwiki.org
            gobject.idle_add(self.info_show_lyrics, _("Fetching lyrics..."), filename_artist, filename_title)
            if self.lyricServer is None:
                wsdlFile = "http://lyricwiki.org/server.php?wsdl"
                try:
                    self.lyricServer = True
                    timeout = socketgettimeout()
                    socketsettimeout(self.LYRIC_TIMEOUT)
                    self.lyricServer = ServiceProxy.ServiceProxy(wsdlFile, cachedir=os.path.expanduser("~/.service_proxy_dir"))
                except:
                    socketsettimeout(timeout)
                    lyrics = _("Couldn't connect to LyricWiki")
                    gobject.idle_add(self.info_show_lyrics, lyrics, filename_artist, filename_title)
                    self.lyricServer = None
                    gobject.idle_add(self.info_searchlabel.set_markup, search_str)
                    gobject.idle_add(self.info_editlyricslabel.set_markup, edit_str)
                    return
            try:
                timeout = socketgettimeout()
                socketsettimeout(self.LYRIC_TIMEOUT)
                lyrics = self.lyricServer.getSong(artist=urllib.quote(misc.capwords(search_artist)), song=urllib.quote(misc.capwords(search_title)))['return']["lyrics"]
                if lyrics.lower() != "not found":
                    lyrics = misc.unescape_html(lyrics)
                    lyrics = misc.wiki_to_html(lyrics)
                    lyrics = lyrics.encode("ISO-8859-1")
                    gobject.idle_add(self.info_show_lyrics, lyrics, filename_artist, filename_title)
                    # Save lyrics to file:
                    misc.create_dir('~/.lyrics/')
                    f = open(filename, 'w')
                    lyrics = misc.unescape_html(lyrics)
                    try:
                        f.write(lyrics.decode(self.enc).encode('utf8'))
                    except:
                        f.write(lyrics)
                    f.close()
                else:
                    lyrics = _("Lyrics not found")
                    gobject.idle_add(self.info_show_lyrics, lyrics, filename_artist, filename_title)
            except:
                lyrics = _("Fetching lyrics failed")
                gobject.idle_add(self.info_show_lyrics, lyrics, filename_artist, filename_title)
            gobject.idle_add(self.info_searchlabel.set_markup, search_str)
            gobject.idle_add(self.info_editlyricslabel.set_markup, edit_str)
            socketsettimeout(timeout)

    def info_show_lyrics(self, lyrics, artist, title, force=False):
        if force:
            # For error messages where there is no appropriate artist or
            # title, we pass force=True:
            self.lyricsText.set_text(lyrics)
        elif self.status and self.status['state'] in ['play', 'pause'] and self.songinfo:
            # Verify that we are displaying the correct lyrics:
            try:
                if misc.strip_all_slashes(mpdh.get(self.songinfo, 'artist')) == artist and misc.strip_all_slashes(mpdh.get(self.songinfo, 'title')) == title:
                    try:
                        self.lyricsText.set_markup(misc.escape_html(lyrics))
                    except:
                        self.lyricsText.set_text(lyrics)
            except:
                pass

    def on_library_key_press(self, widget, event):
        if event.keyval == gtk.gdk.keyval_from_name('Return'):
            self.on_library_row_activated(widget, widget.get_cursor()[0])
            return True

    def on_library_query_tooltip(self, widget, x, y, keyboard_mode, tooltip):
        if keyboard_mode or not self.library_search_visible():
            widget.set_tooltip_text(None)
            return False

        bin_x, bin_y = widget.convert_widget_to_bin_window_coords(x, y)

        path, col, x2, y2 = widget.get_path_at_pos(bin_x, bin_y)
        if not path:
            widget.set_tooltip_text(None)
            return False

        iter = self.librarydata.get_iter(path[0])
        path = misc.escape_html(self.librarydata.get_value(iter, 1))
        song = self.librarydata.get_value(iter, 2)
        new_tooltip = "<b>" + _("Song") + ": </b>" + song + "\n<b>" + _("Path") + ": </b>" + path

        if new_tooltip != self.libsearch_last_tooltip:
            self.libsearch_last_tooltip = new_tooltip
            self.library.set_property('has-tooltip', False)
            gobject.idle_add(self.library_search_tooltips_enable, widget, x, y, keyboard_mode, tooltip)
            return

        gobject.idle_add(widget.set_tooltip_markup, new_tooltip)
        self.libsearch_last_tooltip = new_tooltip

        return False #api says we should return True, but this doesn't work?

    def library_search_tooltips_enable(self, widget, x, y, keyboard_mode, tooltip):
        self.library.set_property('has-tooltip', True)
        self.on_library_query_tooltip(widget, x, y, keyboard_mode, tooltip)

    def on_library_row_activated(self, widget, path, column=0):
        if path is None:
            # Default to last item in selection:
            model, selected = self.library_selection.get_selected_rows()
            if len(selected) >= 1:
                path = selected[0]
            else:
                return
        value = self.librarydata.get_value(self.librarydata.get_iter(path), 1)
        icon = self.librarydata.get_value(self.librarydata.get_iter(path), 0)
        if icon == self.sonatapb:
            # Song found, add item
            self.on_add_item(self.library)
        elif value == self.library_set_data(file=".."):
            self.library_browse_parent(None)
        else:
            if self.lib_view != self.VIEW_FILESYSTEM:
                if value == self.library_set_data(file="/"):
                    if self.lib_view == self.VIEW_ALBUM:
                        self.lib_level = self.LIB_LEVEL_ALBUM
                    elif self.lib_view == self.VIEW_ARTIST:
                        self.lib_level = self.LIB_LEVEL_ARTIST
                    elif self.lib_view == self.VIEW_GENRE:
                        self.lib_level = self.LIB_LEVEL_GENRE
                elif icon != self.sonatapb:
                    self.lib_level += 1
            self.library_browse(None, value)

    def library_browse_parent(self, action):
        if self.current_tab == self.TAB_LIBRARY:
            if not self.library_search_visible():
                if self.library.is_focus():
                    if self.lib_view == self.VIEW_ALBUM:
                        if self.lib_level > self.LIB_LEVEL_ALBUM:
                            self.lib_level -= 1
                            album = self.library_get_data(self.wd, 'album')
                            album = self.library_set_data(album=album)
                        if self.lib_level == self.LIB_LEVEL_ALBUM:
                            value = self.library_set_data(file="/")
                        else:
                            album = self.library_get_data(self.wd, 'album')
                            album = self.library_set_data(album=album)
                    elif self.lib_view == self.VIEW_ARTIST:
                        if self.lib_level > self.LIB_LEVEL_ARTIST:
                            self.lib_level -= 1
                            artist = self.library_get_data(self.wd, 'artist')
                            value = self.library_set_data(artist=artist)
                        if self.lib_level == self.LIB_LEVEL_ARTIST:
                            value = self.library_set_data(file="/")
                        else:
                            artist = self.library_get_data(self.wd, 'artist')
                            value = self.library_set_data(artist=artist)
                    elif self.lib_view == self.VIEW_GENRE:
                        if self.lib_level > self.LIB_LEVEL_GENRE:
                            self.lib_level -= 1
                            genre = self.library_get_data(self.wd, 'genre')
                            value = self.library_set_data(genre=genre)
                        if self.lib_level == self.LIB_LEVEL_GENRE:
                            value = self.library_set_data(file="/")
                        elif self.lib_level == self.LIB_LEVEL_ARTIST:
                            genre = self.library_get_data(self.wd, 'genre')
                            value = self.library_set_data(genre=genre)
                        elif self.lib_level == self.LIB_LEVEL_ALBUM:
                            artist = self.library_get_data(self.wd, 'artist')
                            genre = self.library_get_data(self.wd, 'genre')
                            value = self.library_set_data(genre=genre, artist=artist)
                    else:
                        newvalue = '/'.join(self.library_get_data(self.wd, 'file').split('/')[:-1]) or '/'
                        value = self.library_set_data(file=newvalue)
                    self.library_browse(None, value)

    def on_treeview_selection_changed(self, treeselection):
        self.update_menu_visibility()
        if treeselection == self.current.get_selection():
            # User previously clicked inside group of selected rows, re-select
            # rows so it doesn't look like anything changed:
            if self.sel_rows:
                for row in self.sel_rows:
                    treeselection.select_path(row)

    def on_library_button_press(self, widget, event):
        if self.on_button_press(widget, event, False): return True

    def on_current_button_press(self, widget, event):
        if self.on_button_press(widget, event, True): return True

    def on_playlists_button_press(self, widget, event):
        if self.on_button_press(widget, event, False): return True

    def on_streams_button_press(self, widget, event):
        if self.on_button_press(widget, event, False): return True

    def on_button_press(self, widget, event, widget_is_current):
        ctrl_press = (event.state & gtk.gdk.CONTROL_MASK)
        self.volume_hide()
        self.sel_rows = None
        if event.button == 1 and widget_is_current and not ctrl_press:
            # If the user clicked inside a group of rows that were already selected,
            # we need to retain the selected rows in case the user wants to DND the
            # group of rows. If they release the mouse without first moving it,
            # then we revert to the single selected row. This is similar to the
            # behavior found in thunar.
            try:
                path, col, x, y = widget.get_path_at_pos(int(event.x), int(event.y))
                if widget.get_selection().path_is_selected(path):
                    self.sel_rows = widget.get_selection().get_selected_rows()[1]
            except:
                pass
        elif event.button == 3:
            self.update_menu_visibility()
            # Calling the popup in idle_add is important. It allows the menu items
            # to have been shown/hidden before the menu is popped up. Otherwise, if
            # the menu pops up too quickly, it can result in automatically clicking
            # menu items for the user!
            gobject.idle_add(self.mainmenu.popup, None, None, None, event.button, event.time)
            # Don't change the selection for a right-click. This
            # will allow the user to select multiple rows and then
            # right-click (instead of right-clicking and having
            # the current selection change to the current row)
            if widget.get_selection().count_selected_rows() > 1:
                return True

    def on_current_drag_begin(self, widget, context):
        self.sel_rows = False

    def dnd_after_current_drag_begin(self, widget, context):
        # Override default image of selected row with sonata icon:
        context.set_icon_stock('sonata', 0, 0)

    def on_current_button_release(self, widget, event):
        if self.sel_rows:
            self.sel_rows = False
            # User released mouse, select single row:
            selection = widget.get_selection()
            selection.unselect_all()
            path, col, x, y = widget.get_path_at_pos(int(event.x), int(event.y))
            selection.select_path(path)

    def library_get_path_child_filenames(self, return_root):
        # If return_root=True, return main directories whenever possible
        # instead of individual songs in order to reduce the number of
        # mpd calls we need to make. We won't want this behavior in some
        # instances, like when we want all end files for editing tags
        items = []
        model, selected = self.library_selection.get_selected_rows()
        for path in selected:
            iter = model.get_iter(path)
            pb = model.get_value(iter, 0)
            data = model.get_value(iter, 1)
            value = model.get_value(iter, 2)
            if value != ".." and value != "/":
                album = self.library_get_data(data, 'album')
                artist = self.library_get_data(data, 'artist')
                year = self.library_get_data(data, 'year')
                genre = self.library_get_data(data, 'genre')
                file = self.library_get_data(data, 'file')
                if file is not None and album is None and artist is None and year is None and genre is None:
                    if pb == self.sonatapb:
                        # File
                        items.append(file)
                    else:
                        # Directory
                        if not return_root:
                            list = []
                            self.library_get_path_files_recursive(file, list)
                            for item in list:
                                items.append(item)
                        else:
                            items.append(file)
                else:
                    results, playtime, num_songs = self.library_return_search_items(genre=genre, artist=artist, album=album, year=year)
                    for item in results:
                        items.append(mpdh.get(item, 'file'))
        # Make sure we don't have any EXACT duplicates:
        items = misc.remove_list_duplicates(items, case=True)
        return items

    def library_get_path_files_recursive(self, path, list):
        for item in mpdh.call(self.client, 'lsinfo', path):
            if item.has_key('directory'):
                self.library_get_path_files_recursive(mpdh.get(item, 'directory'), list)
            elif item.has_key('file'):
                list.append(mpdh.get(item, 'file'))

    def on_add_item_play(self, widget):
        self.on_add_item(widget, True)

    def on_add_item(self, widget, play_after=False):
        if self.conn:
            if play_after and self.status:
                playid = self.status['playlistlength']
            if self.current_tab == self.TAB_LIBRARY:
                items = self.library_get_path_child_filenames(True)
                mpdh.call(self.client, 'command_list_ok_begin')
                for item in items:
                    mpdh.call(self.client, 'add', item)
                mpdh.call(self.client, 'command_list_end')
            elif self.current_tab == self.TAB_PLAYLISTS:
                model, selected = self.playlists_selection.get_selected_rows()
                for path in selected:
                    mpdh.call(self.client, 'load', misc.unescape_html(model.get_value(model.get_iter(path), 1)))
            elif self.current_tab == self.TAB_STREAMS:
                model, selected = self.streams_selection.get_selected_rows()
                for path in selected:
                    item = model.get_value(model.get_iter(path), 2)
                    self.stream_parse_and_add(item)
            self.iterate_now()
            if play_after:
                if self.status['random'] == '1':
                    # If we are in random mode, we want to play a random song
                    # instead:
                    mpdh.call(self.client, 'play')
                else:
                    mpdh.call(self.client, 'play', int(playid))

    def stream_parse_and_add(self, item):
        # We need to do different things depending on if this is
        # a normal stream, pls, m3u, etc..
        # Note that we will only download the first 4000 bytes
        while gtk.events_pending():
            gtk.main_iteration()
        f = None
        try:
            request = urllib2.Request(item)
            opener = urllib2.build_opener()
            f = opener.open(request).read(4000)
        except:
            try:
                request = urllib2.Request("http://" + item)
                opener = urllib2.build_opener()
                f = opener.open(request).read(4000)
            except:
                try:
                    request = urllib2.Request("file://" + item)
                    opener = urllib2.build_opener()
                    f = opener.open(request).read(4000)
                except:
                    pass
        while gtk.events_pending():
            gtk.main_iteration()
        if f:
            if misc.is_binary(f):
                # Binary file, just add it:
                mpdh.call(self.client, 'add', item)
            else:
                if "[playlist]" in f:
                    # pls:
                    self.stream_parse_pls(f)
                elif "#EXTM3U" in f:
                    # extended m3u:
                    self.stream_parse_m3u(f)
                elif "http://" in f:
                    # m3u or generic list:
                    self.stream_parse_m3u(f)
                else:
                    # Something else..
                    mpdh.call(self.client, 'add', item)
        else:
            # Hopefully just a regular stream, try to add it:
            mpdh.call(self.client, 'add', item)

    def stream_parse_pls(self, f):
        lines = f.split("\n")
        for line in lines:
            line = line.replace('\r','')
            delim = line.find("=")+1
            if delim > 0:
                line = line[delim:]
                if len(line) > 7 and line[0:7] == 'http://':
                    mpdh.call(self.client, 'add', line)
                elif len(line) > 6 and line[0:6] == 'ftp://':
                    mpdh.call(self.client, 'add', line)

    def stream_parse_m3u(self, f):
        lines = f.split("\n")
        for line in lines:
            line = line.replace('\r','')
            if len(line) > 7 and line[0:7] == 'http://':
                mpdh.call(self.client, 'add', line)
            elif len(line) > 6 and line[0:6] == 'ftp://':
                mpdh.call(self.client, 'add', line)

    def on_replace_item_play(self, widget):
        self.on_replace_item(widget, True)

    def on_replace_item(self, widget, play_after=False):
        if self.status and self.status['state'] == 'play':
            play_after = True
        # Only clear if an item is selected:
        if self.current_tab == self.TAB_LIBRARY:
            num_selected = self.library_selection.count_selected_rows()
        elif self.current_tab == self.TAB_PLAYLISTS:
            num_selected = self.playlists_selection.count_selected_rows()
        elif self.current_tab == self.TAB_STREAMS:
            num_selected = self.streams_selection.count_selected_rows()
        else:
            return
        if num_selected == 0:
            return
        self.mpd_clear(None)
        self.on_add_item(widget, play_after)
        self.iterate_now()

    def library_view_position_menu(self, menu):
        x, y, width, height = self.libraryview.get_allocation()
        return (self.x + x, self.y + y + height, True)

    def menu_position(self, menu):
        if self.expanded:
            x, y, width, height = self.current.get_allocation()
            # Find first selected visible row and popup the menu
            # from there
            if self.current_tab == self.TAB_CURRENT:
                widget = self.current
                column = self.columns[0]
            elif self.current_tab == self.TAB_LIBRARY:
                widget = self.library
                column = self.librarycolumn
            elif self.current_tab == self.TAB_PLAYLISTS:
                widget = self.playlists
                column = self.playlistscolumn
            elif self.current_tab == self.TAB_STREAMS:
                widget = self.streams
                column = self.streamscolumn
            rows = widget.get_selection().get_selected_rows()[1]
            visible_rect = widget.get_visible_rect()
            row_y = 0
            for row in rows:
                row_rect = widget.get_background_area(row, column)
                if row_rect.y + row_rect.height <= visible_rect.height and row_rect.y >= 0:
                    row_y = row_rect.y + 30
                    break
            return (self.x + width - 150, self.y + y + row_y, True)
        else:
            return (self.x + 250, self.y + 80, True)

    def handle_change_status(self):
        # Called when one of the following items are changed:
        #  1. Current playlist (song added, removed, etc)
        #  2. Repeat/random/xfade/volume
        #  3. Currently selected song in playlist
        #  4. Status (playing/paused/stopped)
        if self.status == None:
            # clean up and bail out
            self.update_progressbar()
            self.update_cursong()
            self.update_wintitle()
            self.artwork.artwork_update()
            self.update_statusbar()
            if not self.conn:
                self.librarydata.clear()
                self.playlistsdata.clear()
                self.streamsdata.clear()
            return

        # Display current playlist
        if self.prevstatus == None or self.prevstatus['playlist'] != self.status['playlist']:
            self.current_update()

        # Update progress frequently if we're playing
        if self.status['state'] in ['play', 'pause']:
            self.update_progressbar()

        # If elapsed time is shown in the window title, we need to update more often:
        if "%E" in self.titleformat:
            self.update_wintitle()

        # If state changes
        if self.prevstatus == None or self.prevstatus['state'] != self.status['state']:

            self.album_get_artist()

            # Update progressbar if the state changes too
            self.update_progressbar()
            self.update_cursong()
            self.update_wintitle()
            self.info_update(True)
            if self.status['state'] == 'stop':
                self.ppbutton.set_image(ui.image(stock=gtk.STOCK_MEDIA_PLAY, stocksize=gtk.ICON_SIZE_BUTTON))
                self.ppbutton.get_child().get_child().get_children()[1].set_text('')
                self.UIManager.get_widget('/traymenu/playmenu').show()
                self.UIManager.get_widget('/traymenu/pausemenu').hide()
                if HAVE_STATUS_ICON:
                    self.statusicon.set_from_file(self.find_path('sonata.png'))
                elif HAVE_EGG and self.eggtrayheight:
                    self.eggtrayfile = self.find_path('sonata.png')
                    self.trayimage.set_from_pixbuf(img.get_pixbuf_of_size(gtk.gdk.pixbuf_new_from_file(self.eggtrayfile), self.eggtrayheight)[0])
            elif self.status['state'] == 'pause':
                self.ppbutton.set_image(ui.image(stock=gtk.STOCK_MEDIA_PLAY, stocksize=gtk.ICON_SIZE_BUTTON))
                self.ppbutton.get_child().get_child().get_children()[1].set_text('')
                self.UIManager.get_widget('/traymenu/playmenu').show()
                self.UIManager.get_widget('/traymenu/pausemenu').hide()
                if HAVE_STATUS_ICON:
                    self.statusicon.set_from_file(self.find_path('sonata_pause.png'))
                elif HAVE_EGG and self.eggtrayheight:
                    self.eggtrayfile = self.find_path('sonata_pause.png')
                    self.trayimage.set_from_pixbuf(img.get_pixbuf_of_size(gtk.gdk.pixbuf_new_from_file(self.eggtrayfile), self.eggtrayheight)[0])
            elif self.status['state'] == 'play':
                self.ppbutton.set_image(ui.image(stock=gtk.STOCK_MEDIA_PAUSE, stocksize=gtk.ICON_SIZE_BUTTON))
                self.ppbutton.get_child().get_child().get_children()[1].set_text('')
                self.UIManager.get_widget('/traymenu/playmenu').hide()
                self.UIManager.get_widget('/traymenu/pausemenu').show()
                if self.prevstatus != None:
                    if self.prevstatus['state'] == 'pause':
                        # Forces the notification to popup if specified
                        self.on_currsong_notify()
                if HAVE_STATUS_ICON:
                    self.statusicon.set_from_file(self.find_path('sonata_play.png'))
                elif HAVE_EGG and self.eggtrayheight:
                    self.eggtrayfile = self.find_path('sonata_play.png')
                    self.trayimage.set_from_pixbuf(img.get_pixbuf_of_size(gtk.gdk.pixbuf_new_from_file(self.eggtrayfile), self.eggtrayheight)[0])

            self.artwork.artwork_update()
            if self.status['state'] in ['play', 'pause']:
                self.current_center_song_in_list()

        if self.prevstatus is None or self.status['volume'] != self.prevstatus['volume']:
            try:
                self.volumescale.get_adjustment().set_value(int(self.status['volume']))
                if int(self.status['volume']) == 0:
                    self.volume_set_image("stock_volume-mute")
                elif int(self.status['volume']) < 30:
                    self.volume_set_image("stock_volume-min")
                elif int(self.status['volume']) <= 70:
                    self.volume_set_image("stock_volume-med")
                else:
                    self.volume_set_image("stock_volume-max")
                self.volumebutton.set_tooltip_text(self.status['volume'] + "%")
            except:
                pass

        if self.conn:
            if self.status and self.status.get('updating_db'):
                # MPD library is being updated
                self.update_statusbar(True)
            elif self.prevstatus == None or self.prevstatus.get('updating_db', 0) != self.status.get('updating_db', 0):
                if not (self.status and self.status.get('updating_db', 0)):
                    # Update over:
                    self.library_view_caches_reset()
                    self.update_statusbar(False)
                    # We need to make sure that we update the artist in case tags have changed:
                    self.album_reset_artist()
                    self.album_get_artist()
                    # Now update the library and playlist tabs
                    self.library_browse(root=self.wd)
                    self.playlists_populate()
                    # Update infow if it's visible:
                    self.info_update(True)

        if self.as_enabled:
            if self.status and self.status['state'] == 'play':
                elapsed_prev = self.elapsed_now
                self.elapsed_now, length = [float(c) for c in self.status['time'].split(':')]
                if not self.prevstatus or (self.prevstatus and self.prevstatus['state'] == 'stop'):
                    # Switched from stop to play, prepare current track:
                    self.scrobbler_prepare()
                elif self.prevsonginfo and self.prevsonginfo.has_key('time') \
                and (self.scrob_last_prepared != mpdh.get(self.songinfo, 'file') or \
                (self.scrob_last_prepared == mpdh.get(self.songinfo, 'file') and elapsed_prev \
                and abs(elapsed_prev-length)<=2 and self.elapsed_now<=2 and length>0)):
                    # New song is playing, post previous track if time criteria is met.
                    # In order to account for the situation where the same song is played twice in
                    # a row, we will check if the previous time was the end of the song and we're
                    # now at the beginning of the same song.. this technically isn't right in
                    # the case where a user seeks back to the beginning, but that's an edge case.
                    if self.scrob_playing_duration > 4 * 60 or self.scrob_playing_duration > int(mpdh.get(self.prevsonginfo, 'time'))/2:
                        if self.scrob_start_time != "":
                            self.scrobbler_post()
                    # Prepare current track:
                    self.scrobbler_prepare()
                elif self.scrob_time_now:
                    # Keep track of the total amount of time that the current song
                    # has been playing:
                    self.scrob_playing_duration += time.time() - self.scrob_time_now
            elif self.status and self.status['state'] == 'stop':
                self.elapsed_now = 0
                if self.prevsonginfo and self.prevsonginfo.has_key('time'):
                    if self.scrob_playing_duration > 4 * 60 or self.scrob_playing_duration > int(mpdh.get(self.prevsonginfo, 'time'))/2:
                        # User stopped the client, post previous track if time
                        # criteria is met:
                        if self.scrob_start_time != "":
                            self.scrobbler_post()

    def album_get_artist(self):
        if self.songinfo and self.songinfo.has_key('album'):
            self.album_return_artist_name()
        elif self.songinfo and self.songinfo.has_key('artist'):
            self.album_current_artist = [self.songinfo, mpdh.get(self.songinfo, 'artist')]
        else:
            self.album_current_artist = [self.songinfo, ""]

    def volume_set_image(self, stock_icon):
        image = ui.image(stock=stock_icon, stocksize=VOLUME_ICON_SIZE)
        self.volumebutton.set_image(image)

    def handle_change_song(self):
        # Called when one of the following items are changed for the current
        # mpd song in the playlist:
        #  1. Song tags or filename (e.g. if tags are edited)
        #  2. Position in playlist (e.g. if playlist is sorted)
        # Note that the song does not have to be playing; it can reflect the
        # next song that will be played.
        self.unbold_boldrow(self.prev_boldrow)

        if self.status and self.status.has_key('song'):
            row = int(self.status['song'])
            self.boldrow(row)
            if self.songinfo:
                if not self.prevsonginfo or mpdh.get(self.songinfo, 'file') != mpdh.get(self.prevsonginfo, 'file'):
                    self.current_center_song_in_list()
            self.prev_boldrow = row

        self.album_get_artist()

        self.update_cursong()
        self.update_wintitle()
        self.artwork.artwork_update()
        self.info_update(True)

    def scrobbler_prepare(self):
        if audioscrobbler is not None:
            self.scrob_start_time = ""
            self.scrob_last_prepared = ""
            self.scrob_playing_duration = 0

            if self.as_enabled and self.songinfo:
                # No need to check if the song is 30 seconds or longer,
                # audioscrobbler.py takes care of that.
                if self.songinfo.has_key('time'):
                    self.scrobbler_np()

                    self.scrob_start_time = str(int(time.time()))
                    self.scrob_last_prepared = mpdh.get(self.songinfo, 'file')

    def scrobbler_np(self):
        thread = threading.Thread(target=self.scrobbler_do_np)
        thread.setDaemon(True)
        thread.start()

    def scrobbler_do_np(self):
        self.scrobbler_init()
        if self.as_enabled and self.scrob_post and self.songinfo:
            if self.songinfo.has_key('artist') and \
               self.songinfo.has_key('title') and \
               self.songinfo.has_key('time'):
                if not self.songinfo.has_key('album'):
                    album = u''
                else:
                    album = mpdh.get(self.songinfo, 'album')
                if not self.songinfo.has_key('track'):
                    tracknumber = u''
                else:
                    tracknumber = mpdh.get(self.songinfo, 'track')
                self.scrob_post.nowplaying(mpdh.get(self.songinfo, 'artist'),
                                            mpdh.get(self.songinfo, 'title'),
                                            mpdh.get(self.songinfo, 'time'),
                                            tracknumber,
                                            album,
                                            self.scrob_start_time)
        time.sleep(10)

    def scrobbler_post(self):
        self.scrobbler_init()
        if self.as_enabled and self.scrob_post and self.prevsonginfo:
            if self.prevsonginfo.has_key('artist') and \
               self.prevsonginfo.has_key('title') and \
               self.prevsonginfo.has_key('time'):
                if not self.prevsonginfo.has_key('album'):
                    album = u''
                else:
                    album = mpdh.get(self.prevsonginfo, 'album')
                if not self.prevsonginfo.has_key('track'):
                    tracknumber = u''
                else:
                    tracknumber = mpdh.get(self.prevsonginfo, 'track')
                self.scrob_post.addtrack(mpdh.get(self.prevsonginfo, 'artist'),
                                                mpdh.get(self.prevsonginfo, 'title'),
                                                mpdh.get(self.prevsonginfo, 'time'),
                                                self.scrob_start_time,
                                                tracknumber,
                                                album)

                thread = threading.Thread(target=self.scrobbler_do_post)
                thread.setDaemon(True)
                thread.start()
        self.scrob_start_time = ""

    def scrobbler_do_post(self):
        for i in range(0,3):
            if not self.scrob_post:
                return
            if len(self.scrob_post.cache) == 0:
                return
            try:
                self.scrob_post.post()
            except audioscrobbler.AudioScrobblerConnectionError, e:
                print e
                pass
            time.sleep(10)

    def scrobbler_save_cache(self):
        filename = os.path.expanduser('~/.config/sonata/ascache')
        if self.scrob_post:
            self.scrob_post.savecache(filename)

    def scrobbler_retrieve_cache(self):
        filename = os.path.expanduser('~/.config/sonata/ascache')
        if self.scrob_post:
            self.scrob_post.retrievecache(filename)

    def boldrow(self, row):
        if row > -1:
            try:
                for i in range(len(self.currentdata[row]) - 1):
                    self.currentdata[row][i + 1] = misc.bold(self.currentdata[row][i + 1])
            except:
                pass

    def unbold_boldrow(self, row):
        if row > -1:
            try:
                for i in range(len(self.currentdata[row]) - 1):
                    self.currentdata[row][i + 1] = misc.unbold(self.currentdata[row][i + 1])
            except:
                pass

    def update_progressbar(self):
        if self.conn and self.status and self.status['state'] in ['play', 'pause']:
            at, length = [float(c) for c in self.status['time'].split(':')]
            try:
                newfrac = at/length
            except:
                newfrac = 0
        else:
            newfrac = 0
        if not self.last_progress_frac or self.last_progress_frac != newfrac:
            if newfrac >= 0 and newfrac <= 1:
                self.progressbar.set_fraction(newfrac)
        if self.conn:
            if self.status and self.status['state'] in ['play', 'pause']:
                at, length = [int(c) for c in self.status['time'].split(':')]
                at_time = misc.convert_time(at)
                try:
                    time = misc.convert_time(int(mpdh.get(self.songinfo, 'time')))
                    newtime = at_time + " / " + time
                except:
                    newtime = at_time
            elif self.status:
                newtime = ' '
            else:
                newtime = _('No Read Permission')
        else:
            newtime = _('Not Connected')
        if not self.last_progress_text or self.last_progress_text != newtime:
            self.progressbar.set_text(newtime)
        return

    def update_statusbar(self, updatingdb=False):
        if self.show_statusbar:
            if self.conn and self.status:
                try:
                    days = None
                    hours = None
                    mins = None
                    total_time = misc.convert_time(self.total_time)
                    try:
                        mins = total_time.split(":")[-2]
                        hours = total_time.split(":")[-3]
                        if int(hours) >= 24:
                            days = str(int(hours)/24)
                            hours = str(int(hours) - int(days)*24).zfill(2)
                    except:
                        pass
                    if days:
                        days_text = gettext.ngettext('day', 'days', int(days))
                    if mins:
                        if mins.startswith('0') and len(mins) > 1:
                            mins = mins[1:]
                        mins_text = gettext.ngettext('minute', 'minutes', int(mins))
                    if hours:
                        if hours.startswith('0'):
                            hours = hours[1:]
                        hours_text = gettext.ngettext('hour', 'hours', int(hours))
                    # Show text:
                    songs_text = gettext.ngettext('song', 'songs', int(self.status['playlistlength']))
                    if int(self.status['playlistlength']) > 0:
                        if days:
                            status_text = str(self.status['playlistlength']) + ' ' + songs_text + '   ' + days + ' ' + days_text + ', ' + hours + ' ' + hours_text + ', ' + _('and') + ' ' + mins + ' ' + mins_text
                        elif hours:
                            status_text = str(self.status['playlistlength']) + ' ' + songs_text + '   ' + hours + ' ' + hours_text + ' ' + _('and') + ' ' + mins + ' ' + mins_text
                        elif mins:
                            status_text = str(self.status['playlistlength']) + ' ' + songs_text + '   ' + mins + ' ' + mins_text
                        else:
                            status_text = ""
                    else:
                        status_text = ""
                    if updatingdb:
                        status_text = status_text + "   " + _("(updating mpd)")
                except:
                    status_text = ""
            else:
                status_text = ""
            if status_text != self.last_status_text:
                self.statusbar.push(self.statusbar.get_context_id(""), status_text)
                self.last_status_text = status_text

    def expander_ellipse_workaround(self):
        # Hacky workaround to ellipsize the expander - see
        # http://bugzilla.gnome.org/show_bug.cgi?id=406528
        cursonglabelwidth = self.expander.get_allocation().width - 15
        if cursonglabelwidth > 0:
            self.cursonglabel1.set_size_request(cursonglabelwidth, -1)
            self.cursonglabel1.set_size_request(cursonglabelwidth, -1)

    def update_cursong(self):
        if self.conn and self.status and self.status['state'] in ['play', 'pause']:
            # We must show the trayprogressbar and trayalbumeventbox
            # before changing self.cursonglabel (and consequently calling
            # self.on_currsong_notify()) in order to ensure that the notification
            # popup will have the correct height when being displayed for
            # the first time after a stopped state.
            if self.show_progress:
                self.trayprogressbar.show()
            self.traycursonglabel2.show()
            if self.show_covers:
                self.trayalbumeventbox.show()
                self.trayalbumimage2.show()

            for label in (self.cursonglabel1, self.cursonglabel2, self.traycursonglabel1, self.traycursonglabel2):
                label.set_ellipsize(pango.ELLIPSIZE_END)

            self.expander_ellipse_workaround()

            if len(self.currsongformat1) > 0:
                newlabel1 = '<big><b>' + self.parse_formatting(self.currsongformat1, self.songinfo, True) + ' </b></big>'
            else:
                newlabel1 = '<big><b> </b></big>'
            if len(self.currsongformat2) > 0:
                newlabel2 = '<small>' + self.parse_formatting(self.currsongformat2, self.songinfo, True) + ' </small>'
            else:
                newlabel2 = '<small> </small>'
            if newlabel1 != self.cursonglabel1.get_label():
                self.cursonglabel1.set_markup(newlabel1)
            if newlabel2 != self.cursonglabel2.get_label():
                self.cursonglabel2.set_markup(newlabel2)
            if newlabel1 != self.traycursonglabel1.get_label():
                self.traycursonglabel1.set_markup(newlabel1)
            if newlabel2 != self.traycursonglabel2.get_label():
                self.traycursonglabel2.set_markup(newlabel2)
            self.expander.set_tooltip_text(self.cursonglabel1.get_text() + "\n" + self.cursonglabel2.get_text())
        else:
            for label in (self.cursonglabel1, self.cursonglabel2, self.traycursonglabel1, self.cursonglabel2):
                label.set_ellipsize(pango.ELLIPSIZE_NONE)

            self.cursonglabel1.set_markup('<big><b>' + _('Stopped') + '</b></big>')
            if self.expanded:
                self.cursonglabel2.set_markup('<small>' + _('Click to collapse') + '</small>')
            else:
                self.cursonglabel2.set_markup('<small>' + _('Click to expand') + '</small>')
            self.expander.set_tooltip_text(self.cursonglabel1.get_text())
            if not self.conn:
                self.traycursonglabel1.set_label(_('Not Connected'))
            elif not self.status:
                self.traycursonglabel1.set_label(_('No Read Permission'))
            else:
                self.traycursonglabel1.set_label(_('Stopped'))
            self.trayprogressbar.hide()
            self.trayalbumeventbox.hide()
            self.trayalbumimage2.hide()
            self.traycursonglabel2.hide()
        self.update_infofile()

    def update_wintitle(self):
        if self.window_owner:
            if self.conn and self.status and self.status['state'] in ['play', 'pause']:
                newtitle = self.parse_formatting(self.titleformat, self.songinfo, False, True)
            else:
                newtitle = '[Sonata]'
            if not self.last_title or self.last_title != newtitle:
                self.window.set_property('title', newtitle)
                self.last_title = newtitle

    def current_update_format(self):
        for track in self.current_songs:
            items = []
            for part in self.columnformat:
                items += [self.parse_formatting(part, track, True)]

            self.currentdata.append([int(mpdh.get(track, 'id'))] + items)

    def current_update(self):
        if self.conn:

            if self.sonata_loaded:
                playlistposition = self.current.get_visible_rect()[1]

            self.current.freeze_child_notify()

            if not self.current_update_skip:

                if not self.filterbox_visible:
                    self.current.set_model(None)

                if self.prevstatus:
                    changed_songs = mpdh.call(self.client, 'plchanges', self.prevstatus['playlist'])
                else:
                    changed_songs = mpdh.call(self.client, 'plchanges', 0)
                    self.current_songs = []

                newlen = int(self.status['playlistlength'])
                currlen = len(self.currentdata)

                for track in changed_songs:
                    pos = int(mpdh.get(track, 'pos'))

                    items = []
                    for part in self.columnformat:
                        items += [self.parse_formatting(part, track, True)]

                    if pos < currlen:
                        # Update attributes for item:
                        iter = self.currentdata.get_iter((pos, ))
                        id = int(mpdh.get(track, 'id'))
                        if id != self.currentdata.get_value(iter, 0):
                            self.currentdata.set_value(iter, 0, id)
                        for index in range(len(items)):
                            if items[index] != self.currentdata.get_value(iter, index + 1):
                                self.currentdata.set_value(iter, index + 1, items[index])
                        self.current_songs[pos] = track
                    else:
                        # Add new item:
                        self.currentdata.append([int(mpdh.get(track, 'id'))] + items)
                        self.current_songs.append(track)

                if newlen == 0:
                    self.currentdata.clear()
                    self.current_songs = []
                else:
                    # Remove excess songs:
                    for i in range(currlen-newlen):
                        iter = self.currentdata.get_iter((newlen-1-i,))
                        self.currentdata.remove(iter)
                    self.current_songs = self.current_songs[:newlen]

                if not self.filterbox_visible:
                    self.current.set_model(self.currentdata)

            self.current_update_skip = False

            # Update statusbar time:
            self.total_time = 0
            for track in self.current_songs:
                try:
                    self.total_time = self.total_time + int(mpdh.get(track, 'time'))
                except:
                    pass

            if self.songinfo.has_key('pos'):
                currsong = int(mpdh.get(self.songinfo, 'pos'))
                self.boldrow(currsong)
                self.prev_boldrow = currsong
            if self.filterbox_visible:
                # Refresh filtered results:
                self.prevtodo = "RETAIN_POS_AND_SEL" # Hacky, but this ensures we retain the self.current position/selection
                self.plpos = playlistposition
                self.searchfilter_feed_loop(self.filterpattern)
            elif self.sonata_loaded:
                self.playlist_retain_view(self.current, playlistposition)
                self.current.thaw_child_notify()
            self.header_update_column_indicators()
            self.update_statusbar()
            ui.change_cursor(None)

    def header_update_column_indicators(self):
        # If we just sorted a column, display the sorting arrow:
        if self.column_sorted[0]:
            if self.column_sorted[1] == gtk.SORT_DESCENDING:
                self.header_hide_all_indicators(self.current, True)
                self.column_sorted[0].set_sort_order(gtk.SORT_ASCENDING)
                self.column_sorted = (None, gtk.SORT_ASCENDING)
            else:
                self.header_hide_all_indicators(self.current, True)
                self.column_sorted[0].set_sort_order(gtk.SORT_DESCENDING)
                self.column_sorted = (None, gtk.SORT_DESCENDING)

    def playlist_retain_view(self, listview, playlistposition):
        # Attempt to retain library position:
        try:
            # This is the weirdest thing I've ever seen. But if, for
            # example, you edit a song twice, the position of the
            # playlist will revert to the top the second time because
            # we are telling gtk to scroll to the same point as
            # before. So we will simply scroll to the top and then
            # back to the actual position. The first position change
            # shouldn't be visible by the user.
            listview.scroll_to_point(-1, 0)
            listview.scroll_to_point(-1, playlistposition)
        except:
            pass

    def header_hide_all_indicators(self, treeview, show_sorted_column):
        if not show_sorted_column:
            self.column_sorted = (None, gtk.SORT_DESCENDING)
        for column in treeview.get_columns():
            if show_sorted_column and column == self.column_sorted[0]:
                column.set_sort_indicator(True)
            else:
                column.set_sort_indicator(False)

    def current_center_song_in_list(self, event=None):
        if self.filterbox_visible:
            return
        if self.expanded and len(self.currentdata)>0:
            self.current.realize()
            try:
                row = mpdh.get(self.songinfo, 'pos', None)
                if row is None: return
                visible_rect = self.current.get_visible_rect()
                row_rect = self.current.get_background_area(row, self.columns[0])
                top_coord = (row_rect.y + row_rect.height - int(visible_rect.height/2)) + visible_rect.y
                self.current.scroll_to_point(-1, top_coord)
            except:
                pass

    def set_allow_art_search(self):
        self.allow_art_search = True

    def status_is_play_or_pause(self):
        return self.conn and self.status and self.status['state'] in ['play', 'pause']

    def tooltip_set_window_width(self):
        screen = self.window.get_screen()
        pointer_screen, px, py, _ = screen.get_display().get_pointer()
        monitor_num = screen.get_monitor_at_point(px, py)
        monitor = screen.get_monitor_geometry(monitor_num)
        self.notification_width = int(monitor.width * 0.30)
        if self.notification_width > self.NOTIFICATION_WIDTH_MAX:
            self.notification_width = self.NOTIFICATION_WIDTH_MAX
        elif self.notification_width < self.NOTIFICATION_WIDTH_MIN:
            self.notification_width = self.NOTIFICATION_WIDTH_MIN

    def on_currsong_notify(self, foo=None, bar=None, force_popup=False):
        if self.fullscreencoverart.get_property('visible'):
            return
        if self.sonata_loaded:
            if self.conn and self.status and self.status['state'] in ['play', 'pause']:
                if self.show_covers:
                    self.traytips.set_size_request(self.notification_width, -1)
                else:
                    self.traytips.set_size_request(self.notification_width-100, -1)
            else:
                self.traytips.set_size_request(-1, -1)
            if self.show_notification or force_popup:
                try:
                    gobject.source_remove(self.traytips.notif_handler)
                except:
                    pass
                if self.conn and self.status and self.status['state'] in ['play', 'pause']:
                    try:
                        self.traytips.notifications_location = self.traytips_notifications_location
                        self.traytips.use_notifications_location = True
                        if HAVE_STATUS_ICON and self.statusicon.is_embedded() and self.statusicon.get_visible():
                            self.traytips._real_display(self.statusicon)
                        elif HAVE_EGG and self.trayicon.get_property('visible'):
                            self.traytips._real_display(self.trayeventbox)
                        else:
                            self.traytips._real_display(None)
                        if self.popup_option != len(self.popuptimes)-1:
                            if force_popup and not self.show_notification:
                                # Used -p argument and notification is disabled in
                                # player; default to 3 seconds
                                timeout = 3000
                            else:
                                timeout = int(self.popuptimes[self.popup_option])*1000
                            self.traytips.notif_handler = gobject.timeout_add(timeout, self.traytips.hide)
                        else:
                            # -1 indicates that the timeout should be forever.
                            # We don't want to pass None, because then Sonata
                            # would think that there is no current notification
                            self.traytips.notif_handler = -1
                    except:
                        pass
                else:
                    self.traytips.hide()
            elif self.traytips.get_property('visible'):
                try:
                    self.traytips._real_display(self.trayeventbox)
                except:
                    pass

    def on_progressbar_notify_fraction(self, *args):
        self.trayprogressbar.set_fraction(self.progressbar.get_fraction())

    def on_progressbar_notify_text(self, *args):
        self.trayprogressbar.set_text(self.progressbar.get_text())

    def update_infofile(self):
        if self.use_infofile is True:
            try:
                info_file = open(self.infofile_path, 'w')

                if self.status['state'] in ['play']:
                    info_file.write('Status: ' + 'Playing' + '\n')
                elif self.status['state'] in ['pause']:
                    info_file.write('Status: ' + 'Paused' + '\n')
                elif self.status['state'] in ['stop']:
                    info_file.write('Status: ' + 'Stopped' + '\n')
                try:
                    info_file.write('Title: ' + mpdh.get(self.songinfo, 'artist') + ' - ' + mpdh.get(self.songinfo, 'title') + '\n')
                except:
                    try:
                        info_file.write('Title: ' + mpdh.get(self.songinfo, 'title') + '\n') # No Arist in streams
                    except:
                        info_file.write('Title: No - ID Tag\n')
                info_file.write('Album: ' + mpdh.get(self.songinfo, 'album', 'No Data') + '\n')
                info_file.write('Track: ' + mpdh.get(self.songinfo, 'track', '0') + '\n')
                info_file.write('File: ' + mpdh.get(self.songinfo, 'file', 'No Data') + '\n')
                info_file.write('Time: ' + mpdh.get(self.songinfo, 'time', '0') + '\n')
                info_file.write('Volume: ' + self.status['volume'] + '\n')
                info_file.write('Repeat: ' + self.status['repeat'] + '\n')
                info_file.write('Random: ' + self.status['random'] + '\n')
                info_file.close()
            except:
                pass

    #################
    # Gui Callbacks #
    #################

    def on_delete_event_yes(self, widget):
        self.exit_now = True
        self.on_delete_event(None, None)

    # This one makes sure the program exits when the window is closed
    def on_delete_event(self, widget, data=None):
        if not self.exit_now and self.minimize_to_systray:
            if HAVE_STATUS_ICON and self.statusicon.is_embedded() and self.statusicon.get_visible():
                self.withdraw_app()
                return True
            elif HAVE_EGG and self.trayicon.get_property('visible'):
                self.withdraw_app()
                return True
        self.settings_save()
        if self.as_enabled:
            self.scrobbler_save_cache()
        if self.conn and self.stop_on_exit:
            self.mpd_stop(None)
        sys.exit()
        return False

    def on_window_state_change(self, widget, event):
        self.volume_hide()

    def on_window_lost_focus(self, widget, event):
        self.volume_hide()

    def on_window_configure(self, widget, event):
        width, height = self.window.get_size()
        if self.expanded: self.w, self.h = width, height
        else: self.w = width
        self.x, self.y = self.window.get_position()
        self.expander_ellipse_workaround()

    def on_notebook_resize(self, widget, event):
        if not self.resizing_columns :
            gobject.idle_add(self.header_save_column_widths)
        gobject.idle_add(self.info_resize_elements)

    def info_resize_elements(self):
        # Resize labels in info tab to prevent horiz scrollbar:
        if self.show_covers:
            labelwidth = self.notebook.allocation.width - self.info_left_label.allocation.width - self.info_imagebox.allocation.width - 60 # 60 accounts for vert scrollbar, box paddings, etc..
        else:
            labelwidth = self.notebook.allocation.width - self.info_left_label.allocation.width - 60 # 60 accounts for vert scrollbar, box paddings, etc..
        if labelwidth > 100:
            for label in self.info_labels:
                label.set_size_request(labelwidth, -1)
        # Resize lyrics/album gtk labels:
        labelwidth = self.notebook.allocation.width - 45 # 45 accounts for vert scrollbar, box paddings, etc..
        self.lyricsText.set_size_request(labelwidth, -1)
        self.albumText.set_size_request(labelwidth, -1)

    def on_expand(self, action):
        if not self.expanded:
            self.expander.set_expanded(False)
            self.on_expander_activate(None)
            self.expander.set_expanded(True)

    def on_collapse(self, action):
        if self.expanded:
            self.expander.set_expanded(True)
            self.on_expander_activate(None)
            self.expander.set_expanded(False)

    def on_expander_activate(self, expander):
        currheight = self.window.get_size()[1]
        self.expanded = False
        # Note that get_expanded() will return the state of the expander
        # before this current click
        window_about_to_be_expanded = not self.expander.get_expanded()
        if window_about_to_be_expanded:
            if self.window.get_size()[1] == self.h:
                # For WMs like ion3, the app will not actually resize
                # when in collapsed mode, so prevent the waiting
                # of the player to expand from happening:
                skip_size_check = True
            else:
                skip_size_check = False
            if self.show_statusbar:
                self.statusbar.show()
            self.notebook.show_all()
        else:
            self.statusbar.hide()
            self.notebook.hide()
        if not (self.conn and self.status and self.status['state'] in ['play', 'pause']):
            if window_about_to_be_expanded:
                self.cursonglabel2.set_markup('<small>' + _('Click to collapse') + '</small>')
            else:
                self.cursonglabel2.set_markup('<small>' + _('Click to expand') + '</small>')
        # Now we wait for the height of the player to increase, so that
        # we know the list is visible. This is pretty hacky, but works.
        if self.window_owner:
            if window_about_to_be_expanded:
                if not skip_size_check:
                    while self.window.get_size()[1] == currheight:
                        gtk.main_iteration()
                # Notebook is visible, now resize:
                self.window.resize(self.w, self.h)
            else:
                self.window.resize(self.w, 1)
        if window_about_to_be_expanded:
            self.expanded = True
            if self.status and self.status['state'] in ['play','pause']:
                gobject.idle_add(self.current_center_song_in_list)
            self.window.set_geometry_hints(self.window)
        # Put focus to the notebook:
        self.on_notebook_page_change(self.notebook, 0, self.notebook.get_current_page())
        return

    # This callback allows the user to seek to a specific portion of the song
    def on_progressbar_press(self, widget, event):
        if event.button == 1:
            if self.status and self.status['state'] in ['play', 'pause']:
                at, length = [int(c) for c in self.status['time'].split(':')]
                try:
                    pbsize = self.progressbar.allocation
                    if misc.is_lang_rtl(self.window):
                        seektime = int(((pbsize.width-event.x)/pbsize.width) * length)
                    else:
                        seektime = int((event.x/pbsize.width) * length)
                    self.seek(int(self.status['song']), seektime)
                except:
                    pass
            return True

    def on_progressbar_scroll(self, widget, event):
        if self.status and self.status['state'] in ['play', 'pause']:
            try:
                gobject.source_remove(self.seekidle)
            except:
                pass
            self.seekidle = gobject.idle_add(self._seek_when_idle, event.direction)
        return True

    def _seek_when_idle(self, direction):
        at, length = [int(c) for c in self.status['time'].split(':')]
        try:
            if direction == gtk.gdk.SCROLL_UP:
                seektime = int(self.status['time'].split(":")[0]) - 5
                if seektime < 0: seektime = 0
            elif direction == gtk.gdk.SCROLL_DOWN:
                seektime = int(self.status['time'].split(":")[0]) + 5
                if seektime > mpdh.get(self.songinfo, 'time'):
                    seektime = mpdh.get(self.songinfo, 'time')
            self.seek(int(self.status['song']), seektime)
        except:
            pass

    def on_lyrics_search(self, event):
        artist = mpdh.get(self.songinfo, 'artist')
        title = mpdh.get(self.songinfo, 'title')
        dialog = ui.dialog(title=_('Lyrics Search'), parent=self.window, flags=gtk.DIALOG_MODAL | gtk.DIALOG_DESTROY_WITH_PARENT, buttons=(gtk.STOCK_CANCEL, gtk.RESPONSE_REJECT, gtk.STOCK_FIND, gtk.RESPONSE_ACCEPT), role='lyricsSearch', default=gtk.RESPONSE_ACCEPT)
        dialog.action_area.get_children()[0].set_label(_("_Search"))
        dialog.action_area.get_children()[0].set_image(ui.image(stock=gtk.STOCK_FIND))
        artist_hbox = gtk.HBox()
        artist_label = ui.label(text=_('Artist Name') + ':')
        artist_hbox.pack_start(artist_label, False, False, 5)
        artist_entry = ui.entry(text=artist)
        artist_hbox.pack_start(artist_entry, True, True, 5)
        title_hbox = gtk.HBox()
        title_label = ui.label(text=_('Song Title') + ':')
        title_hbox.pack_start(title_label, False, False, 5)
        title_entry = ui.entry(title)
        title_hbox.pack_start(title_entry, True, True, 5)
        ui.set_widths_equal([artist_label, title_label])
        dialog.vbox.pack_start(artist_hbox)
        dialog.vbox.pack_start(title_hbox)
        ui.show(dialog.vbox)
        response = dialog.run()
        if response == gtk.RESPONSE_ACCEPT:
            dialog.destroy()
            # Delete current lyrics:
            fname = misc.strip_all_slashes(artist + '-' + title + '.txt')
            filename = os.path.expanduser('~/.lyrics/' + fname)
            misc.remove_file(filename)
            # Search for new lyrics:
            lyricThread = threading.Thread(target=self.info_get_lyrics, args=(artist_entry.get_text(), title_entry.get_text(), artist, title))
            lyricThread.setDaemon(True)
            lyricThread.start()
        else:
            dialog.destroy()

    def on_current_column_click(self, column):
        columns = self.current.get_columns()
        col_num = 0
        for col in columns:
            col_num = col_num + 1
            if column == col:
                self.sort('col' + str(col_num), column)
                return

    def on_sort_by_artist(self, action):
        self.sort('artist', lower=misc.lower_no_the)

    def on_sort_by_album(self, action):
        self.sort('album', lower=misc.lower_no_the)

    def on_sort_by_title(self, action):
        self.sort('title')

    def on_sort_by_file(self, action):
        self.sort('file')

    def on_sort_by_dirfile(self, action):
        self.sort('dirfile')

    def sort(self, type, column=None, lower=lambda x: x.lower()):
        if self.conn:
            if not self.status or self.status['playlistlength'] == '0':
                return

            while gtk.events_pending():
                gtk.main_iteration()
            list = []
            track_num = 0

            if type[0:3] == 'col':
                col_num = int(type.replace('col', ''))
                if column.get_sort_indicator():
                    # If this column was already sorted, reverse list:
                    self.column_sorted = (column, self.column_sorted[1])
                    self.on_sort_reverse(None)
                    return
                else:
                    self.column_sorted = (column, gtk.SORT_DESCENDING)
                type = "col"

            # If the first tag in the format is song length, we will make sure to compare
            # the same number of items in the song length string (e.g. always use
            # ##:##:##) and pad the first item to two (e.g. #:##:## -> ##:##:##)
            custom_sort = False
            if type == 'col':
                custom_sort, custom_pos = self.sort_get_first_format_tag(self.currentformat, col_num, 'L')

            for track in self.current_songs:
                dict = {}
                # Those items that don't have the specified tag will be put at
                # the end of the list (hence the 'zzzzzzz'):
                zzz = 'zzzzzzzz'
                if type == 'artist':
                    dict["sortby"] =  (misc.lower_no_the(mpdh.get(track, 'artist', zzz)),
                                mpdh.get(track, 'album', zzz).lower(),
                                mpdh.getnum(track, 'disc', '0', True, 0),
                                mpdh.getnum(track, 'track', '0', True, 0))
                elif type == 'album':
                    dict["sortby"] =  (mpdh.get(track, 'album', zzz).lower(),
                                mpdh.getnum(track, 'disc', '0', True, 0),
                                mpdh.getnum(track, 'track', '0', True, 0))
                elif type == 'file':
                    dict["sortby"] = mpdh.get(track, 'file', zzz).lower().split('/')[-1]
                elif type == 'dirfile':
                    dict["sortby"] = mpdh.get(track, 'file', zzz).lower()
                elif type == 'col':
                    # Sort by column:
                    dict["sortby"] = misc.unbold(self.currentdata.get_value(self.currentdata.get_iter((track_num, 0)), col_num).lower())
                    if custom_sort:
                        dict["sortby"] = self.sanitize_songlen_for_sorting(dict["sortby"], custom_pos)
                else:
                    dict["sortby"] = mpdh.get(track, type, zzz).lower()
                dict["id"] = int(track["id"])
                list.append(dict)
                track_num = track_num + 1

            list.sort(key=lambda x: x["sortby"])

            pos = 0
            mpdh.call(self.client, 'command_list_ok_begin')
            for item in list:
                mpdh.call(self.client, 'moveid', item["id"], pos)
                pos += 1
            mpdh.call(self.client, 'command_list_end')
            self.iterate_now()

            self.header_update_column_indicators()

    def sort_get_first_format_tag(self, format, colnum, tag_letter):
        # Returns a tuple with whether the first tag of the format
        # includes tag_letter and the position of the tag in the string:
        formats = format.split('|')
        format = formats[colnum-1]
        for pos in range(len(format)-1):
            if format[pos] == '%':
                if format[pos+1] == tag_letter:
                    return (True, pos)
                else:
                    break
        return (False, 0)

    def sanitize_songlen_for_sorting(self, songlength, pos_of_string):
        songlength = songlength[pos_of_string:]
        items = songlength.split(':')
        for i in range(len(items)):
            items[i] = items[i].zfill(2)
        for i in range(3-len(items)):
            items.insert(0, "00")
        return items[0] + ":" + items[1] + ":" + items[2]

    def on_sort_reverse(self, action):
        if self.conn:
            if not self.status or self.status['playlistlength'] == '0':
                return
            while gtk.events_pending():
                gtk.main_iteration()
            top = 0
            bot = int(self.status['playlistlength'])-1
            mpdh.call(self.client, 'command_list_ok_begin')
            while top < bot:
                mpdh.call(self.client, 'swap', top, bot)
                top = top + 1
                bot = bot - 1
            mpdh.call(self.client, 'command_list_end')
            self.iterate_now()

    def mpd_shuffle(self, action):
        if self.conn:
            if not self.status or self.status['playlistlength'] == '0':
                return
            ui.change_cursor(gtk.gdk.Cursor(gtk.gdk.WATCH))
            while gtk.events_pending():
                gtk.main_iteration()
            mpdh.call(self.client, 'shuffle')

    def on_dnd(self, treeview, drag_context, x, y, selection, info, timestamp):
        drop_info = treeview.get_dest_row_at_pos(x, y)

        if selection.data is not None:
            if not os.path.isdir(misc.file_from_utf8(self.musicdir[self.profile_num])):
                return
            # DND from outside sonata:
            uri = selection.data.strip()
            path = urllib.url2pathname(uri)
            paths = path.rsplit('\n')
            mpdpaths = []
            # Strip off paranthesis so that we can DND entire music dir
            # if we wish.
            musicdir = self.musicdir[self.profile_num][:-1]
            for i, path in enumerate(paths):
                paths[i] = path.rstrip('\r')
                if paths[i].startswith('file://'):
                    paths[i] = paths[i][7:]
                elif paths[i].startswith('file:'):
                    paths[i] = paths[i][5:]
                if paths[i].startswith(musicdir):
                    paths[i] = paths[i][len(self.musicdir[self.profile_num]):]
                    if len(paths[i]) == 0: paths[i] = "/"
                    listallinfo = mpdh.call(self.client, 'listallinfo', paths[i])
                    for item in listallinfo:
                        if item.has_key('file'):
                            mpdpaths.append(mpdh.get(item, 'file'))
                elif self.mpd_major_version() >= 0.14:
                    # Add local file, available in mpd 0.14. This currently won't
                    # work because python-mpd does not support unix socket paths,
                    # which is needed for authentication for local files. It's also
                    # therefore untested.
                    if os.path.isdir(misc.file_from_utf8(paths[i])):
                        filenames = misc.get_files_recursively(paths[i])
                    else:
                        filenames = [paths[i]]
                    for filename in filenames:
                        if os.path.exists(misc.file_from_utf8(filename)):
                            mpdpaths.append("file://" + urllib.quote(filename))
            if len(mpdpaths) > 0:
                # Items found, add to list at drop position:
                if drop_info:
                    destpath, position = drop_info
                    if position in (gtk.TREE_VIEW_DROP_BEFORE, gtk.TREE_VIEW_DROP_INTO_OR_BEFORE):
                        id = destpath[0]
                    else:
                        id = destpath[0] + 1
                else:
                    id = int(self.status['playlistlength'])
                for mpdpath in mpdpaths:
                    mpdh.call(self.client, 'addid', mpdpath, id)
            self.iterate_now()
            return

        # Otherwise, it's a DND just within the current playlist
        model = treeview.get_model()
        foobar, selected = self.current_selection.get_selected_rows()

        # calculate all this now before we start moving stuff
        drag_sources = []
        for path in selected:
            index = path[0]
            iter = model.get_iter(path)
            id = self.current_get_songid(iter, model)
            text = model.get_value(iter, 1)
            drag_sources.append([index, iter, id, text])

        # Keep track of the moved iters so we can select them afterwards
        moved_iters = []

        # We will manipulate self.current_songs and model to prevent the entire playlist
        # from refreshing
        offset = 0
        mpdh.call(self.client, 'command_list_ok_begin')
        for source in drag_sources:
            index, iter, id, text = source
            if drop_info:
                destpath, position = drop_info
                dest = destpath[0] + offset
                if dest < index:
                    offset = offset + 1
                if position in (gtk.TREE_VIEW_DROP_BEFORE, gtk.TREE_VIEW_DROP_INTO_OR_BEFORE):
                    self.current_songs.insert(dest, self.current_songs[index])
                    if dest < index+1:
                        self.current_songs.pop(index+1)
                        mpdh.call(self.client, 'moveid', id, dest)
                    else:
                        self.current_songs.pop(index)
                        mpdh.call(self.client, 'moveid', id, dest-1)
                    model.insert(dest, model[index])
                    moved_iters += [model.get_iter((dest,))]
                    model.remove(iter)
                else:
                    self.current_songs.insert(dest+1, self.current_songs[index])
                    if dest < index:
                        self.current_songs.pop(index+1)
                        mpdh.call(self.client, 'moveid', id, dest+1)
                    else:
                        self.current_songs.pop(index)
                        mpdh.call(self.client, 'moveid', id, dest)
                    model.insert(dest+1, model[index])
                    moved_iters += [model.get_iter((dest+1,))]
                    model.remove(iter)
            else:
                dest = int(self.status['playlistlength']) - 1
                mpdh.call(self.client, 'moveid', id, dest)
                self.current_songs.insert(dest+1, self.current_songs[index])
                self.current_songs.pop(index)
                model.insert(dest+1, model[index])
                moved_iters += [model.get_iter((dest+1,))]
                model.remove(iter)
            # now fixup
            for source in drag_sources:
                if dest < index:
                    # we moved it back, so all indexes inbetween increased by 1
                    if dest < source[0] < index:
                        source[0] += 1
                else:
                    # we moved it ahead, so all indexes inbetween decreased by 1
                    if index < source[0] < dest:
                        source[0] -= 1
        mpdh.call(self.client, 'command_list_end')

        # we are manipulating the model manually for speed, so...
        self.current_update_skip = True

        if drag_context.action == gtk.gdk.ACTION_MOVE:
            drag_context.finish(True, True, timestamp)
            self.header_hide_all_indicators(self.current, False)
        self.iterate_now()

        gobject.idle_add(self.dnd_retain_selection, treeview.get_selection(), moved_iters)

    def dnd_retain_selection(self, treeselection, moved_iters):
        treeselection.unselect_all()
        for iter in moved_iters:
            treeselection.select_iter(iter)

    def on_menu_popup(self, widget):
        self.update_menu_visibility()
        gobject.idle_add(self.mainmenu.popup, None, None, self.menu_position, 3, 0)

    def on_updatedb(self, widget):
        if self.conn:
            if self.library_search_visible():
                self.on_library_search_end(None)
            self.mpd_update('/')
            self.iterate_now()

    def on_updatedb_path(self, action):
        if self.conn:
            if self.current_tab == self.TAB_LIBRARY:
                if self.library_search_visible():
                    self.on_library_search_end(None)
                model, selected = self.library_selection.get_selected_rows()
                iters = [model.get_iter(path) for path in selected]
                if len(iters) > 0:
                    # If there are selected rows, update these paths..
                    mpdh.call(self.client, 'command_list_ok_begin')
                    for iter in iters:
                        self.mpd_update(self.librarydata.get_value(iter, 1))
                    mpdh.call(self.client, 'command_list_end')
                else:
                    # If no selection, update the current path...
                    self.mpd_update(self.wd)
                self.iterate_now()

    def on_image_activate(self, widget, event):
        self.window.handler_block(self.mainwinhandler)
        if event.button == 1 and widget == self.info_imagebox and self.artwork.have_last():
            if not self.info_art_enlarged:
                self.info_imagebox.set_size_request(-1,-1)
                self.artwork.artwork_set_image_last(True)
                self.info_art_enlarged = True
            else:
                self.info_imagebox.set_size_request(152, -1)
                self.artwork.artwork_set_image_last(True)
                self.info_art_enlarged = False
            self.volume_hide()
            # Force a resize of the info labels, if needed:
            gobject.idle_add(self.on_notebook_resize, self.notebook, None)
        elif event.button == 1 and widget != self.info_imagebox:
            if self.expanded:
                if self.current_tab != self.TAB_INFO:
                    self.img_clicked = True
                    self.switch_to_tab_name(self.TAB_INFO)
                    self.img_clicked = False
                else:
                    self.switch_to_tab_name(self.last_tab)
        elif event.button == 3:
            artist = None
            album = None
            stream = None
            if self.conn and self.status and self.status['state'] in ['play', 'pause']:
                if self.covers_pref != self.ART_LOCAL:
                    self.UIManager.get_widget('/imagemenu/chooseimage_menu/').show()
                else:
                    self.UIManager.get_widget('/imagemenu/chooseimage_menu/').hide()
                self.UIManager.get_widget('/imagemenu/localimage_menu/').show()
                artist = mpdh.get(self.songinfo, 'artist', None)
                album = mpdh.get(self.songinfo, 'album', None)
                stream = mpdh.get(self.songinfo, 'name', None)
            if not (artist or album or stream):
                self.UIManager.get_widget('/imagemenu/localimage_menu/').hide()
                self.UIManager.get_widget('/imagemenu/resetimage_menu/').hide()
                self.UIManager.get_widget('/imagemenu/chooseimage_menu/').hide()
            self.imagemenu.popup(None, None, None, event.button, event.time)
        gobject.timeout_add(50, self.on_image_activate_after)
        return False

    def on_image_motion_cb(self, widget, context, x, y, time):
        context.drag_status(gtk.gdk.ACTION_COPY, time)
        return True

    def on_image_drop_cb(self, widget, context, x, y, selection, info, time):
        if self.conn and self.status and self.status['state'] in ['play', 'pause']:
            uri = selection.data.strip()
            path = urllib.url2pathname(uri)
            paths = path.rsplit('\n')
            thread = threading.Thread(target=self.on_image_drop_cb_thread, args=(paths,))
            thread.setDaemon(True)
            thread.start()

    def on_image_drop_cb_thread(self, paths):
        for i, path in enumerate(paths):
            remove_after_set = False
            paths[i] = path.rstrip('\r')
            # Clean up (remove preceding "file://" or "file:")
            if paths[i].startswith('file://'):
                paths[i] = paths[i][7:]
            elif paths[i].startswith('file:'):
                paths[i] = paths[i][5:]
            elif re.match('^(https?|ftp)://', paths[i]):
                try:
                    # Eliminate query arguments and extract extension & filename
                    path = urllib.splitquery(paths[i])[0]
                    extension = os.path.splitext(path)[1][1:]
                    filename = os.path.split(path)[1]
                    if img.extension_is_valid(extension):
                        # Save to temp dir.. we will delete the image afterwards
                        dest_file = os.path.expanduser('~/.covers/temp/' + filename)
                        misc.create_dir('~/.covers/temp')
                        urllib.urlretrieve(paths[i], dest_file)
                        paths[i] = dest_file
                        remove_after_set = True
                    else:
                        continue
                except:
                    # cleanup undone file
                    misc.remove_file(paths[i])
                    raise
            paths[i] = os.path.abspath(paths[i])
            if img.valid_image(paths[i]):
                stream = mpdh.get(self.songinfo, 'name', None)
                if stream is not None:
                    dest_filename = self.artwork.artwork_stream_filename(mpdh.get(self.songinfo, 'name'))
                else:
                    dest_filename = self.target_image_filename()
                if dest_filename != paths[i]:
                    shutil.copyfile(paths[i], dest_filename)
                self.artwork.artwork_update(True)
                if remove_after_set:
                    misc.remove_file(paths[i])

    def target_lyrics_filename(self, artist, title, force_location=None):
        if self.conn:
            if force_location is not None:
                lyrics_loc = force_location
            else:
                lyrics_loc = self.lyrics_location
            if lyrics_loc == self.LYRICS_LOCATION_HOME:
                targetfile = os.path.expanduser("~/.lyrics/" + artist + "-" + title + ".txt")
            elif lyrics_loc == self.LYRICS_LOCATION_PATH:
                targetfile = self.musicdir[self.profile_num] + os.path.dirname(mpdh.get(self.songinfo, 'file')) + "/" + artist + "-" + title + ".txt"
            targetfile = misc.file_exists_insensitive(targetfile)
            return misc.file_from_utf8(targetfile)

    def target_image_filename(self, force_location=None, songpath=None, artist=None, album=None):
        # Only pass songpath, artist, and album if we are trying to get the
        # filename for an album that isn't currently playing
        if self.conn:
            # If no info passed, you info from currently playing song:
            if not album:
                album = mpdh.get(self.songinfo, 'album', "")
            if not artist:
                artist = self.album_current_artist[1]
            album = album.replace("/", "")
            artist = artist.replace("/", "")
            if songpath is None:
                songpath = os.path.dirname(mpdh.get(self.songinfo, 'file'))
            # Return target filename:
            if force_location is not None:
                art_loc = force_location
            else:
                art_loc = self.art_location
            if art_loc == self.ART_LOCATION_HOMECOVERS:
                targetfile = os.path.expanduser("~/.covers/" + artist + "-" + album + ".jpg")
            elif art_loc == self.ART_LOCATION_COVER:
                targetfile = self.musicdir[self.profile_num] + songpath + "/cover.jpg"
            elif art_loc == self.ART_LOCATION_FOLDER:
                targetfile = self.musicdir[self.profile_num] + songpath + "/folder.jpg"
            elif art_loc == self.ART_LOCATION_ALBUM:
                targetfile = self.musicdir[self.profile_num] + songpath + "/album.jpg"
            elif art_loc == self.ART_LOCATION_CUSTOM:
                targetfile = self.musicdir[self.profile_num] + songpath + "/" + self.art_location_custom_filename
            targetfile = misc.file_exists_insensitive(targetfile)
            return misc.file_from_utf8(targetfile)

    def album_return_artist_name(self):
        # Determine if album_name is a various artists album.
        if self.album_current_artist[0] == self.songinfo:
            return
        list = []
        album = mpdh.get(self.songinfo, 'album')
        songs, playtime, num_songs = self.library_return_search_items(album=album)
        for song in songs:
            year = mpdh.get(song, 'date', '')
            artist = mpdh.get(song, 'artist', '')
            data = self.library_set_data(album=album, artist=artist, year=year)
            list.append(data)
        list = misc.remove_list_duplicates(list, case=False)
        list = self.list_identify_VA_albums(list)
        artist = self.library_get_data(list[0], 'artist')
        self.album_current_artist = [self.songinfo, artist]

    def album_reset_artist(self):
        self.album_current_artist = [None, ""]

    def on_image_activate_after(self):
        self.window.handler_unblock(self.mainwinhandler)

    def update_preview(self, file_chooser, preview):
        filename = file_chooser.get_preview_filename()
        pixbuf = None
        try:
            pixbuf = gtk.gdk.pixbuf_new_from_file_at_size(filename, 128, 128)
        except:
            pass
        if pixbuf == None:
            try:
                pixbuf = gtk.gdk.PixbufAnimation(filename).get_static_image()
                width = pixbuf.get_width()
                height = pixbuf.get_height()
                if width > height:
                    pixbuf = pixbuf.scale_simple(128, int(float(height)/width*128), gtk.gdk.INTERP_HYPER)
                else:
                    pixbuf = pixbuf.scale_simple(int(float(width)/height*128), 128, gtk.gdk.INTERP_HYPER)
            except:
                pass
        if pixbuf == None:
            pixbuf = gtk.gdk.Pixbuf(gtk.gdk.COLORSPACE_RGB, 1, 8, 128, 128)
            pixbuf.fill(0x00000000)
        preview.set_from_pixbuf(pixbuf)
        have_preview = True
        file_chooser.set_preview_widget_active(have_preview)
        del pixbuf
        self.call_gc_collect = True

    def image_local(self, widget):
        dialog = gtk.FileChooserDialog(title=_("Open Image"),action=gtk.FILE_CHOOSER_ACTION_OPEN,buttons=(gtk.STOCK_CANCEL,gtk.RESPONSE_CANCEL,gtk.STOCK_OPEN,gtk.RESPONSE_OK))
        filter = gtk.FileFilter()
        filter.set_name(_("Images"))
        filter.add_pixbuf_formats()
        dialog.add_filter(filter)
        filter = gtk.FileFilter()
        filter.set_name(_("All files"))
        filter.add_pattern("*")
        dialog.add_filter(filter)
        preview = ui.image()
        dialog.set_preview_widget(preview)
        dialog.set_use_preview_label(False)
        dialog.connect("update-preview", self.update_preview, preview)
        stream = mpdh.get(self.songinfo, 'name', None)
        album = mpdh.get(self.songinfo, 'album', "").replace("/", "")
        artist = self.album_current_artist[1].replace("/", "")
        dialog.connect("response", self.image_local_response, artist, album, stream)
        dialog.set_default_response(gtk.RESPONSE_OK)
        songdir = os.path.dirname(mpdh.get(self.songinfo, 'file'))
        currdir = misc.file_from_utf8(self.musicdir[self.profile_num] + songdir)
        if self.art_location != self.ART_LOCATION_HOMECOVERS:
            dialog.set_current_folder(currdir)
        if stream is not None:
            # Allow saving an image file for a stream:
            self.local_dest_filename = self.artwork.artwork_stream_filename(stream)
        else:
            self.local_dest_filename = self.target_image_filename()
        dialog.show()

    def image_local_response(self, dialog, response, artist, album, stream):
        if response == gtk.RESPONSE_OK:
            filename = dialog.get_filenames()[0]
            # Copy file to covers dir:
            if self.local_dest_filename != filename:
                shutil.copyfile(filename, self.local_dest_filename)
            # And finally, set the image in the interface:
            self.artwork.artwork_update(True)
            # Force a resize of the info labels, if needed:
            gobject.idle_add(self.on_notebook_resize, self.notebook, None)
        dialog.destroy()

    def imagelist_append(self, elem):
        self.imagelist.append(elem)

    def remotefilelist_append(self, elem):
        self.remotefilelist.append(elem)

    def image_remote(self, widget):
        self.choose_dialog = ui.dialog(title=_("Choose Cover Art"), parent=self.window, flags=gtk.DIALOG_MODAL, buttons=(gtk.STOCK_CANCEL, gtk.RESPONSE_REJECT), role='chooseCoverArt', default=gtk.RESPONSE_ACCEPT, separator=False, resizable=False)
        choosebutton = self.choose_dialog.add_button(_("C_hoose"), gtk.RESPONSE_ACCEPT)
        chooseimage = ui.image(stock=gtk.STOCK_CONVERT, stocksize=gtk.ICON_SIZE_BUTTON)
        choosebutton.set_image(chooseimage)
        self.imagelist = gtk.ListStore(int, gtk.gdk.Pixbuf)
        imagewidget = ui.iconview(col=2, space=5, margin=10, itemw=150, selmode=gtk.SELECTION_SINGLE)
        scroll = ui.scrollwindow(policy_x=gtk.POLICY_NEVER, policy_y=gtk.POLICY_ALWAYS, w=350, h=325, add=imagewidget)
        self.choose_dialog.vbox.pack_start(scroll, False, False, 0)
        hbox = gtk.HBox()
        vbox = gtk.VBox()
        vbox.pack_start(ui.label(markup='<small> </small>'), False, False, 0)
        self.remote_artistentry = ui.entry()
        self.remote_albumentry = ui.entry()
        entries = [self.remote_artistentry, self.remote_albumentry]
        text = [("Artist"), _("Album")]
        labels = []
        for i in range(len(entries)):
            tmphbox = gtk.HBox()
            tmplabel = ui.label(text=text[i] + ": ")
            labels.append(tmplabel)
            tmphbox.pack_start(tmplabel, False, False, 5)
            entries[i].connect('activate', self.image_remote_refresh, imagewidget)
            tmphbox.pack_start(entries[i], True, True, 5)
            vbox.pack_start(tmphbox)
        ui.set_widths_equal(labels)
        vbox.pack_start(ui.label(markup='<small> </small>'), False, False, 0)
        hbox.pack_start(vbox, True, True, 5)
        vbox2 = gtk.VBox()
        vbox2.pack_start(ui.label(" "))
        refreshbutton = ui.button(text=_('_Update'), img=ui.image(stock=gtk.STOCK_REFRESH))
        refreshbutton.connect('clicked', self.image_remote_refresh, imagewidget)
        vbox2.pack_start(refreshbutton, False, False, 5)
        vbox2.pack_start(ui.label(" "))
        hbox.pack_start(vbox2, False, False, 15)
        searchexpander = ui.expander(text=_("Edit search terms"))
        searchexpander.add(hbox)
        self.choose_dialog.vbox.pack_start(searchexpander, True, True, 0)
        self.choose_dialog.show_all()
        self.chooseimage_visible = True
        self.remotefilelist = []
        stream = mpdh.get(self.songinfo, 'name', None)
        if stream is not None:
            # Allow saving an image file for a stream:
            self.remote_dest_filename = self.artwork.artwork_stream_filename(stream)
        else:
            self.remote_dest_filename = self.target_image_filename()
        album = mpdh.get(self.songinfo, 'album', '')
        artist = self.album_current_artist[1]
        imagewidget.connect('item-activated', self.image_remote_replace_cover, artist.replace("/", ""), album.replace("/", ""), stream)
        self.choose_dialog.connect('response', self.image_remote_response, imagewidget, artist, album, stream)
        self.remote_artistentry.set_text(artist)
        self.remote_albumentry.set_text(album)
        self.allow_art_search = True
        self.image_remote_refresh(None, imagewidget)

    def image_remote_refresh(self, entry, imagewidget):
        if not self.allow_art_search:
            return
        self.allow_art_search = False
        self.artwork.stop_art_update = True
        while self.artwork.downloading_image:
            gtk.main_iteration()
        self.imagelist.clear()
        imagewidget.set_text_column(-1)
        imagewidget.set_model(self.imagelist)
        imagewidget.set_pixbuf_column(1)
        ui.focus(imagewidget)
        ui.change_cursor(gtk.gdk.Cursor(gtk.gdk.WATCH))
        thread = threading.Thread(target=self._image_remote_refresh, args=(imagewidget, None))
        thread.setDaemon(True)
        thread.start()

    def _image_remote_refresh(self, imagewidget, ignore):
        self.artwork.stop_art_update = False
        # Retrieve all images from amazon:
        artist_search = self.remote_artistentry.get_text()
        album_search = self.remote_albumentry.get_text()
        if len(artist_search) == 0 and len(album_search) == 0:
            gobject.idle_add(self.image_remote_no_tag_found, imagewidget)
            return
        filename = os.path.expanduser("~/.covers/temp/<imagenum>.jpg")
        misc.remove_dir(os.path.dirname(filename))
        misc.create_dir(os.path.dirname(filename))
        imgfound = self.artwork.artwork_download_img_to_file(artist_search, album_search, filename, True)
        ui.change_cursor(None)
        if self.chooseimage_visible:
            if not imgfound:
                gobject.idle_add(self.image_remote_no_covers_found, imagewidget)
        self.call_gc_collect = True

    def image_remote_no_tag_found(self, imagewidget):
        self.image_remote_warning(imagewidget, _("No artist or album name found."))

    def image_remote_no_covers_found(self, imagewidget):
        self.image_remote_warning(imagewidget, _("No cover art found."))

    def image_remote_warning(self, imagewidget, msgstr):
        liststore = gtk.ListStore(int, str)
        liststore.append([0, msgstr])
        imagewidget.set_pixbuf_column(-1)
        imagewidget.set_model(liststore)
        imagewidget.set_text_column(1)
        ui.change_cursor(None)
        self.allow_art_search = True

    def image_remote_response(self, dialog, response_id, imagewidget, artist, album, stream):
        self.artwork.stop_art_update = True
        if response_id == gtk.RESPONSE_ACCEPT:
            try:
                self.image_remote_replace_cover(imagewidget, imagewidget.get_selected_items()[0], artist, album, stream)
                # Force a resize of the info labels, if needed:
                gobject.idle_add(self.on_notebook_resize, self.notebook, None)
            except:
                dialog.destroy()
                pass
        else:
            dialog.destroy()
        ui.change_cursor(None)
        self.chooseimage_visible = False

    def image_remote_replace_cover(self, iconview, path, artist, album, stream):
        self.artwork.stop_art_update = True
        image_num = int(path[0])
        if len(self.remotefilelist) > 0:
            filename = self.remotefilelist[image_num]
            if os.path.exists(filename):
                shutil.move(filename, self.remote_dest_filename)
                # And finally, set the image in the interface:
                self.artwork.artwork_update(True)
                # Clean up..
                misc.remove_dir(os.path.dirname(filename))
        self.chooseimage_visible = False
        self.choose_dialog.destroy()
        while self.artwork.downloading_image:
            gtk.main_iteration()

    def fullscreen_cover_art(self, widget):
        if self.fullscreencoverart.get_property('visible'):
            self.fullscreencoverart.hide()
        else:
            self.traytips.hide()
            self.fullscreencoverart.show_all()

    def fullscreen_cover_art_close(self, widget, event, key_press):
        if key_press:
            shortcut = gtk.accelerator_name(event.keyval, event.state)
            shortcut = shortcut.replace("<Mod2>", "")
            if shortcut != 'Escape':
                return
        self.fullscreencoverart.hide()

    def header_save_column_widths(self):
        if not self.withdrawn and self.expanded:
            windowwidth = self.window.allocation.width
            if windowwidth <= 10 or self.columns[0] <= 10:
                # Make sure we only set self.columnwidths if self.current
                # has its normal allocated width:
                return
            notebookwidth = self.notebook.allocation.width
            treewidth = 0
            for i, column in enumerate(self.columns):
                colwidth = column.get_width()
                treewidth += colwidth
                if i == len(self.columns)-1 and treewidth <= windowwidth:
                    self.columnwidths[i] = min(colwidth, column.get_fixed_width())
                else:
                    self.columnwidths[i] = colwidth
            if treewidth > notebookwidth:
                self.expanderwindow.set_policy(gtk.POLICY_AUTOMATIC, gtk.POLICY_AUTOMATIC)
            else:
                self.expanderwindow.set_policy(gtk.POLICY_NEVER, gtk.POLICY_AUTOMATIC)
        self.resizing_columns = False

    def systemtray_menu(self, status_icon, button, activate_time):
        self.traymenu.popup(None, None, None, button, activate_time)

    def systemtray_activate(self, status_icon):
        # Clicking on a gtk.StatusIcon:
        if not self.ignore_toggle_signal:
            # This prevents the user clicking twice in a row quickly
            # and having the second click not revert to the intial
            # state
            self.ignore_toggle_signal = True
            prev_state = self.UIManager.get_widget('/traymenu/showmenu').get_active()
            self.UIManager.get_widget('/traymenu/showmenu').set_active(not prev_state)
            if not self.window.window:
                # For some reason, self.window.window is not defined if mpd is not running
                # and sonata is started with self.withdrawn = True
                self.withdraw_app_undo()
            elif not (self.window.window.get_state() & gtk.gdk.WINDOW_STATE_WITHDRAWN) and self.window.is_active():
                # Window is not withdrawn and is active (has toplevel focus):
                self.withdraw_app()
            else:
                self.withdraw_app_undo()
            # This prevents the tooltip from popping up again until the user
            # leaves and enters the trayicon again
            #if self.traytips.notif_handler == None and self.traytips.notif_handler != -1:
                #self.traytips._remove_timer()
            gobject.timeout_add(100, self.tooltip_set_ignore_toggle_signal_false)

    def tooltip_show_manually(self):
        # Since there is no signal to connect to when the user puts their
        # mouse over the trayicon, we will check the mouse position
        # manually and show/hide the window as appropriate. This is called
        # every iteration. Note: This should not occur if self.traytips.notif_
        # handler has a value, because that means that the tooltip is already
        # visible, and we don't want to override that setting simply because
        # the user's cursor is not over the tooltip.
        if self.traymenu.get_property('visible') and self.traytips.notif_handler != -1:
            self.traytips._remove_timer()
        elif not self.traytips.notif_handler:
            pointer_screen, px, py, _ = self.window.get_screen().get_display().get_pointer()
            icon_screen, icon_rect, icon_orient = self.statusicon.get_geometry()
            x = icon_rect[0]
            y = icon_rect[1]
            width = icon_rect[2]
            height = icon_rect[3]
            if px >= x and px <= x+width and py >= y and py <= y+height:
                self.traytips._start_delay(self.statusicon)
            else:
                self.traytips._remove_timer()

    def systemtray_click(self, widget, event):
        # Clicking on an egg system tray icon:
        if event.button == 1 and not self.ignore_toggle_signal: # Left button shows/hides window(s)
            self.systemtray_activate(None)
        elif event.button == 2: # Middle button will play/pause
            if self.conn:
                self.mpd_pp(self.trayeventbox)
        elif event.button == 3: # Right button pops up menu
            self.traymenu.popup(None, None, None, event.button, event.time)
        return False

    def on_traytips_press(self, widget, event):
        if self.traytips.get_property('visible'):
            self.traytips._remove_timer()

    def withdraw_app_undo(self):
        self.window.move(self.x, self.y)
        if not self.expanded:
            self.notebook.set_no_show_all(True)
            self.statusbar.set_no_show_all(True)
        self.window.show_all()
        self.notebook.set_no_show_all(False)
        self.withdrawn = False
        self.UIManager.get_widget('/traymenu/showmenu').set_active(True)
        gobject.idle_add(self.withdraw_app_undo_present_and_focus)

    def withdraw_app_undo_present_and_focus(self):
        self.window.present() # Helps to raise the window (useful against focus stealing prevention)
        self.window.grab_focus()
        if self.sticky:
            self.window.stick()
        if self.ontop:
            self.window.set_keep_above(True)

    def withdraw_app(self):
        if HAVE_EGG or HAVE_STATUS_ICON:
            # Save the playlist column widths before withdrawing the app.
            # Otherwise we will not be able to correctly save the column
            # widths if the user quits sonata while it is withdrawn.
            self.header_save_column_widths()
            self.window.hide()
            self.withdrawn = True
            self.UIManager.get_widget('/traymenu/showmenu').set_active(False)

    def on_withdraw_app_toggle(self, action):
        if self.ignore_toggle_signal:
            return
        self.ignore_toggle_signal = True
        if self.UIManager.get_widget('/traymenu/showmenu').get_active():
            self.withdraw_app_undo()
        else:
            self.withdraw_app()
        gobject.timeout_add(500, self.tooltip_set_ignore_toggle_signal_false)

    def tooltip_set_ignore_toggle_signal_false(self):
        self.ignore_toggle_signal = False

    # Change volume on mousewheel over systray icon:
    def systemtray_scroll(self, widget, event):
        self.on_volumebutton_scroll(widget, event)

    def systemtray_size(self, widget, allocation):
        if widget.allocation.height <= 5:
            # For vertical panels, height can be 1px, so use width
            size = widget.allocation.width
        else:
            size = widget.allocation.height
        if not self.eggtrayheight or self.eggtrayheight != size:
            self.eggtrayheight = size
            if size > 5 and self.eggtrayfile:
                self.trayimage.set_from_pixbuf(img.get_pixbuf_of_size(gtk.gdk.pixbuf_new_from_file(self.eggtrayfile), self.eggtrayheight)[0])

    def on_current_click(self, treeview, path, column):
        model = self.current.get_model()
        if self.filterbox_visible:
            self.searchfilter_on_enter(None)
            return
        try:
            iter = model.get_iter(path)
            mpdh.call(self.client, 'playid', self.current_get_songid(iter, model))
        except:
            pass
        self.sel_rows = False
        self.iterate_now()

    def switch_to_tab_name(self, tab_name):
        self.notebook.set_current_page(self.notebook_get_tab_num(self.notebook, tab_name))

    def switch_to_tab_num(self, tab_num):
        vis_tabnum = self.notebook_get_visible_tab_num(self.notebook, tab_num)
        if vis_tabnum != -1:
            self.notebook.set_current_page(vis_tabnum)

    def on_switch_to_tab1(self, action):
        self.switch_to_tab_num(0)

    def on_switch_to_tab2(self, action):
        self.switch_to_tab_num(1)

    def on_switch_to_tab3(self, action):
        self.switch_to_tab_num(2)

    def on_switch_to_tab4(self, action):
        self.switch_to_tab_num(3)

    def on_switch_to_tab5(self, action):
        self.switch_to_tab_num(4)

    def switch_to_next_tab(self, action):
        self.notebook.next_page()

    def switch_to_prev_tab(self, action):
        self.notebook.prev_page()

    def on_volume_lower(self, action):
        new_volume = int(self.volumescale.get_adjustment().get_value()) - 5
        if new_volume < 0:
            new_volume = 0
        self.volumescale.get_adjustment().set_value(new_volume)
        self.on_volumescale_change(self.volumescale, 0, 0)

    def on_volume_raise(self, action):
        new_volume = int(self.volumescale.get_adjustment().get_value()) + 5
        if new_volume > 100:
            new_volume = 100
        self.volumescale.get_adjustment().set_value(new_volume)
        self.on_volumescale_change(self.volumescale, 0, 0)

    # Volume control
    def on_volumebutton_clicked(self, widget):
        if not self.volumewindow.get_property('visible'):
            x_win, y_win = self.volumebutton.window.get_origin()
            button_rect = self.volumebutton.get_allocation()
            x_coord, y_coord = button_rect.x + x_win, button_rect.y+y_win
            width, height = button_rect.width, button_rect.height
            self.volumewindow.set_size_request(width, -1)
            self.volumewindow.move(x_coord, y_coord+height)
            self.volumewindow.present()
        else:
            self.volume_hide()
        return

    def on_volumebutton_scroll(self, widget, event):
        if self.conn:
            if event.direction == gtk.gdk.SCROLL_UP:
                self.on_volume_raise(None)
            elif event.direction == gtk.gdk.SCROLL_DOWN:
                self.on_volume_lower(None)
        return

    def on_volumescale_scroll(self, widget, event):
        if event.direction == gtk.gdk.SCROLL_UP:
            new_volume = int(self.volumescale.get_adjustment().get_value()) + 5
            if new_volume > 100:
                new_volume = 100
            self.volumescale.get_adjustment().set_value(new_volume)
        elif event.direction == gtk.gdk.SCROLL_DOWN:
            new_volume = int(self.volumescale.get_adjustment().get_value()) - 5
            if new_volume < 0:
                new_volume = 0
            self.volumescale.get_adjustment().set_value(new_volume)
        return

    def on_volumescale_change(self, obj, value, data):
        new_volume = int(obj.get_adjustment().get_value())
        mpdh.call(self.client, 'setvol', new_volume)
        self.iterate_now()
        return

    def volume_hide(self):
        self.volumebutton.set_active(False)
        if self.volumewindow.get_property('visible'):
            self.volumewindow.hide()

    def mpd_pp(self, widget, key=None):
        if self.conn and self.status:
            if self.status['state'] in ('stop', 'pause'):
                mpdh.call(self.client, 'play')
            elif self.status['state'] == 'play':
                mpdh.call(self.client, 'pause', '1')
            self.iterate_now()
        return

    def mpd_stop(self, widget, key=None):
        if self.conn:
            mpdh.call(self.client, 'stop')
            self.iterate_now()
        return

    def mpd_prev(self, widget, key=None):
        if self.conn:
            mpdh.call(self.client, 'previous')
            self.iterate_now()
        return

    def mpd_next(self, widget, key=None):
        if self.conn:
            mpdh.call(self.client, 'next')
            self.iterate_now()
        return

    def mpd_update(self, path='/'):
        if self.conn:
            mpdh.call(self.client, 'update', path)

    def on_remove(self, widget):
        if self.conn:
            model = None
            while gtk.events_pending():
                gtk.main_iteration()
            if self.current_tab == self.TAB_CURRENT:
                # we are manipulating the model manually for speed, so...
                self.current_update_skip = True
                treeviewsel = self.current_selection
                model, selected = treeviewsel.get_selected_rows()
                if len(selected) == len(self.currentdata) and not self.filterbox_visible:
                    # Everything is selected, clear:
                    mpdh.call(self.client, 'clear')
                elif len(selected) > 0:
                    selected.reverse()
                    if not self.filterbox_visible:
                        # If we remove an item from the filtered results, this
                        # causes a visual refresh in the interface.
                        self.current.set_model(None)
                    mpdh.call(self.client, 'command_list_ok_begin')
                    for path in selected:
                        if not self.filterbox_visible:
                            rownum = path[0]
                        else:
                            rownum = self.filter_row_mapping[path[0]]
                        iter = self.currentdata.get_iter((rownum, 0))
                        mpdh.call(self.client, 'deleteid', self.current_get_songid(iter, self.currentdata))
                        # Prevents the entire playlist from refreshing:
                        self.current_songs.pop(rownum)
                        self.currentdata.remove(iter)
                    mpdh.call(self.client, 'command_list_end')
                    if not self.filterbox_visible:
                        self.current.set_model(model)
            elif self.current_tab == self.TAB_PLAYLISTS:
                treeviewsel = self.playlists_selection
                model, selected = treeviewsel.get_selected_rows()
                if ui.show_msg(self.window, gettext.ngettext("Delete the selected playlist?", "Delete the selected playlists?", int(len(selected))), gettext.ngettext("Delete Playlist", "Delete Playlists", int(len(selected))), 'deletePlaylist', gtk.BUTTONS_YES_NO) == gtk.RESPONSE_YES:
                    iters = [model.get_iter(path) for path in selected]
                    for iter in iters:
                        mpdh.call(self.client, 'rm', misc.unescape_html(self.playlistsdata.get_value(iter, 1)))
                    self.playlists_populate()
            elif self.current_tab == self.TAB_STREAMS:
                treeviewsel = self.streams_selection
                model, selected = treeviewsel.get_selected_rows()
                if ui.show_msg(self.window, gettext.ngettext("Delete the selected stream?", "Delete the selected streams?", int(len(selected))), gettext.ngettext("Delete Stream", "Delete Streams", int(len(selected))), 'deleteStreams', gtk.BUTTONS_YES_NO) == gtk.RESPONSE_YES:
                    iters = [model.get_iter(path) for path in selected]
                    for iter in iters:
                        stream_removed = False
                        for i in range(len(self.stream_names)):
                            if not stream_removed:
                                if self.streamsdata.get_value(iter, 1) == misc.escape_html(self.stream_names[i]):
                                    self.stream_names.pop(i)
                                    self.stream_uris.pop(i)
                                    stream_removed = True
                    self.streams_populate()
            self.iterate_now()
            # Attempt to retain selection in the vicinity..
            if model and len(model) > 0:
                try:
                    # Use top row in selection...
                    selrow = 999999
                    for row in selected:
                        if row[0] < selrow:
                            selrow = row[0]
                    if selrow >= len(model):
                        selrow = len(model)-1
                    treeviewsel.select_path(selrow)
                except:
                    pass

    def mpd_clear(self, widget):
        if self.conn:
            mpdh.call(self.client, 'clear')
            self.iterate_now()

    def on_repeat_clicked(self, widget):
        if self.conn:
            if widget.get_active():
                mpdh.call(self.client, 'repeat', 1)
            else:
                mpdh.call(self.client, 'repeat', 0)

    def on_random_clicked(self, widget):
        if self.conn:
            if widget.get_active():
                mpdh.call(self.client, 'random', 1)
            else:
                mpdh.call(self.client, 'random', 0)

    def on_prefs(self, widget):
        trayicon_available = HAVE_EGG or HAVE_STATUS_ICON
        trayicon_in_use = ((HAVE_STATUS_ICON and self.statusicon.is_embedded() and
                    self.statusicon.get_visible())
                   or (HAVE_EGG and self.trayicon.get_property('visible')))
        self.preferences.on_prefs_real(self.window, self.popuptimes, audioscrobbler is not None, self.scrobbler_import, self.scrobbler_init, self.scrobbler_auth_changed, trayicon_available, trayicon_in_use, self.on_connectkey_pressed, self.on_currsong_notify, self.update_infofile, self.prefs_notif_toggled, self.prefs_stylized_toggled, self.prefs_art_toggled, self.prefs_playback_toggled, self.prefs_progress_toggled, self.prefs_statusbar_toggled, self.prefs_lyrics_toggled, self.prefs_trayicon_toggled, self.prefs_window_response)

    def scrobbler_init(self):
        if audioscrobbler is not None and self.as_enabled and len(self.as_username) > 0 and len(self.as_password_md5) > 0:
            thread = threading.Thread(target=self.scrobbler_init_thread)
            thread.setDaemon(True)
            thread.start()

    def scrobbler_init_thread(self):
        if self.scrob is None:
            self.scrob = audioscrobbler.AudioScrobbler()
        if self.scrob_post is None:
            self.scrob_post = self.scrob.post(self.as_username, self.as_password_md5, verbose=True)
        else:
            if self.scrob_post.authenticated:
                return # We are authenticated
            else:
                self.scrob_post = self.scrob.post(self.as_username, self.as_password_md5, verbose=True)
        try:
            self.scrob_post.auth()
        except Exception, e:
            print "Error authenticating audioscrobbler", e
            self.scrob_post = None
        if self.scrob_post:
            self.scrobbler_retrieve_cache()

    def scrobbler_import(self, show_error=False):
        # We need to try to import audioscrobbler either when the app starts (if
        # as_enabled=True) or if the user enables it in prefs.
        global audioscrobbler
        if audioscrobbler is None:
            import audioscrobbler

    def scrobbler_auth_changed(self):
        if self.scrob_post:
            if self.scrob_post.authenticated:
                self.scrob_post = None

    # XXX move the prefs handling parts of prefs_* to preferences.py
    def prefs_window_response(self, window, response, prefsnotebook, exit_stop, win_ontop, display_art_combo, win_sticky, direntry, minimize, update_start, autoconnect, currentoptions, libraryoptions, titleoptions, currsongoptions1, currsongoptions2, crossfadecheck, crossfadespin, infopath_options, hostentry, portentry, passwordentry, using_mpd_env_vars, prev_host, prev_port, prev_password):
        if response == gtk.RESPONSE_CLOSE:
            self.stop_on_exit = exit_stop.get_active()
            self.ontop = win_ontop.get_active()
            self.covers_pref = display_art_combo.get_active()
            self.sticky = win_sticky.get_active()
            if self.show_lyrics and self.lyrics_location != self.LYRICS_LOCATION_HOME:
                if not os.path.isdir(misc.file_from_utf8(self.musicdir[self.profile_num])):
                    ui.show_msg(self.window, _("To save lyrics to the music file's directory, you must specify a valid music directory."), _("Music Dir Verification"), 'musicdirVerificationError', gtk.BUTTONS_CLOSE)
                    # Set music_dir entry focused:
                    prefsnotebook.set_current_page(0)
                    direntry.grab_focus()
                    return
            if self.show_covers and self.art_location != self.ART_LOCATION_HOMECOVERS:
                if not os.path.isdir(misc.file_from_utf8(self.musicdir[self.profile_num])):
                    ui.show_msg(self.window, _("To save artwork to the music file's directory, you must specify a valid music directory."), _("Music Dir Verification"), 'musicdirVerificationError', gtk.BUTTONS_CLOSE)
                    # Set music_dir entry focused:
                    prefsnotebook.set_current_page(0)
                    direntry.grab_focus()
                    return
            self.minimize_to_systray = minimize.get_active()
            self.update_on_start = update_start.get_active()
            self.autoconnect = autoconnect.get_active()
            if self.currentformat != currentoptions.get_text():
                self.currentformat = currentoptions.get_text()
                for column in self.current.get_columns():
                    self.current.remove_column(column)
                self.current_initialize_columns()
                self.current_update_format()
            if self.libraryformat != libraryoptions.get_text():
                self.libraryformat = libraryoptions.get_text()
                self.library_browse(root=self.wd)
            if self.titleformat != titleoptions.get_text():
                self.titleformat = titleoptions.get_text()
                self.update_wintitle()
            if (self.currsongformat1 != currsongoptions1.get_text()) or (self.currsongformat2 != currsongoptions2.get_text()):
                self.currsongformat1 = currsongoptions1.get_text()
                self.currsongformat2 = currsongoptions2.get_text()
                self.update_cursong()
            if self.window_owner:
                if self.ontop:
                    self.window.set_keep_above(True)
                else:
                    self.window.set_keep_above(False)
                if self.sticky:
                    self.window.stick()
                else:
                    self.window.unstick()
            self.xfade = crossfadespin.get_value_as_int()
            if crossfadecheck.get_active():
                self.xfade_enabled = True
                if self.conn:
                    mpdh.call(self.client, 'crossfade', self.xfade)
            else:
                self.xfade_enabled = False
                if self.conn:
                    mpdh.call(self.client, 'crossfade', 0)
            if self.infofile_path != infopath_options.get_text():
                self.infofile_path = os.path.expanduser(infopath_options.get_text())
                if self.use_infofile: self.update_infofile()
            if not using_mpd_env_vars:
                if prev_host != self.host[self.profile_num] or prev_port != self.port[self.profile_num] or prev_password != self.password[self.profile_num]:
                    # Try to connect if mpd connection info has been updated:
                    ui.change_cursor(gtk.gdk.Cursor(gtk.gdk.WATCH))
                    self.mpd_connect(force=True)
            if self.as_enabled:
                gobject.idle_add(self.scrobbler_init)
            self.settings_save()
            self.populate_profiles_for_menu()
            ui.change_cursor(None)
        window.destroy()

    def prefs_playback_toggled(self, button):
        if button.get_active():
            self.show_playback = True
            for widget in [self.prevbutton, self.ppbutton, self.stopbutton, self.nextbutton, self.volumebutton]:
                ui.show(widget)
        else:
            self.show_playback = False
            for widget in [self.prevbutton, self.ppbutton, self.stopbutton, self.nextbutton, self.volumebutton]:
                ui.hide(widget)

    def prefs_progress_toggled(self, button):
        if button.get_active():
            self.show_progress = True
            for widget in [self.progressbox, self.trayprogressbar]:
                ui.show(widget)
        else:
            self.show_progress = False
            for widget in [self.progressbox, self.trayprogressbar]:
                ui.hide(widget)

    def prefs_art_toggled(self, button, art_hbox1, art_hbox2, art_stylized):
        button_active = button.get_active()
        art_hbox1.set_sensitive(button_active)
        art_hbox2.set_sensitive(button_active)
        art_stylized.set_sensitive(button_active)
        if button_active:
            self.traytips.set_size_request(self.notification_width, -1)
            self.artwork.artwork_set_default_icon()
            for widget in [self.imageeventbox, self.info_imagebox, self.trayalbumeventbox, self.trayalbumimage2]:
                widget.set_no_show_all(False)
                if widget in [self.trayalbumeventbox, self.trayalbumimage2]:
                    if self.conn and self.status and self.status['state'] in ['play', 'pause']:
                        widget.show_all()
                else:
                    widget.show_all()
            self.show_covers = True
            self.update_cursong()
            self.artwork.artwork_update()
        else:
            self.traytips.set_size_request(self.notification_width-100, -1)
            for widget in [self.imageeventbox, self.info_imagebox, self.trayalbumeventbox, self.trayalbumimage2]:
                ui.hide(widget)
            self.show_covers = False
            self.update_cursong()

        # Force a resize of the info labels, if needed:
        gobject.idle_add(self.on_notebook_resize, self.notebook, None)

    def prefs_stylized_toggled(self, button):
        self.covers_type = button.get_active()
        self.artwork.artwork_update(True)

    def prefs_lyrics_toggled(self, button, lyrics_hbox):
        if button.get_active():
            lyrics_hbox.set_sensitive(True)
            self.show_lyrics = True
            ui.show(self.info_lyrics)
            self.info_update(True)
        else:
            lyrics_hbox.set_sensitive(False)
            self.show_lyrics = False
            ui.hide(self.info_lyrics)

    def prefs_statusbar_toggled(self, button):
        if button.get_active():
            self.statusbar.set_no_show_all(False)
            if self.expanded:
                self.statusbar.show_all()
            self.show_statusbar = True
            self.update_statusbar()
        else:
            ui.hide(self.statusbar)
            self.show_statusbar = False
            self.update_statusbar()

    def prefs_notif_toggled(self, button, notifhbox):
        if button.get_active():
            notifhbox.set_sensitive(True)
            self.show_notification = True
            self.on_currsong_notify()
        else:
            notifhbox.set_sensitive(False)
            self.show_notification = False
            try:
                gobject.source_remove(self.traytips.notif_handler)
            except:
                pass
            self.traytips.hide()

    def prefs_trayicon_toggled(self, button, minimize):
        # Note that we update the sensitivity of the minimize
        # CheckButton to reflect if the trayicon is visible.
        if button.get_active():
            self.show_trayicon = True
            if HAVE_STATUS_ICON:
                self.statusicon.set_visible(True)
                if self.statusicon.is_embedded() and self.statusicon.get_visible():
                    minimize.set_sensitive(True)
            elif HAVE_EGG:
                self.trayicon.show_all()
                if self.trayicon.get_property('visible'):
                    minimize.set_sensitive(True)
        else:
            self.show_trayicon = False
            minimize.set_sensitive(False)
            if HAVE_STATUS_ICON:
                self.statusicon.set_visible(False)
            elif HAVE_EGG:
                self.trayicon.hide_all()

    def seek(self, song, seektime):
        mpdh.call(self.client, 'seek', song, seektime)
        self.iterate_now()
        return

    def on_link_enter(self, widget, event):
        if widget.get_children()[0].get_use_markup():
            ui.change_cursor(gtk.gdk.Cursor(gtk.gdk.HAND2))

    def on_link_leave(self, widget, event):
        ui.change_cursor(None)

    def on_link_click(self, widget, event, type):
        if type == 'artist':
            misc.browser_load("http://www.wikipedia.org/wiki/Special:Search/" + urllib.quote(mpdh.get(self.songinfo, 'artist')), self.url_browser, self.window)
        elif type == 'album':
            misc.browser_load("http://www.wikipedia.org/wiki/Special:Search/" + urllib.quote(mpdh.get(self.songinfo, 'album')), self.url_browser, self.window)
        elif type == 'more':
            previous_is_more = (self.info_morelabel.get_text() == "(" + _("more") + ")")
            if previous_is_more:
                self.info_morelabel.set_markup(misc.link_markup(_("hide"), True, True, self.linkcolor))
                self.info_song_more = True
            else:
                self.info_morelabel.set_markup(misc.link_markup(_("more"), True, True, self.linkcolor))
                self.info_song_more = False
            if self.info_song_more:
                for hbox in self.info_boxes_in_more:
                    ui.show(hbox)
            else:
                for hbox in self.info_boxes_in_more:
                    ui.hide(hbox)
        elif type == 'edit':
            if self.songinfo:
                self.on_tags_edit(widget)
        elif type == 'search':
            self.on_lyrics_search(None)
        elif type == 'editlyrics':
            misc.browser_load("http://lyricwiki.org/index.php?title=" + urllib.quote(misc.capwords(mpdh.get(self.songinfo, 'artist'))) + ":" + urllib.quote(misc.capwords(mpdh.get(self.songinfo, 'title'))) + "&action=edit", self.url_browser, self.window)

    def on_tab_click(self, widget, event):
        if event.button == 3:
            self.notebookmenu.popup(None, None, None, 1, 0)
            return True

    def on_notebook_click(self, widget, event):
        if event.button == 1:
            self.volume_hide()

    def notebook_get_tab_num(self, notebook, tabname):
        for tab in range(notebook.get_n_pages()):
            if self.notebook_get_tab_text(self.notebook, tab) == tabname:
                return tab

    def notebook_tab_is_visible(self, notebook, tabname):
        tab = self.notebook.get_children()[self.notebook_get_tab_num(notebook, tabname)]
        if tab.get_property('visible'):
            return True
        else:
            return False

    def notebook_get_visible_tab_num(self, notebook, tab_num):
        # Get actual tab number for visible tab_num. If there is not
        # a visible tab for tab_num, return -1.\
        curr_tab = -1
        for tab in range(notebook.get_n_pages()):
            if notebook.get_children()[tab].get_property('visible'):
                curr_tab += 1
                if curr_tab == tab_num:
                    return tab
        return -1

    def notebook_get_tab_text(self, notebook, tab_num):
        tab = notebook.get_children()[tab_num]
        return notebook.get_tab_label(tab).get_child().get_children()[1].get_text()

    def on_notebook_page_change(self, notebook, page, page_num):
        self.current_tab = self.notebook_get_tab_text(self.notebook, page_num)
        if self.current_tab == self.TAB_CURRENT:
            gobject.idle_add(ui.focus, self.current)
        elif self.current_tab == self.TAB_LIBRARY:
            gobject.idle_add(ui.focus, self.library)
        elif self.current_tab == self.TAB_PLAYLISTS:
            gobject.idle_add(ui.focus, self.playlists)
        elif self.current_tab == self.TAB_STREAMS:
            gobject.idle_add(ui.focus, self.streams)
        elif self.current_tab == self.TAB_INFO:
            gobject.idle_add(ui.focus, self.info)
            # This prevents the artwork from being cutoff when the
            # user first clicks on the Info tab. Why this happens
            # and how this fixes it is beyond me.
            gobject.idle_add(self.info_update, True, False, True)
        gobject.idle_add(self.update_menu_visibility)
        if not self.img_clicked:
            self.last_tab = self.current_tab

    def on_library_search_text_click(self, widget, event):
        if event.button == 1:
            self.volume_hide()

    def on_window_click(self, widget, event):
        if event.button == 1:
            self.volume_hide()
        elif event.button == 3:
            self.menu_popup(self.window, event)

    def menu_popup(self, widget, event):
        if widget == self.window:
            if event.get_coords()[1] > self.notebook.get_allocation()[1]:
                return
        if event.button == 3:
            self.update_menu_visibility(True)
            gobject.idle_add(self.mainmenu.popup, None, None, None, event.button, event.time)

    def on_tab_toggle(self, toggleAction):
        name = toggleAction.get_name()
        if not toggleAction.get_active():
            # Make sure we aren't hiding the last visible tab:
            num_tabs_vis = 0
            for tab in self.notebook.get_children():
                if tab.get_property('visible'):
                    num_tabs_vis += 1
            if num_tabs_vis == 1:
                # Keep menu item checking and exit..
                toggleAction.set_active(True)
                return
        # Store value:
        if name == self.TAB_CURRENT:
            self.current_tab_visible = toggleAction.get_active()
        elif name == self.TAB_LIBRARY:
            self.library_tab_visible = toggleAction.get_active()
        elif name == self.TAB_PLAYLISTS:
            self.playlists_tab_visible = toggleAction.get_active()
        elif name == self.TAB_STREAMS:
            self.streams_tab_visible = toggleAction.get_active()
        elif name == self.TAB_INFO:
            self.info_tab_visible = toggleAction.get_active()
        # Hide/show:
        tabnum = self.notebook_get_tab_num(self.notebook, name)
        if toggleAction.get_active():
            ui.show(self.notebook.get_children()[tabnum])
        else:
            ui.hide(self.notebook.get_children()[tabnum])

    def on_library_search_shortcut(self, event):
        # Ensure library tab is visible
        if not self.notebook_tab_is_visible(self.notebook, self.TAB_LIBRARY):
            return
        if self.current_tab != self.TAB_LIBRARY:
            self.switch_to_tab_name(self.TAB_LIBRARY)
        if self.library_search_visible():
            self.on_library_search_end(None)
        gobject.idle_add(self.searchtext.grab_focus)

    def on_library_search_combo_change(self, combo):
        self.last_search_num = combo.get_active()
        self.prevlibtodo = ""
        self.libsearchfilter_feed_loop(self.searchtext)

    def on_library_search_end(self, button, move_focus=True):
        if self.library_search_visible():
            self.libsearchfilter_toggle(move_focus)

    def library_search_visible(self):
        return self.searchbutton.get_property('visible')

    def update_menu_visibility(self, show_songinfo_only=False):
        if show_songinfo_only or not self.expanded:
            for menu in ['add', 'replace', 'playafter', 'rename', 'rm', 'pl', \
                        'remove', 'clear', 'update', 'new', 'edit', 'sort', 'tag']:
                self.UIManager.get_widget('/mainmenu/' + menu + 'menu/').hide()
            return
        elif self.current_tab == self.TAB_CURRENT:
            if len(self.currentdata) > 0:
                if self.current_selection.count_selected_rows() > 0:
                    for menu in ['remove', 'tag']:
                        self.UIManager.get_widget('/mainmenu/' + menu + 'menu/').show()
                else:
                    for menu in ['remove', 'tag']:
                        self.UIManager.get_widget('/mainmenu/' + menu + 'menu/').hide()
                if not self.filterbox_visible:
                    for menu in ['clear', 'pl', 'sort']:
                        self.UIManager.get_widget('/mainmenu/' + menu + 'menu/').show()
                else:
                    for menu in ['clear', 'pl', 'sort']:
                        self.UIManager.get_widget('/mainmenu/' + menu + 'menu/').hide()
            else:
                for menu in ['clear', 'pl', 'sort', 'remove', 'tag']:
                    self.UIManager.get_widget('/mainmenu/' + menu + 'menu/').hide()
            for menu in ['add', 'replace', 'playafter', 'rename', 'rm', \
                         'update', 'new', 'edit']:
                self.UIManager.get_widget('/mainmenu/' + menu + 'menu/').hide()
        elif self.current_tab == self.TAB_LIBRARY:
            if self.conn:
                self.UIManager.get_widget('/mainmenu/updatemenu/').show()
            else:
                self.UIManager.get_widget('/mainmenu/updatemenu/').hide()
            if len(self.librarydata) > 0:
                if self.library_selection.count_selected_rows() > 0:
                    for menu in ['add', 'replace', 'playafter', 'tag']:
                        self.UIManager.get_widget('/mainmenu/' + menu + 'menu/').show()
                else:
                    for menu in ['add', 'replace', 'playafter', 'tag']:
                        self.UIManager.get_widget('/mainmenu/' + menu + 'menu/').hide()
            else:
                for menu in ['add', 'replace', 'playafter', 'tag']:
                    self.UIManager.get_widget('/mainmenu/' + menu + 'menu/').hide()
            for menu in ['remove', 'clear', 'pl', 'rename', 'rm', 'new', 'edit', 'sort']:
                self.UIManager.get_widget('/mainmenu/' + menu + 'menu/').hide()
        elif self.current_tab == self.TAB_PLAYLISTS:
            if self.playlists_selection.count_selected_rows() > 0:
                for menu in ['add', 'replace', 'playafter', 'rm']:
                    self.UIManager.get_widget('/mainmenu/' + menu + 'menu/').show()
                if self.playlists_selection.count_selected_rows() == 1 and self.mpd_major_version() >= 0.13:
                    self.UIManager.get_widget('/mainmenu/renamemenu/').show()
                else:
                    self.UIManager.get_widget('/mainmenu/renamemenu/').hide()
            else:
                for menu in ['add', 'replace', 'playafter', 'rm', 'rename']:
                    self.UIManager.get_widget('/mainmenu/' + menu + 'menu/').hide()
            for menu in ['remove', 'clear', 'pl', 'update', 'new', 'edit', 'sort', 'tag']:
                self.UIManager.get_widget('/mainmenu/' + menu + 'menu/').hide()
        elif self.current_tab == self.TAB_STREAMS:
            self.UIManager.get_widget('/mainmenu/newmenu/').show()
            if self.streams_selection.count_selected_rows() > 0:
                if self.streams_selection.count_selected_rows() == 1:
                    self.UIManager.get_widget('/mainmenu/editmenu/').show()
                else:
                    self.UIManager.get_widget('/mainmenu/editmenu/').hide()
                for menu in ['add', 'replace', 'playafter', 'rm']:
                    self.UIManager.get_widget('/mainmenu/' + menu + 'menu/').show()
            else:
                for menu in ['add', 'replace', 'playafter', 'rm']:
                    self.UIManager.get_widget('/mainmenu/' + menu + 'menu/').hide()
            for menu in ['rename', 'remove', 'clear', 'pl', 'update', 'sort', 'tag']:
                self.UIManager.get_widget('/mainmenu/' + menu + 'menu/').hide()

    def mpd_major_version(self):
        try:
            if self.conn:
                version = getattr(self.client, "mpd_version", 0.0)
                parts = version.split(".")
                return float(parts[0] + "." + parts[1])
            else:
                return 0
        except:
            return 0

    def find_path(self, filename):
        full_filename = None
        if HAVE_SUGAR:
            full_filename = os.path.join(activity.get_bundle_path(), 'share', filename)
        else:
            if os.path.exists(os.path.join(os.path.split(__file__)[0], filename)):
                full_filename = os.path.join(os.path.split(__file__)[0], filename)
            elif os.path.exists(os.path.join(os.path.split(__file__)[0], 'pixmaps', filename)):
                full_filename = os.path.join(os.path.split(__file__)[0], 'pixmaps', filename)
            elif os.path.exists(os.path.join(os.path.split(__file__)[0], 'share', filename)):
                full_filename = os.path.join(os.path.split(__file__)[0], 'share', filename)
            elif os.path.exists(os.path.join(__file__.split('/lib')[0], 'share', 'pixmaps', filename)):
                full_filename = os.path.join(__file__.split('/lib')[0], 'share', 'pixmaps', filename)
            elif os.path.exists(os.path.join(sys.prefix, 'share', 'pixmaps', filename)):
                full_filename = os.path.join(sys.prefix, 'share', 'pixmaps', filename)
        if not full_filename:
            print filename + " cannot be found. Aborting..."
            sys.exit(1)
        return full_filename

    def on_tags_edit(self, widget):
        files = []
        temp_mpdpaths = []
        if self.current_tab == self.TAB_INFO:
            if self.status and self.status['state'] in ['play', 'pause']:
                # Use current file in songinfo:
                mpdpath = mpdh.get(self.songinfo, 'file')
                fullpath = self.musicdir[self.profile_num] + mpdpath
                files.append(fullpath)
                temp_mpdpaths.append(mpdpath)
        elif self.current_tab == self.TAB_LIBRARY:
            # Populates files array with selected library items:
            items = self.library_get_path_child_filenames(False)
            for item in items:
                files.append(self.musicdir[self.profile_num] + item)
                temp_mpdpaths.append(item)
        elif self.current_tab == self.TAB_CURRENT:
            # Populates files array with selected current playlist items:
            temp_mpdpaths = self.current_get_selected_filenames(False)
            files = self.current_get_selected_filenames(True)

        tageditor = tagedit.TagEditor(self.window, self.tags_mpd_update)
        tageditor.on_tags_edit(files, temp_mpdpaths, self.musicdir[self.profile_num])

    def tags_mpd_update(self, tags, tagnum):
        if tags:
            mpdh.call(self.client, 'command_list_ok_begin')
            for i in range(tagnum):
                mpdh.call(self.client, 'update', tags[i]['mpdpath'])
            mpdh.call(self.client, 'command_list_end')
            self.iterate_now()

    def on_about(self, action):
        self.about_load()

    def about_close(self, event, data=None):
        self.about_dialog.hide()
        return True

    def about_shortcuts(self, button):
        # define the shortcuts and their descriptions
        # these are all gettextable
        mainshortcuts = \
                [[ "F1", _("About Sonata") ],
                 [ "F5", _("Preferences") ],
                 [ "F11", _("Fullscreen Artwork Mode") ],
                 [ "Alt-[1-5]", _("Switch to [1st-5th] tab") ],
                 [ "Alt-C", _("Connect to MPD") ],
                 [ "Alt-D", _("Disconnect from MPD") ],
                 [ "Alt-R", _("Randomize current playlist") ],
                 [ "Alt-Down", _("Expand player") ],
                 [ "Alt-Left", _("Switch to previous tab") ],
                 [ "Alt-Right", _("Switch to next tab") ],
                 [ "Alt-Up", _("Collapse player") ],
                 [ "Ctrl-H", _("Search library") ],
                 [ "Ctrl-Q", _("Quit") ],
                 [ "Ctrl-U", _("Update entire library") ],
                 [ "Menu", _("Display popup menu") ],
                 [ "Escape", _("Minimize to system tray (if enabled)") ]]
        playbackshortcuts = \
                [[ "Ctrl-Left", _("Previous track") ],
                 [ "Ctrl-Right", _("Next track") ],
                 [ "Ctrl-P", _("Play/Pause") ],
                 [ "Ctrl-S", _("Stop") ],
                 [ "Ctrl-Minus", _("Lower the volume") ],
                 [ "Ctrl-Plus", _("Raise the volume") ]]
        currentshortcuts = \
                [[ "Enter/Space", _("Play selected song") ],
                 [ "Delete", _("Remove selected song(s)") ],
                 [ "Ctrl-I", _("Center currently playing song") ],
                 [ "Ctrl-T", _("Edit selected song's tags") ],
                 [ "Ctrl-Shift-S", _("Save to new playlist") ],
                 [ "Ctrl-Delete", _("Clear list") ],
                 [ "Alt-R", _("Randomize list") ]]
        libraryshortcuts = \
                [[ "Enter/Space", _("Add selected song(s) or enter directory") ],
                 [ "Backspace", _("Go to parent directory") ],
                 [ "Ctrl-D", _("Add selected item(s)") ],
                 [ "Ctrl-R", _("Replace with selected item(s)") ],
                 [ "Ctrl-T", _("Edit selected song's tags") ],
                 [ "Ctrl-Shift-D", _("Add selected item(s) and play") ],
                 [ "Ctrl-Shift-R", _("Replace with selected item(s) and play") ],
                 [ "Ctrl-Shift-U", _("Update library for selected item(s)") ]]
        playlistshortcuts = \
                [[ "Enter/Space", _("Add selected playlist(s)") ],
                 [ "Delete", _("Remove selected playlist(s)") ],
                 [ "Ctrl-D", _("Add selected playlist(s)") ],
                 [ "Ctrl-R", _("Replace with selected playlist(s)") ],
                 [ "Ctrl-Shift-D", _("Add selected playlist(s) and play") ],
                 [ "Ctrl-Shift-R", _("Replace with selected playlist(s) and play") ]]
        streamshortcuts = \
                [[ "Enter/Space", _("Add selected stream(s)") ],
                 [ "Delete", _("Remove selected stream(s)") ],
                 [ "Ctrl-D", _("Add selected stream(s)") ],
                 [ "Ctrl-R", _("Replace with selected stream(s)") ],
                 [ "Ctrl-Shift-D", _("Add selected stream(s) and play") ],
                 [ "Ctrl-Shift-R", _("Replace with selected stream(s) and play") ]]
        infoshortcuts = \
                [[ "Ctrl-T", _("Edit playing song's tags") ]]
        # define the main array- this adds headings to each section of
        # shortcuts that will be displayed
        shortcuts = [[ _("Main Shortcuts"), mainshortcuts ],
                [ _("Playback Shortcuts"), playbackshortcuts ],
                [ _("Current Shortcuts"), currentshortcuts ],
                [ _("Library Shortcuts"), libraryshortcuts ],
                [ _("Playlist Shortcuts"), playlistshortcuts ],
                [ _("Stream Shortcuts"), streamshortcuts ],
                [ _("Info Shortcuts"), infoshortcuts ]]
        dialog = ui.dialog(title=_("Shortcuts"), parent=self.about_dialog, flags=gtk.DIALOG_MODAL | gtk.DIALOG_DESTROY_WITH_PARENT, buttons=(gtk.STOCK_CLOSE, gtk.RESPONSE_CLOSE), role='shortcuts', default=gtk.RESPONSE_CLOSE, h=320)

        # each pair is a [ heading, shortcutlist ]
        vbox = gtk.VBox()
        for pair in shortcuts:
            titlelabel = ui.label(markup="<b>" + pair[0] + "</b>")
            vbox.pack_start(titlelabel, False, False, 2)

            # print the items of [ shortcut, desc ]
            for item in pair[1]:
                tmphbox = gtk.HBox()

                tmplabel = ui.label(markup="<b>" + item[0] + ":</b>", y=0)
                tmpdesc = ui.label(text=item[1], wrap=True, y=0)

                tmphbox.pack_start(tmplabel, False, False, 2)
                tmphbox.pack_start(tmpdesc, True, True, 2)

                vbox.pack_start(tmphbox, False, False, 2)
            vbox.pack_start(ui.label(text=" "), False, False, 2)
        scrollbox = ui.scrollwindow(policy_x=gtk.POLICY_NEVER, addvp=vbox)
        dialog.vbox.pack_start(scrollbox, True, True, 2)
        dialog.show_all()
        dialog.run()
        dialog.destroy()

    def about_load(self):
        self.about_dialog = gtk.AboutDialog()
        try:
            self.about_dialog.set_transient_for(self.window)
            self.about_dialog.set_modal(True)
        except:
            pass
        self.about_dialog.set_name('Sonata')
        self.about_dialog.set_role('about')
        self.about_dialog.set_version(__version__)
        commentlabel = _('An elegant music client for MPD.')
        self.about_dialog.set_comments(commentlabel)
        if self.conn:
            # Include MPD stats:
            stats = mpdh.call(self.client, 'stats')
            statslabel = stats['songs'] + ' ' + gettext.ngettext('song', 'songs', int(stats['songs'])) + '.\n'
            statslabel = statslabel + stats['albums'] + ' ' + gettext.ngettext('album', 'albums', int(stats['albums'])) + '.\n'
            statslabel = statslabel + stats['artists'] + ' ' + gettext.ngettext('artist', 'artists', int(stats['artists'])) + '.\n'
            try:
                hours_of_playtime = misc.convert_time(float(stats['db_playtime'])).split(':')[-3]
            except:
                hours_of_playtime = '0'
            if int(hours_of_playtime) >= 24:
                days_of_playtime = str(int(hours_of_playtime)/24)
                statslabel = statslabel + days_of_playtime + ' ' + gettext.ngettext('day of bliss', 'days of bliss', int(days_of_playtime)) + '.'
            else:
                statslabel = statslabel + hours_of_playtime + ' ' + gettext.ngettext('hour of bliss', 'hours of bliss', int(hours_of_playtime)) + '.'
            self.about_dialog.set_copyright(statslabel)
        self.about_dialog.set_license(__license__)
        self.about_dialog.set_authors(['Scott Horowitz <stonecrest@gmail.com>'])
        self.about_dialog.set_artists(['Adrian Chromenko <adrian@rest0re.org>\nhttp://rest0re.org/oss.php'])
        self.about_dialog.set_translator_credits('ar - Ahmad Farghal <ahmad.farghal@gmail.com>\nbe@latin - Ihar Hrachyshka <ihar.hrachyshka@gmail.com>\nca - Franc Rodriguez <franc.rodriguez@tecob.com>\ncs - Jakub Adler <jakubadler@gmail.com>\nda - Martin Dybdal <dybber@dybber.dk>\nde - Paul Johnson <thrillerator@googlemail.com>\nel_GR - Lazaros Koromilas <koromilaz@gmail.com>\nes - Xoan Sampaiño <xoansampainho@gmail.com>\net - Mihkel <turakas@gmail.com>\nfi - Ilkka Tuohelafr <hile@hack.fi>\nfr - Floreal M <florealm@gmail.com>\nit - Gianni Vialetto <forgottencrow@gmail.com>\nnl - Olivier Keun <litemotiv@gmail.com>\npl - Tomasz Dominikowski <dominikowski@gmail.com>\npt_BR - Alex Tercete Matos <alextercete@gmail.com>\nru - Ivan <bkb.box@bk.ru>\nsv - Daniel Nylander <po@danielnylander.se>\ntr - Gökmen Görgen <gkmngrgn@gmail.com>\nuk - Господарисько Тарас <dogmaton@gmail.com>\nzh_CN - Desmond Chang <dochang@gmail.com>\n')
        gtk.about_dialog_set_url_hook(self.show_website, "http://sonata.berlios.de/")
        self.about_dialog.set_website_label("http://sonata.berlios.de/")
        large_icon = gtk.gdk.pixbuf_new_from_file(self.find_path('sonata_large.png'))
        self.about_dialog.set_logo(large_icon)
        # Add button to show keybindings:
        shortcut_button = ui.button(text=_("_Shortcuts"))
        self.about_dialog.action_area.pack_start(shortcut_button)
        self.about_dialog.action_area.reorder_child(self.about_dialog.action_area.get_children()[-1], -2)
        # Connect to callbacks
        self.about_dialog.connect('response', self.about_close)
        self.about_dialog.connect('delete_event', self.about_close)
        shortcut_button.connect('clicked', self.about_shortcuts)
        self.about_dialog.show_all()


    def show_website(self, dialog, blah, link):
        misc.browser_load(link, self.url_browser, self.window)

    def systemtray_initialize(self):
        # Make system tray 'icon' to sit in the system tray
        if HAVE_STATUS_ICON:
            self.statusicon = gtk.StatusIcon()
            self.statusicon.set_from_file(self.find_path('sonata.png'))
            self.statusicon.set_visible(self.show_trayicon)
            self.statusicon.connect('popup_menu', self.systemtray_menu)
            self.statusicon.connect('activate', self.systemtray_activate)
        elif HAVE_EGG:
            self.trayimage = ui.image()
            self.trayeventbox = ui.eventbox(add=self.trayimage)
            self.trayeventbox.connect('button_press_event', self.systemtray_click)
            self.trayeventbox.connect('scroll-event', self.systemtray_scroll)
            self.trayeventbox.connect('size-allocate', self.systemtray_size)
            self.traytips.set_tip(self.trayeventbox)
            try:
                self.trayicon = egg.trayicon.TrayIcon("TrayIcon")
                self.trayicon.add(self.trayeventbox)
                if self.show_trayicon:
                    self.trayicon.show_all()
                    self.eggtrayfile = self.find_path('sonata.png')
                    self.trayimage.set_from_pixbuf(img.get_pixbuf_of_size(gtk.gdk.pixbuf_new_from_file(self.eggtrayfile), self.eggtrayheight)[0])
                else:
                    self.trayicon.hide_all()
            except:
                pass

    def current_get_songid(self, iter, model):
        return int(model.get_value(iter, 0))

    def libsearchfilter_toggle(self, move_focus):
        if not self.library_search_visible() and self.conn:
            self.library.set_property('has-tooltip', True)
            ui.show(self.searchbutton)
            self.prevlibtodo = 'foo'
            self.prevlibtodo_base = "__"
            self.prevlibtodo_base_results = []
            # extra thread for background search work, synchronized with a condition and its internal mutex
            self.libfilterbox_cond = threading.Condition()
            self.libfilterbox_cmd_buf = self.searchtext.get_text()
            qsearch_thread = threading.Thread(target=self.libsearchfilter_loop)
            qsearch_thread.setDaemon(True)
            qsearch_thread.start()
        elif self.library_search_visible():
            ui.hide(self.searchbutton)
            self.searchtext.handler_block(self.libfilter_changed_handler)
            self.searchtext.set_text("")
            self.searchtext.handler_unblock(self.libfilter_changed_handler)
            self.libsearchfilter_stop_loop()
            self.library_browse(root=self.wd)
            if move_focus:
                self.library.grab_focus()

    def libsearchfilter_feed_loop(self, editable):
        if not self.library_search_visible():
            self.libsearchfilter_toggle(None)
        # Lets only trigger the searchfilter_loop if 200ms pass without a change
        # in gtk.Entry
        try:
            gobject.remove_source(self.libfilterbox_source)
        except:
            pass
        self.libfilterbox_source = gobject.timeout_add(300, self.libsearchfilter_start_loop, editable)

    def libsearchfilter_start_loop(self, editable):
        self.libfilterbox_cond.acquire()
        self.libfilterbox_cmd_buf = editable.get_text()
        self.libfilterbox_cond.notifyAll()
        self.libfilterbox_cond.release()

    def libsearchfilter_stop_loop(self):
        self.libfilterbox_cond.acquire()
        self.libfilterbox_cmd_buf='$$$QUIT###'
        self.libfilterbox_cond.notifyAll()
        self.libfilterbox_cond.release()

    def libsearchfilter_loop(self):
        while True:
            # copy the last command or pattern safely
            self.libfilterbox_cond.acquire()
            try:
                while(self.libfilterbox_cmd_buf == '$$$DONE###'):
                    self.libfilterbox_cond.wait()
                todo = self.libfilterbox_cmd_buf
                self.libfilterbox_cond.release()
            except:
                todo = self.libfilterbox_cmd_buf
                pass
            searchby = self.search_terms_mpd[self.last_search_num]
            if self.prevlibtodo != todo:
                if todo == '$$$QUIT###':
                    gobject.idle_add(self.filtering_entry_revert_color, self.searchtext)
                    return
                elif len(todo) > 1:
                    gobject.idle_add(self.libsearchfilter_do_search, searchby, todo)
                elif len(todo) == 0:
                    gobject.idle_add(self.filtering_entry_revert_color, self.searchtext)
                    self.libsearchfilter_toggle(False)
                else:
                    gobject.idle_add(self.filtering_entry_revert_color, self.searchtext)
            self.libfilterbox_cond.acquire()
            self.libfilterbox_cmd_buf='$$$DONE###'
            try:
                self.libfilterbox_cond.release()
            except:
                pass
            self.prevlibtodo = todo

    def libsearchfilter_do_search(self, searchby, todo):
        if not self.prevlibtodo_base in todo:
            # Do library search based on first two letters:
            self.prevlibtodo_base = todo[:2]
            self.prevlibtodo_base_results = mpdh.call(self.client, 'search', searchby, self.prevlibtodo_base)
            subsearch = False
        else:
            subsearch = True
        # Now, use filtering similar to playlist filtering:
        # this make take some seconds... and we'll escape the search text because
        # we'll be searching for a match in items that are also escaped.
        todo = misc.escape_html(todo)
        todo = re.escape(todo)
        todo = '.*' + todo.replace(' ', ' .*').lower()
        regexp = re.compile(todo)
        matches = []
        if searchby != 'any':
            for row in self.prevlibtodo_base_results:
                if regexp.match(mpdh.get(row, searchby).lower()):
                    matches.append(row)
        else:
            for row in self.prevlibtodo_base_results:
                for meta in row:
                    if regexp.match(mpdh.get(row, meta).lower()):
                        matches.append(row)
                        break
        if subsearch and len(matches) == len(self.librarydata):
            # nothing changed..
            return
        self.library.freeze_child_notify()
        currlen = len(self.librarydata)
        newlist = []
        for item in matches:
            if item.has_key('file'):
                newlist.append([self.sonatapb, self.library_set_data(file=mpdh.get(item, 'file')), self.parse_formatting(self.libraryformat, item, True)])
        for i, item in enumerate(newlist):
            if i < currlen:
                iter = self.librarydata.get_iter((i, ))
                for index in range(len(item)):
                    if item[index] != self.librarydata.get_value(iter, index):
                        self.librarydata.set_value(iter, index, item[index])
            else:
                self.librarydata.append(item)
        # Remove excess items...
        newlen = len(newlist)
        if newlen == 0:
            self.librarydata.clear()
        else:
            for i in range(currlen-newlen):
                iter = self.librarydata.get_iter((currlen-1-i,))
                self.librarydata.remove(iter)
        self.library.thaw_child_notify()
        gobject.idle_add(self.library.set_cursor,'0')
        if len(matches) == 0:
            gobject.idle_add(self.filtering_entry_make_red, self.searchtext)
        else:
            gobject.idle_add(self.filtering_entry_revert_color, self.searchtext)

    def libsearchfilter_key_pressed(self, widget, event):
        self.filter_key_pressed(widget, event, self.library)

    def libsearchfilter_on_enter(self, entry):
        self.on_library_row_activated(None, None)

    def searchfilter_toggle(self, widget, initial_text=""):
        if self.filterbox_visible:
            ui.hide(self.filterbox)
            self.filterbox_visible = False
            self.edit_style_orig = self.searchtext.get_style()
            self.filterpattern.set_text("")
            self.searchfilter_stop_loop()
        elif self.conn:
            self.playlist_pos_before_filter = self.current.get_visible_rect()[1]
            self.filterbox_visible = True
            self.filterpattern.handler_block(self.filter_changed_handler)
            self.filterpattern.set_text(initial_text)
            self.filterpattern.handler_unblock(self.filter_changed_handler)
            self.prevtodo = 'foo'
            ui.show(self.filterbox)
            # extra thread for background search work, synchronized with a condition and its internal mutex
            self.filterbox_cond = threading.Condition()
            self.filterbox_cmd_buf = initial_text
            qsearch_thread = threading.Thread(target=self.searchfilter_loop)
            qsearch_thread.setDaemon(True)
            qsearch_thread.start()
            gobject.idle_add(self.filter_entry_grab_focus, self.filterpattern)
        self.current.set_headers_clickable(not self.filterbox_visible)

    def searchfilter_on_enter(self, entry):
        model, selected = self.current.get_selection().get_selected_rows()
        song_id = None
        if len(selected) > 0:
            # If items are selected, play the first selected item:
            song_id = self.current_get_songid(model.get_iter(selected[0]), model)
        elif len(model) > 0:
            # If nothing is selected: play the first item:
            song_id = self.current_get_songid(model.get_iter_first(), model)
        if song_id:
            self.searchfilter_toggle(None)
            mpdh.call(self.client, 'playid', song_id)

    def searchfilter_feed_loop(self, editable):
        # Lets only trigger the searchfilter_loop if 200ms pass without a change
        # in gtk.Entry
        try:
            gobject.remove_source(self.filterbox_source)
        except:
            pass
        self.filterbox_source = gobject.timeout_add(200, self.searchfilter_start_loop, editable)

    def searchfilter_start_loop(self, editable):
        self.filterbox_cond.acquire()
        self.filterbox_cmd_buf = editable.get_text()
        self.filterbox_cond.notifyAll()
        self.filterbox_cond.release()

    def searchfilter_stop_loop(self):
        self.filterbox_cond.acquire()
        self.filterbox_cmd_buf='$$$QUIT###'
        self.filterbox_cond.notifyAll()
        self.filterbox_cond.release()

    def searchfilter_loop(self):
        while self.filterbox_visible:
            # copy the last command or pattern safely
            self.filterbox_cond.acquire()
            try:
                while(self.filterbox_cmd_buf == '$$$DONE###'):
                    self.filterbox_cond.wait()
                todo = self.filterbox_cmd_buf
                self.filterbox_cond.release()
            except:
                todo = self.filterbox_cmd_buf
                pass
            self.current.freeze_child_notify()
            matches = gtk.ListStore(*([int] + [str] * len(self.columnformat)))
            matches.clear()
            filterposition = self.current.get_visible_rect()[1]
            model, selected = self.current_selection.get_selected_rows()
            filterselected = []
            for path in selected:
                filterselected.append(path)
            rownum = 0
            # Store previous rownums in temporary list, in case we are
            # about to populate the songfilter with a subset of the
            # current filter. This will allow us to preserve the mapping.
            prev_rownums = []
            for song in self.filter_row_mapping:
                prev_rownums.append(song)
            self.filter_row_mapping = []
            if todo == '$$$QUIT###':
                gobject.idle_add(self.searchfilter_revert_model)
                return
            elif len(todo) == 0:
                for row in self.currentdata:
                    self.filter_row_mapping.append(rownum)
                    rownum = rownum + 1
                    song_info = [row[0]]
                    for i in range(len(self.columnformat)):
                        song_info.append(misc.unbold(row[i+1]))
                    matches.append(song_info)
            else:
                # this make take some seconds... and we'll escape the search text because
                # we'll be searching for a match in items that are also escaped.
                todo = misc.escape_html(todo)
                todo = re.escape(todo)
                todo = '.*' + todo.replace(' ', ' .*').lower()
                regexp = re.compile(todo)
                rownum = 0
                if self.prevtodo in todo and len(self.prevtodo) > 0:
                    # If the user's current filter is a subset of the
                    # previous selection (e.g. "h" -> "ha"), search
                    # for files only in the current model, not the
                    # entire self.currentdata
                    subset = True
                    use_data = self.current.get_model()
                    if len(use_data) != len(prev_rownums):
                        # Not exactly sure why this happens sometimes
                        # so lets just revert to prevent a possible, but
                        # infrequent, crash. The only downside is speed.
                        subset = False
                        use_data = self.currentdata
                else:
                    subset = False
                    use_data = self.currentdata
                for row in use_data:
                    song_info = [row[0]]
                    for i in range(len(self.columnformat)):
                        song_info.append(misc.unbold(row[i+1]))
                    # Search for matches in all columns:
                    for i in range(len(self.columnformat)):
                        if regexp.match(str(song_info[i+1]).lower()):
                            matches.append(song_info)
                            if subset:
                                self.filter_row_mapping.append(prev_rownums[rownum])
                            else:
                                self.filter_row_mapping.append(rownum)
                            break
                    rownum = rownum + 1
            if self.prevtodo == todo or self.prevtodo == "RETAIN_POS_AND_SEL":
                # mpd update, retain view of treeview:
                retain_position_and_selection = True
                if self.plpos:
                    filterposition = self.plpos
                    self.plpos = None
            else:
                retain_position_and_selection = False
            self.filterbox_cond.acquire()
            self.filterbox_cmd_buf='$$$DONE###'
            try:
                self.filterbox_cond.release()
            except:
                pass
            gobject.idle_add(self.searchfilter_set_matches, matches, filterposition, filterselected, retain_position_and_selection)
            self.prevtodo = todo

    def searchfilter_revert_model(self):
        self.current.set_model(self.currentdata)
        self.current_center_song_in_list()
        self.current.thaw_child_notify()
        gobject.idle_add(self.current_center_song_in_list)
        gobject.idle_add(self.current.grab_focus)

    def searchfilter_set_matches(self, matches, filterposition, filterselected, retain_position_and_selection):
        self.filterbox_cond.acquire()
        flag = self.filterbox_cmd_buf
        self.filterbox_cond.release()
        # blit only when widget is still ok (segfault candidate, Gtk bug?) and no other
        # search is running, avoid pointless work and don't confuse the user
        if (self.current.get_property('visible') and flag == '$$$DONE###'):
            self.current.set_model(matches)
            if retain_position_and_selection and filterposition:
                self.playlist_retain_view(self.current, filterposition)
                for path in filterselected:
                    self.current_selection.select_path(path)
            else:
                self.current.set_cursor('0')
            if len(matches) == 0:
                gobject.idle_add(self.filtering_entry_make_red, self.filterpattern)
            else:
                gobject.idle_add(self.filtering_entry_revert_color, self.filterpattern)
            self.current.thaw_child_notify()

    def searchfilter_key_pressed(self, widget, event):
        self.filter_key_pressed(widget, event, self.current)

    def filter_key_pressed(self, widget, event, treeview):
        if event.keyval == gtk.gdk.keyval_from_name('Down') or event.keyval == gtk.gdk.keyval_from_name('Up') or event.keyval == gtk.gdk.keyval_from_name('Page_Down') or event.keyval == gtk.gdk.keyval_from_name('Page_Up'):
            treeview.grab_focus()
            treeview.emit("key-press-event", event)
            gobject.idle_add(self.filter_entry_grab_focus, widget)

    def filter_entry_grab_focus(self, widget):
        widget.grab_focus()
        widget.set_position(-1)

    def filtering_entry_make_red(self, editable):
        style = editable.get_style().copy()
        style.text[gtk.STATE_NORMAL] = editable.get_colormap().alloc_color("red")
        editable.set_style(style)

    def filtering_entry_revert_color(self, editable):
        editable.set_style(self.edit_style_orig)

    def main(self):
        gtk.main()

if __name__ == "__main__":
    base = Base()
    gtk.gdk.threads_enter()
    base.main()
    gtk.gdk.threads_leave()

def start_dbus_interface(toggle=False, popup=False):
    if HAVE_DBUS:
        try:
            bus = dbus.SessionBus()
            if NEW_DBUS:
                retval = bus.request_name("org.MPD.Sonata", dbus_bindings.NAME_FLAG_DO_NOT_QUEUE)
            else:
                retval = dbus_bindings.bus_request_name(bus.get_connection(), "org.MPD.Sonata", dbus_bindings.NAME_FLAG_DO_NOT_QUEUE)
            if retval in (dbus_bindings.REQUEST_NAME_REPLY_PRIMARY_OWNER, dbus_bindings.REQUEST_NAME_REPLY_ALREADY_OWNER):
                pass
            elif retval in (dbus_bindings.REQUEST_NAME_REPLY_EXISTS, dbus_bindings.REQUEST_NAME_REPLY_IN_QUEUE):
                obj = bus.get_object('org.MPD', '/org/MPD/Sonata')
                if toggle:
                    obj.toggle(dbus_interface='org.MPD.SonataInterface')
                elif popup:
                    obj.popup(dbus_interface='org.MPD.SonataInterface')
                else:
                    print _("An instance of Sonata is already running.")
                    obj.show(dbus_interface='org.MPD.SonataInterface')
                sys.exit()
        except SystemExit:
            raise
        except Exception:
            print _("Sonata failed to connect to the D-BUS session bus: Unable to determine the address of the message bus (try 'man dbus-launch' and 'man dbus-daemon' for help)")

if HAVE_DBUS:
    class BaseDBus(dbus.service.Object, Base):
        def __init__(self, bus_name, object_path, window=None, sugar=False):
            dbus.service.Object.__init__(self, bus_name, object_path)
            Base.__init__(self, window, sugar)
            if HAVE_GNOME_MMKEYS:
                settingsDaemonInterface.connect_to_signal('MediaPlayerKeyPressed', self.mediaPlayerKeysCallback)

        def mediaPlayerKeysCallback(self, app, key):
            if app == 'Sonata':
                if key in ('Play', 'PlayPause', 'Pause'):
                    self.mpd_pp(None)
                elif key == 'Stop':
                    self.mpd_stop(None)
                elif key == 'Previous':
                    self.mpd_prev(None)
                elif key == 'Next':
                    self.mpd_next(None)

        @dbus.service.method('org.MPD.SonataInterface')
        def show(self):
            self.window.hide()
            self.withdraw_app_undo()

        @dbus.service.method('org.MPD.SonataInterface')
        def toggle(self):
            if self.window.get_property('visible'):
                self.withdraw_app()
            else:
                self.withdraw_app_undo()

        @dbus.service.method('org.MPD.SonataInterface')
        def popup(self):
            self.on_currsong_notify(force_popup=True)
