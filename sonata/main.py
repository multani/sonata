
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

import sys
import gettext
import logging
import os
import warnings

import urllib.parse, urllib.request
import re
import gc
import shutil
import threading

import mpd

from gi.repository import Gtk, Gdk, GdkPixbuf, GObject, Pango

import pkg_resources

import sonata.mpdhelper as mpdh

from sonata import misc, ui, consts, img, tray, formatting

from sonata.pluginsystem import pluginsystem
from sonata.config import Config

from sonata import preferences, tagedit, \
                artwork, about, \
                scrobbler, info, \
                library, streams, \
                playlists, current, \
                lyricwiki, rhapsodycovers, \
                dbus_plugin as dbus
from sonata.song import SongRecord

from sonata.version import version


class Base(object):

    ### XXX Warning, a long __init__ ahead:

    def __init__(self, args, window=None):
        self.logger = logging.getLogger(__name__)

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
        self.artwork = None

        self.mpd = mpdh.MPDHelper(mpd.MPDClient())
        self.conn = False
        # Anything != than self.conn, to actually refresh the UI at startup.
        self.prevconn = not self.conn

        # Constants
        self.TAB_CURRENT = _("Current")
        self.TAB_LIBRARY = _("Library")
        self.TAB_PLAYLISTS = _("Playlists")
        self.TAB_STREAMS = _("Streams")
        self.TAB_INFO = _("Info")

        # If the connection to MPD times out, this will cause the interface
        # to freeze while the socket.connect() calls are repeatedly executed.
        # Therefore, if we were not able to make a connection, slow down the
        # iteration check to once every 15 seconds.
        self.iterate_time_when_connected = 500
        # Slow down polling when disconnected stopped
        self.iterate_time_when_disconnected_or_stopped = 1000


        self.trying_connection = False

        self.traytips = tray.TrayIconTips()

        # better keep a reference around
        try:
            self.dbus_service = dbus.SonataDBus(self.dbus_show,
                                                self.dbus_toggle,
                                                self.dbus_popup,
                                                self.dbus_fullscreen)
        except Exception:
            pass
        dbus.start_dbus_interface()

        self.gnome_session_management()

        misc.create_dir('~/.covers/')

        # Initialize vars for GUI
        self.current_tab = self.TAB_CURRENT

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
        self.last_consume = None
        self.last_title = None
        self.last_progress_frac = None
        self.last_progress_text = None

        self.last_status_text = ""

        self.img_clicked = False

        self.mpd_update_queued = False

        # XXX get rid of all of these:
        self.all_tab_names = [self.TAB_CURRENT, self.TAB_LIBRARY,
                              self.TAB_PLAYLISTS, self.TAB_STREAMS,
                              self.TAB_INFO]
        all_tab_ids = "current library playlists streams info".split()
        self.tabname2id = dict(zip(self.all_tab_names, all_tab_ids))
        self.tabid2name = dict(zip(all_tab_ids, self.all_tab_names))
        self.tabname2tab = dict()
        self.tabname2focus = dict()
        self.plugintabs = dict()

        self.config = Config(_('Default Profile'), _("by %A from %B"))
        self.preferences = preferences.Preferences(self.config,
            self.on_connectkey_pressed, self.on_currsong_notify,
            self.update_infofile, self.settings_save,
            self.populate_profiles_for_menu)

        self.settings_load()
        self.setup_prefs_callbacks()

        if args.start_visibility is not None:
            self.config.withdrawn = not args.start_visibility
        if self.config.autoconnect:
            self.user_connect = True
        args.apply_profile_arg(self.config)

        self.notebook_show_first_tab = not self.config.tabs_expanded or \
                self.config.withdrawn

        # Add some icons, assign pixbufs:
        self.iconfactory = Gtk.IconFactory()
        ui.icon(self.iconfactory, 'sonata', self.path_to_icon('sonata.png'))
        ui.icon(self.iconfactory, 'artist',
                self.path_to_icon('sonata-artist.png'))
        ui.icon(self.iconfactory, 'album', self.path_to_icon('sonata-album.png'))
        icon_theme = Gtk.IconTheme.get_default()
        img_res, img_width, _img_height = Gtk.icon_size_lookup(Gtk.IconSize.SMALL_TOOLBAR)
        if not img_res:
                self.logger.error("Invalid size of Volume Icon")
        for iconname in ('stock_volume-mute', 'stock_volume-min',
                         'stock_volume-med', 'stock_volume-max'):
            try:
                ui.icon(self.iconfactory, iconname,
                        icon_theme.lookup_icon(
                            iconname, img_width,
                            Gtk.IconLookupFlags.USE_BUILTIN).get_filename())
            except:
                # Fallback to Sonata-included icons:
                ui.icon(self.iconfactory, iconname,
                        self.path_to_icon('sonata-%s.png' % iconname))

        # Main window
        if window is None:
            self.window = Gtk.Window(type=Gtk.WindowType.TOPLEVEL)
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
        self.preferences.window = self.window

        self.notebook = Gtk.Notebook()

        # Artwork
        self.artwork = artwork.Artwork(
            self.config, self.path_to_icon, misc.is_lang_rtl(self.window),
            lambda: self.info_imagebox.get_size_request(),
            self.schedule_gc_collect, self.target_image_filename,
            self.imagelist_append, self.remotefilelist_append,
            self.notebook.get_allocation, self.set_allow_art_search,
            self.status_is_play_or_pause, self.path_to_icon('sonata-album.png'),
            self.get_current_song_text)


        # Popup menus:
        actions = [
            ('sortmenu', Gtk.STOCK_SORT_ASCENDING, _('_Sort List')),
            ('plmenu', Gtk.STOCK_SAVE, _('Sa_ve Selected to')),
            ('profilesmenu', Gtk.STOCK_CONNECT, _('_Connection')),
            ('playaftermenu', None, _('P_lay after')),
            ('playmodemenu', None, _('Play _Mode')),
            ('updatemenu', Gtk.STOCK_REFRESH, _('_Update')),
            ('chooseimage_menu', Gtk.STOCK_CONVERT, _('Use _Remote Image...'),
             None, None, self.image_remote),
            ('localimage_menu', Gtk.STOCK_OPEN, _('Use _Local Image...'),
             None, None, self.image_local),
            ('fullscreencoverart_menu', Gtk.STOCK_FULLSCREEN,
             _('_Fullscreen Mode'), 'F11', None, self.fullscreen_cover_art),
            ('resetimage_menu', Gtk.STOCK_CLEAR, _('Reset Image'), None, None,
             self.artwork.on_reset_image),
            ('playmenu', Gtk.STOCK_MEDIA_PLAY, _('_Play'), None, None,
             self.mpd_pp),
            ('pausemenu', Gtk.STOCK_MEDIA_PAUSE, _('Pa_use'), None, None,
             self.mpd_pp),
            ('stopmenu', Gtk.STOCK_MEDIA_STOP, _('_Stop'), None, None,
             self.mpd_stop),
            ('prevmenu', Gtk.STOCK_MEDIA_PREVIOUS, _('Pre_vious'), None, None,
             self.mpd_prev),
            ('nextmenu', Gtk.STOCK_MEDIA_NEXT, _('_Next'), None, None,
             self.mpd_next),
            ('quitmenu', Gtk.STOCK_QUIT, _('_Quit'), None, None,
             self.on_delete_event_yes),
            ('removemenu', Gtk.STOCK_REMOVE, _('_Remove'), None, None,
             self.on_remove),
            ('clearmenu', Gtk.STOCK_CLEAR, _('_Clear'), '<Ctrl>Delete', None,
             self.mpd_clear),
            ('updatefullmenu', None, _('_Entire Library'), '<Ctrl><Shift>u',
             None, self.on_updatedb),
            ('updateselectedmenu', None, _('_Selected Items'), '<Ctrl>u', None,
             self.on_updatedb_shortcut),
            ('preferencemenu', Gtk.STOCK_PREFERENCES, _('_Preferences...'),
             'F5', None, self.on_prefs),
            ('aboutmenu', Gtk.STOCK_ABOUT, _('_About...'), 'F1', None, self.on_about),
            ('tagmenu', Gtk.STOCK_EDIT, _('_Edit Tags...'), '<Ctrl>t', None,
             self.on_tags_edit),
            ('addmenu', Gtk.STOCK_ADD, _('_Add'), '<Ctrl>d', None,
             self.on_add_item),
            ('replacemenu', Gtk.STOCK_REDO, _('_Replace'), '<Ctrl>r', None,
             self.on_replace_item),
            ('add2menu', None, _('Add'), '<Shift><Ctrl>d', None,
             self.on_add_item_play),
            ('replace2menu', None, _('Replace'), '<Shift><Ctrl>r', None,
             self.on_replace_item_play),
            ('rmmenu', None, _('_Delete...'), None, None, self.on_remove),
            ('sortshuffle', None, _('Shuffle'), '<Alt>r', None,
             self.mpd_shuffle), ]

        keyactions = [
            ('expandkey', None, 'Expand Key', '<Alt>Down', None,
             self.on_expand),
            ('collapsekey', None, 'Collapse Key', '<Alt>Up', None,
             self.on_collapse),
            ('ppkey', None, 'Play/Pause Key', '<Ctrl>p', None, self.mpd_pp),
            ('stopkey', None, 'Stop Key', '<Ctrl>s', None, self.mpd_stop),
            ('prevkey', None, 'Previous Key', '<Ctrl>Left', None,
             self.mpd_prev),
            ('nextkey', None, 'Next Key', '<Ctrl>Right', None, self.mpd_next),
            ('lowerkey', None, 'Lower Volume Key', '<Ctrl>minus', None,
             self.on_volume_lower),
            ('raisekey', None, 'Raise Volume Key', '<Ctrl>plus', None,
             self.on_volume_raise),
            ('raisekey2', None, 'Raise Volume Key 2', '<Ctrl>equal', None,
             self.on_volume_raise),
            ('quitkey', None, 'Quit Key', '<Ctrl>q', None,
             self.on_delete_event_yes),
            ('quitkey2', None, 'Quit Key 2', '<Ctrl>w', None,
             self.on_delete_event),
            ('connectkey', None, 'Connect Key', '<Alt>c', None,
             self.on_connectkey_pressed),
            ('disconnectkey', None, 'Disconnect Key', '<Alt>d', None,
             self.on_disconnectkey_pressed),
            ('searchkey', None, 'Search Key', '<Ctrl>h', None,
             self.on_library_search_shortcut),
            ('nexttabkey', None, 'Next Tab Key', '<Alt>Right', None,
             self.switch_to_next_tab),
            ('prevtabkey', None, 'Prev Tab Key', '<Alt>Left', None,
             self.switch_to_prev_tab), ]

        tabactions = [('tab%skey' % i, None, 'Tab%s Key' % i,
                   '<Alt>%s' % i, None,
                   lambda _a, i=i: self.switch_to_tab_num(i-1))
                  for i in range(1, 10)]

        toggle_actions = [
            ('showmenu', None, _('S_how Sonata'), None, None,
             self.on_withdraw_app_toggle, not self.config.withdrawn),
            ('repeatmenu', None, _('_Repeat'), None, None,
             self.on_repeat_clicked, False),
            ('randommenu', None, _('Rando_m'), None, None,
             self.on_random_clicked, False),
            ('consumemenu', None, _('Consume'), None, None,
             self.on_consume_clicked, False),
            ]

        toggle_tabactions = [
            (self.TAB_CURRENT, None, self.TAB_CURRENT, None, None,
             self.on_tab_toggle, self.config.current_tab_visible),
            (self.TAB_LIBRARY, None, self.TAB_LIBRARY, None, None,
             self.on_tab_toggle, self.config.library_tab_visible),
            (self.TAB_PLAYLISTS, None, self.TAB_PLAYLISTS, None, None,
             self.on_tab_toggle, self.config.playlists_tab_visible),
            (self.TAB_STREAMS, None, self.TAB_STREAMS, None, None,
             self.on_tab_toggle, self.config.streams_tab_visible),
            (self.TAB_INFO, None, self.TAB_INFO, None, None,
             self.on_tab_toggle, self.config.info_tab_visible), ]

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
                <menu action="playmodemenu">
                  <menuitem action="repeatmenu"/>
                  <menuitem action="randommenu"/>
                  <menuitem action="consumemenu"/>
                </menu>
                <menuitem action="fullscreencoverart_menu"/>
                <menuitem action="preferencemenu"/>
                <separator name="FM3"/>
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
				<menuitem action="consumemenu"/>
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
                <menuitem action="centerplaylistkey"/>
              </popup>
            """

        uiDescription += '<popup name="notebookmenu">'
        uiDescription += ''.join('<menuitem action="%s"/>' % name
                     for name in self.all_tab_names)
        uiDescription += "</popup>"

        uiDescription += ''.join('<accelerator action="%s"/>' % a[0]
                     for a in keyactions + tabactions)

        uiDescription += "</ui>\n"

        # Try to connect to MPD:
        self.mpd_connect(blocking=True)
        if self.conn:
            self.status = self.mpd.status()
            self.iterate_time = self.iterate_time_when_connected
            self.songinfo = self.mpd.currentsong()
            self.artwork.update_songinfo(self.songinfo)
        elif self.config.initial_run:
            show_prefs = True

        # Realizing self.window will allow us to retrieve the theme's
        # link-color; we can then apply to it various widgets:
        try:
            self.window.realize()
            linkcolor = \
                    self.window.style_get_property("link-color").to_string()
        except:
            linkcolor = None

        # Audioscrobbler
        self.scrobbler = scrobbler.Scrobbler(self.config)
        self.scrobbler.import_module()
        self.scrobbler.init()
        self.preferences.scrobbler = self.scrobbler

        # Plug-ins imported as modules
        self.lyricwiki = lyricwiki.LyricWiki()
        self.rhapsodycovers = rhapsodycovers.RhapsodyCovers()

        # Current tab
        self.current = current.Current(
            self.config, self.mpd, self.TAB_CURRENT,
            self.on_current_button_press, self.connected,
            lambda: self.sonata_loaded, lambda: self.songinfo,
            self.update_statusbar, self.iterate_now,
            lambda: self.library.libsearchfilter_get_style(), self.new_tab)

        self.current_treeview = self.current.get_treeview()
        self.current_selection = self.current.get_selection()

        currentactions = [
            ('centerplaylistkey', None, 'Center Playlist Key', '<Ctrl>i',
             None, self.current.center_song_in_list),
            ('sortbyartist', None, _('By Artist'), None, None,
             self.current.on_sort_by_artist),
            ('sortbyalbum', None, _('By Album'), None, None,
             self.current.on_sort_by_album),
            ('sortbytitle', None, _('By Song Title'), None, None,
             self.current.on_sort_by_title),
            ('sortbyfile', None, _('By File Name'), None, None,
             self.current.on_sort_by_file),
            ('sortbydirfile', None, _('By Dir & File Name'), None, None,
             self.current.on_sort_by_dirfile),
            ('sortreverse', None, _('Reverse List'), None, None,
             self.current.on_sort_reverse),
            ]

        # Library tab
        self.library = library.Library(
            self.config, self.mpd, self.artwork, self.TAB_LIBRARY,
            self.path_to_icon('sonata-album.png'), self.settings_save,
            self.current.filtering_entry_make_red,
            self.current.filtering_entry_revert_color,
            self.current.filter_key_pressed, self.on_add_item, self.connected,
            self.on_library_button_press, self.new_tab,
            self.get_multicd_album_root_dir)

        self.library_treeview = self.library.get_treeview()
        self.library_selection = self.library.get_selection()

        libraryactions = self.library.get_libraryactions()

        # Info tab
        self.info = info.Info(self.config, self.artwork.get_info_image(),
                              linkcolor, self.on_link_click,
                              self.get_playing_song,
                              self.TAB_INFO, self.on_image_activate,
                              self.on_image_motion_cb, self.on_image_drop_cb,
                              self.album_return_artist_and_tracks,
                              self.new_tab)

        self.info_imagebox = self.info.get_info_imagebox()

        # Streams tab
        self.streams = streams.Streams(self.config, self.window,
                                       self.on_streams_button_press,
                                       self.on_add_item,
                                       self.settings_save,
                                       self.TAB_STREAMS,
                                       self.new_tab)

        self.streams_treeview = self.streams.get_treeview()
        self.streams_selection = self.streams.get_selection()

        streamsactions = [
            ('newmenu', None, _('_New...'), '<Ctrl>n', None,
             self.streams.on_streams_new),
            ('editmenu', None, _('_Edit...'), None, None,
             self.streams.on_streams_edit), ]

        # Playlists tab
        self.playlists = playlists.Playlists(self.config, self.window,
                                             self.mpd,
                                             lambda: self.UIManager,
                                             self.update_menu_visibility,
                                             self.iterate_now,
                                             self.on_add_item,
                                             self.on_playlists_button_press,
                                             self.current.get_current_songs,
                                             self.connected,
                                             self.add_selected_to_playlist,
                                             self.TAB_PLAYLISTS,
                                             self.new_tab)

        self.playlists_treeview = self.playlists.get_treeview()
        self.playlists_selection = self.playlists.get_selection()

        playlistsactions = [
            ('savemenu', None, _('_New Playlist...'), '<Ctrl><Shift>s', None,
             self.playlists.on_playlist_save),
            ('renamemenu', None, _('_Rename...'), None, None,
             self.playlists.on_playlist_rename),
            ]

        # Main app:
        self.UIManager = Gtk.UIManager()
        actionGroup = Gtk.ActionGroup('Actions')
        actionGroup.add_actions(actions)
        actionGroup.add_actions(keyactions)
        actionGroup.add_actions(tabactions)
        actionGroup.add_actions(currentactions)
        actionGroup.add_actions(libraryactions)
        actionGroup.add_actions(streamsactions)
        actionGroup.add_actions(playlistsactions)
        actionGroup.add_toggle_actions(toggle_actions)
        actionGroup.add_toggle_actions(toggle_tabactions)
        self.UIManager.insert_action_group(actionGroup, 0)
        self.UIManager.add_ui_from_string(uiDescription)
        self.populate_profiles_for_menu()
        self.window.add_accel_group(self.UIManager.get_accel_group())
        self.mainmenu = self.UIManager.get_widget('/mainmenu')
        self.randommenu = self.UIManager.get_widget('/mainmenu/randommenu')
        self.consumemenu = self.UIManager.get_widget('/mainmenu/consumemenu')
        self.repeatmenu = self.UIManager.get_widget('/mainmenu/repeatmenu')
        self.imagemenu = self.UIManager.get_widget('/imagemenu')
        self.traymenu = self.UIManager.get_widget('/traymenu')
        self.librarymenu = self.UIManager.get_widget('/librarymenu')
        self.library.set_librarymenu(self.librarymenu)
        self.notebookmenu = self.UIManager.get_widget('/notebookmenu')
        mainhbox = Gtk.HBox()
        mainvbox = Gtk.VBox()
        tophbox = Gtk.HBox()

        # Autostart plugins
        for plugin in pluginsystem.get_info():
            if plugin.name in self.config.autostart_plugins:
                pluginsystem.set_enabled(plugin, True)

        # New plugins
        for plugin in pluginsystem.get_info():
            if plugin.name not in self.config.known_plugins:
                self.config.known_plugins.append(plugin.name)
                if plugin.name in consts.DEFAULT_PLUGINS:
                    self.logger.info(
                        _("Enabling new plug-in %s..." % plugin.name))
                    pluginsystem.set_enabled(plugin, True)
                else:
                    self.logger.info(_("Found new plug-in %s." % plugin.name))

        self.tray_icon = tray.TrayIcon(self.window, self.traymenu, self.traytips)

        self.albumimage = self.artwork.get_albumimage()

        self.imageeventbox = ui.eventbox(add=self.albumimage)
        self.imageeventbox.drag_dest_set(Gtk.DestDefaults.HIGHLIGHT |
                                         Gtk.DestDefaults.DROP,
                                         [Gtk.TargetEntry.new("text/uri-list", 0, 80),
                                          Gtk.TargetEntry.new("text/plain", 0, 80)],
                                         Gdk.DragAction.DEFAULT)
        if not self.config.show_covers:
            ui.hide(self.imageeventbox)
        tophbox.pack_start(self.imageeventbox, False, False, 5)
        topvbox = Gtk.VBox()
        toptophbox = Gtk.HBox()
        self.prevbutton = ui.button(stock=Gtk.STOCK_MEDIA_PREVIOUS,
                                    relief=Gtk.ReliefStyle.NONE,
                                    can_focus=False, hidetxt=True)
        self.ppbutton = ui.button(stock=Gtk.STOCK_MEDIA_PLAY,
                                  relief=Gtk.ReliefStyle.NONE,
                                  can_focus=False, hidetxt=True)
        self.stopbutton = ui.button(stock=Gtk.STOCK_MEDIA_STOP,
                                    relief=Gtk.ReliefStyle.NONE,
                                    can_focus=False, hidetxt=True)
        self.nextbutton = ui.button(stock=Gtk.STOCK_MEDIA_NEXT,
                                    relief=Gtk.ReliefStyle.NONE,
                                    can_focus=False, hidetxt=True)
        for mediabutton in (self.prevbutton, self.ppbutton, self.stopbutton,
                            self.nextbutton):
            toptophbox.pack_start(mediabutton, False, False, 0)
            if not self.config.show_playback:
                ui.hide(mediabutton)
        self.progressbox = Gtk.VBox()
        self.progresslabel = ui.label(w=-1, h=6)
        self.progressbox.pack_start(self.progresslabel, True, True, 0)
        self.progressbar = Gtk.ProgressBar()
        self.progressbar.set_pulse_step(0.05)
        self.progressbar.set_ellipsize(Pango.EllipsizeMode.NONE)
        self.progressbar.set_show_text(True)

        self.progresseventbox = ui.eventbox(add=self.progressbar, visible=True)
        self.progressbox.pack_start(self.progresseventbox, False, False, 0)
        self.progresslabel2 = ui.label(w=-1, h=6)
        self.progressbox.pack_start(self.progresslabel2, True, True, 0)
        toptophbox.pack_start(self.progressbox, True, True, 0)
        if not self.config.show_progress:
            ui.hide(self.progressbox)
        self.volumebutton = Gtk.VolumeButton()
        self.volumebutton.set_adjustment(Gtk.Adjustment(0, 0, 100, 5, 5,))
        if not self.config.show_playback:
            ui.hide(self.volumebutton)
        toptophbox.pack_start(self.volumebutton, False, False, 0)
        topvbox.pack_start(toptophbox, False, False, 2)
        self.expander = ui.expander(text=_("Playlist"),
                                    expand=self.config.expanded,
                                    can_focus=False)
        expanderbox = Gtk.VBox()
        self.cursonglabel1 = ui.label(y=0)
        self.cursonglabel2 = ui.label(y=0)
        expanderbox.pack_start(self.cursonglabel1, True, True, 0)
        expanderbox.pack_start(self.cursonglabel2, True, True, 0)
        self.expander.set_label_widget(expanderbox)
        topvbox.pack_start(self.expander, False, False, 2)
        tophbox.pack_start(topvbox, True, True, 3)
        mainvbox.pack_start(tophbox, False, False, 5)
        self.notebook.set_tab_pos(Gtk.PositionType.TOP)
        self.notebook.set_scrollable(True)

        mainvbox.pack_start(self.notebook, True, True, 5)

        self.statusbar = Gtk.Statusbar()
        # TODO Find out what to do here
        #self.statusbar.set_has_resize_grip(True)
        if not self.config.show_statusbar or not self.config.expanded:
            ui.hide(self.statusbar)
        mainvbox.pack_start(self.statusbar, False, False, 0)
        mainhbox.pack_start(mainvbox, True, True, 3)
        if self.window_owner:
            self.window.add(mainhbox)
            self.window.move(self.config.x, self.config.y)
            self.window.set_size_request(270, -1)
        if not self.config.expanded:
            ui.hide(self.notebook)
            self.cursonglabel1.set_markup('<big><b>%s</b></big>' %
                                          (_('Stopped'),))
            self.cursonglabel2.set_markup('<small>%s</small>' % (_(('Click to'
                                                                   'expand'))))
            if self.window_owner:
                self.window.set_default_size(self.config.w, 1)
        else:
            self.cursonglabel1.set_markup('<big><b>%s</b></big>' % \
                                          (_('Stopped')))

            self.cursonglabel2.set_markup('<small>%s</small>' % (_(('Click to'
                                                                 'collapse'))))

            if self.window_owner:
                self.window.set_default_size(self.config.w, self.config.h)
        self.expander.set_tooltip_text(self.cursonglabel1.get_text())
        if not self.conn:
            self.progressbar.set_text(_('Not Connected'))
        elif not self.status:
            self.progressbar.set_text(_('No Read Permission'))

        # Update tab positions: XXX move to self.new_tab
        self.notebook.reorder_child(self.current.get_widgets(),
                                    self.config.current_tab_pos)
        self.notebook.reorder_child(self.library.get_widgets(),
                                    self.config.library_tab_pos)
        self.notebook.reorder_child(self.playlists.get_widgets(),
                                    self.config.playlists_tab_pos)
        self.notebook.reorder_child(self.streams.get_widgets(),
                                    self.config.streams_tab_pos)
        self.notebook.reorder_child(self.info.get_widgets(),
                                    self.config.info_tab_pos)
        self.last_tab = self.notebook_get_tab_text(self.notebook, 0)

        # Song notification window:
        outtertipbox = Gtk.VBox()
        tipbox = Gtk.HBox()

        self.trayalbumeventbox, self.trayalbumimage2 = \
                self.artwork.get_trayalbum()

        hiddenlbl = ui.label(w=2, h=-1)
        tipbox.pack_start(hiddenlbl, False, False, 0)
        tipbox.pack_start(self.trayalbumeventbox, False, False, 0)

        tipbox.pack_start(self.trayalbumimage2, False, False, 0)
        if not self.config.show_covers:
            ui.hide(self.trayalbumeventbox)
            ui.hide(self.trayalbumimage2)
        innerbox = Gtk.VBox()
        self.traycursonglabel1 = ui.label(markup=_("Playlist"), y=1)
        self.traycursonglabel2 = ui.label(markup=_("Playlist"), y=0)
        label1 = ui.label(markup='<span size="10"> </span>')
        innerbox.pack_start(label1, True, True, 0)
        innerbox.pack_start(self.traycursonglabel1, True, True, 0)
        innerbox.pack_start(self.traycursonglabel2, True, True, 0)

        self.trayprogressbar = Gtk.ProgressBar()
        self.trayprogressbar.set_pulse_step(0.05)
        self.trayprogressbar.set_ellipsize(Pango.EllipsizeMode.NONE)
        self.trayprogressbar.set_show_text(True)

        label2 = ui.label(markup='<span size="10"> </span>')
        innerbox.pack_start(label2, True, True, 0)
        innerbox.pack_start(self.trayprogressbar, False, False, 0)
        if not self.config.show_progress:
            ui.hide(self.trayprogressbar)
        label3 = ui.label(markup='<span size="10"> </span>')
        innerbox.pack_start(label3, True, True, 0)
        tipbox.pack_start(innerbox, True, True, 6)
        outtertipbox.pack_start(tipbox, False, False, 2)
        outtertipbox.show_all()
        self.traytips.add_widget(outtertipbox)
        self.tooltip_set_window_width()

        # Fullscreen cover art window
        self.fullscreencoverart = Gtk.Window()
        self.fullscreencoverart.set_title(_("Cover Art"))
        self.fullscreencoverart.set_decorated(True)
        self.fullscreencoverart.fullscreen()
        bgcolor = Gdk.RGBA()
        bgcolor.parse("black")
        self.fullscreencoverart\
            .override_background_color(Gtk.StateFlags.NORMAL, bgcolor)
        self.fullscreencoverart.add_accel_group(
            self.UIManager.get_accel_group())
        fscavbox = Gtk.VBox()
        fscahbox = Gtk.HBox()
        self.fullscreenalbumimage = self.artwork.get_fullscreenalbumimage()
        fscalbl, fscalbl2 = self.artwork.get_fullscreenalbumlabels()
        fscahbox.pack_start(self.fullscreenalbumimage, True, False, 0)
        fscavbox.pack_start(ui.label(), True, False, 0)
        fscavbox.pack_start(fscahbox, False, False, 12)
        fscavbox.pack_start(fscalbl, False, False, 5)
        fscavbox.pack_start(fscalbl2, False, False, 5)
        fscavbox.pack_start(ui.label(), True, False, 0)
        if not self.config.show_covers:
            ui.hide(self.fullscreenalbumimage)
        self.fullscreencoverart.add(fscavbox)

        # Connect to signals
        self.window.add_events(Gdk.EventMask.BUTTON_PRESS_MASK)
        self.traytips.add_events(Gdk.EventMask.BUTTON_PRESS_MASK)
        self.traytips.connect('button_press_event', self.on_traytips_press)
        self.window.connect('delete_event', self.on_delete_event)
        self.window.connect('configure_event', self.on_window_configure)
        self.window.connect('key-press-event', self.on_topwindow_keypress)
        self.imageeventbox.connect('button_press_event',
                                   self.on_image_activate)
        self.imageeventbox.connect('drag_motion', self.on_image_motion_cb)
        self.imageeventbox.connect('drag_data_received', self.on_image_drop_cb)
        self.ppbutton.connect('clicked', self.mpd_pp)
        self.stopbutton.connect('clicked', self.mpd_stop)
        self.prevbutton.connect('clicked', self.mpd_prev)
        self.nextbutton.connect('clicked', self.mpd_next)
        self.progresseventbox.connect('button_press_event',
                                      self.on_progressbar_press)
        self.progresseventbox.connect('scroll_event',
                                      self.on_progressbar_scroll)
        self.volumebutton.connect('value-changed', self.on_volume_change)
        self.expander.connect('activate', self.on_expander_activate)
        self.randommenu.connect('toggled', self.on_random_clicked)
        self.repeatmenu.connect('toggled', self.on_repeat_clicked)
        self.cursonglabel1.connect('notify::label', self.on_currsong_notify)
        self.progressbar.connect('notify::fraction',
                                 self.on_progressbar_notify_fraction)
        self.progressbar.connect('notify::text',
                                 self.on_progressbar_notify_text)
        self.mainwinhandler = self.window.connect('button_press_event',
                                                  self.on_window_click)
        self.notebook.connect('size-allocate', self.on_notebook_resize)
        self.notebook.connect('switch-page', self.on_notebook_page_change)

        self.fullscreencoverart.add_events(Gdk.EventMask.BUTTON_PRESS_MASK)
        self.fullscreencoverart.connect("button-press-event",
                                        self.fullscreen_cover_art_close, False)
        self.fullscreencoverart.connect("key-press-event",
                                        self.fullscreen_cover_art_close, True)
        for treeview in [self.current_treeview, self.library_treeview,
                         self.playlists_treeview, self.streams_treeview]:
            treeview.connect('popup_menu', self.on_menu_popup)
        for treeviewsel in [self.current_selection, self.library_selection,
                            self.playlists_selection, self.streams_selection]:
            treeviewsel.connect('changed', self.on_treeview_selection_changed)
        for widget in [self.ppbutton, self.prevbutton, self.stopbutton,
                       self.nextbutton, self.progresseventbox, self.expander]:
            widget.connect('button_press_event', self.menu_popup)

        self.systemtray_initialize()

        # This will ensure that "Not connected" is shown in the systray tooltip
        if not self.conn:
            self.update_cursong()

        # Ensure that the systemtray icon is added here. This is really only
        # important if we're starting in hidden (minimized-to-tray) mode:
        if self.window_owner and self.config.withdrawn:
            while Gtk.events_pending():
                Gtk.main_iteration()

        dbus.init_gnome_mediakeys(self.mpd_pp, self.mpd_stop, self.mpd_prev,
                                  self.mpd_next)

        # XXX find new multimedia key library here, in case we don't have gnome!
        #if not dbus.using_gnome_mediakeys():
        #    pass

        # Set up current view
        self.currentdata = self.current.get_model()

        # Initialize playlist data and widget
        self.playlistsdata = self.playlists.get_model()

        # Initialize streams data and widget
        self.streamsdata = self.streams.get_model()

        # Initialize library data and widget
        self.librarydata = self.library.get_model()
        self.artwork.library_artwork_init(self.librarydata,
                                          consts.LIB_COVER_SIZE)

        if self.window_owner:
            icon = self.window.render_icon('sonata', Gtk.IconSize.DIALOG)
            self.window.set_icon(icon)

        self.streams.populate()

        self.iterate_now()
        if self.window_owner:
            if self.config.withdrawn:
                if self.tray_icon.is_visible():
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

        gc.disable()

        GObject.idle_add(self.header_save_column_widths)

        pluginsystem.notify_of('tab_construct',
                       self.on_enable_tab,
                       self.on_disable_tab)

    ### Tab system:

    def on_enable_tab(self, _plugin, tab):
        self.plugintabs[tab] = self.new_tab(*tab())

    def on_disable_tab(self, _plugin, tab):
        self.notebook.remove(self.plugintabs.pop(tab))

    def new_tab(self, page, stock, text, focus):
        # create the "ear" of the tab:
        hbox = Gtk.HBox()
        hbox.pack_start(ui.image(stock=stock), False, False, 2)
        hbox.pack_start(ui.label(text=text), False, False, 2)
        evbox = ui.eventbox(add=hbox)
        evbox.show_all()

        evbox.connect("button_press_event", self.on_tab_click)

        # create the actual tab:
        self.notebook.append_page(page, evbox)

        if (text in self.tabname2id and
            not getattr(self.config,
                self.tabname2id[text] + '_tab_visible')):
            ui.hide(page)

        self.notebook.set_tab_reorderable(page, True)
        if self.config.tabs_expanded:
            self.notebook.set_tab_label_packing(page, True, True,
                                                Gtk.PACK_START)

        self.tabname2tab[text] = page
        self.tabname2focus[text] = focus

        return page

    def connected(self):
        ### "Model, logic":
        return self.conn

    def status_is_play_or_pause(self):
        return (self.conn and self.status and
            self.status.get('state', None) in ['play', 'pause'])

    def get_playing_song(self):
        if self.status_is_play_or_pause() and self.songinfo:
            return self.songinfo
        return None

    def playing_song_change(self):
        self.artwork.artwork_update()
        for _plugin, cb in pluginsystem.get('playing_song_observers'):
            cb(self.get_playing_song())

    def get_current_song_text(self):
        return (self.cursonglabel1.get_text(),
            self.cursonglabel2.get_text())

    def set_allow_art_search(self):
        self.allow_art_search = True

    def gnome_session_management(self):
        ### XXX The rest:
        try:
            import gnome
            import gnome.ui
            # Code thanks to quodlibet:

            # XXX gnome.init sets process name, locale...
            gnome.init("sonata", version)

            misc.setlocale()

            client = gnome.ui.master_client()
            client.set_restart_style(gnome.ui.RESTART_IF_RUNNING)
            command = os.path.normpath(os.path.join(os.getcwd(), sys.argv[0]))
            try:
                client.set_restart_command([command] + sys.argv[1:])
            except TypeError:
                # Fedora systems have a broken gnome-python wrapper for
                # this function.
                # http://www.sacredchao.net/quodlibet/ticket/591
                # http://trac.gajim.org/ticket/929
                client.set_restart_command(len(sys.argv),
                                           [command] + sys.argv[1:])
            client.connect('die', Gtk.main_quit)
        except:
            pass

    def populate_profiles_for_menu(self):
        host, port, _password = misc.mpd_env_vars()
        if self.merge_id:
            self.UIManager.remove_ui(self.merge_id)
        if self.actionGroupProfiles:
            self.UIManager.remove_action_group(self.actionGroupProfiles)
        self.actionGroupProfiles = Gtk.ActionGroup('MPDProfiles')
        self.UIManager.ensure_update()

        profile_names = [_("MPD_HOST/PORT")] if host \
                or port else self.config.profile_names

        actions = [
            (str(i),
             None,
             "[%d] %s" % (i + 1, ui.quote_label(name)),
             None,
             None,
             i)
            for i, name in enumerate(profile_names)]
        actions.append((
            'disconnect',
            Gtk.STOCK_DISCONNECT,
            _('Disconnect'),
            None,
            None,
            len(self.config.profile_names)))

        active_radio = 0 if host or port else self.config.profile_num
        if not self.conn:
            active_radio = len(self.config.profile_names)
        self.actionGroupProfiles.add_radio_actions(actions, active_radio,
                                                   self.on_profiles_click)
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
            thread = threading.Thread(target=self._mpd_connect,
                                      args=(blocking, force))
            thread.daemon = True
            thread.start()

    def _mpd_connect(self, _blocking, force):
        if self.trying_connection:
            return
        self.trying_connection = True
        if self.user_connect or force:
            host, port, password = misc.mpd_env_vars()
            if not host:
                host = self.config.host[self.config.profile_num]
            if not port:
                port = self.config.port[self.config.profile_num]
            if not password:
                password = self.config.password[self.config.profile_num]
            self.mpd.connect(host, port)
            if len(password) > 0:
                self.mpd.password(password)
            test = self.mpd.status()
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
            self.mpd.close()
            self.mpd.disconnect()
            self.conn = False

    def on_connectkey_pressed(self, _event=None):
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
                self.status = self.mpd.status()
                if self.status:
                    if self.status['state'] == 'stop':
                        self.iterate_time = \
                                self.iterate_time_when_disconnected_or_stopped
                    self.songinfo = self.mpd.currentsong()
                    self.artwork.update_songinfo(self.songinfo)
                    if not self.last_repeat \
                       or self.last_repeat != self.status['repeat']:
                        self.repeatmenu.set_active(
                            self.status['repeat'] == '1')
                    if not self.last_random \
                       or self.last_random != self.status['random']:
                        self.randommenu.set_active(
                            self.status['random'] == '1')
                    if not self.last_consume or self.last_consume != self.status['consume']:
                        self.consumemenu.set_active(self.status['consume'] == '1')
                    if self.status['xfade'] == '0':
                        self.config.xfade_enabled = False
                    else:
                        self.config.xfade_enabled = True
                        self.config.xfade = int(self.status['xfade'])
                        if self.config.xfade > 30:
                            self.config.xfade = 30
                    self.last_repeat = self.status['repeat']
                    self.last_random = self.status['random']
                    self.last_consume = self.status['consume']
                    return
        except:
            pass
        self.prevstatus = self.status
        self.prevsonginfo = self.songinfo
        self.conn = False
        self.status = None
        self.songinfo = None
        self.artwork.update_songinfo(self.songinfo)

    def iterate(self):
        self.update_status()
        self.info_update(False)

        # XXX: this is subject to race condition, since self.conn can be
        # changed in another thread:
        # 1. self.conn == self.prevconn (stable state)
        # 2. This if is tested and self.handle_change_conn is not called
        # 3. The connection thread updates self.conn
        # 4. self.prevconn = self.conn and we never get into the connected
        # state (or maybe throught another way, but well).
        if self.conn != self.prevconn:
            self.handle_change_conn()
        if self.status != self.prevstatus:
            self.handle_change_status()
        if self.songinfo != self.prevsonginfo:
            self.handle_change_song()

        self.prevconn = self.conn
        self.prevstatus = self.status
        self.prevsonginfo = self.songinfo

        # Repeat ad infitum..
        self.iterate_handler = GObject.timeout_add(self.iterate_time,
                                                   self.iterate)

        if self.config.show_trayicon:
            if self.tray_icon.is_available() and \
               not self.tray_icon.is_visible():
                # Systemtray appears, add icon
                self.systemtray_initialize()
            elif not self.tray_icon.is_available() and self.config.withdrawn:
                # Systemtray gone, unwithdraw app
                self.withdraw_app_undo()

        if self.call_gc_collect:
            gc.collect()
            self.call_gc_collect = False

    def schedule_gc_collect(self):
        self.call_gc_collect = True

    def iterate_stop(self):
        try:
            GObject.source_remove(self.iterate_handler)
        except:
            pass

    def iterate_now(self):
        # Since self.iterate_time_when_connected has been
        # slowed down to 500ms, we'll call self.iterate_now()
        # whenever the user performs an action that requires
        # updating the client
        self.iterate_stop()
        self.iterate()

    def on_topwindow_keypress(self, _widget, event):
        shortcut = Gtk.accelerator_name(event.keyval, event.get_state())
        shortcut = shortcut.replace("<Mod2>", "")
        # These shortcuts were moved here so that they don't interfere with
        # searching the library
        if shortcut == 'BackSpace' and self.current_tab == self.TAB_LIBRARY:
            return self.library.library_browse_parent(None)
        elif shortcut == 'Escape':
            if self.current_tab == self.TAB_LIBRARY \
               and self.library.search_visible():
                self.library.on_search_end(None)
            elif self.current_tab == self.TAB_CURRENT \
                    and self.current.filterbox_visible:
                self.current.searchfilter_toggle(None)
            elif self.config.minimize_to_systray and \
                    self.tray_icon.is_visible():
                self.withdraw_app()
            return
        elif shortcut == 'Delete':
            self.on_remove(None)
        if self.current_tab == self.TAB_CURRENT:
            if event.get_state() & (Gdk.ModifierType.CONTROL_MASK | Gdk.ModifierType.MOD1_MASK):
                return

            # XXX this isn't the right thing with GTK input methods:
            text = chr(Gdk.keyval_to_unicode(event.keyval))

            # We only want to toggle open the filterbar if the key press
            # is actual text! This will ensure that we skip, e.g., F5, Alt,
            # Ctrl, ...
            if text != "\x00" and text.strip():
                if not self.current.filterbox_visible:
                    if text != "/":
                        self.current.searchfilter_toggle(None, text)
                    else:
                        self.current.searchfilter_toggle(None)

    def settings_load(self):
        self.config.settings_load_real()

    def settings_save(self):
        self.header_save_column_widths()

        self.config.current_tab_pos = self.notebook_get_tab_num(
            self.notebook, self.TAB_CURRENT)
        self.config.library_tab_pos = self.notebook_get_tab_num(
            self.notebook, self.TAB_LIBRARY)
        self.config.playlists_tab_pos = self.notebook_get_tab_num(
            self.notebook, self.TAB_PLAYLISTS)
        self.config.streams_tab_pos = self.notebook_get_tab_num(
            self.notebook, self.TAB_STREAMS)
        self.config.info_tab_pos = self.notebook_get_tab_num(self.notebook,
                                                             self.TAB_INFO)

        autostart_plugins = []
        for plugin in pluginsystem.plugin_infos:
            if plugin._enabled:
                autostart_plugins.append(plugin.name)
        self.config.autostart_plugins = autostart_plugins

        self.config.settings_save_real()

    def handle_change_conn(self):
        if not self.conn:
            for mediabutton in (self.ppbutton, self.stopbutton,
                                self.prevbutton, self.nextbutton,
                                self.volumebutton):
                mediabutton.set_property('sensitive', False)
            self.currentdata.clear()
            if self.current_treeview.get_model():
                self.current_treeview.get_model().clear()
            self.tray_icon.update_icon(self.path_to_icon('sonata_disconnect.png'))
            self.info_update(True)
            if self.current.filterbox_visible:
                GObject.idle_add(self.current.searchfilter_toggle, None)
            if self.library.search_visible():
                self.library.on_search_end(None)
            self.handle_change_song()
            self.handle_change_status()
        else:
            for mediabutton in (self.ppbutton, self.stopbutton,
                                self.prevbutton, self.nextbutton,
                                self.volumebutton):
                mediabutton.set_property('sensitive', True)
            if self.sonata_loaded:
                self.library.library_browse(root=SongRecord(path="/"))
            self.playlists.populate()
            self.streams.populate()
            self.on_notebook_page_change(self.notebook, 0,
                                         self.notebook.get_current_page())

    def info_update(self, update_all):
        playing_or_paused = self.status_is_play_or_pause()
        newbitrate = None
        if self.status:
            newbitrate = self.status.get('bitrate', '')
        if newbitrate:
            newbitrate += " kbps"
        self.info.update(playing_or_paused, newbitrate, self.songinfo,
                 update_all)

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
        if self.on_button_press(widget, event, False):
            return True

    def on_current_button_press(self, widget, event):
        if self.on_button_press(widget, event, True):
            return True

    def on_playlists_button_press(self, widget, event):
        if self.on_button_press(widget, event, False):
            return True

    def on_streams_button_press(self, widget, event):
        if self.on_button_press(widget, event, False):
            return True

    def on_button_press(self, widget, event, widget_is_current):
        ctrl_press = (event.get_state() & Gdk.ModifierType.CONTROL_MASK)
        self.current.sel_rows = None
        if event.button == 1 and widget_is_current and not ctrl_press:
            # If the user clicked inside a group of rows that were already
            # selected, we need to retain the selected rows in case the user
            # wants to DND the group of rows. If they release the mouse without
            # first moving it, then we revert to the single selected row.
            # This is similar to the behavior found in thunar.
            try:
                path, _col, _x, _y = widget.get_path_at_pos(int(event.x),
                                                            int(event.y))
                if widget.get_selection().path_is_selected(path):
                    self.current.sel_rows = \
                            widget.get_selection().get_selected_rows()[1]
            except:
                pass
        elif event.button == 3:
            self.update_menu_visibility()
            # Calling the popup in idle_add is important. It allows the menu
            # items to have been shown/hidden before the menu is popped up.
            # Otherwise, if the menu pops up too quickly, it can result in
            # automatically clicking menu items for the user!
            GObject.idle_add(self.mainmenu.popup, None, None, None,
                             None, event.button, event.time)
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
                self.mpd.command_list_ok_begin()
                for item in items:
                    self.mpd.add(item)
                self.mpd.command_list_end()
            elif self.current_tab == self.TAB_PLAYLISTS:
                model, selected = self.playlists_selection.get_selected_rows()
                for path in selected:
                    self.mpd.load(
                              misc.unescape_html(
                                  model.get_value(model.get_iter(path), 1)))
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
                    self.mpd.play()
                else:
                    self.mpd.play(int(playid))

    def add_selected_to_playlist(self, plname):
        if self.current_tab == self.TAB_LIBRARY:
            songs = self.library.get_path_child_filenames(True)
        elif self.current_tab == self.TAB_CURRENT:
            songs = self.current.get_selected_filenames(0)
        else:
            raise Exception("This tab doesn't support playlists")

        self.mpd.command_list_ok_begin()
        for song in songs:
            self.mpd.playlistadd(plname, song)
        self.mpd.command_list_end()

    def stream_parse_and_add(self, item):
        # We need to do different things depending on if this is
        # a normal stream, pls, m3u, etc..
        # Note that we will only download the first 4000 bytes
        while Gtk.events_pending():
            Gtk.main_iteration()
        f = None
        try:
            request = urllib.request.Request(item)
            opener = urllib.request.build_opener()
            f = opener.open(request).read(4000)
        except:
            try:
                request = urllib.request.Request("http://" + item)
                opener = urllib.request.build_opener()
                f = opener.open(request).read(4000)
            except:
                try:
                    request = urllib.request.Request("file://" + item)
                    opener = urllib.request.build_opener()
                    f = opener.open(request).read(4000)
                except:
                    pass
        while Gtk.events_pending():
            Gtk.main_iteration()
        if f:
            if misc.is_binary(f):
                # Binary file, just add it:
                self.mpd.add(item)
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
                    self.mpd.add(item)
        else:
            # Hopefully just a regular stream, try to add it:
            self.mpd.add(item)

    def stream_parse_pls(self, f):
        lines = f.split("\n")
        for line in lines:
            line = line.replace('\r', '')
            delim = line.find("=") + 1
            if delim > 0:
                line = line[delim:]
                if len(line) > 7 and line[0:7] == 'http://':
                    self.mpd.add(line)
                elif len(line) > 6 and line[0:6] == 'ftp://':
                    self.mpd.add(line)

    def stream_parse_m3u(self, f):
        lines = f.split("\n")
        for line in lines:
            line = line.replace('\r', '')
            if len(line) > 7 and line[0:7] == 'http://':
                self.mpd.add(line)
            elif len(line) > 6 and line[0:6] == 'ftp://':
                self.mpd.add(line)

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
            _x, y, width, _height = self.current_treeview.get_allocation()
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
                if row_rect.y + row_rect.height <= visible_rect.height \
                   and row_rect.y >= 0:
                    row_y = row_rect.y + 30
                    break
            return (self.config.x + width - 150, self.config.y + y + row_y,
                    True)
        else:
            return (self.config.x + 250, self.config.y + 80, True)

    def handle_change_status(self):
        # Called when one of the following items are changed:
        #  1. Current playlist (song added, removed, etc)
        #  2. Repeat/random/xfade/volume
        #  3. Currently selected song in playlist
        #  4. Status (playing/paused/stopped)
        if self.status is None:
            # clean up and bail out
            self.update_progressbar()
            self.update_cursong()
            self.update_wintitle()
            self.playing_song_change()
            self.update_statusbar()
            if not self.conn:
                self.librarydata.clear()
                self.playlistsdata.clear()
                self.streamsdata.clear()
            return

        # Display current playlist
        if self.prevstatus is None \
           or self.prevstatus['playlist'] != self.status['playlist']:
            prevstatus_playlist = None
            if self.prevstatus:
                prevstatus_playlist = self.prevstatus['playlist']
            self.current.current_update(prevstatus_playlist,
                                        self.status['playlistlength'])

        # Update progress frequently if we're playing
        if self.status_is_play_or_pause():
            self.update_progressbar()

        # If elapsed time is shown in the window title, we need to update
        # more often:
        if "%E" in self.config.titleformat:
            self.update_wintitle()

        # If state changes
        if self.prevstatus is None \
           or self.prevstatus['state'] != self.status['state']:

            self.album_get_artist()

            # Update progressbar if the state changes too
            self.update_progressbar()
            self.update_cursong()
            self.update_wintitle()
            self.info_update(True)
            if self.status['state'] == 'stop':
                self.ppbutton.set_image(ui.image(
                    stock=Gtk.STOCK_MEDIA_PLAY,
                    stocksize=Gtk.IconSize.BUTTON))
                child = self.ppbutton.get_child().get_child().get_children()
                child[1].set_text('')
                self.UIManager.get_widget('/traymenu/playmenu').show()
                self.UIManager.get_widget('/traymenu/pausemenu').hide()
                self.tray_icon.update_icon(self.path_to_icon('sonata.png'))
            elif self.status['state'] == 'pause':
                self.ppbutton.set_image(ui.image(
                    stock=Gtk.STOCK_MEDIA_PLAY,
                    stocksize=Gtk.IconSize.BUTTON))
                child = self.ppbutton.get_child().get_child().get_children()
                child[1].set_text('')
                self.UIManager.get_widget('/traymenu/playmenu').show()
                self.UIManager.get_widget('/traymenu/pausemenu').hide()
                self.tray_icon.update_icon(self.path_to_icon('sonata_pause.png'))
            elif self.status['state'] == 'play':
                self.ppbutton.set_image(ui.image(
                    stock=Gtk.STOCK_MEDIA_PAUSE,
                    stocksize=Gtk.IconSize.BUTTON))
                child = self.ppbutton.get_child().get_child().get_children()
                child[1].set_text('')
                self.UIManager.get_widget('/traymenu/playmenu').hide()
                self.UIManager.get_widget('/traymenu/pausemenu').show()
                if self.prevstatus != None:
                    if self.prevstatus['state'] == 'pause':
                        # Forces the notification to popup if specified
                        self.on_currsong_notify()
                self.tray_icon.update_icon(self.path_to_icon('sonata_play.png'))

            self.playing_song_change()
            if self.status_is_play_or_pause():
                self.current.center_song_in_list()

        if self.prevstatus is None \
           or self.status['volume'] != self.prevstatus['volume']:
            self.volumebutton.set_value(int(self.status['volume']))

        if self.conn:
            if mpdh.mpd_is_updating(self.status):
                # MPD library is being updated
                self.update_statusbar(True)
            elif self.prevstatus is None \
                    or mpdh.mpd_is_updating(self.prevstatus) \
                    != mpdh.mpd_is_updating(self.status):
                if not mpdh.mpd_is_updating(self.status):
                    # Done updating, refresh interface
                    self.mpd_updated_db()
            elif self.mpd_update_queued:
                # If the update happens too quickly, we won't catch it in
                # our polling. So let's force an update of the interface:
                self.mpd_updated_db()
        self.mpd_update_queued = False

        if self.config.as_enabled:
            if self.prevstatus:
                prevstate = self.prevstatus['state']
            else:
                prevstate = 'stop'
            if self.status:
                state = self.status['state']
            else:
                state = 'stop'

            if state in ('play', 'pause'):
                mpd_time_now = self.status['time']
                self.scrobbler.handle_change_status(state, prevstate,
                                                    self.prevsonginfo,
                                                    self.songinfo,
                                                    mpd_time_now)
            elif state == 'stop':
                self.scrobbler.handle_change_status(state, prevstate,
                                                    self.prevsonginfo)

    def mpd_updated_db(self):
        self.library.view_caches_reset()
        self.update_statusbar(False)
        # We need to make sure that we update the artist in case tags
        # have changed:
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
            self.album_current_artist = [self.songinfo,
                                         mpdh.get(self.songinfo, 'artist')]
        else:
            self.album_current_artist = [self.songinfo, ""]

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
                if not self.prevsonginfo or mpdh.get(self.songinfo, 'id') \
                   != mpdh.get(self.prevsonginfo, 'id'):
                    self.current.center_song_in_list()
            self.current.prev_boldrow = row

        self.album_get_artist()

        self.update_cursong()
        self.update_wintitle()
        self.playing_song_change()
        self.info_update(True)

    def update_progressbar(self):
        if self.status_is_play_or_pause():
            at, length = [float(c) for c in self.status['time'].split(':')]
            try:
                newfrac = at / length
            except:
                newfrac = 0
        else:
            newfrac = 0
        if not self.last_progress_frac or self.last_progress_frac != newfrac:
            if newfrac >= 0 and newfrac <= 1:
                self.progressbar.set_fraction(newfrac)
        if self.conn:
            if self.status_is_play_or_pause():
                at, length = [int(c) for c in self.status['time'].split(':')]
                at_time = misc.convert_time(at)
                try:
                    time = misc.convert_time(mpdh.get(self.songinfo,
                                                      'time', 0, True))
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
                            days = str(int(hours) / 24)
                            hours = str(int(hours) - int(days) * 24).zfill(2)
                    except:
                        pass
                    if days:
                        days_text = ngettext('day', 'days', int(days))
                    if mins:
                        if mins.startswith('0') and len(mins) > 1:
                            mins = mins[1:]
                        mins_text = ngettext('minute', 'minutes', int(mins))
                    if hours:
                        if hours.startswith('0'):
                            hours = hours[1:]
                        hours_text = ngettext('hour', 'hours', int(hours))
                    # Show text:
                    songs_text = ngettext('song', 'songs',
                                          int(self.status['playlistlength']))
                    if int(self.status['playlistlength']) > 0:
                        if days:
                            status_text = '%s %s   %s %s, %s %s, %s %s %s' \
                                    % (str(self.status['playlistlength']),
                                       songs_text, days, days_text, hours,
                                       hours_text, _('and'), mins, mins_text,)
                        elif hours:
                            status_text = '%s %s   %s %s %s %s %s' % \
                                    (str(self.status['playlistlength']),
                                     songs_text, hours, hours_text, _('and'),
                                     mins, mins_text,)
                        elif mins:
                            status_text = '%s %s   %s %s' % \
                                    (str(self.status['playlistlength']),
                                     songs_text, mins, mins_text,)
                        else:
                            status_text = ''
                    else:
                        status_text = ''
                    if updatingdb:
                        status_text = '%s   %s' % (status_text, _(('(updating '
                                                                  'mpd)')),)
                except:
                    status_text = ''
            else:
                status_text = ''
            if status_text != self.last_status_text:
                self.statusbar.push(self.statusbar.get_context_id(''),
                                    status_text)
                self.last_status_text = status_text

    def update_cursong(self):
        if self.status_is_play_or_pause():
            # We must show the trayprogressbar and trayalbumeventbox
            # before changing self.cursonglabel (and consequently calling
            # self.on_currsong_notify()) in order to ensure that the
            # notification popup will have the correct height when being
            # displayed for the first time after a stopped state.
            if self.config.show_progress:
                self.trayprogressbar.show()
            self.traycursonglabel2.show()
            if self.config.show_covers:
                self.trayalbumeventbox.show()
                self.trayalbumimage2.show()

            for label in (self.cursonglabel1, self.cursonglabel2,
                          self.traycursonglabel1, self.traycursonglabel2):
                label.set_ellipsize(Pango.EllipsizeMode.END)


            if len(self.config.currsongformat1) > 0:
                newlabel1 = ('<big><b>%s </b></big>' %
                         formatting.parse(
                        self.config.currsongformat1,
                        self.songinfo, True))
            else:
                newlabel1 = '<big><b> </b></big>'
            if len(self.config.currsongformat2) > 0:
                newlabel2 = ('<small>%s </small>' %
                         formatting.parse(
                        self.config.currsongformat2,
                        self.songinfo, True))
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
            self.expander.set_tooltip_text('%s\n%s' % \
                                           (self.cursonglabel1.get_text(),
                                            self.cursonglabel2.get_text(),))
        else:
            for label in (self.cursonglabel1, self.cursonglabel2,
                          self.traycursonglabel1, self.cursonglabel2):
                label.set_ellipsize(Pango.EllipsizeMode.NONE)

            self.cursonglabel1.set_markup('<big><b>%s</b></big>' % \
                                          (_('Stopped'),))
            if self.config.expanded:
                self.cursonglabel2.set_markup('<small>%s</small>' % \
                                              (_('Click to collapse'),))
            else:
                self.cursonglabel2.set_markup('<small>%s</small>' % \
                                              _('Click to expand'))
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
            if self.status_is_play_or_pause():
                newtitle = formatting.parse(
                    self.config.titleformat, self.songinfo,
                    False, True,
                    self.status.get('time', None))
            else:
                newtitle = '[Sonata]'
            if not self.last_title or self.last_title != newtitle:
                self.window.set_property('title', newtitle)
                self.last_title = newtitle

    def tooltip_set_window_width(self):
        screen = self.window.get_screen()
        _pscreen, px, py, _mods = screen.get_display().get_pointer()
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
            if self.status_is_play_or_pause():
                if self.config.show_covers:
                    self.traytips.set_size_request(self.notification_width, -1)
                else:
                    self.traytips.set_size_request(
                        self.notification_width - 100, -1)
            else:
                self.traytips.set_size_request(-1, -1)
            if self.config.show_notification or force_popup:
                try:
                    GObject.source_remove(self.traytips.notif_handler)
                except:
                    pass
                if self.status_is_play_or_pause():
                    try:
                        self.traytips.notifications_location = \
                                self.config.traytips_notifications_location
                        self.traytips.use_notifications_location = True
                        if self.tray_icon.is_visible():
                            self.traytips._real_display(self.tray_icon)
                        else:
                            self.traytips._real_display(None)
                        if self.config.popup_option != len(self.popuptimes)-1:
                            if force_popup and \
                               not self.config.show_notification:
                                # Used -p argument and notification is disabled
                                # in player; default to 3 seconds
                                timeout = 3000
                            else:
                                timeout = \
                                        int(self.popuptimes[
                                            self.config.popup_option]) * 1000
                            self.traytips.notif_handler = \
                                    GObject.timeout_add(timeout,
                                                        self.traytips.hide)
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
                self.traytips._real_display(self.tray_icon)

    def on_progressbar_notify_fraction(self, *_args):
        self.trayprogressbar.set_fraction(self.progressbar.get_fraction())

    def on_progressbar_notify_text(self, *_args):
        self.trayprogressbar.set_text(self.progressbar.get_text())

    def update_infofile(self):
        if self.config.use_infofile is True:
            try:
                info_file = open(self.config.infofile_path, 'w',
                                 encoding="utf-8")

                if self.status['state'] in ['play']:
                    info_file.write('Status: ' + 'Playing' + '\n')
                elif self.status['state'] in ['pause']:
                    info_file.write('Status: ' + 'Paused' + '\n')
                elif self.status['state'] in ['stop']:
                    info_file.write('Status: ' + 'Stopped' + '\n')
                try:
                    info_file.write('Title: %s - %s\n' %
                                    (mpdh.get(self.songinfo, 'artist'),
                                     mpdh.get(self.songinfo, 'title'),))
                except:
                    try:
                        # No Arist in streams
                        info_file.write('Title: %s\n' % \
                                        (mpdh.get(self.songinfo, 'title'),))
                    except:
                        info_file.write('Title: No - ID Tag\n')
                info_file.write('Album: %s\n' % (mpdh.get(self.songinfo,
                                                         'album', 'No Data'),))
                info_file.write('Track: %s\n' % (mpdh.get(self.songinfo,
                                                          'track', '0'),))
                info_file.write('File: %s\n' % (mpdh.get(self.songinfo, 'file',
                                                         'No Data'),))
                info_file.write('Time: %s\n' % (mpdh.get(self.songinfo, 'time',
                                                         '0'),))
                info_file.write('Volume: %s\n' % (self.status['volume'],))
                info_file.write('Repeat: %s\n' % (self.status['repeat'],))
                info_file.write('Random: %s\n' % (self.status['random'],))
                info_file.write('Consume: %s\n' % (self.status['consume'],))
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
            if self.tray_icon.is_visible():
                self.withdraw_app()
                return True
        self.settings_save()
        self.artwork.artwork_save_cache()
        if self.config.as_enabled:
            self.scrobbler.save_cache()
        if self.conn and self.config.stop_on_exit:
            self.mpd_stop(None)
        sys.exit()

    def on_window_configure(self, window, _event):
        # When withdrawing an app, extra configure events (with wrong coords)
        # are fired (at least on Openbox). This prevents a user from moving
        # the window, withdrawing it, then unwithdrawing it and finding it in
        # an older position
        if not window.props.visible:
            return

        width, height = window.get_size()
        if self.config.expanded:
            self.config.w, self.config.h = width, height
        else:
            self.config.w = width
        self.config.x, self.config.y = window.get_position()

    def on_notebook_resize(self, _widget, _event):
        if not self.current.resizing_columns:
            GObject.idle_add(self.header_save_column_widths)
        GObject.idle_add(self.info.resize_elements, self.notebook.get_allocation())

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
        if not self.status_is_play_or_pause():
            if window_about_to_be_expanded:
                self.cursonglabel2.set_markup('<small>%s</small>' % \
                                              (_('Click to collapse'),))
            else:
                self.cursonglabel2.set_markup('<small>%s</small>' % \
                                              (_('Click to expand'),))
        # Now we wait for the height of the player to increase, so that
        # we know the list is visible. This is pretty hacky, but works.
        if self.window_owner:
            if window_about_to_be_expanded:
                if not skip_size_check:
                    while self.window.get_size()[1] == currheight:
                        Gtk.main_iteration()
                # Notebook is visible, now resize:
                self.window.resize(self.config.w, self.config.h)
            else:
                self.window.resize(self.config.w, 1)
        if window_about_to_be_expanded:
            self.config.expanded = True
            if self.status_is_play_or_pause():
                GObject.idle_add(self.current.center_song_in_list)

            hints = Gdk.Geometry()
            hints.min_height = -1
            hints.max_height = -1
            hints.min_width = -1
            hints.max_width = -1
            self.window.set_geometry_hints(self.window, hints, Gdk.WindowHints.USER_SIZE)
        if self.notebook_show_first_tab:
            # Sonata was launched in collapsed state. Ensure we display
            # first tab:
            self.notebook_show_first_tab = False
            self.notebook.set_current_page(0)
        # Put focus to the notebook:
        self.on_notebook_page_change(self.notebook, 0,
                                     self.notebook.get_current_page())

    # This callback allows the user to seek to a specific portion of the song
    def on_progressbar_press(self, _widget, event):
        if event.button == 1:
            if self.status_is_play_or_pause():
                at, length = [int(c) for c in self.status['time'].split(':')]
                try:
                    pbsize = self.progressbar.get_allocation()
                    if misc.is_lang_rtl(self.window):
                        seektime = int(
                            ((pbsize.width - event.x) / pbsize.width) * length)
                    else:
                        seektime = int((event.x / pbsize.width) * length)
                    self.seek(int(self.status['song']), seektime)
                except:
                    pass
            return True

    def on_progressbar_scroll(self, _widget, event):
        if self.status_is_play_or_pause():
            try:
                GObject.source_remove(self.seekidle)
            except:
                pass
            self.seekidle = GObject.idle_add(self._seek_when_idle,
                                             event.direction)
        return True

    def _seek_when_idle(self, direction):
        at, _length = [int(c) for c in self.status['time'].split(':')]
        try:
            if direction == Gdk.ScrollDirection.UP:
                seektime = max(0, at + 5)
            elif direction == Gdk.ScrollDirection.DOWN:
                seektime = min(mpdh.get(self.songinfo, 'time'),
                           at - 5)
            self.seek(int(self.status['song']), seektime)
        except:
            pass

    def on_lyrics_search(self, _event):
        artist = mpdh.get(self.songinfo, 'artist')
        title = mpdh.get(self.songinfo, 'title')
        dialog = ui.dialog(
            title=_('Lyrics Search'), parent=self.window,
            flags=Gtk.DialogFlags.MODAL | Gtk.DialogFlags.DESTROY_WITH_PARENT,
            buttons=(Gtk.STOCK_CANCEL, Gtk.ResponseType.REJECT, Gtk.STOCK_FIND,
                     Gtk.ResponseType.ACCEPT), role='lyricsSearch',
            default=Gtk.ResponseType.ACCEPT)
        dialog.action_area.get_children()[0].set_label(_("_Search"))
        dialog.action_area.get_children()[0].set_image(
            ui.image(stock=Gtk.STOCK_FIND))
        artist_hbox = Gtk.HBox()
        artist_label = ui.label(text=_('Artist Name:'))
        artist_hbox.pack_start(artist_label, False, False, 5)
        artist_entry = ui.entry(text=artist)
        artist_hbox.pack_start(artist_entry, True, True, 5)
        title_hbox = Gtk.HBox()
        title_label = ui.label(text=_('Song Title:'))
        title_hbox.pack_start(title_label, False, False, 5)
        title_entry = ui.entry(title)
        title_hbox.pack_start(title_entry, True, True, 5)
        ui.set_widths_equal([artist_label, title_label])
        dialog.vbox.pack_start(artist_hbox, True, True, 0)
        dialog.vbox.pack_start(title_hbox, True, True, 0)
        ui.show(dialog.vbox)
        response = dialog.run()
        if response == Gtk.ResponseType.ACCEPT:
            # Search for new lyrics:
            self.info.get_lyrics_start(
                artist_entry.get_text(),
                title_entry.get_text(),
                artist,
                title,
                os.path.dirname(mpdh.get(self.songinfo, 'file')),
                force_fetch=True)

        dialog.destroy()

    def mpd_shuffle(self, _action):
        if self.conn:
            if not self.status or self.status['playlistlength'] == '0':
                return
            ui.change_cursor(Gdk.Cursor.new(Gdk.CursorType.WATCH))
            while Gtk.events_pending():
                Gtk.main_iteration()
            self.mpd.shuffle()

    def on_menu_popup(self, _widget):
        self.update_menu_visibility()
        GObject.idle_add(self.mainmenu.popup, None, None, self.menu_position,
                         None, 3, 0)

    def on_updatedb(self, _action):
        if self.conn:
            if self.library.search_visible():
                self.library.on_search_end(None)
            self.mpd.update('/') # XXX we should pass a list here!
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
            filenames = self.library.get_path_child_filenames(True,
                                                              selected_only)
            if len(filenames) > 0:
                self.mpd.update(filenames)
                self.mpd_update_queued = True

    def on_image_activate(self, widget, event):
        self.window.handler_block(self.mainwinhandler)
        if event.button == 1 and widget == self.info_imagebox and \
           self.artwork.have_last():
            if not self.config.info_art_enlarged:
                self.info_imagebox.set_size_request(-1, -1)
                self.artwork.artwork_set_image_last()
                self.config.info_art_enlarged = True
            else:
                self.info_imagebox.set_size_request(152, -1)
                self.artwork.artwork_set_image_last()
                self.config.info_art_enlarged = False
            # Force a resize of the info labels, if needed:
            GObject.idle_add(self.on_notebook_resize, self.notebook, None)
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
            path_chooseimage = '/imagemenu/chooseimage_menu/'
            path_localimage = '/imagemenu/localimage_menu/'
            path_resetimage = '/imagemenu/resetimage_menu/'
            if self.status_is_play_or_pause():
                self.UIManager.get_widget(path_chooseimage).show()
                self.UIManager.get_widget(path_localimage).show()
                artist = mpdh.get(self.songinfo, 'artist', None)
                album = mpdh.get(self.songinfo, 'album', None)
                stream = mpdh.get(self.songinfo, 'name', None)
            if not (artist or album or stream):
                self.UIManager.get_widget(path_localimage).hide()
                self.UIManager.get_widget(path_resetimage).hide()
                self.UIManager.get_widget(path_chooseimage).hide()
            self.imagemenu.popup(None, None, None, None, event.button, event.time)
        GObject.timeout_add(50, self.on_image_activate_after)
        return False

    def on_image_motion_cb(self, _widget, context, _x, _y, time):
        context.drag_status(Gdk.DragAction.COPY, time)
        return True

    def on_image_drop_cb(self, _widget, _context, _x, _y, selection,
                         _info, _time):
        if self.status_is_play_or_pause():
            uri = selection.data.strip()
            path = urllib.request.url2pathname(uri)
            paths = path.rsplit('\n')
            thread = threading.Thread(target=self.on_image_drop_cb_thread,
                                      args=(paths,))
            thread.daemon = True
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
                    # Eliminate query arguments and extract extension
                    # & filename
                    path = urllib.parse.urlparse(paths[i]).path
                    extension = os.path.splitext(path)[1][1:]
                    filename = os.path.split(path)[1]
                    if img.extension_is_valid(extension):
                        # Save to temp dir.. we will delete the image
                        # afterwards
                        dest_file = os.path.expanduser('~/.covers/temp/%s' % \
                                                       (filename,))
                        misc.create_dir('~/.covers/temp')
                        src  = urllib.request.urlopen(paths[i], dest_file)
                        dest = open(dest_file, "w+")
                        dest.write(src.read())
                        paths[i] = dest_file
                        remove_after_set = True
                    else:
                        continue
                except Exception as e:
                    self.logger.critical("Can't retrieve cover: %s", e)
                    # cleanup undone file
                    misc.remove_file(paths[i])
                    raise e
            paths[i] = os.path.abspath(paths[i])
            if img.valid_image(paths[i]):
                stream = mpdh.get(self.songinfo, 'name', None)
                if stream is not None:
                    dest_filename = self.artwork.artwork_stream_filename(
                        mpdh.get(self.songinfo, 'name'))
                else:
                    dest_filename = self.target_image_filename()
                if dest_filename != paths[i]:
                    shutil.copyfile(paths[i], dest_filename)
                self.artwork.artwork_update(True)
                if remove_after_set:
                    misc.remove_file(paths[i])

    def target_image_filename(self, force_location=None, songpath=None,
                              artist=None, album=None):
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
            songpath = self.get_multicd_album_root_dir(songpath)
            # Return target filename:
            if force_location is not None:
                art_loc = force_location
            else:
                art_loc = self.config.art_location
            if art_loc == consts.ART_LOCATION_HOMECOVERS:
                targetfile = os.path.join(os.path.expanduser("~/.covers"),
                                          "%s-%s.jpg" % (artist, album))
            elif art_loc == consts.ART_LOCATION_COVER:
                targetfile = os.path.join(
                    self.config.musicdir[self.config.profile_num],
                    songpath, "cover.jpg")
            elif art_loc == consts.ART_LOCATION_FOLDER:
                targetfile = os.path.join(
                    self.config.musicdir[self.config.profile_num],
                    songpath, "folder.jpg")
            elif art_loc == consts.ART_LOCATION_ALBUM:
                targetfile = os.path.join(
                    self.config.musicdir[self.config.profile_num],
                    songpath, "album.jpg")
            elif art_loc == consts.ART_LOCATION_CUSTOM:
                targetfile = os.path.join(
                    self.config.musicdir[self.config.profile_num],
                    songpath, self.config.art_location_custom_filename)
            targetfile = misc.file_exists_insensitive(targetfile)
            return misc.file_from_utf8(targetfile)

    def get_multicd_album_root_dir(self, albumpath):
        """Go one dir upper for multicd albums
        Examples:
            'Moonspell/1995 - Wolfheart/cd 2' -> 'Moonspell/1995 - Wolfheart'
            '2007 - Dark Passion Play/CD3' -> '2007 - Dark Passion Play'
            'Ayreon/2008 - 01011001/CD 1 - Y' -> 'Ayreon/2008 - 01011001'
        """

        if re.compile(r'(?i)cd\s*\d+').match(os.path.split(albumpath)[1]):
            albumpath = os.path.split(albumpath)[0]
        return albumpath

    def album_return_artist_and_tracks(self):
        # Includes logic for Various Artists albums to determine
        # the tracks.
        datalist = []
        album = mpdh.get(self.songinfo, 'album')
        songs, _playtime, _num_songs = \
                self.library.library_return_search_items(album=album)
        for song in songs:
            year = mpdh.get(song, 'date', '')
            artist = mpdh.get(song, 'artist', '')
            path = os.path.dirname(mpdh.get(song, 'file'))
            data = SongRecord(album=album, artist=artist, \
                                       year=year, path=path)
            datalist.append(data)
        if len(datalist) > 0:
            datalist = misc.remove_list_duplicates(datalist, case=False)
            datalist = library.list_mark_various_artists_albums(datalist)
            if len(datalist) > 0:
                # Multiple albums with same name and year, choose the
                # right one. If we have a VA album, compare paths. Otherwise,
                # compare artists.
                for dataitem in datalist:
                    if dataitem.artist.lower() == \
                       mpdh.get(self.songinfo, 'artist').lower() \
                       or dataitem.artist == library.VARIOUS_ARTISTS \
                       and dataitem.path == \
                       os.path.dirname(mpdh.get(self.songinfo, 'file')):
                        datalist = [dataitem]
                        break
            # Find all songs in album:
            retsongs = []
            for song in songs:
                if mpdh.get(song, 'album').lower() == datalist[0].album.lower() \
                   and mpdh.get(song, 'date', None) == datalist[0].year \
                   and (datalist[0].artist == library.VARIOUS_ARTISTS \
                        or datalist[0].artist.lower() ==  \
                        mpdh.get(song, 'artist').lower()):
                        retsongs.append(song)

            return artist, retsongs
        else:
            return None, None

    def album_return_artist_name(self):
        # Determine if album_name is a various artists album.
        if self.album_current_artist[0] == self.songinfo:
            return
        artist, _tracks = self.album_return_artist_and_tracks()
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
            pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_size(filename, 128, 128)
        except:
            pass
        if pixbuf is None:
            try:
                pixbuf = GdkPixbuf.PixbufAnimation(filename).get_static_image()
                width = pixbuf.get_width()
                height = pixbuf.get_height()
                if width > height:
                    pixbuf = pixbuf.scale_simple(
                        128, int(float(height) / width * 128),
                        GdkPixbuf.InterpType.HYPER)
                else:
                    pixbuf = pixbuf.scale_simple(
                        int(float(width) / height * 128), 128,
                        GdkPixbuf.InterpType.HYPER)
            except:
                pass
        if pixbuf is None:
            pixbuf = GdkPixbuf.Pixbuf(GdkPixbuf.Colorspace.RGB, 1, 8, 128, 128)
            pixbuf.fill(0x00000000)
        preview.set_from_pixbuf(pixbuf)
        have_preview = True
        file_chooser.set_preview_widget_active(have_preview)
        del pixbuf
        self.call_gc_collect = True

    def image_local(self, _widget):
        dialog = Gtk.FileChooserDialog(
            title=_("Open Image"),
            action=Gtk.FileChooserAction.OPEN,
            buttons=(Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL,
                 Gtk.STOCK_OPEN, Gtk.ResponseType.OK))
        filefilter = Gtk.FileFilter()
        filefilter.set_name(_("Images"))
        filefilter.add_pixbuf_formats()
        dialog.add_filter(filefilter)
        filefilter = Gtk.FileFilter()
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
        dialog.connect("response", self.image_local_response, artist,
                       album, stream)
        dialog.set_default_response(Gtk.ResponseType.OK)
        songdir = os.path.dirname(mpdh.get(self.songinfo, 'file'))
        currdir = misc.file_from_utf8(
            os.path.join(self.config.musicdir[self.config.profile_num],
                         songdir))
        if self.config.art_location != consts.ART_LOCATION_HOMECOVERS:
            dialog.set_current_folder(currdir)
        if stream is not None:
            # Allow saving an image file for a stream:
            self.local_dest_filename = self.artwork.artwork_stream_filename(
                stream)
        else:
            self.local_dest_filename = self.target_image_filename()
        dialog.show()

    def image_local_response(self, dialog, response, _artist, _album, _stream):
        if response == Gtk.ResponseType.OK:
            filename = dialog.get_filenames()[0]
            # Copy file to covers dir:
            if self.local_dest_filename != filename:
                shutil.copyfile(filename, self.local_dest_filename)
            # And finally, set the image in the interface:
            self.artwork.artwork_update(True)
            # Force a resize of the info labels, if needed:
            GObject.idle_add(self.on_notebook_resize, self.notebook, None)
        dialog.destroy()

    def imagelist_append(self, elem):
        self.imagelist.append(elem)

    def remotefilelist_append(self, elem):
        self.remotefilelist.append(elem)

    def image_remote(self, _widget):
        self.choose_dialog = ui.dialog(title=_("Choose Cover Art"),
                                       parent=self.window,
                                       flags=Gtk.DialogFlags.MODAL,
                                       buttons=(Gtk.STOCK_CANCEL,
                                                Gtk.ResponseType.REJECT),
                                       role='chooseCoverArt',
                                       default=Gtk.ResponseType.ACCEPT,
                                       resizable=False)
        choosebutton = self.choose_dialog.add_button(_("C_hoose"),
                                                     Gtk.ResponseType.ACCEPT)
        chooseimage = ui.image(stock=Gtk.STOCK_CONVERT,
                               stocksize=Gtk.IconSize.BUTTON)
        choosebutton.set_image(chooseimage)
        self.imagelist = Gtk.ListStore(int, GdkPixbuf.Pixbuf)
        # Setting col=2 only shows 1 column with gtk 2.16 while col=-1 shows 2
        imagewidget = ui.iconview(col=-1, space=0, margin=0, itemw=75,
                                  selmode=Gtk.SelectionMode.SINGLE)
        scroll = ui.scrollwindow(policy_x=Gtk.PolicyType.NEVER,
                                 policy_y=Gtk.PolicyType.ALWAYS, w=360, h=325,
                                 add=imagewidget)
        self.choose_dialog.vbox.pack_start(scroll, False, False, 0)
        hbox = Gtk.HBox()
        vbox = Gtk.VBox()
        vbox.pack_start(ui.label(markup='<small> </small>'), False, False, 0)
        self.remote_artistentry = ui.entry()
        self.remote_albumentry = ui.entry()
        text = [("Artist"), _("Album")]
        labels = [ui.label(text=labelname + ": ") for labelname in text]
        entries = [self.remote_artistentry, self.remote_albumentry]
        for entry, label in zip(entries, labels):
            tmphbox = Gtk.HBox()
            tmphbox.pack_start(label, False, False, 5)
            entry.connect('activate', self.image_remote_refresh, imagewidget)
            tmphbox.pack_start(entry, True, True, 5)
            vbox.pack_start(tmphbox, True, True, 0)
        ui.set_widths_equal(labels)
        vbox.pack_start(ui.label(markup='<small> </small>'), False, False, 0)
        hbox.pack_start(vbox, True, True, 5)
        vbox2 = Gtk.VBox()
        vbox2.pack_start(ui.label(" "), True, True, 0)
        refreshbutton = ui.button(text=_('_Update'),
                                  img=ui.image(stock=Gtk.STOCK_REFRESH))
        refreshbutton.connect('clicked', self.image_remote_refresh,
                              imagewidget)
        vbox2.pack_start(refreshbutton, False, False, 5)
        vbox2.pack_start(ui.label(" "), True, True, 0)
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
            self.remote_dest_filename = self.artwork.artwork_stream_filename(
                stream)
        else:
            self.remote_dest_filename = self.target_image_filename()
        album = mpdh.get(self.songinfo, 'album', '')
        artist = self.album_current_artist[1]
        imagewidget.connect('item-activated', self.image_remote_replace_cover,
                            artist.replace("/", ""), album.replace("/", ""),
                            stream)
        self.choose_dialog.connect('response', self.image_remote_response,
                                   imagewidget, artist, album, stream)
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
            Gtk.main_iteration()
        self.imagelist.clear()
        imagewidget.set_text_column(-1)
        imagewidget.set_model(self.imagelist)
        imagewidget.set_pixbuf_column(1)
        ui.focus(imagewidget)
        ui.change_cursor(Gdk.Cursor.new(Gdk.CursorType.WATCH))
        thread = threading.Thread(target=self._image_remote_refresh,
                                  args=(imagewidget, None))
        thread.daemon = True
        thread.start()

    def _image_remote_refresh(self, imagewidget, _ignore):
        self.artwork.stop_art_update = False
        # Retrieve all images from rhapsody:
        artist_search = self.remote_artistentry.get_text()
        album_search = self.remote_albumentry.get_text()
        if len(artist_search) == 0 and len(album_search) == 0:
            GObject.idle_add(self.image_remote_no_tag_found, imagewidget)
            return
        filename = os.path.expanduser("~/.covers/temp/<imagenum>.jpg")
        misc.remove_dir_recursive(os.path.dirname(filename))
        misc.create_dir(os.path.dirname(filename))
        imgfound = self.artwork.artwork_download_img_to_file(artist_search,
                                                             album_search,
                                                             filename, True)
        ui.change_cursor(None)
        if self.chooseimage_visible:
            if not imgfound:
                GObject.idle_add(self.image_remote_no_covers_found,
                                 imagewidget)
        self.call_gc_collect = True

    def image_remote_no_tag_found(self, imagewidget):
        self.image_remote_warning(imagewidget,
                                  _("No artist or album name found."))

    def image_remote_no_covers_found(self, imagewidget):
        self.image_remote_warning(imagewidget, _("No cover art found."))

    def image_remote_warning(self, imagewidget, msgstr):
        liststore = Gtk.ListStore(int, str)
        liststore.append([0, msgstr])
        imagewidget.set_pixbuf_column(-1)
        imagewidget.set_model(liststore)
        imagewidget.set_text_column(1)
        ui.change_cursor(None)
        self.allow_art_search = True

    def image_remote_response(self, dialog, response_id, imagewidget, artist,
                              album, stream):
        self.artwork.artwork_stop_update()
        if response_id == Gtk.ResponseType.ACCEPT:
            try:
                self.image_remote_replace_cover(
                    imagewidget, imagewidget.get_selected_items()[0], artist,
                    album, stream)
                # Force a resize of the info labels, if needed:
                GObject.idle_add(self.on_notebook_resize, self.notebook, None)
            except:
                dialog.destroy()
        else:
            dialog.destroy()
        ui.change_cursor(None)
        self.chooseimage_visible = False

    def image_remote_replace_cover(self, _iconview, path, _artist, _album,
                                   _stream):
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
            Gtk.main_iteration()

    def fullscreen_cover_art(self, _widget):
        if self.fullscreencoverart.get_property('visible'):
            self.fullscreencoverart.hide()
        else:
            self.traytips.hide()
            self.artwork.fullscreen_cover_art_set_image(force_update=True)
            self.fullscreencoverart.show_all()
            # setting up invisible cursor
            window = self.fullscreencoverart.get_window()
            window.set_cursor(Gdk.Cursor.new(Gdk.CursorType.BLANK_CURSOR))

    def fullscreen_cover_art_close(self, _widget, event, key_press):
        if key_press:
            shortcut = Gtk.accelerator_name(event.keyval, event.get_state())
            shortcut = shortcut.replace("<Mod2>", "")
            if shortcut != 'Escape':
                return
        self.fullscreencoverart.hide()

    def header_save_column_widths(self):
        if not self.config.withdrawn and self.config.expanded:
            windowwidth = self.window.get_allocation().width
            if windowwidth <= 10 or self.current.columns[0].get_width() <= 10:
                # Make sure we only set self.config.columnwidths if
                # self.current has its normal allocated width:
                return
            notebookwidth = self.notebook.get_allocation().width
            treewidth = 0
            for i, column in enumerate(self.current.columns):
                colwidth = column.get_width()
                treewidth += colwidth
                if i == len(self.current.columns)-1 \
                   and treewidth <= windowwidth:
                    self.config.columnwidths[i] = min(colwidth,
                                                      column.get_fixed_width())
                else:
                    self.config.columnwidths[i] = colwidth
        self.current.resizing_columns = False

    def systemtray_activate(self, _status_icon):
        # Clicking on a Gtk.StatusIcon:
        if not self.ignore_toggle_signal:
            # This prevents the user clicking twice in a row quickly
            # and having the second click not revert to the intial
            # state
            self.ignore_toggle_signal = True
            path_showmenu = '/traymenu/showmenu'
            prev_state = self.UIManager.get_widget(path_showmenu).get_active()
            self.UIManager.get_widget(path_showmenu).set_active(not prev_state)
            if not self.window.get_window():
                # For some reason, self.window.window is not defined if
                # mpd is not running and sonata is started with
                # self.config.withdrawn = True
                self.withdraw_app_undo()
            elif not (self.window.get_window().get_state() & \
                      Gdk.WindowState.WITHDRAWN) and \
                    self.window.is_active():
                # Window is not withdrawn and is active (has toplevel focus):
                self.withdraw_app()
            else:
                self.withdraw_app_undo()
            # This prevents the tooltip from popping up again until the user
            # leaves and enters the trayicon again
            # if self.traytips.notif_handler is None and
            # self.traytips.notif_handler != -1:
            # self.traytips._remove_timer()
            GObject.timeout_add(100,
                                self.tooltip_set_ignore_toggle_signal_false)

    def systemtray_click(self, _widget, event):
        # Clicking on a system tray icon:
        # Left button shows/hides window(s)
        if event.button == 1 and not self.ignore_toggle_signal:
            self.systemtray_activate(None)
        elif event.button == 2: # Middle button will play/pause
            if self.conn:
                self.mpd_pp(None)
        elif event.button == 3: # Right button pops up menu
            self.traymenu.popup(None, None, None, None, event.button, event.time)
        return False

    def on_traytips_press(self, _widget, _event):
        if self.traytips.get_property('visible'):
            self.traytips._remove_timer()

    def withdraw_app_undo(self):
        desktop = Gdk.get_default_root_window()
        # convert window coordinates to current workspace so sonata
        # will always appear on the current workspace with the same
        # position as it was before (may be on the other workspace)
        self.config.x %= desktop.get_width()
        self.config.y %= desktop.get_height()
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
        self.withdraw_app_undo_present_and_focus()

    def withdraw_app_undo_present_and_focus(self):
        # Helps to raise the window (useful against focus stealing prevention)
        self.window.present()
        self.window.grab_focus()
        if self.config.sticky:
            self.window.stick()
        if self.config.ontop:
            self.window.set_keep_above(True)

    def withdraw_app(self):
        if self.tray_icon.is_available():
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
        GObject.timeout_add(500, self.tooltip_set_ignore_toggle_signal_false)

    def tooltip_set_ignore_toggle_signal_false(self):
        self.ignore_toggle_signal = False

    # Change volume on mousewheel over systray icon:
    def systemtray_scroll(self, widget, event):
        if self.conn:
            self.volumebutton.emit("scroll-event", event.copy())

    def switch_to_tab_name(self, tab_name):
        self.notebook.set_current_page(self.notebook_get_tab_num(self.notebook,
                                                                 tab_name))

    def switch_to_tab_num(self, tab_num):
        vis_tabnum = self.notebook_get_visible_tab_num(self.notebook, tab_num)
        if vis_tabnum != -1:
            self.notebook.set_current_page(vis_tabnum)

    def switch_to_next_tab(self, _action):
        self.notebook.next_page()

    def switch_to_prev_tab(self, _action):
        self.notebook.prev_page()

    # Volume control
    def on_volume_lower(self, _action):
        new_volume = int(self.volumebutton.get_value()) - 5
        self.volumebutton.set_value(new_volume)

    def on_volume_raise(self, _action):
        new_volume = int(self.volumebutton.get_value()) + 5
        self.volumebutton.set_value(new_volume)

    def on_volume_change(self, _button, new_volume):
        self.mpd.setvol(int(new_volume))

    def mpd_pp(self, _widget, _key=None):
        if self.conn and self.status:
            if self.status['state'] in ('stop', 'pause'):
                self.mpd.play()
            elif self.status['state'] == 'play':
                self.mpd.pause('1')
            self.iterate_now()

    def mpd_stop(self, _widget, _key=None):
        if self.conn:
            self.mpd.stop()
            self.iterate_now()

    def mpd_prev(self, _widget, _key=None):
        if self.conn:
            self.mpd.previous()
            self.iterate_now()

    def mpd_next(self, _widget, _key=None):
        if self.conn:
            self.mpd.next()
            self.iterate_now()

    def on_remove(self, _widget):
        if self.conn:
            model = None
            while Gtk.events_pending():
                Gtk.main_iteration()
            if self.current_tab == self.TAB_CURRENT:
                self.current.on_remove()
            elif self.current_tab == self.TAB_PLAYLISTS:
                treeviewsel = self.playlists_selection
                model, selected = treeviewsel.get_selected_rows()
                if ui.show_msg(self.window,
                               ngettext("Delete the selected playlist?",
                                        "Delete the selected playlists?",
                                        int(len(selected))),
                               ngettext("Delete Playlist",
                                        "Delete Playlists",
                                        int(len(selected))),
                               'deletePlaylist', Gtk.ButtonsType.YES_NO) == \
                   Gtk.ResponseType.YES:
                    iters = [model.get_iter(path) for path in selected]
                    for i in iters:
                        self.mpd.rm(misc.unescape_html(
                            self.playlistsdata.get_value(i, 1)))
                    self.playlists.populate()
            elif self.current_tab == self.TAB_STREAMS:
                treeviewsel = self.streams_selection
                model, selected = treeviewsel.get_selected_rows()
                if ui.show_msg(self.window,
                               ngettext("Delete the selected stream?",
                                        "Delete the selected streams?",
                                        int(len(selected))),
                               ngettext("Delete Stream",
                                        "Delete Streams",
                                        int(len(selected))),
                               'deleteStreams', Gtk.ButtonsType.YES_NO) == \
                   Gtk.ResponseType.YES:
                    iters = [model.get_iter(path) for path in selected]
                    for i in iters:
                        stream_removed = False
                        for j in range(len(self.config.stream_names)):
                            if not stream_removed:
                                if self.streamsdata.get_value(i, 1) == \
                                   misc.escape_html(
                                       self.config.stream_names[j]):
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
            self.mpd.clear()
            self.iterate_now()

    def on_repeat_clicked(self, widget):
        if self.conn:
            self.mpd.repeat(int(widget.get_active()))

    def on_random_clicked(self, widget):
        if self.conn:
            self.mpd.random(int(widget.get_active()))

    def on_consume_clicked(self, widget):
        if self.conn:
            self.mpd.consume(int(widget.get_active()))

    def setup_prefs_callbacks(self):
        extras = preferences.Extras_cbs
        extras.popuptimes = self.popuptimes
        extras.notif_toggled = self.prefs_notif_toggled
        extras.crossfade_toggled = self.prefs_crossfade_toggled
        extras.crossfade_changed = self.prefs_crossfade_changed

        display = preferences.Display_cbs
        display.stylized_toggled = self.prefs_stylized_toggled
        display.art_toggled = self.prefs_art_toggled
        display.playback_toggled = self.prefs_playback_toggled
        display.progress_toggled = self.prefs_progress_toggled
        display.statusbar_toggled = self.prefs_statusbar_toggled
        display.lyrics_toggled = self.prefs_lyrics_toggled
        # TODO: the tray icon object has not been build yet, so we don't know
        # if the tray icon will be available at this time.
        # We should find a way to update this when the tray icon will be
        # initialized.
        display.trayicon_available = True

        behavior = preferences.Behavior_cbs
        behavior.trayicon_toggled = self.prefs_trayicon_toggled
        behavior.sticky_toggled = self.prefs_sticky_toggled
        behavior.ontop_toggled = self.prefs_ontop_toggled
        behavior.decorated_toggled = self.prefs_decorated_toggled
        behavior.infofile_changed = self.prefs_infofile_changed

        format = preferences.Format_cbs
        format.currentoptions_changed = self.prefs_currentoptions_changed
        format.libraryoptions_changed = self.prefs_libraryoptions_changed
        format.titleoptions_changed = self.prefs_titleoptions_changed
        format.currsongoptions1_changed = self.prefs_currsongoptions1_changed
        format.currsongoptions2_changed = self.prefs_currsongoptions2_changed

    def on_prefs(self, _widget):
        preferences.Behavior_cbs.trayicon_in_use = self.tray_icon.is_visible()
        self.preferences.on_prefs_real()

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

    def prefs_ontop_toggled(self, button):
        self.config.ontop = button.get_active()
        if self.window_owner:
            self.window.set_keep_above(self.config.ontop)

    def prefs_sticky_toggled(self, button):
        self.config.sticky = button.get_active()
        if self.window_owner:
            if self.config.sticky:
                self.window.stick()
            else:
                self.window.unstick()

    def prefs_decorated_toggled(self, button, prefs_window):
        self.config.decorated = not button.get_active()
        if self.window_owner:
            if self.config.decorated != self.window.get_decorated():
                self.withdraw_app()
                self.window.set_decorated(self.config.decorated)
                self.withdraw_app_undo()
                prefs_window.present()

    def prefs_infofile_changed(self, entry, _event):
        if self.config.infofile_path != entry.get_text():
            self.config.infofile_path = os.path.expanduser(entry.get_text())
            if self.config.use_infofile:
                self.update_infofile()

    def prefs_crossfade_changed(self, crossfade_spin):
        crossfade_value = crossfade_spin.get_value_as_int()
        self.mpd.crossfade(crossfade_value)

    def prefs_crossfade_toggled(self, button, crossfade_spin):
        crossfade_value = crossfade_spin.get_value_as_int()
        if button.get_active():
            self.mpd.crossfade(crossfade_value)
        else:
            self.mpd.crossfade(0)

    def prefs_playback_toggled(self, button):
        self.config.show_playback = button.get_active()
        func = 'show' if self.config.show_playback else 'hide'
        for widget in [self.prevbutton, self.ppbutton, self.stopbutton,
                       self.nextbutton, self.volumebutton]:
            getattr(ui, func)(widget)

    def prefs_progress_toggled(self, button):
        self.config.show_progress = button.get_active()
        func = ui.show if self.config.show_progress else ui.hide
        for widget in [self.progressbox, self.trayprogressbar]:
            func(widget)

    def prefs_art_toggled(self, button, art_hbox1, art_hbox2, art_stylized):
        button_active = button.get_active()
        art_hbox1.set_sensitive(button_active)
        art_hbox2.set_sensitive(button_active)
        art_stylized.set_sensitive(button_active)
        if button_active:
            self.traytips.set_size_request(self.notification_width, -1)
            self.artwork.artwork_set_default_icon()
            for widget in [self.imageeventbox, self.info_imagebox,
                           self.trayalbumeventbox, self.trayalbumimage2]:
                widget.set_no_show_all(False)
                if widget in [self.trayalbumeventbox, self.trayalbumimage2]:
                    if self.status_is_play_or_pause():
                        widget.show_all()
                else:
                    widget.show_all()
            self.config.show_covers = True
            self.update_cursong()
            self.artwork.artwork_update()
        else:
            self.traytips.set_size_request(self.notification_width-100, -1)
            for widget in [self.imageeventbox, self.info_imagebox,
                           self.trayalbumeventbox, self.trayalbumimage2]:
                ui.hide(widget)
            self.config.show_covers = False
            self.update_cursong()

        # Force a resize of the info labels, if needed:
        GObject.idle_add(self.on_notebook_resize, self.notebook, None)

    def prefs_stylized_toggled(self, button):
        self.config.covers_type = button.get_active()
        self.library.library_browse(root=self.config.wd)
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
                GObject.source_remove(self.traytips.notif_handler)
            except:
                pass
            self.traytips.hide()

    def prefs_trayicon_toggled(self, button, minimize):
        # Note that we update the sensitivity of the minimize
        # CheckButton to reflect if the trayicon is visible.
        if button.get_active():
            self.config.show_trayicon = True
            self.tray_icon.show()
            minimize.set_sensitive(True)
        else:
            self.config.show_trayicon = False
            minimize.set_sensitive(False)
            self.tray_icon.hide()

    def seek(self, song, seektime):
        self.mpd.seek(song, seektime)
        self.iterate_now()

    def on_link_click(self, linktype):
        browser_not_loaded = False
        wikipedia_search = "http://www.wikipedia.org/wiki/Special:Search/"
        if linktype == 'artist':
            browser_not_loaded = not misc.browser_load(
                '%s%s' % (wikipedia_search,
                          urllib.parse.quote(mpdh.get(self.songinfo, 'artist')),),
                self.config.url_browser, self.window)
        elif linktype == 'album':
            browser_not_loaded = not misc.browser_load(
                '%s%s' % (wikipedia_search,
                          urllib.parse.quote(mpdh.get(self.songinfo, 'album')),),
                self.config.url_browser, self.window)
        elif linktype == 'edit':
            if self.songinfo:
                self.on_tags_edit(None)
        elif linktype == 'search':
            self.on_lyrics_search(None)
        elif linktype == 'editlyrics':
            browser_not_loaded = not misc.browser_load(
                self.lyricwiki.lyricwiki_editlink(self.songinfo),
                self.config.url_browser, self.window)
        if browser_not_loaded:
            ui.show_msg(self.window, _('Unable to launch a suitable browser.'),
                        _('Launch Browser'),
                        'browserLoadError', Gtk.ButtonsType.CLOSE)

    def on_tab_click(self, _widget, event):
        if event.button == 3:
            self.notebookmenu.popup(None, None, None, None, event.button, event.time)
            return True

    def notebook_get_tab_num(self, notebook, tabname):
        for tab in range(notebook.get_n_pages()):
            if self.notebook_get_tab_text(self.notebook, tab) == tabname:
                return tab

    def notebook_tab_is_visible(self, notebook, tabname):
        tab = self.notebook.get_children()[self.notebook_get_tab_num(notebook,
                                                                     tabname)]
        return tab.get_property('visible')

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
        child = notebook.get_tab_label(tab).get_child().get_children()[1]
        return child.get_text()

    def on_notebook_page_change(self, _notebook, _page, page_num):
        self.current_tab = self.notebook_get_tab_text(self.notebook, page_num)
        to_focus = self.tabname2focus.get(self.current_tab, None)
        if to_focus:
            GObject.idle_add(ui.focus, to_focus)

        GObject.idle_add(self.update_menu_visibility)
        if not self.img_clicked:
            self.last_tab = self.current_tab

    def on_window_click(self, _widget, event):
        if event.button == 3:
            self.menu_popup(self.window, event)

    def menu_popup(self, widget, event):
        if widget == self.window:
            if event.get_coords()[1] > self.notebook.get_allocation().height:
                return
        if event.button == 3:
            self.update_menu_visibility(True)
            GObject.idle_add(self.mainmenu.popup, None, None, None, None,
                             event.button, event.time)

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
                        'remove', 'clear', 'update', 'new', 'edit',
                         'sort', 'tag']:
                self.UIManager.get_widget('/mainmenu/' + menu + 'menu/').hide()
            return
        elif self.current_tab == self.TAB_CURRENT:
            if len(self.currentdata) > 0:
                if self.current_selection.count_selected_rows() > 0:
                    for menu in ['remove', 'tag']:
                        self.UIManager.get_widget('/mainmenu/%smenu/' % \
                                                  (menu,)).show()
                else:
                    for menu in ['remove', 'tag']:
                        self.UIManager.get_widget('/mainmenu/%smenu/' % \
                                                  (menu,)).hide()
                if not self.current.filterbox_visible:
                    for menu in ['clear', 'pl', 'sort']:
                        self.UIManager.get_widget('/mainmenu/%smenu/' % \
                                                  (menu,)).show()
                else:
                    for menu in ['clear', 'pl', 'sort']:
                        self.UIManager.get_widget('/mainmenu/%smenu/' % \
                                                  (menu,)).hide()

            else:
                for menu in ['clear', 'pl', 'sort', 'remove', 'tag']:

                    self.UIManager.get_widget('/mainmenu/%smenu/' % \
                                              (menu,)).hide()

            for menu in ['add', 'replace', 'playafter', 'rename', 'rm', \
                         'update', 'new', 'edit']:
                self.UIManager.get_widget('/mainmenu/' + menu + 'menu/').hide()

        elif self.current_tab == self.TAB_LIBRARY:
            if len(self.librarydata) > 0:
                path_update = '/mainmenu/updatemenu/updateselectedmenu/'
                if self.library_selection.count_selected_rows() > 0:
                    for menu in ['add', 'replace', 'playafter', 'tag', 'pl']:
                        self.UIManager.get_widget('/mainmenu/%smenu/' % \
                                                  (menu,)).show()

                    self.UIManager.get_widget(path_update).show()

                else:
                    for menu in ['add', 'replace', 'playafter', 'tag', 'pl']:
                        self.UIManager.get_widget('/mainmenu/%smenu/' % \
                                                  (menu,)).hide()
                    self.UIManager.get_widget(path_update).hide()
            else:
                for menu in ['add', 'replace', 'playafter',
                             'tag', 'update', 'pl']:
                    self.UIManager.get_widget('/mainmenu/%smenu/' \
                                             % (menu,)).hide()
            for menu in ['remove', 'clear', 'rename', 'rm',
                         'new', 'edit', 'sort']:
                self.UIManager.get_widget('/mainmenu/' + menu + 'menu/').hide()
            if self.library.search_visible():
                self.UIManager.get_widget('/mainmenu/updatemenu/').hide()
            else:
                self.UIManager.get_widget('/mainmenu/updatemenu/').show()
                path_update_full = '/mainmenu/updatemenu/updatefullmenu/'
                self.UIManager.get_widget(path_update_full).show()
        elif self.current_tab == self.TAB_PLAYLISTS:
            if self.playlists_selection.count_selected_rows() > 0:
                for menu in ['add', 'replace', 'playafter', 'rm']:
                    self.UIManager.get_widget('/mainmenu/%smenu/' % \
                                             (menu,)).show()
                if self.playlists_selection.count_selected_rows() == 1:
                    self.UIManager.get_widget('/mainmenu/renamemenu/').show()
                else:
                    self.UIManager.get_widget('/mainmenu/renamemenu/').hide()
            else:
                for menu in ['add', 'replace', 'playafter', 'rm', 'rename']:
                    self.UIManager.get_widget('/mainmenu/%smenu/' % \
                                             (menu,)).hide()
            for menu in ['remove', 'clear', 'pl', 'update',
                         'new', 'edit', 'sort', 'tag']:
                self.UIManager.get_widget('/mainmenu/' + menu + 'menu/').hide()
        elif self.current_tab == self.TAB_STREAMS:
            self.UIManager.get_widget('/mainmenu/newmenu/').show()
            if self.streams_selection.count_selected_rows() > 0:
                if self.streams_selection.count_selected_rows() == 1:
                    self.UIManager.get_widget('/mainmenu/editmenu/').show()
                else:
                    self.UIManager.get_widget('/mainmenu/editmenu/').hide()
                for menu in ['add', 'replace', 'playafter', 'rm']:
                    self.UIManager.get_widget('/mainmenu/%smenu/' % \
                                             (menu,)).show()

            else:
                for menu in ['add', 'replace', 'playafter', 'rm']:
                    self.UIManager.get_widget('/mainmenu/%smenu/' % \
                                             (menu,)).hide()
            for menu in ['rename', 'remove', 'clear',
                         'pl', 'update', 'sort', 'tag']:
                self.UIManager.get_widget('/mainmenu/' + menu + 'menu/').hide()

    def path_to_icon(self, icon_name):
        full_filename = pkg_resources.resource_filename( __name__, \
                                                        "pixmaps/%s" % icon_name)
        if os.path.exists(full_filename):
            return full_filename
        else:
            self.logger.critical("Icon %r cannot be found. Aborting...", icon_name)
            sys.exit(1)

    def on_tags_edit(self, _widget):
        ui.change_cursor(Gdk.Cursor.new(Gdk.CursorType.WATCH))
        while Gtk.events_pending():
            Gtk.main_iteration()

        files = []
        temp_mpdpaths = []
        if self.current_tab == self.TAB_INFO:
            if self.status_is_play_or_pause():
                # Use current file in songinfo:
                mpdpath = mpdh.get(self.songinfo, 'file')
                fullpath = os.path.join(
                    self.config.musicdir[self.config.profile_num], mpdpath)
                files.append(fullpath)
                temp_mpdpaths.append(mpdpath)
        elif self.current_tab == self.TAB_LIBRARY:
            # Populates files array with selected library items:
            items = self.library.get_path_child_filenames(False)
            for item in items:
                files.append(
                    os.path.join(self.config.musicdir[self.config.profile_num],
                                 item))
                temp_mpdpaths.append(item)
        elif self.current_tab == self.TAB_CURRENT:
            # Populates files array with selected current playlist items:
            temp_mpdpaths = self.current.get_selected_filenames(False)
            files = self.current.get_selected_filenames(True)

        tageditor = tagedit.TagEditor(self.window,
                                      self.tags_mpd_update,
                                      self.tags_set_use_mpdpath)
        tageditor.set_use_mpdpaths(self.config.tags_use_mpdpath)
        tageditor.on_tags_edit(files, temp_mpdpaths,
                               self.config.musicdir[self.config.profile_num])

    def tags_set_use_mpdpath(self, use_mpdpath):
        self.config.tags_use_mpdpath = use_mpdpath

    def tags_mpd_update(self, tag_paths):
        self.mpd.update(list(tag_paths))
        self.mpd_update_queued = True

    def on_about(self, _action):
        about_dialog = about.About(self.window,
                                   self.config,
                                   version,
                                   __license__,
                                   self.path_to_icon('sonata_large.png'))

        stats = None
        if self.conn:
            # Extract some MPD stats:
            mpdstats = self.mpd.stats()
            stats = {'artists': mpdstats['artists'],
                 'albums': mpdstats['albums'],
                 'songs': mpdstats['songs'],
                 'db_playtime': mpdstats['db_playtime'],
                 }

        about_dialog.about_load(stats)

    def systemtray_initialize(self):
        # Make system tray 'icon' to sit in the system tray
        self.tray_icon.initialize(
            self.systemtray_click,
            self.systemtray_scroll,
            self.systemtray_activate,
        )

        if self.config.show_trayicon:
            self.tray_icon.show()
        else:
            self.tray_icon.hide()
        self.tray_icon.update_icon(self.path_to_icon('sonata.png'))

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

    def dbus_fullscreen(self):
        self.fullscreen_cover_art(None)

    def main(self):
        Gtk.main()
