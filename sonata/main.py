
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

import sys, locale, gettext, os, warnings
import urllib, urllib2, re, gc, shutil
import threading

import mpd

import gobject, gtk, pango

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

import mpdhelper as mpdh

import misc, ui, img, tray

from consts import consts
from pluginsystem import pluginsystem
from preferences import Preferences
from config import Config

import tagedit, artwork, about, scrobbler, info, library, streams, playlists, current
import dbus_plugin as dbus

try:
    import version
except ImportError:
    import svnversion as version

class Base(object):
    def __init__(self, args, window=None, sugar=False):
        # The following attributes were used but not defined here before:
        self.album_current_artist = None

        self.allow_art_search = None
        self.choose_dialog = None
        self.chooseimage_visible = None

        self.imagelist = None

        self.iterate_handler = None
        self.local_dest_filename = None

        self.notification_width = None

        self.remote_albumentry = None
        self.remote_artistentry = None
        self.remote_dest_filename = None
        self.remotefilelist = None
        self.seekidle = None
        self.statusicon = None
        self.trayeventbox = None
        self.trayicon = None
        self.trayimage = None
        self.artwork = None

        self.client = mpd.MPDClient()
        self.conn = False

        # Constants
        self.TAB_CURRENT = _("Current")
        self.TAB_LIBRARY = _("Library")
        self.TAB_PLAYLISTS = _("Playlists")
        self.TAB_STREAMS = _("Streams")
        self.TAB_INFO = _("Info")

        # If the connection to MPD times out, this will cause the interface to freeze while
        # the socket.connect() calls are repeatedly executed. Therefore, if we were not
        # able to make a connection, slow down the iteration check to once every 15 seconds.
        self.iterate_time_when_connected = 500
        self.iterate_time_when_disconnected_or_stopped = 1000 # Slow down polling when disconnected stopped


        self.trying_connection = False

        self.traytips = tray.TrayIconTips()

        # better keep a reference around
        try:
            self.dbus_service = dbus.SonataDBus(self.dbus_show, self.dbus_toggle, self.dbus_popup)
        except Exception:
            pass
        dbus.start_dbus_interface()

        self.gnome_session_management()

        misc.create_dir('~/.covers/')

        # Initialize vars for GUI
        self.current_tab = self.TAB_CURRENT

        self.prevconn = []
        self.prevstatus = None
        self.prevsonginfo = None

        self.popuptimes = ['2', '3', '5', '10', '15', '30', _('Entire song')]

        self.exit_now = False
        self.ignore_toggle_signal = False

        self.user_connect = False

        self.sonata_loaded = False
        self.call_gc_collect = False

        self.album_reset_artist()

        show_prefs = False
        self.merge_id = None

        self.actionGroupProfiles = None

        self.skip_on_profiles_click = False
        self.last_repeat = None
        self.last_random = None
        self.last_title = None
        self.last_progress_frac = None
        self.last_progress_text = None

        self.last_status_text = ""

        self.eggtrayfile = None
        self.eggtrayheight = None

        self.img_clicked = False

        self.mpd_update_queued = False

        self.prefs_last_tab = 0

        # XXX get rid of all of these:
        self.all_tab_names = [self.TAB_CURRENT, self.TAB_LIBRARY, self.TAB_PLAYLISTS, self.TAB_STREAMS, self.TAB_INFO]
        all_tab_ids = "current library playlists streams info".split()
        self.tabname2id = dict(zip(self.all_tab_names, all_tab_ids))
        self.tabid2name = dict(zip(all_tab_ids, self.all_tab_names))
        self.tabname2focus = dict()

        self.config = Config(_('Default Profile'), _("by") + " %A " + _("from") + " %B", library.library_set_data)
        self.preferences = Preferences(self.config)
        self.settings_load()

        if args.start_visibility is not None:
            self.config.withdrawn = not args.start_visibility
        if self.config.autoconnect:
            self.user_connect = True
        args.apply_profile_arg(self)

        self.notebook_show_first_tab = not self.config.tabs_expanded or self.config.withdrawn

        # Add some icons, assign pixbufs:
        self.iconfactory = gtk.IconFactory()
        ui.icon(self.iconfactory, 'sonata', self.find_path('sonata.png'))
        ui.icon(self.iconfactory, 'artist', self.find_path('sonata-artist.png'))
        ui.icon(self.iconfactory, 'album', self.find_path('sonata-album.png'))
        icon_theme = gtk.icon_theme_get_default()
        if HAVE_SUGAR:
            activity_root = activity.get_bundle_path()
            icon_theme.append_search_path(os.path.join(activity_root, 'share'))
        img_width, _img_height = gtk.icon_size_lookup(VOLUME_ICON_SIZE)
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
            if self.config.ontop:
                self.window.set_keep_above(True)
            if self.config.sticky:
                self.window.stick()
            if not self.config.decorated:
                self.window.set_decorated(False)

        self.notebook = gtk.Notebook()

        # Artwork
        self.artwork = artwork.Artwork(self.config, self.find_path, misc.is_lang_rtl(self.window), lambda:self.info_imagebox.get_size_request(), self.schedule_gc_collect, self.target_image_filename, self.imagelist_append, self.remotefilelist_append, self.notebook.get_allocation, self.set_allow_art_search, self.status_is_play_or_pause, self.find_path('sonata-album.png'), self.get_current_song_text)

        # Popup menus:
        actions = (
            ('sortmenu', None, _('_Sort List')),
            ('plmenu', None, _('Sa_ve List to')),
            ('profilesmenu', None, _('_Connection')),
            ('playaftermenu', None, _('P_lay after')),
            ('updatemenu', None, _('_Update')),
            ('chooseimage_menu', gtk.STOCK_CONVERT, _('Use _Remote Image...'), None, None, self.image_remote),
            ('localimage_menu', gtk.STOCK_OPEN, _('Use _Local Image...'), None, None, self.image_local),
            ('fullscreencoverart_menu', gtk.STOCK_FULLSCREEN, _('_Fullscreen Mode'), 'F11', None, self.fullscreen_cover_art),
            ('resetimage_menu', gtk.STOCK_CLEAR, _('Reset Image'), None, None, self.artwork.on_reset_image),
            ('playmenu', gtk.STOCK_MEDIA_PLAY, _('_Play'), None, None, self.mpd_pp),
            ('pausemenu', gtk.STOCK_MEDIA_PAUSE, _('Pa_use'), None, None, self.mpd_pp),
            ('stopmenu', gtk.STOCK_MEDIA_STOP, _('_Stop'), None, None, self.mpd_stop),
            ('prevmenu', gtk.STOCK_MEDIA_PREVIOUS, _('Pre_vious'), None, None, self.mpd_prev),
            ('nextmenu', gtk.STOCK_MEDIA_NEXT, _('_Next'), None, None, self.mpd_next),
            ('quitmenu', gtk.STOCK_QUIT, _('_Quit'), None, None, self.on_delete_event_yes),
            ('removemenu', gtk.STOCK_REMOVE, _('_Remove'), None, None, self.on_remove),
            ('clearmenu', gtk.STOCK_CLEAR, _('_Clear'), '<Ctrl>Delete', None, self.mpd_clear),
            ('updatefullmenu', None, _('_Entire Library'), '<Ctrl><Shift>u', None, self.on_updatedb),
            ('updateselectedmenu', None, _('_Selected Items'), '<Ctrl>u', None, self.on_updatedb_shortcut),
            ('preferencemenu', gtk.STOCK_PREFERENCES, _('_Preferences...'), 'F5', None, self.on_prefs),
            ('aboutmenu', None, _('_About...'), 'F1', None, self.on_about),
            ('tagmenu', None, _('_Edit Tags...'), '<Ctrl>t', None, self.on_tags_edit),
            ('addmenu', gtk.STOCK_ADD, _('_Add'), '<Ctrl>d', None, self.on_add_item),
            ('replacemenu', gtk.STOCK_REDO, _('_Replace'), '<Ctrl>r', None, self.on_replace_item),
            ('add2menu', None, _('Add'), '<Shift><Ctrl>d', None, self.on_add_item_play),
            ('replace2menu', None, _('Replace'), '<Shift><Ctrl>r', None, self.on_replace_item_play),
            ('rmmenu', None, _('_Delete...'), None, None, self.on_remove),
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
            ('connectkey', None, 'Connect Key', '<Alt>c', None, self.on_connectkey_pressed),
            ('disconnectkey', None, 'Disconnect Key', '<Alt>d', None, self.on_disconnectkey_pressed),
            ('searchkey', None, 'Search Key', '<Ctrl>h', None, self.on_library_search_shortcut),
            )

        toggle_actions = (
            ('showmenu', None, _('S_how Sonata'), None, None, self.on_withdraw_app_toggle, not self.config.withdrawn),
            ('repeatmenu', None, _('_Repeat'), None, None, self.on_repeat_clicked, False),
            ('randommenu', None, _('Rando_m'), None, None, self.on_random_clicked, False),
            (self.TAB_CURRENT, None, self.TAB_CURRENT, None, None, self.on_tab_toggle, self.config.current_tab_visible),
            (self.TAB_LIBRARY, None, self.TAB_LIBRARY, None, None, self.on_tab_toggle, self.config.library_tab_visible),
            (self.TAB_PLAYLISTS, None, self.TAB_PLAYLISTS, None, None, self.on_tab_toggle, self.config.playlists_tab_visible),
            (self.TAB_STREAMS, None, self.TAB_STREAMS, None, None, self.on_tab_toggle, self.config.streams_tab_visible),
            (self.TAB_INFO, None, self.TAB_INFO, None, None, self.on_tab_toggle, self.config.info_tab_visible),
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
                <menuitem action="repeatmenu"/>
                <menuitem action="randommenu"/>
                <menu action="updatemenu">
                  <menuitem action="updateselectedmenu"/>
                  <menuitem action="updatefullmenu"/>
                </menu>
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
        elif self.config.initial_run:
            show_prefs = True

        # Realizing self.window will allow us to retrieve the theme's
        # link-color; we can then apply to it various widgets:
        try:
            self.window.realize()
            linkcolor = self.window.style_get_property("link-color").to_string()
        except:
            linkcolor = None

        # Audioscrobbler
        self.scrobbler = scrobbler.Scrobbler(self.config)
        self.scrobbler.import_module()
        self.scrobbler.init()

        # Current tab
        self.current = current.Current(self.config, self.client, self.TAB_CURRENT, self.on_current_button_press, self.parse_formatting_colnames, self.parse_formatting, self.connected, lambda:self.sonata_loaded, lambda:self.songinfo, self.update_statusbar, self.iterate_now, lambda:self.library.libsearchfilter_get_style(), self.new_tab)

        self.current_treeview = self.current.get_treeview()
        self.current_selection = self.current.get_selection()

        currentactions = [
            ('centerplaylistkey', None, 'Center Playlist Key', '<Ctrl>i', None, self.current.center_song_in_list),
            ('sortbyartist', None, _('By Artist'), None, None, self.current.on_sort_by_artist),
            ('sortbyalbum', None, _('By Album'), None, None, self.current.on_sort_by_album),
            ('sortbytitle', None, _('By Song Title'), None, None, self.current.on_sort_by_title),
            ('sortbyfile', None, _('By File Name'), None, None, self.current.on_sort_by_file),
            ('sortbydirfile', None, _('By Dir & File Name'), None, None, self.current.on_sort_by_dirfile),
            ('sortreverse', None, _('Reverse List'), None, None, self.current.on_sort_reverse),
            ]

        # Library tab
        self.library = library.Library(self.config, self.client, self.artwork, self.TAB_LIBRARY, self.find_path('sonata-album.png'), self.settings_save, self.current.filtering_entry_make_red, self.current.filtering_entry_revert_color, self.current.filter_key_pressed, self.on_add_item, self.parse_formatting, self.connected, self.on_library_button_press, self.on_library_search_text_click, self.new_tab)

        self.library_treeview = self.library.get_treeview()
        self.library_selection = self.library.get_selection()

        libraryactions = self.library.get_libraryactions()

        # Info tab
        self.info = info.Info(self.config, self.artwork.get_info_image(), linkcolor, self.on_link_click, self.library.library_return_search_items, self.get_playing_song, self.TAB_INFO, self.on_image_activate, self.on_image_motion_cb, self.on_image_drop_cb, self.album_return_artist_and_tracks, self.new_tab)

        self.info_imagebox = self.info.get_info_imagebox()

        # Streams tab
        self.streams = streams.Streams(self.config, self.window, self.on_streams_button_press, self.on_add_item, self.settings_save, self.iterate_now, self.TAB_STREAMS, self.new_tab)

        self.streams_treeview = self.streams.get_treeview()
        self.streams_selection = self.streams.get_selection()

        streamsactions = [
            ('newmenu', None, _('_New...'), '<Ctrl>n', None, self.streams.on_streams_new),
            ('editmenu', None, _('_Edit...'), None, None, self.streams.on_streams_edit),
            ]

        # Playlists tab
        self.playlists = playlists.Playlists(self.config, self.window, self.client, lambda:self.UIManager, self.update_menu_visibility, self.iterate_now, self.on_add_item, self.on_playlists_button_press, self.current.get_current_songs, self.connected, self.TAB_PLAYLISTS, self.new_tab)

        self.playlists_treeview = self.playlists.get_treeview()
        self.playlists_selection = self.playlists.get_selection()

        playlistsactions = [
            ('savemenu', None, _('_New...'), '<Ctrl><Shift>s', None, self.playlists.on_playlist_save),
            ('renamemenu', None, _('_Rename...'), None, None, self.playlists.on_playlist_rename),
            ]

        # Main app:
        self.UIManager = gtk.UIManager()
        actionGroup = gtk.ActionGroup('Actions')
        actionGroup.add_actions(actions)
        actionGroup.add_actions(currentactions)
        actionGroup.add_actions(libraryactions)
        actionGroup.add_actions(streamsactions)
        actionGroup.add_actions(playlistsactions)
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
        self.library.set_librarymenu(self.librarymenu)
        self.notebookmenu = self.UIManager.get_widget('/notebookmenu')
        mainhbox = gtk.HBox()
        mainvbox = gtk.VBox()
        tophbox = gtk.HBox()

        self.albumimage = self.artwork.get_albumimage()

        self.imageeventbox = ui.eventbox(add=self.albumimage)
        self.imageeventbox.drag_dest_set(gtk.DEST_DEFAULT_HIGHLIGHT | gtk.DEST_DEFAULT_DROP, [("text/uri-list", 0, 80), ("text/plain", 0, 80)], gtk.gdk.ACTION_DEFAULT)
        if not self.config.show_covers:
            ui.hide(self.imageeventbox)
        tophbox.pack_start(self.imageeventbox, False, False, 5)
        topvbox = gtk.VBox()
        toptophbox = gtk.HBox()
        self.prevbutton = ui.button(stock=gtk.STOCK_MEDIA_PREVIOUS, relief=gtk.RELIEF_NONE, can_focus=False, hidetxt=True)
        self.ppbutton = ui.button(stock=gtk.STOCK_MEDIA_PLAY, relief=gtk.RELIEF_NONE, can_focus=False, hidetxt=True)
        self.stopbutton = ui.button(stock=gtk.STOCK_MEDIA_STOP, relief=gtk.RELIEF_NONE, can_focus=False, hidetxt=True)
        self.nextbutton = ui.button(stock=gtk.STOCK_MEDIA_NEXT, relief=gtk.RELIEF_NONE, can_focus=False, hidetxt=True)
        for mediabutton in (self.prevbutton, self.ppbutton, self.stopbutton, self.nextbutton):
            toptophbox.pack_start(mediabutton, False, False, 0)
            if not self.config.show_playback:
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
        if not self.config.show_progress:
            ui.hide(self.progressbox)
        self.volumebutton = ui.togglebutton(relief=gtk.RELIEF_NONE, can_focus=False)
        self.volume_set_image("stock_volume-med")
        if not self.config.show_playback:
            ui.hide(self.volumebutton)
        toptophbox.pack_start(self.volumebutton, False, False, 0)
        topvbox.pack_start(toptophbox, False, False, 2)
        self.expander = ui.expander(text=_("Playlist"), expand=self.config.expanded, can_focus=False)
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

        mainvbox.pack_start(self.notebook, True, True, 5)

        self.statusbar = gtk.Statusbar()
        self.statusbar.set_has_resize_grip(True)
        if not self.config.show_statusbar or not self.config.expanded:
            ui.hide(self.statusbar)
        mainvbox.pack_start(self.statusbar, False, False, 0)
        mainhbox.pack_start(mainvbox, True, True, 3)
        if self.window_owner:
            self.window.add(mainhbox)
            self.window.move(self.config.x, self.config.y)
            self.window.set_size_request(270, -1)
        elif HAVE_SUGAR:
            self.window.set_canvas(mainhbox)
        if not self.config.expanded:
            ui.hide(self.notebook)
            self.cursonglabel1.set_markup('<big><b>' + _('Stopped') + '</b></big>')
            self.cursonglabel2.set_markup('<small>' + _('Click to expand') + '</small>')
            if self.window_owner:
                self.window.set_default_size(self.config.w, 1)
        else:
            self.cursonglabel1.set_markup('<big><b>' + _('Stopped') + '</b></big>')
            self.cursonglabel2.set_markup('<small>' + _('Click to collapse') + '</small>')
            if self.window_owner:
                self.window.set_default_size(self.config.w, self.config.h)
        self.expander.set_tooltip_text(self.cursonglabel1.get_text())
        if not self.conn:
            self.progressbar.set_text(_('Not Connected'))
        elif not self.status:
            self.progressbar.set_text(_('No Read Permission'))

        # Update tab positions: XXX move to self.new_tab
        self.notebook.reorder_child(self.current.get_widgets(), self.config.current_tab_pos)
        self.notebook.reorder_child(self.library.get_widgets(), self.config.library_tab_pos)
        self.notebook.reorder_child(self.playlists.get_widgets(), self.config.playlists_tab_pos)
        self.notebook.reorder_child(self.streams.get_widgets(), self.config.streams_tab_pos)
        self.notebook.reorder_child(self.info.get_widgets(), self.config.info_tab_pos)
        self.last_tab = self.notebook_get_tab_text(self.notebook, 0)

        # Song notification window:
        outtertipbox = gtk.VBox()
        tipbox = gtk.HBox()

        self.trayalbumeventbox, self.trayalbumimage2 = self.artwork.get_trayalbum()

        hiddenlbl = ui.label(w=2, h=-1)
        tipbox.pack_start(hiddenlbl, False, False, 0)
        tipbox.pack_start(self.trayalbumeventbox, False, False, 0)

        tipbox.pack_start(self.trayalbumimage2, False, False, 0)
        if not self.config.show_covers:
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
        if not self.config.show_progress:
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
        style = self.fullscreencoverart.get_style().copy()
        style.bg[gtk.STATE_NORMAL] = self.fullscreencoverart.get_colormap().alloc_color("black")
        style.bg_pixmap[gtk.STATE_NORMAL] = None
        self.fullscreencoverart.set_style(style)
        self.fullscreencoverart.add_accel_group(self.UIManager.get_accel_group())
        fscavbox = gtk.VBox()
        fscahbox = gtk.HBox()
        self.fullscreenalbumimage = self.artwork.get_fullscreenalbumimage()
        fscalbl, fscalbl2 = self.artwork.get_fullscreenalbumlabels()
        fscahbox.pack_start(self.fullscreenalbumimage, True, False, 0)
        fscavbox.pack_start(ui.label(), True, False, 0)
        fscavbox.pack_start(fscahbox, False, False, 0)
        fscavbox.pack_start(fscalbl, False, False, 5)
        fscavbox.pack_start(fscalbl2, False, False, 5)
        fscavbox.pack_start(ui.label(), True, False, 0)
        if not self.config.show_covers:
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
        self.randommenu.connect('toggled', self.on_random_clicked)
        self.repeatmenu.connect('toggled', self.on_repeat_clicked)
        self.volumescale.connect('change_value', self.on_volumescale_change)
        self.volumescale.connect('scroll-event', self.on_volumescale_scroll)
        self.cursonglabel1.connect('notify::label', self.on_currsong_notify)
        self.progressbar.connect('notify::fraction', self.on_progressbar_notify_fraction)
        self.progressbar.connect('notify::text', self.on_progressbar_notify_text)
        self.mainwinhandler = self.window.connect('button_press_event', self.on_window_click)
        self.notebook.connect('button_press_event', self.on_notebook_click)
        self.notebook.connect('size-allocate', self.on_notebook_resize)
        self.notebook.connect('switch-page', self.on_notebook_page_change)

        self.fullscreencoverart.add_events(gtk.gdk.BUTTON_PRESS_MASK)
        self.fullscreencoverart.connect("button-press-event", self.fullscreen_cover_art_close, False)
        self.fullscreencoverart.connect("key-press-event", self.fullscreen_cover_art_close, True)
        for treeview in [self.current_treeview, self.library_treeview, self.playlists_treeview, self.streams_treeview]:
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
        if self.window_owner and self.config.withdrawn:
            while gtk.events_pending():
                gtk.main_iteration()

        dbus.init_gnome_mediakeys(self.mpd_pp, self.mpd_stop, self.mpd_prev, self.mpd_next)

        # Try to connect to mmkeys signals, if no dbus and gnome 2.18+
        if not dbus.using_gnome_mediakeys():
            try:
                import mmkeys
                # this must be an attribute to keep it around:
                self.keys = mmkeys.MmKeys()
                self.keys.connect("mm_prev", self.mpd_prev)
                self.keys.connect("mm_next", self.mpd_next)
                self.keys.connect("mm_playpause", self.mpd_pp)
                self.keys.connect("mm_stop", self.mpd_stop)
            except ImportError:
                pass

        # Set up current view
        self.currentdata = self.current.get_model()

        # Initialize playlist data and widget
        self.playlistsdata = self.playlists.get_model()

        # Initialize streams data and widget
        self.streamsdata = self.streams.get_model()

        # Initialize library data and widget
        self.librarydata = self.library.get_model()
        self.artwork.library_artwork_init(self.librarydata, consts.LIB_COVER_SIZE)

        if self.window_owner:
            icon = self.window.render_icon('sonata', gtk.ICON_SIZE_DIALOG)
            self.window.set_icon(icon)

        self.streams.populate()

        self.iterate_now()
        if self.window_owner:
            if self.config.withdrawn:
                if (HAVE_EGG and self.trayicon.get_property('visible')) or (HAVE_STATUS_ICON and self.statusicon.is_embedded() and self.statusicon.get_visible()):
                    ui.hide(self.window)
        self.window.show_all()

        # Ensure that button images are displayed despite GTK+ theme
        self.window.get_settings().set_property("gtk-button-images", True)

        if self.config.update_on_start:
            self.on_updatedb(None)

        self.notebook.set_no_show_all(False)
        self.window.set_no_show_all(False)

        if show_prefs:
            self.on_prefs(None)

        self.config.initial_run = False

        # Ensure that sonata is loaded before we display the notif window
        self.sonata_loaded = True
        self.on_currsong_notify()
        self.current.center_song_in_list()

        if HAVE_STATUS_ICON:
            gobject.timeout_add(250, self.iterate_status_icon)

        gc.disable()

        gobject.idle_add(self.header_save_column_widths)

        # XXX Plugins temporarily disabled
        #for tabs in pluginsystem.get('tabs'):
        #	self.new_tab(*tabs())


    def new_tab(self, page, stock, text, focus):
        # create the "ear" of the tab:
        hbox = gtk.HBox()
        hbox.pack_start(ui.image(stock=stock), False, False, 2)
        hbox.pack_start(ui.label(text=text), False, False, 2)
        evbox = ui.eventbox(add=hbox)
        evbox.show_all()

        evbox.connect("button_press_event", self.on_tab_click)

        # create the actual tab:
        self.notebook.append_page(page, evbox)

        if (text in self.tabname2id and
            not getattr(self.config,
                self.tabname2id[text]+'_tab_visible')):
            ui.hide(page)

        self.notebook.set_tab_reorderable(page, True)
        if self.config.tabs_expanded:
            self.notebook.set_tab_label_packing(page, True, True, gtk.PACK_START)

        self.tabname2focus[text] = focus

        return page

    def get_playing_song(self):
        if self.status and self.status['state'] in ['play', 'pause'] and self.songinfo:
            return self.songinfo
        return None

    def gnome_session_management(self):
        try:
            import gnome, gnome.ui
            # Code thanks to quodlibet:

            # XXX gnome.init sets process name, locale...
            gnome.init("sonata", version.VERSION)

            misc.setlocale()

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

    def populate_profiles_for_menu(self):
        host, port, _password = misc.mpd_env_vars()
        if self.merge_id:
            self.UIManager.remove_ui(self.merge_id)
        if self.actionGroupProfiles:
            self.UIManager.remove_action_group(self.actionGroupProfiles)
        self.actionGroupProfiles = gtk.ActionGroup('MPDProfiles')
        self.UIManager.ensure_update()

        profile_names = [_("MPD_HOST/PORT")] if host or port else self.config.profile_names
        actions = [(str(i), None,
            "[%s] %s" % (i+1, name.replace("_", "__")), None,
            None, i)
            for i, name in enumerate(profile_names)]
        actions.append(('disconnect', None, _('Disconnect'), None, None, len(self.config.profile_names)))

        active_radio = 0 if host or port else self.config.profile_num
        if not self.conn:
            active_radio = len(self.config.profile_names)
        self.actionGroupProfiles.add_radio_actions(actions, active_radio, self.on_profiles_click)
        uiDescription = """
            <ui>
              <popup name="mainmenu">
                  <menu action="profilesmenu">
            """
        uiDescription += "".join(
            '<menuitem action=\"%s\" position="top"/>' % action[0]
            for action in reversed(actions))
        uiDescription += """</menu></popup></ui>"""
        self.merge_id = self.UIManager.add_ui_from_string(uiDescription)
        self.UIManager.insert_action_group(self.actionGroupProfiles, 0)
        self.UIManager.get_widget('/hidden').set_property('visible', False)

    def on_profiles_click(self, _radioaction, profile):
        if self.skip_on_profiles_click:
            return
        if profile.get_name() == 'disconnect':
            self.on_disconnectkey_pressed(None)
        else:
            # Clear sonata before we try to connect:
            self.mpd_disconnect()
            self.iterate_now()
            # Now connect to new profile:
            self.config.profile_num = profile.get_current_value()
            self.on_connectkey_pressed(None)

    def mpd_connect(self, blocking=False, force=False):
        if blocking:
            self._mpd_connect(blocking, force)
        else:
            thread = threading.Thread(target=self._mpd_connect, args=(blocking, force))
            thread.setDaemon(True)
            thread.start()

    def _mpd_connect(self, _blocking, force):
        if self.trying_connection:
            return
        self.trying_connection = True
        if self.user_connect or force:
            mpdh.call(self.client, 'disconnect')
            host, port, password = misc.mpd_env_vars()
            if not host:
                host = self.config.host[self.config.profile_num]
            if not port:
                port = self.config.port[self.config.profile_num]
            if not password:
                password = self.config.password[self.config.profile_num]
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

    def on_connectkey_pressed(self, _event):
        self.user_connect = True
        # Update selected radio button in menu:
        self.skip_on_profiles_click = True
        host, port, _password = misc.mpd_env_vars()
        index = str(0 if host or port else self.config.profile_num)
        self.actionGroupProfiles.get_action(index).activate()
        self.skip_on_profiles_click = False
        # Connect:
        self.mpd_connect(force=True)
        self.iterate_now()

    def on_disconnectkey_pressed(self, _event):
        self.user_connect = False
        # Update selected radio button in menu:
        self.skip_on_profiles_click = True
        self.actionGroupProfiles.get_action('disconnect').activate()
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
                        self.config.xfade_enabled = False
                    else:
                        self.config.xfade_enabled = True
                        self.config.xfade = int(self.status['xfade'])
                        if self.config.xfade > 30:
                            self.config.xfade = 30
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
        if self.config.as_enabled:
            # We update this here because self.handle_change_status() won't be
            # called while the client is paused.
            self.scrobbler.iterate()
        if self.songinfo != self.prevsonginfo:
            self.handle_change_song()

        self.prevconn = self.conn
        self.prevstatus = self.status
        self.prevsonginfo = self.songinfo

        self.iterate_handler = gobject.timeout_add(self.iterate_time, self.iterate) # Repeat ad infitum..

        if self.config.show_trayicon:
            if HAVE_STATUS_ICON:
                if self.statusicon.is_embedded() and not self.statusicon.get_visible():
                    # Systemtray appears, add icon:
                    self.systemtray_initialize()
                elif not self.statusicon.is_embedded() and self.config.withdrawn:
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
        if self.config.show_trayicon:
            if self.statusicon.is_embedded() and self.statusicon.get_visible():
                self.tooltip_show_manually()
        gobject.timeout_add(250, self.iterate_status_icon)

    def on_topwindow_keypress(self, _widget, event):
        shortcut = gtk.accelerator_name(event.keyval, event.state)
        shortcut = shortcut.replace("<Mod2>", "")
        # These shortcuts were moved here so that they don't interfere with searching the library
        if shortcut == 'BackSpace' and self.current_tab == self.TAB_LIBRARY:
            return self.library.library_browse_parent(None)
        elif shortcut == 'Escape':
            if self.volumewindow.get_property('visible'):
                self.volume_hide()
            elif self.current_tab == self.TAB_LIBRARY and self.library.search_visible():
                self.library.on_search_end(None)
            elif self.current_tab == self.TAB_CURRENT and self.current.filterbox_visible:
                self.current.searchfilter_toggle(None)
            elif self.config.minimize_to_systray:
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

            # XXX this isn't the right thing with GTK input methods:
            text = unichr(gtk.gdk.keyval_to_unicode(event.keyval))

            # We only want to toggle open the filterbar if the key press is actual text! This
            # will ensure that we skip, e.g., F5, Alt, Ctrl, ...
            if text != u"\x00" and text.strip():
                if not self.current.filterbox_visible:
                    if text != u"/":
                        self.current.searchfilter_toggle(None, text)
                    else:
                        self.current.searchfilter_toggle(None)

    def settings_load(self):
        self.config.settings_load_real(library.library_set_data)

    def settings_save(self):
        self.header_save_column_widths()

        self.config.current_tab_pos = self.notebook_get_tab_num(self.notebook, self.TAB_CURRENT)
        self.config.library_tab_pos = self.notebook_get_tab_num(self.notebook, self.TAB_LIBRARY)
        self.config.playlists_tab_pos = self.notebook_get_tab_num(self.notebook, self.TAB_PLAYLISTS)
        self.config.streams_tab_pos = self.notebook_get_tab_num(self.notebook, self.TAB_STREAMS)
        self.config.info_tab_pos = self.notebook_get_tab_num(self.notebook, self.TAB_INFO)

        self.config.settings_save_real(library.library_get_data)

    def handle_change_conn(self):
        if not self.conn:
            for mediabutton in (self.ppbutton, self.stopbutton, self.prevbutton, self.nextbutton, self.volumebutton):
                mediabutton.set_property('sensitive', False)
            self.currentdata.clear()
            if self.current_treeview.get_model():
                self.current_treeview.get_model().clear()
            if HAVE_STATUS_ICON:
                self.statusicon.set_from_file(self.find_path('sonata_disconnect.png'))
            elif HAVE_EGG and self.eggtrayheight:
                self.eggtrayfile = self.find_path('sonata_disconnect.png')
                self.trayimage.set_from_pixbuf(img.get_pixbuf_of_size(gtk.gdk.pixbuf_new_from_file(self.eggtrayfile), self.eggtrayheight)[0])
            self.info_update(True)
            if self.current.filterbox_visible:
                gobject.idle_add(self.current.searchfilter_toggle, None)
            if self.library.search_visible():
                self.library.on_search_end(None)
            self.handle_change_song()
            self.handle_change_status()
        else:
            for mediabutton in (self.ppbutton, self.stopbutton, self.prevbutton, self.nextbutton, self.volumebutton):
                mediabutton.set_property('sensitive', True)
            if self.sonata_loaded:
                self.library.library_browse(library.library_set_data(path="/"))
            self.playlists.populate()
            self.streams.populate()
            self.on_notebook_page_change(self.notebook, 0, self.notebook.get_current_page())

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
            text[i] = text[i].replace("%P", _("Path"))
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
                text = text.replace("%Y", date)
            else:
                if not has_brackets: text = text.replace("%Y", "?")
                else: return ""

        pathname = mpdh.get(item, 'file')
        try:
            dirname, filename = pathname.rsplit('/', 1)
        except ValueError: # XXX is file without '/' ever possible?
            dirname, filename = "", pathname
        if "%P" in text:
            text = text.replace("%P", dirname)
        if "%F" in text:
            text = text.replace("%F", filename)

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
        text = "".join(self._parse_formatting_substrings(sub, item,
                                 wintitle)
                for sub in substrings)
        return misc.escape_html(text) if use_escape_html else text

    def info_update(self, update_all, blank_window=False, skip_lyrics=False):
        playing_or_paused = self.conn and self.status and self.status['state'] in ['play', 'pause']
        try:
            newbitrate = self.status['bitrate'] + " kbps"
        except:
            newbitrate = ''
        self.info.info_update(playing_or_paused, newbitrate, self.songinfo, update_all, blank_window, skip_lyrics)

    def on_treeview_selection_changed(self, treeselection):
        self.update_menu_visibility()
        if treeselection == self.current.get_selection():
            # User previously clicked inside group of selected rows, re-select
            # rows so it doesn't look like anything changed:
            if self.current.sel_rows:
                for row in self.current.sel_rows:
                    treeselection.select_path(row)
        # Update lib artwork
        self.library.on_library_scrolled(None, None)

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
        self.current.sel_rows = None
        if event.button == 1 and widget_is_current and not ctrl_press:
            # If the user clicked inside a group of rows that were already selected,
            # we need to retain the selected rows in case the user wants to DND the
            # group of rows. If they release the mouse without first moving it,
            # then we revert to the single selected row. This is similar to the
            # behavior found in thunar.
            try:
                path, col, x, y = widget.get_path_at_pos(int(event.x), int(event.y))
                if widget.get_selection().path_is_selected(path):
                    self.current.sel_rows = widget.get_selection().get_selected_rows()[1]
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

    def on_add_item_play(self, widget):
        self.on_add_item(widget, True)

    def on_add_item(self, _widget, play_after=False):
        if self.conn:
            if play_after and self.status:
                playid = self.status['playlistlength']
            if self.current_tab == self.TAB_LIBRARY:
                items = self.library.get_path_child_filenames(True)
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

    def menu_position(self, _menu):
        if self.config.expanded:
            x, y, width, height = self.current_treeview.get_allocation()
            # Find first selected visible row and popup the menu
            # from there
            if self.current_tab == self.TAB_CURRENT:
                widget = self.current_treeview
                column = self.current.columns[0]
            elif self.current_tab == self.TAB_LIBRARY:
                widget = self.library_treeview
                column = self.library.librarycolumn
            elif self.current_tab == self.TAB_PLAYLISTS:
                widget = self.playlists_treeview
                column = self.playlists.playlistscolumn
            elif self.current_tab == self.TAB_STREAMS:
                widget = self.streams_treeview
                column = self.streams.streamscolumn
            rows = widget.get_selection().get_selected_rows()[1]
            visible_rect = widget.get_visible_rect()
            row_y = 0
            for row in rows:
                row_rect = widget.get_background_area(row, column)
                if row_rect.y + row_rect.height <= visible_rect.height and row_rect.y >= 0:
                    row_y = row_rect.y + 30
                    break
            return (self.config.x + width - 150, self.config.y + y + row_y, True)
        else:
            return (self.config.x + 250, self.config.y + 80, True)

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
            prevstatus_playlist = None
            if self.prevstatus:
                prevstatus_playlist = self.prevstatus['playlist']
            self.current.current_update(prevstatus_playlist, self.status['playlistlength'])

        # Update progress frequently if we're playing
        if self.status['state'] in ['play', 'pause']:
            self.update_progressbar()

        # If elapsed time is shown in the window title, we need to update more often:
        if "%E" in self.config.titleformat:
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
                self.current.center_song_in_list()

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
            if mpdh.mpd_is_updating(self.status):
                # MPD library is being updated
                self.update_statusbar(True)
            elif self.prevstatus == None or mpdh.mpd_is_updating(self.prevstatus) != mpdh.mpd_is_updating(self.status):
                if not mpdh.mpd_is_updating(self.status):
                    # Done updating, refresh interface
                    self.mpd_updated_db()
            elif self.mpd_update_queued:
                # If the update happens too quickly, we won't catch it in
                # our polling. So let's force an update of the interface:
                self.mpd_updated_db()
        self.mpd_update_queued = False

        if self.config.as_enabled:
            playing = self.status and self.status['state'] == 'play'
            stopped = self.status and self.status['state'] == 'stop'

            if playing:
                mpd_time_now = self.status['time']
                switched_from_stop_to_play = not self.prevstatus or (self.prevstatus and self.prevstatus['state'] == 'stop')

                self.scrobbler.handle_change_status(True, self.prevsonginfo, self.songinfo, switched_from_stop_to_play, mpd_time_now)
            elif stopped:
                self.scrobbler.handle_change_status(False, self.prevsonginfo)

    def mpd_updated_db(self):
        self.library.view_caches_reset()
        self.update_statusbar(False)
        # We need to make sure that we update the artist in case tags have changed:
        self.album_reset_artist()
        self.album_get_artist()
        # Now update the library and playlist tabs
        if self.library.search_visible():
            self.library.on_library_search_combo_change()
        else:
            self.library.library_browse(root=self.config.wd)
        self.playlists.populate()
        # Update info if it's visible:
        self.info_update(True)
        return False

    def album_get_artist(self):
        if self.songinfo and 'album' in self.songinfo:
            self.album_return_artist_name()
        elif self.songinfo and 'artist' in self.songinfo:
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
        self.current.unbold_boldrow(self.current.prev_boldrow)

        if self.status and 'song' in self.status:
            row = int(self.status['song'])
            self.current.boldrow(row)
            if self.songinfo:
                if not self.prevsonginfo or mpdh.get(self.songinfo, 'file') != mpdh.get(self.prevsonginfo, 'file'):
                    self.current.center_song_in_list()
            self.current.prev_boldrow = row

        self.album_get_artist()

        self.update_cursong()
        self.update_wintitle()
        self.artwork.artwork_update()
        self.info_update(True)

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

    def update_statusbar(self, updatingdb=False):
        if self.config.show_statusbar:
            if self.conn and self.status:
                try:
                    days = None
                    hours = None
                    mins = None
                    total_time = misc.convert_time(self.current.total_time)
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

    def get_current_song_text(self):
        return self.cursonglabel1.get_text(), self.cursonglabel2.get_text()

    def update_cursong(self):
        if self.conn and self.status and self.status['state'] in ['play', 'pause']:
            # We must show the trayprogressbar and trayalbumeventbox
            # before changing self.cursonglabel (and consequently calling
            # self.on_currsong_notify()) in order to ensure that the notification
            # popup will have the correct height when being displayed for
            # the first time after a stopped state.
            if self.config.show_progress:
                self.trayprogressbar.show()
            self.traycursonglabel2.show()
            if self.config.show_covers:
                self.trayalbumeventbox.show()
                self.trayalbumimage2.show()

            for label in (self.cursonglabel1, self.cursonglabel2, self.traycursonglabel1, self.traycursonglabel2):
                label.set_ellipsize(pango.ELLIPSIZE_END)

            self.expander_ellipse_workaround()

            if len(self.config.currsongformat1) > 0:
                newlabel1 = '<big><b>' + self.parse_formatting(self.config.currsongformat1, self.songinfo, True) + ' </b></big>'
            else:
                newlabel1 = '<big><b> </b></big>'
            if len(self.config.currsongformat2) > 0:
                newlabel2 = '<small>' + self.parse_formatting(self.config.currsongformat2, self.songinfo, True) + ' </small>'
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
            if self.config.expanded:
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
                newtitle = self.parse_formatting(self.config.titleformat, self.songinfo, False, True)
            else:
                newtitle = '[Sonata]'
            if not self.last_title or self.last_title != newtitle:
                self.window.set_property('title', newtitle)
                self.last_title = newtitle

    def set_allow_art_search(self):
        self.allow_art_search = True

    def status_is_play_or_pause(self):
        return self.conn and self.status and self.status['state'] in ['play', 'pause']

    def connected(self):
        return self.conn

    def tooltip_set_window_width(self):
        screen = self.window.get_screen()
        pointer_screen, px, py, _ = screen.get_display().get_pointer()
        monitor_num = screen.get_monitor_at_point(px, py)
        monitor = screen.get_monitor_geometry(monitor_num)
        self.notification_width = int(monitor.width * 0.30)
        if self.notification_width > consts.NOTIFICATION_WIDTH_MAX:
            self.notification_width = consts.NOTIFICATION_WIDTH_MAX
        elif self.notification_width < consts.NOTIFICATION_WIDTH_MIN:
            self.notification_width = consts.NOTIFICATION_WIDTH_MIN

    def on_currsong_notify(self, _foo=None, _bar=None, force_popup=False):
        if self.fullscreencoverart.get_property('visible'):
            return
        if self.sonata_loaded:
            if self.conn and self.status and self.status['state'] in ['play', 'pause']:
                if self.config.show_covers:
                    self.traytips.set_size_request(self.notification_width, -1)
                else:
                    self.traytips.set_size_request(self.notification_width-100, -1)
            else:
                self.traytips.set_size_request(-1, -1)
            if self.config.show_notification or force_popup:
                try:
                    gobject.source_remove(self.traytips.notif_handler)
                except:
                    pass
                if self.conn and self.status and self.status['state'] in ['play', 'pause']:
                    try:
                        self.traytips.notifications_location = self.config.traytips_notifications_location
                        self.traytips.use_notifications_location = True
                        if HAVE_STATUS_ICON and self.statusicon.is_embedded() and self.statusicon.get_visible():
                            self.traytips._real_display(self.statusicon)
                        elif HAVE_EGG and self.trayicon.get_property('visible'):
                            self.traytips._real_display(self.trayeventbox)
                        else:
                            self.traytips._real_display(None)
                        if self.config.popup_option != len(self.popuptimes)-1:
                            if force_popup and not self.config.show_notification:
                                # Used -p argument and notification is disabled in
                                # player; default to 3 seconds
                                timeout = 3000
                            else:
                                timeout = int(self.popuptimes[self.config.popup_option])*1000
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

    def on_progressbar_notify_fraction(self, *_args):
        self.trayprogressbar.set_fraction(self.progressbar.get_fraction())

    def on_progressbar_notify_text(self, *_args):
        self.trayprogressbar.set_text(self.progressbar.get_text())

    def update_infofile(self):
        if self.config.use_infofile is True:
            try:
                info_file = open(self.config.infofile_path, 'w')

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

    def on_delete_event_yes(self, _widget):
        self.exit_now = True
        self.on_delete_event(None, None)

    # This one makes sure the program exits when the window is closed
    def on_delete_event(self, _widget, _data=None):
        if not self.exit_now and self.config.minimize_to_systray:
            if HAVE_STATUS_ICON and self.statusicon.is_embedded() and self.statusicon.get_visible():
                self.withdraw_app()
                return True
            elif HAVE_EGG and self.trayicon.get_property('visible'):
                self.withdraw_app()
                return True
        self.settings_save()
        self.artwork.artwork_save_cache()
        if self.config.as_enabled:
            self.scrobbler.save_cache()
        if self.conn and self.config.stop_on_exit:
            self.mpd_stop(None)
        sys.exit()

    def on_window_state_change(self, _widget, _event):
        self.volume_hide()

    def on_window_lost_focus(self, _widget, _event):
        self.volume_hide()

    def on_window_configure(self, _widget, _event):
        width, height = self.window.get_size()
        if self.config.expanded: self.config.w, self.config.h = width, height
        else: self.config.w = width
        self.config.x, self.config.y = self.window.get_position()
        self.expander_ellipse_workaround()

    def on_notebook_resize(self, _widget, _event):
        if not self.current.resizing_columns :
            gobject.idle_add(self.header_save_column_widths)
        gobject.idle_add(self.info.resize_elements, self.notebook.allocation)

    def on_expand(self, _action):
        if not self.config.expanded:
            self.expander.set_expanded(False)
            self.on_expander_activate(None)
            self.expander.set_expanded(True)

    def on_collapse(self, _action):
        if self.config.expanded:
            self.expander.set_expanded(True)
            self.on_expander_activate(None)
            self.expander.set_expanded(False)

    def on_expander_activate(self, _expander):
        currheight = self.window.get_size()[1]
        self.config.expanded = False
        # Note that get_expanded() will return the state of the expander
        # before this current click
        window_about_to_be_expanded = not self.expander.get_expanded()
        if window_about_to_be_expanded:
            if self.window.get_size()[1] == self.config.h:
                # For WMs like ion3, the app will not actually resize
                # when in collapsed mode, so prevent the waiting
                # of the player to expand from happening:
                skip_size_check = True
            else:
                skip_size_check = False
            if self.config.show_statusbar:
                self.statusbar.show()
            self.notebook.show_all()
            if self.config.show_statusbar:
                ui.show(self.statusbar)
        else:
            ui.hide(self.statusbar)
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
                self.window.resize(self.config.w, self.config.h)
            else:
                self.window.resize(self.config.w, 1)
        if window_about_to_be_expanded:
            self.config.expanded = True
            if self.status and self.status['state'] in ['play','pause']:
                gobject.idle_add(self.current.center_song_in_list)
            self.window.set_geometry_hints(self.window)
        if self.notebook_show_first_tab:
            # Sonata was launched in collapsed state. Ensure we display
            # first tab:
            self.notebook_show_first_tab = False
            self.notebook.set_current_page(0)
        # Put focus to the notebook:
        self.on_notebook_page_change(self.notebook, 0, self.notebook.get_current_page())

    # This callback allows the user to seek to a specific portion of the song
    def on_progressbar_press(self, _widget, event):
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

    def on_progressbar_scroll(self, _widget, event):
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
                seektime = int(self.status['time'].split(":")[0]) + 5
                if seektime < 0: seektime = 0
            elif direction == gtk.gdk.SCROLL_DOWN:
                seektime = int(self.status['time'].split(":")[0]) - 5
                if seektime > mpdh.get(self.songinfo, 'time'):
                    seektime = mpdh.get(self.songinfo, 'time')
            self.seek(int(self.status['song']), seektime)
        except:
            pass

    def on_lyrics_search(self, _event):
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
            filename = self.info.target_lyrics_filename(artist, title, None, consts.LYRICS_LOCATION_HOME)
            misc.remove_file(filename)
            # Search for new lyrics:
            self.info.get_lyrics_start(artist_entry.get_text(), title_entry.get_text(), artist, title, os.path.dirname(mpdh.get(self.songinfo, 'file')))
        else:
            dialog.destroy()

    def mpd_shuffle(self, _action):
        if self.conn:
            if not self.status or self.status['playlistlength'] == '0':
                return
            ui.change_cursor(gtk.gdk.Cursor(gtk.gdk.WATCH))
            while gtk.events_pending():
                gtk.main_iteration()
            mpdh.call(self.client, 'shuffle')

    def on_menu_popup(self, _widget):
        self.update_menu_visibility()
        gobject.idle_add(self.mainmenu.popup, None, None, self.menu_position, 3, 0)

    def on_updatedb(self, _action):
        if self.conn:
            if self.library.search_visible():
                self.library.on_search_end(None)
            mpdh.update(self.client, '/', self.status)
            self.mpd_update_queued = True

    def on_updatedb_shortcut(self, _action):
        # If no songs selected, update view. Otherwise update
        # selected items.
        if self.library.not_parent_is_selected():
            self.on_updatedb_path(True)
        else:
            self.on_updatedb_path(False)

    def on_updatedb_path(self, selected_only):
        if self.conn and self.current_tab == self.TAB_LIBRARY:
            if self.library.search_visible():
                self.library.on_search_end(None)
            filenames = self.library.get_path_child_filenames(True, selected_only)
            if len(filenames) > 0:
                mpdh.update(self.client, filenames, self.status)
                self.mpd_update_queued = True

    def on_image_activate(self, widget, event):
        self.window.handler_block(self.mainwinhandler)
        if event.button == 1 and widget == self.info_imagebox and self.artwork.have_last():
            if not self.config.info_art_enlarged:
                self.info_imagebox.set_size_request(-1,-1)
                self.artwork.artwork_set_image_last()
                self.config.info_art_enlarged = True
            else:
                self.info_imagebox.set_size_request(152, -1)
                self.artwork.artwork_set_image_last()
                self.config.info_art_enlarged = False
            self.volume_hide()
            # Force a resize of the info labels, if needed:
            gobject.idle_add(self.on_notebook_resize, self.notebook, None)
        elif event.button == 1 and widget != self.info_imagebox:
            if self.config.expanded:
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
                self.UIManager.get_widget('/imagemenu/chooseimage_menu/').show()
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

    def on_image_motion_cb(self, _widget, context, _x, _y, time):
        context.drag_status(gtk.gdk.ACTION_COPY, time)
        return True

    def on_image_drop_cb(self, _widget, _context, _x, _y, selection, _info, _time):
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
                art_loc = self.config.art_location
            if art_loc == consts.ART_LOCATION_HOMECOVERS:
                targetfile = os.path.expanduser("~/.covers/" + artist + "-" + album + ".jpg")
            elif art_loc == consts.ART_LOCATION_COVER:
                targetfile = self.config.musicdir[self.config.profile_num] + songpath + "/cover.jpg"
            elif art_loc == consts.ART_LOCATION_FOLDER:
                targetfile = self.config.musicdir[self.config.profile_num] + songpath + "/folder.jpg"
            elif art_loc == consts.ART_LOCATION_ALBUM:
                targetfile = self.config.musicdir[self.config.profile_num] + songpath + "/album.jpg"
            elif art_loc == consts.ART_LOCATION_CUSTOM:
                targetfile = self.config.musicdir[self.config.profile_num] + songpath + "/" + self.config.art_location_custom_filename
            targetfile = misc.file_exists_insensitive(targetfile)
            return misc.file_from_utf8(targetfile)

    def album_return_artist_and_tracks(self):
        # Includes logic for Various Artists albums to determine
        # the tracks.
        datalist = []
        album = mpdh.get(self.songinfo, 'album')
        songs, playtime, num_songs = self.library.library_return_search_items(album=album)
        for song in songs:
            year = mpdh.get(song, 'date', '')
            artist = mpdh.get(song, 'artist', '')
            path = os.path.dirname(mpdh.get(song, 'file'))
            data = library.library_set_data(album=album, artist=artist, year=year, path=path)
            datalist.append(data)
        if len(datalist) > 0:
            datalist = misc.remove_list_duplicates(datalist, case=False)
            datalist = self.library.list_identify_VA_albums(datalist)
            # Find all songs in album:
            retsongs = []
            for song in songs:
                if unicode(mpdh.get(song, 'album')).lower() == unicode(library.library_get_data(datalist[0], 'album')).lower() \
                and mpdh.get(song, 'date', '') == library.library_get_data(datalist[0], 'year'):
                    retsongs.append(song)

            artist = library.library_get_data(datalist[0], 'artist')
            return artist, retsongs
        else:
            return None, None

    def album_return_artist_name(self):
        # Determine if album_name is a various artists album.
        if self.album_current_artist[0] == self.songinfo:
            return
        artist, tracks = self.album_return_artist_and_tracks()
        if artist is not None:
            self.album_current_artist = [self.songinfo, artist]
        else:
            self.album_current_artist = [self.songinfo, ""]

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

    def image_local(self, _widget):
        dialog = gtk.FileChooserDialog(title=_("Open Image"),action=gtk.FILE_CHOOSER_ACTION_OPEN,buttons=(gtk.STOCK_CANCEL,gtk.RESPONSE_CANCEL,gtk.STOCK_OPEN,gtk.RESPONSE_OK))
        filefilter = gtk.FileFilter()
        filefilter.set_name(_("Images"))
        filefilter.add_pixbuf_formats()
        dialog.add_filter(filefilter)
        filefilter = gtk.FileFilter()
        filefilter.set_name(_("All files"))
        filefilter.add_pattern("*")
        dialog.add_filter(filefilter)
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
        currdir = misc.file_from_utf8(self.config.musicdir[self.config.profile_num] + songdir)
        if self.config.art_location != consts.ART_LOCATION_HOMECOVERS:
            dialog.set_current_folder(currdir)
        if stream is not None:
            # Allow saving an image file for a stream:
            self.local_dest_filename = self.artwork.artwork_stream_filename(stream)
        else:
            self.local_dest_filename = self.target_image_filename()
        dialog.show()

    def image_local_response(self, dialog, response, _artist, _album, _stream):
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

    def image_remote(self, _widget):
        self.choose_dialog = ui.dialog(title=_("Choose Cover Art"), parent=self.window, flags=gtk.DIALOG_MODAL, buttons=(gtk.STOCK_CANCEL, gtk.RESPONSE_REJECT), role='chooseCoverArt', default=gtk.RESPONSE_ACCEPT, separator=False, resizable=False)
        choosebutton = self.choose_dialog.add_button(_("C_hoose"), gtk.RESPONSE_ACCEPT)
        chooseimage = ui.image(stock=gtk.STOCK_CONVERT, stocksize=gtk.ICON_SIZE_BUTTON)
        choosebutton.set_image(chooseimage)
        self.imagelist = gtk.ListStore(int, gtk.gdk.Pixbuf)
        # Setting col=2 only shows 1 column with gtk 2.16 while col=-1 shows 2
        imagewidget = ui.iconview(col=-1, space=0, margin=0, itemw=75, selmode=gtk.SELECTION_SINGLE)
        scroll = ui.scrollwindow(policy_x=gtk.POLICY_NEVER, policy_y=gtk.POLICY_ALWAYS, w=360, h=325, add=imagewidget)
        self.choose_dialog.vbox.pack_start(scroll, False, False, 0)
        hbox = gtk.HBox()
        vbox = gtk.VBox()
        vbox.pack_start(ui.label(markup='<small> </small>'), False, False, 0)
        self.remote_artistentry = ui.entry()
        self.remote_albumentry = ui.entry()
        text = [("Artist"), _("Album")]
        labels = [ui.label(text=labelname + ": ") for labelname in text]
        entries = [self.remote_artistentry, self.remote_albumentry]
        for entry, label in zip(entries, labels):
            tmphbox = gtk.HBox()
            tmphbox.pack_start(label, False, False, 5)
            entry.connect('activate', self.image_remote_refresh, imagewidget)
            tmphbox.pack_start(entry, True, True, 5)
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

    def image_remote_refresh(self, _entry, imagewidget):
        if not self.allow_art_search:
            return
        self.allow_art_search = False
        self.artwork.artwork_stop_update()
        while self.artwork.artwork_is_downloading_image():
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

    def _image_remote_refresh(self, imagewidget, _ignore):
        self.artwork.stop_art_update = False
        # Retrieve all images from amazon:
        artist_search = self.remote_artistentry.get_text()
        album_search = self.remote_albumentry.get_text()
        if len(artist_search) == 0 and len(album_search) == 0:
            gobject.idle_add(self.image_remote_no_tag_found, imagewidget)
            return
        filename = os.path.expanduser("~/.covers/temp/<imagenum>.jpg")
        misc.remove_dir_recursive(os.path.dirname(filename))
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
        self.artwork.artwork_stop_update()
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

    def image_remote_replace_cover(self, _iconview, path, _artist, _album, _stream):
        self.artwork.artwork_stop_update()
        image_num = int(path[0])
        if len(self.remotefilelist) > 0:
            filename = self.remotefilelist[image_num]
            if os.path.exists(filename):
                shutil.move(filename, self.remote_dest_filename)
                # And finally, set the image in the interface:
                self.artwork.artwork_update(True)
                # Clean up..
                misc.remove_dir_recursive(os.path.dirname(filename))
        self.chooseimage_visible = False
        self.choose_dialog.destroy()
        while self.artwork.artwork_is_downloading_image():
            gtk.main_iteration()

    def fullscreen_cover_art(self, _widget):
        if self.fullscreencoverart.get_property('visible'):
            self.fullscreencoverart.hide()
        else:
            self.traytips.hide()
            self.artwork.fullscreen_cover_art_set_image(force_update=True)
            self.fullscreencoverart.show_all()

    def fullscreen_cover_art_close(self, _widget, event, key_press):
        if key_press:
            shortcut = gtk.accelerator_name(event.keyval, event.state)
            shortcut = shortcut.replace("<Mod2>", "")
            if shortcut != 'Escape':
                return
        self.fullscreencoverart.hide()

    def header_save_column_widths(self):
        if not self.config.withdrawn and self.config.expanded:
            windowwidth = self.window.allocation.width
            if windowwidth <= 10 or self.current.columns[0].get_width() <= 10:
                # Make sure we only set self.config.columnwidths if self.current
                # has its normal allocated width:
                return
            notebookwidth = self.notebook.allocation.width
            treewidth = 0
            for i, column in enumerate(self.current.columns):
                colwidth = column.get_width()
                treewidth += colwidth
                if i == len(self.current.columns)-1 and treewidth <= windowwidth:
                    self.config.columnwidths[i] = min(colwidth, column.get_fixed_width())
                else:
                    self.config.columnwidths[i] = colwidth
            if treewidth > notebookwidth:
                self.current.expanderwindow.set_policy(gtk.POLICY_AUTOMATIC, gtk.POLICY_AUTOMATIC)
            else:
                self.current.expanderwindow.set_policy(gtk.POLICY_NEVER, gtk.POLICY_AUTOMATIC)
        self.current.resizing_columns = False

    def systemtray_menu(self, status_icon, button, activate_time):
        self.traymenu.popup(None, None, gtk.status_icon_position_menu, button, activate_time, status_icon)

    def systemtray_activate(self, _status_icon):
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
                # and sonata is started with self.config.withdrawn = True
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

    def systemtray_click(self, _widget, event):
        # Clicking on an egg system tray icon:
        if event.button == 1 and not self.ignore_toggle_signal: # Left button shows/hides window(s)
            self.systemtray_activate(None)
        elif event.button == 2: # Middle button will play/pause
            if self.conn:
                self.mpd_pp(self.trayeventbox)
        elif event.button == 3: # Right button pops up menu
            self.traymenu.popup(None, None, None, event.button, event.time)
        return False

    def on_traytips_press(self, _widget, _event):
        if self.traytips.get_property('visible'):
            self.traytips._remove_timer()

    def withdraw_app_undo(self):
        self.window.move(self.config.x, self.config.y)
        if not self.config.expanded:
            self.notebook.set_no_show_all(True)
            self.statusbar.set_no_show_all(True)
        self.window.show_all()
        self.notebook.set_no_show_all(False)
        self.config.withdrawn = False
        self.UIManager.get_widget('/traymenu/showmenu').set_active(True)
        if self.notebook_show_first_tab and self.config.expanded:
            # Sonata was launched in withdrawn state. Ensure we display
            # first tab:
            self.notebook_show_first_tab = False
            self.notebook.set_current_page(0)
        gobject.idle_add(self.withdraw_app_undo_present_and_focus)

    def withdraw_app_undo_present_and_focus(self):
        self.window.present() # Helps to raise the window (useful against focus stealing prevention)
        self.window.grab_focus()
        if self.config.sticky:
            self.window.stick()
        if self.config.ontop:
            self.window.set_keep_above(True)

    def withdraw_app(self):
        if HAVE_EGG or HAVE_STATUS_ICON:
            # Save the playlist column widths before withdrawing the app.
            # Otherwise we will not be able to correctly save the column
            # widths if the user quits sonata while it is withdrawn.
            self.header_save_column_widths()
            self.window.hide()
            self.config.withdrawn = True
            self.UIManager.get_widget('/traymenu/showmenu').set_active(False)

    def on_withdraw_app_toggle(self, _action):
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

    def systemtray_size(self, widget, _allocation):
        if widget.allocation.height <= 5:
            # For vertical panels, height can be 1px, so use width
            size = widget.allocation.width
        else:
            size = widget.allocation.height
        if not self.eggtrayheight or self.eggtrayheight != size:
            self.eggtrayheight = size
            if size > 5 and self.eggtrayfile:
                self.trayimage.set_from_pixbuf(img.get_pixbuf_of_size(gtk.gdk.pixbuf_new_from_file(self.eggtrayfile), self.eggtrayheight)[0])

    def switch_to_tab_name(self, tab_name):
        self.notebook.set_current_page(self.notebook_get_tab_num(self.notebook, tab_name))

    def switch_to_tab_num(self, tab_num):
        vis_tabnum = self.notebook_get_visible_tab_num(self.notebook, tab_num)
        if vis_tabnum != -1:
            self.notebook.set_current_page(vis_tabnum)

    def on_switch_to_tab1(self, _action):
        self.switch_to_tab_num(0)

    def on_switch_to_tab2(self, _action):
        self.switch_to_tab_num(1)

    def on_switch_to_tab3(self, _action):
        self.switch_to_tab_num(2)

    def on_switch_to_tab4(self, _action):
        self.switch_to_tab_num(3)

    def on_switch_to_tab5(self, _action):
        self.switch_to_tab_num(4)

    def switch_to_next_tab(self, _action):
        self.notebook.next_page()

    def switch_to_prev_tab(self, _action):
        self.notebook.prev_page()

    def on_volume_lower(self, _action):
        new_volume = int(self.volumescale.get_adjustment().get_value()) - 5
        if new_volume < 0:
            new_volume = 0
        self.volumescale.get_adjustment().set_value(new_volume)
        self.on_volumescale_change(self.volumescale, 0, 0)

    def on_volume_raise(self, _action):
        new_volume = int(self.volumescale.get_adjustment().get_value()) + 5
        if new_volume > 100:
            new_volume = 100
        self.volumescale.get_adjustment().set_value(new_volume)
        self.on_volumescale_change(self.volumescale, 0, 0)

    # Volume control
    def on_volumebutton_clicked(self, _widget):
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

    def on_volumebutton_scroll(self, _widget, event):
        if self.conn:
            if event.direction == gtk.gdk.SCROLL_UP:
                self.on_volume_raise(None)
            elif event.direction == gtk.gdk.SCROLL_DOWN:
                self.on_volume_lower(None)

    def on_volumescale_scroll(self, _widget, event):
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

    def on_volumescale_change(self, obj, _value, _data):
        new_volume = int(obj.get_adjustment().get_value())
        mpdh.call(self.client, 'setvol', new_volume)
        self.iterate_now()

    def volume_hide(self):
        self.volumebutton.set_active(False)
        if self.volumewindow.get_property('visible'):
            self.volumewindow.hide()

    def mpd_pp(self, _widget, _key=None):
        if self.conn and self.status:
            if self.status['state'] in ('stop', 'pause'):
                mpdh.call(self.client, 'play')
            elif self.status['state'] == 'play':
                mpdh.call(self.client, 'pause', '1')
            self.iterate_now()

    def mpd_stop(self, _widget, _key=None):
        if self.conn:
            mpdh.call(self.client, 'stop')
            self.iterate_now()

    def mpd_prev(self, _widget, _key=None):
        if self.conn:
            mpdh.call(self.client, 'previous')
            self.iterate_now()

    def mpd_next(self, _widget, _key=None):
        if self.conn:
            mpdh.call(self.client, 'next')
            self.iterate_now()

    def on_remove(self, _widget):
        if self.conn:
            model = None
            while gtk.events_pending():
                gtk.main_iteration()
            if self.current_tab == self.TAB_CURRENT:
                self.current.on_remove()
            elif self.current_tab == self.TAB_PLAYLISTS:
                treeviewsel = self.playlists_selection
                model, selected = treeviewsel.get_selected_rows()
                if ui.show_msg(self.window, gettext.ngettext("Delete the selected playlist?", "Delete the selected playlists?", int(len(selected))), gettext.ngettext("Delete Playlist", "Delete Playlists", int(len(selected))), 'deletePlaylist', gtk.BUTTONS_YES_NO) == gtk.RESPONSE_YES:
                    iters = [model.get_iter(path) for path in selected]
                    for i in iters:
                        mpdh.call(self.client, 'rm', misc.unescape_html(self.playlistsdata.get_value(i, 1)))
                    self.playlists.populate()
            elif self.current_tab == self.TAB_STREAMS:
                treeviewsel = self.streams_selection
                model, selected = treeviewsel.get_selected_rows()
                if ui.show_msg(self.window, gettext.ngettext("Delete the selected stream?", "Delete the selected streams?", int(len(selected))), gettext.ngettext("Delete Stream", "Delete Streams", int(len(selected))), 'deleteStreams', gtk.BUTTONS_YES_NO) == gtk.RESPONSE_YES:
                    iters = [model.get_iter(path) for path in selected]
                    for i in iters:
                        stream_removed = False
                        for j in range(len(self.config.stream_names)):
                            if not stream_removed:
                                if self.streamsdata.get_value(i, 1) == misc.escape_html(self.config.stream_names[j]):
                                    self.config.stream_names.pop(j)
                                    self.config.stream_uris.pop(j)
                                    stream_removed = True
                    self.streams.populate()
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

    def mpd_clear(self, _widget):
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

    def on_prefs(self, _widget):
        trayicon_available = HAVE_EGG or HAVE_STATUS_ICON
        trayicon_in_use = ((HAVE_STATUS_ICON and self.statusicon.is_embedded() and
                    self.statusicon.get_visible())
                   or (HAVE_EGG and self.trayicon.get_property('visible')))
        self.preferences.on_prefs_real(self.window, self.popuptimes, self.scrobbler, trayicon_available, trayicon_in_use, self.on_connectkey_pressed, self.on_currsong_notify, self.update_infofile, self.prefs_notif_toggled, self.prefs_stylized_toggled, self.prefs_art_toggled, self.prefs_playback_toggled, self.prefs_progress_toggled, self.prefs_statusbar_toggled, self.prefs_lyrics_toggled, self.prefs_trayicon_toggled, self.prefs_crossfade_toggled, self.prefs_crossfade_changed, self.prefs_window_response, self.prefs_last_tab, self.prefs_currentoptions_changed, self.prefs_libraryoptions_changed, self.prefs_titleoptions_changed, self.prefs_currsongoptions1_changed, self.prefs_currsongoptions2_changed)

    def prefs_currentoptions_changed(self, entry, _event):
        if self.config.currentformat != entry.get_text():
            self.config.currentformat = entry.get_text()
            for column in self.current_treeview.get_columns():
                self.current_treeview.remove_column(column)
            self.current.initialize_columns()
            self.current.update_format()

    def prefs_libraryoptions_changed(self, entry, _event):
        if self.config.libraryformat != entry.get_text():
            self.config.libraryformat = entry.get_text()
            self.library.library_browse(root=self.config.wd)

    def prefs_titleoptions_changed(self, entry, _event):
        if self.config.titleformat != entry.get_text():
            self.config.titleformat = entry.get_text()
            self.update_wintitle()

    def prefs_currsongoptions1_changed(self, entry, _event):
        if self.config.currsongformat1 != entry.get_text():
            self.config.currsongformat1 = entry.get_text()
            self.update_cursong()

    def prefs_currsongoptions2_changed(self, entry, _event):
        if self.config.currsongformat2 != entry.get_text():
            self.config.currsongformat2 = entry.get_text()
            self.update_cursong()

    # XXX move the prefs handling parts of prefs_* to preferences.py
    def prefs_window_response(self, window, response, prefsnotebook, direntry, infopath_options, using_mpd_env_vars, prev_host, prev_port, prev_password):
        if response == gtk.RESPONSE_CLOSE:
            self.prefs_last_tab = prefsnotebook.get_current_page()
            if self.config.show_lyrics and self.config.lyrics_location != consts.LYRICS_LOCATION_HOME:
                if not os.path.isdir(misc.file_from_utf8(self.config.musicdir[self.config.profile_num])):
                    ui.show_msg(self.window, _("To save lyrics to the music file's directory, you must specify a valid music directory."), _("Music Dir Verification"), 'musicdirVerificationError', gtk.BUTTONS_CLOSE)
                    # Set music_dir entry focused:
                    prefsnotebook.set_current_page(0)
                    direntry.grab_focus()
                    return
            if self.config.show_covers and self.config.art_location != consts.ART_LOCATION_HOMECOVERS:
                if not os.path.isdir(misc.file_from_utf8(self.config.musicdir[self.config.profile_num])):
                    ui.show_msg(self.window, _("To save artwork to the music file's directory, you must specify a valid music directory."), _("Music Dir Verification"), 'musicdirVerificationError', gtk.BUTTONS_CLOSE)
                    # Set music_dir entry focused:
                    prefsnotebook.set_current_page(0)
                    direntry.grab_focus()
                    return
            if self.window_owner:
                if self.config.ontop:
                    self.window.set_keep_above(True)
                else:
                    self.window.set_keep_above(False)
                if self.config.sticky:
                    self.window.stick()
                else:
                    self.window.unstick()
                if self.config.decorated != self.window.get_decorated():
                    self.withdraw_app()
                    self.window.set_decorated(self.config.decorated)
                    self.withdraw_app_undo()
            if self.config.infofile_path != infopath_options.get_text():
                self.config.infofile_path = os.path.expanduser(infopath_options.get_text())
                if self.config.use_infofile: self.update_infofile()
            if not using_mpd_env_vars:
                if prev_host != self.config.host[self.config.profile_num] or prev_port != self.config.port[self.config.profile_num] or prev_password != self.config.password[self.config.profile_num]:
                    # Try to connect if mpd connection info has been updated:
                    ui.change_cursor(gtk.gdk.Cursor(gtk.gdk.WATCH))
                    self.mpd_connect(force=True)
            if self.config.as_enabled:
                gobject.idle_add(self.scrobbler.init)
            self.settings_save()
            self.populate_profiles_for_menu()
            ui.change_cursor(None)
        window.destroy()

    def prefs_crossfade_changed(self, crossfade_spin):
        crossfade_value = crossfade_spin.get_value_as_int()
        mpdh.call(self.client, 'crossfade', crossfade_value)

    def prefs_crossfade_toggled(self, button, crossfade_spin):
        crossfade_value = crossfade_spin.get_value_as_int()
        if button.get_active():
            mpdh.call(self.client, 'crossfade', crossfade_value)
        else:
            mpdh.call(self.client, 'crossfade', 0)

    def prefs_playback_toggled(self, button):
        self.config.show_playback = button.get_active()
        func = 'show' if self.config.show_playback else 'hide'
        for widget in [self.prevbutton, self.ppbutton, self.stopbutton, self.nextbutton, self.volumebutton]:
            getattr(ui, func)(widget)

    def prefs_progress_toggled(self, button):
        self.config.show_progress = button.get_active()
        func = 'show' if self.config.show_progress else 'hide'
        for widget in [self.progressbox, self.trayprogressbar]:
            getattr(ui,func)(widget)

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
            self.config.show_covers = True
            self.update_cursong()
            self.artwork.artwork_update()
        else:
            self.traytips.set_size_request(self.notification_width-100, -1)
            for widget in [self.imageeventbox, self.info_imagebox, self.trayalbumeventbox, self.trayalbumimage2]:
                ui.hide(widget)
            self.config.show_covers = False
            self.update_cursong()

        # Force a resize of the info labels, if needed:
        gobject.idle_add(self.on_notebook_resize, self.notebook, None)

    def prefs_stylized_toggled(self, button):
        self.config.covers_type = button.get_active()
        self.artwork.artwork_update(True)

    def prefs_lyrics_toggled(self, button, lyrics_hbox):
        self.config.show_lyrics = button.get_active()
        lyrics_hbox.set_sensitive(self.config.show_lyrics)
        self.info.show_lyrics_updated()
        if self.config.show_lyrics:
            self.info_update(True)

    def prefs_statusbar_toggled(self, button):
        self.config.show_statusbar = button.get_active()
        if self.config.show_statusbar:
            self.statusbar.set_no_show_all(False)
            if self.config.expanded:
                self.statusbar.show_all()
        else:
            ui.hide(self.statusbar)
        self.update_statusbar()

    def prefs_notif_toggled(self, button, notifhbox):
        self.config.show_notification = button.get_active()
        notifhbox.set_sensitive(self.config.show_notification)
        if self.config.show_notification:
            self.on_currsong_notify()
        else:
            try:
                gobject.source_remove(self.traytips.notif_handler)
            except:
                pass
            self.traytips.hide()

    def prefs_trayicon_toggled(self, button, minimize):
        # Note that we update the sensitivity of the minimize
        # CheckButton to reflect if the trayicon is visible.
        if button.get_active():
            self.config.show_trayicon = True
            if HAVE_STATUS_ICON:
                self.statusicon.set_visible(True)
                if self.statusicon.is_embedded() or self.statusicon.get_visible():
                    minimize.set_sensitive(True)
            elif HAVE_EGG:
                self.trayicon.show_all()
                if self.trayicon.get_property('visible'):
                    minimize.set_sensitive(True)
        else:
            self.config.show_trayicon = False
            minimize.set_sensitive(False)
            if HAVE_STATUS_ICON:
                self.statusicon.set_visible(False)
            elif HAVE_EGG:
                self.trayicon.hide_all()

    def seek(self, song, seektime):
        mpdh.call(self.client, 'seek', song, seektime)
        self.iterate_now()

    def on_link_click(self, type):
        browser_not_loaded = False
        if type == 'artist':
            browser_not_loaded = not misc.browser_load("http://www.wikipedia.org/wiki/Special:Search/" + urllib.quote(mpdh.get(self.songinfo, 'artist')), self.config.url_browser, self.window)
        elif type == 'album':
            browser_not_loaded = not misc.browser_load("http://www.wikipedia.org/wiki/Special:Search/" + urllib.quote(mpdh.get(self.songinfo, 'album')), self.config.url_browser, self.window)
        elif type == 'edit':
            if self.songinfo:
                self.on_tags_edit(None)
        elif type == 'search':
            self.on_lyrics_search(None)
        elif type == 'editlyrics':
            browser_not_loaded = not misc.browser_load(self.info.lyricwiki_editlink(self.songinfo), self.config.url_browser, self.window)
        if browser_not_loaded:
            ui.show_msg(self.window, _('Unable to launch a suitable browser.'), _('Launch Browser'), 'browserLoadError', gtk.BUTTONS_CLOSE)

    def on_tab_click(self, _widget, event):
        if event.button == 3:
            self.notebookmenu.popup(None, None, None, event.button, event.time)
            return True

    def on_notebook_click(self, _widget, event):
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

    def on_notebook_page_change(self, _notebook, _page, page_num):
        self.current_tab = self.notebook_get_tab_text(self.notebook, page_num)
        to_focus = self.tabname2focus.get(self.current_tab, None)
        if to_focus:
            gobject.idle_add(ui.focus, to_focus)

        gobject.idle_add(self.update_menu_visibility)
        if not self.img_clicked:
            self.last_tab = self.current_tab

    def on_library_search_text_click(self, _widget, event):
        if event.button == 1:
            self.volume_hide()

    def on_window_click(self, _widget, event):
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
            self.config.current_tab_visible = toggleAction.get_active()
        elif name == self.TAB_LIBRARY:
            self.config.library_tab_visible = toggleAction.get_active()
        elif name == self.TAB_PLAYLISTS:
            self.config.playlists_tab_visible = toggleAction.get_active()
        elif name == self.TAB_STREAMS:
            self.config.streams_tab_visible = toggleAction.get_active()
        elif name == self.TAB_INFO:
            self.config.info_tab_visible = toggleAction.get_active()
        # Hide/show:
        tabnum = self.notebook_get_tab_num(self.notebook, name)
        if toggleAction.get_active():
            ui.show(self.notebook.get_children()[tabnum])
        else:
            ui.hide(self.notebook.get_children()[tabnum])

    def on_library_search_shortcut(self, _event):
        # Ensure library tab is visible
        if not self.notebook_tab_is_visible(self.notebook, self.TAB_LIBRARY):
            return
        if self.current_tab != self.TAB_LIBRARY:
            self.switch_to_tab_name(self.TAB_LIBRARY)
        if self.library.search_visible():
            self.library.on_search_end(None)
        self.library.libsearchfilter_set_focus()

    def update_menu_visibility(self, show_songinfo_only=False):
        if show_songinfo_only or not self.config.expanded:
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
                if not self.current.filterbox_visible:
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
            if len(self.librarydata) > 0:
                if self.library_selection.count_selected_rows() > 0:
                    for menu in ['add', 'replace', 'playafter', 'tag']:
                        self.UIManager.get_widget('/mainmenu/' + menu + 'menu/').show()
                    self.UIManager.get_widget('/mainmenu/updatemenu/updateselectedmenu/').show()
                else:
                    for menu in ['add', 'replace', 'playafter', 'tag']:
                        self.UIManager.get_widget('/mainmenu/' + menu + 'menu/').hide()
                    self.UIManager.get_widget('/mainmenu/updatemenu/updateselectedmenu/').hide()
            else:
                for menu in ['add', 'replace', 'playafter', 'tag', 'update']:
                    self.UIManager.get_widget('/mainmenu/' + menu + 'menu/').hide()
            for menu in ['remove', 'clear', 'pl', 'rename', 'rm', 'new', 'edit', 'sort']:
                self.UIManager.get_widget('/mainmenu/' + menu + 'menu/').hide()
            if self.library.search_visible():
                self.UIManager.get_widget('/mainmenu/updatemenu/').hide()
            else:
                self.UIManager.get_widget('/mainmenu/updatemenu/').show()
                self.UIManager.get_widget('/mainmenu/updatemenu/updatefullmenu/').show()
        elif self.current_tab == self.TAB_PLAYLISTS:
            if self.playlists_selection.count_selected_rows() > 0:
                for menu in ['add', 'replace', 'playafter', 'rm']:
                    self.UIManager.get_widget('/mainmenu/' + menu + 'menu/').show()
                if self.playlists_selection.count_selected_rows() == 1 and mpdh.mpd_major_version(self.client) >= 0.13:
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

    def on_tags_edit(self, _widget):
        ui.change_cursor(gtk.gdk.Cursor(gtk.gdk.WATCH))
        while gtk.events_pending():
            gtk.main_iteration()

        files = []
        temp_mpdpaths = []
        if self.current_tab == self.TAB_INFO:
            if self.status and self.status['state'] in ['play', 'pause']:
                # Use current file in songinfo:
                mpdpath = mpdh.get(self.songinfo, 'file')
                fullpath = self.config.musicdir[self.config.profile_num] + mpdpath
                files.append(fullpath)
                temp_mpdpaths.append(mpdpath)
        elif self.current_tab == self.TAB_LIBRARY:
            # Populates files array with selected library items:
            items = self.library.get_path_child_filenames(False)
            for item in items:
                files.append(self.config.musicdir[self.config.profile_num] + item)
                temp_mpdpaths.append(item)
        elif self.current_tab == self.TAB_CURRENT:
            # Populates files array with selected current playlist items:
            temp_mpdpaths = self.current.get_selected_filenames(False)
            files = self.current.get_selected_filenames(True)

        tageditor = tagedit.TagEditor(self.window, self.tags_mpd_update, self.tags_set_use_mpdpath)
        tageditor.set_use_mpdpaths(self.config.tags_use_mpdpath)
        tageditor.on_tags_edit(files, temp_mpdpaths, self.config.musicdir[self.config.profile_num])

    def tags_set_use_mpdpath(self, use_mpdpath):
        self.config.tags_use_mpdpath = use_mpdpath

    def tags_mpd_update(self, tag_paths):
        mpdh.update(self.client, list(tag_paths), self.status)
        self.mpd_update_queued = True

    def on_about(self, _action):
        about_dialog = about.About(self.window, self.config, version.VERSION, __license__, self.find_path('sonata_large.png'))

        stats = None
        if self.conn:
            # Extract some MPD stats:
            mpdstats = mpdh.call(self.client, 'stats')
            stats = {'artists': mpdstats['artists'],
                 'albums': mpdstats['albums'],
                 'songs': mpdstats['songs'],
                 'db_playtime': mpdstats['db_playtime'],
                 }

        about_dialog.about_load(stats)

    def systemtray_initialize(self):
        # Make system tray 'icon' to sit in the system tray
        if HAVE_STATUS_ICON:
            self.statusicon = gtk.StatusIcon()
            self.statusicon.set_from_file(self.find_path('sonata.png'))
            self.statusicon.set_visible(self.config.show_trayicon)
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
                if self.config.show_trayicon:
                    self.trayicon.show_all()
                    self.eggtrayfile = self.find_path('sonata.png')
                    self.trayimage.set_from_pixbuf(img.get_pixbuf_of_size(gtk.gdk.pixbuf_new_from_file(self.eggtrayfile), self.eggtrayheight)[0])
                else:
                    self.trayicon.hide_all()
            except:
                pass

    def dbus_show(self):
        self.window.hide()
        self.withdraw_app_undo()

    def dbus_toggle(self):
        if self.window.get_property('visible'):
            self.withdraw_app()
        else:
            self.withdraw_app_undo()

    def dbus_popup(self):
        self.on_currsong_notify(force_popup=True)

    def main(self):
        gtk.main()
