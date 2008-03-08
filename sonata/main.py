# coding=utf-8
# $HeadURL: http://svn.berlios.de/svnroot/repos/sonata/trunk/main.py $
# $Id: main.py 141 2006-09-11 04:51:07Z stonecrest $

__version__ = "1.4.2"

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

import getopt, sys, mpd, gettext, os, ConfigParser, misc
import mpdhelper as mpdh
from socket import getdefaulttimeout as socketgettimeout
from socket import setdefaulttimeout as socketsettimeout

tagpy = None
ElementTree = None
ServiceProxy = None
audioscrobbler = None

all_args = ["toggle", "version", "status", "info", "play", "pause",
            "stop", "next", "prev", "pp", "shuffle", "repeat", "hidden",
            "visible", "profile=", "popup"]
cli_args = ("play", "pause", "stop", "next", "prev", "pp", "info",
            "status", "repeat", "shuffle", "popup")
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

    # Prevent deprecation warning for egg:
    warnings.simplefilter('ignore', DeprecationWarning)
    try:
        import egg.trayicon
        HAVE_EGG = True
        HAVE_STATUS_ICON = False
    except ImportError:
        HAVE_EGG = False
        if gtk.pygtk_version >= (2, 10, 0):
            # Revert to pygtk status icon:
            HAVE_STATUS_ICON = True
        else:
            HAVE_STATUS_ICON = False
    # Reset so that we can see any other deprecation warnings
    warnings.simplefilter('default', DeprecationWarning)

    HAVE_GNOME_MMKEYS = False
    if HAVE_DBUS:
        try:
            # mmkeys for gnome 2.18+
            bus = dbus.SessionBus()
            dbusObj = bus.get_object('org.freedesktop.DBus', '/org/freedesktop/DBus')
            dbusInterface = dbus.Interface(dbusObj, 'org.freedesktop.DBus')
            if dbusInterface.NameHasOwner('org.gnome.SettingsDaemon'):
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

    try:
        from sugar.activity import activity
        HAVE_STATUS_ICON = False
        HAVE_SUGAR = True
        VOLUME_ICON_SIZE = 3
    except:
        HAVE_SUGAR = False
        VOLUME_ICON_SIZE = 4

    # Test pygtk version
    if gtk.pygtk_version < (2, 6, 0):
        sys.stderr.write("Sonata requires PyGTK 2.6.0 or newer. Aborting...\n")
        sys.exit(1)

class Base:
    def __init__(self, window=None, sugar=False):

        try:
            gettext.install('sonata', os.path.join(__file__.split('/lib')[0], 'share', 'locale'), unicode=1)
        except:
            gettext.install('sonata', '/usr/share/locale', unicode=1)
        gettext.textdomain('sonata')

        # Initialize vars (these can be needed if we have a cli argument, e.g., "sonata play")
        socketsettimeout(5)
        self.profile_num = 0
        self.profile_names = [_('Default Profile')]
        self.musicdir = [self.sanitize_musicdir("~/music")]
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
        self.ART_LOCAL = 0
        self.ART_LOCAL_REMOTE = 1
        self.VIEW_FILESYSTEM = 0
        self.VIEW_ARTIST = 1
        self.VIEW_GENRE = 2
        self.LYRIC_TIMEOUT = 10
        self.NOTIFICATION_WIDTH_MAX = 500
        self.NOTIFICATION_WIDTH_MIN = 350
        self.ART_LOCATION_HOMECOVERS = 0		# ~/.covers/[artist]-[album].jpg
        self.ART_LOCATION_COVER = 1				# file_dir/cover.jpg
        self.ART_LOCATION_ALBUM = 2				# file_dir/album.jpg
        self.ART_LOCATION_FOLDER = 3			# file_dir/folder.jpg
        self.ART_LOCATION_CUSTOM = 4			# file_dir/[custom]
        self.ART_LOCATION_NONE = 5				# Use default Sonata icons
        self.ART_LOCATION_SINGLE = 6
        self.ART_LOCATION_MISC = 7
        self.ART_LOCATION_NONE_FLAG = "USE_DEFAULT"
        self.ART_LOCATIONS_MISC = ['front.jpg', '.folder.jpg', '.folder.png', 'AlbumArt.jpg', 'AlbumArtSmall.jpg']
        self.LYRICS_LOCATION_HOME = 0			# ~/.lyrics/[artist]-[song].txt
        self.LYRICS_LOCATION_PATH = 1			# file_dir/[artist]-[song].txt
        self.LIB_COVER_SIZE = 16
        self.COVERS_TYPE_STANDARD = 0
        self.COVERS_TYPE_STYLIZED = 1
        self.LIB_LEVEL_GENRE = 0
        self.LIB_LEVEL_ARTIST = 1
        self.LIB_LEVEL_ALBUM = 2
        self.LIB_LEVEL_SONG = 3
        self.NOTAG = _("Untagged")

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
                    if o in ("-p", "--popup"):
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

        if not HAVE_EGG and not HAVE_STATUS_ICON:
            print _("PyGTK+ 2.10 or gnome-python-extras not found, system tray support disabled.")

        gtk.gdk.threads_init()

        self.traytips = tray.TrayIconTips()

        start_dbus_interface(toggle_arg, popup_arg)

        self.gnome_session_management()

        misc.create_dir('~/.covers/')

        # Initialize vars for GUI
        self.current_tab = self.TAB_CURRENT
        self.x = 0
        self.y = 0
        self.w = 400
        self.h = 300
        self.expanded = True
        self.withdrawn = False
        self.sticky = False
        self.ontop = False
        self.screen = 0
        self.prevconn = []
        self.prevstatus = None
        self.prevsonginfo = None
        self.lastalbumart = None
        self.xfade = 0
        self.xfade_enabled = False
        self.show_covers = True
        self.covers_type = 1
        self.covers_pref = self.ART_LOCAL_REMOTE
        self.lyricServer = None
        self.show_notification = False
        self.show_playback = True
        self.show_progress = True
        self.show_statusbar = False
        self.show_trayicon = True
        self.show_lyrics = True
        self.stop_on_exit = False
        self.update_on_start = False
        self.minimize_to_systray = False
        self.popuptimes = ['2', '3', '5', '10', '15', '30', _('Entire song')]
        self.popuplocations = [_('System tray'), _('Top Left'), _('Top Right'), _('Bottom Left'), _('Bottom Right'), _('Screen Center')]
        self.popup_option = 2
        self.exit_now = False
        self.ignore_toggle_signal = False
        self.initial_run = True
        self.show_header = True
        self.tabs_expanded = False
        self.currentformat = "%A - %T"
        self.libraryformat = "%A - %T"
        self.titleformat = "[Sonata] %A - %T"
        self.currsongformat1 = "%T"
        self.currsongformat2 = _("by") + " %A " + _("from") + " %B"
        self.columnwidths = []
        self.colwidthpercents = []
        self.autoconnect = True
        self.user_connect = False
        self.stream_names = []
        self.stream_uris = []
        self.downloading_image = False
        self.search_terms = [_('Artist'), _('Title'), _('Album'), _('Genre'), _('Filename'), _('Everything')]
        self.search_terms_mpd = ['artist', 'title', 'album', 'genre', 'filename', 'any']
        self.last_search_num = 0
        self.sonata_loaded = False
        self.call_gc_collect = False
        self.single_img_in_dir = None
        self.misc_img_in_dir = None
        self.total_time = 0
        self.prev_boldrow = -1
        self.use_infofile = False
        self.infofile_path = '/tmp/xmms-info'
        self.lib_view = self.VIEW_FILESYSTEM
        self.lib_level = self.LIB_LEVEL_ARTIST
        self.lib_level_prev = -1
        self.lib_genre = ''
        self.lib_artist = ''
        self.lib_album = ''
        self.songs = None
        self.art_location = self.ART_LOCATION_HOMECOVERS
        self.art_location_custom_filename = ""
        self.lyrics_location = self.LYRICS_LOCATION_HOME
        self.filterbox_visible = False
        self.edit_style_orig = None
        self.album_reset_artist()
        self.as_enabled = False
        self.as_username = ""
        self.as_password = ""
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
        self.url_browser = ""
        self.wd = '/'
        self.filter_row_mapping = [] # Mapping between filter rows and self.currentdata rows
        self.plpos = None
        self.info_song_expanded = True
        self.info_lyrics_expanded = True
        self.info_album_expanded = True
        self.info_song_more = False
        self.current_tab_visible = True
        self.library_tab_visible = True
        self.playlists_tab_visible = True
        self.streams_tab_visible = True
        self.info_tab_visible = True
        self.current_tab_pos = 0
        self.library_tab_pos = 1
        self.playlists_tab_pos = 2
        self.streams_tab_pos = 3
        self.info_tab_pos = 4
        self.last_status_text = ""
        self.info_art_enlarged = False
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
        # If the connection to MPD times out, this will cause the interface to freeze while
        # the socket.connect() calls are repeatedly executed. Therefore, if we were not
        # able to make a connection, slow down the iteration check to once every 15 seconds.
        self.iterate_time_when_connected = 500
        self.iterate_time_when_disconnected_or_stopped = 1000 # Slow down polling when disconnected stopped

        try:
            self.enc = locale.getpreferredencoding()
        except:
            print "Locale cannot be found; please set your system's locale. Aborting..."
            sys.exit(1)

        self.all_tab_names = [self.TAB_CURRENT, self.TAB_LIBRARY, self.TAB_PLAYLISTS, self.TAB_STREAMS, self.TAB_INFO]

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

        # Popup menus:
        actions = (
            ('sortmenu', None, _('_Sort List')),
            ('plmenu', None, _('Sa_ve List to')),
            ('profilesmenu', None, _('_Connection')),
            ('playaftermenu', None, _('P_lay after')),
            ('filesystemview', gtk.STOCK_HARDDISK, _('Filesystem'), None, None, self.on_libraryview_chosen),
            ('artistview', 'artist', _('Artist'), None, None, self.on_libraryview_chosen),
            ('genreview', gtk.STOCK_ORIENTATION_PORTRAIT, _('Genre'), None, None, self.on_libraryview_chosen),
            ('chooseimage_menu', gtk.STOCK_CONVERT, _('Use _Remote Image...'), None, None, self.image_remote),
            ('localimage_menu', gtk.STOCK_OPEN, _('Use _Local Image...'), None, None, self.image_local),
            ('resetimage_menu', gtk.STOCK_CLEAR, _('Reset to Default'), None, None, self.on_reset_image),
            ('playmenu', gtk.STOCK_MEDIA_PLAY, _('_Play'), None, None, self.mpd_pp),
            ('pausemenu', gtk.STOCK_MEDIA_PAUSE, _('_Pause'), None, None, self.mpd_pp),
            ('stopmenu', gtk.STOCK_MEDIA_STOP, _('_Stop'), None, None, self.mpd_stop),
            ('prevmenu', gtk.STOCK_MEDIA_PREVIOUS, _('_Previous'), None, None, self.mpd_prev),
            ('nextmenu', gtk.STOCK_MEDIA_NEXT, _('_Next'), None, None, self.mpd_next),
            ('quitmenu', gtk.STOCK_QUIT, _('_Quit'), None, None, self.on_delete_event_yes),
            ('removemenu', gtk.STOCK_REMOVE, _('_Remove'), None, None, self.on_remove),
            ('clearmenu', gtk.STOCK_CLEAR, _('_Clear'), '<Ctrl>Delete', None, self.mpd_clear),
            ('savemenu', None, _('_New Playlist...'), '<Ctrl><Shift>s', None, self.on_playlist_save),
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
            ('sortrandom', None, _('Random'), '<Alt>r', None, self.mpd_shuffle),
            ('tab1key', None, 'Tab1 Key', '<Alt>1', None, self.on_switch_to_tab1),
            ('tab2key', None, 'Tab2 Key', '<Alt>2', None, self.on_switch_to_tab2),
            ('tab3key', None, 'Tab3 Key', '<Alt>3', None, self.on_switch_to_tab3),
            ('tab4key', None, 'Tab4 Key', '<Alt>4', None, self.on_switch_to_tab4),
            ('tab5key', None, 'Tab5 Key', '<Alt>5', None, self.on_switch_to_tab5),
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
            ('shufflemenu', None, _('_Shuffle'), None, None, self.on_shuffle_clicked, False),
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
                  <menuitem action="sortrandom"/>
                  <menuitem action="sortreverse"/>
                </menu>
                <menu action="plmenu">
                  <menuitem action="savemenu"/>
                  <separator name="FM4"/>
                </menu>
                <separator name="FM1"/>
                <menuitem action="updatemenu"/>
                <menuitem action="repeatmenu"/>
                <menuitem action="shufflemenu"/>
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
              </popup>
              <popup name="hidden">
                <menuitem action="quitkey"/>
                <menuitem action="quitkey2"/>
                <menuitem action="tab1key"/>
                <menuitem action="tab2key"/>
                <menuitem action="tab3key"/>
                <menuitem action="tab4key"/>
                <menuitem action="tab5key"/>
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
        elif self.initial_run:
            show_prefs = True

        # Audioscrobbler
        self.scrobbler_import()
        self.scrobbler_init()

        # Images...
        self.sonatacd = self.find_path('sonatacd.png')
        self.sonatacd_large = self.find_path('sonatacd_large.png')

        # Main app:
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
        self.tooltips = gtk.Tooltips()
        self.UIManager = gtk.UIManager()
        actionGroup = gtk.ActionGroup('Actions')
        actionGroup.add_actions(actions)
        actionGroup.add_toggle_actions(toggle_actions)
        self.UIManager.insert_action_group(actionGroup, 0)
        self.UIManager.add_ui_from_string(uiDescription)
        self.populate_profiles_for_menu()
        self.window.add_accel_group(self.UIManager.get_accel_group())
        self.mainmenu = self.UIManager.get_widget('/mainmenu')
        self.shufflemenu = self.UIManager.get_widget('/mainmenu/shufflemenu')
        self.repeatmenu = self.UIManager.get_widget('/mainmenu/repeatmenu')
        self.imagemenu = self.UIManager.get_widget('/imagemenu')
        self.traymenu = self.UIManager.get_widget('/traymenu')
        self.librarymenu = self.UIManager.get_widget('/librarymenu')
        self.notebookmenu = self.UIManager.get_widget('/notebookmenu')
        mainhbox = gtk.HBox()
        mainvbox = gtk.VBox()
        tophbox = gtk.HBox()
        self.albumimage = ui.image()
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
        self.notebook = gtk.Notebook()
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
        self.tooltips.set_tip(self.libraryview, _("Library browsing view"))
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
        self.tooltips.set_tip(self.expander, self.cursonglabel1.get_text())
        if not self.conn:
            self.progressbar.set_text(_('Not Connected'))
        elif not self.status:
            self.progressbar.set_text(_('No Read Permission'))
        self.tooltips.set_tip(self.libraryview, _("Library browsing view"))
        if gtk.pygtk_version >= (2, 10, 0):
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

        # Systray:
        outtertipbox = gtk.VBox()
        tipbox = gtk.HBox()
        self.trayalbumimage1 = ui.image(w=51, h=77, x=1)
        self.trayalbumeventbox = ui.eventbox(w=59, h=90, add=self.trayalbumimage1, state=gtk.STATE_SELECTED, visible=True)
        hiddenlbl = ui.label(w=2, h=-1)
        tipbox.pack_start(hiddenlbl, False, False, 0)
        tipbox.pack_start(self.trayalbumeventbox, False, False, 0)
        self.trayalbumimage2 = ui.image(w=26, h=77)
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
        self.shufflemenu.connect('toggled', self.on_shuffle_clicked)
        self.repeatmenu.connect('toggled', self.on_repeat_clicked)
        self.volumescale.connect('change_value', self.on_volumescale_change)
        self.volumescale.connect('scroll-event', self.on_volumescale_scroll)
        self.cursonglabel1.connect('notify::label', self.on_currsong_notify)
        self.progressbar.connect('notify::fraction', self.on_progressbar_notify_fraction)
        self.progressbar.connect('notify::text', self.on_progressbar_notify_text)
        self.library.connect('row_activated', self.on_library_row_activated)
        self.library.connect('button_press_event', self.on_library_button_press)
        self.library.connect('key-press-event', self.on_library_key_press)
        self.libraryview.connect('clicked', self.library_view_popup)
        self.playlists.connect('button_press_event', self.on_playlists_button_press)
        self.playlists.connect('row_activated', self.playlists_activated)
        self.playlists.connect('key-press-event', self.playlists_key_press)
        self.streams.connect('button_press_event', self.on_streams_button_press)
        self.streams.connect('row_activated', self.on_streams_activated)
        self.streams.connect('key-press-event', self.on_streams_key_press)
        self.mainwinhandler = self.window.connect('button_press_event', self.on_window_click)
        self.searchcombo.connect('changed', self.on_library_search_combo_change)
        self.searchtext.connect('activate', self.on_library_search_activate)
        self.searchbutton.connect('clicked', self.on_library_search_end)
        self.notebook.connect('button_press_event', self.on_notebook_click)
        self.notebook.connect('size-allocate', self.on_notebook_resize)
        self.notebook.connect('switch-page', self.on_notebook_page_change)
        self.searchtext.connect('button_press_event', self.on_library_search_text_click)
        self.filter_changed_handler = self.filterpattern.connect('changed', self.searchfilter_feed_loop)
        self.filterpattern.connect('activate', self.searchfilter_on_enter)
        self.filterpattern.connect('key-press-event', self.searchfilter_key_pressed)
        filterclosebutton.connect('clicked', self.searchfilter_toggle)
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

        # Put blank cd to albumimage widget by default
        self.albumimage.set_from_file(self.sonatacd)

        # Set up current view
        self.current_initialize_columns()
        self.current_selection.set_mode(gtk.SELECTION_MULTIPLE)
        self.current.enable_model_drag_source(gtk.gdk.BUTTON1_MASK, [('STRING', 0, 0), ("text/uri-list", 0, 80)], gtk.gdk.ACTION_MOVE)
        self.current.enable_model_drag_dest([('STRING', 0, 0), ("text/uri-list", 0, 80)], gtk.gdk.ACTION_MOVE)

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
        self.searchcombo.set_active(self.last_search_num)
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
        self.openpb = self.library.render_icon(gtk.STOCK_OPEN, gtk.ICON_SIZE_MENU)
        self.harddiskpb = self.library.render_icon(gtk.STOCK_HARDDISK, gtk.ICON_SIZE_MENU)
        self.albumpb = gtk.gdk.pixbuf_new_from_file_at_size(self.find_path('sonata-album.png'), self.LIB_COVER_SIZE, self.LIB_COVER_SIZE)
        self.genrepb = self.library.render_icon('gtk-orientation-portrait', gtk.ICON_SIZE_MENU)
        self.artistpb = self.library.render_icon('artist', gtk.ICON_SIZE_MENU)
        self.sonatapb = self.library.render_icon('sonata', gtk.ICON_SIZE_MENU)
        self.casepb = gtk.gdk.pixbuf_new_from_file(self.find_path('sonata-case.png'))

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
        print "  shuffle              " + _("Toggle shuffle mode")
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
        self.info_image = ui.image(y=0)
        if self.info_art_enlarged:
            self.info_imagebox = ui.eventbox(add=self.info_image)
        else:
            self.info_imagebox = ui.eventbox(add=self.info_image, w=152)
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
        searchevbox = ui.eventbox(add=self.info_searchlabel)
        self.info_apply_link_signals(searchevbox, 'search', _("Search Lyricwiki.org for lyrics"))
        lyricsbox_bottom.pack_start(searchevbox, False, False, horiz_spacing)
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
        self.tooltips.set_tip(widget, tooltip)

    def current_initialize_columns(self):
        # Initialize current playlist data and widget
        self.resizing_columns = False
        self.columnformat = self.currentformat.split("|")
        self.currentdata = gtk.ListStore(*([int] + [str] * len(self.columnformat)))
        self.current.set_model(self.currentdata)
        cellrenderer = gtk.CellRendererText()
        cellrenderer.set_property("ellipsize", pango.ELLIPSIZE_END)
        self.columns = []
        index = 1
        colnames = self.parse_formatting_colnames(self.currentformat)
        if len(self.columnformat) <> len(self.columnwidths):
            # Number of columns changed, set columns equally spaced:
            self.columnwidths = []
            self.colwidthpercents = [ 1/float(len(self.columnformat)) ] * len(self.columnformat)
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
        self.mpd_connect(blocking=True, force_connection=True)
        if self.conn:
            self.status = mpdh.status(self.client)
            self.songinfo = mpdh.currsong(self.client)
            if type == "play":
                self.client.play()
            elif type == "pause":
                self.client.pause(1)
            elif type == "stop":
                self.client.stop()
            elif type == "next":
                self.client.next()
            elif type == "prev":
                self.client.previous()
            elif type == "shuffle":
                if self.status:
                    self.client.random()
            elif type == "repeat":
                if self.status:
                    self.client.repeat()
            elif type == "pp":
                self.status = mpdh.status(self.client)
                if self.status:
                    if self.status['state'] in ['play']:
                        self.client.pause(1)
                    elif self.status['state'] in ['pause', 'stop']:
                        self.client.play()
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
                            print _("Shuffle") + ": " + _("Off")
                        else:
                            print _("Shuffle") + ": " + _("On")
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
            actions.append((action_name, None, misc.unescape_html(playlistinfo[i]), None, None, self.on_playlist_add_songs))
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

    def populate_profiles_for_menu(self):
        host, port, password = self.mpd_env_vars()
        if host or port: return
        if self.merge_id:
            self.UIManager.remove_ui(self.merge_id)
        if self.actionGroupProfiles:
            self.UIManager.remove_action_group(self.actionGroupProfiles)
            self.actionGroupProfiles = None
        self.actionGroupProfiles = gtk.ActionGroup('MPDProfiles')
        self.UIManager.ensure_update()
        actions = []
        for i in range(len(self.profile_names)):
            action_name = "Profile: " + self.profile_names[i].replace("&", "")
            actions.append((action_name, None, "[" + str(i+1) + "] " + self.profile_names[i], None, None, i))
        actions.append(('disconnect', None, _('Disconnect'), None, None, len(self.profile_names)))
        self.actionGroupProfiles.add_radio_actions(actions, self.profile_num, self.on_profiles_click)
        uiDescription = """
            <ui>
              <popup name="mainmenu">
                  <menu action="profilesmenu">
            """
        uiDescription = uiDescription + """<menuitem action=\"""" + 'disconnect' + """\" position="top"/>"""
        for i in range(len(self.profile_names)):
            action_name = "Profile: " + self.profile_names[len(self.profile_names)-i-1].replace("&", "")
            uiDescription = uiDescription + """<menuitem action=\"""" + action_name + """\" position="top"/>"""
        uiDescription = uiDescription + """</menu></popup></ui>"""
        self.merge_id = self.UIManager.add_ui_from_string(uiDescription)
        self.UIManager.insert_action_group(self.actionGroupProfiles, 0)
        self.UIManager.get_widget('/hidden').set_property('visible', False)

    def on_profiles_click(self, radioaction, current):
        if self.skip_on_profiles_click:
            return
        self.on_disconnectkey_pressed(None)
        if current.get_current_value() < len(self.profile_names):
            self.profile_num = current.get_current_value()
            self.on_connectkey_pressed(None)

    def mpd_connect(self, blocking=False, force_connection=False):
        if blocking:
            self._mpd_connect(blocking, force_connection)
        else:
            thread = threading.Thread(target=self._mpd_connect, args=(blocking, force_connection))
            thread.setDaemon(True)
            thread.start()

    def _mpd_connect(self, blocking, force_connection):
        if self.trying_connection:
            return
        self.trying_connection = True
        if self.user_connect or force_connection:
            try:
                host, port, password = self.mpd_env_vars()
                if not host: host = self.host[self.profile_num]
                if not port: port = self.port[self.profile_num]
                if not password: password = self.password[self.profile_num]
                self.client.connect(host, port)
                if len(password) > 0:
                    self.client.password(password)
                test = mpdh.status(self.client)
                if test:
                    self.conn = True
                else:
                    self.conn = False
            except:
                self.client = None
        else:
            self.conn = False
        if not self.conn:
            self.status = None
            self.songinfo = None
            self.iterate_time = self.iterate_time_when_disconnected_or_stopped
        self.trying_connection = False

    def mpd_disconnect(self):
        if self.conn:
            try:
                self.client.close()
            except:
                pass
            self.conn = False

    def on_connectkey_pressed(self, event):
        self.user_connect = True
        # Update selected radio button in menu:
        self.skip_on_profiles_click = True
        for gtkAction in self.actionGroupProfiles.list_actions():
            if gtkAction.get_name() == self.profile_names[self.profile_num]:
                gtkAction.activate()
                break
        self.skip_on_profiles_click = False
        # Connect:
        self.mpd_connect()
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
        # I'm not sure why this doesn't automatically happen, so
        # we'll do it manually for the time being
        self.librarydata.clear()
        self.playlistsdata.clear()
        if self.filterbox_visible:
            gobject.idle_add(self.searchfilter_toggle, None)

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
                if self.status:
                    if not self.last_repeat or self.last_repeat != self.status['repeat']:
                        self.repeatmenu.set_active(self.status['repeat'] == '1')
                    if not self.last_random or self.last_random != self.status['random']:
                        self.shufflemenu.set_active(self.status['random'] == '1')
                    if self.status['xfade'] == '0':
                        self.xfade_enabled = False
                    else:
                        self.xfade_enabled = True
                        self.xfade = int(self.status['xfade'])
                        if self.xfade > 30: self.xfade = 30
                    self.last_repeat = self.status['repeat']
                    self.last_random = self.status['random']
        except:
            self.prevconn = self.client
            self.prevstatus = self.status
            self.prevsonginfo = self.songinfo
            self.conn = False
            self.status = None
            self.songinfo = None

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
                if self.trayicon.get_property('visible') == False:
                    # Systemtray appears, add icon:
                    self.systemtray_initialize()

        if self.call_gc_collect:
            gc.collect()
            self.call_gc_collect = False

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
                elif HAVE_EGG and self.trayicon.get_property('visible') == True:
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
        # Load config
        conf = ConfigParser.ConfigParser()
        misc.create_dir('~/.config/sonata/')
        if os.path.isfile(os.path.expanduser('~/.config/sonata/sonatarc')):
            conf.read(os.path.expanduser('~/.config/sonata/sonatarc'))
        else:
            return
        # Compatibility with previous versions of Sonata:
        # --------------------------------------------------------------------
        if conf.has_option('connection', 'host'):
            self.host[0] = conf.get('connection', 'host')
        if conf.has_option('connection', 'port'):
            self.port[0] = int(conf.get('connection', 'port'))
        if conf.has_option('connection', 'password'):
            self.password[0] = conf.get('connection', 'password')
        if conf.has_option('connection', 'musicdir'):
            self.musicdir[0] = self.sanitize_musicdir(conf.get('connection', 'musicdir'))
        # --------------------------------------------------------------------
        if conf.has_option('connection', 'auto'):
            self.autoconnect = conf.getboolean('connection', 'auto')
        if conf.has_option('connection', 'profile_num'):
            self.profile_num = conf.getint('connection', 'profile_num')
        if conf.has_option('player', 'x'):
            self.x = conf.getint('player', 'x')
        if conf.has_option('player', 'y'):
            self.y = conf.getint('player', 'y')
        if conf.has_option('player', 'w'):
            self.w = conf.getint('player', 'w')
        if conf.has_option('player', 'h'):
            self.h = conf.getint('player', 'h')
        if conf.has_option('player', 'expanded'):
            self.expanded = conf.getboolean('player', 'expanded')
        if conf.has_option('player', 'withdrawn'):
            self.withdrawn = conf.getboolean('player', 'withdrawn')
        if conf.has_option('player', 'screen'):
            self.screen = conf.getint('player', 'screen')
        if conf.has_option('player', 'covers'):
            self.show_covers = conf.getboolean('player', 'covers')
        if conf.has_option('player', 'covers_type'):
            self.covers_type = conf.getint('player', 'covers_type')
        if conf.has_option('player', 'stop_on_exit'):
            self.stop_on_exit = conf.getboolean('player', 'stop_on_exit')
        if conf.has_option('player', 'minimize'):
            self.minimize_to_systray = conf.getboolean('player', 'minimize')
        if conf.has_option('player', 'initial_run'):
            self.initial_run = conf.getboolean('player', 'initial_run')
        if conf.has_option('player', 'statusbar'):
            self.show_statusbar = conf.getboolean('player', 'statusbar')
        if conf.has_option('player', 'lyrics'):
            self.show_lyrics = conf.getboolean('player', 'lyrics')
        if conf.has_option('player', 'sticky'):
            self.sticky = conf.getboolean('player', 'sticky')
        if conf.has_option('player', 'ontop'):
            self.ontop = conf.getboolean('player', 'ontop')
        if conf.has_option('player', 'notification'):
            self.show_notification = conf.getboolean('player', 'notification')
        if conf.has_option('player', 'popup_time'):
            self.popup_option = conf.getint('player', 'popup_time')
        if conf.has_option('player', 'update_on_start'):
            self.update_on_start = conf.getboolean('player', 'update_on_start')
        if conf.has_option('player', 'notif_location'):
            if not skip_gui:
                self.traytips.notifications_location = conf.getint('player', 'notif_location')
        if conf.has_option('player', 'playback'):
            self.show_playback = conf.getboolean('player', 'playback')
        if conf.has_option('player', 'progressbar'):
            self.show_progress = conf.getboolean('player', 'progressbar')
        if conf.has_option('player', 'crossfade'):
            crossfade = conf.getint('player', 'crossfade')
            # Backwards compatibility:
            self.xfade = [1,2,3,5,10,15][crossfade]
        if conf.has_option('player', 'xfade'):
            self.xfade = conf.getint('player', 'xfade')
        if conf.has_option('player', 'xfade_enabled'):
            self.xfade_enabled = conf.getboolean('player', 'xfade_enabled')
        if conf.has_option('player', 'covers_pref'):
            self.covers_pref = conf.getint('player', 'covers_pref')
            # Specifying remote artwork first is too confusing and probably
            # rarely used, so we're removing this option and defaulting users
            # back to the default 'local, then remote' option.
            if self.covers_pref > self.ART_LOCAL_REMOTE:
                self.covers_pref = self.ART_LOCAL_REMOTE
        if conf.has_option('player', 'use_infofile'):
            self.use_infofile = conf.getboolean('player', 'use_infofile')
        if conf.has_option('player', 'infofile_path'):
            self.infofile_path = conf.get('player', 'infofile_path')
        if conf.has_option('player', 'trayicon'):
            self.show_trayicon = conf.getboolean('player', 'trayicon')
        if conf.has_option('player', 'view'):
            self.lib_view = conf.getint('player', 'view')
        if conf.has_option('player', 'search_num'):
            self.last_search_num = conf.getint('player', 'search_num')
        if conf.has_option('player', 'art_location'):
            self.art_location = conf.getint('player', 'art_location')
        if conf.has_option('player', 'art_location_custom_filename'):
            self.art_location_custom_filename = conf.get('player', 'art_location_custom_filename')
        if conf.has_option('player', 'lyrics_location'):
            self.lyrics_location = conf.getint('player', 'lyrics_location')
        if conf.has_option('player', 'info_song_expanded'):
            self.info_song_expanded = conf.getboolean('player', 'info_song_expanded')
        if conf.has_option('player', 'info_lyrics_expanded'):
            self.info_lyrics_expanded = conf.getboolean('player', 'info_lyrics_expanded')
        if conf.has_option('player', 'info_album_expanded'):
            self.info_album_expanded = conf.getboolean('player', 'info_album_expanded')
        if conf.has_option('player', 'info_song_more'):
            self.info_song_more = conf.getboolean('player', 'info_song_more')
        if conf.has_option('player', 'columnwidths'):
            self.columnwidths = conf.get('player', 'columnwidths').split(",")
            for col in range(len(self.columnwidths)):
                self.columnwidths[col] = int(self.columnwidths[col])
            self.colwidthpercents = [0] * len(self.columnwidths)
        if conf.has_option('player', 'show_header'):
            self.show_header = conf.getboolean('player', 'show_header')
        if conf.has_option('player', 'tabs_expanded'):
            self.tabs_expanded = conf.getboolean('player', 'tabs_expanded')
        if conf.has_option('player', 'browser'):
            self.url_browser = conf.get('player', 'browser')
        if conf.has_option('player', 'info_art_enlarged'):
            self.info_art_enlarged = conf.getboolean('player', 'info_art_enlarged')
        if conf.has_section('notebook'):
            if conf.has_option('notebook', 'current_tab_visible'):
                self.current_tab_visible = conf.getboolean('notebook', 'current_tab_visible')
            if conf.has_option('notebook', 'library_tab_visible'):
                self.library_tab_visible = conf.getboolean('notebook', 'library_tab_visible')
            if conf.has_option('notebook', 'playlists_tab_visible'):
                self.playlists_tab_visible = conf.getboolean('notebook', 'playlists_tab_visible')
            if conf.has_option('notebook', 'streams_tab_visible'):
                self.streams_tab_visible = conf.getboolean('notebook', 'streams_tab_visible')
            if conf.has_option('notebook', 'info_tab_visible'):
                self.info_tab_visible = conf.getboolean('notebook', 'info_tab_visible')
            if conf.has_option('notebook', 'current_tab_pos'):
                try: self.current_tab_pos = conf.getint('notebook', 'current_tab_pos')
                except: pass
            if conf.has_option('notebook', 'library_tab_pos'):
                try: self.library_tab_pos = conf.getint('notebook', 'library_tab_pos')
                except: pass
            if conf.has_option('notebook', 'playlists_tab_pos'):
                try: self.playlists_tab_pos = conf.getint('notebook', 'playlists_tab_pos')
                except: pass
            if conf.has_option('notebook', 'streams_tab_pos'):
                try: self.streams_tab_pos = conf.getint('notebook', 'streams_tab_pos')
                except: pass
            if conf.has_option('notebook', 'info_tab_pos'):
                try: self.info_tab_pos = conf.getint('notebook', 'info_tab_pos')
                except: pass
        if conf.has_section('library'):
            if conf.has_option('library', 'root'):
                self.wd = conf.get('library', 'root')
            if conf.has_option('library', 'root_artist_level'):
                self.lib_level = conf.getint('library', 'root_artist_level')
            if conf.has_option('library', 'root_artist_artist'):
                self.lib_artist = conf.get('library', 'root_artist_artist')
            if conf.has_option('library', 'root_artist_album'):
                self.lib_album = conf.get('library', 'root_artist_album')
            if conf.has_option('library', 'root_genre'):
                self.lib_genre = conf.get('library', 'root_genre')
        if conf.has_section('currformat'):
            if conf.has_option('currformat', 'current'):
                self.currentformat = conf.get('currformat', 'current')
            if conf.has_option('currformat', 'library'):
                self.libraryformat = conf.get('currformat', 'library')
            if conf.has_option('currformat', 'title'):
                self.titleformat = conf.get('currformat', 'title')
            if conf.has_option('currformat', 'currsong1'):
                self.currsongformat1 = conf.get('currformat', 'currsong1')
            if conf.has_option('currformat', 'currsong2'):
                self.currsongformat2 = conf.get('currformat', 'currsong2')
        elif conf.has_section('format'): # old format
            if conf.has_option('format', 'current'):
                self.currentformat = conf.get('format', 'current').replace("%T", "%N").replace("%S", "%T")
            if conf.has_option('format', 'library'):
                self.libraryformat = conf.get('format', 'library').replace("%T", "%N").replace("%S", "%T")
            if conf.has_option('format', 'title'):
                self.titleformat = conf.get('format', 'title').replace("%T", "%N").replace("%S", "%T")
            if conf.has_option('format', 'currsong1'):
                self.currsongformat1 = conf.get('format', 'currsong1').replace("%T", "%N").replace("%S", "%T")
            if conf.has_option('format', 'currsong2'):
                self.currsongformat2 = conf.get('format', 'currsong2').replace("%T", "%N").replace("%S", "%T")
        if conf.has_option('streams', 'num_streams'):
            num_streams = conf.getint('streams', 'num_streams')
            self.stream_names = []
            self.stream_uris = []
            for i in range(num_streams):
                self.stream_names.append(conf.get('streams', 'names[' + str(i) + ']'))
                self.stream_uris.append(conf.get('streams', 'uris[' + str(i) + ']'))
        if conf.has_option('audioscrobbler', 'use_audioscrobbler'):
            self.as_enabled = conf.getboolean('audioscrobbler', 'use_audioscrobbler')
        if conf.has_option('audioscrobbler', 'username'):
            self.as_username = conf.get('audioscrobbler', 'username')
        if conf.has_option('audioscrobbler', 'password'):
            self.as_password = conf.get('audioscrobbler', 'password')
        if conf.has_option('profiles', 'num_profiles'):
            num_profiles = conf.getint('profiles', 'num_profiles')
            self.profile_names = []
            self.host = []
            self.port = []
            self.password = []
            self.musicdir = []
            for i in range(num_profiles):
                self.profile_names.append(conf.get('profiles', 'names[' + str(i) + ']'))
                self.host.append(conf.get('profiles', 'hosts[' + str(i) + ']'))
                self.port.append(conf.getint('profiles', 'ports[' + str(i) + ']'))
                self.password.append(conf.get('profiles', 'passwords[' + str(i) + ']'))
                self.musicdir.append(self.sanitize_musicdir(conf.get('profiles', 'musicdirs[' + str(i) + ']')))

    def settings_save(self):
        conf = ConfigParser.ConfigParser()
        conf.add_section('profiles')
        conf.set('profiles', 'num_profiles', len(self.profile_names))
        for i in range(len(self.profile_names)):
            conf.set('profiles', 'names[' + str(i) + ']', self.profile_names[i])
            conf.set('profiles', 'hosts[' + str(i) + ']', self.host[i])
            conf.set('profiles', 'ports[' + str(i) + ']', self.port[i])
            conf.set('profiles', 'passwords[' + str(i) + ']', self.password[i])
            conf.set('profiles', 'musicdirs[' + str(i) + ']', self.musicdir[i])
        conf.add_section('connection')
        conf.set('connection', 'auto', self.autoconnect)
        conf.set('connection', 'profile_num', self.profile_num)
        conf.add_section('player')
        conf.set('player', 'w', self.w)
        conf.set('player', 'h', self.h)
        conf.set('player', 'x', self.x)
        conf.set('player', 'y', self.y)
        conf.set('player', 'expanded', self.expanded)
        conf.set('player', 'withdrawn', self.withdrawn)
        conf.set('player', 'screen', self.screen)
        conf.set('player', 'covers', self.show_covers)
        conf.set('player', 'covers_type', self.covers_type)
        conf.set('player', 'stop_on_exit', self.stop_on_exit)
        conf.set('player', 'minimize', self.minimize_to_systray)
        conf.set('player', 'initial_run', self.initial_run)
        conf.set('player', 'statusbar', self.show_statusbar)
        conf.set('player', 'lyrics', self.show_lyrics)
        conf.set('player', 'sticky', self.sticky)
        conf.set('player', 'ontop', self.ontop)
        conf.set('player', 'notification', self.show_notification)
        conf.set('player', 'popup_time', self.popup_option)
        conf.set('player', 'update_on_start', self.update_on_start)
        conf.set('player', 'notif_location', self.traytips.notifications_location)
        conf.set('player', 'playback', self.show_playback)
        conf.set('player', 'progressbar', self.show_progress)
        conf.set('player', 'xfade', self.xfade)
        conf.set('player', 'xfade_enabled', self.xfade_enabled)
        conf.set('player', 'covers_pref', self.covers_pref)
        conf.set('player', 'use_infofile', self.use_infofile)
        conf.set('player', 'infofile_path', self.infofile_path)
        conf.set('player', 'trayicon', self.show_trayicon)
        conf.set('player', 'view', self.lib_view)
        conf.set('player', 'search_num', self.last_search_num)
        conf.set('player', 'art_location', self.art_location)
        conf.set('player', 'art_location_custom_filename', self.art_location_custom_filename)
        conf.set('player', 'lyrics_location', self.lyrics_location)
        conf.set('player', 'info_song_expanded', self.info_song_expanded)
        conf.set('player', 'info_lyrics_expanded', self.info_lyrics_expanded)
        conf.set('player', 'info_album_expanded', self.info_album_expanded)
        conf.set('player', 'info_song_more', self.info_song_more)
        conf.set('player', 'info_art_enlarged', self.info_art_enlarged)
        self.header_save_column_widths()
        tmp = ""
        for i in range(len(self.columns)-1):
            tmp += str(self.columnwidths[i]) + ","
        tmp += str(self.columnwidths[len(self.columns)-1])
        conf.set('player', 'columnwidths', tmp)
        conf.set('player', 'show_header', self.show_header)
        conf.set('player', 'tabs_expanded', self.tabs_expanded)
        conf.set('player', 'browser', self.url_browser)
        conf.add_section('notebook')
        # Save tab positions:
        conf.set('notebook', 'current_tab_visible', self.current_tab_visible)
        conf.set('notebook', 'library_tab_visible', self.library_tab_visible)
        conf.set('notebook', 'playlists_tab_visible', self.playlists_tab_visible)
        conf.set('notebook', 'streams_tab_visible', self.streams_tab_visible)
        conf.set('notebook', 'info_tab_visible', self.info_tab_visible)
        self.current_tab_pos = self.notebook_get_tab_num(self.notebook, self.TAB_CURRENT)
        self.library_tab_pos = self.notebook_get_tab_num(self.notebook, self.TAB_LIBRARY)
        self.playlists_tab_pos = self.notebook_get_tab_num(self.notebook, self.TAB_PLAYLISTS)
        self.streams_tab_pos = self.notebook_get_tab_num(self.notebook, self.TAB_STREAMS)
        self.info_tab_pos = self.notebook_get_tab_num(self.notebook, self.TAB_INFO)
        conf.set('notebook', 'current_tab_pos', self.current_tab_pos)
        conf.set('notebook', 'library_tab_pos', self.library_tab_pos)
        conf.set('notebook', 'playlists_tab_pos', self.playlists_tab_pos)
        conf.set('notebook', 'streams_tab_pos', self.streams_tab_pos)
        conf.set('notebook', 'info_tab_pos', self.info_tab_pos)
        conf.add_section('library')
        conf.set('library', 'root', self.wd)
        conf.set('library', 'root_artist_level', self.lib_level)
        conf.set('library', 'root_artist_artist', self.lib_artist)
        conf.set('library', 'root_artist_album', self.lib_album)
        conf.set('library', 'root_genre', self.lib_genre)
        # Old formats, before some letter changes. We'll keep this in for compatibility with
        # older versions of Sonata for the time being.
        conf.add_section('format')
        conf.set('format', 'current', self.currentformat.replace("%T", "%S").replace("%N", "%T"))
        conf.set('format', 'library', self.libraryformat.replace("%T", "%S").replace("%N", "%T"))
        conf.set('format', 'title', self.titleformat.replace("%T", "%S").replace("%N", "%T"))
        conf.set('format', 'currsong1', self.currsongformat1.replace("%T", "%S").replace("%N", "%T"))
        conf.set('format', 'currsong2', self.currsongformat2.replace("%T", "%S").replace("%N", "%T"))
        # New format
        conf.add_section('currformat')
        conf.set('currformat', 'current', self.currentformat)
        conf.set('currformat', 'library', self.libraryformat)
        conf.set('currformat', 'title', self.titleformat)
        conf.set('currformat', 'currsong1', self.currsongformat1)
        conf.set('currformat', 'currsong2', self.currsongformat2)
        conf.add_section('streams')
        conf.set('streams', 'num_streams', len(self.stream_names))
        for i in range(len(self.stream_names)):
            conf.set('streams', 'names[' + str(i) + ']', self.stream_names[i])
            conf.set('streams', 'uris[' + str(i) + ']', self.stream_uris[i])
        conf.add_section('audioscrobbler')
        conf.set('audioscrobbler', 'use_audioscrobbler', self.as_enabled)
        conf.set('audioscrobbler', 'username', self.as_username)
        conf.set('audioscrobbler', 'password', self.as_password)
        conf.write(file(os.path.expanduser('~/.config/sonata/sonatarc'), 'w'))

    def handle_change_conn(self):
        if not self.conn:
            for mediabutton in (self.ppbutton, self.stopbutton, self.prevbutton, self.nextbutton, self.volumebutton):
                mediabutton.set_property('sensitive', False)
            self.currentdata.clear()
            if self.current.get_model():
                self.current.get_model().clear()
            self.songs = None
            if HAVE_STATUS_ICON:
                self.statusicon.set_from_file(self.find_path('sonata_disconnect.png'))
            elif HAVE_EGG and self.eggtrayheight:
                self.eggtrayfile = self.find_path('sonata_disconnect.png')
                self.trayimage.set_from_pixbuf(img.get_pixbuf_of_size(gtk.gdk.pixbuf_new_from_file(self.eggtrayfile), self.eggtrayheight)[0])
            self.info_update(True)
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
                    if not edit_mode or (edit_mode and i <> stream_num):
                        if item == name:
                            dialog.destroy()
                            if ui.show_error_msg_yesno(self.window, _("A stream with this name already exists. Would you like to replace it?"), _("New Stream"), 'newStreamError') == gtk.RESPONSE_YES:
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
            try:
                self.client.rm(plname)
            except:
                pass
            self.client.save(plname)
            self.playlists_populate()
            self.iterate_now()

    def on_playlist_add_songs(self, action):
        plname = misc.unescape_html(action.get_name().replace("Playlist: ", ""))
        self.client.command_list_ok_begin()
        for song in self.songs:
            self.client.playlistadd(plname, mpdh.get(song, 'file'))
        self.client.command_list_end()

    def playlist_name_exists(self, title, role, plname, skip_plname=""):
        # If the playlist already exists, and the user does not want to replace it, return True; In
        # all other cases, return False
        for item in self.client.lsinfo():
            if item.has_key('playlist'):
                if mpdh.get(item, 'playlist') == plname and plname != skip_plname:
                    if ui.show_error_msg_yesno(self.window, _("A playlist with this name already exists. Would you like to replace it?"), title, role) == gtk.RESPONSE_YES:
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
            for item in self.client.lsinfo():
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
            try:
                self.client.rm(plname)
            except:
                pass
            self.client.rename(oldname, plname)
            self.playlists_populate()
            self.iterate_now()
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
        prev_view = self.lib_view
        if action.get_name() == 'filesystemview':
            self.lib_view = self.VIEW_FILESYSTEM
        elif action.get_name() == 'artistview':
            self.lib_view = self.VIEW_ARTIST
        elif action.get_name() == 'genreview':
            self.lib_view = self.VIEW_GENRE
        self.library.grab_focus()
        self.library_view_assign_image()
        # Go to highest level for artist/genre views:
        if self.lib_view == self.VIEW_ARTIST:
            self.lib_level = self.LIB_LEVEL_ARTIST
        elif self.lib_view == self.VIEW_GENRE:
            self.lib_level = self.LIB_LEVEL_GENRE
        self.libraryposition = {}
        self.libraryselectedpath = {}
        try:
            self.library_browse()
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

    def library_browse_verify(self, root):
        # Handle special cases, such as if the path has disappeared.
        # Typically we will keep on traversing up the hierarchy until
        # we find items that exist.
        #
        # Returns lsinfo so that we don't have to do another
        # self.client.lsinfo() call for self.VIEW_FILESYSTEM
        try:
            lsinfo = self.client.lsinfo(root)
        except:
            lsinfo = []
        while lsinfo == []:
            if self.lib_view == self.VIEW_FILESYSTEM:
                if root == '/':
                    return
                else:
                    # Back up and try the parent
                    root = '/'.join(root.split('/')[:-1]) or '/'
            elif self.lib_view == self.VIEW_ARTIST or self.lib_view == self.VIEW_GENRE:
                if self.lib_level == self.LIB_LEVEL_GENRE:
                    break
                elif self.lib_level == self.LIB_LEVEL_ARTIST:
                    if self.lib_view == self.VIEW_ARTIST:
                        break
                    elif self.lib_view == self.VIEW_GENRE:
                        if root == self.NOTAG:
                            # It's okay for this to not have items...
                            break
                        elif len(self.return_genres()) == 0:
                            # Back up and try the parent:
                            self.lib_level -= 1
                        else:
                            break
                elif self.lib_level == self.LIB_LEVEL_ALBUM:
                    if root == self.NOTAG:
                        # It's okay for these to not have items...
                        break
                    elif len(self.return_artist_items(root)) == 0:
                        # Back up and try the parent
                        self.lib_level -= 1
                    else:
                        break
                else:
                    break
            else:
                break
            try:
                lsinfo = self.client.lsinfo(root)
            except:
                lsinfo = []
        return lsinfo

    def library_browse(self, widget=None, root='/'):
        # Populates the library list with entries starting at root
        if not self.conn:
            return

        lsinfo = self.library_browse_verify(root)

        prev_selection = []
        prev_selection_root = False
        prev_selection_parent = False
        if (self.lib_view == self.VIEW_FILESYSTEM and root == self.wd) \
        or (self.lib_view != self.VIEW_FILESYSTEM and self.lib_level == self.lib_level_prev):
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

        # The logic below is more consistent with, e.g., thunar
        if (self.lib_view == self.VIEW_FILESYSTEM and len(root) > len(self.wd)) \
        or (self.lib_view != self.VIEW_FILESYSTEM and self.lib_level > self.lib_level_prev):
            # Save position and row for where we just were if we've
            # navigated into a sub-directory:
            self.libraryposition[self.wd] = self.library.get_visible_rect()[1]
            model, rows = self.library_selection.get_selected_rows()
            if len(rows) > 0:
                value_for_selection = self.librarydata.get_value(self.librarydata.get_iter(rows[0]), 2)
                if value_for_selection != ".." and value_for_selection != "/":
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

        bd = []  # will be put into librarydata later
        if self.lib_view == self.VIEW_FILESYSTEM:
            if self.wd != '/':
                bd += [('0', [self.harddiskpb, '/', '/'])]
                bd += [('1', [self.openpb, '..', '..'])]
            for item in lsinfo:
                if item.has_key('directory'):
                    name = mpdh.get(item, 'directory').split('/')[-1]
                    bd += [('d' + name.lower(), [self.openpb, mpdh.get(item, 'directory'), misc.escape_html(name)])]
                elif item.has_key('file'):
                    bd += [('f' + mpdh.get(item, 'file').lower(), [self.sonatapb, mpdh.get(item, 'file'), self.parse_formatting(self.libraryformat, item, True)])]
            bd.sort(key=misc.first_of_2tuple)
        elif self.lib_view == self.VIEW_ARTIST or self.lib_view == self.VIEW_GENRE:
            if self.lib_level == self.LIB_LEVEL_GENRE:
                self.lib_genre = ''
                self.lib_artist = ''
                self.lib_album = ''
                untagged_tag = False
                for genre in self.return_genres():
                    bd += [(misc.lower_no_the(genre), [self.genrepb, genre, misc.escape_html(genre)])]
                    if genre.lower() == self.NOTAG.lower():
                        untagged_tag = True
                # Add Untagged item if it's not already there:
                if not untagged_tag:
                    bd += [(self.NOTAG.lower(), [self.genrepb, self.NOTAG, self.NOTAG])]
                bd.sort(key=misc.first_of_2tuple)
            elif self.lib_level == self.LIB_LEVEL_ARTIST:
                if self.lib_view == self.VIEW_GENRE:
                    bd += [('0', [self.harddiskpb, '/', '/'])]
                    bd += [('1', [self.openpb, '..', '..'])]
                self.lib_artist = ''
                self.lib_album = ''
                self.lib_genre = self.wd
                untagged_tag = False
                for artist in self.return_artists():
                    bd += [(misc.lower_no_the(artist), [self.artistpb, artist, misc.escape_html(artist)])]
                    if artist.lower() == self.NOTAG.lower():
                        untagged_tag = True
                if self.lib_view == self.VIEW_ARTIST:
                    # Add Untagged item if it's not already there:
                    if not untagged_tag:
                        bd += [(self.NOTAG.lower(), [self.artistpb, self.NOTAG, self.NOTAG])]
                bd.sort(key=misc.first_of_2tuple)
            elif self.lib_level == self.LIB_LEVEL_ALBUM:
                bd += [('0', [self.harddiskpb, '/', '/'])]
                bd += [('1', [self.openpb, '..', '..'])]
                if self.wd != "..":
                    self.lib_artist = self.wd
                albums = []
                songs = []
                years = []
                dirs = []
                for item in self.return_artist_items(self.lib_artist):
                    try:
                        albums.append(mpdh.get(item, 'album'))
                        years.append(mpdh.get(item, 'date', '9999').split('-')[0].zfill(4))
                    except:
                        songs.append(item)
                    dirs.append(os.path.dirname(mpdh.get(item, 'file')))
                (albums, years, dirs) = misc.remove_list_duplicates(albums, years, dirs, False)
                for i in range(len(albums)):
                    coverfile = self.library_get_album_cover(dirs[i], self.lib_artist, albums[i])
                    if years[i] == '9999':
                        bd += [('d' + years[i] + misc.lower_no_the(albums[i]), [coverfile, years[i] + albums[i], misc.escape_html(albums[i])])]
                    else:
                        bd += [('d' + years[i] + misc.lower_no_the(albums[i]), [coverfile, years[i] + albums[i], misc.escape_html(years[i] + ' - ' + albums[i])])]
                for song in songs:
                    try:
                        bd += [('f' + misc.lower_no_the(mpdh.get(song, 'title')), [self.sonatapb, mpdh.get(song, 'file'), self.parse_formatting(self.libraryformat, song, True)])]
                    except:
                        bd += [('f' + mpdh.get(song, 'file').lower(), [self.sonatapb, mpdh.get(song, 'file'), self.parse_formatting(self.libraryformat, song, True)])]
                bd.sort(key=misc.first_of_2tuple)
            else: # Songs in albums
                bd += [('0', [self.harddiskpb, '/', '/'])]
                bd += [('1', [self.openpb, '..', '..'])]
                (self.lib_album, year) = self.library_album_and_year_from_path(root)
                for item in self.return_album_items_with_artist_and_year(self.lib_artist, self.lib_album, year):
                    num = mpdh.getnum(item, 'disc', '1', False, 2) + mpdh.getnum(item, 'track', '1', False, 2)
                    bd += [('f' + num, [self.sonatapb, mpdh.get(item, 'file'), self.parse_formatting(self.libraryformat, item, True)])]
                # List already sorted in return_album_items_with_artist_and_year...

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

    def library_get_album_cover(self, dir, artist, album):
        tmp, coverfile = self.artwork_get_local_image(dir, artist, album)
        if coverfile:
            coverfile = gtk.gdk.pixbuf_new_from_file_at_size(coverfile, self.LIB_COVER_SIZE, self.LIB_COVER_SIZE)
            w = coverfile.get_width()
            h = coverfile.get_height()
            coverfile = self.artwork_apply_composite_case(coverfile, w, h)
        else:
            # Revert to standard album cover:
            coverfile = self.albumpb
        return coverfile

    def return_genres(self):
        # Returns all genres in alphabetical order
        list = []
        for item in self.client.list('genre'):
            list.append(item)
        (list, tmp, tmp2) = misc.remove_list_duplicates(list, case=False)
        list.sort(locale.strcoll)
        return list

    def return_genre_items(self, search_genre=None):
        # Returns all songs of the specified genre. Sorts by disc and
        # track number.
        if search_genre:
            genre = search_genre
        else:
            genre = self.lib_genre
        untagged_genre = (genre == self.NOTAG)
        list = []
        if not untagged_genre:
            for item in self.client.search('genre', genre):
                # Make sure it's an exact match:
                if genre.lower() == mpdh.get(item, 'genre').lower():
                    list.append(item)
        else:
            for item in self.client.listallinfo('/'):
                if item.has_key('file'):
                    if not item.has_key('genre'):
                        list.append(item)
                    elif mpdh.get(item, 'genre') == self.NOTAG:
                        list.append(item)
        return list

    def return_artists(self, use_genre_if_genre_view=True):
        # Returns all artists in alphabetical order
        use_genre = (use_genre_if_genre_view and self.lib_view == self.VIEW_GENRE)
        untagged_genre = (self.lib_genre == self.NOTAG)
        if use_genre:
            list = []
            if not untagged_genre:
                for item in self.client.search('genre', self.lib_genre):
                    if item.has_key('artist'):
                        # Make sure it's an exact match:
                        if self.lib_genre.lower() == mpdh.get(item, 'genre').lower():
                            list.append(mpdh.get(item, 'artist'))
            else:
                for item in self.client.listallinfo('/'):
                    if item.has_key('file') and item.has_key('artist'):
                        if not item.has_key('genre'):
                            list.append(mpdh.get(item, 'artist'))
                        elif mpdh.get(item, 'genre') == self.NOTAG:
                            list.append(mpdh.get(item, 'artist'))
            (list, tmp, tmp2) = misc.remove_list_duplicates(list, case=False)
            list.sort(locale.strcoll)
            return list
        else:
            list = []
            for item in self.client.list('artist'):
                list.append(item)
            (list, tmp, tmp2) = misc.remove_list_duplicates(list, case=False)
            list.sort(locale.strcoll)
            return list

    def return_album_items(self, album, use_genre_if_genre_view=True):
        # Return songs of the specified album. Sorts by disc and track number
        # If we are in genre view, make sure items match the genre too.
        list = []
        use_genre = (use_genre_if_genre_view and self.lib_view == self.VIEW_GENRE)
        untagged_genre = (self.lib_genre == self.NOTAG)
        if use_genre and not untagged_genre:
            items = self.client.search('album', album, 'genre', self.lib_genre)
        else:
            items = self.client.search('album', album)
        for item in items:
            # Make sure it's an exact match:
            if album.lower() == mpdh.get(item, 'album').lower():
                if not untagged_genre:
                    if not use_genre or (use_genre and self.lib_genre.lower() == mpdh.get(item, 'genre').lower()):
                        list.append(item)
                else:
                    if item.has_key('file'):
                        if not item.has_key('genre'):
                            list.append(item)
                        elif mpdh.get(item, 'genre') == self.NOTAG:
                            list.append(item)
        list.sort(key=lambda x: int(mpdh.getnum(x, 'disc', '0', False, 2) + mpdh.getnum(x, 'track', '0', False, 2)))
        return list

    def return_artist_items(self, artist, use_genre_if_genre_view=True):
        # Return albums/songs of the specified artist. Sorts by year
        # If we are in genre view, make sure items match the genre too.
        list = []
        use_genre = (use_genre_if_genre_view and self.lib_view == self.VIEW_GENRE)
        untagged_genre = (self.lib_genre == self.NOTAG)
        untagged_artist = (artist == self.NOTAG)
        if not untagged_artist:
            items = self.client.search('artist', artist)
        else:
            items = self.client.listallinfo('/')
        for item in items:
            if untagged_artist:
                if item.has_key('file'):
                    if not item.has_key('artist'):
                        list.append(item)
                    elif mpdh.get(item, 'artist') == self.NOTAG:
                        list.append(item)
            else:
                # Make sure it's an exact match:
                if artist.lower() == mpdh.get(item, 'artist').lower():
                    if not untagged_genre:
                        if not use_genre or (use_genre and self.lib_genre.lower() == mpdh.get(item, 'genre').lower()):
                            list.append(item)
                    elif not untagged_artist:
                        if item.has_key('file'):
                            if not item.has_key('genre'):
                                list.append(item)
                            elif mpdh.get(item, 'genre') == self.NOTAG:
                                list.append(item)
        list.sort(key=lambda x: mpdh.get(x, 'date', '0').split('-')[0].zfill(4))
        return list

    def return_album_items_with_artist_and_year(self, artist, album, year, use_genre_if_genre_view=True):
        # Return songs of specified album, artist, and year. Sorts by disc and
        # track num.
        # If year is None, skips that requirement
        # If we are in genre view, make sure items match the genre too.
        list = []
        use_genre = (use_genre_if_genre_view and self.lib_view == self.VIEW_GENRE)
        untagged_genre = (self.lib_genre == self.NOTAG)
        untagged_artist = (artist == self.NOTAG)
        if use_genre and not untagged_genre and not untagged_artist:
            items = self.client.search('album', album, 'artist', artist, 'genre', self.lib_genre)
        elif not untagged_artist:
            items = self.client.search('album', album, 'artist', artist)
        else:
            items = self.client.search('album', album)
        for item in items:
            match = False
            if untagged_artist:
                if item.has_key('file'):
                    if not item.has_key('artist'):
                        match = True
                    elif mpdh.get(item, 'artist') == self.NOTAG:
                        match = True
            else:
                # Make sure it's an exact match:
                if artist.lower() == mpdh.get(item, 'artist').lower() and album.lower() == mpdh.get(item, 'album').lower():
                    if not untagged_genre:
                        if not use_genre or (use_genre and self.lib_genre.lower() == mpdh.get(item, 'genre').lower()):
                            match = True
                    else:
                        if item.has_key('file'):
                            if not item.has_key('genre'):
                                match = True
                            elif mpdh.get(item, 'genre') == self.NOTAG:
                                match = True
            if match:
                if year is None:
                    list.append(item)
                else:
                    # Make sure it also matches the year:
                    if year != '9999' and item.has_key('date'):
                        # Only show songs whose years match the year var:
                        try:
                            if int(mpdh.get(item, 'date').split('-')[0]) == int(year):
                                list.append(item)
                        except:
                            pass
                    elif year == '9999' and not item.has_key('date'):
                        # Only show songs that have no year specified:
                        list.append(item)
        list.sort(key=lambda x: int(mpdh.getnum(x, 'disc', '0', False, 2) + mpdh.getnum(x, 'track', '0', False, 2)))
        return list

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

        # Select and focus previously selected item if it's not ".." or "/"
        if select_items:
            if self.lib_view == self.VIEW_ARTIST:
                if self.lib_level == self.LIB_LEVEL_ARTIST:
                    item = "/"
                elif self.lib_level == self.LIB_LEVEL_ALBUM:
                    item = self.lib_artist
                else:
                    return
            elif self.lib_view == self.VIEW_GENRE:
                if self.lib_level == self.LIB_LEVEL_GENRE:
                    item = "/"
                elif self.lib_level == self.LIB_LEVEL_ARTIST:
                    item = self.lib_genre
                elif self.lib_level == self.LIB_LEVEL_ALBUM:
                    item = self.lib_artist
                else:
                    return
            else:
                item = self.wd
            if item in self.libraryselectedpath:
                try:
                    if self.libraryselectedpath[item]:
                        self.library_selection.select_path(self.libraryselectedpath[item])
                        self.library.grab_focus()
                except:
                    pass

    def library_album_and_year_from_path(self, path):
        # The first four chars are used to store the year. Returns
        # a tuple.
        year = path[:4]
        album = path[4:]
        return (album, year)

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
                        return misc.escape_html(item['file'])
                    else:
                        # Use file name only:
                        return misc.escape_html(item['file'].split('/')[-1])
                else:
                    return ""
        if "%N" in text:
            track = mpdh.getnum(item, 'track', flag, False, 2)
            if track != flag:
                text = text.replace("%N", track)
            else:
                if not has_brackets: text = text.replace("%N", "0")
                else: return ""
        if "%D" in text:
            disc = mpdh.getnum(item, 'disc', flag, False, 0)
            if disc != flag:
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
                        year = []
                        albumtime = 0
                        trackinfo = ""
                        albuminfo = mpdh.get(self.songinfo, 'album') + "\n"
                        tracks = self.return_album_items(mpdh.get(self.songinfo, 'album'), False)
                        if len(tracks) > 0:
                            for track in tracks:
                                if os.path.dirname(mpdh.get(self.songinfo, 'file')) == os.path.dirname(mpdh.get(track, 'file')):
                                    if track.has_key('title'):
                                        trackinfo = trackinfo + mpdh.getnum(track, 'track', '0', False, 2) + '. ' + mpdh.get(track, 'title') + '\n'
                                    else:
                                        trackinfo = trackinfo + mpdh.getnum(track, 'track', '0', False, 2) + '. ' + mpdh.get(track, 'file').split('/')[-1] + '\n'
                                    if track.has_key('date'):
                                        year.append(mpdh.get(track, 'date'))
                                    try:
                                        albumtime = albumtime + int(mpdh.get(track, 'time'))
                                    except:
                                        pass
                            (year, tmp, tmp2) = misc.remove_list_duplicates(year, case=False)
                            artist = self.album_current_artist[1]
                            artist_use_link = False
                            if artist != _("Various Artists"):
                                artist_use_link = True
                            albuminfo = albuminfo + artist + "\n"
                            if len(year) == 1:
                                albuminfo = albuminfo + year[0] + "\n"
                            albuminfo = albuminfo + misc.convert_time(albumtime) + "\n"
                            albuminfo = albuminfo + "\n" + trackinfo
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
        if blank_window:
            newtime = ''
            newbitrate = ''
            for label in self.info_labels:
                label.set_text("")
            self.info_editlabel.set_text("")
            if self.show_lyrics:
                self.info_searchlabel.set_text("")
                self.info_show_lyrics("", "", "", True)
            self.albumText.set_text("")
            self.last_info_bitrate = newbitrate

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
            # Strip artist - filename line from file if it exists, since we
            # now have that information visible elsewhere.
            header = filename_artist + " - " + filename_title + "\n\n"
            if lyrics[:len(header)] == header:
                lyrics = lyrics[len(header):]
            gobject.idle_add(self.info_show_lyrics, lyrics, filename_artist, filename_title)
            gobject.idle_add(self.info_searchlabel.set_markup, search_str)
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
                    self.lyricServer = ServiceProxy.ServiceProxy(wsdlFile)
                except:
                    socketsettimeout(timeout)
                    lyrics = _("Couldn't connect to LyricWiki")
                    gobject.idle_add(self.info_show_lyrics, lyrics, filename_artist, filename_title)
                    self.lyricServer = None
                    gobject.idle_add(self.info_searchlabel.set_markup, search_str)
                    return
            try:
                timeout = socketgettimeout()
                socketsettimeout(self.LYRIC_TIMEOUT)
                lyrics = self.lyricServer.getSong(artist=urllib.quote(search_artist), song=urllib.quote(search_title))['return']["lyrics"]
                if lyrics.lower() != "not found":
                    lyrics = filename_artist + " - " + filename_title + "\n\n" + lyrics
                    lyrics = misc.unescape_html(lyrics)
                    lyrics = misc.wiki_to_html(lyrics)
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
        elif value == "..":
            self.library_browse_parent(None)
        else:
            if self.lib_view == self.VIEW_ARTIST or self.lib_view == self.VIEW_GENRE:
                if value == "/":
                    if self.lib_view == self.VIEW_ARTIST:
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
                    if self.lib_view == self.VIEW_ARTIST:
                        if self.lib_level > self.LIB_LEVEL_ARTIST:
                            self.lib_level -= 1
                        if self.lib_level == self.LIB_LEVEL_ARTIST:
                            value = "/"
                        else:
                            value = self.lib_artist
                    elif self.lib_view == self.VIEW_GENRE:
                        if self.lib_level > self.LIB_LEVEL_GENRE:
                            self.lib_level -= 1
                        if self.lib_level == self.LIB_LEVEL_GENRE:
                            value = "/"
                        elif self.lib_level == self.LIB_LEVEL_ARTIST:
                            value = self.lib_genre
                        elif self.lib_level == self.LIB_LEVEL_ALBUM:
                            value = self.lib_artist
                    else:
                        value = '/'.join(self.wd.split('/')[:-1]) or '/'
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
        if self.on_button_press(widget, event,	False): return True

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

    def library_get_recursive_filenames(self, return_root):
        # If return_root=True, return main directories whenever possible
        # instead of individual songs in order to reduce the number of
        # mpd calls we need to make. We won't want this behavior in some
        # instances, like when we want all end files for editing tags
        items = []
        model, selected = self.library_selection.get_selected_rows()
        if self.lib_view == self.VIEW_FILESYSTEM or self.library_search_visible():
            if return_root and not self.library_search_visible() and ((self.wd == "/" and len(selected) == len(model)) or (self.wd != "/" and len(selected) >= len(model)-2)):
                # Everything selected, this is faster..
                items.append(self.wd)
            else:
                for path in selected:
                    while gtk.events_pending():
                        gtk.main_iteration()
                    if model.get_value(model.get_iter(path), 2) != "/" and model.get_value(model.get_iter(path), 2) != "..":
                        if model.get_value(model.get_iter(path), 0) == self.openpb:
                            if return_root and not self.library_search_visible():
                                items.append(model.get_value(model.get_iter(path), 1))
                            else:
                                for item in self.client.listall(model.get_value(model.get_iter(path), 1)):
                                    if item.has_key('file'):
                                        items.append(mpdh.get(item, 'file'))
                        else:
                            items.append(model.get_value(model.get_iter(path), 1))
        elif self.lib_view == self.VIEW_ARTIST or (self.VIEW_GENRE and self.lib_level > self.LIB_LEVEL_GENRE):
            # lib_level > 0 in genre view is equivalent to one of the
            # artist view levels:
            for path in selected:
                while gtk.events_pending():
                    gtk.main_iteration()
                if model.get_value(model.get_iter(path), 2) != "/" and model.get_value(model.get_iter(path), 2) != "..":
                    if self.lib_level == self.LIB_LEVEL_ARTIST:
                        for item in self.return_artist_items(model.get_value(model.get_iter(path), 1)):
                            items.append(mpdh.get(item, 'file'))
                    else:
                        if model.get_value(model.get_iter(path), 0) != self.sonatapb:
                            (album, year) = self.library_album_and_year_from_path(model.get_value(model.get_iter(path), 1))
                            for item in self.return_album_items_with_artist_and_year(self.lib_artist, album, year):
                                items.append(mpdh.get(item, 'file'))
                        else:
                            items.append(model.get_value(model.get_iter(path), 1))
        elif self.lib_view == self.VIEW_GENRE:
            for path in selected:
                while gtk.events_pending():
                    gtk.main_iteration()
                genre = model.get_value(model.get_iter(path), 1)
                for item in self.return_genre_items(genre):
                    items.append(mpdh.get(item, 'file'))
        # Make sure we don't have any EXACT duplicates:
        (items, tmp, tmp2) = misc.remove_list_duplicates(items, case=True)
        return items

    def on_add_item_play(self, widget):
        self.on_add_item(widget, True)

    def on_add_item(self, widget, play_after=False):
        if self.conn:
            if play_after and self.status:
                playid = self.status['playlistlength']
            if self.current_tab == self.TAB_LIBRARY:
                items = self.library_get_recursive_filenames(True)
                self.client.command_list_ok_begin()
                for item in items:
                    self.client.add(item)
                self.client.command_list_end()
            elif self.current_tab == self.TAB_PLAYLISTS:
                model, selected = self.playlists_selection.get_selected_rows()
                for path in selected:
                    self.client.load(misc.unescape_html(model.get_value(model.get_iter(path), 1)))
            elif self.current_tab == self.TAB_STREAMS:
                model, selected = self.streams_selection.get_selected_rows()
                for path in selected:
                    item = model.get_value(model.get_iter(path), 2)
                    self.stream_parse_and_add(item)
            self.iterate_now()
            if play_after:
                self.client.play(int(playid))

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
                self.client.add(item)
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
                    self.client.add(item)
        else:
            # Hopefully just a regular stream, try to add it:
            self.client.add(item)

    def stream_parse_pls(self, f):
        lines = f.split("\n")
        for line in lines:
            line = line.replace('\r','')
            delim = line.find("=")+1
            if delim > 0:
                line = line[delim:]
                if len(line) > 7 and line[0:7] == 'http://':
                    self.client.add(line)
                elif len(line) > 6 and line[0:6] == 'ftp://':
                    self.client.add(line)

    def stream_parse_m3u(self, f):
        lines = f.split("\n")
        for line in lines:
            line = line.replace('\r','')
            if len(line) > 7 and line[0:7] == 'http://':
                self.client.add(line)
            elif len(line) > 6 and line[0:6] == 'ftp://':
                self.client.add(line)

    def on_replace_item_play(self, widget):
        self.on_replace_item(widget, True)

    def on_replace_item(self, widget, play_after=False):
        play_after_replace = False
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
            self.artwork_update()
            self.update_statusbar()
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

            self.artwork_update()
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
                self.tooltips.set_tip(self.volumebutton, self.status['volume'] + "%")
            except:
                pass

        if self.conn:
            if self.status and self.status.get('updating_db'):
                # MPD library is being updated
                self.update_statusbar(True)
            elif self.prevstatus == None or self.prevstatus.get('updating_db', 0) != self.status.get('updating_db', 0):
                if not (self.status and self.status.get('updating_db', 0)):
                    # Update over:
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
                if not self.prevstatus or (self.prevstatus and self.prevstatus['state'] == 'stop'):
                    # Switched from stop to play, prepare current track:
                    self.scrobbler_prepare()
                elif self.prevsonginfo and self.prevsonginfo.has_key('time') and self.scrob_last_prepared != mpdh.get(self.songinfo, 'file'):
                    # New song is playing, post previous track if time criteria is met:
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
                    gobject.idle_add(self.current_center_song_in_list)
            self.prev_boldrow = row

        self.album_get_artist()

        self.update_cursong()
        self.update_wintitle()
        self.artwork_update()
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
        if self.filterbox_visible:
            return
        if row > -1:
            try:
                for i in range(len(self.currentdata[row]) - 1):
                    self.currentdata[row][i + 1] = misc.bold(self.currentdata[row][i + 1])
            except:
                pass

    def unbold_boldrow(self, row):
        if self.filterbox_visible:
            return
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
                    if days:
                        status_text = str(self.status['playlistlength']) + ' ' + songs_text + '   ' + days + ' ' + days_text + ', ' + hours + ' ' + hours_text + ', ' + _('and') + ' ' + mins + ' ' + mins_text
                    elif hours:
                        status_text = str(self.status['playlistlength']) + ' ' + songs_text + '   ' + hours + ' ' + hours_text + ' ' + _('and') + ' ' + mins + ' ' + mins_text
                    elif mins:
                        status_text = str(self.status['playlistlength']) + ' ' + songs_text + '   ' + mins + ' ' + mins_text
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

            newlabelfound = False
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
            self.tooltips.set_tip(self.expander, self.cursonglabel1.get_text() + "\n" + self.cursonglabel2.get_text())
        else:
            for label in (self.cursonglabel1, self.cursonglabel2, self.traycursonglabel1, self.cursonglabel2):
                label.set_ellipsize(pango.ELLIPSIZE_NONE)

            self.cursonglabel1.set_markup('<big><b>' + _('Stopped') + '</b></big>')
            if self.expanded:
                self.cursonglabel2.set_markup('<small>' + _('Click to collapse') + '</small>')
            else:
                self.cursonglabel2.set_markup('<small>' + _('Click to expand') + '</small>')
            self.tooltips.set_tip(self.expander, self.cursonglabel1.get_text())
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
                newtitle = 'Sonata'
            if not self.last_title or self.last_title != newtitle:
                self.window.set_property('title', newtitle)
                self.last_title = newtitle

    def current_update(self):
        if self.conn:
            try:
                prev_songs = self.songs
            except:
                prev_songs = None
            self.songs = self.client.playlistinfo()
            self.total_time = 0
            if self.sonata_loaded:
                playlistposition = self.current.get_visible_rect()[1]
            self.current.freeze_child_notify()
            if not self.filterbox_visible:
                self.current.set_model(None)
            songlen = len(self.songs)
            currlen = len(self.currentdata)
            # Add/update songs in current playlist:
            for i in range(songlen):
                track = self.songs[i]
                try:
                    self.total_time = self.total_time + int(mpdh.get(track, 'time'))
                except:
                    pass
                iter = None
                if i < currlen and prev_songs:
                    iter = self.currentdata.get_iter((i, ))
                update_item = False
                items = []
                for part in self.columnformat:
                    items += [self.parse_formatting(part, track, True)]
                if i < currlen and iter:
                    # Update attributes only for item:
                    self.currentdata.set_value(iter, 0, int(mpdh.get(track, 'id')))
                    for index in range(len(items)):
                        self.currentdata.set_value(iter, index + 1, items[index])
                else:
                    # Add new item:
                    self.currentdata.append([int(mpdh.get(track, 'id'))] + items)
            # Remove excess songs:
            for i in range(currlen-songlen):
                iter = self.currentdata.get_iter((currlen-1-i,))
                self.currentdata.remove(iter)
            if not self.filterbox_visible:
                self.current.set_model(self.currentdata)
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

    def on_reset_image(self, action):
        if self.songinfo:
            if self.songinfo.has_key('name'):
                # Stream, remove file:
                misc.remove_file(self.artwork_stream_filename(mpdh.get(self.songinfo, 'name')))
            else:
                # Normal song:
                misc.remove_file(self.target_image_filename(self.ART_LOCATION_HOMECOVERS))
                self.artwork_create_none_file()
            self.artwork_update(True)

    def artwork_set_tooltip_art(self, pix):
        pix1 = pix.subpixbuf(0, 0, 51, 77)
        pix2 = pix.subpixbuf(51, 0, 26, 77)
        self.trayalbumimage1.set_from_pixbuf(pix1)
        self.trayalbumimage2.set_from_pixbuf(pix2)
        del pix1
        del pix2

    def artwork_update(self, force=False):
        if force:
            self.lastalbumart = None
        self.stop_art_update = True
        thread = threading.Thread(target=self._artwork_update)
        thread.setDaemon(True)
        thread.start()

    def _artwork_update(self):
        self.stop_art_update = False
        if not self.show_covers:
            return
        if not self.songinfo:
            self.artwork_set_default_icon()
            return
        if self.conn and self.status and self.status['state'] in ['play', 'pause']:
            if self.songinfo.has_key('name'):
                # Stream
                streamfile = self.artwork_stream_filename(mpdh.get(self.songinfo, 'name'))
                if os.path.exists(streamfile):
                    gobject.idle_add(self.artwork_set_image, streamfile)
                else:
                    self.artwork_set_default_icon()
                    return
            else:
                # Normal song:
                artist = mpdh.get(self.songinfo, 'artist', "")
                album = mpdh.get(self.songinfo, 'album', "")
                if len(artist) == 0 and len(album) == 0:
                    self.artwork_set_default_icon()
                    return
                filename = self.target_image_filename()
                if filename == self.lastalbumart:
                    # No need to update..
                    self.stop_art_update = False
                    return
                self.lastalbumart = None
                if os.path.exists(self.target_image_filename(self.ART_LOCATION_NONE)):
                    self.artwork_set_default_icon()
                    return
                imgfound = self.artwork_check_for_local()
                if not imgfound:
                    if self.covers_pref == self.ART_LOCAL_REMOTE:
                        imgfound = self.artwork_check_for_remote(artist, album, filename)
        else:
            self.artwork_set_default_icon()

    def artwork_stream_filename(self, streamname):
        return os.path.expanduser('~/.covers/') + streamname.replace("/", "") + ".jpg"

    def artwork_create_none_file(self):
        # If this file exists, Sonata will use the "blank" default artwork for the song
        # We will only use this if the user explicitly resets the artwork.
        filename = self.target_image_filename(self.ART_LOCATION_NONE)
        f = open(filename, 'w')
        f.close()

    def artwork_check_for_local(self):
        songdir = os.path.dirname(mpdh.get(self.songinfo, 'file'))
        self.artwork_set_default_icon()
        self.misc_img_in_dir = None
        self.single_img_in_dir = None
        type, filename = self.artwork_get_local_image()

        if type is not None and filename:
            if type == self.ART_LOCATION_MISC:
                self.misc_img_in_dir = filename
            elif type == self.ART_LOCATION_SINGLE:
                self.single_img_in_dir = filename
            gobject.idle_add(self.artwork_set_image, filename)
            return True

        return False

    def artwork_get_local_image(self, songpath=None, artist=None, album=None):
        # Returns a tuple (location_type, filename) or (None, None).
        # Only pass a songpath, artist, and album if we don't want
        # to use info from the currently playing song.

        if songpath is None:
            songpath = os.path.dirname(mpdh.get(self.songinfo, 'file'))

        # Give precedence to images defined by the user's current
        # self.art_location (in case they have multiple valid images
        # that can be used for cover art).
        testfile = self.target_image_filename(None, songpath, artist, album)
        if os.path.exists(testfile):
            return self.art_location, testfile

        # Now try all local possibilities...
        testfile = self.target_image_filename(self.ART_LOCATION_HOMECOVERS, songpath, artist, album)
        if os.path.exists(testfile):
            return self.ART_LOCATION_HOMECOVERS, testfile
        testfile = self.target_image_filename(self.ART_LOCATION_COVER, songpath, artist, album)
        if os.path.exists(testfile):
            return self.ART_LOCATION_COVER, testfile
        testfile = self.target_image_filename(self.ART_LOCATION_ALBUM, songpath, artist, album)
        if os.path.exists(testfile):
            return self.ART_LOCATION_ALBUM, testfile
        testfile = self.target_image_filename(self.ART_LOCATION_FOLDER, songpath, artist, album)
        if os.path.exists(testfile):
            return self.ART_LOCATION_FOLDER, testfile
        testfile = self.target_image_filename(self.ART_LOCATION_CUSTOM, songpath, artist, album)
        if self.art_location == self.ART_LOCATION_CUSTOM and len(self.art_location_custom_filename) > 0 and os.path.exists(testfile):
            return self.ART_LOCATION_CUSTOM, testfile
        if self.artwork_get_misc_img_in_path(songpath):
            return self.ART_LOCATION_MISC, self.artwork_get_misc_img_in_path(songpath)
        testfile = img.single_image_in_dir(self.musicdir[self.profile_num] + songpath)
        if testfile is not None:
            return self.ART_LOCATION_SINGLE, testfile
        return None, None

    def artwork_check_for_remote(self, artist, album, filename):
        self.artwork_set_default_icon()
        self.artwork_download_img_to_file(artist, album, filename)
        if os.path.exists(filename):
            gobject.idle_add(self.artwork_set_image, filename)
            return True
        return False

    def artwork_set_default_icon(self):
        if self.albumimage.get_property('file') != self.sonatacd:
            gobject.idle_add(self.albumimage.set_from_file, self.sonatacd)
            gobject.idle_add(self.info_image.set_from_file, self.sonatacd_large)
        gobject.idle_add(self.artwork_set_tooltip_art, gtk.gdk.pixbuf_new_from_file(self.sonatacd))
        self.lastalbumart = None

    def artwork_get_misc_img_in_path(self, songdir):
        path = misc.file_from_utf8(self.musicdir[self.profile_num] + songdir)
        if os.path.exists(path):
            for f in self.ART_LOCATIONS_MISC:
                filename = path + "/" + f
                if os.path.exists(filename):
                    return filename
        return False

    def artwork_set_image(self, filename, info_img_only=False):
        # Note: filename arrives here is in FILESYSTEM_CHARSET, not UTF-8!
        if self.artwork_is_for_playing_song(filename):
            if os.path.exists(filename):
                # We use try here because the file might exist, but might
                # still be downloading
                try:
                    pix = gtk.gdk.pixbuf_new_from_file(filename)
                    # Artwork for tooltip, left-top of player:
                    if not info_img_only:
                        (pix1, w, h) = img.get_pixbuf_of_size(pix, 75)
                        pix1 = self.artwork_apply_composite_case(pix1, w, h)
                        pix1 = img.pixbuf_add_border(pix1)
                        pix1 = img.pixbuf_pad(pix1, 77, 77)
                        self.albumimage.set_from_pixbuf(pix1)
                        self.artwork_set_tooltip_art(pix1)
                        del pix1
                    # Artwork for info tab:
                    if self.info_imagebox.get_size_request()[0] == -1:
                        fullwidth = self.notebook.get_allocation()[2] - 50
                        (pix2, w, h) = img.get_pixbuf_of_size(pix, fullwidth)
                    else:
                        (pix2, w, h) = img.get_pixbuf_of_size(pix, 150)
                    pix2 = self.artwork_apply_composite_case(pix2, w, h)
                    pix2 = img.pixbuf_add_border(pix2)
                    self.info_image.set_from_pixbuf(pix2)
                    del pix, pix2
                    # Artwork for albums in the library tab
                    if not info_img_only and not self.library_search_visible():
                        if self.lib_level == self.LIB_LEVEL_ALBUM:
                            if self.lib_view == self.VIEW_ARTIST or self.lib_view == self.VIEW_GENRE:
                                if self.songinfo and self.songinfo.has_key('artist'):
                                    if self.wd == mpdh.get(self.songinfo, 'artist'):
                                        self.library_browse(root=self.wd)
                    self.lastalbumart = filename
                except:
                    pass
                self.call_gc_collect = True

    def artwork_apply_composite_case(self, pix, w, h):
        if self.covers_type == self.COVERS_TYPE_STYLIZED and float(w)/h > 0.5:
            # Rather than merely compositing the case on top of the artwork, we will
            # scale the artwork so that it isn't covered by the case:
            spine_ratio = float(60)/600 # From original png
            spine_width = int(w * spine_ratio)
            case = self.casepb.scale_simple(w, h, gtk.gdk.INTERP_BILINEAR)
            # Scale pix and shift to the right on a transparent pixbuf:
            pix = pix.scale_simple(w-spine_width, h, gtk.gdk.INTERP_BILINEAR)
            blank = gtk.gdk.Pixbuf(gtk.gdk.COLORSPACE_RGB, True, 8, w, h)
            blank.fill(0x00000000)
            pix.copy_area(0, 0, pix.get_width(), pix.get_height(), blank, spine_width, 0)
            # Composite case and scaled pix:
            case.composite(blank, 0, 0, w, h, 0, 0, 1, 1, gtk.gdk.INTERP_BILINEAR, 250)
            del case
            return blank
        return pix

    def artwork_is_for_playing_song(self, filename):
        # Since there can be multiple threads that are getting album art,
        # this will ensure that only the artwork for the currently playing
        # song is displayed
        if self.conn and self.status and self.status['state'] in ['play', 'pause'] and self.songinfo:
            if self.songinfo.has_key('name'):
                streamfile = self.artwork_stream_filename(mpdh.get(self.songinfo, 'name'))
                if filename == streamfile:
                    return True
            else:
                # Normal song:
                if filename == self.target_image_filename(self.ART_LOCATION_HOMECOVERS):
                    return True
                if filename == self.target_image_filename(self.ART_LOCATION_COVER):
                    return True
                if filename == self.target_image_filename(self.ART_LOCATION_ALBUM):
                    return True
                if filename == self.target_image_filename(self.ART_LOCATION_FOLDER):
                    return True
                if filename == self.target_image_filename(self.ART_LOCATION_CUSTOM):
                    return True
                if self.misc_img_in_dir and filename == self.misc_img_in_dir:
                    return True
                if self.single_img_in_dir and filename == self.single_img_in_dir:
                    return True
        # If we got this far, no match:
        return False

    def artwork_download_img_to_file(self, artist, album, dest_filename, all_images=False):
        global ElementTree
        if ElementTree is None:
            try: # Python 2.5, module bundled:
                from xml.etree import ElementTree
            except:
                try: # Python 2.4, separate module:
                    from elementtree.ElementTree import ElementTree
                except:
                    sys.stderr.write("Sonata requires Python 2.5 or python-elementtree. Aborting... \n")
                    sys.exit(1)
        # Returns False if no images found
        if len(artist) == 0 and len(album) == 0:
            self.downloading_image = False
            return False
        #try:
        img_url = ""
        self.downloading_image = True
        # Amazon currently doesn't support utf8 and suggests latin1 encoding instead:
        try:
            artist = urllib.quote(artist.encode('latin1'))
            album = urllib.quote(album.encode('latin1'))
        except:
            artist = urllib.quote(artist)
            album = urllib.quote(album)
        amazon_key = "12DR2PGAQT303YTEWP02"
        prefix = "{http://webservices.amazon.com/AWSECommerceService/2005-10-05}"
        search_url = "http://webservices.amazon.com/onca/xml?Service=AWSECommerceService&AWSAccessKeyId=" + amazon_key + "&Operation=ItemSearch&SearchIndex=Music&Artist=" + artist + "&ResponseGroup=Images&Keywords=" + album
        request = urllib2.Request(search_url)
        opener = urllib2.build_opener()
        f = opener.open(request).read()
        xml = ElementTree.fromstring(f)
        largeimgs = xml.getiterator(prefix + "LargeImage")
        if len(largeimgs) == 0:
            # No search results returned, search again with just artist name:
            search_url = "http://webservices.amazon.com/onca/xml?Service=AWSECommerceService&AWSAccessKeyId=" + amazon_key + "&Operation=ItemSearch&SearchIndex=Music&Artist=" + artist + "&ResponseGroup=Images"
            request = urllib2.Request(search_url)
            opener = urllib2.build_opener()
            f = opener.open(request).read()
            xml = ElementTree.fromstring(f)
            largeimgs = xml.getiterator(prefix + "LargeImage")
            if len(largeimgs) == 0:
                self.downloading_image = False
                return False
        imglist = []
        for largeimg in largeimgs:
            for url in largeimg.getiterator(prefix + "URL"):
                if not url.text in imglist:
                    imglist.append(url.text)
        if not all_images:
            urllib.urlretrieve(imglist[0], dest_filename)
            self.downloading_image = False
            return True
        else:
            try:
                imgfound = False
                for i in range(len(imglist)):
                    dest_filename_curr = dest_filename.replace("<imagenum>", str(i+1))
                    urllib.urlretrieve(imglist[i], dest_filename_curr)
                    # This populates self.imagelist for the remote image window
                    if os.path.exists(dest_filename_curr):
                        pix = gtk.gdk.pixbuf_new_from_file(dest_filename_curr)
                        pix = pix.scale_simple(148, 148, gtk.gdk.INTERP_HYPER)
                        pix = self.artwork_apply_composite_case(pix, 148, 148)
                        pix = img.pixbuf_add_border(pix)
                        if self.stop_art_update:
                            del pix
                            self.downloading_image = False
                            return imgfound
                        self.imagelist.append([i+1, pix])
                        del pix
                        imgfound = True
                        self.remotefilelist.append(dest_filename_curr)
                        if i == 0:
                            self.allow_art_search = True
                    ui.change_cursor(None)
            except:
                pass
            self.downloading_image = False
            return imgfound

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
                        self.traytips.use_notifications_location = True
                        if HAVE_STATUS_ICON and self.statusicon.is_embedded() and self.statusicon.get_visible():
                            self.traytips._real_display(self.statusicon)
                        elif HAVE_EGG and self.trayicon.get_property('visible') == True:
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
                info_file.write('Shuffle: ' + self.status['random'] + '\n')
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
            elif HAVE_EGG and self.trayicon.get_property('visible') == True:
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

    def current_columns_resize(self):
        if not self.withdrawn and self.expanded and len(self.columns) > 1:
            self.resizing_columns = True
            width = self.window.allocation.width
            for i, column in enumerate(self.columns):
                try:
                    newsize = int(round(self.colwidthpercents[i]*width))
                    if newsize == 0:
                        # self.colwidthpercents has not yet been set, don't resize...
                        self.resizing_columns = False
                        return
                    newsize = max(newsize, 10)
                except:
                    newsize = 150
                if newsize != column.get_fixed_width():
                    column.set_fixed_width(newsize)
            self.resizing_columns = False

    def on_notebook_resize(self, widget, event):
        if not self.resizing_columns :
            self.current_columns_resize()
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
                    progressbarsize = self.progressbar.allocation
                    seektime = int((event.x/progressbarsize.width) * length)
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
            if len(self.songs) == 0:
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

            for track in self.songs:
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
            self.client.command_list_ok_begin()
            for item in list:
                self.client.moveid(item["id"], pos)
                pos += 1
            self.client.command_list_end()
            self.iterate_now()

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
            if len(self.songs) == 0:
                return
            while gtk.events_pending():
                gtk.main_iteration()
            top = 0
            bot = len(self.songs)-1
            self.client.command_list_ok_begin()
            while top < bot:
                self.client.swap(top, bot)
                top = top + 1
                bot = bot - 1
            self.client.command_list_end()
            self.iterate_now()

    def mpd_shuffle(self, action):
        if self.conn:
            if len(self.songs) == 0:
                return
            ui.change_cursor(gtk.gdk.Cursor(gtk.gdk.WATCH))
            while gtk.events_pending():
                gtk.main_iteration()
            self.client.shuffle()

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
                    listallinfo = self.client.listallinfo(paths[i])
                    for item in listallinfo:
                        if item.has_key('file'):
                            mpdpaths.append(mpdh.get(item, 'file'))
            if len(mpdpaths) > 0:
                # Items found, add to list at drop position:
                if drop_info:
                    destpath, position = drop_info
                    if position in (gtk.TREE_VIEW_DROP_BEFORE, gtk.TREE_VIEW_DROP_INTO_OR_BEFORE):
                        id = destpath[0]
                    else:
                        id = destpath[0] + 1
                else:
                    id = len(self.songs)
                self.client.command_list_ok_begin()
                for mpdpath in mpdpaths:
                    self.client.addid(mpdpath, id)
                    id += 1
                self.client.command_list_end()
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

        # We will manipulate self.songs and model to prevent the entire playlist
        # from refreshing
        offset = 0
        top_row_for_selection = len(model)
        self.client.command_list_ok_begin()
        for source in drag_sources:
            index, iter, id, text = source
            if drop_info:
                destpath, position = drop_info
                dest = destpath[0] + offset
                if dest < index:
                    offset = offset + 1
                if position in (gtk.TREE_VIEW_DROP_BEFORE, gtk.TREE_VIEW_DROP_INTO_OR_BEFORE):
                    self.songs.insert(dest, self.songs[index])
                    if dest < index+1:
                        self.songs.pop(index+1)
                        self.client.moveid(id, dest)
                    else:
                        self.songs.pop(index)
                        self.client.moveid(id, dest-1)
                    model.insert(dest, model[index])
                    moved_iters += [model.get_iter((dest,))]
                    model.remove(iter)
                else:
                    self.songs.insert(dest+1, self.songs[index])
                    if dest < index:
                        self.songs.pop(index+1)
                        self.client.moveid(id, dest+1)
                    else:
                        self.songs.pop(index)
                        self.client.moveid(id, dest)
                    model.insert(dest+1, model[index])
                    moved_iters += [model.get_iter((dest+1,))]
                    model.remove(iter)
            else:
                dest = len(self.songs) - 1
                self.client.moveid(id, dest)
                self.songs.insert(dest+1, self.songs[index])
                self.songs.pop(index)
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
        self.client.command_list_end()

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
            self.client.update('/')
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
                    self.client.command_list_ok_begin()
                    for iter in iters:
                        self.client.update(self.librarydata.get_value(iter, 1))
                    self.client.command_list_end()
                else:
                    # If no selection, update the current path...
                    self.client.update(self.wd)
                self.iterate_now()

    def on_image_activate(self, widget, event):
        self.window.handler_block(self.mainwinhandler)
        if event.button == 1 and widget == self.info_imagebox and self.lastalbumart:
            if not self.info_art_enlarged:
                self.info_imagebox.set_size_request(-1,-1)
                self.artwork_set_image(self.lastalbumart, True)
                self.info_art_enlarged = True
            else:
                self.info_imagebox.set_size_request(152, -1)
                self.artwork_set_image(self.lastalbumart, True)
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
            if self.conn and self.status and self.status['state'] in ['play', 'pause']:
                self.UIManager.get_widget('/imagemenu/chooseimage_menu/').hide()
                self.UIManager.get_widget('/imagemenu/localimage_menu/').hide()
                if self.covers_pref != self.ART_LOCAL:
                    self.UIManager.get_widget('/imagemenu/chooseimage_menu/').show()
                self.UIManager.get_widget('/imagemenu/localimage_menu/').show()
                artist = mpdh.get(self.songinfo, 'artist', None)
                album = mpdh.get(self.songinfo, 'album', None)
                stream = mpdh.get(self.songinfo, 'name', None)
                if os.path.exists(self.target_image_filename(self.ART_LOCATION_NONE)):
                    self.UIManager.get_widget('/imagemenu/resetimage_menu/').set_sensitive(False)
                else:
                    self.UIManager.get_widget('/imagemenu/resetimage_menu/').set_sensitive(True)
                if artist or album or stream:
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
                    dest_filename = self.artwork_stream_filename(mpdh.get(self.songinfo, 'name'))
                else:
                    dest_filename = self.target_image_filename()
                    album = mpdh.get(self.songinfo, 'album', "").replace("/", "")
                    artist = self.album_current_artist[1].replace("/", "")
                    self.artwork_remove_none_file(artist, album)
                if dest_filename != paths[i]:
                    shutil.copyfile(paths[i], dest_filename)
                self.artwork_update(True)
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
            elif art_loc == self.ART_LOCATION_NONE:
                # flag filename to indicate that we should use the default Sonata icons:
                targetfile = os.path.expanduser("~/.covers/" + artist + "-" + album + "-" + self.ART_LOCATION_NONE_FLAG + ".jpg")
            return misc.file_from_utf8(targetfile)

    def album_return_artist_name(self):
        # Determine if album_name is a various artists album. We'll use a little
        # bit of hard-coded logic and assume that an album is a VA album if
        # there are more than 3 artists with the same album_name. The reason for
        # not assuming an album with >1 artists is a VA album is to prevent
        # marking albums by different artists that aren't actually VA (e.g.
        # albums with the name "Untitled", "Self-titled", and so on). The artist
        # will be set in the album_current_artist variable.
        #
        # Update: We will also check that the files are in the same path
        # to attempt to prevent Various Artists being set on a very common
        # album name like 'Unplugged'.
        if self.album_current_artist[0] == self.songinfo:
            return
        songs = self.return_album_items(mpdh.get(self.songinfo, 'album'), False)
        dir = os.path.dirname(mpdh.get(self.songinfo, 'file'))
        artists = []
        return_artist = ""
        for song in songs:
            if song.has_key('artist'):
                if dir == os.path.dirname(mpdh.get(song, 'file')):
                    artists.append(mpdh.get(song, 'artist'))
                    if mpdh.get(self.songinfo, 'file') == mpdh.get(song, 'file'):
                        return_artist = mpdh.get(song, 'artist')
        (artists, tmp, tmp2) = misc.remove_list_duplicates(artists, case=False)
        if len(artists) > 3:
            return_artist = _("Various Artists")
        self.album_current_artist = [self.songinfo, return_artist]

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
            self.local_dest_filename = self.artwork_stream_filename(stream)
        else:
            self.local_dest_filename = self.target_image_filename()
        dialog.show()

    def image_local_response(self, dialog, response, artist, album, stream):
        if response == gtk.RESPONSE_OK:
            filename = dialog.get_filenames()[0]
            if stream is None:
                self.artwork_remove_none_file(artist, album)
            # Copy file to covers dir:
            if self.local_dest_filename != filename:
                shutil.copyfile(filename, self.local_dest_filename)
            # And finally, set the image in the interface:
            self.artwork_update(True)
            # Force a resize of the info labels, if needed:
            gobject.idle_add(self.on_notebook_resize, self.notebook, None)
        dialog.destroy()

    def artwork_remove_none_file(self, artist, album):
        # If the flag file exists (to tell Sonata to use the default artwork
        # icons), remove the file
        delfile = os.path.expanduser("~/.covers/" + artist + "-" + album + "-" + self.ART_LOCATION_NONE_FLAG + ".jpg")
        misc.remove_file(delfile)

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
            self.remote_dest_filename = self.artwork_stream_filename(stream)
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
        self.stop_art_update = True
        while self.downloading_image:
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
        self.stop_art_update = False
        # Retrieve all images from amazon:
        artist_search = self.remote_artistentry.get_text()
        album_search = self.remote_albumentry.get_text()
        if len(artist_search) == 0 and len(album_search) == 0:
            gobject.idle_add(self.image_remote_no_tag_found, imagewidget)
            return
        filename = os.path.expanduser("~/.covers/temp/<imagenum>.jpg")
        misc.remove_dir(os.path.dirname(filename))
        misc.create_dir(os.path.dirname(filename))
        imgfound = self.artwork_download_img_to_file(artist_search, album_search, filename, True)
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

    def dialog_destroy(self, dialog, response_id):
        dialog.destroy()

    def image_remote_response(self, dialog, response_id, imagewidget, artist, album, stream):
        self.stop_art_update = True
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
        self.stop_art_update = True
        image_num = int(path[0])
        if len(self.remotefilelist) > 0:
            filename = self.remotefilelist[image_num]
            if os.path.exists(filename):
                if stream is None:
                    self.artwork_remove_none_file(artist, album)
                shutil.move(filename, self.remote_dest_filename)
                # And finally, set the image in the interface:
                self.artwork_update(True)
                # Clean up..
                misc.remove_dir(os.path.dirname(filename))
        self.chooseimage_visible = False
        self.choose_dialog.destroy()
        while self.downloading_image:
            gtk.main_iteration()

    def header_save_column_widths(self):
        if not self.withdrawn and self.expanded:
            windowwidth = self.window.allocation.width
            if windowwidth <= 10 or self.columns[0] <= 10:
                # Make sure we only set self.colwidthpercents if self.current
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
                # Save widths as percentages for when the application is resized.
                self.colwidthpercents[i] = float(self.columnwidths[i])/windowwidth
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
            elif self.window.window.get_state() & gtk.gdk.WINDOW_STATE_WITHDRAWN:
                # window is hidden
                self.withdraw_app_undo()
            elif not (self.window.window.get_state() & gtk.gdk.WINDOW_STATE_WITHDRAWN):
                # window is showing
                self.withdraw_app()
            # This prevents the tooltip from popping up again until the user
            # leaves and enters the trayicon again
            #if self.traytips.notif_handler == None and self.traytips.notif_handler <> -1:
            #	self.traytips._remove_timer()
            gobject.timeout_add(100, self.tooltip_set_ignore_toggle_signal_false)

    def tooltip_show_manually(self):
        # Since there is no signal to connect to when the user puts their
        # mouse over the trayicon, we will check the mouse position
        # manually and show/hide the window as appropriate. This is called
        # every iteration. Note: This should not occur if self.traytips.notif_
        # handler has a value, because that means that the tooltip is already
        # visible, and we don't want to override that setting simply because
        # the user's cursor is not over the tooltip.
        if self.traymenu.get_property('visible') and self.traytips.notif_handler <> -1:
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
        if self.UIManager.get_widget('/traymenu/showmenu').get_active() == True:
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
        if (not self.eggtrayheight or self.eggtrayheight != size) and self.eggtrayfile:
            self.eggtrayheight = size
            if size > 5:
                self.trayimage.set_from_pixbuf(img.get_pixbuf_of_size(gtk.gdk.pixbuf_new_from_file(self.eggtrayfile), self.eggtrayheight)[0])

    def on_current_click(self, treeview, path, column):
        model = self.current.get_model()
        if self.filterbox_visible:
            self.searchfilter_toggle(None)
        try:
            iter = model.get_iter(path)
            self.client.playid(self.current_get_songid(iter, model))
        except:
            pass
        self.iterate_now()

    def switch_to_tab_name(self, tab_name):
        self.notebook.set_current_page(self.notebook_get_tab_num(self.notebook, tab_name))

    def switch_to_tab_num(self, tab_num):
        vis_tabnum = self.notebook_get_visible_tab_num(self.notebook, tab_num)
        if vis_tabnum <> -1:
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
        self.client.setvol(new_volume)
        self.iterate_now()
        return

    def volume_hide(self):
        self.volumebutton.set_active(False)
        if self.volumewindow.get_property('visible'):
            self.volumewindow.hide()

    def mpd_pp(self, widget):
        if self.conn and self.status:
            if self.status['state'] in ('stop', 'pause'):
                self.client.play()
            elif self.status['state'] == 'play':
                self.client.pause(1)
            self.iterate_now()
        return

    def mpd_stop(self, widget, key=None):
        if self.conn:
            self.client.stop()
            self.iterate_now()
        return

    def mpd_prev(self, widget, key=None):
        if self.conn:
            self.client.previous()
            self.iterate_now()
        return

    def mpd_next(self, widget, key=None):
        if self.conn:
            self.client.next()
            self.iterate_now()
        return

    def on_remove(self, widget):
        if self.conn:
            while gtk.events_pending():
                gtk.main_iteration()
            if self.current_tab == self.TAB_CURRENT:
                treeviewsel = self.current_selection
                model, selected = treeviewsel.get_selected_rows()
                if len(selected) == len(self.currentdata) and not self.filterbox_visible:
                    # Everything is selected, clear:
                    self.client.clear()
                elif len(selected) > 0:
                    selected.reverse()
                    if not self.filterbox_visible:
                        # If we remove an item from the filtered results, this
                        # causes a visual refresh in the interface.
                        self.current.set_model(None)
                    self.client.command_list_ok_begin()
                    for path in selected:
                        if not self.filterbox_visible:
                            rownum = path[0]
                        else:
                            rownum = self.filter_row_mapping[path[0]]
                        iter = self.currentdata.get_iter((rownum, 0))
                        self.client.deleteid(self.current_get_songid(iter, self.currentdata))
                        # Prevents the entire playlist from refreshing:
                        self.songs.pop(rownum)
                        self.currentdata.remove(iter)
                    self.client.command_list_end()
                    if not self.filterbox_visible:
                        self.current.set_model(model)
            elif self.current_tab == self.TAB_PLAYLISTS:
                treeviewsel = self.playlists_selection
                model, selected = treeviewsel.get_selected_rows()
                if ui.show_error_msg_yesno(self.window, gettext.ngettext("Delete the selected playlist?", "Delete the selected playlists?", int(len(selected))), gettext.ngettext("Delete Playlist", "Delete Playlists", int(len(selected))), 'deletePlaylist') == gtk.RESPONSE_YES:
                    iters = [model.get_iter(path) for path in selected]
                    for iter in iters:
                        self.client.rm(misc.unescape_html(self.playlistsdata.get_value(iter, 1)))
                    self.playlists_populate()
            elif self.current_tab == self.TAB_STREAMS:
                treeviewsel = self.streams_selection
                model, selected = treeviewsel.get_selected_rows()
                if ui.show_error_msg_yesno(self.window, gettext.ngettext("Delete the selected stream?", "Delete the selected streams?", int(len(selected))), gettext.ngettext("Delete Stream", "Delete Streams", int(len(selected))), 'deleteStreams') == gtk.RESPONSE_YES:
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
            if len(model) > 0:
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
            self.client.clear()
            self.iterate_now()

    def on_repeat_clicked(self, widget):
        if self.conn:
            if widget.get_active():
                self.client.repeat(1)
            else:
                self.client.repeat(0)

    def on_shuffle_clicked(self, widget):
        if self.conn:
            if widget.get_active():
                self.client.random(1)
            else:
                self.client.random(0)

    def on_prefs(self, widget):
        prefswindow = ui.dialog(title=_("Preferences"), parent=self.window, flags=gtk.DIALOG_DESTROY_WITH_PARENT, role='preferences', resizable=False, separator=False)
        hbox = gtk.HBox()
        prefsnotebook = gtk.Notebook()
        # MPD tab
        mpdlabel = ui.label(markup='<b>' + _('MPD Connection') + '</b>', y=1)
        controlbox = gtk.HBox()
        profiles = ui.combo()
        add_profile = ui.button(img=ui.image(stock=gtk.STOCK_ADD))
        remove_profile = ui.button(img=ui.image(stock=gtk.STOCK_REMOVE))
        self.prefs_populate_profile_combo(profiles, self.profile_num, remove_profile)
        controlbox.pack_start(profiles, False, False, 2)
        controlbox.pack_start(remove_profile, False, False, 2)
        controlbox.pack_start(add_profile, False, False, 2)
        namebox = gtk.HBox()
        namelabel = ui.label(text=_("Name") + ":")
        namebox.pack_start(namelabel, False, False, 0)
        nameentry = ui.entry()
        namebox.pack_start(nameentry, True, True, 10)
        hostbox = gtk.HBox()
        hostlabel = ui.label(text=_("Host") + ":")
        hostbox.pack_start(hostlabel, False, False, 0)
        hostentry = ui.entry()
        hostbox.pack_start(hostentry, True, True, 10)
        portbox = gtk.HBox()
        portlabel = ui.label(text=_("Port") + ":")
        portbox.pack_start(portlabel, False, False, 0)
        portentry = ui.entry()
        portbox.pack_start(portentry, True, True, 10)
        dirbox = gtk.HBox()
        dirlabel = ui.label(text=_("Music dir") + ":")
        dirbox.pack_start(dirlabel, False, False, 0)
        direntry = ui.entry()
        direntry.connect('changed', self.prefs_direntry_changed, profiles)
        dirbox.pack_start(direntry, True, True, 10)
        passwordbox = gtk.HBox()
        passwordlabel = ui.label(text=_("Password") + ":")
        passwordbox.pack_start(passwordlabel, False, False, 0)
        passwordentry = ui.entry(password=True)
        self.tooltips.set_tip(passwordentry, _("Leave blank if no password is required."))
        passwordbox.pack_start(passwordentry, True, True, 10)
        mpd_labels = [namelabel, hostlabel, portlabel, passwordlabel, dirlabel]
        ui.set_widths_equal(mpd_labels)
        autoconnect = gtk.CheckButton(_("Autoconnect on start"))
        autoconnect.set_active(self.autoconnect)
        # Fill in entries with current profile:
        self.prefs_profile_chosen(profiles, nameentry, hostentry, portentry, passwordentry, direntry)
        # Update display if $MPD_HOST or $MPD_PORT is set:
        host, port, password = self.mpd_env_vars()
        if host or port:
            using_mpd_env_vars = True
            if not host: host = ""
            if not port: port = ""
            if not password: password = ""
            hostentry.set_text(str(host))
            portentry.set_text(str(port))
            passwordentry.set_text(str(password))
            nameentry.set_text(_("Using MPD_HOST/PORT"))
            for widget in [hostentry, portentry, passwordentry, nameentry, profiles, add_profile, remove_profile]:
                widget.set_sensitive(False)
        else:
            using_mpd_env_vars = False
            for widget in [hostentry, portentry, passwordentry, nameentry, profiles, add_profile, remove_profile]:
                widget.set_sensitive(True)
            nameentry.connect('changed', self.prefs_nameentry_changed, profiles, remove_profile)
            hostentry.connect('changed', self.prefs_hostentry_changed, profiles)
            portentry.connect('changed', self.prefs_portentry_changed, profiles)
            passwordentry.connect('changed', self.prefs_passwordentry_changed, profiles)
            profiles.connect('changed', self.prefs_profile_chosen, nameentry, hostentry, portentry, passwordentry, direntry)
            add_profile.connect('clicked', self.prefs_add_profile, nameentry, profiles, remove_profile)
            remove_profile.connect('clicked', self.prefs_remove_profile, profiles, remove_profile)
        mpd_frame = gtk.Frame()
        table = gtk.Table(6, 2, False)
        table.set_col_spacings(3)
        table.attach(ui.label(), 1, 3, 1, 2, gtk.FILL|gtk.EXPAND, gtk.FILL|gtk.EXPAND, 10, 0)
        table.attach(namebox, 1, 3, 2, 3, gtk.FILL|gtk.EXPAND, gtk.FILL|gtk.EXPAND, 10, 0)
        table.attach(hostbox, 1, 3, 3, 4, gtk.FILL|gtk.EXPAND, gtk.FILL|gtk.EXPAND, 10, 0)
        table.attach(portbox, 1, 3, 4, 5, gtk.FILL|gtk.EXPAND, gtk.FILL|gtk.EXPAND, 10, 0)
        table.attach(passwordbox, 1, 3, 5, 6, gtk.FILL|gtk.EXPAND, gtk.FILL|gtk.EXPAND, 10, 0)
        table.attach(dirbox, 1, 3, 6, 7, gtk.FILL|gtk.EXPAND, gtk.FILL|gtk.EXPAND, 10, 0)
        table.attach(ui.label(), 1, 3, 7, 8, gtk.FILL|gtk.EXPAND, gtk.FILL|gtk.EXPAND, 10, 0)
        mpd_frame.add(table)
        mpd_frame.set_label_widget(controlbox)
        mpd_table = gtk.Table(9, 2, False)
        mpd_table.set_col_spacings(3)
        mpd_table.attach(ui.label(), 1, 3, 1, 2, gtk.FILL|gtk.EXPAND, gtk.FILL|gtk.EXPAND, 10, 0)
        mpd_table.attach(mpdlabel, 1, 3, 2, 3, gtk.FILL|gtk.EXPAND, gtk.FILL|gtk.EXPAND, 15, 0)
        mpd_table.attach(ui.label(), 1, 3, 3, 4, gtk.FILL|gtk.EXPAND, gtk.FILL|gtk.EXPAND, 10, 0)
        mpd_table.attach(mpd_frame, 1, 3, 4, 10, gtk.FILL|gtk.EXPAND, gtk.FILL|gtk.EXPAND, 30, 0)
        mpd_table.attach(ui.label(), 1, 3, 10, 11, gtk.FILL|gtk.EXPAND, gtk.FILL|gtk.EXPAND, 30, 0)
        mpd_table.attach(autoconnect, 1, 3, 11, 12, gtk.FILL|gtk.EXPAND, gtk.FILL|gtk.EXPAND, 30, 0)
        mpd_table.attach(ui.label(), 1, 3, 12, 13, gtk.FILL|gtk.EXPAND, gtk.FILL|gtk.EXPAND, 30, 0)
        mpd_table.attach(ui.label(), 1, 3, 13, 14, gtk.FILL|gtk.EXPAND, gtk.FILL|gtk.EXPAND, 30, 0)
        mpd_table.attach(ui.label(), 1, 3, 14, 15, gtk.FILL|gtk.EXPAND, gtk.FILL|gtk.EXPAND, 30, 0)
        # Extras tab
        if not audioscrobbler is not None:
            self.as_enabled = False
        as_label = ui.label(markup='<b>' + _('Extras') + '</b>')
        as_frame = gtk.Frame()
        as_frame.set_label_widget(as_label)
        as_frame.set_shadow_type(gtk.SHADOW_NONE)
        as_frame.set_border_width(15)
        as_vbox = gtk.VBox()
        as_vbox.set_border_width(15)
        as_checkbox = gtk.CheckButton(_("Enable Audioscrobbler"))
        as_checkbox.set_active(self.as_enabled)
        as_vbox.pack_start(as_checkbox, False)
        as_table = gtk.Table(2, 2)
        as_table.set_col_spacings(3)
        as_user_label = ui.label(text="          " + _("Username:"))
        as_pass_label = ui.label(text="          " + _("Password:"))
        as_user_entry = ui.entry(text=self.as_username, changed_cb=self.prefs_as_username_changed)
        as_pass_entry = ui.entry(text=self.as_password, password=True, changed_cb=self.prefs_as_password_changed)
        displaylabel2 = ui.label(markup='<b>' + _('Notification') + '</b>', y=1)
        display_notification = gtk.CheckButton(_("Popup notification on song changes"))
        display_notification.set_active(self.show_notification)
        notifhbox = gtk.HBox()
        notif_blank = ui.label(x=1)
        notifhbox.pack_start(notif_blank)
        list = []
        for i in self.popuptimes:
            if i != _('Entire song'):
                list.append(i + ' ' + gettext.ngettext('second', 'seconds', int(i)))
            else:
                list.append(i)
        notification_options = ui.combo(list=list, active=self.popup_option, changed_cb=self.prefs_notiftime_changed)
        notification_locs = ui.combo(list=self.popuplocations, active=self.traytips.notifications_location, changed_cb=self.prefs_notiflocation_changed)
        display_notification.connect('toggled', self.prefs_notif_toggled, notifhbox)
        notifhbox.pack_start(notification_options, False, False, 2)
        notifhbox.pack_start(notification_locs, False, False, 2)
        if not self.show_notification:
            notifhbox.set_sensitive(False)
        crossfadecheck = gtk.CheckButton(_("Enable Crossfade"))
        crossfadespin = gtk.SpinButton()
        crossfadespin.set_digits(0)
        crossfadespin.set_range(1, 30)
        crossfadespin.set_value(self.xfade)
        crossfadespin.set_numeric(True)
        crossfadespin.set_increments(1,5)
        crossfadespin.set_size_request(70,-1)
        crossfadelabel2 = ui.label(text=_("Fade length") + ":", x=1)
        crossfadelabel3 = ui.label(text=_("sec"))
        if not self.xfade_enabled:
            crossfadespin.set_sensitive(False)
            crossfadelabel2.set_sensitive(False)
            crossfadelabel3.set_sensitive(False)
            crossfadecheck.set_active(False)
        else:
            crossfadespin.set_sensitive(True)
            crossfadelabel2.set_sensitive(True)
            crossfadelabel3.set_sensitive(True)
            crossfadecheck.set_active(True)
        crossfadebox = gtk.HBox()
        crossfadebox.pack_start(crossfadelabel2)
        crossfadebox.pack_start(crossfadespin, False, False, 5)
        crossfadebox.pack_start(crossfadelabel3, False, False, 0)
        crossfadecheck.connect('toggled', self.prefs_crossfadecheck_toggled, crossfadespin, crossfadelabel2, crossfadelabel3)
        as_table.attach(as_user_label, 0, 1, 0, 1)
        as_table.attach(as_user_entry, 1, 2, 0, 1)
        as_table.attach(as_pass_label, 0, 1, 1, 2)
        as_table.attach(as_pass_entry, 1, 2, 1, 2)
        as_table.attach(ui.label(), 0, 2, 2, 3)
        as_table.attach(display_notification, 0, 2, 3, 4)
        as_table.attach(notifhbox, 0, 2, 4, 5)
        as_table.attach(ui.label(), 0, 2, 5, 6)
        as_table.attach(crossfadecheck, 0, 2, 6, 7)
        as_table.attach(crossfadebox, 0, 2, 7, 8)
        as_table.attach(ui.label(), 0, 2, 8, 9)
        as_vbox.pack_start(as_table, False)
        as_frame.add(as_vbox)
        as_checkbox.connect('toggled', self.prefs_as_enabled_toggled, as_user_entry, as_pass_entry, as_user_label, as_pass_label)
        if not self.as_enabled or audioscrobbler is None:
            as_user_entry.set_sensitive(False)
            as_pass_entry.set_sensitive(False)
            as_user_label.set_sensitive(False)
            as_pass_label.set_sensitive(False)
        # Display tab
        table2 = gtk.Table(7, 2, False)
        displaylabel = ui.label(markup='<b>' + _('Display') + '</b>', y=1)
        display_art_hbox = gtk.HBox()
        display_art = gtk.CheckButton(_("Enable album art"))
        display_art.set_active(self.show_covers)
        display_stylized_combo = ui.combo(list=[_("Standard"), _("Stylized")], active=self.covers_type, changed_cb=self.prefs_stylized_toggled)
        display_stylized_hbox = gtk.HBox()
        display_stylized_hbox.pack_start(ui.label(text=_("Artwork style:"), x=1))
        display_stylized_hbox.pack_start(display_stylized_combo, False, False, 5)
        display_stylized_hbox.set_sensitive(self.show_covers)
        display_art_combo = ui.combo(list=[_("Local only"), _("Local, then remote")], active=self.covers_pref)
        orderart_label = ui.label(text=_("Search order:"), x=1)
        display_art_hbox.pack_start(orderart_label)
        display_art_hbox.pack_start(display_art_combo, False, False, 5)
        display_art_hbox.set_sensitive(self.show_covers)
        display_art_location_hbox = gtk.HBox()
        display_art_location_hbox.pack_start(ui.label(text=_("Save art to:"), x=1))
        list = ["~/.covers/"]
        for item in ["/cover.jpg", "/album.jpg", "/folder.jpg", "/" + _("custom")]:
            list.append("../" + _("file_path") + item)
        display_art_location = ui.combo(list=list, active=self.art_location, changed_cb=self.prefs_art_location_changed)
        display_art_location_hbox.pack_start(display_art_location, False, False, 5)
        display_art_location_hbox.set_sensitive(self.show_covers)
        display_art.connect('toggled', self.prefs_art_toggled, display_art_hbox, display_art_location_hbox, display_stylized_hbox)
        display_playback = gtk.CheckButton(_("Enable playback/volume buttons"))
        display_playback.set_active(self.show_playback)
        display_playback.connect('toggled', self.prefs_playback_toggled)
        display_progress = gtk.CheckButton(_("Enable progressbar"))
        display_progress.set_active(self.show_progress)
        display_progress.connect('toggled', self.prefs_progress_toggled)
        display_statusbar = gtk.CheckButton(_("Enable statusbar"))
        display_statusbar.set_active(self.show_statusbar)
        display_statusbar.connect('toggled', self.prefs_statusbar_toggled)
        display_lyrics = gtk.CheckButton(_("Enable lyrics"))
        display_lyrics.set_active(self.show_lyrics)
        display_lyrics_location_hbox = gtk.HBox()
        savelyrics_label = ui.label(text=_("Save lyrics to:"), x=1)
        display_lyrics_location_hbox.pack_start(savelyrics_label)
        display_lyrics_location = ui.combo(list=["~/.lyrics/", "../" + _("file_path") + "/"], active=self.lyrics_location, changed_cb=self.prefs_lyrics_location_changed)
        display_lyrics_location_hbox.pack_start(display_lyrics_location, False, False, 5)
        display_lyrics_location_hbox.set_sensitive(self.show_lyrics)
        display_lyrics.connect('toggled', self.prefs_lyrics_toggled, display_lyrics_location_hbox)
        display_trayicon = gtk.CheckButton(_("Enable system tray icon"))
        display_trayicon.set_active(self.show_trayicon)
        if not HAVE_EGG and not HAVE_STATUS_ICON:
            display_trayicon.set_sensitive(False)
        table2.attach(ui.label(), 1, 3, 1, 2, gtk.FILL|gtk.EXPAND, gtk.FILL|gtk.EXPAND, 15, 0)
        table2.attach(displaylabel, 1, 3, 2, 3, gtk.FILL|gtk.EXPAND, gtk.FILL|gtk.EXPAND, 15, 0)
        table2.attach(ui.label(), 1, 3, 3, 4, gtk.FILL|gtk.EXPAND, gtk.FILL|gtk.EXPAND, 15, 0)
        table2.attach(display_playback, 1, 3, 4, 5, gtk.FILL|gtk.EXPAND, gtk.FILL|gtk.EXPAND, 30, 0)
        table2.attach(display_progress, 1, 3, 5, 6, gtk.FILL|gtk.EXPAND, gtk.FILL|gtk.EXPAND, 30, 0)
        table2.attach(display_statusbar, 1, 3, 6, 7, gtk.FILL|gtk.EXPAND, gtk.FILL|gtk.EXPAND, 30, 0)
        table2.attach(display_trayicon, 1, 3, 7, 8, gtk.FILL|gtk.EXPAND, gtk.FILL|gtk.EXPAND, 30, 0)
        table2.attach(display_lyrics, 1, 3, 8, 9, gtk.FILL|gtk.EXPAND, gtk.FILL|gtk.EXPAND, 30, 0)
        table2.attach(display_lyrics_location_hbox, 1, 3, 9, 10, gtk.FILL|gtk.EXPAND, gtk.FILL|gtk.EXPAND, 30, 0)
        table2.attach(display_art, 1, 3, 10, 11, gtk.FILL|gtk.EXPAND, gtk.FILL|gtk.EXPAND, 30, 0)
        table2.attach(display_stylized_hbox, 1, 3, 11, 12, gtk.FILL|gtk.EXPAND, gtk.FILL|gtk.EXPAND, 30, 0)
        table2.attach(display_art_hbox, 1, 3, 12, 13, gtk.FILL|gtk.EXPAND, gtk.FILL|gtk.EXPAND, 30, 0)
        table2.attach(display_art_location_hbox, 1, 3, 13, 14, gtk.FILL|gtk.EXPAND, gtk.FILL|gtk.EXPAND, 30, 0)
        table2.attach(ui.label(), 1, 3, 14, 15, gtk.FILL|gtk.EXPAND, gtk.FILL|gtk.EXPAND, 75, 0)
        # Behavior tab
        table3 = gtk.Table()
        behaviorlabel = ui.label(markup='<b>' + _('Window Behavior') + '</b>', y=1)
        win_sticky = gtk.CheckButton(_("Show window on all workspaces"))
        win_sticky.set_active(self.sticky)
        win_ontop = gtk.CheckButton(_("Keep window above other windows"))
        win_ontop.set_active(self.ontop)
        update_start = gtk.CheckButton(_("Update MPD library on start"))
        update_start.set_active(self.update_on_start)
        self.tooltips.set_tip(update_start, _("If enabled, Sonata will automatically update your MPD library when it starts up."))
        exit_stop = gtk.CheckButton(_("Stop playback on exit"))
        exit_stop.set_active(self.stop_on_exit)
        self.tooltips.set_tip(exit_stop, _("MPD allows playback even when the client is not open. If enabled, Sonata will behave like a more conventional music player and, instead, stop playback upon exit."))
        minimize = gtk.CheckButton(_("Minimize to system tray on close/escape"))
        minimize.set_active(self.minimize_to_systray)
        self.tooltips.set_tip(minimize, _("If enabled, closing Sonata will minimize it to the system tray. Note that it's currently impossible to detect if there actually is a system tray, so only check this if you have one."))
        display_trayicon.connect('toggled', self.prefs_trayicon_toggled, minimize)
        if HAVE_STATUS_ICON and self.statusicon.is_embedded() and self.statusicon.get_visible():
            minimize.set_sensitive(True)
        elif HAVE_EGG and self.trayicon.get_property('visible') == True:
            minimize.set_sensitive(True)
        else:
            minimize.set_sensitive(False)
        infofilebox = gtk.HBox()
        infofile_usage = gtk.CheckButton(_("Write status file:"))
        infofile_usage.set_active(self.use_infofile)
        self.tooltips.set_tip(infofile_usage, _("If enabled, Sonata will create a xmms-infopipe like file containing information about the current song. Many applications support the xmms-info file (Instant Messengers, IRC Clients...)"))
        infopath_options = ui.entry(text=self.infofile_path)
        self.tooltips.set_tip(infopath_options, _("If enabled, Sonata will create a xmms-infopipe like file containing information about the current song. Many applications support the xmms-info file (Instant Messengers, IRC Clients...)"))
        if not self.use_infofile:
            infopath_options.set_sensitive(False)
        infofile_usage.connect('toggled', self.prefs_infofile_toggled, infopath_options)
        infofilebox.pack_start(infofile_usage, False, False, 0)
        infofilebox.pack_start(infopath_options, True, True, 5)
        behaviorlabel2 = ui.label(markup='<b>' + _('Miscellaneous') + '</b>', y=1)
        table3.attach(ui.label(), 1, 3, 1, 2, gtk.FILL|gtk.EXPAND, gtk.FILL|gtk.EXPAND, 15, 0)
        table3.attach(behaviorlabel, 1, 3, 2, 3, gtk.FILL|gtk.EXPAND, gtk.FILL|gtk.EXPAND, 15, 0)
        table3.attach(ui.label(), 1, 3, 3, 4, gtk.FILL|gtk.EXPAND, gtk.FILL|gtk.EXPAND, 15, 0)
        table3.attach(win_sticky, 1, 3, 4, 5, gtk.FILL|gtk.EXPAND, gtk.FILL|gtk.EXPAND, 30, 0)
        table3.attach(win_ontop, 1, 3, 5, 6, gtk.FILL|gtk.EXPAND, gtk.FILL|gtk.EXPAND, 30, 0)
        table3.attach(minimize, 1, 3, 6, 7, gtk.FILL|gtk.EXPAND, gtk.FILL|gtk.EXPAND, 30, 0)
        table3.attach(ui.label(), 1, 3, 7, 8, gtk.FILL|gtk.EXPAND, gtk.FILL|gtk.EXPAND, 15, 0)
        table3.attach(behaviorlabel2, 1, 3, 8, 9, gtk.FILL|gtk.EXPAND, gtk.FILL|gtk.EXPAND, 15, 0)
        table3.attach(ui.label(), 1, 3, 9, 10, gtk.FILL|gtk.EXPAND, gtk.FILL|gtk.EXPAND, 15, 0)
        table3.attach(update_start, 1, 3, 10, 11, gtk.FILL|gtk.EXPAND, gtk.FILL|gtk.EXPAND, 30, 0)
        table3.attach(exit_stop, 1, 3, 11, 12, gtk.FILL|gtk.EXPAND, gtk.FILL|gtk.EXPAND, 30, 0)
        table3.attach(infofilebox, 1, 3, 12, 13, gtk.FILL|gtk.EXPAND, gtk.FILL|gtk.EXPAND, 30, 0)
        table3.attach(ui.label(), 1, 3, 13, 14, gtk.FILL|gtk.EXPAND, gtk.FILL|gtk.EXPAND, 30, 0)
        table3.attach(ui.label(), 1, 3, 14, 15, gtk.FILL|gtk.EXPAND, gtk.FILL|gtk.EXPAND, 30, 0)
        table3.attach(ui.label(), 1, 3, 15, 16, gtk.FILL|gtk.EXPAND, gtk.FILL|gtk.EXPAND, 30, 0)
        table3.attach(ui.label(), 1, 3, 16, 17, gtk.FILL|gtk.EXPAND, gtk.FILL|gtk.EXPAND, 30, 0)
        table3.attach(ui.label(), 1, 3, 17, 18, gtk.FILL|gtk.EXPAND, gtk.FILL|gtk.EXPAND, 30, 0)
        table3.attach(ui.label(), 1, 3, 18, 19, gtk.FILL|gtk.EXPAND, gtk.FILL|gtk.EXPAND, 30, 0)
        # Format tab
        table4 = gtk.Table(9, 2, False)
        table4.set_col_spacings(3)
        formatlabel = ui.label(markup='<b>' + _('Song Formatting') + '</b>', y=1)
        currentformatbox = gtk.HBox()
        currentlabel = ui.label(text=_("Current playlist:"))
        currentoptions = ui.entry(text=self.currentformat)
        currentformatbox.pack_start(currentlabel, False, False, 0)
        currentformatbox.pack_start(currentoptions, False, False, 10)
        libraryformatbox = gtk.HBox()
        librarylabel = ui.label(text=_("Library:"))
        libraryoptions = ui.entry(text=self.libraryformat)
        libraryformatbox.pack_start(librarylabel, False, False, 0)
        libraryformatbox.pack_start(libraryoptions, False, False, 10)
        titleformatbox = gtk.HBox()
        titlelabel = ui.label(text=_("Window title:"))
        titleoptions = ui.entry(text=self.titleformat)
        titleoptions.set_text(self.titleformat)
        titleformatbox.pack_start(titlelabel, False, False, 0)
        titleformatbox.pack_start(titleoptions, False, False, 10)
        currsongformatbox1 = gtk.HBox()
        currsonglabel1 = ui.label(text=_("Current song line 1:"))
        currsongoptions1 = ui.entry(text=self.currsongformat1)
        currsongformatbox1.pack_start(currsonglabel1, False, False, 0)
        currsongformatbox1.pack_start(currsongoptions1, False, False, 10)
        currsongformatbox2 = gtk.HBox()
        currsonglabel2 = ui.label(text=_("Current song line 2:"))
        currsongoptions2 = ui.entry(text=self.currsongformat2)
        currsongformatbox2.pack_start(currsonglabel2, False, False, 0)
        currsongformatbox2.pack_start(currsongoptions2, False, False, 10)
        formatlabels = [currentlabel, librarylabel, titlelabel, currsonglabel1, currsonglabel2]
        for label in formatlabels:
            label.set_alignment(0, 0.5)
        ui.set_widths_equal(formatlabels)
        availableheading = ui.label(markup='<small>' + _('Available options') + ':</small>', y=0)
        availablevbox = gtk.VBox()
        availableformatbox = gtk.HBox()
        availableformatting = ui.label(markup='<small><span font_family="Monospace">%A</span> - ' + _('Artist name') + '\n<span font_family="Monospace">%B</span> - ' + _('Album name') + '\n<span font_family="Monospace">%T</span> - ' + _('Track name') + '\n<span font_family="Monospace">%N</span> - ' + _('Track number') + '\n<span font_family="Monospace">%D</span> - ' + _('Disc Number') + '\n<span font_family="Monospace">%Y</span> - ' + _('Year') + '</small>', y=0)
        availableformatting2 = ui.label(markup='<small><span font_family="Monospace">%G</span> - ' + _('Genre') + '\n<span font_family="Monospace">%F</span> - ' + _('File name') + '\n<span font_family="Monospace">%S</span> - ' + _('Stream name') + '\n<span font_family="Monospace">%L</span> - ' + _('Song length') + '\n<span font_family="Monospace">%E</span> - ' + _('Elapsed time (title only)') + '</small>', y=0)
        availableformatbox.pack_start(availableformatting)
        availableformatbox.pack_start(availableformatting2)
        availablevbox.pack_start(availableformatbox, False, False, 0)
        additionalinfo = ui.label(markup='<small>{ } - ' + _('Info displayed only if all enclosed tags are defined') + '\n' + '| - ' + _('Creates columns in the current playlist') + '</small>', y=0)
        availablevbox.pack_start(additionalinfo, False, False, 4)
        table4.attach(ui.label(), 1, 3, 1, 2, gtk.FILL|gtk.EXPAND, gtk.FILL|gtk.EXPAND, 15, 0)
        table4.attach(formatlabel, 1, 3, 2, 3, gtk.FILL|gtk.EXPAND, gtk.FILL|gtk.EXPAND, 15, 0)
        table4.attach(ui.label(), 1, 3, 3, 4, gtk.FILL|gtk.EXPAND, gtk.FILL|gtk.EXPAND, 15, 0)
        table4.attach(currentformatbox, 1, 3, 4, 5, gtk.FILL|gtk.EXPAND, gtk.FILL|gtk.EXPAND, 30, 0)
        table4.attach(libraryformatbox, 1, 3, 5, 6, gtk.FILL|gtk.EXPAND, gtk.FILL|gtk.EXPAND, 30, 0)
        table4.attach(titleformatbox, 1, 3, 6, 7, gtk.FILL|gtk.EXPAND, gtk.FILL|gtk.EXPAND, 30, 0)
        table4.attach(currsongformatbox1, 1, 3, 7, 8, gtk.FILL|gtk.EXPAND, gtk.FILL|gtk.EXPAND, 30, 0)
        table4.attach(currsongformatbox2, 1, 3, 8, 9, gtk.FILL|gtk.EXPAND, gtk.FILL|gtk.EXPAND, 30, 0)
        table4.attach(ui.label(), 1, 3, 9, 10, gtk.FILL|gtk.EXPAND, gtk.FILL|gtk.EXPAND, 30, 0)
        table4.attach(availableheading, 1, 3, 10, 11, gtk.FILL|gtk.EXPAND, gtk.FILL|gtk.EXPAND, 30, 0)
        table4.attach(availablevbox, 1, 3, 11, 12, gtk.FILL|gtk.EXPAND, gtk.FILL|gtk.EXPAND, 45, 0)
        table4.attach(ui.label(), 1, 3, 12, 13, gtk.FILL|gtk.EXPAND, gtk.FILL|gtk.EXPAND, 30, 0)
        table_names = [[_("_MPD"), mpd_table],
                       [_("_Display"), table2],
                       [_("_Behavior"), table3],
                       [_("_Format"), table4],
                       [_("_Extras"), as_frame]]
        for table_name in table_names:
            tmplabel = ui.label(textmn=table_name[0])
            prefsnotebook.append_page(table_name[1], tmplabel)
        hbox.pack_start(prefsnotebook, False, False, 10)
        prefswindow.vbox.pack_start(hbox, False, False, 10)
        close_button = prefswindow.add_button(gtk.STOCK_CLOSE, gtk.RESPONSE_CLOSE)
        prefswindow.show_all()
        close_button.grab_focus()
        prefswindow.connect('response', self.prefs_window_response, prefsnotebook, exit_stop, win_ontop, display_art_combo, win_sticky, direntry, minimize, update_start, autoconnect, currentoptions, libraryoptions, titleoptions, currsongoptions1, currsongoptions2, crossfadecheck, crossfadespin, infopath_options, hostentry, portentry, passwordentry, using_mpd_env_vars)
        # Save previous connection properties to determine if we should try to
        # connect to MPD after prefs are closed:
        self.prev_host = self.host[self.profile_num]
        self.prev_port = self.port[self.profile_num]
        self.prev_password = self.password[self.profile_num]
        response = prefswindow.show()

    def mpd_env_vars(self):
        host = None
        port = None
        password = None
        if os.environ.has_key('MPD_HOST'):
            if '@' in os.environ['MPD_HOST']:
                password, host = os.environ['MPD_HOST'].split('@')
            else:
                host = os.environ['MPD_HOST']
        if os.environ.has_key('MPD_PORT'):
            port = int(os.environ['MPD_PORT'])
        return (host, port, password)

    def scrobbler_init(self):
        if audioscrobbler is not None and self.as_enabled and len(self.as_username) > 0 and len(self.as_password) > 0:
            thread = threading.Thread(target=self.scrobbler_init_thread)
            thread.setDaemon(True)
            thread.start()

    def scrobbler_init_thread(self):
        if self.scrob is None:
            self.scrob = audioscrobbler.AudioScrobbler()
        if self.scrob_post is None:
            self.scrob_post = self.scrob.post(self.as_username, self.as_password, verbose=True)
        else:
            if self.scrob_post.authenticated:
                return # We are authenticated
            else:
                self.scrob_post = self.scrob.post(self.as_username, self.as_password, verbose=True)
        try:
            self.scrob_post.auth()
        except Exception, e:
            print "Error authenticating audioscrobbler", e
            self.scrob_post = None
        if self.scrob_post:
            self.scrobbler_retrieve_cache()

    def prefs_as_enabled_toggled(self, checkbox, userentry, passentry, userlabel, passlabel):
        if checkbox.get_active():
            self.scrobbler_import(True)
        if audioscrobbler is not None:
            self.as_enabled = checkbox.get_active()
            self.scrobbler_init()
            for widget in [userlabel, passlabel, userentry, passentry]:
                widget.set_sensitive(self.as_enabled)
        elif checkbox.get_active():
            checkbox.set_active(False)

    def scrobbler_import(self, show_error=False):
        # We need to try to import audioscrobbler either when the app starts (if
        # as_enabled=True) or if the user enables it in prefs.
        global audioscrobbler
        if audioscrobbler is None:
            try:
                import audioscrobbler
            except:
                if show_error:
                    ui.show_error_msg(self.window, _("Python 2.5 or python-elementtree not found, audioscrobbler support disabled."), _("Audioscrobbler Verification"), 'pythonElementtreeError')

    def prefs_as_username_changed(self, entry):
        if audioscrobbler is not None:
            self.as_username = entry.get_text()
            if self.scrob_post:
                if self.scrob_post.authenticated:
                    self.scrob_post = None

    def prefs_as_password_changed(self, entry):
        if audioscrobbler is not None:
            self.as_password = entry.get_text()
            if self.scrob_post:
                if self.scrob_post.authenticated:
                    self.scrob_post = None

    def prefs_window_response(self, window, response, prefsnotebook, exit_stop, win_ontop, display_art_combo, win_sticky, direntry, minimize, update_start, autoconnect, currentoptions, libraryoptions, titleoptions, currsongoptions1, currsongoptions2, crossfadecheck, crossfadespin, infopath_options, hostentry, portentry, passwordentry, using_mpd_env_vars):
        if response == gtk.RESPONSE_CLOSE:
            self.stop_on_exit = exit_stop.get_active()
            self.ontop = win_ontop.get_active()
            self.covers_pref = display_art_combo.get_active()
            self.sticky = win_sticky.get_active()
            if self.show_lyrics and self.lyrics_location != self.LYRICS_LOCATION_HOME:
                if not os.path.isdir(misc.file_from_utf8(self.musicdir[self.profile_num])):
                    ui.show_error_msg(self.window, _("To save lyrics to the music file's directory, you must specify a valid music directory."), _("Music Dir Verification"), 'musicdirVerificationError')
                    # Set music_dir entry focused:
                    prefsnotebook.set_current_page(0)
                    direntry.grab_focus()
                    return
            if self.show_covers and self.art_location != self.ART_LOCATION_HOMECOVERS:
                if not os.path.isdir(misc.file_from_utf8(self.musicdir[self.profile_num])):
                    ui.show_error_msg(self.window, _("To save artwork to the music file's directory, you must specify a valid music directory."), _("Music Dir Verification"), 'musicdirVerificationError')
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
                self.songs = None
                self.current_initialize_columns()
                self.current_update()
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
                    self.client.crossfade(self.xfade)
            else:
                self.xfade_enabled = False
                if self.conn:
                    self.client.crossfade(0)
            if self.infofile_path != infopath_options.get_text():
                self.infofile_path = os.path.expanduser(infopath_options.get_text())
                if self.use_infofile: self.update_infofile()
            if not using_mpd_env_vars:
                if self.prev_host != self.host[self.profile_num] or self.prev_port != self.port[self.profile_num] or self.prev_password != self.password[self.profile_num]:
                    # Try to connect if mpd connection info has been updated:
                    ui.change_cursor(gtk.gdk.Cursor(gtk.gdk.WATCH))
                    self.mpd_connect()
            if self.as_enabled:
                gobject.idle_add(self.scrobbler_init)
            self.settings_save()
            self.populate_profiles_for_menu()
            ui.change_cursor(None)
        window.destroy()

    def prefs_nameentry_changed(self, entry, profile_combo, remove_profiles):
        if not self.updating_nameentry:
            prefs_profile_num = profile_combo.get_active()
            self.profile_names[prefs_profile_num] = entry.get_text()
            self.prefs_populate_profile_combo(profile_combo, prefs_profile_num, remove_profiles)

    def prefs_hostentry_changed(self, entry, profile_combo):
        prefs_profile_num = profile_combo.get_active()
        self.host[prefs_profile_num] = entry.get_text()

    def prefs_portentry_changed(self, entry, profile_combo):
        prefs_profile_num = profile_combo.get_active()
        try:
            self.port[prefs_profile_num] = int(entry.get_text())
        except:
            pass

    def prefs_passwordentry_changed(self, entry, profile_combo):
        prefs_profile_num = profile_combo.get_active()
        self.password[prefs_profile_num] = entry.get_text()

    def prefs_direntry_changed(self, entry, profile_combo):
        prefs_profile_num = profile_combo.get_active()
        self.musicdir[prefs_profile_num] = self.sanitize_musicdir(entry.get_text())

    def sanitize_musicdir(self, mdir):
        mdir = os.path.expanduser(mdir)
        if len(mdir) > 0:
            if mdir[-1] != "/":
                mdir = mdir + "/"
        return mdir

    def prefs_add_profile(self, button, nameentry, profile_combo, remove_profiles):
        self.updating_nameentry = True
        prefs_profile_num = profile_combo.get_active()
        self.profile_names.append(_("New Profile"))
        nameentry.set_text(self.profile_names[len(self.profile_names)-1])
        self.updating_nameentry = False
        self.host.append(self.host[prefs_profile_num])
        self.port.append(self.port[prefs_profile_num])
        self.password.append(self.password[prefs_profile_num])
        self.musicdir.append(self.musicdir[prefs_profile_num])
        self.prefs_populate_profile_combo(profile_combo, len(self.profile_names)-1, remove_profiles)

    def prefs_remove_profile(self, button, profile_combo, remove_profiles):
        prefs_profile_num = profile_combo.get_active()
        if prefs_profile_num == self.profile_num:
            # Profile deleted, revert to first profile:
            self.profile_num = 0
            self.on_connectkey_pressed(None)
        self.profile_names.pop(prefs_profile_num)
        self.host.pop(prefs_profile_num)
        self.port.pop(prefs_profile_num)
        self.password.pop(prefs_profile_num)
        self.musicdir.pop(prefs_profile_num)
        if prefs_profile_num > 0:
            self.prefs_populate_profile_combo(profile_combo, prefs_profile_num-1, remove_profiles)
        else:
            self.prefs_populate_profile_combo(profile_combo, 0, remove_profiles)

    def prefs_profile_chosen(self, profile_combo, nameentry, hostentry, portentry, passwordentry, direntry):
        prefs_profile_num = profile_combo.get_active()
        self.updating_nameentry = True
        nameentry.set_text(str(self.profile_names[prefs_profile_num]))
        self.updating_nameentry = False
        hostentry.set_text(str(self.host[prefs_profile_num]))
        portentry.set_text(str(self.port[prefs_profile_num]))
        passwordentry.set_text(str(self.password[prefs_profile_num]))
        direntry.set_text(str(self.musicdir[prefs_profile_num]))

    def prefs_populate_profile_combo(self, profile_combo, active_index, remove_profiles):
        new_model = gtk.ListStore(str)
        new_model.clear()
        profile_combo.set_model(new_model)
        for i in range(len(self.profile_names)):
            if len(self.profile_names[i])	> 15:
                profile_combo.append_text("[" + str(i+1) + "] " + self.profile_names[i][:15] + "...")
            else:
                profile_combo.append_text("[" + str(i+1) + "] " + self.profile_names[i])
        profile_combo.set_active(active_index)
        if len(self.profile_names) == 1:
            remove_profiles.set_sensitive(False)
        else:
            remove_profiles.set_sensitive(True)

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
            self.artwork_set_default_icon()
            for widget in [self.imageeventbox, self.info_imagebox, self.trayalbumeventbox, self.trayalbumimage2]:
                widget.set_no_show_all(False)
                if widget in [self.trayalbumeventbox, self.trayalbumimage2]:
                    if self.conn and self.status and self.status['state'] in ['play', 'pause']:
                        widget.show_all()
                else:
                    widget.show_all()
            self.show_covers = True
            self.update_cursong()
            self.artwork_update()
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
        self.artwork_update(True)

    def prefs_lyrics_location_changed(self, combobox):
        self.lyrics_location = combobox.get_active()

    def prefs_art_location_changed(self, combobox):
        if combobox.get_active() == self.ART_LOCATION_CUSTOM:
            # Prompt user for playlist name:
            dialog = ui.dialog(title=_("Custom Artwork"), parent=self.window, flags=gtk.DIALOG_MODAL | gtk.DIALOG_DESTROY_WITH_PARENT, buttons=(gtk.STOCK_CANCEL, gtk.RESPONSE_REJECT, gtk.STOCK_OK, gtk.RESPONSE_ACCEPT), role='customArtwork', default=gtk.RESPONSE_ACCEPT)
            hbox = gtk.HBox()
            hbox.pack_start(ui.label(text=_('Artwork filename') + ':'), False, False, 5)
            entry = ui.entry()
            entry.set_activates_default(True)
            hbox.pack_start(entry, True, True, 5)
            dialog.vbox.pack_start(hbox)
            dialog.vbox.show_all()
            response = dialog.run()
            if response == gtk.RESPONSE_ACCEPT:
                self.art_location_custom_filename = entry.get_text().replace("/", "")
            else:
                # Revert to non-custom item in combobox:
                combobox.set_active(self.art_location)
            dialog.destroy()
        self.art_location = combobox.get_active()

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

    def prefs_crossfadecheck_toggled(self, button, combobox, label1, label2):
        button_active = button.get_active()
        for widget in [combobox, label1, label2]:
            widget.set_sensitive(button_active)

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
                if self.trayicon.get_property('visible') == True:
                    minimize.set_sensitive(True)
        else:
            self.show_trayicon = False
            minimize.set_sensitive(False)
            if HAVE_STATUS_ICON:
                self.statusicon.set_visible(False)
            elif HAVE_EGG:
                self.trayicon.hide_all()

    def prefs_notiflocation_changed(self, combobox):
        self.traytips.notifications_location = combobox.get_active()
        self.on_currsong_notify()

    def prefs_notiftime_changed(self, combobox):
        self.popup_option = combobox.get_active()
        self.on_currsong_notify()

    def prefs_infofile_toggled(self, button, infofileformatbox):
        if button.get_active():
            infofileformatbox.set_sensitive(True)
            self.use_infofile = True
            self.update_infofile()
        else:
            infofileformatbox.set_sensitive(False)
            self.use_infofile = False

    def seek(self, song, seektime):
        self.client.seek(song, seektime)
        self.iterate_now()
        return

    def on_link_enter(self, widget, event):
        if widget.get_children()[0].get_use_markup() == True:
            ui.change_cursor(gtk.gdk.Cursor(gtk.gdk.HAND2))

    def on_link_leave(self, widget, event):
        ui.change_cursor(None)

    def on_link_click(self, widget, event, type):
        if type == 'artist':
            misc.browser_load("http://www.wikipedia.org/wiki/Special:Search/" + mpdh.get(self.songinfo, 'artist'), self.url_browser, self.window)
        elif type == 'album':
            misc.browser_load("http://www.wikipedia.org/wiki/Special:Search/" + mpdh.get(self.songinfo, 'album'), self.url_browser, self.window)
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
        if self.library_search_visible():
            self.on_library_search_end(None)
        self.last_search_num = combo.get_active()

    def on_library_search_activate(self, entry):
        searchby = self.search_terms_mpd[self.last_search_num]
        if self.searchtext.get_text() != "":
            list = self.client.search(searchby, self.searchtext.get_text())
            self.librarydata.clear()
            bd = []
            for item in list:
                if item.has_key('directory'):
                    name = mpdh.get(item, 'directory').split('/')[-1]
                    # Sorting shouldn't really matter here. Ever seen a search turn up a directory?
                    bd += [('d' + mpdh.get(item, 'directory').lower(), [self.openpb, mpdh.get(item, 'directory'), misc.escape_html(name)])]
                elif item.has_key('file'):
                    try:
                        bd += [('f' + misc.lower_no_the(mpdh.get(item, 'artist')) + '\t' + mpdh.get(item, 'title').lower(), [self.sonatapb, mpdh.get(item, 'file'), self.parse_formatting(self.libraryformat, item, True)])]
                    except:
                        bd += [('f' + mpdh.get(item, 'file').lower(), [self.sonatapb, mpdh.get(item, 'file'), self.parse_formatting(self.libraryformat, item, True)])]
            bd.sort(key=misc.first_of_2tuple)
            for sort, list in bd:
                self.librarydata.append(list)

            self.library.grab_focus()
            self.library.scroll_to_point(0, 0)
            ui.show(self.searchbutton)
        else:
            self.on_library_search_end(None)

    def on_library_search_end(self, button):
        ui.hide(self.searchbutton)
        self.searchtext.set_text("")
        self.library_browse(root=self.wd)
        self.library.grab_focus()

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
            self.UIManager.get_widget('/mainmenu/updatemenu/').show()
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
        # Try loading module
        global tagpy
        if tagpy is None:
            try:
                import tagpy
                try:
                    # Set default tag encoding to utf8.. fixes some reported bugs.
                    import tagpy.id3v2 as id3v2
                    id3v2.FrameFactory.instance().setDefaultTextEncoding(tagpy.StringType.UTF8)
                except:
                    pass
            except:
                pass
        if tagpy is None:
            ui.show_error_msg(self.window, _("Taglib and/or tagpy not found, tag editing support disabled."), _("Edit Tags"), 'editTagsError', self.dialog_destroy)
            return
        if not os.path.isdir(misc.file_from_utf8(self.musicdir[self.profile_num])):
            ui.show_error_msg(self.window, _("The path") + " " + self.musicdir[self.profile_num] + " " + _("does not exist. Please specify a valid music directory in preferences."), _("Edit Tags"), 'editTagsError', self.dialog_destroy)
            return
        ui.change_cursor(gtk.gdk.Cursor(gtk.gdk.WATCH))
        self.edit_style_orig = self.searchtext.get_style()
        while gtk.events_pending():
            gtk.main_iteration()
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
            items = self.library_get_recursive_filenames(False)
            for item in items:
                files.append(self.musicdir[self.profile_num] + item)
                temp_mpdpaths.append(item)
        elif self.current_tab == self.TAB_CURRENT:
            # Populates files array with selected current playlist items:
            model, selected = self.current_selection.get_selected_rows()
            for path in selected:
                if not self.filterbox_visible:
                    item = mpdh.get(self.songs[path[0]], 'file')
                else:
                    item = mpdh.get(self.songs[self.filter_row_mapping[path[0]]], 'file')
                files.append(self.musicdir[self.profile_num] + item)
                temp_mpdpaths.append(item)
        if len(files) == 0:
            ui.change_cursor(None)
            return
        self.tagpy_is_91 = None
        # Initialize tags:
        tags = []
        for filenum in range(len(files)):
            tags.append({'title':'', 'artist':'', 'album':'', 'year':'',
                     'track':'', 'genre':'', 'comment':'', 'title-changed':False,
                     'artist-changed':False, 'album-changed':False, 'year-changed':False,
                     'track-changed':False, 'genre-changed':False, 'comment-changed':False,
                     'fullpath':misc.file_from_utf8(files[filenum]),
                     'mpdpath':temp_mpdpaths[filenum]})
        self.tagnum = -1
        if not os.path.exists(tags[0]['fullpath']):
            ui.change_cursor(None)
            ui.show_error_msg(self.window, _("File ") + "\"" + tags[0]['fullpath'] + "\"" + _(" not found. Please specify a valid music directory in preferences."), _("Edit Tags"), 'editTagsError', self.dialog_destroy)
            return
        if self.tags_next_tag(tags) == False:
            ui.change_cursor(None)
            ui.show_error_msg(self.window, _("No music files with editable tags found."), _("Edit Tags"), 'editTagsError', self.dialog_destroy)
            return
        editwindow = ui.dialog(parent=self.window, flags=gtk.DIALOG_MODAL, role='editTags', resizable=False, separator=False)
        editwindow.set_size_request(375, -1)
        table = gtk.Table(9, 2, False)
        table.set_row_spacings(2)
        filelabel = ui.label(select=True, wrap=True)
        filehbox = gtk.HBox()
        sonataicon = ui.image(stock='sonata', stocksize=gtk.ICON_SIZE_DND, x=1)
        blanklabel = ui.label(w=15, h=12)
        filehbox.pack_start(sonataicon, False, False, 2)
        filehbox.pack_start(filelabel, True, True, 2)
        filehbox.pack_start(blanklabel, False, False, 2)
        titlelabel = ui.label(text=_("Title") + ":", x=1)
        titleentry = ui.entry()
        titlebutton = ui.button()
        titlebuttonvbox = gtk.VBox()
        self.tags_win_create_apply_all_button(titlebutton, titlebuttonvbox, titleentry)
        titlehbox = gtk.HBox()
        titlehbox.pack_start(titlelabel, False, False, 2)
        titlehbox.pack_start(titleentry, True, True, 2)
        titlehbox.pack_start(titlebuttonvbox, False, False, 2)
        artistlabel = ui.label(text=_("Artist") + ":", x=1)
        artistentry = ui.entry()
        artisthbox = gtk.HBox()
        artistbutton = ui.button()
        artistbuttonvbox = gtk.VBox()
        self.tags_win_create_apply_all_button(artistbutton, artistbuttonvbox, artistentry)
        artisthbox.pack_start(artistlabel, False, False, 2)
        artisthbox.pack_start(artistentry, True, True, 2)
        artisthbox.pack_start(artistbuttonvbox, False, False, 2)
        albumlabel = ui.label(text=_("Album") + ":", x=1)
        albumentry = ui.entry()
        albumhbox = gtk.HBox()
        albumbutton = ui.button()
        albumbuttonvbox = gtk.VBox()
        self.tags_win_create_apply_all_button(albumbutton, albumbuttonvbox, albumentry)
        albumhbox.pack_start(albumlabel, False, False, 2)
        albumhbox.pack_start(albumentry, True, True, 2)
        albumhbox.pack_start(albumbuttonvbox, False, False, 2)
        yearlabel = ui.label(text="  " + _("Year") + ":", x=1)
        yearentry = ui.entry(w=50)
        handlerid = yearentry.connect("insert_text", self.tags_win_entry_constraint, True)
        yearentry.set_data('handlerid', handlerid)
        tracklabel = ui.label(text="  " + _("Track") + ":", x=1)
        trackentry = ui.entry(w=50)
        handlerid2 = trackentry.connect("insert_text", self.tags_win_entry_constraint, False)
        trackentry.set_data('handlerid2', handlerid2)
        yearbutton = ui.button()
        yearbuttonvbox = gtk.VBox()
        self.tags_win_create_apply_all_button(yearbutton, yearbuttonvbox, yearentry)
        trackbutton = ui.button()
        trackbuttonvbox = gtk.VBox()
        self.tags_win_create_apply_all_button(trackbutton, trackbuttonvbox, trackentry, True)
        yearandtrackhbox = gtk.HBox()
        yearandtrackhbox.pack_start(yearlabel, False, False, 2)
        yearandtrackhbox.pack_start(yearentry, True, True, 2)
        yearandtrackhbox.pack_start(yearbuttonvbox, False, False, 2)
        yearandtrackhbox.pack_start(tracklabel, False, False, 2)
        yearandtrackhbox.pack_start(trackentry, True, True, 2)
        yearandtrackhbox.pack_start(trackbuttonvbox, False, False, 2)
        genrelabel = ui.label(text=_("Genre") + ":", x=1)
        genrecombo = ui.comboentry(list=self.tags_win_genres(), wrap=2)
        genreentry = genrecombo.get_child()
        genrehbox = gtk.HBox()
        genrebutton = ui.button()
        genrebuttonvbox = gtk.VBox()
        self.tags_win_create_apply_all_button(genrebutton, genrebuttonvbox, genreentry)
        genrehbox.pack_start(genrelabel, False, False, 2)
        genrehbox.pack_start(genrecombo, True, True, 2)
        genrehbox.pack_start(genrebuttonvbox, False, False, 2)
        commentlabel = ui.label(text=_("Comment") + ":", x=1)
        commententry = ui.entry()
        commenthbox = gtk.HBox()
        commentbutton = ui.button()
        commentbuttonvbox = gtk.VBox()
        self.tags_win_create_apply_all_button(commentbutton, commentbuttonvbox, commententry)
        commenthbox.pack_start(commentlabel, False, False, 2)
        commenthbox.pack_start(commententry, True, True, 2)
        commenthbox.pack_start(commentbuttonvbox, False, False, 2)
        ui.set_widths_equal([titlelabel, artistlabel, albumlabel, yearlabel, genrelabel, commentlabel, sonataicon])
        genrecombo.set_size_request(-1, titleentry.size_request()[1])
        tablewidgets = [ui.label(), filehbox, ui.label(), titlehbox, artisthbox, albumhbox, yearandtrackhbox, genrehbox, commenthbox, ui.label()]
        for i in range(len(tablewidgets)):
            table.attach(tablewidgets[i], 1, 2, i+1, i+2, gtk.FILL|gtk.EXPAND, gtk.FILL|gtk.EXPAND, 2, 0)
        editwindow.vbox.pack_start(table)
        saveall_button = None
        if len(files) > 1:
            # Only show save all button if more than one song being edited.
            saveall_button = ui.button(text=_("Save _All"))
            editwindow.action_area.pack_start(saveall_button)
        cancelbutton = editwindow.add_button(gtk.STOCK_CANCEL, gtk.RESPONSE_REJECT)
        savebutton = editwindow.add_button(gtk.STOCK_SAVE, gtk.RESPONSE_ACCEPT)
        editwindow.connect('delete_event', self.tags_win_hide, tags)
        entries = [titleentry, artistentry, albumentry, yearentry, trackentry, genreentry, commententry, filelabel]
        buttons = [titlebutton, artistbutton, albumbutton, yearbutton, trackbutton, genrebutton, commentbutton]
        entries_names = ["title", "artist", "album", "year", "track", "genre", "comment"]
        editwindow.connect('response', self.tags_win_response, tags, entries, entries_names)
        if saveall_button:
            saveall_button.connect('clicked', self.tags_win_save_all, editwindow, tags, entries, entries_names)
        for i in range(len(entries)-1):
            entries[i].connect('changed', self.tags_win_entry_changed)
        for i in range(len(buttons)):
            buttons[i].connect('clicked', self.tags_win_apply_all, entries_names[i], tags, entries)
        self.tags_win_update(editwindow, tags, entries, entries_names)
        ui.change_cursor(None)
        entries[7].set_size_request(editwindow.size_request()[0] - titlelabel.size_request()[0] - 50, -1)
        editwindow.show_all()

    def tags_next_tag(self, tags):
        # Returns true if next tag found (and self.tagnum is updated).
        # If no next tag found, returns False.
        while self.tagnum < len(tags)-1:
            self.tagnum = self.tagnum + 1
            if os.path.exists(tags[self.tagnum]['fullpath']):
                try:
                    fileref = tagpy.FileRef(tags[self.tagnum]['fullpath'])
                    if not fileref.isNull():
                        return True
                except:
                    pass
        return False

    def tags_win_entry_changed(self, editable, force_red=False):
        if force_red or not self.updating_edit_entries:
            style = editable.get_style().copy()
            style.text[gtk.STATE_NORMAL] = editable.get_colormap().alloc_color("red")
            editable.set_style(style)

    def tags_win_entry_revert_color(self, editable):
        editable.set_style(self.edit_style_orig)

    def tags_win_create_apply_all_button(self, button, vbox, entry, autotrack=False):
        button.set_size_request(12, 12)
        if autotrack:
            self.tooltips.set_tip(button, _("Increment each selected music file, starting at track 1 for this file."))
        else:
            self.tooltips.set_tip(button, _("Apply to all selected music files."))
        padding = int((entry.size_request()[1] - button.size_request()[1])/2)+1
        vbox.pack_start(button, False, False, padding)

    def tags_win_apply_all(self, button, item, tags, entries):
        tagnum = 0
        for tag in tags:
            tagnum = tagnum + 1
            if item == "title":
                tag['title'] = entries[0].get_text()
                tag['title-changed'] = True
            elif item == "album":
                tag['album'] = entries[2].get_text()
                tag['album-changed'] = True
            elif item == "artist":
                tag['artist'] = entries[1].get_text()
                tag['artist-changed'] = True
            elif item == "year":
                if len(entries[3].get_text()) > 0:
                    tag['year'] = int(entries[3].get_text())
                else:
                    tag['year'] = 0
                tag['year-changed'] = True
            elif item == "track":
                if tagnum >= self.tagnum-1:
                    # Start the current song at track 1, as opposed to the first
                    # song in the list.
                    tag['track'] = tagnum - self.tagnum
                tag['track-changed'] = True
            elif item == "genre":
                tag['genre'] = entries[5].get_text()
                tag['genre-changed'] = True
            elif item == "comment":
                tag['comment'] = entries[6].get_text()
                tag['comment-changed'] = True
        if item == "track":
            # Update the entry for the current song:
            entries[4].set_text(str(tags[self.tagnum]['track']))

    def tags_win_update(self, window, tags, entries, entries_names):
        self.updating_edit_entries = True
        # Populate tags(). Note that we only retrieve info from the
        # file if the info hasn't already been changed:
        fileref = tagpy.FileRef(tags[self.tagnum]['fullpath'])
        if not tags[self.tagnum]['title-changed']:
            tags[self.tagnum]['title'] = fileref.tag().title
        if not tags[self.tagnum]['artist-changed']:
            tags[self.tagnum]['artist'] = fileref.tag().artist
        if not tags[self.tagnum]['album-changed']:
            tags[self.tagnum]['album'] = fileref.tag().album
        if not tags[self.tagnum]['year-changed']:
            tags[self.tagnum]['year'] = fileref.tag().year
        if not tags[self.tagnum]['track-changed']:
            tags[self.tagnum]['track'] = fileref.tag().track
        if not tags[self.tagnum]['genre-changed']:
            tags[self.tagnum]['genre'] = fileref.tag().genre
        if not tags[self.tagnum]['comment-changed']:
            tags[self.tagnum]['comment'] = fileref.tag().comment
        # Update interface:
        entries[0].set_text(self.tags_get_tag(tags[self.tagnum], 'title'))
        entries[1].set_text(self.tags_get_tag(tags[self.tagnum], 'artist'))
        entries[2].set_text(self.tags_get_tag(tags[self.tagnum], 'album'))
        if self.tags_get_tag(tags[self.tagnum], 'year') != 0:
            entries[3].set_text(str(self.tags_get_tag(tags[self.tagnum], 'year')))
        else:
            entries[3].set_text('')
        if self.tags_get_tag(tags[self.tagnum], 'track') != 0:
            entries[4].set_text(str(self.tags_get_tag(tags[self.tagnum], 'track')))
        else:
            entries[4].set_text('')
        entries[5].set_text(self.tags_get_tag(tags[self.tagnum], 'genre'))
        entries[6].set_text(self.tags_get_tag(tags[self.tagnum], 'comment'))
        filename = gobject.filename_display_name(tags[self.tagnum]['mpdpath'].split('/')[-1])
        entries[7].set_text(filename)
        entries[0].select_region(0, len(entries[0].get_text()))
        entries[0].grab_focus()
        window.set_title(_("Edit Tags") + " - " + str(self.tagnum+1) + " " + _("of") + " " + str(len(tags)))
        self.updating_edit_entries = False
        # Update text colors as appropriate:
        for i in range(len(entries)-1):
            if tags[self.tagnum][entries_names[i] + '-changed']:
                self.tags_win_entry_changed(entries[i])
            else:
                self.tags_win_entry_revert_color(entries[i])
        self.tags_win_set_sensitive(window.action_area)

    def tags_win_set_sensitive(self, action_area):
        # Hacky workaround to allow the user to click the save button again when the
        # mouse stays over the button (see http://bugzilla.gnome.org/show_bug.cgi?id=56070)
        action_area.set_sensitive(True)
        action_area.hide()
        action_area.show_all()

    def tags_get_tag(self, tag, field):
        # Since tagpy went through an API change from 0.90.1 to 0.91, we'll
        # implement both methods of retrieving the tag:
        if self.tagpy_is_91 is None:
            try:
                test = tag[field]()
                self.tagpy_is_91 = False
            except:
                self.tagpy_is_91 = True
        if self.tagpy_is_91 == False:
            try:
                return tag[field]().strip()
            except:
                return tag[field]()
        else:
            try:
                return tag[field].strip()
            except:
                return tag[field]

    def tags_set_tag(self, tag, field, value):
        # Since tagpy went through an API change from 0.90.1 to 0.91, we'll
        # implement both methods of setting the tag:
        try:
            value = value.strip()
        except:
            pass
        if field=='artist':
            if self.tagpy_is_91 == False:
                tag.setArtist(value)
            else:
                tag.artist = value
        elif field=='title':
            if self.tagpy_is_91 == False:
                tag.setTitle(value)
            else:
                tag.title = value
        elif field=='album':
            if self.tagpy_is_91 == False:
                tag.setAlbum(value)
            else:
                tag.album = value
        elif field=='year':
            if self.tagpy_is_91 == False:
                tag.setYear(int(value))
            else:
                tag.year = int(value)
        elif field=='track':
            if self.tagpy_is_91 == False:
                tag.setTrack(int(value))
            else:
                tag.track = int(value)
        elif field=='genre':
            if self.tagpy_is_91 == False:
                tag.setGenre(value)
            else:
                tag.genre = value
        elif field=='comment':
            if self.tagpy_is_91 == False:
                tag.setComment(value)
            else:
                tag.comment = value

    def tags_win_save_all(self, button, window, tags, entries, entries_names):
        for entry in entries:
            try: # Skip GtkLabels
                entry.set_property('editable', False)
            except:
                pass
        while window.get_property('visible'):
            self.tags_win_response(window, gtk.RESPONSE_ACCEPT, tags, entries, entries_names)

    def tags_win_response(self, window, response, tags, entries, entries_names):
        if response == gtk.RESPONSE_REJECT:
            self.tags_win_hide(window, None, tags)
        elif response == gtk.RESPONSE_ACCEPT:
            window.action_area.set_sensitive(False)
            while window.action_area.get_property("sensitive") == True or gtk.events_pending():
                gtk.main_iteration()
            filetag = tagpy.FileRef(tags[self.tagnum]['fullpath'])
            self.tags_set_tag(filetag.tag(), 'title', entries[0].get_text())
            self.tags_set_tag(filetag.tag(), 'artist', entries[1].get_text())
            self.tags_set_tag(filetag.tag(), 'album', entries[2].get_text())
            if len(entries[3].get_text()) > 0:
                self.tags_set_tag(filetag.tag(), 'year', entries[3].get_text())
            else:
                self.tags_set_tag(filetag.tag(), 'year', 0)
            if len(entries[4].get_text()) > 0:
                self.tags_set_tag(filetag.tag(), 'track', entries[4].get_text())
            else:
                self.tags_set_tag(filetag.tag(), 'track', 0)
            self.tags_set_tag(filetag.tag(), 'genre', entries[5].get_text())
            self.tags_set_tag(filetag.tag(), 'comment', entries[6].get_text())
            save_success = filetag.save()
            if not (save_success and self.conn and self.status):
                ui.show_error_msg(self.window, _("Unable to save tag to music file."), _("Edit Tags"), 'editTagsError', self.dialog_destroy)
            if self.tags_next_tag(tags):
                # Next file:
                self.tags_win_update(window, tags, entries, entries_names)
            else:
                # No more (valid) files:
                self.tagnum = self.tagnum + 1 # To ensure we update the last file in tags_mpd_update
                self.tags_win_hide(window, None, tags)

    def tags_win_hide(self, window, data=None, tags=None):
        gobject.idle_add(self.tags_mpd_update, tags)
        window.destroy()

    def tags_mpd_update(self, tags):
        if tags:
            self.client.command_list_ok_begin()
            for i in range(self.tagnum):
                self.client.update(tags[i]['mpdpath'])
            self.client.command_list_end()
            self.iterate_now()

    def tags_win_genres(self):
        return ["", "A Cappella", "Acid", "Acid Jazz", "Acid Punk", "Acoustic",
                "Alt. Rock", "Alternative", "Ambient", "Anime", "Avantgarde", "Ballad",
                "Bass", "Beat", "Bebob", "Big Band", "Black Metal", "Bluegrass",
                "Blues", "Booty Bass", "BritPop", "Cabaret", "Celtic", "Chamber music",
                "Chanson", "Chorus", "Christian Gangsta Rap", "Christian Rap",
                "Christian Rock", "Classic Rock", "Classical", "Club", "Club-House",
                "Comedy", "Contemporary Christian", "Country", "Crossover", "Cult",
                "Dance", "Dance Hall", "Darkwave", "Death Metal", "Disco", "Dream",
                "Drum &amp; Bass", "Drum Solo", "Duet", "Easy Listening", "Electronic",
                "Ethnic", "Euro-House", "Euro-Techno", "Eurodance", "Fast Fusion",
                "Folk", "Folk-Rock", "Folklore", "Freestyle", "Funk", "Fusion", "Game",
                "Gangsta", "Goa", "Gospel", "Gothic", "Gothic Rock", "Grunge",
                "Hard Rock", "Hardcore", "Heavy Metal", "Hip-Hop", "House", "Humour",
                "Indie", "Industrial", "Instrumental", "Instrumental pop",
                "Instrumental rock", "JPop", "Jazz", "Jazz+Funk", "Jungle", "Latin",
                "Lo-Fi", "Meditative", "Merengue", "Metal", "Musical", "National Folk",
                "Native American", "Negerpunk", "New Age", "New Wave", "Noise",
                "Oldies", "Opera", "Other", "Polka", "Polsk Punk", "Pop", "Pop-Folk",
                "Pop/Funk", "Porn Groove", "Power Ballad", "Pranks", "Primus",
                "Progressive Rock", "Psychedelic", "Psychedelic Rock", "Punk",
                "Punk Rock", "R&amp;B", "Rap", "Rave", "Reggae", "Retro", "Revival",
                "Rhythmic soul", "Rock", "Rock &amp; Roll", "Salsa", "Samba", "Satire",
                "Showtunes", "Ska", "Slow Jam", "Slow Rock", "Sonata", "Soul",
                "Sound Clip", "Soundtrack", "Southern Rock", "Space", "Speech",
                "Swing", "Symphonic Rock", "Symphony", "Synthpop", "Tango", "Techno",
                "Techno-Industrial", "Terror", "Thrash Metal", "Top 40", "Trailer"]

    def tags_win_entry_constraint(self, entry, new_text, new_text_length, position, isyearlabel):
        lst_old_string = list(entry.get_chars(0, -1))
        _pos = entry.get_position()
        lst_new_string = lst_old_string.insert(_pos, new_text)
        _string = "".join(lst_old_string)
        if isyearlabel:
            _hid = entry.get_data('handlerid')
        else:
            _hid = entry.get_data('handlerid2')
        entry.handler_block(_hid)
        try:
            _val = float(_string)
            if (isyearlabel and _val <= 9999) or not isyearlabel:
                _pos = entry.insert_text(new_text, _pos)
        except StandardError, e:
            pass
        entry.handler_unblock(_hid)
        gobject.idle_add(lambda t: t.set_position(t.get_position()+1), entry)
        entry.stop_emission("insert-text")
        pass

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
                 [ "Alt-[1-5]", _("Switch to [1st-5th] tab") ],
                 [ "Alt-C", _("Connect to MPD") ],
                 [ "Alt-D", _("Disconnect from MPD") ],
                 [ "Alt-R", _("Randomize current playlist") ],
                 [ "Alt-Down", _("Expand player") ],
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
            stats = self.client.stats()
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
        self.about_dialog.set_translator_credits('be@latin - Ihar Hrachyshka <ihar.hrachyshka@gmail.com>\ncs - Jakub Adler <jakubadler@gmail.com>\nda - Martin Dybdal <dybber@dybber.dk>\nde - Paul Johnson <thrillerator@googlemail.com>\nes - Xoan Sampaiño <xoansampainho@gmail.com>\net - Mihkel <turakas@gmail.com>\nfi - Ilkka Tuohelafr <hile@hack.fi>\nfr - Floreal M <florealm@gmail.com>\nit - Gianni Vialetto <forgottencrow@gmail.com>\nnl - Olivier Keun <litemotiv@gmail.com>\npl - Tomasz Dominikowski <dominikowski@gmail.com>\npt_BR - Alex Tercete Matos <alextercete@gmail.com>\nru - Ivan <bkb.box@bk.ru>\nsv - Daniel Nylander <po@danielnylander.se>\nuk - Господарисько Тарас <dogmaton@gmail.com>\nzh_CN - Desmond Chang <dochang@gmail.com>\n')
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

    def searchfilter_toggle(self, widget, initial_text=""):
        if self.filterbox_visible:
            self.filterbox_visible = False
            self.edit_style_orig = self.searchtext.get_style()
            ui.hide(self.filterbox)
            self.searchfilter_stop_loop(self.filterbox);
            self.filterpattern.set_text("")
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
            gobject.idle_add(self.searchfilter_entry_grab_focus, self.filterpattern)
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
            self.client.playid(song_id)
            self.current_center_song_in_list()

    def current_get_songid(self, iter, model):
        return int(model.get_value(iter, 0))

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

    def searchfilter_stop_loop(self, window):
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
                gobject.idle_add(self.searchfilter_revert_model, self.playlist_pos_before_filter)
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

    def searchfilter_revert_model(self, filterposition):
        self.current.set_model(self.currentdata)
        self.playlist_retain_view(self.current, filterposition)
        self.current.thaw_child_notify()
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
                gobject.idle_add(self.tags_win_entry_changed, self.filterpattern, True)
            else:
                gobject.idle_add(self.tags_win_entry_revert_color, self.filterpattern)
            self.current.thaw_child_notify()

    def searchfilter_key_pressed(self, widget, event):
        if event.keyval == gtk.gdk.keyval_from_name('Down') or event.keyval == gtk.gdk.keyval_from_name('Up') or event.keyval == gtk.gdk.keyval_from_name('Page_Down') or event.keyval == gtk.gdk.keyval_from_name('Page_Up'):
            self.current.grab_focus()
            self.current.emit("key-press-event", event)
            gobject.idle_add(self.searchfilter_entry_grab_focus, widget)

    def searchfilter_entry_grab_focus(self, widget):
        widget.grab_focus()
        widget.set_position(-1)

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
