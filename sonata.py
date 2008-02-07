# coding=utf-8
# $HeadURL: http://svn.berlios.de/svnroot/repos/sonata/trunk/sonata.py $
# $Id: sonata.py 141 2006-09-11 04:51:07Z stonecrest $

__version__ = "1.4.1"

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

import warnings, sys, os, gobject, ConfigParser, urllib, urllib2
import socket, gc, subprocess, gettext, locale, shutil, getopt
import threading, re, time

try:
    import gtk, pango, mpdclient3
except ImportError, (strerror):
    print >>sys.stderr, "%s.  Please make sure you have this library installed into a directory in Python's path or in the same directory as Sonata.\n" % strerror
    sys.exit(1)

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
    import audioscrobbler
    HAVE_AUDIOSCROBBLER = True
except:
    HAVE_AUDIOSCROBBLER = False

try:
    from sugar.activity import activity
    HAVE_STATUS_ICON = False
    HAVE_SUGAR = True
    VOLUME_ICON_SIZE = 3
except:
    HAVE_SUGAR = False
    VOLUME_ICON_SIZE = 4

try:
    import tagpy
    HAVE_TAGPY = True
except:
    HAVE_TAGPY = False

if HAVE_TAGPY:
    try:
        # Set default tag encoding to utf8.. fixes some reported bugs.
        import tagpy.id3v2 as id3v2
        id3v2.FrameFactory.instance().setDefaultTextEncoding(tagpy.StringType.UTF8)
    except:
        pass

try:
    from ZSI import ServiceProxy
    # Make sure we have the right version..
    test = ServiceProxy.ServiceProxy
    HAVE_WSDL = True
except:
    HAVE_WSDL = False

try:
    import gnome, gnome.ui
    HAVE_GNOME_UI = True
except:
    HAVE_GNOME_UI = False

# Test pygtk version
if gtk.pygtk_version < (2, 6, 0):
    sys.stderr.write("Sonata requires PyGTK 2.6.0 or newer.\n")
    sys.exit(1)

class Connection(mpdclient3.mpd_connection):
    """A connection to the daemon. Will use MPD_HOST/MPD_PORT in preference to the supplied config if available."""

    def __init__(self, Base):
        """Open a connection using the host/port values from the provided config. If conf is None, an empty object will be returned, suitable for comparing != to any other connection."""

        host, port, password = Base.mpd_env_vars()
        if not host: host = Base.host[Base.profile_num]
        if not port: port = Base.port[Base.profile_num]
        if not password: password = Base.password[Base.profile_num]

        mpdclient3.mpd_connection.__init__(self, host, port, password)
        mpdclient3.connect(host=host, port=port, password=password)

class Base(mpdclient3.mpd_connection):
    def __init__(self, window=None, sugar=False):

        gtk.gdk.threads_init()

        try:
            gettext.install('sonata', os.path.join(__file__.split('/lib')[0], 'share', 'locale'), unicode=1)
        except:
            gettext.install('sonata', '/usr/share/locale', unicode=1)
        gettext.textdomain('sonata')

        self.traytips = TrayIconTips()

        # Initialize vars (these can be needed if we have a cli argument, e.g., "sonata play")
        socket.setdefaulttimeout(5)
        self.profile_num = 0
        self.profile_names = [_('Default Profile')]
        self.musicdir = [self.sanitize_musicdir("~/music")]
        self.host = ['localhost']
        self.port = [6600]
        self.password = ['']

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
        self.VIEW_ALBUM = 2
        self.LYRIC_TIMEOUT = 10
        self.NOTIFICATION_WIDTH_MAX = 500
        self.NOTIFICATION_WIDTH_MIN = 350
        self.ART_LOCATION_HOMECOVERS = 0		# ~/.covers/[artist]-[album].jpg
        self.ART_LOCATION_COVER = 1				# file_dir/cover.jpg
        self.ART_LOCATION_ALBUM = 2				# file_dir/album.jpg
        self.ART_LOCATION_FOLDER = 3			# file_dir/folder.jpg
        self.ART_LOCATION_CUSTOM = 4			# file_dir/[custom]
        self.ART_LOCATION_NONE = 5				# Use default Sonata icons
        self.ART_LOCATION_NONE_FLAG = "USE_DEFAULT"
        self.ART_LOCATIONS_MISC = ['front.jpg', '.folder.jpg', '.folder.png', 'AlbumArt.jpg', 'AlbumArtSmall.jpg']
        self.LYRICS_LOCATION_HOME = 0			# ~/.lyrics/[artist]-[song].txt
        self.LYRICS_LOCATION_PATH = 1			# file_dir/[artist]-[song].txt

        self.trying_connection = False
        toggle_arg = False
        start_hidden = False
        start_visible = False
        arg_profile = False
        # Read any passed options/arguments:
        if not sugar:
            try:
                opts, args = getopt.getopt(sys.argv[1:], "tv", ["toggle", "version", "status", "info", "play", "pause", "stop", "next", "prev", "pp", "shuffle", "repeat", "hidden", "visible", "profile="])
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
                    if a in ("play", "pause", "stop", "next", "prev", "pp", "info", "status", "repeat", "shuffle"):
                        self.single_connect_for_passed_arg(a)
                    else:
                        self.print_usage()
                    sys.exit()

        if not HAVE_TAGPY:
            print _("Taglib and/or tagpy not found, tag editing support disabled.")
        if not HAVE_WSDL:
            print _("ZSI not found, fetching lyrics support disabled.")
        if not HAVE_EGG and not HAVE_STATUS_ICON:
            print _("PyGTK+ 2.10 or gnome-python-extras not found, system tray support disabled.")
        if not HAVE_AUDIOSCROBBLER:
            print _("Python 2.5 or python-elementtree not found, audioscrobbler support disabled.")

        start_dbus_interface(toggle_arg)

        self.gnome_session_management()

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
        self.currentformat = "%A - %T"
        self.libraryformat = "%A - %T"
        self.titleformat = "[Sonata] %A - %T"
        self.currsongformat1 = "%T"
        self.currsongformat2 = _("by") + " %A " + _("from") + " %B"
        self.columnwidths = []
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
        self.play_on_activate = False
        self.view = self.VIEW_FILESYSTEM
        self.view_artist_artist = ''
        self.view_artist_album = ''
        self.view_artist_level = 1
        self.view_artist_level_prev = 0
        self.songs = None
        self.tagpy_is_91 = None
        self.art_location = self.ART_LOCATION_HOMECOVERS
        self.art_location_custom_filename = ""
        self.lyrics_location = self.LYRICS_LOCATION_HOME
        self.filterbox_visible = False
        self.edit_style_orig = None
        self.reset_artist_for_album_name()
        self.use_scrobbler = False
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
        # For increased responsiveness after the initial load, we cache the root artist and
        # album view results and simply refresh on any mpd update
        self.albums_root = None
        self.artists_root = None
        # If the connection to MPD times out, this will cause the interface to freeze while
        # the socket.connect() calls are repeatedly executed. Therefore, if we were not
        # able to make a connection, slow down the iteration check to once every 15 seconds.
        # Eventually we'd like to ues non-blocking sockets in mpdclient3.py
        self.iterate_time_when_connected = 500
        self.iterate_time_when_disconnected_or_stopped = 1000 # Slow down polling when disconnected stopped

        try:
            self.enc = locale.getpreferredencoding()
        except:
            print "Locale cannot be found; please set your system's locale. Aborting..."
            sys.exit()

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

        # Add some icons:
        self.iconfactory = gtk.IconFactory()
        self.new_icon('sonata', file='sonata.png')
        self.new_icon('artist', file='sonata-artist.png')
        self.new_icon('album', file='sonata-album.png')
        icon_theme = gtk.icon_theme_get_default()
        if HAVE_SUGAR:
            activity_root = activity.get_bundle_path()
            icon_theme.append_search_path(os.path.join(activity_root, 'share'))
        (img_width, img_height) = gtk.icon_size_lookup(VOLUME_ICON_SIZE)
        for iconname in ('stock_volume-mute', 'stock_volume-min', 'stock_volume-med', 'stock_volume-max'):
            try:
                self.new_icon(iconname, fullpath=icon_theme.lookup_icon(iconname, img_width, gtk.ICON_LOOKUP_USE_BUILTIN).get_filename())
            except:
                # Fallback to Sonata-included icons:
                self.new_icon(iconname, file='sonata-'+iconname+'.png')

        # Popup menus:
        actions = (
            ('sortmenu', None, _('_Sort List')),
            ('playlistmenu', None, _('Sa_ve List to')),
            ('profilesmenu', None, _('_Connection')),
            ('filesystemview', gtk.STOCK_HARDDISK, _('Filesystem'), None, None, self.on_libraryview_chosen),
            ('artistview', 'artist', _('Artist'), None, None, self.on_libraryview_chosen),
            ('albumview', 'album', _('Album'), None, None, self.on_libraryview_chosen),
            ('chooseimage_menu', gtk.STOCK_CONVERT, _('Use _Remote Image...'), None, None, self.on_choose_image),
            ('localimage_menu', gtk.STOCK_OPEN, _('Use _Local Image...'), None, None, self.on_choose_image_local),
            ('resetimage_menu', gtk.STOCK_CLEAR, _('Reset to Default'), None, None, self.on_reset_image),
            ('playmenu', gtk.STOCK_MEDIA_PLAY, _('_Play'), None, None, self.pp),
            ('pausemenu', gtk.STOCK_MEDIA_PAUSE, _('_Pause'), None, None, self.pp),
            ('stopmenu', gtk.STOCK_MEDIA_STOP, _('_Stop'), None, None, self.stop),
            ('prevmenu', gtk.STOCK_MEDIA_PREVIOUS, _('_Previous'), None, None, self.prev),
            ('nextmenu', gtk.STOCK_MEDIA_NEXT, _('_Next'), None, None, self.next),
            ('quitmenu', gtk.STOCK_QUIT, _('_Quit'), None, None, self.on_delete_event_yes),
            ('removemenu', gtk.STOCK_REMOVE, _('_Remove'), None, None, self.remove),
            ('clearmenu', gtk.STOCK_CLEAR, _('_Clear'), '<Ctrl>Delete', None, self.clear),
            ('savemenu', None, _('_New Playlist...'), '<Ctrl><Shift>s', None, self.on_playlist_save),
            ('updatemenu', None, _('_Update Library'), None, None, self.updatedb),
            ('preferencemenu', gtk.STOCK_PREFERENCES, _('_Preferences...'), 'F5', None, self.prefs),
            ('aboutmenu', None, _('_About...'), 'F1', None, self.about),
            ('newmenu', None, _('_New...'), '<Ctrl>n', None, self.streams_new),
            ('editmenu', None, _('_Edit...'), None, None, self.streams_edit),
            ('renamemenu', None, _('_Rename...'), None, None, self.on_playlist_rename),
            ('edittagmenu', None, _('_Edit Tags...'), '<Ctrl>t', None, self.edit_tags),
            ('addmenu', gtk.STOCK_ADD, _('_Add'), '<Ctrl>d', None, self.add_item),
            ('replacemenu', gtk.STOCK_REDO, _('_Replace'), '<Ctrl>r', None, self.replace_item),
            ('rmmenu', None, _('_Delete...'), None, None, self.remove),
            ('sortbyartist', None, _('By Artist'), None, None, self.on_sort_by_artist),
            ('sortbyalbum', None, _('By Album'), None, None, self.on_sort_by_album),
            ('sortbytitle', None, _('By Song Title'), None, None, self.on_sort_by_title),
            ('sortbyfile', None, _('By File Name'), None, None, self.on_sort_by_file),
            ('sortbydirfile', None, _('By Dir & File Name'), None, None, self.on_sort_by_dirfile),
            ('sortreverse', None, _('Reverse List'), None, None, self.on_sort_reverse),
            ('sortrandom', None, _('Random'), '<Alt>r', None, self.on_sort_random),
            ('tab1key', None, 'Tab1 Key', '<Alt>1', None, self.switch_to_tab1),
            ('tab2key', None, 'Tab2 Key', '<Alt>2', None, self.switch_to_tab2),
            ('tab3key', None, 'Tab3 Key', '<Alt>3', None, self.switch_to_tab3),
            ('tab4key', None, 'Tab4 Key', '<Alt>4', None, self.switch_to_tab4),
            ('tab5key', None, 'Tab5 Key', '<Alt>5', None, self.switch_to_tab5),
            ('expandkey', None, 'Expand Key', '<Alt>Down', None, self.on_expand),
            ('collapsekey', None, 'Collapse Key', '<Alt>Up', None, self.on_collapse),
            ('ppkey', None, 'Play/Pause Key', '<Ctrl>p', None, self.pp),
            ('stopkey', None, 'Stop Key', '<Ctrl>s', None, self.stop),
            ('prevkey', None, 'Previous Key', '<Ctrl>Left', None, self.prev),
            ('nextkey', None, 'Next Key', '<Ctrl>Right', None, self.next),
            ('lowerkey', None, 'Lower Volume Key', '<Ctrl>minus', None, self.volume_lower),
            ('raisekey', None, 'Raise Volume Key', '<Ctrl>plus', None, self.volume_raise),
            ('raisekey2', None, 'Raise Volume Key 2', '<Ctrl>equal', None, self.volume_raise),
            ('quitkey', None, 'Quit Key', '<Ctrl>q', None, self.on_delete_event_yes),
            ('quitkey2', None, 'Quit Key 2', '<Ctrl>w', None, self.on_delete_event_yes),
            ('updatekey', None, 'Update Key', '<Ctrl>u', None, self.updatedb),
            ('updatekey2', None, 'Update Key 2', '<Ctrl><Shift>u', None, self.updatedb_path),
            ('connectkey', None, 'Connect Key', '<Alt>c', None, self.connectkey_pressed),
            ('disconnectkey', None, 'Disconnect Key', '<Alt>d', None, self.disconnectkey_pressed),
            ('centerplaylistkey', None, 'Center Playlist Key', '<Ctrl>i', None, self.center_playlist),
            ('searchkey', None, 'Search Key', '<Ctrl>h', None, self.searchkey_pressed),
            )

        toggle_actions = (
            ('showmenu', None, _('_Show Sonata'), None, None, self.withdraw_app_toggle, not self.withdrawn),
            ('repeatmenu', None, _('_Repeat'), None, None, self.on_repeat_clicked, False),
            ('shufflemenu', None, _('_Shuffle'), None, None, self.on_shuffle_clicked, False),
            (self.TAB_CURRENT, None, self.TAB_CURRENT, None, None, self.tab_toggle, self.current_tab_visible),
            (self.TAB_LIBRARY, None, self.TAB_LIBRARY, None, None, self.tab_toggle, self.library_tab_visible),
            (self.TAB_PLAYLISTS, None, self.TAB_PLAYLISTS, None, None, self.tab_toggle, self.playlists_tab_visible),
            (self.TAB_STREAMS, None, self.TAB_STREAMS, None, None, self.tab_toggle, self.streams_tab_visible),
            (self.TAB_INFO, None, self.TAB_INFO, None, None, self.tab_toggle, self.info_tab_visible),
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
                <menuitem action="newmenu"/>
                <menuitem action="editmenu"/>
                <menuitem action="removemenu"/>
                <menuitem action="clearmenu"/>
                <menuitem action="edittagmenu"/>
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
                <menu action="playlistmenu">
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
        self.connect(blocking=True)
        if self.conn:
            self.status = self.conn.do.status()
            self.iterate_time = self.iterate_time_when_connected
            try:
                test = self.status.state
            except:
                self.status = None
            try:
                self.songinfo = self.conn.do.currentsong()
            except:
                self.songinfo = None
        else:
            if self.initial_run:
                show_prefs = True
            self.iterate_time = self.iterate_time_when_disconnected_or_stopped
            self.status = None
            self.songinfo = None

        # Audioscrobbler
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
        self.imageeventbox = gtk.EventBox()
        self.imageeventbox.set_visible_window(False)
        self.imageeventbox.drag_dest_set(gtk.DEST_DEFAULT_HIGHLIGHT | gtk.DEST_DEFAULT_DROP, [("text/uri-list", 0, 80)], gtk.gdk.ACTION_DEFAULT)
        self.albumimage = gtk.Image()
        self.imageeventbox.add(self.albumimage)
        if not self.show_covers:
            self.imageeventbox.set_no_show_all(True)
            self.imageeventbox.hide()
        tophbox.pack_start(self.imageeventbox, False, False, 5)
        topvbox = gtk.VBox()
        toptophbox = gtk.HBox()
        self.prevbutton = gtk.Button("", gtk.STOCK_MEDIA_PREVIOUS, True)
        self.ppbutton = gtk.Button("", gtk.STOCK_MEDIA_PLAY, True)
        self.stopbutton = gtk.Button("", gtk.STOCK_MEDIA_STOP, True)
        self.nextbutton = gtk.Button("", gtk.STOCK_MEDIA_NEXT, True)
        for mediabutton in (self.prevbutton, self.ppbutton, self.stopbutton, self.nextbutton):
            mediabutton.set_relief(gtk.RELIEF_NONE)
            mediabutton.set_property('can-focus', False)
            mediabutton.get_child().get_child().get_children()[1].set_text('')
            toptophbox.pack_start(mediabutton, False, False, 0)
            if not self.show_playback:
                mediabutton.set_no_show_all(True)
                mediabutton.hide()
        self.progressbox = gtk.VBox()
        self.progresslabel = gtk.Label()
        self.progresslabel.set_size_request(-1, 6)
        self.progressbox.pack_start(self.progresslabel)
        self.progresseventbox = gtk.EventBox()
        self.progressbar = gtk.ProgressBar()
        self.progressbar.set_orientation(gtk.PROGRESS_LEFT_TO_RIGHT)
        self.progressbar.set_fraction(0)
        self.progressbar.set_pulse_step(0.05)
        self.progressbar.set_ellipsize(pango.ELLIPSIZE_END)
        self.progresseventbox.add(self.progressbar)
        self.progressbox.pack_start(self.progresseventbox, False, False, 0)
        self.progresslabel2 = gtk.Label()
        self.progresslabel2.set_size_request(-1, 6)
        self.progressbox.pack_start(self.progresslabel2)
        toptophbox.pack_start(self.progressbox, True, True, 0)
        if not self.show_progress:
            self.progressbox.set_no_show_all(True)
            self.progressbox.hide()
        self.volumebutton = gtk.ToggleButton("", True)
        self.volumebutton.set_relief(gtk.RELIEF_NONE)
        self.volumebutton.set_property('can-focus', False)
        self.set_volumebutton("stock_volume-med")
        if not self.show_playback:
            self.volumebutton.set_no_show_all(True)
            self.volumebutton.hide()
        toptophbox.pack_start(self.volumebutton, False, False, 0)
        topvbox.pack_start(toptophbox, False, False, 2)
        self.expander = gtk.Expander(_("Playlist"))
        self.expander.set_expanded(self.expanded)
        self.expander.set_property('can-focus', False)
        expanderbox = gtk.VBox()
        self.cursonglabel1 = gtk.Label()
        self.cursonglabel2 = gtk.Label()
        self.cursonglabel1.set_alignment(0, 0)
        self.cursonglabel2.set_alignment(0, 0)
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
        self.expanderwindow = gtk.ScrolledWindow()
        self.expanderwindow.set_policy(gtk.POLICY_AUTOMATIC, gtk.POLICY_AUTOMATIC)
        self.expanderwindow.set_shadow_type(gtk.SHADOW_IN)
        self.current = gtk.TreeView()
        self.current.set_rules_hint(True)
        self.current.set_reorderable(True)
        self.current.set_enable_search(False)
        self.current_selection = self.current.get_selection()
        self.expanderwindow.add(self.current)
        self.filterpattern = gtk.Entry()
        self.filterbox = gtk.HBox()
        self.filterbox.pack_start(gtk.Label(_("Filter") + ":"), False, False, 5)
        self.filterbox.pack_start(self.filterpattern, True, True, 5)
        filterclosebutton = gtk.Button()
        filterclosebutton.set_image(gtk.image_new_from_stock(gtk.STOCK_CLOSE, gtk.ICON_SIZE_MENU))
        filterclosebutton.set_relief(gtk.RELIEF_NONE)
        self.filterbox.pack_start(filterclosebutton, False, False, 0)
        self.filterbox.set_no_show_all(True)
        vbox_current = gtk.VBox()
        vbox_current.pack_start(self.expanderwindow, True, True)
        vbox_current.pack_start(self.filterbox, False, False, 5)
        playlistevbox = gtk.EventBox()
        playlistevbox.set_visible_window(False)
        playlisthbox = gtk.HBox()
        playlisthbox.pack_start(gtk.image_new_from_stock(gtk.STOCK_CDROM, gtk.ICON_SIZE_MENU), False, False, 2)
        playlisthbox.pack_start(gtk.Label(str=self.TAB_CURRENT), False, False, 2)
        playlistevbox.add(playlisthbox)
        playlistevbox.show_all()
        playlistevbox.connect("button_press_event", self.on_tab_click)
        self.notebook.append_page(vbox_current, playlistevbox)
        current_tab = self.notebook.get_children()[0]
        if not self.current_tab_visible:
            current_tab.set_no_show_all(True)
            current_tab.hide_all()
        # Library tab
        browservbox = gtk.VBox()
        expanderwindow2 = gtk.ScrolledWindow()
        expanderwindow2.set_policy(gtk.POLICY_AUTOMATIC, gtk.POLICY_AUTOMATIC)
        expanderwindow2.set_shadow_type(gtk.SHADOW_IN)
        self.browser = gtk.TreeView()
        self.browser.set_headers_visible(False)
        self.browser.set_rules_hint(True)
        self.browser.set_reorderable(False)
        self.browser.set_enable_search(True)
        self.browser_selection = self.browser.get_selection()
        expanderwindow2.add(self.browser)
        self.searchbox = gtk.HBox()
        self.searchcombo = gtk.combo_box_new_text()
        for item in self.search_terms:
            self.searchcombo.append_text(item)
        self.searchtext = gtk.Entry()
        self.searchbutton = gtk.Button(_('_End Search'))
        self.searchbutton.set_image(gtk.image_new_from_stock(gtk.STOCK_CLOSE, gtk.ICON_SIZE_MENU))
        self.searchbutton.set_size_request(-1, self.searchcombo.size_request()[1])
        self.searchbutton.set_no_show_all(True)
        self.searchbutton.hide()
        self.libraryview = gtk.Button()
        self.tooltips.set_tip(self.libraryview, _("Library browsing view"))
        self.libraryview_assign_image()
        self.libraryview.set_relief(gtk.RELIEF_NONE)
        self.librarymenu.attach_to_widget(self.libraryview, None)
        self.searchbox.pack_start(self.libraryview, False, False, 1)
        self.searchbox.pack_start(gtk.VSeparator(), False, False, 0)
        self.searchbox.pack_start(self.searchcombo, False, False, 2)
        self.searchbox.pack_start(self.searchtext, True, True, 2)
        self.searchbox.pack_start(self.searchbutton, False, False, 2)
        browservbox.pack_start(expanderwindow2, True, True, 2)
        browservbox.pack_start(self.searchbox, False, False, 2)
        libraryevbox = gtk.EventBox()
        libraryevbox.set_visible_window(False)
        libraryhbox = gtk.HBox()
        libraryhbox.pack_start(gtk.image_new_from_stock(gtk.STOCK_HARDDISK, gtk.ICON_SIZE_MENU), False, False, 2)
        libraryhbox.pack_start(gtk.Label(str=self.TAB_LIBRARY), False, False, 2)
        libraryevbox.add(libraryhbox)
        libraryevbox.show_all()
        libraryevbox.connect("button_press_event", self.on_tab_click)
        self.notebook.append_page(browservbox, libraryevbox)
        library_tab = self.notebook.get_children()[1]
        if not self.library_tab_visible:
            library_tab.set_no_show_all(True)
            library_tab.hide_all()
        # Playlists tab
        expanderwindow3 = gtk.ScrolledWindow()
        expanderwindow3.set_policy(gtk.POLICY_AUTOMATIC, gtk.POLICY_AUTOMATIC)
        expanderwindow3.set_shadow_type(gtk.SHADOW_IN)
        self.playlists = gtk.TreeView()
        self.playlists.set_headers_visible(False)
        self.playlists.set_rules_hint(True)
        self.playlists.set_reorderable(False)
        self.playlists.set_enable_search(True)
        self.playlists_selection = self.playlists.get_selection()
        expanderwindow3.add(self.playlists)
        playlistsevbox = gtk.EventBox()
        playlistsevbox.set_visible_window(False)
        playlistshbox = gtk.HBox()
        playlistshbox.pack_start(gtk.image_new_from_stock(gtk.STOCK_JUSTIFY_CENTER, gtk.ICON_SIZE_MENU), False, False, 2)
        playlistshbox.pack_start(gtk.Label(str=self.TAB_PLAYLISTS), False, False, 2)
        playlistsevbox.add(playlistshbox)
        playlistsevbox.show_all()
        playlistsevbox.connect("button_press_event", self.on_tab_click)
        self.notebook.append_page(expanderwindow3, playlistsevbox)
        playlists_tab = self.notebook.get_children()[2]
        if not self.playlists_tab_visible:
            playlists_tab.set_no_show_all(True)
            playlists_tab.hide_all()
        # Streams tab
        expanderwindow4 = gtk.ScrolledWindow()
        expanderwindow4.set_policy(gtk.POLICY_AUTOMATIC, gtk.POLICY_AUTOMATIC)
        expanderwindow4.set_shadow_type(gtk.SHADOW_IN)
        self.streams = gtk.TreeView()
        self.streams.set_headers_visible(False)
        self.streams.set_rules_hint(True)
        self.streams.set_reorderable(False)
        self.streams.set_enable_search(True)
        self.streams_selection = self.streams.get_selection()
        expanderwindow4.add(self.streams)
        streamsevbox = gtk.EventBox()
        streamsevbox.set_visible_window(False)
        streamshbox = gtk.HBox()
        streamshbox.pack_start(gtk.image_new_from_stock(gtk.STOCK_NETWORK, gtk.ICON_SIZE_MENU), False, False, 2)
        streamshbox.pack_start(gtk.Label(str=self.TAB_STREAMS), False, False, 2)
        streamsevbox.add(streamshbox)
        streamsevbox.show_all()
        streamsevbox.connect("button_press_event", self.on_tab_click)
        self.notebook.append_page(expanderwindow4, streamsevbox)
        streams_tab = self.notebook.get_children()[3]
        if not self.streams_tab_visible:
            streams_tab.set_no_show_all(True)
            streams_tab.hide_all()
        # Info tab
        info = gtk.ScrolledWindow()
        info.set_policy(gtk.POLICY_AUTOMATIC, gtk.POLICY_AUTOMATIC)
        info.set_shadow_type(gtk.SHADOW_IN)
        infoevbox = gtk.EventBox()
        infoevbox.set_visible_window(False)
        infohbox = gtk.HBox()
        infohbox.pack_start(gtk.image_new_from_stock(gtk.STOCK_JUSTIFY_FILL, gtk.ICON_SIZE_MENU), False, False, 2)
        infohbox.pack_start(gtk.Label(str=self.TAB_INFO), False, False, 2)
        infoevbox.add(infohbox)
        infoevbox.show_all()
        infoevbox.connect("button_press_event", self.on_tab_click)
        self.info_widgets_initialize(info)
        self.notebook.append_page(info, infoevbox)
        mainvbox.pack_start(self.notebook, True, True, 5)
        info_tab = self.notebook.get_children()[4]
        if not self.info_tab_visible:
            info_tab.set_no_show_all(True)
            info_tab.hide_all()
        self.statusbar = gtk.Statusbar()
        self.statusbar.set_has_resize_grip(True)
        if not self.show_statusbar or not self.expanded:
            self.statusbar.hide()
            self.statusbar.set_no_show_all(True)
        mainvbox.pack_start(self.statusbar, False, False, 0)
        mainhbox.pack_start(mainvbox, True, True, 3)
        if self.window_owner:
            self.window.add(mainhbox)
            self.window.move(self.x, self.y)
            self.window.set_size_request(270, -1)
        elif HAVE_SUGAR:
            self.window.set_canvas(mainhbox)
        if not self.expanded:
            self.notebook.set_no_show_all(True)
            self.notebook.hide()
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
        self.tooltips.set_tip(self.libraryview, _("Library browsing view"))
        if gtk.pygtk_version >= (2, 10, 0):
            for child in self.notebook.get_children():
                self.notebook.set_tab_reorderable(child, True)
        # Update tab positions:
        self.notebook.reorder_child(current_tab, self.current_tab_pos)
        self.notebook.reorder_child(library_tab, self.library_tab_pos)
        self.notebook.reorder_child(playlists_tab, self.playlists_tab_pos)
        self.notebook.reorder_child(streams_tab, self.streams_tab_pos)
        self.notebook.reorder_child(info_tab, self.info_tab_pos)

        # Systray:
        outtertipbox = gtk.VBox()
        tipbox = gtk.HBox()
        self.trayalbumeventbox = gtk.EventBox()
        self.trayalbumeventbox.set_size_request(59, 90)
        self.trayalbumimage1 = gtk.Image()
        self.trayalbumimage1.set_size_request(51, 77)
        self.trayalbumimage1.set_alignment(1, 0.5)
        self.trayalbumeventbox.add(self.trayalbumimage1)
        self.trayalbumeventbox.set_state(gtk.STATE_SELECTED)
        hiddenlbl = gtk.Label()
        hiddenlbl.set_size_request(2, -1)
        tipbox.pack_start(hiddenlbl, False, False, 0)
        tipbox.pack_start(self.trayalbumeventbox, False, False, 0)
        self.trayalbumimage2 = gtk.Image()
        self.trayalbumimage2.set_size_request(26, 77)
        tipbox.pack_start(self.trayalbumimage2, False, False, 0)
        if not self.show_covers:
            self.trayalbumeventbox.set_no_show_all(True)
            self.trayalbumeventbox.hide()
            self.trayalbumimage2.set_no_show_all(True)
            self.trayalbumimage2.hide()
        innerbox = gtk.VBox()
        self.traycursonglabel1 = gtk.Label()
        self.traycursonglabel1.set_markup(_("Playlist"))
        self.traycursonglabel1.set_alignment(0, 1)
        self.traycursonglabel2 = gtk.Label()
        self.traycursonglabel2.set_markup(_("Playlist"))
        self.traycursonglabel2.set_alignment(0, 0)
        label1 = gtk.Label()
        label1.set_markup('<span size="10"> </span>')
        innerbox.pack_start(label1)
        innerbox.pack_start(self.traycursonglabel1, True, True, 0)
        innerbox.pack_start(self.traycursonglabel2, True, True, 0)
        self.trayprogressbar = gtk.ProgressBar()
        self.trayprogressbar.set_orientation(gtk.PROGRESS_LEFT_TO_RIGHT)
        self.trayprogressbar.set_fraction(0)
        self.trayprogressbar.set_pulse_step(0.05)
        self.trayprogressbar.set_ellipsize(pango.ELLIPSIZE_NONE)
        label2 = gtk.Label()
        label2.set_markup('<span size="10"> </span>')
        innerbox.pack_start(label2)
        innerbox.pack_start(self.trayprogressbar, False, False, 0)
        if not self.show_progress:
            self.trayprogressbar.set_no_show_all(True)
            self.trayprogressbar.hide()
        label3 = gtk.Label()
        label3.set_markup('<span size="10"> </span>')
        innerbox.pack_start(label3)
        tipbox.pack_start(innerbox, True, True, 6)
        outtertipbox.pack_start(tipbox, False, False, 2)
        outtertipbox.show_all()
        self.traytips.add_widget(outtertipbox)
        self.set_notification_window_width()

        # Volumescale window
        self.volumewindow = gtk.Window(gtk.WINDOW_POPUP)
        self.volumewindow.set_skip_taskbar_hint(True)
        self.volumewindow.set_skip_pager_hint(True)
        self.volumewindow.set_decorated(False)
        frame = gtk.Frame()
        frame.set_shadow_type(gtk.SHADOW_ETCHED_IN)
        self.volumewindow.add(frame)
        volbox = gtk.VBox()
        volbox.pack_start(gtk.Label("+"), False, False, 0)
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
        volbox.pack_start(gtk.Label("-"), False, False, 0)
        frame.add(volbox)
        frame.show_all()

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
        self.ppbutton.connect('clicked', self.pp)
        self.stopbutton.connect('clicked', self.stop)
        self.prevbutton.connect('clicked', self.prev)
        self.nextbutton.connect('clicked', self.next)
        self.progresseventbox.connect('button_press_event', self.on_progressbar_button_press_event)
        self.progresseventbox.connect('scroll_event', self.on_progressbar_scroll_event)
        self.volumebutton.connect('clicked', self.on_volumebutton_clicked)
        self.volumebutton.connect('scroll-event', self.on_volumebutton_scroll)
        self.expander.connect('activate', self.on_expander_activate)
        self.current.connect('drag_data_received', self.on_drag_drop)
        self.current.connect('row_activated', self.on_current_click)
        self.current.connect('button_press_event', self.on_current_button_press)
        self.current.connect('drag-begin', self.on_current_drag_begin)
        self.current.connect_after('drag-begin', self.after_current_drag_begin)
        self.current.connect('button_release_event', self.on_current_button_release)
        self.current_selection.connect('changed', self.on_treeview_selection_changed)
        self.current.connect('popup_menu', self.on_popup_menu)
        self.shufflemenu.connect('toggled', self.on_shuffle_clicked)
        self.repeatmenu.connect('toggled', self.on_repeat_clicked)
        self.volumescale.connect('change_value', self.on_volumescale_change)
        self.volumescale.connect('scroll-event', self.on_volumescale_scroll)
        self.cursonglabel1.connect('notify::label', self.labelnotify)
        self.progressbar.connect('notify::fraction', self.progressbarnotify_fraction)
        self.progressbar.connect('notify::text', self.progressbarnotify_text)
        self.browser.connect('row_activated', self.on_browse_row)
        self.browser.connect('button_press_event', self.on_browser_button_press)
        self.browser.connect('key-press-event', self.on_browser_key_press)
        self.browser_selection.connect('changed', self.on_treeview_selection_changed)
        self.browser.connect('popup_menu', self.on_popup_menu)
        self.libraryview.connect('clicked', self.libraryview_popup)
        self.playlists.connect('button_press_event', self.on_playlists_button_press)
        self.playlists.connect('row_activated', self.playlists_activated)
        self.playlists_selection.connect('changed', self.on_treeview_selection_changed)
        self.playlists.connect('key-press-event', self.playlists_key_press)
        self.playlists.connect('popup_menu', self.on_popup_menu)
        self.streams.connect('button_press_event', self.on_streams_button_press)
        self.streams.connect('row_activated', self.on_streams_activated)
        self.streams_selection.connect('changed', self.on_treeview_selection_changed)
        self.streams.connect('key-press-event', self.on_streams_key_press)
        self.streams.connect('popup_menu', self.on_popup_menu)
        self.ppbutton.connect('button_press_event', self.popup_menu)
        self.prevbutton.connect('button_press_event', self.popup_menu)
        self.stopbutton.connect('button_press_event', self.popup_menu)
        self.nextbutton.connect('button_press_event', self.popup_menu)
        self.progresseventbox.connect('button_press_event', self.popup_menu)
        self.expander.connect('button_press_event', self.popup_menu)
        self.volumebutton.connect('button_press_event', self.popup_menu)
        self.mainwinhandler = self.window.connect('button_press_event', self.on_window_click)
        self.searchcombo.connect('changed', self.on_search_combo_change)
        self.searchtext.connect('activate', self.on_search_activate)
        self.searchbutton.connect('clicked', self.on_search_end)
        self.notebook.connect('button_press_event', self.on_notebook_click)
        self.notebook.connect('size-allocate', self.on_notebook_resize)
        self.notebook.connect('switch-page', self.on_notebook_page_change)
        self.searchtext.connect('button_press_event', self.on_searchtext_click)
        self.filter_changed_handler = self.filterpattern.connect('changed', self.searchfilter_feed_loop)
        self.filterpattern.connect('activate', self.searchfilter_on_enter)
        self.filterpattern.connect('key-press-event', self.searchfilter_key_pressed)
        filterclosebutton.connect('clicked', self.searchfilter_toggle)

        self.initialize_systrayicon()

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
            self.keys.connect("mm_prev", self.mmprev)
            self.keys.connect("mm_next", self.mmnext)
            self.keys.connect("mm_playpause", self.mmpp)
            self.keys.connect("mm_stop", self.mmstop)

        # Put blank cd to albumimage widget by default
        self.albumimage.set_from_file(self.sonatacd)

        # Set up current view
        self.parse_currentformat()
        self.current_selection.set_mode(gtk.SELECTION_MULTIPLE)
        self.current.enable_model_drag_source(gtk.gdk.BUTTON1_MASK, [('STRING', 0, 0)], gtk.gdk.ACTION_MOVE)
        self.current.enable_model_drag_dest([('STRING', 0, 0)], gtk.gdk.ACTION_MOVE)

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

        # Initialize browser data and widget
        self.browserposition = {}
        self.browserselectedpath = {}
        self.searchcombo.set_active(self.last_search_num)
        self.prevstatus = None
        self.browserdata = gtk.ListStore(str, str, str)
        self.browser.set_model(self.browserdata)
        self.browser.set_search_column(2)
        self.browsercell = gtk.CellRendererText()
        self.browsercell.set_property("ellipsize", pango.ELLIPSIZE_END)
        self.browserimg = gtk.CellRendererPixbuf()
        self.browsercolumn = gtk.TreeViewColumn()
        self.browsercolumn.pack_start(self.browserimg, False)
        self.browsercolumn.pack_start(self.browsercell, True)
        self.browsercolumn.set_attributes(self.browserimg, stock_id=0)
        self.browsercolumn.set_attributes(self.browsercell, markup=2)
        self.browsercolumn.set_sizing(gtk.TREE_VIEW_COLUMN_FIXED)
        self.browser.append_column(self.browsercolumn)
        self.browser_selection.set_mode(gtk.SELECTION_MULTIPLE)
        self.browser.set_fixed_height_mode(True)

        if self.window_owner:
            icon = self.window.render_icon('sonata', gtk.ICON_SIZE_DIALOG)
            self.window.set_icon(icon)

        self.streams_populate()

        self.iterate_now()
        if self.window_owner:
            if self.withdrawn:
                if (HAVE_EGG and self.trayicon.get_property('visible')) or (HAVE_STATUS_ICON and self.statusicon.is_embedded() and self.statusicon.get_visible()):
                    self.window.set_no_show_all(True)
                    self.window.hide()
        self.window.show_all()

        # Ensure that button images are displayed despite GTK+ theme
        self.window.get_settings().set_property("gtk-button-images", True)

        if self.update_on_start:
            self.updatedb(None)

        self.notebook.set_no_show_all(False)
        self.window.set_no_show_all(False)

        if show_prefs:
            self.prefs(None)

        self.initial_run = False

        # Ensure that sonata is loaded before we display the notif window
        self.sonata_loaded = True
        self.labelnotify()
        self.keep_song_centered_in_list()

        if HAVE_STATUS_ICON:
            gobject.timeout_add(250, self.iterate_status_icon)

        gc.disable()

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
        print "  -v, --version        " + _("Show version information and exit")
        print "  -t, --toggle         " + _("Toggles whether the app is minimized")
        print "                       " + _("to tray or visible (requires D-Bus)")
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
        info_song = gtk.Expander()
        info_song.set_property("can-focus", False)
        info_song.set_expanded(self.info_song_expanded)
        info_song.connect("activate", self.info_expanded, "song")
        songinfolabel = gtk.Label()
        songinfolabel.set_markup("<b>" + _("Song Info") + "</b>")
        info_song.set_label_widget(songinfolabel)
        inner_hbox = gtk.HBox()
        self.info_imagebox = gtk.EventBox()
        self.info_imagebox.set_visible_window(False)
        self.info_imagebox.drag_dest_set(gtk.DEST_DEFAULT_HIGHLIGHT | gtk.DEST_DEFAULT_DROP, [("text/uri-list", 0, 80)], gtk.gdk.ACTION_DEFAULT)
        self.info_image = gtk.Image()
        self.info_image.set_alignment(0.5, 0)
        self.info_imagebox.connect('button_press_event', self.on_image_activate)
        self.info_imagebox.connect('drag_motion', self.on_image_motion_cb)
        self.info_imagebox.connect('drag_data_received', self.on_image_drop_cb)
        self.info_imagebox.add(self.info_image)
        if self.info_art_enlarged:
            self.info_imagebox.set_size_request(-1, -1)
        else:
            self.info_imagebox.set_size_request(152, -1)
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
            tmplabel = gtk.Label()
            if i == 0:
                self.info_left_label = tmplabel
            tmplabel2 = gtk.Label("")
            if labels_link[i]:
                tmpevbox = gtk.EventBox()
                tmpevbox.set_visible_window(False)
                self.info_apply_link_signals(tmpevbox, labels_type[i], labels_tooltip[i])
                tmpevbox.add(tmplabel2)
            tmplabel.set_markup("<b>" + labels_text[i] + ":</b>")
            tmplabel.set_alignment(0, 0)
            tmphbox.pack_start(tmplabel, False, False, horiz_spacing)
            if labels_link[i]:
                tmphbox.pack_start(tmpevbox, False, False, horiz_spacing)
            else:
                tmphbox.pack_start(tmplabel2, False, False, horiz_spacing)
            self.info_labels += [tmplabel2]
            labels_left += [tmplabel]
            tmplabel2.set_alignment(0, 0)
            tmplabel2.set_line_wrap(True)
            try: # Only recent versions of pygtk/gtk have this
                tmplabel2.set_line_wrap_mode(pango.WRAP_WORD_CHAR)
            except:
                pass
            if not labels_link[i]:
                tmplabel2.set_selectable(True)
            else:
                # Using set_selectable overrides the hover cursor that sonata
                # tries to set for the links, and I can't figure out how to
                # stop that. So we'll disable set_selectable for these two
                # labels until it's figured out.
                tmplabel2.set_selectable(False)
            self.info_tagbox.pack_start(tmphbox, False, False, vert_spacing)
        self.set_label_widths_equal(labels_left)

        mischbox = gtk.HBox()
        moreevbox = gtk.EventBox()
        moreevbox.set_visible_window(False)
        self.info_morelabel = gtk.Label()
        self.info_morelabel.set_alignment(0, 0)
        self.info_apply_link_signals(moreevbox, 'more', _("Toggle extra tags"))
        moreevbox.add(self.info_morelabel)
        editevbox = gtk.EventBox()
        editevbox.set_visible_window(False)
        self.info_editlabel = gtk.Label()
        self.info_editlabel.set_alignment(0, 0)
        self.info_apply_link_signals(editevbox, 'edit', _("Edit song tags"))
        editevbox.add(self.info_editlabel)
        mischbox.pack_start(moreevbox, False, False, horiz_spacing)
        mischbox.pack_start(editevbox, False, False, horiz_spacing)

        self.info_tagbox.pack_start(mischbox, False, False, vert_spacing)
        inner_hbox.pack_start(self.info_tagbox, False, False, horiz_spacing)
        info_song.add(inner_hbox)
        outter_vbox.pack_start(info_song, False, False, margin)

        # Lyrics
        self.info_lyrics = gtk.Expander()
        self.info_lyrics.set_property("can-focus", False)
        self.info_lyrics.set_expanded(self.info_lyrics_expanded)
        self.info_lyrics.connect("activate", self.info_expanded, "lyrics")
        lyricslabel = gtk.Label()
        lyricslabel.set_markup("<b>" + _("Lyrics") + "</b>")
        self.info_lyrics.set_label_widget(lyricslabel)
        lyricsbox = gtk.VBox()
        lyricsbox_top = gtk.HBox()
        self.lyricsText = gtk.Label()
        self.lyricsText.set_use_markup(True)
        self.lyricsText.set_alignment(0,0)
        self.lyricsText.set_selectable(True)
        self.lyricsText.set_line_wrap(True)
        try: # Only recent versions of pygtk/gtk have this
            self.lyricsText.set_line_wrap_mode(pango.WRAP_WORD_CHAR)
        except:
            pass
        lyricsbox_top.pack_start(self.lyricsText, True, True, horiz_spacing)
        lyricsbox.pack_start(lyricsbox_top, True, True, vert_spacing)
        lyricsbox_bottom = gtk.HBox()
        searchevbox = gtk.EventBox()
        searchevbox.set_visible_window(False)
        self.info_searchlabel = gtk.Label()
        self.info_searchlabel.set_alignment(0, 0)
        self.info_apply_link_signals(searchevbox, 'search', _("Search Lyricwiki.org for lyrics"))
        searchevbox.add(self.info_searchlabel)
        lyricsbox_bottom.pack_start(searchevbox, False, False, horiz_spacing)
        lyricsbox.pack_start(lyricsbox_bottom, False, False, vert_spacing)
        self.info_lyrics.add(lyricsbox)
        outter_vbox.pack_start(self.info_lyrics, False, False, margin)
        # Album info
        info_album = gtk.Expander()
        info_album.set_property("can-focus", False)
        info_album.set_expanded(self.info_album_expanded)
        info_album.connect("activate", self.info_expanded, "album")
        albumlabel = gtk.Label()
        albumlabel.set_markup("<b>" + _("Album Info") + "</b>")
        info_album.set_label_widget(albumlabel)
        albumbox = gtk.VBox()
        albumbox_top = gtk.HBox()
        self.albumText = gtk.Label()
        self.albumText.set_use_markup(True)
        self.albumText.set_alignment(0,0)
        self.albumText.set_selectable(True)
        self.albumText.set_line_wrap(True)
        try: # Only recent versions of pygtk/gtk have this
            self.albumText.set_line_wrap_mode(pango.WRAP_WORD_CHAR)
        except:
            pass
        albumbox_top.pack_start(self.albumText, False, False, horiz_spacing)
        albumbox.pack_start(albumbox_top, False, False, vert_spacing)
        info_album.add(albumbox)
        outter_vbox.pack_start(info_album, False, False, margin)
        # Finish..
        if not self.show_lyrics:
            self.info_lyrics.hide_all()
            self.info_lyrics.set_no_show_all(True)
        if not self.show_covers:
            self.info_imagebox.set_no_show_all(True)
            self.info_imagebox.hide()
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

    def parse_currentformat(self):
        # Initialize current playlist data and widget
        self.columnformat = self.currentformat.split("|")
        self.currentdata = gtk.ListStore(*([int] + [str] * len(self.columnformat)))
        self.current.set_model(self.currentdata)
        cellrenderer = gtk.CellRendererText()
        cellrenderer.set_property("ellipsize", pango.ELLIPSIZE_END)
        self.columns = []
        index = 1
        colnames = self.parse_formatting_for_column_names(self.currentformat)
        if len(self.columnformat) <> len(self.columnwidths):
            # Number of columns changed, set columns equally spaced:
            self.columnwidths = []
            for i in range(len(self.columnformat)):
                self.columnwidths.append(int(self.current.allocation.width/len(self.columnformat)))
        for i in range(len(self.columnformat)):
            column = gtk.TreeViewColumn(colnames[i], cellrenderer, markup=(i+1))
            self.columns += [column]
            column.set_sizing(gtk.TREE_VIEW_COLUMN_FIXED)
            # If just one column, we want it to expand with the tree, so don't set a fixed_width; if
            # multiple columns, size accordingly:
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
        if HAVE_GNOME_UI:
            # Code thanks to quodlibet:
            gnome.init("sonata", __version__)
            client = gnome.ui.master_client()
            client.set_restart_style(gnome.ui.RESTART_IF_RUNNING)
            command = os.path.normpath(os.path.join(os.getcwd(), sys.argv[0]))
            try: client.set_restart_command([command] + sys.argv[1:])
            except TypeError:
                # Fedora systems have a broken gnome-python wrapper for this function.
                # http://www.sacredchao.net/quodlibet/ticket/591
                # http://trac.gajim.org/ticket/929
                client.set_restart_command(len(sys.argv), [command] + sys.argv[1:])
            client.connect('die', gtk.main_quit)

    def single_connect_for_passed_arg(self, type):
        self.user_connect = True
        self.settings_load()
        self.conn = None
        self.connect(blocking=True, force_connection=True)
        if self.conn:
            self.status = self.conn.do.status()
            try:
                test = self.status.state
            except:
                self.status = None
            try:
                self.songinfo = self.conn.do.currentsong()
            except:
                self.songinfo = None
            if type == "play":
                self.conn.do.play()
            elif type == "pause":
                self.conn.do.pause(1)
            elif type == "stop":
                self.conn.do.stop()
            elif type == "next":
                self.conn.do.next()
            elif type == "prev":
                self.conn.do.previous()
            elif type == "shuffle":
                if self.status:
                    if self.status.random == '0':
                        self.conn.do.random(1)
                    elif self.status.random == '1':
                        self.conn.do.random(0)
            elif type == "repeat":
                if self.status:
                    if self.status.repeat == '0':
                        self.conn.do.repeat(1)
                    elif self.status.repeat == '1':
                        self.conn.do.repeat(0)
            elif type == "pp":
                self.status = self.conn.do.status()
                if self.status:
                    if self.status.state in ['play']:
                        self.conn.do.pause(1)
                    elif self.status.state in ['pause', 'stop']:
                        self.conn.do.play()
            elif type == "info":
                if self.status and self.status.state in ['play', 'pause']:
                    print _("Title") + ": " + getattr(self.songinfo, 'title', '')
                    print _("Artist") + ": " + getattr(self.songinfo, 'artist', '')
                    print _("Album") + ": " + getattr(self.songinfo, 'album', '')
                    print _("Date") + ": " + getattr(self.songinfo, 'date', '')
                    print _("Track") + ": " + self.sanitize_mpdtag(getattr(self.songinfo, 'track', '0'), False, 2)
                    print _("Genre") + ": " + getattr(self.songinfo, 'genre', '')
                    print _("File") + ": " + os.path.basename(self.songinfo.file)
                    at, length = [int(c) for c in self.status.time.split(':')]
                    at_time = convert_time(at)
                    try:
                        time = convert_time(int(self.songinfo.time))
                        print _("Time") + ": " + at_time + " / " + time
                    except:
                        print _("Time") + ": " + at_time
                    print _("Bitrate") + ": " + getattr(self.status, 'bitrate', '')
                else:
                    print _("MPD stopped")
            elif type == "status":
                if self.status:
                    try:
                        if self.status.state == 'play':
                            print _("State") + ": " + _("Playing")
                        elif self.status.state == 'pause':
                            print _("State") + ": " + _("Paused")
                        elif self.status.state == 'stop':
                            print _("State") + ": " + _("Stopped")
                        if self.status.repeat == '0':
                            print _("Repeat") + ": " + _("Off")
                        else:
                            print _("Repeat") + ": " + _("On")
                        if self.status.random == '0':
                            print _("Shuffle") + ": " + _("Off")
                        else:
                            print _("Shuffle") + ": " + _("On")
                        print _("Volume") + ": " + self.status.volume + "/100"
                        print _('Crossfade') + ": " + self.status.xfade + ' ' + gettext.ngettext('second', 'seconds', int(self.status.xfade))
                    except:
                        pass
        else:
            print _("Unable to connect to MPD.\nPlease check your Sonata preferences.")

    def new_icon(self, icon_name, file=None, fullpath=None):
        # Either the file or fullpath must be supplied, but not both:
        sonataset = gtk.IconSet()
        if file:
            filename = [self.find_path(file)]
        else:
            filename = [fullpath]
        icons = [gtk.IconSource() for i in filename]
        for i, iconsource in enumerate(icons):
            iconsource.set_filename(filename[i])
            sonataset.add_source(iconsource)
        self.iconfactory.add(icon_name, sonataset)
        self.iconfactory.add_default()

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
            actions.append((action_name, None, unescape_html(playlistinfo[i]), None, None, self.on_playlist_add_songs))
        self.actionGroupPlaylists.add_actions(actions)
        uiDescription = """
            <ui>
              <popup name="mainmenu">
                  <menu action="playlistmenu">
            """
        for i in range(len(playlistinfo)):
            action_name = "Playlist: " + playlistinfo[i].replace("&", "")
            uiDescription = uiDescription + """<menuitem action=\"""" + action_name + """\" position="bottom"/>"""
        uiDescription = uiDescription + """</menu></popup></ui>"""
        self.mergepl_id = self.UIManager.add_ui_from_string(uiDescription)
        self.UIManager.insert_action_group(self.actionGroupPlaylists, 0)
        self.UIManager.get_widget('/hidden').set_property('visible', False)

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
        if not self.sonata_loaded and not self.conn:
            self.actionGroupProfiles.add_radio_actions(actions, len(self.profile_names), self.on_profiles_click)
        else:
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
        self.disconnectkey_pressed(None)
        if current.get_current_value() < len(self.profile_names):
            self.profile_num = current.get_current_value()
            self.connectkey_pressed(None)

    def connect(self, blocking=False, force_connection=False):
        if blocking:
            self.connect2(blocking, force_connection)
        else:
            thread = threading.Thread(target=self.connect2, args=(blocking, force_connection))
            thread.setDaemon(True)
            thread.start()

    def connect2(self, blocking, force_connection):
        if self.trying_connection:
            return
        self.trying_connection = True
        if self.user_connect or force_connection:
            try:
                self.conn = Connection(self)
                host, port, password = self.mpd_env_vars()
                if not password:
                    password = self.password[self.profile_num]
                if len(password) > 0:
                    self.conn.do.password(password)
            except (mpdclient3.socket.error, EOFError):
                self.conn = None
        else:
            self.conn = None
        self.trying_connection = False

    def connectkey_pressed(self, event):
        self.user_connect = True
        # Update selected radio button in menu:
        self.skip_on_profiles_click = True
        for gtkAction in self.actionGroupProfiles.list_actions():
            if gtkAction.get_name() == self.profile_names[self.profile_num]:
                gtkAction.activate()
                break
        self.skip_on_profiles_click = False
        # Connect:
        self.connect()
        self.iterate_now()

    def disconnectkey_pressed(self, event):
        self.user_connect = False
        # Update selected radio button in menu:
        self.skip_on_profiles_click = True
        for gtkAction in self.actionGroupProfiles.list_actions():
            if gtkAction.get_name() == 'disconnect':
                gtkAction.activate()
                break
        self.skip_on_profiles_click = False
        # Disconnect:
        if self.conn:
            try:
                self.conn.do.close()
            except:
                pass
        # I'm not sure why this doesn't automatically happen, so
        # we'll do it manually for the time being
        self.browserdata.clear()
        self.playlistsdata.clear()
        if self.filterbox_visible:
            gobject.idle_add(self.searchfilter_toggle, None)

    def update_status(self):
        try:
            if not self.conn:
                self.connect()
            if self.conn:
                self.iterate_time = self.iterate_time_when_connected
                self.status = self.conn.do.status()
                try:
                    test = self.status.state
                    if self.status.state == 'stop':
                        self.iterate_time = self.iterate_time_when_disconnected_or_stopped
                except:
                    self.status = None
                self.songinfo = self.conn.do.currentsong()
                if self.status:
                    if not self.last_repeat or self.last_repeat != self.status.repeat:
                        self.repeatmenu.set_active(self.status.repeat == '1')
                    if not self.last_random or self.last_random != self.status.random:
                        self.shufflemenu.set_active(self.status.random == '1')
                    if self.status.xfade == '0':
                        self.xfade_enabled = False
                    else:
                        self.xfade_enabled = True
                        self.xfade = int(self.status.xfade)
                        if self.xfade > 30: self.xfade = 30
                    self.last_repeat = self.status.repeat
                    self.last_random = self.status.random
            else:
                self.iterate_time = self.iterate_time_when_disconnected_or_stopped
                self.status = None
                self.songinfo = None
        except (mpdclient3.socket.error, EOFError):
            self.prevconn = self.conn
            self.prevstatus = self.status
            self.prevsonginfo = self.songinfo
            self.conn = None
            self.status = None
            self.songinfo = None

    def iterate(self):
        self.update_status()
        self.info_update(False)

        if self.conn != self.prevconn:
            self.handle_change_conn()
        if self.status != self.prevstatus:
            self.handle_change_status()
        if self.use_scrobbler:
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
                    self.initialize_systrayicon()
                elif not self.statusicon.is_embedded() and self.withdrawn:
                    # Systemtray gone, unwithdraw app:
                    self.withdraw_app_undo()
            elif HAVE_EGG:
                if self.trayicon.get_property('visible') == False:
                    # Systemtray appears, add icon:
                    self.initialize_systrayicon()

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
            self.browse_parent_dir(None)
        elif shortcut == 'Escape':
            if self.volumewindow.get_property('visible'):
                self.volume_hide()
            elif self.current_tab == self.TAB_LIBRARY and self.searchbutton.get_property('visible'):
                self.on_search_end(None)
            elif self.current_tab == self.TAB_CURRENT and self.filterbox_visible:
                self.searchfilter_toggle(None)
            elif self.minimize_to_systray:
                if HAVE_STATUS_ICON and self.statusicon.is_embedded() and self.statusicon.get_visible():
                    self.withdraw_app()
                elif HAVE_EGG and self.trayicon.get_property('visible') == True:
                    self.withdraw_app()
            return
        elif shortcut == 'Delete':
            self.remove(None)
        elif self.volumewindow.get_property('visible') and (shortcut == 'Up' or shortcut == 'Down'):
            if shortcut == 'Up':
                self.volume_raise(None)
            else:
                self.volume_lower(None)
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
        if os.path.exists(os.path.expanduser('~/.config/')) == False:
            os.mkdir(os.path.expanduser('~/.config/'))
        if os.path.exists(os.path.expanduser('~/.config/sonata/')) == False:
            os.mkdir(os.path.expanduser('~/.config/sonata/'))
        if os.path.isfile(os.path.expanduser('~/.config/sonata/sonatarc')):
            conf.read(os.path.expanduser('~/.config/sonata/sonatarc'))
        elif os.path.isfile(os.path.expanduser('~/.sonatarc')):
            conf.read(os.path.expanduser('~/.sonatarc'))
            os.remove(os.path.expanduser('~/.sonatarc'))
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
        if conf.has_option('player', 'play_on_activate'):
            self.play_on_activate = conf.getboolean('player', 'play_on_activate')
        if conf.has_option('player', 'trayicon'):
            self.show_trayicon = conf.getboolean('player', 'trayicon')
        if conf.has_option('player', 'view'):
            self.view = conf.getint('player', 'view')
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
        if conf.has_option('player', 'show_header'):
            self.show_header = conf.getboolean('player', 'show_header')
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
                self.current_tab_pos = conf.getint('notebook', 'current_tab_pos')
            if conf.has_option('notebook', 'library_tab_pos'):
                self.library_tab_pos = conf.getint('notebook', 'library_tab_pos')
            if conf.has_option('notebook', 'playlists_tab_pos'):
                self.playlists_tab_pos = conf.getint('notebook', 'playlists_tab_pos')
            if conf.has_option('notebook', 'streams_tab_pos'):
                self.streams_tab_pos = conf.getint('notebook', 'streams_tab_pos')
            if conf.has_option('notebook', 'info_tab_pos'):
                self.info_tab_pos = conf.getint('notebook', 'info_tab_pos')
        if conf.has_section('library'):
            if conf.has_option('library', 'root'):
                self.wd = conf.get('library', 'root')
            if conf.has_option('library', 'root_artist_level'):
                self.view_artist_level = conf.getint('library', 'root_artist_level')
            if conf.has_option('library', 'root_artist_artist'):
                self.view_artist_artist = conf.get('library', 'root_artist_artist')
            if conf.has_option('library', 'root_artist_album'):
                self.view_artist_album = conf.get('library', 'root_artist_album')
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
            self.use_scrobbler = conf.getboolean('audioscrobbler', 'use_audioscrobbler')
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
        conf.set('player', 'play_on_activate', self.play_on_activate)
        conf.set('player', 'trayicon', self.show_trayicon)
        conf.set('player', 'view', self.view)
        conf.set('player', 'search_num', self.last_search_num)
        conf.set('player', 'art_location', self.art_location)
        conf.set('player', 'art_location_custom_filename', self.art_location_custom_filename)
        conf.set('player', 'lyrics_location', self.lyrics_location)
        conf.set('player', 'info_song_expanded', self.info_song_expanded)
        conf.set('player', 'info_lyrics_expanded', self.info_lyrics_expanded)
        conf.set('player', 'info_album_expanded', self.info_album_expanded)
        conf.set('player', 'info_song_more', self.info_song_more)
        conf.set('player', 'info_art_enlarged', self.info_art_enlarged)
        self.update_column_widths()
        tmp = ""
        for i in range(len(self.columns)-1):
            tmp += str(self.columnwidths[i]) + ","
        tmp += str(self.columnwidths[len(self.columns)-1])
        conf.set('player', 'columnwidths', tmp)
        conf.set('player', 'show_header', self.show_header)
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
        conf.set('library', 'root_artist_level', self.view_artist_level)
        conf.set('library', 'root_artist_artist', self.view_artist_artist)
        conf.set('library', 'root_artist_album', self.view_artist_album)
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
        conf.set('audioscrobbler', 'use_audioscrobbler', self.use_scrobbler)
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
                self.trayimage.set_from_pixbuf(self.get_pixbuf_of_size(gtk.gdk.pixbuf_new_from_file(self.eggtrayfile), self.eggtrayheight)[0])
            self.info_update(True)
        else:
            for mediabutton in (self.ppbutton, self.stopbutton, self.prevbutton, self.nextbutton, self.volumebutton):
                mediabutton.set_property('sensitive', True)
            if self.sonata_loaded:
                self.browse(root='/')
            self.playlists_populate()
            self.on_notebook_page_change(self.notebook, 0, self.notebook.get_current_page())

    def give_widget_focus(self, widget):
        widget.grab_focus()

    def streams_edit(self, action):
        model, selected = self.streams_selection.get_selected_rows()
        try:
            streamname = model.get_value(model.get_iter(selected[0]), 1)
            for i in range(len(self.stream_names)):
                if self.stream_names[i] == streamname:
                    self.streams_new(action, i)
                    return
        except:
            pass

    def streams_new(self, action, stream_num=-1):
        if stream_num > -1:
            edit_mode = True
        else:
            edit_mode = False
        # Prompt user for playlist name:
        dialog = gtk.Dialog(None, self.window, gtk.DIALOG_MODAL | gtk.DIALOG_DESTROY_WITH_PARENT, (gtk.STOCK_CANCEL, gtk.RESPONSE_REJECT, gtk.STOCK_OK, gtk.RESPONSE_ACCEPT))
        if edit_mode:
            dialog.set_title(_("Edit Stream"))
        else:
            dialog.set_title(_("New Stream"))
        dialog.set_role("streamsNew")
        hbox = gtk.HBox()
        namelabel = gtk.Label(_('Stream name') + ':')
        hbox.pack_start(namelabel, False, False, 5)
        nameentry = gtk.Entry()
        if edit_mode:
            nameentry.set_text(self.stream_names[stream_num])
        hbox.pack_start(nameentry, True, True, 5)
        hbox2 = gtk.HBox()
        urllabel = gtk.Label(_('Stream URL') + ':')
        hbox2.pack_start(urllabel, False, False, 5)
        urlentry = gtk.Entry()
        if edit_mode:
            urlentry.set_text(self.stream_uris[stream_num])
        hbox2.pack_start(urlentry, True, True, 5)
        self.set_label_widths_equal([namelabel, urllabel])
        dialog.vbox.pack_start(hbox)
        dialog.vbox.pack_start(hbox2)
        dialog.vbox.show_all()
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
                            if show_error_msg_yesno(self.window, _("A stream with this name already exists. Would you like to replace it?"), _("New Stream"), 'newStreamError') == gtk.RESPONSE_YES:
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
            self.conn.do.rm(plname)
            self.conn.do.save(plname)
            self.playlists_populate()
            self.iterate_now()

    def on_playlist_add_songs(self, action):
        plname = unescape_html(action.get_name().replace("Playlist: ", ""))
        self.conn.send.command_list_begin()
        for song in self.songs:
            self.conn.send.playlistadd(plname, song.file)
        self.conn.do.command_list_end()

    def playlist_name_exists(self, title, role, plname, skip_plname=""):
        # If the playlist already exists, and the user does not want to replace it, return True; In
        # all other cases, return False
        for item in self.conn.do.lsinfo():
            if item.type == 'playlist':
                if item.playlist == plname and plname != skip_plname:
                    if show_error_msg_yesno(self.window, _("A playlist with this name already exists. Would you like to replace it?"), title, role) == gtk.RESPONSE_YES:
                        return False
                    else:
                        return True
        return False

    def prompt_for_playlist_name(self, title, role):
        plname = None
        if self.conn:
            # Prompt user for playlist name:
            dialog = gtk.Dialog(title, self.window, gtk.DIALOG_MODAL | gtk.DIALOG_DESTROY_WITH_PARENT, (gtk.STOCK_CANCEL, gtk.RESPONSE_REJECT, gtk.STOCK_SAVE, gtk.RESPONSE_ACCEPT))
            dialog.set_role(role)
            hbox = gtk.HBox()
            hbox.pack_start(gtk.Label(_('Playlist name') + ':'), False, False, 5)
            entry = gtk.Entry()
            entry.set_activates_default(True)
            hbox.pack_start(entry, True, True, 5)
            dialog.vbox.pack_start(hbox)
            dialog.set_default_response(gtk.RESPONSE_ACCEPT)
            dialog.vbox.show_all()
            response = dialog.run()
            if response == gtk.RESPONSE_ACCEPT:
                plname = strip_all_slashes(entry.get_text())
            dialog.destroy()
        return plname

    def playlists_populate(self):
        if self.conn:
            self.playlistsdata.clear()
            playlistinfo = []
            for item in self.conn.do.lsinfo():
                if item.type == 'playlist':
                    playlistinfo.append(escape_html(item.playlist))
            playlistinfo.sort(key=lambda x: x.lower()) # Remove case sensitivity
            for item in playlistinfo:
                self.playlistsdata.append([gtk.STOCK_JUSTIFY_FILL, item])
            if self.mpd_major_version() >= 0.13:
                self.populate_playlists_for_menu(playlistinfo)

    def on_playlist_rename(self, action):
        plname = self.prompt_for_playlist_name(_("Rename Playlist"), 'renamePlaylist')
        if plname:
            model, selected = self.playlists_selection.get_selected_rows()
            oldname = unescape_html(model.get_value(model.get_iter(selected[0]), 1))
            if self.playlist_name_exists(_("Rename Playlist"), 'renamePlaylistError', plname, oldname):
                return
            self.conn.do.rm(plname)
            self.conn.do.rename(oldname, plname)
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
            dict["name"] = escape_html(self.stream_names[i])
            dict["uri"] = escape_html(self.stream_uris[i])
            streamsinfo.append(dict)
        streamsinfo.sort(key=lambda x: x["name"].lower()) # Remove case sensitivity
        for item in streamsinfo:
            self.streamsdata.append([gtk.STOCK_NETWORK, item["name"], item["uri"]])

    def playlists_key_press(self, widget, event):
        if event.keyval == gtk.gdk.keyval_from_name('Return'):
            self.playlists_activated(widget, widget.get_cursor()[0])
            return True

    def playlists_activated(self, treeview, path, column=0):
        self.add_item(None, self.play_on_activate)

    def on_streams_key_press(self, widget, event):
        if event.keyval == gtk.gdk.keyval_from_name('Return'):
            self.on_streams_activated(widget, widget.get_cursor()[0])
            return True

    def on_streams_activated(self, treeview, path, column=0):
        self.add_item(None, self.play_on_activate)

    def libraryview_popup(self, button):
        self.librarymenu.popup(None, None, self.libraryview_position_menu, 1, 0)

    def on_libraryview_chosen(self, action):
        if self.searchbutton.get_property('visible'):
            self.on_search_end(None)
        prev_view = self.view
        if action.get_name() == 'filesystemview':
            self.view = self.VIEW_FILESYSTEM
        elif action.get_name() == 'artistview':
            self.view = self.VIEW_ARTIST
        elif action.get_name() == 'albumview':
            self.view = self.VIEW_ALBUM
        self.browser.grab_focus()
        if self.view != prev_view:
            self.libraryview_assign_image()
            if self.view == self.VIEW_ARTIST:
                self.view_artist_level = 1
            self.browserposition = {}
            self.browserselectedpath = {}
            try:
                self.browse()
                if len(self.browserdata) > 0:
                    self.browser_selection.unselect_range((0,), (len(self.browserdata)-1,))
            except:
                pass
            gobject.idle_add(self.browser.scroll_to_point, 0, 0)

    def libraryview_assign_image(self):
        if self.view == self.VIEW_FILESYSTEM:
            self.libraryview.set_image(gtk.image_new_from_stock(gtk.STOCK_HARDDISK, gtk.ICON_SIZE_MENU))
        elif self.view == self.VIEW_ARTIST:
            self.libraryview.set_image(gtk.image_new_from_stock('artist', gtk.ICON_SIZE_MENU))
        elif self.view == self.VIEW_ALBUM:
            self.libraryview.set_image(gtk.image_new_from_stock('album', gtk.ICON_SIZE_MENU))

    def browse(self, widget=None, root='/'):
        # Populates the library list with entries starting at root
        if not self.conn:
            return

        # Handle special cases (i.e. if we are browsing to a song or
        # if the path has disappeared)
        lsinfo = self.conn.do.lsinfo(root)
        while lsinfo == []:
            if self.conn.do.listallinfo(root):
                # Info exists if we try to browse to a song
                self.add_item(self.browser, self.play_on_activate)
                return
            elif self.view == self.VIEW_ARTIST:
                if self.view_artist_level == 1:
                    break
                elif self.view_artist_level == 2:
                    if len(self.browse_search_artist(root)) == 0:
                        # Back up and try the parent
                        self.view_artist_level = self.view_artist_level - 1
                    else:
                        break
                elif self.view_artist_level == 3:
                    (album, year) = self.browse_parse_albumview_path(root)
                    if len(self.browse_search_album_with_artist_and_year(self.view_artist_artist, album, year)) == 0:
                        # Back up and try the parent
                        self.view_artist_level = self.view_artist_level - 1
                        root = self.view_artist_artist
                    else:
                        break
                else:
                    break
            elif self.view == self.VIEW_FILESYSTEM:
                if root == '/':
                    # Nothing in the library at all
                    return
                else:
                    # Back up and try the parent
                    root = '/'.join(root.split('/')[:-1]) or '/'
            else:
                if len(self.browse_search_album(root)) == 0:
                    root = "/"
                    break
                else:
                    break
            lsinfo = self.conn.do.lsinfo(root)

        prev_selection = []
        prev_selection_root = False
        prev_selection_parent = False
        if (self.view != self.VIEW_ARTIST and root == self.wd) or (self.view == self.VIEW_ARTIST and self.view_artist_level == self.view_artist_level_prev):
            # This will happen when the database is updated. So, lets save
            # the current selection in order to try to re-select it after
            # the update is over.
            model, selected = self.browser_selection.get_selected_rows()
            for path in selected:
                if model.get_value(model.get_iter(path), 2) == "/":
                    prev_selection_root = True
                elif model.get_value(model.get_iter(path), 2) == "..":
                    prev_selection_parent = True
                else:
                    prev_selection.append(model.get_value(model.get_iter(path), 1))
            self.browserposition[self.wd] = self.browser.get_visible_rect()[1]
            path_updated = True
        else:
            path_updated = False

        # The logic below is more consistent with, e.g., thunar
        if (self.view != self.VIEW_ARTIST and len(root) > len(self.wd)) or (self.view == self.VIEW_ARTIST and self.view_artist_level > self.view_artist_level_prev):
            # Save position and row for where we just were if we've
            # navigated into a sub-directory:
            self.browserposition[self.wd] = self.browser.get_visible_rect()[1]
            model, rows = self.browser_selection.get_selected_rows()
            if len(rows) > 0:
                value_for_selection = self.browserdata.get_value(self.browserdata.get_iter(rows[0]), 2)
                if value_for_selection != ".." and value_for_selection != "/":
                    self.browserselectedpath[self.wd] = rows[0]
        elif (self.view != self.VIEW_ARTIST and root != self.wd) or (self.view == self.VIEW_ARTIST and self.view_artist_level != self.view_artist_level_prev):
            # If we've navigated to a parent directory, don't save
            # anything so that the user will enter that subdirectory
            # again at the top position with nothing selected
            self.browserposition[self.wd] = 0
            self.browserselectedpath[self.wd] = None

        # In case sonata is killed or crashes, we'll save the browser state
        # in 5 seconds (first removing any current settings_save timeouts)
        if self.wd != root:
            try:
                gobject.source_remove(self.save_timeout)
            except:
                pass
            self.save_timeout = gobject.timeout_add(5000, self.settings_save)

        self.wd = root
        self.browser.freeze_child_notify()
        self.browserdata.clear()

        bd = []  # will be put into browserdata later
        if self.view == self.VIEW_FILESYSTEM:
            if self.wd != '/':
                bd += [('0', [gtk.STOCK_HARDDISK, '/', '/'])]
                bd += [('1', [gtk.STOCK_OPEN, '..', '..'])]
            for item in lsinfo:
                if item.type == 'directory':
                    name = item.directory.split('/')[-1]
                    bd += [('d' + name.lower(), [gtk.STOCK_OPEN, item.directory, escape_html(name)])]
                elif item.type == 'file':
                    bd += [('f' + item.file.lower(), ['sonata', item.file, self.parse_formatting(self.libraryformat, item, True)])]
            bd.sort(key=first_of_2tuple)
        elif self.view == self.VIEW_ARTIST:
            if self.view_artist_level == 1:
                self.view_artist_artist = ''
                self.view_artist_album = ''
                root = '/'
                if self.artists_root is None:
                    self.artists_root = []
                    for item in self.conn.do.list('artist'):
                        self.artists_root.append(item.artist)
                    (self.artists_root, i) = remove_list_duplicates(self.artists_root, [], False)
                    self.artists_root.sort(locale.strcoll)
                for artist in self.artists_root:
                    bd += [(lower_no_the(artist), ['artist', artist, escape_html(artist)])]
                bd.sort(key=first_of_2tuple)
            elif self.view_artist_level == 2:
                bd += [('0', [gtk.STOCK_HARDDISK, '/', '/'])]
                bd += [('1', [gtk.STOCK_OPEN, '..', '..'])]
                if self.wd != "..":
                    self.view_artist_artist = self.wd
                albums = []
                songs = []
                years = []
                for item in self.browse_search_artist(self.view_artist_artist):
                    try:
                        albums.append(item.album)
                        years.append(getattr(item, 'date', '9999').split('-')[0].zfill(4))
                    except:
                        songs.append(item)
                (albums, years) = remove_list_duplicates(albums, years, False)
                for itemnum in range(len(albums)):
                    if years[itemnum] == '9999':
                        bd += [('d' + years[itemnum] + lower_no_the(albums[itemnum]), ['album', years[itemnum] + albums[itemnum], escape_html(albums[itemnum])])]
                    else:
                        bd += [('d' + years[itemnum] + lower_no_the(albums[itemnum]), ['album', years[itemnum] + albums[itemnum], escape_html(years[itemnum] + ' - ' + albums[itemnum])])]
                for song in songs:
                    bd += [('f' + lower_no_the(song.title), ['sonata', song.file, self.parse_formatting(self.libraryformat, song, True)])]
                bd.sort(key=first_of_2tuple)
            else:
                bd += [('0', [gtk.STOCK_HARDDISK, '/', '/'])]
                bd += [('1', [gtk.STOCK_OPEN, '..', '..'])]
                (self.view_artist_album, year) = self.browse_parse_albumview_path(root)
                for item in self.browse_search_album_with_artist_and_year(self.view_artist_artist, self.view_artist_album, year):
                    num = self.sanitize_mpdtag(getattr(item, 'disc', '1'), False, 2) + self.sanitize_mpdtag(getattr(item, 'track', '1'), False, 2)
                    bd += [('f' + num, ['sonata', item.file, self.parse_formatting(self.libraryformat, item, True)])]
                # List already sorted in self.browse_parse_albumview_path...
        elif self.view == self.VIEW_ALBUM:
            items = []
            if self.wd == '/':
                if self.albums_root is None:
                    self.albums_root = []
                    for item in self.conn.do.list('album'):
                        self.albums_root.append(item.album)
                    (self.albums_root, i) = remove_list_duplicates(self.albums_root, [], False)
                    self.albums_root.sort(locale.strcoll)
                for item in self.albums_root:
                    bd += [('d' + lower_no_the(item), ['album', item, escape_html(item)])]
                bd.sort(key=first_of_2tuple)
            else:
                bd += [('0', [gtk.STOCK_HARDDISK, '/', '/'])]
                bd += [('1', [gtk.STOCK_OPEN, '..', '..'])]
                for item in self.browse_search_album(root):
                    num = self.sanitize_mpdtag(getattr(item, 'disc', '1'), False, 2) + self.sanitize_mpdtag(getattr(item, 'track', '1'), False, 2)
                    bd += [('f' + num, ['sonata', item.file, self.parse_formatting(self.libraryformat, item, True)])]
                # List already sorted in self.browse_parse_albumview_path...

        for sort, list in bd:
            self.browserdata.append(list)

        self.browser.thaw_child_notify()

        # Scroll back to set view for current dir:
        self.browser.realize()
        gobject.idle_add(self.browser_set_view, not path_updated)
        if len(prev_selection) > 0 or prev_selection_root or prev_selection_parent:
            self.browser_retain_preupdate_selection(prev_selection, prev_selection_root, prev_selection_parent)

        self.view_artist_level_prev = self.view_artist_level

    def browse_search_album(self, album):
        # Return songs of the specified album. Sorts by disc and track number
        list = []
        for item in self.conn.do.search('album', album):
            if item.has_key('album'):
                # Make sure it's an exact match:
                if album.lower() == item.album.lower():
                    list.append(item)
        list.sort(key=lambda x: int(self.sanitize_mpdtag(getattr(x, 'disc', '0'), False, 2) + self.sanitize_mpdtag(getattr(x, 'track', '0'), False, 2)))
        return list

    def browse_search_artist(self, artist):
        # Return songs of the specified artist. Sorts by year
        list = []
        for item in self.conn.do.search('artist', artist):
            # Make sure it's an exact match:
            if artist.lower() == item.artist.lower():
                list.append(item)
        list.sort(key=lambda x: getattr(x, 'date', '0').split('-')[0].zfill(4))
        return list

    def browse_search_album_with_artist_and_year(self, artist, album, year):
        # Return songs of specified album, artist, and year. Sorts by disc and
        # track num.
        # If year is None, skips that requirement
        list = []
        for item in self.conn.do.search('album', album, 'artist', artist):
            # Make sure it's an exact match:
            if artist.lower() == item.artist.lower() and album.lower() == item.album.lower():
                if year is None:
                    list.append(item)
                else:
                    # Make sure it also matches the year:
                    if year != '9999' and item.has_key('date'):
                        # Only show songs whose years match the year var:
                        try:
                            if int(item.date.split('-')[0]) == int(year):
                                list.append(item)
                        except:
                            pass
                    elif not item.has_key('date'):
                        # Only show songs that have no year specified:
                        list.append(item)
        list.sort(key=lambda x: int(self.sanitize_mpdtag(getattr(x, 'disc', '0'), False, 2) + self.sanitize_mpdtag(getattr(x, 'track', '0'), False, 2)))
        return list

    def browser_retain_preupdate_selection(self, prev_selection, prev_selection_root, prev_selection_parent):
        # Unselect everything:
        if len(self.browserdata) > 0:
            self.browser_selection.unselect_range((0,), (len(self.browserdata)-1,))
        # Now attempt to retain the selection from before the update:
        for value in prev_selection:
            for rownum in range(len(self.browserdata)):
                if value == self.browserdata.get_value(self.browserdata.get_iter((rownum,)), 1):
                    self.browser_selection.select_path((rownum,))
                    break
        if prev_selection_root:
            self.browser_selection.select_path((0,))
        if prev_selection_parent:
            self.browser_selection.select_path((1,))

    def browser_set_view(self, select_items=True):
        # select_items should be false if the same directory has merely
        # been refreshed (updated)
        try:
            if self.wd in self.browserposition:
                self.browser.scroll_to_point(-1, self.browserposition[self.wd])
            else:
                self.browser.scroll_to_point(0, 0)
        except:
            self.browser.scroll_to_point(0, 0)

        # Select and focus previously selected item if it's not ".." or "/"
        if select_items:
            if self.view == self.VIEW_ARTIST:
                if self.view_artist_level == 1:
                    item = "/"
                elif self.view_artist_level == 2:
                    item = self.view_artist_artist
                else:
                    return
            else:
                item = self.wd
            if item in self.browserselectedpath:
                try:
                    if self.browserselectedpath[item]:
                        self.browser_selection.select_path(self.browserselectedpath[item])
                        self.browser.grab_focus()
                except:
                    pass

    def browse_parse_albumview_path(self, path):
        # The first four chars are used to store the year. Returns
        # a tuple.
        year = path[:4]
        album = path[4:]
        return (album, year)

    def parse_formatting_return_substrings(self, format):
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

    def parse_formatting_for_column_names(self, format):
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

    def parse_formatting_for_substring(self, subformat, item, wintitle):
        text = subformat
        if subformat.startswith("{") and subformat.endswith("}"):
            has_brackets = True
        else:
            has_brackets = False
        if "%A" in text:
            try:
                text = text.replace("%A", item.artist)
            except:
                if not has_brackets: text = text.replace("%A", _('Unknown'))
                else: return ""
        if "%B" in text:
            try:
                text = text.replace("%B", item.album)
            except:
                if not has_brackets: text = text.replace("%B", _('Unknown'))
                else: return ""
        if "%T" in text:
            try:
                text = text.replace("%T", item.title)
            except:
                if not has_brackets: return self.filename_or_fullpath(item.file)
                else: return ""
        if "%N" in text:
            try:
                text = text.replace("%N", self.sanitize_mpdtag(item.track, False, 2))
            except:
                if not has_brackets: text = text.replace("%N", "0")
                else: return ""
        if "%D" in text:
            try:
                text = text.replace("%D", self.sanitize_mpdtag(item.disc, False, 0))
            except:
                if not has_brackets: text = text.replace("%D", "0")
                else: return ""
        if "%S" in text:
            try:
                text = text.replace("%S", item.name)
            except:
                if not has_brackets: text = text.replace("%S", _('Unknown'))
                else: return ""
        if "%G" in text:
            try:
                text = text.replace("%G", item.genre)
            except:
                if not has_brackets: text = text.replace("%G", _('Unknown'))
                else: return ""
        if "%Y" in text:
            try:
                text = text.replace("%Y", item.date)
            except:
                if not has_brackets: text = text.replace("%Y", "?")
                else: return ""
        if "%F" in text:
            text = text.replace("%F", item.file)
        if "%P" in text:
            text = text.replace("%P", item.file.split('/')[-1])
        if "%L" in text:
            try:
                time = convert_time(int(item.time))
                text = text.replace("%L", time)
            except:
                if not has_brackets: text = text.replace("%L", "?")
                else: return ""
        if wintitle:
            if "%E" in text:
                try:
                    at, length = [int(c) for c in self.status.time.split(':')]
                    at_time = convert_time(at)
                    text = text.replace("%E", at_time)
                except:
                    if not has_brackets: text = text.replace("%E", "?")
                    else: return ""
        if text.startswith("{") and text.endswith("}"):
            return text[1:-1]
        else:
            return text

    def parse_formatting(self, format, item, use_escape_html, wintitle=False):
        substrings = self.parse_formatting_return_substrings(format)
        text = ""
        for sub in substrings:
            text = text + str(self.parse_formatting_for_substring(sub, item, wintitle))
        if use_escape_html:
            return escape_html(text)
        else:
            return text

    def filename_or_fullpath(self, file):
        if len(file.split('/')[-1]) == 0 or file[:7] == 'http://' or file[:6] == 'ftp://':
            # Use path and file name:
            return escape_html(file)
        else:
            # Use file name only:
            return escape_html(file.split('/')[-1])

    def song_has_metadata(self, item):
        if item.has_key('title') or item.has_key('artist'):
            return True
        return False

    def info_update(self, update_all, blank_window=False):
        # update_all = True means that every tag should update. This is
        # only the case on song and status changes. Otherwise we only
        # want to update the minimum number of widgets so the user can
        # do things like select label text.
        if self.current_tab == self.TAB_INFO:
            if self.conn:
                if self.status and self.status.state in ['play', 'pause']:
                    bitratelabel = self.info_labels[self.info_type[_("Bitrate")]]
                    titlelabel = self.info_labels[self.info_type[_("Title")]]
                    artistlabel = self.info_labels[self.info_type[_("Artist")]]
                    albumlabel = self.info_labels[self.info_type[_("Album")]]
                    datelabel = self.info_labels[self.info_type[_("Date")]]
                    genrelabel = self.info_labels[self.info_type[_("Genre")]]
                    tracklabel = self.info_labels[self.info_type[_("Track")]]
                    filelabel = self.info_labels[self.info_type[_("File")]]
                    try:
                        newbitrate = self.status.bitrate + " kbps"
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
                        titlelabel.set_text(getattr(self.songinfo, 'title', ''))
                        if artist_use_link:
                            artistlabel.set_markup(link_markup(escape_html(self.songinfo.artist), False, False, self.linkcolor))
                        else:
                            artistlabel.set_text(getattr(self.songinfo, 'artist', ''))
                        if album_use_link:
                            albumlabel.set_markup(link_markup(escape_html(self.songinfo.album), False, False, self.linkcolor))
                        else:
                            albumlabel.set_text(getattr(self.songinfo, 'album', ''))
                        datelabel.set_text(getattr(self.songinfo, 'date', ''))
                        genrelabel.set_text(getattr(self.songinfo, 'genre', ''))
                        if self.songinfo.has_key('track'):
                            tracklabel.set_text(self.sanitize_mpdtag(getattr(self.songinfo, 'track', '0'), False, 0))
                        else:
                            tracklabel.set_text("")
                        if os.path.exists(self.musicdir[self.profile_num] + os.path.dirname(self.songinfo.file)):
                            filelabel.set_text(self.musicdir[self.profile_num] + self.songinfo.file)
                            self.info_editlabel.set_markup(link_markup(_("edit tags"), True, True, self.linkcolor))
                        else:
                            filelabel.set_text(self.songinfo.file)
                            self.info_editlabel.set_text("")
                        if self.songinfo.has_key('album'):
                            # Update album info:
                            year = []
                            albumtime = 0
                            trackinfo = ""
                            albuminfo = self.songinfo.album + "\n"
                            tracks = self.browse_search_album(self.songinfo.album)
                            for track in tracks:
                                if track.has_key('title'):
                                    trackinfo = trackinfo + self.sanitize_mpdtag(getattr(track, 'track', '0'), False, 2) + '. ' + track.title + '\n'
                                else:
                                    trackinfo = trackinfo + self.sanitize_mpdtag(getattr(track, 'track', '0'), False, 2) + '. ' + track.file.split('/')[-1] + '\n'
                                if track.has_key('date'):
                                    year.append(track.date)
                                try:
                                    albumtime = albumtime + int(track.time)
                                except:
                                    pass
                            (year, i) = remove_list_duplicates(year, [], False)
                            artist = self.current_artist_for_album_name[1]
                            artist_use_link = False
                            if artist != _("Various Artists"):
                                artist_use_link = True
                            albuminfo = albuminfo + artist + "\n"
                            if len(year) == 1:
                                albuminfo = albuminfo + year[0] + "\n"
                            albuminfo = albuminfo + convert_time(albumtime) + "\n"
                            albuminfo = albuminfo + "\n" + trackinfo
                            self.albumText.set_markup(albuminfo)
                        else:
                            self.albumText.set_text(_("Album name not set."))
                        # Update lyrics:
                        if self.show_lyrics:
                            if self.songinfo.has_key('artist') and self.songinfo.has_key('title'):
                                lyricThread = threading.Thread(target=self.info_get_lyrics, args=(self.songinfo.artist, self.songinfo.title, self.songinfo.artist, self.songinfo.title))
                                lyricThread.setDaemon(True)
                                lyricThread.start()
                            elif not HAVE_WSDL:
                                self.info_searchlabel.set_text("")
                                self.info_show_lyrics(_("ZSI not found, fetching lyrics support disabled."), "", "", True)
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
        filename_artist = strip_all_slashes(filename_artist)
        filename_title = strip_all_slashes(filename_title)
        filename = self.info_check_for_local_lyrics(filename_artist, filename_title)
        search_str = link_markup(_("search"), True, True, self.linkcolor)
        if filename:
            # If the lyrics only contain "not found", delete the file and try to
            # fetch new lyrics. If there is a bug in Sonata/SZI/LyricWiki that
            # prevents lyrics from being found, storing the "not found" will
            # prevent a future release from correctly fetching the lyrics.
            f = open(filename, 'r')
            lyrics = f.read()
            f.close()
            if lyrics == _("Lyrics not found"):
                os.remove(filename)
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
            if not HAVE_WSDL:
                gobject.idle_add(self.info_show_lyrics, _("ZSI not found, fetching lyrics support disabled."), "", "", True)
                gobject.idle_add(self.info_searchlabel.set_text, "")
                return
            # Use default filename:
            filename = self.target_lyrics_filename(filename_artist, filename_title)
            # Fetch lyrics from lyricwiki.org
            gobject.idle_add(self.info_show_lyrics, _("Fetching lyrics..."), filename_artist, filename_title)
            if self.lyricServer is None:
                wsdlFile = "http://lyricwiki.org/server.php?wsdl"
                try:
                    self.lyricServer = True
                    timeout = socket.getdefaulttimeout()
                    socket.setdefaulttimeout(self.LYRIC_TIMEOUT)
                    self.lyricServer = ServiceProxy.ServiceProxy(wsdlFile)
                except:
                    socket.setdefaulttimeout(timeout)
                    lyrics = _("Couldn't connect to LyricWiki")
                    gobject.idle_add(self.info_show_lyrics, lyrics, filename_artist, filename_title)
                    self.lyricServer = None
                    gobject.idle_add(self.info_searchlabel.set_markup, search_str)
                    return
            try:
                timeout = socket.getdefaulttimeout()
                socket.setdefaulttimeout(self.LYRIC_TIMEOUT)
                lyrics = self.lyricServer.getSong(artist=urllib.quote(search_artist), song=urllib.quote(search_title))['return']["lyrics"]
                if lyrics.lower() != "not found":
                    lyrics = filename_artist + " - " + filename_title + "\n\n" + lyrics
                    lyrics = unescape_html(lyrics)
                    lyrics = wiki_to_html(lyrics)
                    gobject.idle_add(self.info_show_lyrics, lyrics, filename_artist, filename_title)
                    # Save lyrics to file:
                    self.create_dir_if_not_existing('~/.lyrics/')
                    f = open(filename, 'w')
                    lyrics = unescape_html(lyrics)
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
            socket.setdefaulttimeout(timeout)

    def info_show_lyrics(self, lyrics, artist, title, force=False):
        if force:
            # For error messages where there is no appropriate artist or
            # title, we pass force=True:
            self.lyricsText.set_text(lyrics)
        elif self.status and self.status.state in ['play', 'pause'] and self.songinfo:
            # Verify that we are displaying the correct lyrics:
            try:
                if strip_all_slashes(self.songinfo.artist) == artist and strip_all_slashes(self.songinfo.title) == title:
                    try:
                        self.lyricsText.set_markup(lyrics)
                    except:
                        self.lyricsText.set_text(lyrics)
            except:
                pass

    def on_browser_key_press(self, widget, event):
        if event.keyval == gtk.gdk.keyval_from_name('Return'):
            self.on_browse_row(widget, widget.get_cursor()[0])
            return True

    def on_browse_row(self, widget, path, column=0):
        if path is None:
            # Default to last item in selection:
            model, selected = self.browser_selection.get_selected_rows()
            if len(selected) >=1:
                path = (len(selected)-1,)
            elif len(model) > 0:
                path = (0,)
            else:
                return
        value = self.browserdata.get_value(self.browserdata.get_iter(path), 1)
        icon = self.browserdata.get_value(self.browserdata.get_iter(path), 0)
        if value == "..":
            self.browse_parent_dir(None)
        else:
            if self.view == self.VIEW_ARTIST:
                if value == "/":
                    self.view_artist_level = 1
                elif icon != 'sonata':
                    self.view_artist_level = self.view_artist_level + 1
            self.browse(None, value)

    def browse_parent_dir(self, action):
        if self.current_tab == self.TAB_LIBRARY:
            if not self.searchbutton.get_property('visible'):
                if self.browser.is_focus():
                    if self.view == self.VIEW_ARTIST:
                        if self.view_artist_level > 1:
                            self.view_artist_level = self.view_artist_level - 1
                        if self.view_artist_level == 1:
                            value = "/"
                        else:
                            value = self.view_artist_artist
                    else:
                        value = '/'.join(self.wd.split('/')[:-1]) or '/'
                    self.browse(None, value)

    def on_treeview_selection_changed(self, treeselection):
        self.set_menu_contextual_items_visible()
        if treeselection == self.current.get_selection():
            # User previously clicked inside group of selected rows, re-select
            # rows so it doesn't look like anything changed:
            if self.sel_rows:
                for row in self.sel_rows:
                    treeselection.select_path(row)

    def on_browser_button_press(self, widget, event):
        if self.button_press(widget, event, False): return True

    def on_current_button_press(self, widget, event):
        if self.button_press(widget, event, True): return True

    def on_playlists_button_press(self, widget, event):
        if self.button_press(widget, event,	False): return True

    def on_streams_button_press(self, widget, event):
        if self.button_press(widget, event, False): return True

    def button_press(self, widget, event, widget_is_current):
        self.volume_hide()
        self.sel_rows = None
        if event.button == 1 and widget_is_current:
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
            self.set_menu_contextual_items_visible()
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

    def after_current_drag_begin(self, widget, context):
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

    def play_item(self, playid):
        if self.conn:
            self.conn.do.play(int(playid))

    def browser_get_selected_items_recursive(self, return_root):
        # If return_root=True, return main directories whenever possible
        # instead of individual songs in order to reduce the number of
        # mpd calls we need to make. We won't want this behavior in some
        # instances, like when we want all end files for editing tags
        items = []
        model, selected = self.browser_selection.get_selected_rows()
        if self.view == self.VIEW_FILESYSTEM or self.search_mode_enabled():
            if return_root and not self.search_mode_enabled() and ((self.wd == "/" and len(selected) == len(model)) or (self.wd != "/" and len(selected) >= len(model)-2)):
                # Everything selected, this is faster..
                items.append(self.wd)
            else:
                for path in selected:
                    while gtk.events_pending():
                        gtk.main_iteration()
                    if model.get_value(model.get_iter(path), 2) != "/" and model.get_value(model.get_iter(path), 2) != "..":
                        if model.get_value(model.get_iter(path), 0) == gtk.STOCK_OPEN:
                            if return_root and not self.search_mode_enabled():
                                items.append(model.get_value(model.get_iter(path), 1))
                            else:
                                for item in self.conn.do.listall(model.get_value(model.get_iter(path), 1)):
                                    if item.type == 'file':
                                        items.append(item.file)
                        else:
                            items.append(model.get_value(model.get_iter(path), 1))
        elif self.view == self.VIEW_ARTIST:
            for path in selected:
                while gtk.events_pending():
                    gtk.main_iteration()
                if model.get_value(model.get_iter(path), 2) != "/" and model.get_value(model.get_iter(path), 2) != "..":
                    if self.view_artist_level == 1:
                        for item in self.browse_search_artist(model.get_value(model.get_iter(path), 1)):
                            items.append(item.file)
                    else:
                        if model.get_value(model.get_iter(path), 0) == 'album':
                            (album, year) = self.browse_parse_albumview_path(model.get_value(model.get_iter(path), 1))
                            for item in self.browse_search_album_with_artist_and_year(self.view_artist_artist, album, year):
                                items.append(item.file)
                        else:
                            items.append(model.get_value(model.get_iter(path), 1))
        elif self.view == self.VIEW_ALBUM:
            for path in selected:
                while gtk.events_pending():
                    gtk.main_iteration()
                if model.get_value(model.get_iter(path), 2) != "/" and model.get_value(model.get_iter(path), 2) != "..":
                    if self.wd == "/":
                        for item in self.browse_search_album(model.get_value(model.get_iter(path), 1)):
                            items.append(item.file)
                    else:
                        items.append(model.get_value(model.get_iter(path), 1))
        # Make sure we don't have any EXACT duplicates:
        (items, i) = remove_list_duplicates(items, [], True)
        return items

    def add_item(self, widget, play_after=False):
        if self.conn:
            if play_after and self.status:
                playid = self.status.playlistlength
            if self.current_tab == self.TAB_LIBRARY:
                items = self.browser_get_selected_items_recursive(True)
                self.conn.send.command_list_begin()
                for item in items:
                    self.conn.send.add(item)
                self.conn.do.command_list_end()
            elif self.current_tab == self.TAB_PLAYLISTS:
                model, selected = self.playlists_selection.get_selected_rows()
                for path in selected:
                    self.conn.do.load(unescape_html(model.get_value(model.get_iter(path), 1)))
            elif self.current_tab == self.TAB_STREAMS:
                model, selected = self.streams_selection.get_selected_rows()
                for path in selected:
                    item = model.get_value(model.get_iter(path), 2)
                    self.stream_parse_and_add(item)
            self.iterate_now()
            if play_after:
                self.play_item(playid)

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
            if is_binary(f):
                # Binary file, just add it:
                self.conn.do.add(item)
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
                    self.conn.do.add(item)
        else:
            # Hopefully just a regular stream, try to add it:
            self.conn.do.add(item)

    def stream_parse_pls(self, f):
        lines = f.split("\n")
        for line in lines:
            line = line.replace('\r','')
            delim = line.find("=")+1
            if delim > 0:
                line = line[delim:]
                if len(line) > 7 and line[0:7] == 'http://':
                    self.conn.do.add(line)
                elif len(line) > 6 and line[0:6] == 'ftp://':
                    self.conn.do.add(line)

    def stream_parse_m3u(self, f):
        lines = f.split("\n")
        for line in lines:
            line = line.replace('\r','')
            if len(line) > 7 and line[0:7] == 'http://':
                self.conn.do.add(line)
            elif len(line) > 6 and line[0:6] == 'ftp://':
                self.conn.do.add(line)

    def replace_item(self, widget):
        play_after_replace = False
        if self.status and self.status.state == 'play':
            play_after_replace = True
        # Only clear if an item is selected:
        if self.current_tab == self.TAB_LIBRARY:
            num_selected = self.browser_selection.count_selected_rows()
        elif self.current_tab == self.TAB_PLAYLISTS:
            num_selected = self.playlists_selection.count_selected_rows()
        elif self.current_tab == self.TAB_STREAMS:
            num_selected = self.streams_selection.count_selected_rows()
        else:
            return
        if num_selected == 0:
            return
        self.clear(None)
        if play_after_replace and self.conn:
            self.add_item(widget, True)
        else:
            self.add_item(widget, False)
        self.iterate_now()

    def libraryview_position_menu(self, menu):
        x, y, width, height = self.libraryview.get_allocation()
        return (self.x + x, self.y + y + height, True)

    def position_menu(self, menu):
        if self.expanded:
            x, y, width, height = self.current.get_allocation()
            # Find first selected visible row and popup the menu
            # from there
            if self.current_tab == self.TAB_CURRENT:
                widget = self.current
                column = self.columns[0]
            elif self.current_tab == self.TAB_LIBRARY:
                widget = self.browser
                column = self.browsercolumn
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
            self.update_album_art()
            self.update_statusbar()
            return

        # Display current playlist
        if self.prevstatus == None or self.prevstatus.playlist != self.status.playlist:
            self.update_playlist()

        # Update progress frequently if we're playing
        if self.status.state in ['play', 'pause']:
            self.update_progressbar()

        # If elapsed time is shown in the window title, we need to update more often:
        if "%E" in self.titleformat:
            self.update_wintitle()

        # If state changes
        if self.prevstatus == None or self.prevstatus.state != self.status.state:

            self.get_new_artist_for_album_name()

            # Update progressbar if the state changes too
            self.update_progressbar()
            self.update_cursong()
            self.update_wintitle()
            self.info_update(True)
            if self.status.state == 'stop':
                self.ppbutton.set_image(gtk.image_new_from_stock(gtk.STOCK_MEDIA_PLAY, gtk.ICON_SIZE_BUTTON))
                self.ppbutton.get_child().get_child().get_children()[1].set_text('')
                self.UIManager.get_widget('/traymenu/playmenu').show()
                self.UIManager.get_widget('/traymenu/pausemenu').hide()
                if HAVE_STATUS_ICON:
                    self.statusicon.set_from_file(self.find_path('sonata.png'))
                elif HAVE_EGG and self.eggtrayheight:
                    self.eggtrayfile = self.find_path('sonata.png')
                    self.trayimage.set_from_pixbuf(self.get_pixbuf_of_size(gtk.gdk.pixbuf_new_from_file(self.eggtrayfile), self.eggtrayheight)[0])
            elif self.status.state == 'pause':
                self.ppbutton.set_image(gtk.image_new_from_stock(gtk.STOCK_MEDIA_PLAY, gtk.ICON_SIZE_BUTTON))
                self.ppbutton.get_child().get_child().get_children()[1].set_text('')
                self.UIManager.get_widget('/traymenu/playmenu').show()
                self.UIManager.get_widget('/traymenu/pausemenu').hide()
                if HAVE_STATUS_ICON:
                    self.statusicon.set_from_file(self.find_path('sonata_pause.png'))
                elif HAVE_EGG and self.eggtrayheight:
                    self.eggtrayfile = self.find_path('sonata_pause.png')
                    self.trayimage.set_from_pixbuf(self.get_pixbuf_of_size(gtk.gdk.pixbuf_new_from_file(self.eggtrayfile), self.eggtrayheight)[0])
            elif self.status.state == 'play':
                self.ppbutton.set_image(gtk.image_new_from_stock(gtk.STOCK_MEDIA_PAUSE, gtk.ICON_SIZE_BUTTON))
                self.ppbutton.get_child().get_child().get_children()[1].set_text('')
                self.UIManager.get_widget('/traymenu/playmenu').hide()
                self.UIManager.get_widget('/traymenu/pausemenu').show()
                if self.prevstatus != None:
                    if self.prevstatus.state == 'pause':
                        # Forces the notification to popup if specified
                        self.labelnotify()
                if HAVE_STATUS_ICON:
                    self.statusicon.set_from_file(self.find_path('sonata_play.png'))
                elif HAVE_EGG and self.eggtrayheight:
                    self.eggtrayfile = self.find_path('sonata_play.png')
                    self.trayimage.set_from_pixbuf(self.get_pixbuf_of_size(gtk.gdk.pixbuf_new_from_file(self.eggtrayfile), self.eggtrayheight)[0])
            self.update_album_art()
            if self.status.state in ['play', 'pause']:
                self.keep_song_centered_in_list()

        if self.prevstatus is None or self.status.volume != self.prevstatus.volume:
            try:
                self.volumescale.get_adjustment().set_value(int(self.status.volume))
                if int(self.status.volume) == 0:
                    self.set_volumebutton("stock_volume-mute")
                elif int(self.status.volume) < 30:
                    self.set_volumebutton("stock_volume-min")
                elif int(self.status.volume) <= 70:
                    self.set_volumebutton("stock_volume-med")
                else:
                    self.set_volumebutton("stock_volume-max")
                self.tooltips.set_tip(self.volumebutton, self.status.volume + "%")
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
                    self.reset_artist_for_album_name()
                    self.get_new_artist_for_album_name()
                    # Resetting albums_root and artists_root to None will cause
                    # the two lists to update to the new contents
                    self.albums_root = None
                    self.artists_root = None
                    # Now update the library and playlist tabs
                    self.browse(root=self.wd)
                    self.playlists_populate()
                    # Update infow if it's visible:
                    self.info_update(True)

        if self.use_scrobbler:
            if self.status and self.status.state == 'play':
                if not self.prevstatus or (self.prevstatus and self.prevstatus.state == 'stop'):
                    # Switched from stop to play, prepare current track:
                    self.scrobbler_prepare()
                elif self.prevsonginfo and self.prevsonginfo.has_key('time') and self.scrob_last_prepared != self.songinfo.file:
                    # New song is playing, post previous track if time criteria is met:
                    if self.scrob_playing_duration > 4 * 60 or self.scrob_playing_duration > int(self.prevsonginfo.time)/2:
                        if self.scrob_start_time != "":
                            self.scrobbler_post()
                    # Prepare current track:
                    self.scrobbler_prepare()
                elif self.scrob_time_now:
                    # Keep track of the total amount of time that the current song
                    # has been playing:
                    self.scrob_playing_duration += time.time() - self.scrob_time_now
            elif self.status and self.status.state == 'stop':
                if self.prevsonginfo and self.prevsonginfo.has_key('time'):
                    if self.scrob_playing_duration > 4 * 60 or self.scrob_playing_duration > int(self.prevsonginfo.time)/2:
                        # User stopped the client, post previous track if time
                        # criteria is met:
                        if self.scrob_start_time != "":
                            self.scrobbler_post()

    def get_new_artist_for_album_name(self):
        if self.songinfo and self.songinfo.has_key('album'):
            self.set_artist_for_album_name()
        elif self.songinfo and self.songinfo.has_key('artist'):
            self.current_artist_for_album_name = [self.songinfo, self.songinfo.artist]
        else:
            self.current_artist_for_album_name = [self.songinfo, ""]

    def set_volumebutton(self, stock_icon):
        image = gtk.image_new_from_stock(stock_icon, VOLUME_ICON_SIZE)
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
            row = int(self.status.song)
            self.boldrow(row)
            if self.songinfo:
                if not self.prevsonginfo or self.songinfo.file != self.prevsonginfo.file:
                    gobject.idle_add(self.keep_song_centered_in_list)
            self.prev_boldrow = row

        self.get_new_artist_for_album_name()

        self.update_cursong()
        self.update_wintitle()
        self.update_album_art()
        self.info_update(True)

    def scrobbler_prepare(self):
        if HAVE_AUDIOSCROBBLER:
            self.scrob_start_time = ""
            self.scrob_last_prepared = ""
            self.scrob_playing_duration = 0

            if self.use_scrobbler and self.songinfo:
                # No need to check if the song is 30 seconds or longer,
                # audioscrobbler.py takes care of that.
                if self.songinfo.has_key('time'):
                    self.scrobbler_np()

                    self.scrob_start_time = str(int(time.time()))
                    self.scrob_last_prepared = self.songinfo.file

    def scrobbler_np(self):
        thread = threading.Thread(target=self._do_scrobbler_np)
        thread.setDaemon(True)
        thread.start()

    def _do_scrobbler_np(self):
        self.scrobbler_init()
        if self.use_scrobbler and self.scrob_post and self.songinfo:
            if self.songinfo.has_key('artist') and \
               self.songinfo.has_key('title') and \
               self.songinfo.has_key('time'):
                if not self.songinfo.has_key('album'):
                    album = u''
                else:
                    album = self.songinfo['album']
                if not self.songinfo.has_key('track'):
                    tracknumber = u''
                else:
                    tracknumber = self.songinfo['track']
                self.scrob_post.nowplaying(self.songinfo['artist'],
                                            self.songinfo['title'],
                                            self.songinfo['time'],
                                            tracknumber,
                                            album,
                                            self.scrob_start_time)
        time.sleep(10)

    def scrobbler_post(self):
        self.scrobbler_init()
        if self.use_scrobbler and self.scrob_post and self.prevsonginfo:
            if self.prevsonginfo.has_key('artist') and \
               self.prevsonginfo.has_key('title') and \
               self.prevsonginfo.has_key('time'):
                if not self.prevsonginfo.has_key('album'):
                    album = u''
                else:
                    album = self.prevsonginfo['album']
                if not self.prevsonginfo.has_key('track'):
                    tracknumber = u''
                else:
                    tracknumber = self.prevsonginfo['track']
                self.scrob_post.addtrack(self.prevsonginfo['artist'],
                                                self.prevsonginfo['title'],
                                                self.prevsonginfo['time'],
                                                self.scrob_start_time,
                                                tracknumber,
                                                album)

                thread = threading.Thread(target=self._do_post_scrobbler)
                thread.setDaemon(True)
                thread.start()
        self.scrob_start_time = ""

    def _do_post_scrobbler(self):
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
                    self.currentdata[row][i + 1] = make_bold(self.currentdata[row][i + 1])
            except:
                pass

    def unbold_boldrow(self, row):
        if self.filterbox_visible:
            return
        if row > -1:
            try:
                for i in range(len(self.currentdata[row]) - 1):
                    self.currentdata[row][i + 1] = make_unbold(self.currentdata[row][i + 1])
            except:
                pass

    def update_progressbar(self):
        if self.conn and self.status and self.status.state in ['play', 'pause']:
            at, length = [float(c) for c in self.status.time.split(':')]
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
            if self.status and self.status.state in ['play', 'pause']:
                at, length = [int(c) for c in self.status.time.split(':')]
                at_time = convert_time(at)
                try:
                    time = convert_time(int(self.songinfo.time))
                    newtime = at_time + " / " + time
                except:
                    newtime = at_time
            else:
                newtime = ' '
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
                    total_time = convert_time(self.total_time)
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
                    songs_text = gettext.ngettext('song', 'songs', int(self.status.playlistlength))
                    if days:
                        status_text = str(self.status.playlistlength) + ' ' + songs_text + '   ' + days + ' ' + days_text + ', ' + hours + ' ' + hours_text + ', ' + _('and') + ' ' + mins + ' ' + mins_text
                    elif hours:
                        status_text = str(self.status.playlistlength) + ' ' + songs_text + '   ' + hours + ' ' + hours_text + ' ' + _('and') + ' ' + mins + ' ' + mins_text
                    elif mins:
                        status_text = str(self.status.playlistlength) + ' ' + songs_text + '   ' + mins + ' ' + mins_text
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

    def set_ellipsize_workaround(self):
        # Hacky workaround to ellipsize the expander - see http://bugzilla.gnome.org/show_bug.cgi?id=406528
        cursonglabelwidth = self.expander.get_allocation().width - 15
        if cursonglabelwidth > 0:
            self.cursonglabel1.set_size_request(cursonglabelwidth, -1)
            self.cursonglabel1.set_size_request(cursonglabelwidth, -1)

    def update_cursong(self):
        if self.conn and self.status and self.status.state in ['play', 'pause']:
            # We must show the trayprogressbar and trayalbumeventbox
            # before changing self.cursonglabel (and consequently calling
            # self.labelnotify()) in order to ensure that the notification
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

            self.set_ellipsize_workaround()

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
                self.traycursonglabel1.set_label(_('Not connected'))
            else:
                self.traycursonglabel1.set_label(_('Stopped'))
            self.trayprogressbar.hide()
            self.trayalbumeventbox.hide()
            self.trayalbumimage2.hide()
            self.traycursonglabel2.hide()
        self.update_infofile()

    def update_wintitle(self):
        if self.window_owner:
            if self.conn and self.status and self.status.state in ['play', 'pause']:
                newtitle = self.parse_formatting(self.titleformat, self.songinfo, False, True)
            else:
                newtitle = 'Sonata'
            if not self.last_title or self.last_title != newtitle:
                self.window.set_property('title', newtitle)
                self.last_title = newtitle

    def update_playlist(self):
        if self.conn:
            try:
                prev_songs = self.songs
            except:
                prev_songs = None
            self.songs = self.conn.do.playlistinfo()
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
                    self.total_time = self.total_time + int(track.time)
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
                    self.currentdata.set_value(iter, 0, int(track.id))
                    for index in range(len(items)):
                        self.currentdata.set_value(iter, index + 1, items[index])
                else:
                    # Add new item:
                    self.currentdata.append([int(track.id)] + items)
            # Remove excess songs:
            for i in range(currlen-songlen):
                iter = self.currentdata.get_iter((currlen-1-i,))
                self.currentdata.remove(iter)
            if not self.filterbox_visible:
                self.current.set_model(self.currentdata)
            if self.songinfo.has_key('pos'):
                currsong = int(self.songinfo.pos)
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
            self.update_column_indicators()
            self.update_statusbar()
            self.change_cursor(None)

    def update_column_indicators(self):
        # If we just sorted a column, display the sorting arrow:
        if self.column_sorted[0]:
            if self.column_sorted[1] == gtk.SORT_DESCENDING:
                self.hide_all_header_indicators(self.current, True)
                self.column_sorted[0].set_sort_order(gtk.SORT_ASCENDING)
                self.column_sorted = (None, gtk.SORT_ASCENDING)
            else:
                self.hide_all_header_indicators(self.current, True)
                self.column_sorted[0].set_sort_order(gtk.SORT_DESCENDING)
                self.column_sorted = (None, gtk.SORT_DESCENDING)

    def center_playlist(self, event):
        self.keep_song_centered_in_list()

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

    def hide_all_header_indicators(self, treeview, show_sorted_column):
        if not show_sorted_column:
            self.column_sorted = (None, gtk.SORT_DESCENDING)
        for column in treeview.get_columns():
            if show_sorted_column and column == self.column_sorted[0]:
                column.set_sort_indicator(True)
            else:
                column.set_sort_indicator(False)

    def keep_song_centered_in_list(self):
        if self.filterbox_visible:
            return
        if self.expanded and len(self.currentdata)>0:
            self.current.realize()
            try:
                row = self.songinfo.pos
                visible_rect = self.current.get_visible_rect()
                row_rect = self.current.get_background_area(row, self.columns[0])
                top_coord = (row_rect.y + row_rect.height - int(visible_rect.height/2)) + visible_rect.y
                self.current.scroll_to_point(-1, top_coord)
            except:
                pass

    def on_reset_image(self, action):
        if os.path.exists(self.target_image_filename(self.ART_LOCATION_HOMECOVERS)):
            os.remove(self.target_image_filename(self.ART_LOCATION_HOMECOVERS))
        self.create_art_location_none_file()
        self.lastalbumart = None
        self.update_album_art()

    def update_album_art(self):
        self.stop_art_update = True
        thread = threading.Thread(target=self.update_album_art2)
        thread.setDaemon(True)
        thread.start()

    def set_tooltip_art(self, pix):
        pix1 = pix.subpixbuf(0, 0, 51, 77)
        pix2 = pix.subpixbuf(51, 0, 26, 77)
        self.trayalbumimage1.set_from_pixbuf(pix1)
        self.trayalbumimage2.set_from_pixbuf(pix2)
        del pix1
        del pix2

    def update_album_art2(self):
        self.stop_art_update = False
        if not self.show_covers:
            return
        if self.conn and self.status and self.status.state in ['play', 'pause']:
            artist = getattr(self.songinfo, 'artist', "").replace("/", "")
            album = getattr(self.songinfo, 'album', "").replace("/", "")
            filename = self.target_image_filename()
            if filename == self.lastalbumart:
                # No need to update..
                self.stop_art_update = False
                return
            self.lastalbumart = None
            if os.path.exists(self.target_image_filename(self.ART_LOCATION_NONE)):
                # Use default Sonata icons to prevent remote/local artwork searching:
                self.set_default_icon_for_art()
                return
            songdir = os.path.dirname(self.songinfo.file)
            imgfound = self.check_for_local_images(songdir)
            if not imgfound:
                if self.covers_pref == self.ART_LOCAL_REMOTE:
                    imgfound = self.check_remote_images(artist, album, filename)
        else:
            self.set_default_icon_for_art()

    def create_art_location_none_file(self):
        # If this file exists, Sonata will use the "blank" default artwork for the song
        # We will only use this if the user explicitly resets the artwork.
        self.create_dir_if_not_existing('~/.covers/')
        filename = self.target_image_filename(self.ART_LOCATION_NONE)
        f = open(filename, 'w')
        f.close()

    def check_for_local_images(self, songdir):
        self.set_default_icon_for_art()
        self.misc_img_in_dir = None
        self.single_img_in_dir = None
        if os.path.exists(self.target_image_filename(self.ART_LOCATION_HOMECOVERS)):
            gobject.idle_add(self.set_image_for_cover, self.target_image_filename(self.ART_LOCATION_HOMECOVERS))
            return True
        elif os.path.exists(self.target_image_filename(self.ART_LOCATION_COVER)):
            gobject.idle_add(self.set_image_for_cover, self.target_image_filename(self.ART_LOCATION_COVER))
            return True
        elif os.path.exists(self.target_image_filename(self.ART_LOCATION_ALBUM)):
            gobject.idle_add(self.set_image_for_cover, self.target_image_filename(self.ART_LOCATION_ALBUM))
            return True
        elif os.path.exists(self.target_image_filename(self.ART_LOCATION_FOLDER)):
            gobject.idle_add(self.set_image_for_cover, self.target_image_filename(self.ART_LOCATION_FOLDER))
            return True
        elif self.art_location == self.ART_LOCATION_CUSTOM and len(self.art_location_custom_filename) > 0 and os.path.exists(self.target_image_filename(self.ART_LOCATION_CUSTOM)):
            gobject.idle_add(self.set_image_for_cover, self.target_image_filename(self.ART_LOCATION_CUSTOM))
            return True
        elif self.get_misc_img_in_path(songdir):
            self.misc_img_in_dir = self.get_misc_img_in_path(songdir)
            gobject.idle_add(self.set_image_for_cover, self.musicdir[self.profile_num] + songdir + "/" + self.misc_img_in_dir)
            return True
        elif self.get_single_img_in_path(songdir):
            self.single_img_in_dir = self.get_single_img_in_path(songdir)
            gobject.idle_add(self.set_image_for_cover, self.musicdir[self.profile_num] + songdir + "/" + self.single_img_in_dir)
            return True
        return False

    def check_remote_images(self, artist, album, filename):
        self.set_default_icon_for_art()
        self.download_image_to_filename(artist, album, filename)
        if os.path.exists(filename):
            gobject.idle_add(self.set_image_for_cover, filename)
            return True
        return False

    def set_default_icon_for_art(self):
        if self.albumimage.get_property('file') != self.sonatacd:
            gobject.idle_add(self.albumimage.set_from_file, self.sonatacd)
            gobject.idle_add(self.info_image.set_from_file, self.sonatacd_large)
        gobject.idle_add(self.set_tooltip_art, gtk.gdk.pixbuf_new_from_file(self.sonatacd))
        self.lastalbumart = None

    def get_single_img_in_path(self, songdir):
        single_img = None
        if os.path.exists(self.musicdir[self.profile_num] + songdir):
            for file in os.listdir(self.musicdir[self.profile_num] + songdir):
                # Check against gtk+ supported image formats
                for i in gtk.gdk.pixbuf_get_formats():
                    if os.path.splitext(file)[1].replace(".","").lower() in i['extensions']:
                        if single_img == None:
                            single_img = file
                        else:
                            return False
            return single_img
        else:
            return False

    def get_misc_img_in_path(self, songdir):
        if os.path.exists(self.musicdir[self.profile_num] + songdir):
            for f in self.ART_LOCATIONS_MISC:
                if os.path.exists(self.musicdir[self.profile_num] + songdir + "/" + f):
                    return f
        return False

    def set_image_for_cover(self, filename, info_img_only=False):
        if self.filename_is_for_current_song(filename):
            if os.path.exists(filename):
                # We use try here because the file might exist, but still
                # be downloading so it's not complete
                try:
                    pix = gtk.gdk.pixbuf_new_from_file(filename)
                    if not info_img_only:
                        (pix1, w, h) = self.get_pixbuf_of_size(pix, 75)
                        pix1 = self.pixbuf_add_border(pix1)
                        pix1 = self.pixbuf_pad(pix1, 77, 77)
                        self.albumimage.set_from_pixbuf(pix1)
                        self.set_tooltip_art(pix1)
                        del pix1
                    if self.info_imagebox.get_size_request()[0] == -1:
                        fullwidth = self.notebook.get_allocation()[2] - 50
                        (pix2, w, h) = self.get_pixbuf_of_size(pix, fullwidth)
                    else:
                        (pix2, w, h) = self.get_pixbuf_of_size(pix, 150)
                    pix2 = self.pixbuf_add_border(pix2)
                    self.info_image.set_from_pixbuf(pix2)
                    del pix2
                    self.lastalbumart = filename
                    del pix
                except:
                    pass
                self.call_gc_collect = True

    def filename_is_for_current_song(self, filename):
        # Since there can be multiple threads that are getting album art,
        # this will ensure that only the artwork for the currently playing
        # song is displayed
        if self.conn and self.status and self.status.state in ['play', 'pause']:
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
            if self.misc_img_in_dir and self.songinfo:
                songdir = os.path.dirname(self.songinfo.file)
                if filename == self.musicdir[self.profile_num] + songdir + "/" + self.misc_img_in_dir:
                    return True
            if self.single_img_in_dir and self.songinfo:
                songdir = os.path.dirname(self.songinfo.file)
                if filename == self.musicdir[self.profile_num] + songdir + "/" + self.single_img_in_dir:
                    return True
        # If we got this far, no match:
        return False

    def download_image_to_filename(self, artist, album, dest_filename, all_images=False, populate_imagelist=False):
        # Returns False if no images found
        imgfound = False
        if len(artist) == 0 and len(album) == 0:
            self.downloading_image = False
            return imgfound
        try:
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
            search_url = "http://webservices.amazon.com/onca/xml?Service=AWSECommerceService&AWSAccessKeyId=" + amazon_key + "&Operation=ItemSearch&SearchIndex=Music&Artist=" + artist + "&ResponseGroup=Images&Keywords=" + album
            request = urllib2.Request(search_url)
            opener = urllib2.build_opener()
            f = opener.open(request).read()
            curr_pos = 300    # Skip header..
            # Check if any results were returned; if not, search  again with just the artist name:
            url_start = f.find("<URL>http://", curr_pos)+len("<URL>")
            url_end = f.find("</URL>", curr_pos)
            if url_start > -1 and url_end > -1:
                img_url = f[url_start:url_end]
            if len(img_url) == 0:
                search_url = "http://webservices.amazon.com/onca/xml?Service=AWSECommerceService&AWSAccessKeyId=" + amazon_key + "&Operation=ItemSearch&SearchIndex=Music&Artist=" + artist + "&ResponseGroup=Images"
                request = urllib2.Request(search_url)
                opener = urllib2.build_opener()
                f = opener.open(request).read()
                url_start = f.find("<URL>http://", curr_pos)+len("<URL>")
                url_end = f.find("</URL>", curr_pos)
                if url_start > -1 and url_end > -1:
                    img_url = f[url_start:url_end]
            if all_images:
                curr_img = 1
                img_url = " "
                if len(img_url) == 0:
                    self.downloading_image = False
                    return imgfound
                while len(img_url) > 0 and curr_pos > 0:
                    img_url = ""
                    curr_pos = f.find("<LargeImage>", curr_pos+10)
                    if curr_pos > 0:
                        url_start = f.find("<URL>http://", curr_pos)+len("<URL>")
                        url_end = f.find("</URL>", curr_pos)
                        if url_start > -1 and url_end > -1:
                            img_url = f[url_start:url_end]
                        if len(img_url) > 0:
                            if self.stop_art_update:
                                self.downloading_image = False
                                return imgfound
                            dest_filename_curr = dest_filename.replace("<imagenum>", str(curr_img))
                            urllib.urlretrieve(img_url, dest_filename_curr)
                            if populate_imagelist:
                                # This populates self.imagelist for the remote image window
                                if os.path.exists(dest_filename_curr):
                                    pix = gtk.gdk.pixbuf_new_from_file(dest_filename_curr)
                                    pix = pix.scale_simple(148, 148, gtk.gdk.INTERP_HYPER)
                                    pix = self.pixbuf_add_border(pix)
                                    if self.stop_art_update:
                                        del pix
                                        self.downloading_image = False
                                        return imgfound
                                    self.imagelist.append([curr_img, pix])
                                    del pix
                                    self.remotefilelist.append(dest_filename_curr)
                                    imgfound = True
                                    if curr_img == 1:
                                        self.allow_art_search = True
                                self.change_cursor(None)
                            curr_img += 1
                            # Skip the next LargeImage:
                            curr_pos = f.find("<LargeImage>", curr_pos+10)
            else:
                curr_pos = f.find("<LargeImage>", curr_pos+10)
                url_start = f.find("<URL>http://", curr_pos)+len("<URL>")
                url_end = f.find("</URL>", curr_pos)
                if url_start > -1 and url_end > -1:
                    img_url = f[url_start:url_end]
                if len(img_url) > 0:
                    urllib.urlretrieve(img_url, dest_filename)
                    imgfound = True
        except:
            pass
        self.downloading_image = False
        return imgfound

    def set_notification_window_width(self):
        screen = self.window.get_screen()
        pointer_screen, px, py, _ = screen.get_display().get_pointer()
        monitor_num = screen.get_monitor_at_point(px, py)
        monitor = screen.get_monitor_geometry(monitor_num)
        self.notification_width = int(monitor.width * 0.30)
        if self.notification_width > self.NOTIFICATION_WIDTH_MAX:
            self.notification_width = self.NOTIFICATION_WIDTH_MAX
        elif self.notification_width < self.NOTIFICATION_WIDTH_MIN:
            self.notification_width = self.NOTIFICATION_WIDTH_MIN

    def labelnotify(self, *args):
        if self.sonata_loaded:
            if self.conn and self.status and self.status.state in ['play', 'pause']:
                if self.show_covers:
                    self.traytips.set_size_request(self.notification_width, -1)
                else:
                    self.traytips.set_size_request(self.notification_width-100, -1)
            else:
                self.traytips.set_size_request(-1, -1)
            if self.show_notification:
                try:
                    gobject.source_remove(self.traytips.notif_handler)
                except:
                    pass
                if self.conn and self.status and self.status.state in ['play', 'pause']:
                    try:
                        self.traytips.use_notifications_location = True
                        if HAVE_STATUS_ICON:
                            self.traytips._real_display(self.statusicon)
                        elif HAVE_EGG:
                            self.traytips._real_display(self.trayeventbox)
                        else:
                            self.traytips._real_display(None)
                        if self.popup_option != len(self.popuptimes)-1:
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

    def progressbarnotify_fraction(self, *args):
        self.trayprogressbar.set_fraction(self.progressbar.get_fraction())

    def progressbarnotify_text(self, *args):
        self.trayprogressbar.set_text(self.progressbar.get_text())

    def update_infofile(self):
        if self.use_infofile is True:
            try:
                info_file = open(self.infofile_path, 'w')

                if self.status.state in ['play']:
                    info_file.write('Status: ' + 'Playing' + '\n')
                elif self.status.state in ['pause']:
                    info_file.write('Status: ' + 'Paused' + '\n')
                elif self.status.state in ['stop']:
                    info_file.write('Status: ' + 'Stopped' + '\n')
                try:
                    info_file.write('Title: ' + self.songinfo.artist + ' - ' + self.songinfo.title + '\n')
                except:
                    try:
                        info_file.write('Title: ' + self.songinfo.title + '\n') # No Arist in streams
                    except:
                        info_file.write('Title: No - ID Tag\n')
                info_file.write('Album: ' + getattr(self.songinfo, 'album', 'No Data') + '\n')
                info_file.write('Track: ' + getattr(self.songinfo, 'track', '0') + '\n')
                info_file.write('File: ' + getattr(self.songinfo, 'file', 'No Data') + '\n')
                info_file.write('Time: ' + getattr(self.songinfo, 'time', '0') + '\n')
                info_file.write('Volume: ' + self.status.volume + '\n')
                info_file.write('Repeat: ' + self.status.repeat + '\n')
                info_file.write('Shuffle: ' + self.status.random + '\n')
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
        if self.use_scrobbler:
            self.scrobbler_save_cache()
        if self.conn and self.stop_on_exit:
            self.stop(None)
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
        self.set_ellipsize_workaround()

    def on_notebook_resize(self, widget, event):
        # Resize labels in info tab to prevent horiz scrollbar:
        labelwidth = self.notebook.allocation.width - self.info_left_label.allocation.width - self.info_imagebox.allocation.width - 60 # 60 accounts for vert scrollbar, box paddings, etc..
        if labelwidth > 100:
            for label in self.info_labels:
                label.set_size_request(labelwidth, -1)
        # Resize lyrics/album gtk labels:
        labelwidth = self.notebook.allocation.width - 40 # 60 accounts for vert scrollbar, box paddings, etc..
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
        if not (self.conn and self.status and self.status.state in ['play', 'pause']):
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
            if self.status and self.status.state in ['play','pause']:
                gobject.idle_add(self.keep_song_centered_in_list)
            self.window.set_geometry_hints(self.window)
        # Put focus to the notebook:
        self.on_notebook_page_change(self.notebook, 0, self.notebook.get_current_page())
        return

    # This callback allows the user to seek to a specific portion of the song
    def on_progressbar_button_press_event(self, widget, event):
        if event.button == 1:
            if self.status and self.status.state in ['play', 'pause']:
                at, length = [int(c) for c in self.status.time.split(':')]
                try:
                    progressbarsize = self.progressbar.allocation
                    seektime = int((event.x/progressbarsize.width) * length)
                    self.seek(int(self.status.song), seektime)
                except:
                    pass
            return True

    def on_progressbar_scroll_event(self, widget, event):
        if self.status and self.status.state in ['play', 'pause']:
            try:
                gobject.source_remove(self.seekidle)
            except:
                pass
            self.seekidle = gobject.idle_add(self.seek_when_idle, event.direction)
        return True

    def seek_when_idle(self, direction):
        at, length = [int(c) for c in self.status.time.split(':')]
        try:
            if direction == gtk.gdk.SCROLL_UP:
                seektime = int(self.status.time.split(":")[0]) - 5
                if seektime < 0: seektime = 0
            elif direction == gtk.gdk.SCROLL_DOWN:
                seektime = int(self.status.time.split(":")[0]) + 5
                if seektime > self.songinfo.time:
                    seektime = self.songinfo.time
            self.seek(int(self.status.song), seektime)
        except:
            pass

    def on_lyrics_search(self, event):
        artist = self.songinfo.artist
        title = self.songinfo.title
        dialog = gtk.Dialog('Lyrics Search', self.window, gtk.DIALOG_MODAL | gtk.DIALOG_DESTROY_WITH_PARENT, (gtk.STOCK_CANCEL, gtk.RESPONSE_REJECT, gtk.STOCK_FIND, gtk.RESPONSE_ACCEPT))
        dialog.action_area.get_children()[0].set_label(_("_Search"))
        dialog.action_area.get_children()[0].set_image(gtk.image_new_from_stock(gtk.STOCK_FIND, gtk.ICON_SIZE_MENU))
        dialog.set_role('lyricsSearch')
        artist_hbox = gtk.HBox()
        artist_label = gtk.Label(_('Artist Name') + ':')
        artist_hbox.pack_start(artist_label, False, False, 5)
        artist_entry = gtk.Entry()
        artist_entry.set_text(artist)
        artist_hbox.pack_start(artist_entry, True, True, 5)
        title_hbox = gtk.HBox()
        title_label = gtk.Label(_('Song Title') + ':')
        title_hbox.pack_start(title_label, False, False, 5)
        title_entry = gtk.Entry()
        title_entry.set_text(title)
        title_hbox.pack_start(title_entry, True, True, 5)
        self.set_label_widths_equal([artist_label, title_label])
        dialog.vbox.pack_start(artist_hbox)
        dialog.vbox.pack_start(title_hbox)
        dialog.set_default_response(gtk.RESPONSE_ACCEPT)
        dialog.vbox.show_all()
        response = dialog.run()
        if response == gtk.RESPONSE_ACCEPT:
            dialog.destroy()
            # Delete current lyrics:
            fname = strip_all_slashes(artist + '-' + title + '.txt')
            filename = os.path.expanduser('~/.lyrics/' + fname)
            if os.path.exists(filename):
                os.remove(filename)
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
        self.sort('artist', lower=lower_no_the)

    def on_sort_by_album(self, action):
        self.sort('album', lower=lower_no_the)

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
                custom_sort, custom_pos = self.first_tag_of_format(self.currentformat, col_num, 'L')

            for track in self.songs:
                dict = {}
                # Those items that don't have the specified tag will be put at
                # the end of the list (hence the 'zzzzzzz'):
                zzz = 'zzzzzzzz'
                if type == 'artist':
                    dict["sortby"] =  (lower_no_the(getattr(track,'artist', zzz)),
                                getattr(track,'album' , zzz).lower(),
                                self.sanitize_mpdtag(getattr(track,'disc', '0'), True, 0),
                                self.sanitize_mpdtag(getattr(track,'track', '0'), True, 0))
                elif type == 'album':
                    dict["sortby"] =  (getattr(track,'album', zzz).lower(),
                                self.sanitize_mpdtag(getattr(track,'disc', '0'), True, 0),
                                self.sanitize_mpdtag(getattr(track,'track', '0'), True, 0))
                elif type == 'file':
                    dict["sortby"] = getattr(track,'file', zzz).lower().split('/')[-1]
                elif type == 'dirfile':
                    dict["sortby"] = getattr(track,'file', zzz).lower()
                elif type == 'col':
                    # Sort by column:
                    dict["sortby"] = make_unbold(self.currentdata.get_value(self.currentdata.get_iter((track_num, 0)), col_num).lower())
                    if custom_sort:
                        dict["sortby"] = self.sanitize_song_length_for_sorting(dict["sortby"], custom_pos)
                else:
                    dict["sortby"] = getattr(track, type, zzz).lower()
                dict["id"] = int(track.id)
                list.append(dict)
                track_num = track_num + 1

            list.sort(key=lambda x: x["sortby"])

            pos = 0
            self.conn.send.command_list_begin()
            for item in list:
                self.conn.send.moveid(item["id"], pos)
                pos += 1
            self.conn.do.command_list_end()
            self.iterate_now()

    def first_tag_of_format(self, format, colnum, tag_letter):
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

    def sanitize_song_length_for_sorting(self, songlength, pos_of_string):
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
            self.conn.send.command_list_begin()
            while top < bot:
                self.conn.send.swap(top, bot)
                top = top + 1
                bot = bot - 1
            self.conn.do.command_list_end()
            self.iterate_now()

    def on_sort_random(self, action):
        if self.conn:
            if len(self.songs) == 0:
                return
            self.change_cursor(gtk.gdk.Cursor(gtk.gdk.WATCH))
            while gtk.events_pending():
                gtk.main_iteration()
            self.conn.do.shuffle()

    def on_drag_drop(self, treeview, drag_context, x, y, selection, info, timestamp):
        model = treeview.get_model()
        foobar, selected = self.current_selection.get_selected_rows()
        drop_info = treeview.get_dest_row_at_pos(x, y)

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
        self.conn.send.command_list_begin()
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
                        self.conn.send.moveid(id, dest)
                    else:
                        self.songs.pop(index)
                        self.conn.send.moveid(id, dest-1)
                    model.insert(dest, model[index])
                    moved_iters += [model.get_iter((dest,))]
                    model.remove(iter)
                else:
                    self.songs.insert(dest+1, self.songs[index])
                    if dest < index:
                        self.songs.pop(index+1)
                        self.conn.send.moveid(id, dest+1)
                    else:
                        self.songs.pop(index)
                        self.conn.send.moveid(id, dest)
                    model.insert(dest+1, model[index])
                    moved_iters += [model.get_iter((dest+1,))]
                    model.remove(iter)
            else:
                dest = len(self.songs) - 1
                self.conn.send.moveid(id, dest)
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
        self.conn.do.command_list_end()

        if drag_context.action == gtk.gdk.ACTION_MOVE:
            drag_context.finish(True, True, timestamp)
            self.hide_all_header_indicators(self.current, False)
        self.iterate_now()

        gobject.idle_add(self.drag_retain_selection, treeview.get_selection(), moved_iters)

    def drag_retain_selection(self, treeselection, moved_iters):
        treeselection.unselect_all()
        for iter in moved_iters:
            treeselection.select_iter(iter)

    def on_popup_menu(self, widget):
        self.set_menu_contextual_items_visible()
        gobject.idle_add(self.mainmenu.popup, None, None, self.position_menu, 3, 0)

    def updatedb(self, widget):
        if self.conn:
            if self.searchbutton.get_property('visible'):
                self.on_search_end(None)
            self.conn.do.update('/')
            self.iterate_now()

    def updatedb_path(self, action):
        if self.conn:
            if self.current_tab == self.TAB_LIBRARY:
                if self.searchbutton.get_property('visible'):
                    self.on_search_end(None)
                model, selected = self.browser_selection.get_selected_rows()
                iters = [model.get_iter(path) for path in selected]
                if len(iters) > 0:
                    # If there are selected rows, update these paths..
                    self.conn.send.command_list_begin()
                    for iter in iters:
                        self.conn.send.update(self.browserdata.get_value(iter, 1))
                    self.conn.do.command_list_end()
                else:
                    # If no selection, update the current path...
                    self.conn.do.update(self.wd)
                self.iterate_now()

    def on_image_activate(self, widget, event):
        self.window.handler_block(self.mainwinhandler)
        if event.button == 1 and widget == self.info_imagebox and self.lastalbumart:
            if not self.info_art_enlarged:
                self.info_imagebox.set_size_request(-1,-1)
                self.set_image_for_cover(self.lastalbumart, True)
                self.info_art_enlarged = True
            else:
                self.info_imagebox.set_size_request(152, -1)
                self.set_image_for_cover(self.lastalbumart, True)
                self.info_art_enlarged = False
            self.volume_hide()
            # Force a resize of the info labels, if needed:
            gobject.idle_add(self.on_notebook_resize, self.notebook, None)
        elif event.button == 1:
            if self.current_tab != self.TAB_INFO:
                self.switch_to_tab_name(self.TAB_INFO)
        elif event.button == 3:
            if self.conn and self.status and self.status.state in ['play', 'pause']:
                self.UIManager.get_widget('/imagemenu/chooseimage_menu/').hide()
                self.UIManager.get_widget('/imagemenu/localimage_menu/').hide()
                if self.covers_pref != self.ART_LOCAL:
                    self.UIManager.get_widget('/imagemenu/chooseimage_menu/').show()
                self.UIManager.get_widget('/imagemenu/localimage_menu/').show()
                artist = getattr(self.songinfo, 'artist', None)
                album = getattr(self.songinfo, 'album', None)
                if os.path.exists(self.target_image_filename(self.ART_LOCATION_NONE)):
                    self.UIManager.get_widget('/imagemenu/resetimage_menu/').set_sensitive(False)
                else:
                    self.UIManager.get_widget('/imagemenu/resetimage_menu/').set_sensitive(True)
                if artist or album:
                    self.imagemenu.popup(None, None, None, event.button, event.time)
        gobject.timeout_add(50, self.unblock_window_popup_handler)
        return False

    def on_image_motion_cb(self, widget, context, x, y, time):
        context.drag_status(gtk.gdk.ACTION_COPY, time)
        return True

    def on_image_drop_cb(self, widget, context, x, y, selection, info, time):
        if self.conn and self.status and self.status.state in ['play', 'pause']:
            uri = selection.data.strip()
            path = urllib.url2pathname(uri)
            paths = path.rsplit('\n')
            for i, path in enumerate(paths):
                paths[i] = path.rstrip('\r')
                # Clean up (remove preceding "file://" or "file:")
                if paths[i].startswith('file://'):
                    paths[i] = paths[i][7:]
                elif paths[i].startswith('file:'):
                    paths[i] = paths[i][5:]
                paths[i] = os.path.abspath(paths[i])
                if self.valid_image(paths[i]):
                    dest_filename = self.target_image_filename()
                    album = getattr(self.songinfo, 'album', "").replace("/", "")
                    artist = self.current_artist_for_album_name[1].replace("/", "")
                    self.remove_art_location_none_file(artist, album)
                    self.create_dir_if_not_existing('~/.covers/')
                    if dest_filename != paths[i]:
                        shutil.copyfile(paths[i], dest_filename)
                    self.lastalbumart = None
                    self.update_album_art()

    def target_lyrics_filename(self, artist, title, force_location=None):
        if self.conn:
            if force_location is not None:
                lyrics_loc = force_location
            else:
                lyrics_loc = self.lyrics_location
            if lyrics_loc == self.LYRICS_LOCATION_HOME:
                targetfile = os.path.expanduser("~/.lyrics/" + artist + "-" + title + ".txt")
            elif lyrics_loc == self.LYRICS_LOCATION_PATH:
                targetfile = self.musicdir[self.profile_num] + os.path.dirname(self.songinfo.file) + "/" + artist + "-" + title + ".txt"
            try:
                return targetfile.decode(self.enc).encode('utf8')
            except:
                return targetfile

    def target_image_filename(self, force_location=None):
        if self.conn:
            if force_location is not None:
                art_loc = force_location
            else:
                art_loc = self.art_location
            if art_loc == self.ART_LOCATION_HOMECOVERS:
                album = getattr(self.songinfo, 'album', "").replace("/", "")
                artist = self.current_artist_for_album_name[1].replace("/", "")
                targetfile = os.path.expanduser("~/.covers/" + artist + "-" + album + ".jpg")
            elif art_loc == self.ART_LOCATION_COVER:
                targetfile = self.musicdir[self.profile_num] + os.path.dirname(self.songinfo.file) + "/cover.jpg"
            elif art_loc == self.ART_LOCATION_FOLDER:
                targetfile = self.musicdir[self.profile_num] + os.path.dirname(self.songinfo.file) + "/folder.jpg"
            elif art_loc == self.ART_LOCATION_ALBUM:
                targetfile = self.musicdir[self.profile_num] + os.path.dirname(self.songinfo.file) + "/album.jpg"
            elif art_loc == self.ART_LOCATION_CUSTOM:
                targetfile = self.musicdir[self.profile_num] + os.path.dirname(self.songinfo.file) + "/" + self.art_location_custom_filename
            elif art_loc == self.ART_LOCATION_NONE:
                # flag filename to indicate that we should use the default Sonata icons:
                album = getattr(self.songinfo, 'album', "").replace("/", "")
                artist = self.current_artist_for_album_name[1].replace("/", "")
                targetfile = os.path.expanduser("~/.covers/" + artist + "-" + album + "-" + self.ART_LOCATION_NONE_FLAG + ".jpg")
            try:
                return targetfile.decode(self.enc).encode('utf8')
            except:
                return targetfile

    def valid_image(self, file):
        test = gtk.gdk.pixbuf_get_file_info(file)
        if test == None:
            return False
        else:
            return True

    def set_artist_for_album_name(self):
        # Determine if album_name is a various artists album. We'll use a little
        # bit of hard-coded logic and assume that an album is a VA album if
        # there are more than 3 artists with the same album_name. The reason for
        # not assuming an album with >1 artists is a VA album is to prevent
        # marking albums by different artists that aren't actually VA (e.g.
        # albums with the name "Untitled", "Self-titled", and so on). Either
        # the artist name or "Various Artists" will be returned.
        # Update: We will also check that the files are in the same path
        # to attempt to prevent Various Artists being set on a very common
        # album name like 'Unplugged'.
        if self.current_artist_for_album_name[0] == self.songinfo:
            # Re-use existing info:
            return self.current_artist_for_album_name[1]
        songs = self.browse_search_album(self.songinfo.album)
        artists = []
        return_artist = ""
        for song in songs:
            if song.has_key('artist'):
                if os.path.dirname(self.songinfo.file) == os.path.dirname(song.file):
                    artists.append(song.artist)
                    if self.songinfo.file == song.file:
                        return_artist = song.artist
        (artists, i) = remove_list_duplicates(artists, [], False)
        if len(artists) > 3:
            return_artist = _("Various Artists")
        self.current_artist_for_album_name = [self.songinfo, return_artist]
        return return_artist

    def reset_artist_for_album_name(self):
        self.current_artist_for_album_name = [None, ""]

    def follow_if_link(self, text_view, iter):
        tags = iter.get_tags()
        for tag in tags:
            url = tag.get_data("url")
                if url != 0:
                self.show_website(None, None, url)
                break

    def get_pixbuf_of_size(self, pixbuf, size):
        # Creates a pixbuf that fits in the specified square of sizexsize
        # while preserving the aspect ratio
        # Returns tuple: (scaled_pixbuf, actual_width, actual_height)
        image_width = pixbuf.get_width()
        image_height = pixbuf.get_height()
        if image_width-size > image_height-size:
            if image_width > size:
                image_height = int(size/float(image_width)*image_height)
                image_width = size
        else:
            if image_height > size:
                image_width = int(size/float(image_height)*image_width)
                image_height = size
        crop_pixbuf = pixbuf.scale_simple(image_width, image_height, gtk.gdk.INTERP_HYPER)
        return (crop_pixbuf, image_width, image_height)

    def pixbuf_add_border(self, pix):
        # Add a gray outline to pix. This will increase the pixbuf size by
        # 2 pixels lengthwise and heightwise, 1 on each side. Returns pixbuf.
        width = pix.get_width()
        height = pix.get_height()
        newpix = gtk.gdk.Pixbuf(gtk.gdk.COLORSPACE_RGB, True, 8, width+2, height+2)
        newpix.fill(0x858585ff)
        pix.copy_area(0, 0, width, height, newpix, 1, 1)
        return newpix

    def pixbuf_pad(self, pix, w, h):
        # Adds transparent canvas so that the pixbuf is of size (w,h). Also
        # centers the pixbuf in the canvas.
        width = pix.get_width()
        height = pix.get_height()
        transpbox = gtk.gdk.Pixbuf(gtk.gdk.COLORSPACE_RGB, True, 8, w, h)
        transpbox.fill(0xffff00)
        x_pos = int((w - width)/2)
        y_pos = int((h - height)/2)
        pix.copy_area(0, 0, width, height, transpbox, x_pos, y_pos)
        return transpbox

    def unblock_window_popup_handler(self):
        self.window.handler_unblock(self.mainwinhandler)

    def change_cursor(self, type):
        for i in gtk.gdk.window_get_toplevels():
            i.set_cursor(type)

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

    def on_choose_image_local(self, widget):
        dialog = gtk.FileChooserDialog(title=_("Open Image"),action=gtk.FILE_CHOOSER_ACTION_OPEN,buttons=(gtk.STOCK_CANCEL,gtk.RESPONSE_CANCEL,gtk.STOCK_OPEN,gtk.RESPONSE_OK))
        filter = gtk.FileFilter()
        filter.set_name(_("Images"))
        filter.add_pixbuf_formats()
        dialog.add_filter(filter)
        filter = gtk.FileFilter()
        filter.set_name(_("All files"))
        filter.add_pattern("*")
        dialog.add_filter(filter)
        preview = gtk.Image()
        dialog.set_preview_widget(preview)
        dialog.set_use_preview_label(False)
        dialog.connect("update-preview", self.update_preview, preview)
        album = getattr(self.songinfo, 'album', "").replace("/", "")
        artist = self.current_artist_for_album_name[1].replace("/", "")
        dialog.connect("response", self.choose_image_local_response, artist, album)
        dialog.set_default_response(gtk.RESPONSE_OK)
        songdir = os.path.dirname(self.songinfo.file)
        currdir = self.musicdir[self.profile_num] + songdir
        if os.path.exists(currdir):
            dialog.set_current_folder(currdir)
        self.local_dest_filename = self.target_image_filename()
        dialog.show()

    def choose_image_local_response(self, dialog, response, artist, album):
        if response == gtk.RESPONSE_OK:
            filename = dialog.get_filenames()[0]
            self.remove_art_location_none_file(artist, album)
            # Copy file to covers dir:
            self.create_dir_if_not_existing('~/.covers/')
            if self.local_dest_filename != filename:
                shutil.copyfile(filename, self.local_dest_filename)
            # And finally, set the image in the interface:
            self.lastalbumart = None
            self.update_album_art()
        dialog.destroy()

    def remove_art_location_none_file(self, artist, album):
        # If the flag file exists (to tell Sonata to use the default artwork icons), remove the file
        delete_filename = os.path.expanduser("~/.covers/" + artist + "-" + album + "-" + self.ART_LOCATION_NONE_FLAG + ".jpg")
        if os.path.exists(delete_filename):
            os.remove(delete_filename)

    def on_choose_image(self, widget):
        self.choose_dialog = gtk.Dialog(_("Choose Cover Art"), self.window, gtk.DIALOG_MODAL, (gtk.STOCK_CANCEL, gtk.RESPONSE_REJECT))
        self.choose_dialog.set_role('chooseCoverArt')
        choosebutton = self.choose_dialog.add_button(_("Choose"), gtk.RESPONSE_ACCEPT)
        chooseimage = gtk.Image()
        chooseimage.set_from_stock(gtk.STOCK_CONVERT, gtk.ICON_SIZE_BUTTON)
        choosebutton.set_image(chooseimage)
        self.choose_dialog.set_has_separator(False)
        self.choose_dialog.set_default(choosebutton)
        self.choose_dialog.set_resizable(False)
        scroll = gtk.ScrolledWindow()
        scroll.set_size_request(350, 325)
        scroll.set_policy(gtk.POLICY_NEVER, gtk.POLICY_ALWAYS)
        self.imagelist = gtk.ListStore(int, gtk.gdk.Pixbuf)
        imagewidget = gtk.IconView()
        imagewidget.set_columns(2)
        imagewidget.set_item_width(150)
        imagewidget.set_spacing(5)
        imagewidget.set_margin(10)
        imagewidget.set_selection_mode(gtk.SELECTION_SINGLE)
        scroll.add(imagewidget)
        self.choose_dialog.vbox.pack_start(scroll, False, False, 0)
        searchexpander = gtk.expander_new_with_mnemonic(_("Edit search terms"))
        vbox = gtk.VBox()
        hbox1 = gtk.HBox()
        artistlabel = gtk.Label(_("Artist") + ": ")
        hbox1.pack_start(artistlabel)
        self.remote_artistentry = gtk.Entry()
        self.tooltips.set_tip(self.remote_artistentry, _("Press enter to search for these terms."))
        self.remote_artistentry.connect('activate', self.choose_image_update, imagewidget)
        hbox1.pack_start(self.remote_artistentry, True, True, 5)
        hbox2 = gtk.HBox()
        albumlabel = gtk.Label(_("Album") + ": ")
        hbox2.pack_start(albumlabel)
        self.remote_albumentry = gtk.Entry()
        self.tooltips.set_tip(self.remote_albumentry, _("Press enter to search for these terms."))
        self.remote_albumentry.connect('activate', self.choose_image_update, imagewidget)
        hbox2.pack_start(self.remote_albumentry, True, True, 5)
        self.set_label_widths_equal([artistlabel, albumlabel])
        artistlabel.set_alignment(1, 0.5)
        albumlabel.set_alignment(1, 0.5)
        vbox.pack_start(hbox1)
        vbox.pack_start(hbox2)
        searchexpander.add(vbox)
        self.choose_dialog.vbox.pack_start(searchexpander, True, True, 0)
        self.choose_dialog.show_all()
        self.chooseimage_visible = True
        self.remotefilelist = []
        self.remote_dest_filename = self.target_image_filename()
        album = getattr(self.songinfo, 'album', "").replace("/", "")
        artist = self.current_artist_for_album_name[1].replace("/", "")
        imagewidget.connect('item-activated', self.replace_cover, artist, album)
        self.choose_dialog.connect('response', self.choose_image_response, imagewidget, artist, album)
        self.remote_artistentry.set_text(artist)
        self.remote_albumentry.set_text(album)
        self.allow_art_search = True
        self.choose_image_update(None, imagewidget)

    def choose_image_update(self, entry, imagewidget):
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
        self.change_cursor(gtk.gdk.Cursor(gtk.gdk.WATCH))
        thread = threading.Thread(target=self.choose_image_update2, args=(imagewidget, None))
        thread.setDaemon(True)
        thread.start()

    def choose_image_update2(self, imagewidget, ignore):
        self.stop_art_update = False
        # Retrieve all images from amazon:
        artist_search = self.remote_artistentry.get_text()
        album_search = self.remote_albumentry.get_text()
        if len(artist_search) == 0 and len(album_search) == 0:
            gobject.idle_add(self.choose_image_no_artist_or_album_dialog, imagewidget)
            return
        self.create_dir_if_not_existing('~/.covers/')
        filename = os.path.expanduser("~/.covers/temp/<imagenum>.jpg")
        if os.path.exists(os.path.dirname(filename)):
            removeall(os.path.dirname(filename))
        if not os.path.exists(os.path.dirname(filename)):
            os.mkdir(os.path.dirname(filename))
        imgfound = self.download_image_to_filename(artist_search, album_search, filename, True, True)
        self.change_cursor(None)
        if self.chooseimage_visible:
            if not imgfound:
                gobject.idle_add(self.choose_image_no_art_found, imagewidget)
                self.allow_art_search = True
        self.call_gc_collect = True

    def choose_image_no_artist_or_album_dialog(self, imagewidget):
        liststore = gtk.ListStore(int, str)
        liststore.append([0, _("No artist or album name found.")])
        imagewidget.set_pixbuf_column(-1)
        imagewidget.set_model(liststore)
        imagewidget.set_text_column(1)

    def choose_image_no_art_found(self, imagewidget):
        liststore = gtk.ListStore(int, str)
        liststore.append([0, _("No cover art found.")])
        imagewidget.set_pixbuf_column(-1)
        imagewidget.set_model(liststore)
        imagewidget.set_text_column(1)

    def choose_image_dialog_response(self, dialog, response_id):
        dialog.destroy()

    def choose_image_response(self, dialog, response_id, imagewidget, artist, album):
        self.stop_art_update = True
        if response_id == gtk.RESPONSE_ACCEPT:
            try:
                self.replace_cover(imagewidget, imagewidget.get_selected_items()[0], artist, album)
            except:
                dialog.destroy()
                pass
        else:
            dialog.destroy()
        self.change_cursor(None)
        self.chooseimage_visible = False

    def replace_cover(self, iconview, path, artist, album):
        self.stop_art_update = True
        image_num = int(path[0])
        if len(self.remotefilelist) > 0:
            filename = self.remotefilelist[image_num]
            if os.path.exists(filename):
                self.remove_art_location_none_file(artist, album)
                self.create_dir_if_not_existing('~/.covers/')
                shutil.move(filename, self.remote_dest_filename)
                # And finally, set the image in the interface:
                self.lastalbumart = None
                self.update_album_art()
                # Clean up..
                if os.path.exists(os.path.dirname(filename)):
                    removeall(os.path.dirname(filename))
        self.chooseimage_visible = False
        self.choose_dialog.destroy()
        while self.downloading_image:
            gtk.main_iteration()

    def update_column_widths(self):
        if not self.withdrawn:
            self.columnwidths = []
            for i in range(len(self.columns) - 1):
                self.columnwidths.append(self.columns[i].get_width())
            if self.expanderwindow.get_hscrollbar().get_property('visible'):
                self.columnwidths.append(self.columns[len(self.columns) - 1].get_width())
            else:
                # The last column may be larger than specified, since it expands to fill
                # the treeview, so lets get the minimum of the current width and the
                # fixed width. This will prevent a horizontal scrollbar from unnecessarily
                # showing sometimes.
                self.columnwidths.append(min(self.columns[len(self.columns) - 1].get_fixed_width(), self.columns[len(self.columns) - 1].get_width()))

    def trayaction_menu(self, status_icon, button, activate_time):
        self.traymenu.popup(None, None, None, button, activate_time)

    def trayaction_activate(self, status_icon):
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
            gobject.timeout_add(100, self.set_ignore_toggle_signal_false)

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

    def trayaction(self, widget, event):
        # Clicking on an egg system tray icon:
        if event.button == 1 and not self.ignore_toggle_signal: # Left button shows/hides window(s)
            self.trayaction_activate(None)
        elif event.button == 2: # Middle button will play/pause
            if self.conn:
                self.pp(self.trayeventbox)
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
            self.update_column_widths()
            self.window.hide()
            self.withdrawn = True
            self.UIManager.get_widget('/traymenu/showmenu').set_active(False)

    def withdraw_app_toggle(self, action):
        if self.ignore_toggle_signal:
            return
        self.ignore_toggle_signal = True
        if self.UIManager.get_widget('/traymenu/showmenu').get_active() == True:
            self.withdraw_app_undo()
        else:
            self.withdraw_app()
        gobject.timeout_add(500, self.set_ignore_toggle_signal_false)

    def set_ignore_toggle_signal_false(self):
        self.ignore_toggle_signal = False

    # Change volume on mousewheel over systray icon:
    def trayaction_scroll(self, widget, event):
        self.on_volumebutton_scroll(widget, event)

    def trayaction_size(self, widget, allocation):
        if not self.eggtrayheight or self.eggtrayheight != widget.allocation.height:
            self.eggtrayheight = widget.allocation.height
            if self.eggtrayfile > 5:
                self.trayimage.set_from_pixbuf(self.get_pixbuf_of_size(gtk.gdk.pixbuf_new_from_file(self.eggtrayfile), self.eggtrayheight)[0])

    def quit_activate(self, widget):
        self.window.destroy()

    def on_current_click(self, treeview, path, column):
        model = self.current.get_model()
        if self.filterbox_visible:
            self.searchfilter_toggle(None)
        try:
            iter = model.get_iter(path)
            self.conn.do.playid(self.current_get_songid(iter, model))
        except:
            pass
        self.iterate_now()

    def switch_to_tab_name(self, tab_name):
        self.notebook.set_current_page(self.notebook_get_tab_num(self.notebook, tab_name))

    def switch_to_tab_num(self, tab_num):
        vis_tabnum = self.notebook_get_visible_tab_num(self.notebook, tab_num)
        if vis_tabnum <> -1:
            self.notebook.set_current_page(vis_tabnum)

    def switch_to_tab1(self, action):
        self.switch_to_tab_num(0)

    def switch_to_tab2(self, action):
        self.switch_to_tab_num(1)

    def switch_to_tab3(self, action):
        self.switch_to_tab_num(2)

    def switch_to_tab4(self, action):
        self.switch_to_tab_num(3)

    def switch_to_tab5(self, action):
        self.switch_to_tab_num(4)

    def volume_lower(self, action):
        new_volume = int(self.volumescale.get_adjustment().get_value()) - 5
        if new_volume < 0:
            new_volume = 0
        self.volumescale.get_adjustment().set_value(new_volume)
        self.on_volumescale_change(self.volumescale, 0, 0)

    def volume_raise(self, action):
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
                self.volume_raise(None)
            elif event.direction == gtk.gdk.SCROLL_DOWN:
                self.volume_lower(None)
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
        self.conn.do.setvol(new_volume)
        self.iterate_now()
        return

    def volume_hide(self):
        self.volumebutton.set_active(False)
        if self.volumewindow.get_property('visible'):
            self.volumewindow.hide()

    # Control callbacks
    def pp(self, widget):
        if self.conn and self.status:
            if self.status.state in ('stop', 'pause'):
                self.conn.do.play()
            elif self.status.state == 'play':
                self.conn.do.pause(1)
            self.iterate_now()
        return

    def stop(self, widget):
        if self.conn:
            self.conn.do.stop()
            self.iterate_now()
        return

    def prev(self, widget):
        if self.conn:
            self.conn.do.previous()
            self.iterate_now()
        return

    def next(self, widget):
        if self.conn:
            self.conn.do.next()
            self.iterate_now()
        return

    def mmpp(self, keys, key):
        self.pp(None)

    def mmstop(self, keys, key):
        self.stop(None)

    def mmprev(self, keys, key):
        self.prev(None)

    def mmnext(self, keys, key):
        self.next(None)

    def remove(self, widget):
        if self.conn:
            while gtk.events_pending():
                gtk.main_iteration()
            if self.current_tab == self.TAB_CURRENT:
                model, selected = self.current_selection.get_selected_rows()
                if len(selected) == len(self.currentdata) and not self.filterbox_visible:
                    # Everything is selected, clear:
                    self.conn.do.clear()
                elif len(selected) > 0:
                    selected.reverse()
                    if not self.filterbox_visible:
                        # If we remove an item from the filtered results, this
                        # causes a visual refresh in the interface.
                        self.current.set_model(None)
                    self.conn.send.command_list_begin()
                    for path in selected:
                        if not self.filterbox_visible:
                            rownum = path[0]
                        else:
                            rownum = self.filter_row_mapping[path[0]]
                        iter = self.currentdata.get_iter((rownum, 0))
                        self.conn.send.deleteid(self.current_get_songid(iter, self.currentdata))
                        # Prevents the entire playlist from refreshing:
                        self.songs.pop(rownum)
                        self.currentdata.remove(iter)
                    self.conn.do.command_list_end()
                    if not self.filterbox_visible:
                        self.current.set_model(model)
            elif self.current_tab == self.TAB_PLAYLISTS:
                model, selected = self.playlists_selection.get_selected_rows()
                if show_error_msg_yesno(self.window, gettext.ngettext("Delete the selected playlist?", "Delete the selected playlists?", int(len(selected))), gettext.ngettext("Delete Playlist", "Delete Playlists", int(len(selected))), 'deletePlaylist') == gtk.RESPONSE_YES:
                    iters = [model.get_iter(path) for path in selected]
                    for iter in iters:
                        self.conn.do.rm(unescape_html(self.playlistsdata.get_value(iter, 1)))
                    self.playlists_populate()
            elif self.current_tab == self.TAB_STREAMS:
                model, selected = self.streams_selection.get_selected_rows()
                if show_error_msg_yesno(self.window, gettext.ngettext("Delete the selected stream?", "Delete the selected streams?", int(len(selected))), gettext.ngettext("Delete Stream", "Delete Streams", int(len(selected))), 'deleteStreams') == gtk.RESPONSE_YES:
                    iters = [model.get_iter(path) for path in selected]
                    for iter in iters:
                        stream_removed = False
                        for i in range(len(self.stream_names)):
                            if not stream_removed:
                                if self.streamsdata.get_value(iter, 1) == escape_html(self.stream_names[i]):
                                    self.stream_names.pop(i)
                                    self.stream_uris.pop(i)
                                    stream_removed = True
                    self.streams_populate()
            self.iterate_now()

    def randomize(self, widget):
        # Ironically enough, the command to turn shuffle on/off is called
        # random, and the command to randomize the playlist is called shuffle.
        self.conn.do.shuffle()
        return

    def clear(self, widget):
        if self.conn:
            self.conn.do.clear()
            self.iterate_now()
        return

    def on_repeat_clicked(self, widget):
        if self.conn:
            if widget.get_active():
                self.conn.do.repeat(1)
            else:
                self.conn.do.repeat(0)

    def on_shuffle_clicked(self, widget):
        if self.conn:
            if widget.get_active():
                self.conn.do.random(1)
            else:
                self.conn.do.random(0)

    def prefs(self, widget):
        prefswindow = gtk.Dialog(_("Preferences"), self.window, flags=gtk.DIALOG_DESTROY_WITH_PARENT)
        prefswindow.set_role('preferences')
        prefswindow.set_resizable(False)
        prefswindow.set_has_separator(False)
        hbox = gtk.HBox()
        prefsnotebook = gtk.Notebook()
        # MPD tab
        mpdlabel = gtk.Label()
        mpdlabel.set_markup('<b>' + _('MPD Connection') + '</b>')
        mpdlabel.set_alignment(0, 1)
        controlbox = gtk.HBox()
        profiles = gtk.combo_box_new_text()
        add_profile = gtk.Button()
        add_profile.set_image(gtk.image_new_from_stock(gtk.STOCK_ADD, gtk.ICON_SIZE_MENU))
        self.tooltips.set_tip(add_profile, _("Add new profile"))
        remove_profile = gtk.Button()
        remove_profile.set_image(gtk.image_new_from_stock(gtk.STOCK_REMOVE, gtk.ICON_SIZE_MENU))
        self.tooltips.set_tip(remove_profile, _("Remove current profile"))
        self.prefs_populate_profile_combo(profiles, self.profile_num, remove_profile)
        controlbox.pack_start(profiles, False, False, 2)
        controlbox.pack_start(remove_profile, False, False, 2)
        controlbox.pack_start(add_profile, False, False, 2)
        namebox = gtk.HBox()
        namelabel = gtk.Label(_("Name") + ":")
        namebox.pack_start(namelabel, False, False, 0)
        nameentry = gtk.Entry()
        namebox.pack_start(nameentry, True, True, 10)
        hostbox = gtk.HBox()
        hostlabel = gtk.Label(_("Host") + ":")
        hostbox.pack_start(hostlabel, False, False, 0)
        hostentry = gtk.Entry()
        hostbox.pack_start(hostentry, True, True, 10)
        portbox = gtk.HBox()
        portlabel = gtk.Label(_("Port") + ":")
        portbox.pack_start(portlabel, False, False, 0)
        portentry = gtk.Entry()
        portbox.pack_start(portentry, True, True, 10)
        dirbox = gtk.HBox()
        dirlabel = gtk.Label(_("Music dir") + ":")
        dirbox.pack_start(dirlabel, False, False, 0)
        direntry = gtk.Entry()
        direntry.connect('changed', self.prefs_direntry_changed, profiles)
        dirbox.pack_start(direntry, True, True, 10)
        passwordbox = gtk.HBox()
        passwordlabel = gtk.Label(_("Password") + ":")
        passwordbox.pack_start(passwordlabel, False, False, 0)
        passwordentry = gtk.Entry()
        passwordentry.set_visibility(False)
        self.tooltips.set_tip(passwordentry, _("Leave blank if no password is required."))
        passwordbox.pack_start(passwordentry, True, True, 10)
        mpd_labels = [namelabel, hostlabel, portlabel, passwordlabel, dirlabel]
        for label in mpd_labels:
            label.set_alignment(0, 0.5)
        self.set_label_widths_equal(mpd_labels)
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
        table.attach(gtk.Label(), 1, 3, 1, 2, gtk.FILL|gtk.EXPAND, gtk.FILL|gtk.EXPAND, 10, 0)
        table.attach(namebox, 1, 3, 2, 3, gtk.FILL|gtk.EXPAND, gtk.FILL|gtk.EXPAND, 10, 0)
        table.attach(hostbox, 1, 3, 3, 4, gtk.FILL|gtk.EXPAND, gtk.FILL|gtk.EXPAND, 10, 0)
        table.attach(portbox, 1, 3, 4, 5, gtk.FILL|gtk.EXPAND, gtk.FILL|gtk.EXPAND, 10, 0)
        table.attach(passwordbox, 1, 3, 5, 6, gtk.FILL|gtk.EXPAND, gtk.FILL|gtk.EXPAND, 10, 0)
        table.attach(dirbox, 1, 3, 6, 7, gtk.FILL|gtk.EXPAND, gtk.FILL|gtk.EXPAND, 10, 0)
        table.attach(gtk.Label(), 1, 3, 7, 8, gtk.FILL|gtk.EXPAND, gtk.FILL|gtk.EXPAND, 10, 0)
        mpd_frame.add(table)
        mpd_frame.set_label_widget(controlbox)
        mpd_table = gtk.Table(9, 2, False)
        mpd_table.set_col_spacings(3)
        mpd_table.attach(gtk.Label(), 1, 3, 1, 2, gtk.FILL|gtk.EXPAND, gtk.FILL|gtk.EXPAND, 10, 0)
        mpd_table.attach(mpdlabel, 1, 3, 2, 3, gtk.FILL|gtk.EXPAND, gtk.FILL|gtk.EXPAND, 15, 0)
        mpd_table.attach(gtk.Label(), 1, 3, 3, 4, gtk.FILL|gtk.EXPAND, gtk.FILL|gtk.EXPAND, 10, 0)
        mpd_table.attach(mpd_frame, 1, 3, 4, 10, gtk.FILL|gtk.EXPAND, gtk.FILL|gtk.EXPAND, 30, 0)
        mpd_table.attach(gtk.Label(), 1, 3, 10, 11, gtk.FILL|gtk.EXPAND, gtk.FILL|gtk.EXPAND, 30, 0)
        mpd_table.attach(autoconnect, 1, 3, 11, 12, gtk.FILL|gtk.EXPAND, gtk.FILL|gtk.EXPAND, 30, 0)
        mpd_table.attach(gtk.Label(), 1, 3, 12, 13, gtk.FILL|gtk.EXPAND, gtk.FILL|gtk.EXPAND, 30, 0)
        mpd_table.attach(gtk.Label(), 1, 3, 13, 14, gtk.FILL|gtk.EXPAND, gtk.FILL|gtk.EXPAND, 30, 0)
        # Extras tab
        if not HAVE_AUDIOSCROBBLER:
            self.use_scrobbler = False
        as_label = gtk.Label()
        as_label.set_markup('<b>' + _('Extras') + '</b>')
        as_frame = gtk.Frame()
        as_frame.set_label_widget(as_label)
        as_frame.set_shadow_type(gtk.SHADOW_NONE)
        as_frame.set_border_width(15)
        as_vbox = gtk.VBox()
        as_vbox.set_border_width(15)
        as_checkbox = gtk.CheckButton(_("Enable Audioscrobbler"))
        as_checkbox.set_active(self.use_scrobbler)
        as_vbox.pack_start(as_checkbox, False)
        as_table = gtk.Table(2, 2)
        as_table.set_col_spacings(3)
        as_user_label = gtk.Label("          " + _("Username:"))
        as_pass_label = gtk.Label("          " + _("Password:"))
        as_user_entry = gtk.Entry()
        as_user_entry.set_text(self.as_username)
        as_user_entry.connect('changed', self.prefs_as_username_changed)
        as_pass_entry = gtk.Entry()
        as_pass_entry.set_visibility(False)
        as_pass_entry.set_text(self.as_password)
        as_pass_entry.connect('changed', self.prefs_as_password_changed)
        displaylabel2 = gtk.Label()
        displaylabel2.set_markup('<b>' + _('Notification') + '</b>')
        displaylabel2.set_alignment(0, 1)
        display_notification = gtk.CheckButton(_("Popup notification on song changes"))
        display_notification.set_active(self.show_notification)
        notifhbox = gtk.HBox()
        notif_blank = gtk.Label()
        notif_blank.set_alignment(1, 0.5)
        notifhbox.pack_start(notif_blank)
        notification_options = gtk.combo_box_new_text()
        for i in self.popuptimes:
            if i != _('Entire song'):
                notification_options.append_text(i + ' ' + gettext.ngettext('second', 'seconds', int(i)))
            else:
                notification_options.append_text(i)
        notification_options.set_active(self.popup_option)
        notification_options.connect('changed', self.prefs_notiftime_changed)
        notification_locs = gtk.combo_box_new_text()
        for i in self.popuplocations:
            notification_locs.append_text(i)
        notification_locs.set_active(self.traytips.notifications_location)
        notification_locs.connect('changed', self.prefs_notiflocation_changed)
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
        crossfadelabel2 = gtk.Label(_("Fade length") + ":")
        crossfadelabel2.set_alignment(1, 0.5)
        crossfadelabel3 = gtk.Label(_("sec"))
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
        as_table.attach(gtk.Label(), 0, 2, 2, 3)
        as_table.attach(display_notification, 0, 2, 3, 4)
        as_table.attach(notifhbox, 0, 2, 4, 5)
        as_table.attach(gtk.Label(), 0, 2, 5, 6)
        as_table.attach(crossfadecheck, 0, 2, 6, 7)
        as_table.attach(crossfadebox, 0, 2, 7, 8)
        as_vbox.pack_start(as_table, False)
        as_frame.add(as_vbox)
        as_checkbox.connect('toggled', self.use_scrobbler_toggled, as_user_entry, as_pass_entry, as_user_label, as_pass_label)
        if not self.use_scrobbler or not HAVE_AUDIOSCROBBLER:
            as_user_entry.set_sensitive(False)
            as_pass_entry.set_sensitive(False)
            as_user_label.set_sensitive(False)
            as_pass_label.set_sensitive(False)
        # Display tab
        table2 = gtk.Table(7, 2, False)
        displaylabel = gtk.Label()
        displaylabel.set_markup('<b>' + _('Display') + '</b>')
        displaylabel.set_alignment(0, 1)
        display_art_hbox = gtk.HBox()
        display_art = gtk.CheckButton(_("Enable album art"))
        display_art.set_active(self.show_covers)
        display_art_combo = gtk.combo_box_new_text()
        display_art_combo.append_text(_("Local only"))
        display_art_combo.append_text(_("Local, then remote"))
        display_art_combo.set_active(self.covers_pref)
        display_art_combo.set_sensitive(self.show_covers)
        orderart_label = gtk.Label(_("Search order:"))
        orderart_label.set_alignment(1, 0.5)
        display_art_hbox.pack_start(orderart_label)
        display_art_hbox.pack_start(display_art_combo, False, False, 5)
        display_art_location_hbox = gtk.HBox()
        saveart_label = gtk.Label(_("Save art to:"))
        saveart_label.set_alignment(1, 0.5)
        display_art_location_hbox.pack_start(saveart_label)
        display_art_location = gtk.combo_box_new_text()
        display_art_location_hbox.pack_start(display_art_location, False, False, 5)
        display_art_location.append_text("~/.covers/")
        display_art_location.append_text("../" + _("file_path") + "/cover.jpg")
        display_art_location.append_text("../" + _("file_path") + "/album.jpg")
        display_art_location.append_text("../" + _("file_path") + "/folder.jpg")
        display_art_location.append_text("../" + _("file_path") + "/" + _("custom"))
        display_art_location.set_active(self.art_location)
        display_art_location.set_sensitive(self.show_covers)
        display_art_location.connect('changed', self.prefs_art_location_changed)
        display_art.connect('toggled', self.prefs_art_toggled, display_art_combo, display_art_location_hbox)
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
        savelyrics_label = gtk.Label(_("Save lyrics to:"))
        savelyrics_label.set_alignment(1, 0.5)
        display_lyrics_location_hbox.pack_start(savelyrics_label)
        display_lyrics_location = gtk.combo_box_new_text()
        display_lyrics_location_hbox.pack_start(display_lyrics_location, False, False, 5)
        display_lyrics_location.append_text("~/.lyrics/")
        display_lyrics_location.append_text("../" + _("file_path") + "/")
        display_lyrics_location.set_active(self.lyrics_location)
        display_lyrics_location.set_sensitive(self.show_covers)
        display_lyrics_location.connect('changed', self.prefs_lyrics_location_changed)
        display_lyrics.connect('toggled', self.prefs_lyrics_toggled, display_lyrics_location_hbox)
        display_trayicon = gtk.CheckButton(_("Enable system tray icon"))
        display_trayicon.set_active(self.show_trayicon)
        if not HAVE_EGG and not HAVE_STATUS_ICON:
            display_trayicon.set_sensitive(False)
        table2.attach(gtk.Label(), 1, 3, 1, 2, gtk.FILL|gtk.EXPAND, gtk.FILL|gtk.EXPAND, 15, 0)
        table2.attach(displaylabel, 1, 3, 2, 3, gtk.FILL|gtk.EXPAND, gtk.FILL|gtk.EXPAND, 15, 0)
        table2.attach(gtk.Label(), 1, 3, 3, 4, gtk.FILL|gtk.EXPAND, gtk.FILL|gtk.EXPAND, 15, 0)
        table2.attach(display_playback, 1, 3, 4, 5, gtk.FILL|gtk.EXPAND, gtk.FILL|gtk.EXPAND, 30, 0)
        table2.attach(display_progress, 1, 3, 5, 6, gtk.FILL|gtk.EXPAND, gtk.FILL|gtk.EXPAND, 30, 0)
        table2.attach(display_statusbar, 1, 3, 6, 7, gtk.FILL|gtk.EXPAND, gtk.FILL|gtk.EXPAND, 30, 0)
        table2.attach(display_trayicon, 1, 3, 7, 8, gtk.FILL|gtk.EXPAND, gtk.FILL|gtk.EXPAND, 30, 0)
        table2.attach(display_lyrics, 1, 3, 8, 9, gtk.FILL|gtk.EXPAND, gtk.FILL|gtk.EXPAND, 30, 0)
        table2.attach(display_lyrics_location_hbox, 1, 3, 9, 10, gtk.FILL|gtk.EXPAND, gtk.FILL|gtk.EXPAND, 30, 0)
        table2.attach(display_art, 1, 3, 10, 11, gtk.FILL|gtk.EXPAND, gtk.FILL|gtk.EXPAND, 30, 0)
        table2.attach(display_art_hbox, 1, 3, 11, 12, gtk.FILL|gtk.EXPAND, gtk.FILL|gtk.EXPAND, 30, 0)
        table2.attach(display_art_location_hbox, 1, 3, 12, 13, gtk.FILL|gtk.EXPAND, gtk.FILL|gtk.EXPAND, 30, 0)
        table2.attach(gtk.Label(), 1, 3, 13, 14, gtk.FILL|gtk.EXPAND, gtk.FILL|gtk.EXPAND, 75, 0)
        table2.attach(gtk.Label(), 1, 3, 14, 15, gtk.FILL|gtk.EXPAND, gtk.FILL|gtk.EXPAND, 75, 0)
        # Behavior tab
        table3 = gtk.Table()
        behaviorlabel = gtk.Label()
        behaviorlabel.set_markup('<b>' + _('Window Behavior') + '</b>')
        behaviorlabel.set_alignment(0, 1)
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
        activate = gtk.CheckButton(_("Play enqueued files on activate"))
        activate.set_active(self.play_on_activate)
        self.tooltips.set_tip(activate, _("Automatically play enqueued items when activated via double-click or enter."))
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
        infopath_options = gtk.Entry()
        infopath_options.set_text(self.infofile_path)
        self.tooltips.set_tip(infopath_options, _("If enabled, Sonata will create a xmms-infopipe like file containing information about the current song. Many applications support the xmms-info file (Instant Messengers, IRC Clients...)"))
        if not self.use_infofile:
            infopath_options.set_sensitive(False)
        infofile_usage.connect('toggled', self.prefs_infofile_toggled, infopath_options)
        infofilebox.pack_start(infofile_usage, False, False, 0)
        infofilebox.pack_start(infopath_options, True, True, 5)
        behaviorlabel2 = gtk.Label()
        behaviorlabel2.set_markup('<b>' + _('Miscellaneous') + '</b>')
        behaviorlabel2.set_alignment(0, 1)
        table3.attach(gtk.Label(), 1, 3, 1, 2, gtk.FILL|gtk.EXPAND, gtk.FILL|gtk.EXPAND, 15, 0)
        table3.attach(behaviorlabel, 1, 3, 2, 3, gtk.FILL|gtk.EXPAND, gtk.FILL|gtk.EXPAND, 15, 0)
        table3.attach(gtk.Label(), 1, 3, 3, 4, gtk.FILL|gtk.EXPAND, gtk.FILL|gtk.EXPAND, 15, 0)
        table3.attach(win_sticky, 1, 3, 4, 5, gtk.FILL|gtk.EXPAND, gtk.FILL|gtk.EXPAND, 30, 0)
        table3.attach(win_ontop, 1, 3, 5, 6, gtk.FILL|gtk.EXPAND, gtk.FILL|gtk.EXPAND, 30, 0)
        table3.attach(minimize, 1, 3, 6, 7, gtk.FILL|gtk.EXPAND, gtk.FILL|gtk.EXPAND, 30, 0)
        table3.attach(gtk.Label(), 1, 3, 7, 8, gtk.FILL|gtk.EXPAND, gtk.FILL|gtk.EXPAND, 15, 0)
        table3.attach(behaviorlabel2, 1, 3, 8, 9, gtk.FILL|gtk.EXPAND, gtk.FILL|gtk.EXPAND, 15, 0)
        table3.attach(gtk.Label(), 1, 3, 9, 10, gtk.FILL|gtk.EXPAND, gtk.FILL|gtk.EXPAND, 15, 0)
        table3.attach(update_start, 1, 3, 10, 11, gtk.FILL|gtk.EXPAND, gtk.FILL|gtk.EXPAND, 30, 0)
        table3.attach(exit_stop, 1, 3, 11, 12, gtk.FILL|gtk.EXPAND, gtk.FILL|gtk.EXPAND, 30, 0)
        table3.attach(infofilebox, 1, 3, 12, 13, gtk.FILL|gtk.EXPAND, gtk.FILL|gtk.EXPAND, 30, 0)
        table3.attach(activate, 1, 3, 13, 14, gtk.FILL|gtk.EXPAND, gtk.FILL|gtk.EXPAND, 30, 0)
        table3.attach(gtk.Label(), 1, 3, 14, 15, gtk.FILL|gtk.EXPAND, gtk.FILL|gtk.EXPAND, 30, 0)
        table3.attach(gtk.Label(), 1, 3, 15, 16, gtk.FILL|gtk.EXPAND, gtk.FILL|gtk.EXPAND, 30, 0)
        # Format tab
        table4 = gtk.Table(9, 2, False)
        table4.set_col_spacings(3)
        formatlabel = gtk.Label()
        formatlabel.set_markup('<b>' + _('Song Formatting') + '</b>')
        formatlabel.set_alignment(0, 1)
        currentformatbox = gtk.HBox()
        currentlabel = gtk.Label(_("Current playlist:"))
        currentoptions = gtk.Entry()
        currentoptions.set_text(self.currentformat)
        currentformatbox.pack_start(currentlabel, False, False, 0)
        currentformatbox.pack_start(currentoptions, False, False, 10)
        libraryformatbox = gtk.HBox()
        librarylabel = gtk.Label(_("Library:"))
        libraryoptions = gtk.Entry()
        libraryoptions.set_text(self.libraryformat)
        libraryformatbox.pack_start(librarylabel, False, False, 0)
        libraryformatbox.pack_start(libraryoptions, False, False, 10)
        titleformatbox = gtk.HBox()
        titlelabel = gtk.Label(_("Window title:"))
        titleoptions = gtk.Entry()
        titleoptions.set_text(self.titleformat)
        titleformatbox.pack_start(titlelabel, False, False, 0)
        titleformatbox.pack_start(titleoptions, False, False, 10)
        currsongformatbox1 = gtk.HBox()
        currsonglabel1 = gtk.Label(_("Current song line 1:"))
        currsongoptions1 = gtk.Entry()
        currsongoptions1.set_text(self.currsongformat1)
        currsongformatbox1.pack_start(currsonglabel1, False, False, 0)
        currsongformatbox1.pack_start(currsongoptions1, False, False, 10)
        currsongformatbox2 = gtk.HBox()
        currsonglabel2 = gtk.Label(_("Current song line 2:"))
        currsongoptions2 = gtk.Entry()
        currsongoptions2.set_text(self.currsongformat2)
        currsongformatbox2.pack_start(currsonglabel2, False, False, 0)
        currsongformatbox2.pack_start(currsongoptions2, False, False, 10)
        formatlabels = [currentlabel, librarylabel, titlelabel, currsonglabel1, currsonglabel2]
        for label in formatlabels:
            label.set_alignment(0, 0.5)
        self.set_label_widths_equal(formatlabels)
        availableheading = gtk.Label()
        availableheading.set_markup('<small>' + _('Available options') + ':</small>')
        availableheading.set_alignment(0, 0)
        availablevbox = gtk.VBox()
        availableformatbox = gtk.HBox()
        availableformatting = gtk.Label()
        availableformatting.set_markup('<small><span font_family="Monospace">%A</span> - ' + _('Artist name') + '\n<span font_family="Monospace">%B</span> - ' + _('Album name') + '\n<span font_family="Monospace">%T</span> - ' + _('Track name') + '\n<span font_family="Monospace">%N</span> - ' + _('Track number') + '\n<span font_family="Monospace">%D</span> - ' + _('Disc Number') + '\n<span font_family="Monospace">%Y</span> - ' + _('Year') + '</small>')
        availableformatting.set_alignment(0, 0)
        availableformatting2 = gtk.Label()
        availableformatting2.set_markup('<small><span font_family="Monospace">%G</span> - ' + _('Genre') + '\n<span font_family="Monospace">%F</span> - ' + _('File name') + '\n<span font_family="Monospace">%S</span> - ' + _('Stream name') + '\n<span font_family="Monospace">%L</span> - ' + _('Song length') + '\n<span font_family="Monospace">%E</span> - ' + _('Elapsed time (title only)') + '</small>')
        availableformatting2.set_alignment(0, 0)
        availableformatbox.pack_start(availableformatting)
        availableformatbox.pack_start(availableformatting2)
        availablevbox.pack_start(availableformatbox, False, False, 0)
        additionalinfo = gtk.Label()
        additionalinfo.set_markup('<small>{ } - ' + _('Info displayed only if all enclosed tags are defined') + '\n' + '| - ' + _('Creates columns in the current playlist') + '</small>')
        additionalinfo.set_alignment(0,0)
        availablevbox.pack_start(additionalinfo, False, False, 4)
        table4.attach(gtk.Label(), 1, 3, 1, 2, gtk.FILL|gtk.EXPAND, gtk.FILL|gtk.EXPAND, 15, 0)
        table4.attach(formatlabel, 1, 3, 2, 3, gtk.FILL|gtk.EXPAND, gtk.FILL|gtk.EXPAND, 15, 0)
        table4.attach(gtk.Label(), 1, 3, 3, 4, gtk.FILL|gtk.EXPAND, gtk.FILL|gtk.EXPAND, 15, 0)
        table4.attach(currentformatbox, 1, 3, 4, 5, gtk.FILL|gtk.EXPAND, gtk.FILL|gtk.EXPAND, 30, 0)
        table4.attach(libraryformatbox, 1, 3, 5, 6, gtk.FILL|gtk.EXPAND, gtk.FILL|gtk.EXPAND, 30, 0)
        table4.attach(titleformatbox, 1, 3, 6, 7, gtk.FILL|gtk.EXPAND, gtk.FILL|gtk.EXPAND, 30, 0)
        table4.attach(currsongformatbox1, 1, 3, 7, 8, gtk.FILL|gtk.EXPAND, gtk.FILL|gtk.EXPAND, 30, 0)
        table4.attach(currsongformatbox2, 1, 3, 8, 9, gtk.FILL|gtk.EXPAND, gtk.FILL|gtk.EXPAND, 30, 0)
        table4.attach(gtk.Label(), 1, 3, 9, 10, gtk.FILL|gtk.EXPAND, gtk.FILL|gtk.EXPAND, 30, 0)
        table4.attach(availableheading, 1, 3, 10, 11, gtk.FILL|gtk.EXPAND, gtk.FILL|gtk.EXPAND, 30, 0)
        table4.attach(availablevbox, 1, 3, 11, 12, gtk.FILL|gtk.EXPAND, gtk.FILL|gtk.EXPAND, 45, 0)
        table4.attach(gtk.Label(), 1, 3, 12, 13, gtk.FILL|gtk.EXPAND, gtk.FILL|gtk.EXPAND, 30, 0)
        table_names = [[_("_MPD"), mpd_table],
                       [_("_Display"), table2],
                       [_("_Behavior"), table3],
                       [_("_Format"), table4],
                       [_("_Extras"), as_frame]]
        for table_name in table_names:
            tmplabel = gtk.Label()
            tmplabel.set_text_with_mnemonic(table_name[0])
            prefsnotebook.append_page(table_name[1], tmplabel)
        hbox.pack_start(prefsnotebook, False, False, 10)
        prefswindow.vbox.pack_start(hbox, False, False, 10)
        close_button = prefswindow.add_button(gtk.STOCK_CLOSE, gtk.RESPONSE_CLOSE)
        prefswindow.show_all()
        close_button.grab_focus()
        prefswindow.connect('response', self.prefs_window_response, prefsnotebook, exit_stop, activate, win_ontop, display_art_combo, win_sticky, direntry, minimize, update_start, autoconnect, currentoptions, libraryoptions, titleoptions, currsongoptions1, currsongoptions2, crossfadecheck, crossfadespin, infopath_options, hostentry, portentry, passwordentry, using_mpd_env_vars)
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
        if HAVE_AUDIOSCROBBLER and self.use_scrobbler and len(self.as_username) > 0 and len(self.as_password) > 0:
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

    def use_scrobbler_toggled(self, checkbox, userentry, passentry, userlabel, passlabel):
        if HAVE_AUDIOSCROBBLER:
            self.use_scrobbler = checkbox.get_active()
            self.scrobbler_init()
            for widget in [userlabel, passlabel, userentry, passentry]:
                widget.set_sensitive(self.use_scrobbler)
        elif checkbox.get_active():
            show_error_msg(self.window, _("Python 2.5 or python-elementtree not found, audioscrobbler support disabled."), _("Audioscrobbler Verification"), 'pythonElementtreeError')
            checkbox.set_active(False)

    def prefs_as_username_changed(self, entry):
        if HAVE_AUDIOSCROBBLER:
            self.as_username = entry.get_text()
            if self.scrob_post:
                if self.scrob_post.authenticated:
                    self.scrob_post = None

    def prefs_as_password_changed(self, entry):
        if HAVE_AUDIOSCROBBLER:
            self.as_password = entry.get_text()
            if self.scrob_post:
                if self.scrob_post.authenticated:
                    self.scrob_post = None

    def prefs_window_response(self, window, response, prefsnotebook, exit_stop, activate, win_ontop, display_art_combo, win_sticky, direntry, minimize, update_start, autoconnect, currentoptions, libraryoptions, titleoptions, currsongoptions1, currsongoptions2, crossfadecheck, crossfadespin, infopath_options, hostentry, portentry, passwordentry, using_mpd_env_vars):
        if response == gtk.RESPONSE_CLOSE:
            self.stop_on_exit = exit_stop.get_active()
            self.play_on_activate = activate.get_active()
            self.ontop = win_ontop.get_active()
            self.covers_pref = display_art_combo.get_active()
            self.sticky = win_sticky.get_active()
            if self.show_lyrics and self.lyrics_location != self.LYRICS_LOCATION_HOME:
                if not os.path.isdir(self.musicdir[self.profile_num]):
                    show_error_msg(self.window, _("To save lyrics to the music file's directory, you must specify a valid music directory."), _("Music Dir Verification"), 'musicdirVerificationError')
                    # Set music_dir entry focused:
                    prefsnotebook.set_current_page(0)
                    direntry.grab_focus()
                    return
            if self.show_covers and self.art_location != self.ART_LOCATION_HOMECOVERS:
                if not os.path.isdir(self.musicdir[self.profile_num]):
                    show_error_msg(self.window, _("To save artwork to the music file's directory, you must specify a valid music directory."), _("Music Dir Verification"), 'musicdirVerificationError')
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
                self.parse_currentformat()
                self.update_playlist()
            if self.libraryformat != libraryoptions.get_text():
                self.libraryformat = libraryoptions.get_text()
                self.browse(root=self.wd)
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
                    self.conn.do.crossfade(self.xfade)
            else:
                self.xfade_enabled = False
                if self.conn:
                    self.conn.do.crossfade(0)
            if self.infofile_path != infopath_options.get_text():
                self.infofile_path = os.path.expanduser(infopath_options.get_text())
                if self.use_infofile: self.update_infofile()
            if not using_mpd_env_vars:
                if self.prev_host != self.host[self.profile_num] or self.prev_port != self.port[self.profile_num] or self.prev_password != self.password[self.profile_num]:
                    # Try to connect if mpd connection info has been updated:
                    self.change_cursor(gtk.gdk.Cursor(gtk.gdk.WATCH))
                    self.connect()
            if self.use_scrobbler:
                gobject.idle_add(self.scrobbler_init)
            self.settings_save()
            self.populate_profiles_for_menu()
            self.change_cursor(None)
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
            self.connectkey_pressed(None)
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
                widget.set_no_show_all(False)
                widget.show_all()
        else:
            self.show_playback = False
            for widget in [self.prevbutton, self.ppbutton, self.stopbutton, self.nextbutton, self.volumebutton]:
                widget.set_no_show_all(True)
                widget.hide()

    def prefs_progress_toggled(self, button):
        if button.get_active():
            self.show_progress = True
            for widget in [self.progressbox, self.trayprogressbar]:
                widget.set_no_show_all(False)
                widget.show_all()
        else:
            self.show_progress = False
            for widget in [self.progressbox, self.trayprogressbar]:
                widget.set_no_show_all(True)
                widget.hide()

    def prefs_art_toggled(self, button, art_combo, art_hbox):
        button_active = button.get_active()
        art_combo.set_sensitive(button_active)
        art_hbox.set_sensitive(button_active)
        if button_active:
            self.traytips.set_size_request(self.notification_width, -1)
            self.set_default_icon_for_art()
            for widget in [self.imageeventbox, self.info_imagebox, self.trayalbumeventbox, self.trayalbumimage2]:
                widget.set_no_show_all(False)
                if widget in [self.trayalbumeventbox, self.trayalbumimage2]:
                    if self.conn and self.status and self.status.state in ['play', 'pause']:
                        widget.show_all()
                else:
                    widget.show_all()
            self.show_covers = True
            self.update_cursong()
            self.update_album_art()
        else:
            self.traytips.set_size_request(self.notification_width-100, -1)
            for widget in [self.imageeventbox, self.info_imagebox, self.trayalbumeventbox, self.trayalbumimage2]:
                widget.set_no_show_all(True)
                widget.hide()
            self.show_covers = False
            self.update_cursong()

    def prefs_lyrics_location_changed(self, combobox):
        self.lyrics_location = combobox.get_active()

    def prefs_art_location_changed(self, combobox):
        if combobox.get_active() == self.ART_LOCATION_CUSTOM:
            self.get_art_location_custom(combobox)
        self.art_location = combobox.get_active()

    def get_art_location_custom(self, combobox):
        # Prompt user for playlist name:
        dialog = gtk.Dialog(_("Custom Artwork"), self.window, gtk.DIALOG_MODAL | gtk.DIALOG_DESTROY_WITH_PARENT, (gtk.STOCK_CANCEL, gtk.RESPONSE_REJECT, gtk.STOCK_OK, gtk.RESPONSE_ACCEPT))
        dialog.set_role('customArtwork')
        hbox = gtk.HBox()
        hbox.pack_start(gtk.Label(_('Artwork filename') + ':'), False, False, 5)
        entry = gtk.Entry()
        entry.set_activates_default(True)
        hbox.pack_start(entry, True, True, 5)
        dialog.vbox.pack_start(hbox)
        dialog.set_default_response(gtk.RESPONSE_ACCEPT)
        dialog.vbox.show_all()
        response = dialog.run()
        if response == gtk.RESPONSE_ACCEPT:
            self.art_location_custom_filename = entry.get_text().replace("/", "")
        else:
            # Revert to non-custom item in combobox:
            combobox.set_active(self.art_location)
        dialog.destroy()

    def prefs_lyrics_toggled(self, button, lyrics_hbox):
        if button.get_active():
            lyrics_hbox.set_sensitive(True)
            self.show_lyrics = True
            self.info_lyrics.set_no_show_all(False)
            self.info_lyrics.show_all()
            self.info_update(True)
        else:
            lyrics_hbox.set_sensitive(False)
            self.show_lyrics = False
            self.info_lyrics.hide_all()
            self.info_lyrics.set_no_show_all(True)

    def prefs_statusbar_toggled(self, button):
        if button.get_active():
            self.statusbar.set_no_show_all(False)
            if self.expanded:
                self.statusbar.show_all()
            self.show_statusbar = True
            self.update_statusbar()
        else:
            self.statusbar.set_no_show_all(True)
            self.statusbar.hide()
            self.show_statusbar = False
            self.update_statusbar()

    def prefs_notif_toggled(self, button, notifhbox):
        if button.get_active():
            notifhbox.set_sensitive(True)
            self.show_notification = True
            self.labelnotify()
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
        self.labelnotify()

    def prefs_notiftime_changed(self, combobox):
        self.popup_option = combobox.get_active()
        self.labelnotify()

    def prefs_infofile_toggled(self, button, infofileformatbox):
        if button.get_active():
            infofileformatbox.set_sensitive(True)
            self.use_infofile = True
            self.update_infofile()
        else:
            infofileformatbox.set_sensitive(False)
            self.use_infofile = False

    def seek(self, song, seektime):
        self.conn.do.seek(song, seektime)
        self.iterate_now()
        return

    def on_link_enter(self, widget, event):
        if widget.get_children()[0].get_use_markup() == True:
            self.change_cursor(gtk.gdk.Cursor(gtk.gdk.HAND2))

    def on_link_leave(self, widget, event):
        self.change_cursor(None)

    def on_link_click(self, widget, event, type):
        if type == 'artist':
            self.browser_load("http://www.wikipedia.org/wiki/Special:Search/" + self.songinfo.artist)
        elif type == 'album':
            self.browser_load("http://www.wikipedia.org/wiki/Special:Search/" + self.songinfo.album)
        elif type == 'more':
            previous_is_more = (self.info_morelabel.get_text() == "(" + _("more") + ")")
            if previous_is_more:
                self.info_morelabel.set_markup(link_markup(_("hide"), True, True, self.linkcolor))
                self.info_song_more = True
            else:
                self.info_morelabel.set_markup(link_markup(_("more"), True, True, self.linkcolor))
                self.info_song_more = False
            if self.info_song_more:
                for hbox in self.info_boxes_in_more:
                    hbox.set_no_show_all(False)
                    hbox.show_all()
            else:
                for hbox in self.info_boxes_in_more:
                    hbox.hide_all()
                    hbox.set_no_show_all(True)
        elif type == 'edit':
            if self.songinfo:
                self.edit_tags(widget)
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
            gobject.idle_add(self.give_widget_focus, self.current)
        elif self.current_tab == self.TAB_LIBRARY:
            gobject.idle_add(self.give_widget_focus, self.browser)
        elif self.current_tab == self.TAB_PLAYLISTS:
            gobject.idle_add(self.give_widget_focus, self.playlists)
        elif self.current_tab == self.TAB_STREAMS:
            gobject.idle_add(self.give_widget_focus, self.streams)
        elif self.current_tab == self.TAB_INFO:
            gobject.idle_add(self.info_update, True)
        gobject.idle_add(self.set_menu_contextual_items_visible)

    def on_searchtext_click(self, widget, event):
        if event.button == 1:
            self.volume_hide()

    def on_window_click(self, widget, event):
        if event.button == 1:
            self.volume_hide()
        elif event.button == 3:
            self.popup_menu(self.window, event)

    def popup_menu(self, widget, event):
        if widget == self.window:
            if event.get_coords()[1] > self.notebook.get_allocation()[1]:
                return
        if event.button == 3:
            self.set_menu_contextual_items_visible(True)
            gobject.idle_add(self.mainmenu.popup, None, None, None, event.button, event.time)

    def tab_toggle(self, toggleAction):
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
            self.notebook.get_children()[tabnum].set_no_show_all(False)
            self.notebook.get_children()[tabnum].show_all()
        else:
            self.notebook.get_children()[tabnum].hide_all()
            self.notebook.get_children()[tabnum].set_no_show_all(True)

    def searchkey_pressed(self, event):
        # Ensure library tab is visible
        if not self.notebook_tab_is_visible(self.notebook, self.TAB_LIBRARY):
            return
        if self.current_tab != self.TAB_LIBRARY:
            self.switch_to_tab_name(self.TAB_LIBRARY)
        if self.searchbutton.get_property('visible'):
            self.on_search_end(None)
        gobject.idle_add(self.searchtext.grab_focus)

    def on_search_combo_change(self, combo):
        if self.searchbutton.get_property('visible'):
            self.on_search_end(None)
        self.last_search_num = combo.get_active()

    def on_search_activate(self, entry):
        searchby = self.search_terms_mpd[self.last_search_num]
        if self.searchtext.get_text() != "":
            list = self.conn.do.search(searchby, self.searchtext.get_text())
            self.browserdata.clear()
            bd = []
            for item in list:
                if item.type == 'directory':
                    name = item.directory.split('/')[-1]
                    # sorting shouldn't really matter here. Ever seen a search turn up a directory?
                    bd += [('d' + item.directory.lower(), [gtk.STOCK_OPEN, item.directory, escape_html(name)])]
                elif item.type == 'file':
                    try:
                        bd += [('f' + lower_no_the(item.artist) + '\t' + item.title.lower(), ['sonata', item.file, self.parse_formatting(self.libraryformat, item, True)])]
                    except:
                        bd += [('f' + item.file.lower(), ['sonata', item.file, self.parse_formatting(self.libraryformat, item, True)])]
            bd.sort(key=first_of_2tuple)
            for sort, list in bd:
                self.browserdata.append(list)

            self.browser.grab_focus()
            self.browser.scroll_to_point(0, 0)
            self.searchbutton.show()
            self.searchbutton.set_no_show_all(False)
        else:
            self.on_search_end(None)

    def on_search_end(self, button):
        self.searchbutton.hide()
        self.searchbutton.set_no_show_all(True)
        self.searchtext.set_text("")
        self.browse(root=self.wd)
        self.browser.grab_focus()

    def search_mode_enabled(self):
        if self.searchbutton.get_property('visible'):
            return True
        else:
            return False

    def set_menu_contextual_items_visible(self, show_songinfo_only=False):
        if show_songinfo_only or not self.expanded:
            self.UIManager.get_widget('/mainmenu/addmenu/').hide()
            self.UIManager.get_widget('/mainmenu/replacemenu/').hide()
            self.UIManager.get_widget('/mainmenu/renamemenu/').hide()
            self.UIManager.get_widget('/mainmenu/rmmenu/').hide()
            self.UIManager.get_widget('/mainmenu/removemenu/').hide()
            self.UIManager.get_widget('/mainmenu/clearmenu/').hide()
            self.UIManager.get_widget('/mainmenu/playlistmenu/').hide()
            self.UIManager.get_widget('/mainmenu/updatemenu/').hide()
            self.UIManager.get_widget('/mainmenu/newmenu/').hide()
            self.UIManager.get_widget('/mainmenu/editmenu/').hide()
            self.UIManager.get_widget('/mainmenu/sortmenu/').hide()
            self.UIManager.get_widget('/mainmenu/edittagmenu/').hide()
            return
        elif self.current_tab == self.TAB_CURRENT:
            if len(self.currentdata) > 0:
                if self.current_selection.count_selected_rows() > 0:
                    self.UIManager.get_widget('/mainmenu/removemenu/').show()
                    self.UIManager.get_widget('/mainmenu/edittagmenu/').show()
                else:
                    self.UIManager.get_widget('/mainmenu/removemenu/').hide()
                    self.UIManager.get_widget('/mainmenu/edittagmenu/').hide()
                if not self.filterbox_visible:
                    self.UIManager.get_widget('/mainmenu/clearmenu/').show()
                    self.UIManager.get_widget('/mainmenu/playlistmenu/').show()
                    self.UIManager.get_widget('/mainmenu/sortmenu/').show()
                else:
                    self.UIManager.get_widget('/mainmenu/clearmenu/').hide()
                    self.UIManager.get_widget('/mainmenu/playlistmenu/').hide()
                    self.UIManager.get_widget('/mainmenu/sortmenu/').hide()
            else:
                self.UIManager.get_widget('/mainmenu/clearmenu/').hide()
                self.UIManager.get_widget('/mainmenu/playlistmenu/').hide()
                self.UIManager.get_widget('/mainmenu/sortmenu/').hide()
                self.UIManager.get_widget('/mainmenu/removemenu/').hide()
                self.UIManager.get_widget('/mainmenu/edittagmenu/').hide()
            self.UIManager.get_widget('/mainmenu/addmenu/').hide()
            self.UIManager.get_widget('/mainmenu/replacemenu/').hide()
            self.UIManager.get_widget('/mainmenu/renamemenu/').hide()
            self.UIManager.get_widget('/mainmenu/rmmenu/').hide()
            self.UIManager.get_widget('/mainmenu/updatemenu/').hide()
            self.UIManager.get_widget('/mainmenu/newmenu/').hide()
            self.UIManager.get_widget('/mainmenu/editmenu/').hide()
        elif self.current_tab == self.TAB_LIBRARY:
            self.UIManager.get_widget('/mainmenu/updatemenu/').show()
            if len(self.browserdata) > 0:
                if self.browser_selection.count_selected_rows() > 0:
                    self.UIManager.get_widget('/mainmenu/addmenu/').show()
                    self.UIManager.get_widget('/mainmenu/replacemenu/').show()
                    self.UIManager.get_widget('/mainmenu/edittagmenu/').show()
                else:
                    self.UIManager.get_widget('/mainmenu/addmenu/').hide()
                    self.UIManager.get_widget('/mainmenu/replacemenu/').hide()
                    self.UIManager.get_widget('/mainmenu/edittagmenu/').hide()
            else:
                self.UIManager.get_widget('/mainmenu/addmenu/').hide()
                self.UIManager.get_widget('/mainmenu/replacemenu/').hide()
                self.UIManager.get_widget('/mainmenu/edittagmenu/').hide()
            self.UIManager.get_widget('/mainmenu/removemenu/').hide()
            self.UIManager.get_widget('/mainmenu/clearmenu/').hide()
            self.UIManager.get_widget('/mainmenu/playlistmenu/').hide()
            self.UIManager.get_widget('/mainmenu/renamemenu/').hide()
            self.UIManager.get_widget('/mainmenu/rmmenu/').hide()
            self.UIManager.get_widget('/mainmenu/newmenu/').hide()
            self.UIManager.get_widget('/mainmenu/editmenu/').hide()
            self.UIManager.get_widget('/mainmenu/sortmenu/').hide()
        elif self.current_tab == self.TAB_PLAYLISTS:
            if self.playlists_selection.count_selected_rows() > 0:
                self.UIManager.get_widget('/mainmenu/addmenu/').show()
                self.UIManager.get_widget('/mainmenu/replacemenu/').show()
                self.UIManager.get_widget('/mainmenu/rmmenu/').show()
                if self.playlists_selection.count_selected_rows() == 1 and self.mpd_major_version() >= 0.13:
                    self.UIManager.get_widget('/mainmenu/renamemenu/').show()
                else:
                    self.UIManager.get_widget('/mainmenu/renamemenu/').hide()
            else:
                self.UIManager.get_widget('/mainmenu/addmenu/').hide()
                self.UIManager.get_widget('/mainmenu/replacemenu/').hide()
                self.UIManager.get_widget('/mainmenu/rmmenu/').hide()
                self.UIManager.get_widget('/mainmenu/renamemenu/').hide()
            self.UIManager.get_widget('/mainmenu/removemenu/').hide()
            self.UIManager.get_widget('/mainmenu/clearmenu/').hide()
            self.UIManager.get_widget('/mainmenu/playlistmenu/').hide()
            self.UIManager.get_widget('/mainmenu/updatemenu/').hide()
            self.UIManager.get_widget('/mainmenu/newmenu/').hide()
            self.UIManager.get_widget('/mainmenu/editmenu/').hide()
            self.UIManager.get_widget('/mainmenu/sortmenu/').hide()
            self.UIManager.get_widget('/mainmenu/edittagmenu/').hide()
        elif self.current_tab == self.TAB_STREAMS:
            self.UIManager.get_widget('/mainmenu/newmenu/').show()
            if self.streams_selection.count_selected_rows() > 0:
                if self.streams_selection.count_selected_rows() == 1:
                    self.UIManager.get_widget('/mainmenu/editmenu/').show()
                else:
                    self.UIManager.get_widget('/mainmenu/editmenu/').hide()
                self.UIManager.get_widget('/mainmenu/addmenu/').show()
                self.UIManager.get_widget('/mainmenu/replacemenu/').show()
                self.UIManager.get_widget('/mainmenu/rmmenu/').show()
            else:
                self.UIManager.get_widget('/mainmenu/addmenu/').hide()
                self.UIManager.get_widget('/mainmenu/editmenu/').hide()
                self.UIManager.get_widget('/mainmenu/replacemenu/').hide()
                self.UIManager.get_widget('/mainmenu/rmmenu/').hide()
            self.UIManager.get_widget('/mainmenu/renamemenu/').hide()
            self.UIManager.get_widget('/mainmenu/removemenu/').hide()
            self.UIManager.get_widget('/mainmenu/clearmenu/').hide()
            self.UIManager.get_widget('/mainmenu/playlistmenu/').hide()
            self.UIManager.get_widget('/mainmenu/updatemenu/').hide()
            self.UIManager.get_widget('/mainmenu/sortmenu/').hide()
            self.UIManager.get_widget('/mainmenu/edittagmenu/').hide()

    def mpd_major_version(self):
        try:
            if self.conn:
                version = getattr(self.conn, "mpd_version", 0.0)
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
            if os.path.exists(os.path.join(sys.prefix, 'share', 'pixmaps', filename)):
                full_filename = os.path.join(sys.prefix, 'share', 'pixmaps', filename)
            elif os.path.exists(os.path.join(os.path.split(__file__)[0], filename)):
                full_filename = os.path.join(os.path.split(__file__)[0], filename)
            elif os.path.exists(os.path.join(os.path.split(__file__)[0], 'pixmaps', filename)):
                full_filename = os.path.join(os.path.split(__file__)[0], 'pixmaps', filename)
            elif os.path.exists(os.path.join(os.path.split(__file__)[0], 'share', filename)):
                full_filename = os.path.join(os.path.split(__file__)[0], 'share', filename)
            elif os.path.exists(os.path.join(__file__.split('/lib')[0], 'share', 'pixmaps', filename)):
                full_filename = os.path.join(__file__.split('/lib')[0], 'share', 'pixmaps', filename)
        if not full_filename:
            print filename + " cannot be found. Aborting..."
            sys.exit()
        return full_filename

    def edit_tags(self, widget):
        if not HAVE_TAGPY:
            error_dialog = gtk.MessageDialog(self.window, gtk.DIALOG_MODAL, gtk.MESSAGE_WARNING, gtk.BUTTONS_CLOSE, _("Taglib and/or tagpy not found, tag editing support disabled."))
            error_dialog.set_title(_("Edit Tags"))
            error_dialog.set_role('editTagsError')
            error_dialog.connect('response', self.choose_image_dialog_response)
            error_dialog.show()
            return
        if not os.path.isdir(self.musicdir[self.profile_num]):
            error_dialog = gtk.MessageDialog(self.window, gtk.DIALOG_MODAL, gtk.MESSAGE_WARNING, gtk.BUTTONS_CLOSE, _("The path") + " " + self.musicdir[self.profile_num] + " " + _("does not exist. Please specify a valid music directory in preferences."))
            error_dialog.set_title(_("Edit Tags"))
            error_dialog.set_role('editTagsError')
            error_dialog.connect('response', self.choose_image_dialog_response)
            error_dialog.show()
            return
        self.change_cursor(gtk.gdk.Cursor(gtk.gdk.WATCH))
        self.edit_style_orig = self.searchtext.get_style()
        while gtk.events_pending():
            gtk.main_iteration()
        files = []
        temp_mpdpaths = []
        if self.current_tab == self.TAB_INFO:
            if self.status and self.status.state in ['play', 'pause']:
                # Use current file in songinfo:
                mpdpath = self.songinfo.file
                files.append(self.musicdir[self.profile_num] + mpdpath)
                temp_mpdpaths.append(mpdpath)
        elif self.current_tab == self.TAB_LIBRARY:
            # Populates files array with selected library items:
            items = self.browser_get_selected_items_recursive(False)
            for item in items:
                files.append(self.musicdir[self.profile_num] + item)
                temp_mpdpaths.append(item)
        elif self.current_tab == self.TAB_CURRENT:
            # Populates files array with selected current playlist items:
            model, selected = self.current_selection.get_selected_rows()
            for path in selected:
                if not self.filterbox_visible:
                    item = self.songs[path[0]].file
                else:
                    item = self.songs[self.filter_row_mapping[path[0]]].file
                files.append(self.musicdir[self.profile_num] + item)
                temp_mpdpaths.append(item)
        if len(files) == 0:
            self.change_cursor(None)
            return
        # Initialize tags:
        tags = []
        for filenum in range(len(files)):
            tags.append({'title':'', 'artist':'', 'album':'', 'year':'', 'track':'', 'genre':'', 'comment':'', 'title-changed':False, 'artist-changed':False, 'album-changed':False, 'year-changed':False, 'track-changed':False, 'genre-changed':False, 'comment-changed':False, 'fullpath':files[filenum], 'mpdpath':temp_mpdpaths[filenum]})
        self.tagnum = -1
        if not os.path.exists(tags[0]['fullpath']):
            self.change_cursor(None)
            error_dialog = gtk.MessageDialog(self.window, gtk.DIALOG_MODAL, gtk.MESSAGE_WARNING, gtk.BUTTONS_CLOSE, _("File ") + "\"" + tags[0]['fullpath'] + "\"" + _(" not found. Please specify a valid music directory in preferences."))
            error_dialog.set_title(_("Edit Tags"))
            error_dialog.set_role('editTagsError')
            error_dialog.connect('response', self.choose_image_dialog_response)
            error_dialog.show()
            return
        if self.edit_next_tag(tags) == False:
            self.change_cursor(None)
            error_dialog = gtk.MessageDialog(self.window, gtk.DIALOG_MODAL, gtk.MESSAGE_WARNING, gtk.BUTTONS_CLOSE, _("No music files with editable tags found."))
            error_dialog.set_title(_("Edit Tags"))
            error_dialog.set_role('editTagsError')
            error_dialog.connect('response', self.choose_image_dialog_response)
            error_dialog.show()
            return
        editwindow = gtk.Dialog("", self.window, gtk.DIALOG_MODAL)
        editwindow.set_role('editTags')
        editwindow.set_size_request(375, -1)
        editwindow.set_resizable(False)
        editwindow.set_has_separator(False)
        table = gtk.Table(9, 2, False)
        table.set_row_spacings(2)
        filelabel = gtk.Label()
        filelabel.set_selectable(True)
        filelabel.set_line_wrap(True)
        filelabel.set_alignment(0, 0.5)
        filehbox = gtk.HBox()
        sonataicon = gtk.image_new_from_stock('sonata', gtk.ICON_SIZE_DND)
        sonataicon.set_alignment(1, 0.5)
        blanklabel = gtk.Label()
        blanklabel.set_size_request(15, 12)
        filehbox.pack_start(sonataicon, False, False, 2)
        filehbox.pack_start(filelabel, True, True, 2)
        filehbox.pack_start(blanklabel, False, False, 2)
        titlelabel = gtk.Label(_("Title") + ":")
        titlelabel.set_alignment(1, 0.5)
        titleentry = gtk.Entry()
        titlebutton = gtk.Button()
        titlebuttonvbox = gtk.VBox()
        self.editwindow_create_applyall_button(titlebutton, titlebuttonvbox, titleentry)
        titlehbox = gtk.HBox()
        titlehbox.pack_start(titlelabel, False, False, 2)
        titlehbox.pack_start(titleentry, True, True, 2)
        titlehbox.pack_start(titlebuttonvbox, False, False, 2)
        artistlabel = gtk.Label(_("Artist") + ":")
        artistlabel.set_alignment(1, 0.5)
        artistentry = gtk.Entry()
        artisthbox = gtk.HBox()
        artistbutton = gtk.Button()
        artistbuttonvbox = gtk.VBox()
        self.editwindow_create_applyall_button(artistbutton, artistbuttonvbox, artistentry)
        artisthbox.pack_start(artistlabel, False, False, 2)
        artisthbox.pack_start(artistentry, True, True, 2)
        artisthbox.pack_start(artistbuttonvbox, False, False, 2)
        albumlabel = gtk.Label(_("Album") + ":")
        albumlabel.set_alignment(1, 0.5)
        albumentry = gtk.Entry()
        albumhbox = gtk.HBox()
        albumbutton = gtk.Button()
        albumbuttonvbox = gtk.VBox()
        self.editwindow_create_applyall_button(albumbutton, albumbuttonvbox, albumentry)
        albumhbox.pack_start(albumlabel, False, False, 2)
        albumhbox.pack_start(albumentry, True, True, 2)
        albumhbox.pack_start(albumbuttonvbox, False, False, 2)
        yearlabel = gtk.Label("  " + _("Year") + ":")
        yearlabel.set_alignment(1, 0.5)
        yearentry = gtk.Entry()
        yearentry.set_size_request(50, -1)
        handlerid = yearentry.connect("insert_text", self.entry_float, True)
        yearentry.set_data('handlerid', handlerid)
        tracklabel = gtk.Label("  " + _("Track") + ":")
        tracklabel.set_alignment(1, 0.5)
        trackentry = gtk.Entry()
        trackentry.set_size_request(50, -1)
        handlerid2 = trackentry.connect("insert_text", self.entry_float, False)
        trackentry.set_data('handlerid2', handlerid2)
        yearbutton = gtk.Button()
        yearbuttonvbox = gtk.VBox()
        self.editwindow_create_applyall_button(yearbutton, yearbuttonvbox, yearentry)
        trackbutton = gtk.Button()
        trackbuttonvbox = gtk.VBox()
        self.editwindow_create_applyall_button(trackbutton, trackbuttonvbox, trackentry, True)
        yearandtrackhbox = gtk.HBox()
        yearandtrackhbox.pack_start(yearlabel, False, False, 2)
        yearandtrackhbox.pack_start(yearentry, True, True, 2)
        yearandtrackhbox.pack_start(yearbuttonvbox, False, False, 2)
        yearandtrackhbox.pack_start(tracklabel, False, False, 2)
        yearandtrackhbox.pack_start(trackentry, True, True, 2)
        yearandtrackhbox.pack_start(trackbuttonvbox, False, False, 2)
        genrelabel = gtk.Label(_("Genre") + ":")
        genrelabel.set_alignment(1, 0.5)
        genrecombo = gtk.combo_box_entry_new_text()
        genrecombo.set_wrap_width(2)
        self.editwindow_populate_genre_combo(genrecombo)
        genreentry = genrecombo.get_child()
        genrehbox = gtk.HBox()
        genrebutton = gtk.Button()
        genrebuttonvbox = gtk.VBox()
        self.editwindow_create_applyall_button(genrebutton, genrebuttonvbox, genreentry)
        genrehbox.pack_start(genrelabel, False, False, 2)
        genrehbox.pack_start(genrecombo, True, True, 2)
        genrehbox.pack_start(genrebuttonvbox, False, False, 2)
        commentlabel = gtk.Label(_("Comment") + ":")
        commentlabel.set_alignment(1, 0.5)
        commententry = gtk.Entry()
        commenthbox = gtk.HBox()
        commentbutton = gtk.Button()
        commentbuttonvbox = gtk.VBox()
        self.editwindow_create_applyall_button(commentbutton, commentbuttonvbox, commententry)
        commenthbox.pack_start(commentlabel, False, False, 2)
        commenthbox.pack_start(commententry, True, True, 2)
        commenthbox.pack_start(commentbuttonvbox, False, False, 2)
        self.set_label_widths_equal([titlelabel, artistlabel, albumlabel, yearlabel, genrelabel, commentlabel, sonataicon])
        genrecombo.set_size_request(-1, titleentry.size_request()[1])
        table.attach(gtk.Label(), 1, 2, 1, 2, gtk.FILL|gtk.EXPAND, gtk.FILL|gtk.EXPAND, 2, 0)
        table.attach(filehbox, 1, 2, 2, 3, gtk.FILL|gtk.EXPAND, gtk.FILL|gtk.EXPAND, 2, 0)
        table.attach(gtk.Label(), 1, 2, 3, 4, gtk.FILL|gtk.EXPAND, gtk.FILL|gtk.EXPAND, 2, 0)
        table.attach(titlehbox, 1, 2, 4, 5, gtk.FILL|gtk.EXPAND, gtk.FILL|gtk.EXPAND, 2, 0)
        table.attach(artisthbox, 1, 2, 5, 6, gtk.FILL|gtk.EXPAND, gtk.FILL|gtk.EXPAND, 2, 0)
        table.attach(albumhbox, 1, 2, 6, 7, gtk.FILL|gtk.EXPAND, gtk.FILL|gtk.EXPAND, 2, 0)
        table.attach(yearandtrackhbox, 1, 2, 7, 8, gtk.FILL|gtk.EXPAND, gtk.FILL|gtk.EXPAND, 2, 0)
        table.attach(genrehbox, 1, 2, 8, 9, gtk.FILL|gtk.EXPAND, gtk.FILL|gtk.EXPAND, 2, 0)
        table.attach(commenthbox, 1, 2, 9, 10, gtk.FILL|gtk.EXPAND, gtk.FILL|gtk.EXPAND, 2, 0)
        table.attach(gtk.Label(), 1, 2, 10, 11, gtk.FILL|gtk.EXPAND, gtk.FILL|gtk.EXPAND, 2, 0)
        editwindow.vbox.pack_start(table)
        saveall_button = None
        if len(files) > 1:
            # Only show save all button if more than one song being edited.
            saveall_button = gtk.Button(_("Save _All"))
            editwindow.action_area.pack_start(saveall_button)
        cancelbutton = editwindow.add_button(gtk.STOCK_CANCEL, gtk.RESPONSE_REJECT)
        savebutton = editwindow.add_button(gtk.STOCK_SAVE, gtk.RESPONSE_ACCEPT)
        editwindow.connect('delete_event', self.editwindow_hide, tags)
        entries = [titleentry, artistentry, albumentry, yearentry, trackentry, genreentry, commententry, filelabel]
        buttons = [titlebutton, artistbutton, albumbutton, yearbutton, trackbutton, genrebutton, commentbutton]
        entries_names = ["title", "artist", "album", "year", "track", "genre", "comment"]
        editwindow.connect('response', self.editwindow_response, tags, entries, entries_names)
        if saveall_button:
            saveall_button.connect('clicked', self.editwindow_save_all, editwindow, tags, entries, entries_names)
        for i in range(len(entries)-1):
            entries[i].connect('changed', self.edit_entry_changed)
        for i in range(len(buttons)):
            buttons[i].connect('clicked', self.editwindow_applyall, entries_names[i], tags, entries)
        self.editwindow_update(editwindow, tags, entries, entries_names)
        self.change_cursor(None)
        entries[7].set_size_request(editwindow.size_request()[0] - titlelabel.size_request()[0] - 50, -1)
        editwindow.show_all()

    def edit_next_tag(self, tags):
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

    def edit_entry_changed(self, editable, force_red=False):
        if force_red or not self.updating_edit_entries:
            style = editable.get_style().copy()
            style.text[gtk.STATE_NORMAL] = editable.get_colormap().alloc_color("red")
            editable.set_style(style)

    def edit_entry_revert_color(self, editable):
        editable.set_style(self.edit_style_orig)

    def editwindow_create_applyall_button(self, button, vbox, entry, autotrack=False):
        button.set_size_request(12, 12)
        if autotrack:
            self.tooltips.set_tip(button, _("Increment each selected music file, starting at track 1 for this file."))
        else:
            self.tooltips.set_tip(button, _("Apply to all selected music files."))
        padding = int((entry.size_request()[1] - button.size_request()[1])/2)+1
        vbox.pack_start(button, False, False, padding)

    def editwindow_applyall(self, button, item, tags, entries):
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

    def editwindow_update(self, window, tags, entries, entries_names):
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
        entries[0].set_text(self.tagpy_get_tag(tags[self.tagnum], 'title'))
        entries[1].set_text(self.tagpy_get_tag(tags[self.tagnum], 'artist'))
        entries[2].set_text(self.tagpy_get_tag(tags[self.tagnum], 'album'))
        if self.tagpy_get_tag(tags[self.tagnum], 'year') != 0:
            entries[3].set_text(str(self.tagpy_get_tag(tags[self.tagnum], 'year')))
        else:
            entries[3].set_text('')
        if self.tagpy_get_tag(tags[self.tagnum], 'track') != 0:
            entries[4].set_text(str(self.tagpy_get_tag(tags[self.tagnum], 'track')))
        else:
            entries[4].set_text('')
        entries[5].set_text(self.tagpy_get_tag(tags[self.tagnum], 'genre'))
        entries[6].set_text(self.tagpy_get_tag(tags[self.tagnum], 'comment'))
        entries[7].set_text(tags[self.tagnum]['mpdpath'].split('/')[-1])
        entries[0].select_region(0, len(entries[0].get_text()))
        entries[0].grab_focus()
        window.set_title(_("Edit Tags") + " - " + str(self.tagnum+1) + " " + _("of") + " " + str(len(tags)))
        self.updating_edit_entries = False
        # Update text colors as appropriate:
        for i in range(len(entries)-1):
            if tags[self.tagnum][entries_names[i] + '-changed']:
                self.edit_entry_changed(entries[i])
            else:
                self.edit_entry_revert_color(entries[i])
        self.edit_set_action_area_sensitive(window.action_area)

    def edit_set_action_area_sensitive(self, action_area):
        # Hacky workaround to allow the user to click the save button again when the
        # mouse stays over the button (see http://bugzilla.gnome.org/show_bug.cgi?id=56070)
        action_area.set_sensitive(True)
        action_area.hide()
        action_area.show_all()

    def tagpy_get_tag(self, tag, field):
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

    def tagpy_set_tag(self, tag, field, value):
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

    def editwindow_save_all(self, button, window, tags, entries, entries_names):
        for entry in entries:
            try: # Skip GtkLabels
                entry.set_property('editable', False)
            except:
                pass
        while window.get_property('visible'):
            self.editwindow_response(window, gtk.RESPONSE_ACCEPT, tags, entries, entries_names)

    def editwindow_response(self, window, response, tags, entries, entries_names):
        if response == gtk.RESPONSE_REJECT:
            self.editwindow_hide(window, None, tags)
        elif response == gtk.RESPONSE_ACCEPT:
            window.action_area.set_sensitive(False)
            while window.action_area.get_property("sensitive") == True or gtk.events_pending():
                gtk.main_iteration()
            filetag = tagpy.FileRef(tags[self.tagnum]['fullpath'])
            self.tagpy_set_tag(filetag.tag(), 'title', entries[0].get_text())
            self.tagpy_set_tag(filetag.tag(), 'artist', entries[1].get_text())
            self.tagpy_set_tag(filetag.tag(), 'album', entries[2].get_text())
            if len(entries[3].get_text()) > 0:
                self.tagpy_set_tag(filetag.tag(), 'year', entries[3].get_text())
            else:
                self.tagpy_set_tag(filetag.tag(), 'year', 0)
            if len(entries[4].get_text()) > 0:
                self.tagpy_set_tag(filetag.tag(), 'track', entries[4].get_text())
            else:
                self.tagpy_set_tag(filetag.tag(), 'track', 0)
            self.tagpy_set_tag(filetag.tag(), 'genre', entries[5].get_text())
            self.tagpy_set_tag(filetag.tag(), 'comment', entries[6].get_text())
            save_success = filetag.save()
            if not (save_success and self.conn and self.status):
                error_dialog = gtk.MessageDialog(self.window, gtk.DIALOG_MODAL, gtk.MESSAGE_WARNING, gtk.BUTTONS_CLOSE, _("Unable to save tag to music file."))
                error_dialog.set_title(_("Edit Tags"))
                error_dialog.set_role('editTagsError')
                error_dialog.connect('response', self.choose_image_dialog_response)
                error_dialog.show()
            if self.edit_next_tag(tags):
                # Next file:
                self.editwindow_update(window, tags, entries, entries_names)
            else:
                # No more (valid) files:
                self.tagnum = self.tagnum + 1 # To ensure we update the last file in editwindow_mpd_update
                self.editwindow_hide(window, None, tags)

    def editwindow_hide(self, window, data=None, tags=None):
        gobject.idle_add(self.editwindow_mpd_update, tags)
        window.destroy()

    def editwindow_mpd_update(self, tags):
        if tags:
            self.conn.send.command_list_begin()
            for i in range(self.tagnum):
                self.conn.send.update(tags[i]['mpdpath'])
            self.conn.do.command_list_end()
            self.iterate_now()

    def editwindow_populate_genre_combo(self, genrecombo):
        genres = ["", "A Cappella", "Acid", "Acid Jazz", "Acid Punk", "Acoustic",
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
        for genre in genres:
            genrecombo.append_text(genre)

    def set_label_widths_equal(self, labels):
        max_label_width = 0
        for label in labels:
            if label.size_request()[0] > max_label_width: max_label_width = label.size_request()[0]
        for label in labels:
            label.set_size_request(max_label_width, -1)

    def entry_float(self, entry, new_text, new_text_length, position, isyearlabel):
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

    def create_dir_if_not_existing(self, dir):
        if os.path.exists(os.path.expanduser(dir)) == False:
            os.mkdir(os.path.expanduser(dir))

    def about(self, action):
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
            stats = self.conn.do.stats()
            statslabel = stats.songs + ' ' + gettext.ngettext('song', 'songs', int(stats.songs)) + '.\n'
            statslabel = statslabel + stats.albums + ' ' + gettext.ngettext('album', 'albums', int(stats.albums)) + '.\n'
            statslabel = statslabel + stats.artists + ' ' + gettext.ngettext('artist', 'artists', int(stats.artists)) + '.\n'
            try:
                hours_of_playtime = convert_time(float(stats.db_playtime)).split(':')[-3]
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
        self.about_dialog.set_translator_credits('be@latin - Ihar Hrachyshka <ihar.hrachyshka@gmail.com>\ncs - Jakub Adler <jakubadler@gmail.com>\nda - Martin Dybdal <dybber@dybber.dk>\nde - Paul Johnson <thrillerator@googlemail.com>\nes - Xoan Sampaiño <xoansampainho@gmail.com>\nfi - Ilkka Tuohelafr <hile@hack.fi>\nfr - Floreal M <florealm@gmail.com>\nit - Gianni Vialetto <forgottencrow@gmail.com>\nnl - Olivier Keun <litemotiv@gmail.com>\npl - Tomasz Dominikowski <dominikowski@gmail.com>\npt_BR - Alex Tercete Matos <alextercete@gmail.com>\nru - Ivan <bkb.box@bk.ru>\nsv - Daniel Nylander <po@danielnylander.se>\nuk - Господарисько Тарас <dogmaton@gmail.com>\nzh_CN - Desmond Chang <dochang@gmail.com>\n')
        gtk.about_dialog_set_url_hook(self.show_website, "http://sonata.berlios.de/")
        self.about_dialog.set_website_label("http://sonata.berlios.de/")
        large_icon = gtk.gdk.pixbuf_new_from_file(self.find_path('sonata_large.png'))
        self.about_dialog.set_logo(large_icon)
        # Add button to show keybindings:
        shortcut_button = gtk.Button(_("_Shortcuts"))
        self.about_dialog.action_area.pack_start(shortcut_button)
        self.about_dialog.action_area.reorder_child(self.about_dialog.action_area.get_children()[-1], -2)
        # Connect to callbacks
        self.about_dialog.connect('response', self.about_close)
        self.about_dialog.connect('delete_event', self.about_close)
        shortcut_button.connect('clicked', self.about_shortcuts)
        self.about_dialog.show_all()

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
                 [ "Ctrl-D", _("Add selected song(s) or directory(s)") ],
                 [ "Ctrl-R", _("Replace with selected song(s) or directory(s)") ],
                 [ "Ctrl-T", _("Edit selected song's tags") ],
                 [ "Ctrl-Shift-U", _("Update library for selected path(s)") ]]
        playlistshortcuts = \
                [[ "Enter/Space", _("Add selected playlist(s)") ],
                 [ "Delete", _("Remove selected playlist(s)") ],
                 [ "Ctrl-D", _("Add selected playlist(s)") ],
                 [ "Ctrl-R", _("Replace with selected playlist(s)") ]]
        streamshortcuts = \
                [[ "Enter/Space", _("Add selected stream(s)") ],
                 [ "Delete", _("Remove selected stream(s)") ],
                 [ "Ctrl-D", _("Add selected stream(s)") ],
                 [ "Ctrl-R", _("Replace with selected stream(s)") ]]
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
        dialog = gtk.Dialog(_("Shortcuts"), self.about_dialog, gtk.DIALOG_MODAL | gtk.DIALOG_DESTROY_WITH_PARENT, (gtk.STOCK_CLOSE, gtk.RESPONSE_CLOSE))
        dialog.set_role('shortcuts')
        dialog.set_default_response(gtk.RESPONSE_CLOSE)
        dialog.set_size_request(-1, 320)
        scrollbox = gtk.ScrolledWindow()
        scrollbox.set_policy(gtk.POLICY_NEVER, gtk.POLICY_AUTOMATIC)
        dialog.vbox.pack_start(scrollbox, True, True, 2)

        # each pair is a [ heading, shortcutlist ]
        vbox = gtk.VBox()
        for pair in shortcuts:
            titlelabel = gtk.Label()
            titlelabel.set_markup("<b>" + pair[0] + "</b>")
            vbox.pack_start(titlelabel, False, False, 2)

            # print the items of [ shortcut, desc ]
            for item in pair[1]:
                tmphbox = gtk.HBox()

                tmplabel = gtk.Label()
                tmplabel.set_markup("<b>" + item[0] + ":</b>")
                tmplabel.set_alignment(0, 0)

                tmpdesc = gtk.Label(item[1])
                tmpdesc.set_line_wrap(True)
                tmpdesc.set_alignment(0, 0)

                tmphbox.pack_start(tmplabel, False, False, 2)
                tmphbox.pack_start(tmpdesc, True, True, 2)

                vbox.pack_start(tmphbox, False, False, 2)
            vbox.pack_start(gtk.Label(" "), False, False, 2)
        scrollbox.add_with_viewport(vbox)
        dialog.show_all()
        dialog.run()
        dialog.destroy()

    def show_website(self, dialog, blah, link):
        self.browser_load(link)

    def initialize_systrayicon(self):
        # Make system tray 'icon' to sit in the system tray
        if HAVE_STATUS_ICON:
            self.statusicon = gtk.StatusIcon()
            self.statusicon.set_from_file(self.find_path('sonata.png'))
            self.statusicon.set_visible(self.show_trayicon)
            self.statusicon.connect('popup_menu', self.trayaction_menu)
            self.statusicon.connect('activate', self.trayaction_activate)
        elif HAVE_EGG:
            self.trayeventbox = gtk.EventBox()
            self.trayeventbox.set_visible_window(False)
            self.trayeventbox.connect('button_press_event', self.trayaction)
            self.trayeventbox.connect('scroll-event', self.trayaction_scroll)
            self.trayeventbox.connect('size-allocate', self.trayaction_size)
            self.traytips.set_tip(self.trayeventbox)
            self.trayimage = gtk.Image()
            self.trayeventbox.add(self.trayimage)
            try:
                self.trayicon = egg.trayicon.TrayIcon("TrayIcon")
                self.trayicon.add(self.trayeventbox)
                if self.show_trayicon:
                    self.trayicon.show_all()
                else:
                    self.trayicon.hide_all()
            except:
                pass

    def browser_load(self, docslink):
        browser_error = False
        if len(self.url_browser.strip()) > 0:
            try:
                pid = subprocess.Popen([self.url_browser, docslink]).pid
            except:
                browser_error = True
        else:
            try:
                pid = subprocess.Popen(["gnome-open", docslink]).pid
            except:
                try:
                    pid = subprocess.Popen(["exo-open", docslink]).pid
                except:
                    try:
                        pid = subprocess.Popen(["kfmclient", "openURL", docslink]).pid
                    except:
                        try:
                            pid = subprocess.Popen(["firefox", docslink]).pid
                        except:
                            try:
                                pid = subprocess.Popen(["mozilla", docslink]).pid
                            except:
                                try:
                                    pid = subprocess.Popen(["opera", docslink]).pid
                                except:
                                    browser_error = True
        if browser_error:
            show_error_msg(self.window, _('Unable to launch a suitable browser.'), _('Launch Browser'), 'browserLoadError')

    def sanitize_mpdtag(self, mpdtag, return_int=False, str_padding=0):
        # Takes the mpd tag and tries to convert it to simply the
        # track/disc number. Known forms for the mpd tag can be
        # "4", "4/10", and "4,10".
        try:
            ret = int(mpdtag.split('/')[0])
        except:
            try:
                ret = int(mpdtag.split(',')[0])
            except:
                ret = 0
        # Don't allow negative numbers:
        if ret < 0:
            ret = 0
        if not return_int:
            ret = str(ret).zfill(str_padding)
        return ret

    def searchfilter_toggle(self, widget, initial_text=""):
        if self.filterbox_visible:
            self.filterbox_visible = False
            self.edit_style_orig = self.searchtext.get_style()
            self.filterbox.set_no_show_all(True)
            self.filterbox.hide()
            self.searchfilter_stop_loop(self.filterbox);
            self.filterpattern.set_text("")
        elif self.conn:
            self.playlist_pos_before_filter = self.current.get_visible_rect()[1]
            self.filterbox_visible = True
            self.filterpattern.handler_block(self.filter_changed_handler)
            self.filterpattern.set_text(initial_text)
            self.filterpattern.handler_unblock(self.filter_changed_handler)
            self.prevtodo = 'foo'
            self.filterbox.set_no_show_all(False)
            self.filterbox.show_all()
            # extra thread for background search work, synchronized with a condition and its internal mutex
            self.filterbox_cond = threading.Condition()
            self.filterbox_cmd_buf = initial_text
            qsearch_thread = threading.Thread(target=self.searchfilter_loop)
            qsearch_thread.setDaemon(True)
            qsearch_thread.start()
            gobject.idle_add(self.search_entry_grab_focus, self.filterpattern)
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
            self.conn.do.playid(song_id)
            self.keep_song_centered_in_list()

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
                        song_info.append(make_unbold(row[i+1]))
                    matches.append(song_info)
            else:
                # this make take some seconds... and we'll escape the search text because
                # we'll be searching for a match in items that are also escaped.
                todo = escape_html(todo)
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
                        song_info.append(make_unbold(row[i+1]))
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
                gobject.idle_add(self.edit_entry_changed, self.filterpattern, True)
            else:
                gobject.idle_add(self.edit_entry_revert_color, self.filterpattern)
            self.current.thaw_child_notify()

    def searchfilter_key_pressed(self, widget, event):
        if event.keyval == gtk.gdk.keyval_from_name('Down') or event.keyval == gtk.gdk.keyval_from_name('Up') or event.keyval == gtk.gdk.keyval_from_name('Page_Down') or event.keyval == gtk.gdk.keyval_from_name('Page_Up'):
            self.current.grab_focus()
            self.current.emit("key-press-event", event)
            gobject.idle_add(self.search_entry_grab_focus, widget)

    def search_entry_grab_focus(self, widget):
        widget.grab_focus()
        widget.set_position(-1)

    def main(self):
        gtk.main()

class TrayIconTips(gtk.Window):
    """Custom tooltips derived from gtk.Window() that allow for markup text and multiple widgets, e.g. a progress bar. ;)"""
    MARGIN = 4

    def __init__(self, widget=None):
        gtk.Window.__init__(self, gtk.WINDOW_POPUP)
        # from gtktooltips.c:gtk_tooltips_force_window
        self.set_app_paintable(True)
        self.set_resizable(False)
        self.set_name("gtk-tooltips")
        self.connect('expose-event', self._on__expose_event)

        if widget != None:
            self._label = gtk.Label()
            self.add(self._label)

        self._show_timeout_id = -1
        self.timer_tag = None
        self.notif_handler = None
        self.use_notifications_location = False
        self.notifications_location = 0

    def _calculate_pos(self, widget):
        if HAVE_STATUS_ICON:
            icon_screen, icon_rect, icon_orient = widget.get_geometry()
            x = icon_rect[0]
            y = icon_rect[1]
            width = icon_rect[2]
            height = icon_rect[3]
        else:
            try:
                x, y = widget.window.get_origin()
                if widget.flags() & gtk.NO_WINDOW:
                    x += widget.allocation.x
                    y += widget.allocation.y
                width = widget.allocation.width
                height = widget.allocation.height
            except:
                pass
        w, h = self.size_request()

        screen = self.get_screen()
        pointer_screen, px, py, _ = screen.get_display().get_pointer()
        if pointer_screen != screen:
            px = x
            py = y
        try:
            # Use the monitor that the systemtray icon is on
            monitor_num = screen.get_monitor_at_point(x, y)
        except:
            # No systemtray icon, use the monitor that the pointer is on
            monitor_num = screen.get_monitor_at_point(px, py)
        monitor = screen.get_monitor_geometry(monitor_num)

        try:
            # If the tooltip goes off the screen horizontally, realign it so that
            # it all displays.
            if (x + w) > monitor.x + monitor.width:
                x = monitor.x + monitor.width - w
            # If the tooltip goes off the screen vertically (i.e. the system tray
            # icon is on the bottom of the screen), realign the icon so that it
            # shows above the icon.
            if ((y + h + height + self.MARGIN) >
                monitor.y + monitor.height):
                y = y - h - self.MARGIN
            else:
                y = y + height + self.MARGIN
        except:
            pass

        if self.use_notifications_location == False:
            try:
                return x, y
            except:
                #Fallback to top-left:
                return monitor.x, monitor.y
        elif self.notifications_location == 0:
            try:
                return x, y
            except:
                #Fallback to top-left:
                return monitor.x, monitor.y
        elif self.notifications_location == 1:
            return monitor.x, monitor.y
        elif self.notifications_location == 2:
            return monitor.x + monitor.width - w, monitor.y
        elif self.notifications_location == 3:
            return monitor.x, monitor.y + monitor.height - h
        elif self.notifications_location == 4:
            return monitor.x + monitor.width - w, monitor.y + monitor.height - h
        elif self.notifications_location == 5:
            return monitor.x + (monitor.width - w)/2, monitor.y + (monitor.height - h)/2

    def _event_handler (self, widget):
        widget.connect_after("event-after", self._motion_cb)

    def _motion_cb (self, widget, event):
        if self.notif_handler != None:
            return
        if event.type == gtk.gdk.LEAVE_NOTIFY:
            self._remove_timer()
        if event.type == gtk.gdk.ENTER_NOTIFY:
            self._start_delay(widget)

    def _start_delay (self, widget):
        self.timer_tag = gobject.timeout_add(500, self._tips_timeout, widget)

    def _tips_timeout (self, widget):
        self.use_notifications_location = False
        self._real_display(widget)

    def _remove_timer(self):
        self.hide()
        if self.timer_tag:
            gobject.source_remove(self.timer_tag)
        self.timer_tag = None

    # from gtktooltips.c:gtk_tooltips_paint_window
    def _on__expose_event(self, window, event):
        w, h = window.size_request()
        window.style.paint_flat_box(window.window,
                                    gtk.STATE_NORMAL, gtk.SHADOW_OUT,
                                    None, window, "tooltip",
                                    0, 0, w, h)
        return False

    def _real_display(self, widget):
        x, y = self._calculate_pos(widget)
        self.move(x, y)
        self.show()

    # Public API

    def set_text(self, text):
        self._label.set_text(text)

    def hide(self):
        gtk.Window.hide(self)
        gobject.source_remove(self._show_timeout_id)
        self._show_timeout_id = -1
        self.notif_handler = None

    def display(self, widget):
        if not self._label.get_text():
            return

        if self._show_timeout_id != -1:
            return

        self._show_timeout_id = gobject.timeout_add(500, self._real_display, widget)

    def set_tip (self, widget):
        self.widget = widget
        self._event_handler (self.widget)

    def add_widget (self, widget_to_add):
        self.widget_to_add = widget_to_add
        self.add(self.widget_to_add)

if __name__ == "__main__":
    base = Base()
    gtk.gdk.threads_enter()
    base.main()
    gtk.gdk.threads_leave()

def show_error_msg(owner, message, title, role):
    error_dialog = gtk.MessageDialog(owner, gtk.DIALOG_MODAL, gtk.MESSAGE_WARNING, gtk.BUTTONS_CLOSE, message)
    error_dialog.set_title(title)
    error_dialog.set_role(role)
    error_dialog.run()
    error_dialog.destroy()

def show_error_msg_yesno(owner, message, title, role):
    error_dialog = gtk.MessageDialog(owner, gtk.DIALOG_MODAL, gtk.MESSAGE_WARNING, gtk.BUTTONS_YES_NO, message)
    error_dialog.set_title(title)
    error_dialog.set_role(role)
    response = error_dialog.run()
    value = response
    error_dialog.destroy()
    return value

def convert_time(raw):
    # Converts raw time to 'hh:mm:ss' with leading zeros as appropriate
    h, m, s = ['%02d' % c for c in (raw/3600, (raw%3600)/60, raw%60)]
    if h == '00':
        if m.startswith('0'):
            m = m[1:]
        return m + ':' + s
    else:
        if h.startswith('0'):
            h = h[1:]
        return h + ':' + m + ':' + s

def make_bold(s):
    if not (str(s).startswith('<b>') and str(s).endswith('</b>')):
        return '<b>%s</b>' % s
    else:
        return s

def make_unbold(s):
    if str(s).startswith('<b>') and str(s).endswith('</b>'):
        return s[3:-4]
    else:
        return s

def escape_html(s):
    s = s.replace('&', '&amp;')
    s = s.replace('<', '&lt;')
    s = s.replace('>', '&gt;')
    s = s.replace('"', '&quot;')
    return s

def unescape_html(s):
    s = s.replace('&amp;', '&')
    s = s.replace('amp;', '&')
    s = s.replace('&lt;', '<')
    s = s.replace('&gt;', '>')
    s = s.replace('&quot;', '"')
    s = s.replace('&nbsp;', ' ')
    return s

def wiki_to_html(s):
    tag_pairs = [["'''", "<b>", "</b>"], ["''", "<i>", "</i>"]]
    for tag in tag_pairs:
        tag_start = True
        pos = 0
        while pos > -1:
            pos = s.find(tag[0], pos)
            if pos > -1:
                if tag_start:
                    s = s[:pos] + tag[1] + s[pos+3:]
                else:
                    s = s[:pos] + tag[2] + s[pos+3:]
                pos += 1
                tag_start = not tag_start
    return s

def strip_all_slashes(s):
    s = s.replace("\\", "")
    s = s.replace("/", "")
    s = s.replace("\"", "")
    return s

def rmgeneric(path, __func__):
    try:
        __func__(path)
    except OSError, (errno, strerror):
        pass

def is_binary(f):
    if '\0' in f: # found null byte
        return True
    return False

def link_markup(s, enclose_in_parentheses, small, linkcolor):
    if enclose_in_parentheses:
        s = "(" + s + ")"
    if small:
        s = "<small>" + s + "</small>"
    if linkcolor:
        color = linkcolor
    else:
        color = "blue" #no theme color, default to blue..
    s = "<span color='" + color + "'>" + s + "</span>"
    return s

def removeall(path):
    if not os.path.isdir(path):
        return

    files=os.listdir(path)

    for x in files:
        fullpath=os.path.join(path, x)
        if os.path.isfile(fullpath):
            f=os.remove
            rmgeneric(fullpath, f)
        elif os.path.isdir(fullpath):
            removeall(fullpath)
            f=os.rmdir
            rmgeneric(fullpath, f)

def remove_list_duplicates(inputlist, inputlist2=[], case_sensitive=True):
    # If inputlist2 is provided, keep it synced with inputlist.
    # Note that this is only implemented if case_sensitive=False.
    # Also note that we do this manually instead of using list(set(x))
    # so that the inputlist order is preserved.
    if len(inputlist2) > 0:
        sync_lists = True
    else:
        sync_lists = False
    outputlist = []
    outputlist2 = []
    for i in range(len(inputlist)):
        dup = False
        # Search outputlist from the end, since the inputlist is typically in
        # alphabetical order
        j = len(outputlist)-1
        if case_sensitive:
            while j >= 0:
                if inputlist[i] == outputlist[j]:
                    dup = True
                    break
                j = j - 1
        elif sync_lists:
            while j >= 0:
                if inputlist[i].lower() == outputlist[j].lower() and inputlist2[i].lower() == outputlist2[j].lower():
                    dup = True
                    break
                j = j - 1
        else:
            while j >= 0:
                if inputlist[i].lower() == outputlist[j].lower():
                    dup = True
                    break
                j = j - 1
        if not dup:
            outputlist.append(inputlist[i])
            if sync_lists:
                outputlist2.append(inputlist2[i])
    return (outputlist, outputlist2)

the_re = re.compile('^the ')
def lower_no_the(s):
    return the_re.sub('', s.lower())

def first_of_2tuple(t):
    fst, snd = t
    return fst

def start_dbus_interface(toggle=False):
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
                    self.pp(None)
                elif key == 'Stop':
                    self.stop(None)
                elif key == 'Previous':
                    self.prev(None)
                elif key == 'Next':
                    self.next(None)

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
