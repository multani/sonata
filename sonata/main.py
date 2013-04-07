
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

from gi.repository import Gtk, Gdk, GdkPixbuf, GLib, Pango

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
                dbus_plugin as dbus
from sonata.song import SongRecord

from sonata.version import version


class Base:

    ### XXX Warning, a long __init__ ahead:

    def __init__(self, args):
        self.logger = logging.getLogger(__name__)

        # The following attributes were used but not defined here before:
        self.album_current_artist = None

        self.allow_art_search = None
        self.choose_dialog = None
        self.image_local_dialog = None
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

        self.lyrics_search_dialog = None

        self.mpd = mpdh.MPDClient()
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
        self.all_tab_ids = "current library playlists streams info".split()
        self.tabname2id = dict(zip(self.all_tab_names, self.all_tab_ids))
        self.tabid2name = dict(zip(self.all_tab_ids, self.all_tab_names))
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

        self.builder = ui.builder('sonata')
        self.provider = ui.css_provider('sonata')

        icon_factory_src = ui.builder_string('icons')
        icon_path = pkg_resources.resource_filename(__name__, "pixmaps")
        icon_factory_src = icon_factory_src.format(base_path=icon_path)
        self.builder.add_from_string(icon_factory_src)
        icon_factory = self.builder.get_object('sonata_iconfactory')
        Gtk.IconFactory.add_default(icon_factory)

        # Main window
        self.window = self.builder.get_object('main_window')

        if self.config.ontop:
            self.window.set_keep_above(True)
        if self.config.sticky:
            self.window.stick()
        if not self.config.decorated:
            self.window.set_decorated(False)
        self.preferences.window = self.window

        self.notebook = self.builder.get_object('main_notebook')
        self.album_image = self.builder.get_object('main_album_image')
        self.tray_album_image = self.builder.get_object('tray_album_image')

        # Fullscreen cover art window
        self.fullscreen_window = self.builder.get_object("fullscreen_window")
        self.fullscreen_window.fullscreen()
        bgcolor = Gdk.RGBA()
        bgcolor.parse("black")
        self.fullscreen_window.override_background_color(Gtk.StateFlags.NORMAL,
                                                         bgcolor)
        self.fullscreen_image = self.builder.get_object("fullscreen_image")
        fullscreen_label1 = self.builder.get_object("fullscreen_label_1")
        fullscreen_label2 = self.builder.get_object("fullscreen_label_2")
        if not self.config.show_covers:
            self.fullscreen_image.hide()

        # Artwork
        self.artwork = artwork.Artwork(
            self.config, misc.is_lang_rtl(self.window),
            self.schedule_gc_collect, self.target_image_filename,
            self.imagelist_append, self.remotefilelist_append,
            self.set_allow_art_search, self.status_is_play_or_pause,
            self.get_current_song_text, self.album_image, self.tray_album_image,
            self.fullscreen_image, fullscreen_label1, fullscreen_label2)


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
            ('fullscreen_window_menu', Gtk.STOCK_FULLSCREEN,
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
            (self.tabname2id[self.TAB_CURRENT], None, self.TAB_CURRENT,
             None, None, self.on_tab_toggle, self.config.current_tab_visible),
            (self.tabname2id[self.TAB_LIBRARY], None, self.TAB_LIBRARY,
             None, None, self.on_tab_toggle, self.config.library_tab_visible),
            (self.tabname2id[self.TAB_PLAYLISTS], None, self.TAB_PLAYLISTS,
             None, None, self.on_tab_toggle, self.config.playlists_tab_visible),
            (self.tabname2id[self.TAB_STREAMS], None, self.TAB_STREAMS,
             None, None, self.on_tab_toggle, self.config.streams_tab_visible),
            (self.tabname2id[self.TAB_INFO], None, self.TAB_INFO,
             None, None, self.on_tab_toggle, self.config.info_tab_visible), ]

        uiDescription = """
            <ui>
              <popup name="imagemenu">
                <menuitem action="chooseimage_menu"/>
                <menuitem action="localimage_menu"/>
                <menuitem action="fullscreen_window_menu"/>
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
                <menuitem action="fullscreen_window_menu"/>
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
                     for name in self.all_tab_ids)#FIXME

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

        # Current tab
        self.current = current.Current(
            self.config, self.mpd, self.TAB_CURRENT,
            self.on_current_button_press, self.connected,
            lambda: self.sonata_loaded, lambda: self.songinfo,
            self.update_statusbar, self.iterate_now, self.add_tab)

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
            self.settings_save, self.current.filter_key_pressed,
            self.on_add_item, self.connected, self.on_library_button_press,
            self.add_tab, self.get_multicd_album_root_dir)

        self.library_treeview = self.library.get_treeview()
        self.library_selection = self.library.get_selection()

        libraryactions = self.library.get_libraryactions()

        # Info tab
        self.info = info.Info(self.config, linkcolor, self.on_link_click,
                              self.get_playing_song,
                              self.TAB_INFO, self.on_image_activate,
                              self.on_image_motion_cb, self.on_image_drop_cb,
                              self.album_return_artist_and_tracks,
                              self.add_tab)
        self.artwork.connect('artwork-changed',
                             self.info.on_artwork_changed)
        self.artwork.connect('artwork-reset',
                             self.info.on_artwork_reset)
        self.info_imagebox = self.info.get_info_imagebox()

        # Streams tab
        self.streams = streams.Streams(self.config, self.window,
                                       self.on_streams_button_press,
                                       self.on_add_item,
                                       self.settings_save,
                                       self.TAB_STREAMS,
                                       self.add_tab)

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
                                             self.connected,
                                             self.add_selected_to_playlist,
                                             self.TAB_PLAYLISTS,
                                             self.add_tab)

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
        accel_group = self.UIManager.get_accel_group()
        self.fullscreen_window.add_accel_group(accel_group)
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

        self.imageeventbox = self.builder.get_object('image_event_box')
        self.imageeventbox.drag_dest_set(Gtk.DestDefaults.HIGHLIGHT |
                                         Gtk.DestDefaults.DROP,
                                         [Gtk.TargetEntry.new("text/uri-list", 0, 80),
                                          Gtk.TargetEntry.new("text/plain", 0, 80)],
                                         Gdk.DragAction.DEFAULT)
        if not self.config.show_covers:
            self.imageeventbox.hide()
        self.prevbutton = self.builder.get_object('prev_button')
        self.ppbutton = self.builder.get_object('playpause_button')
        self.ppbutton_image = self.builder.get_object('playpause_button_image')
        self.stopbutton = self.builder.get_object('stop_button')
        self.nextbutton = self.builder.get_object('next_button')
        for mediabutton in (self.prevbutton, self.ppbutton, self.stopbutton,
                            self.nextbutton):
            if not self.config.show_playback:
                ui.hide(mediabutton)
        self.progressbox = self.builder.get_object('progress_box')
        self.progressbar = self.builder.get_object('progress_bar')

        self.progresseventbox = self.builder.get_object('progress_event_box')
        if not self.config.show_progress:
            ui.hide(self.progressbox)
        self.volumebutton = self.builder.get_object('volume_button')
        if not self.config.show_playback:
            ui.hide(self.volumebutton)
        self.expander = self.builder.get_object('expander')
        self.expander.set_expanded(self.config.expanded)
        self.cursonglabel1 = self.builder.get_object('current_label_1')
        self.cursonglabel2 = self.builder.get_object('current_label_2')
        expanderbox = self.builder.get_object('expander_label_widget')
        self.expander.set_label_widget(expanderbox)
        self.statusbar = self.builder.get_object('main_statusbar')
        if not self.config.show_statusbar or not self.config.expanded:
            ui.hide(self.statusbar)
        self.window.move(self.config.x, self.config.y)
        self.window.set_size_request(270, -1)
        songlabel1 = '<big>{}</big>'.format(_('Stopped'))
        self.cursonglabel1.set_markup(songlabel1)
        if not self.config.expanded:
            ui.hide(self.notebook)
            songlabel2 = _('Click to expand')
            self.window.set_default_size(self.config.w, 1)
        else:
            songlabel2 = _('Click to collapse')
            self.window.set_default_size(self.config.w, self.config.h)
        songlabel2 = '<small>{}</small>'.format(songlabel2)
        self.cursonglabel2.set_markup(songlabel2)

        self.expander.set_tooltip_text(self.cursonglabel1.get_text())
        if not self.conn:
            self.progressbar.set_text(_('Not Connected'))
        elif not self.status:
            self.progressbar.set_text(_('No Read Permission'))

        # Update tab positions:
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
        self.tray_v_box = self.builder.get_object('tray_v_box')

        if not self.config.show_covers:
            self.tray_album_image.hide()

        self.tray_current_label1 = self.builder.get_object('tray_label_1')
        self.tray_current_label2 = self.builder.get_object('tray_label_2')

        self.tray_progressbar = self.builder.get_object('tray_progressbar')
        if not self.config.show_progress:
            ui.hide(self.tray_progressbar)

        self.tray_v_box.show_all()
        self.traytips.add_widget(self.tray_v_box)
        self.tooltip_set_window_width()

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

        self.fullscreen_window.add_events(Gdk.EventMask.BUTTON_PRESS_MASK)
        self.fullscreen_window.connect("button-press-event",
                                       self.fullscreen_cover_art_close, False)
        self.fullscreen_window.connect("key-press-event",
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
        if self.config.withdrawn:
            while Gtk.events_pending():
                Gtk.main_iteration()

        dbus.init_gnome_mediakeys(self.mpd_pp, self.mpd_stop, self.mpd_prev,
                                  self.mpd_next)

        # XXX find new multimedia key library here, in case we don't have gnome!
        #if not dbus.using_gnome_mediakeys():
        #    pass

        # Initialize playlist data and widget
        self.playlistsdata = self.playlists.get_model()

        # Initialize streams data and widget
        self.streamsdata = self.streams.get_model()

        # Initialize library data and widget
        self.librarydata = self.library.get_model()
        self.artwork.library_artwork_init(self.librarydata,
                                          consts.LIB_COVER_SIZE)

        icon = self.window.render_icon('sonata', Gtk.IconSize.DIALOG)
        self.window.set_icon(icon)
        self.streams.populate()

        self.iterate_now()
        if self.config.withdrawn and self.tray_icon.is_visible():
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

        GLib.idle_add(self.header_save_column_widths)

        pluginsystem.notify_of('tab_construct',
                       self.on_enable_tab,
                       self.on_disable_tab)

    ### Tab system:

    def on_enable_tab(self, _plugin, tab):
        tab_parts = tab()
        name = tab_parts[2]
        self.plugintabs[name] = self.add_tab(*tab_parts)

    def on_disable_tab(self, _plugin, tab):
        name = tab()[2]
        tab = self.plugintabs.pop(name)
        self.notebook.remove(tab)

    def add_tab(self, page, label_widget, text, focus):
        label_widget.show_all()
        label_widget.connect("button_press_event", self.on_tab_click)

        self.notebook.append_page(page, label_widget)
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
        return (self.cursonglabel1.get_text(), self.cursonglabel2.get_text())

    def set_allow_art_search(self):
        self.allow_art_search = True

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
        self.iterate_handler = GLib.timeout_add(self.iterate_time, self.iterate)

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
            GLib.source_remove(self.iterate_handler)
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
            return self.on_remove(None)
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
            self.current.clear()
            self.tray_icon.update_icon('sonata-disconnect')
            self.info_update(True)
            if self.current.filterbox_visible:
                GLib.idle_add(self.current.searchfilter_toggle, None)
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
            GLib.idle_add(self.mainmenu.popup, None, None, None, None,
                          event.button, event.time)
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
                self.ppbutton_image.set_from_stock(Gtk.STOCK_MEDIA_PLAY,
                                                   Gtk.IconSize.BUTTON)
                self.UIManager.get_widget('/traymenu/playmenu').show()
                self.UIManager.get_widget('/traymenu/pausemenu').hide()
                icon = 'sonata'
            elif self.status['state'] == 'pause':
                self.ppbutton_image.set_from_stock(Gtk.STOCK_MEDIA_PLAY,
                                                   Gtk.IconSize.BUTTON)
                self.UIManager.get_widget('/traymenu/playmenu').show()
                self.UIManager.get_widget('/traymenu/pausemenu').hide()
                icon = 'sonata-pause'
            elif self.status['state'] == 'play':
                self.ppbutton_image.set_from_stock(Gtk.STOCK_MEDIA_PAUSE,
                                                   Gtk.IconSize.BUTTON)
                self.UIManager.get_widget('/traymenu/playmenu').hide()
                self.UIManager.get_widget('/traymenu/pausemenu').show()
                if self.prevstatus != None:
                    if self.prevstatus['state'] == 'pause':
                        # Forces the notification to popup if specified
                        self.on_currsong_notify()
                icon = 'sonata-play'
            else:
                icon = 'sonata-disconnect'

            self.tray_icon.update_icon(icon)
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
                                         self.songinfo.artist]
        else:
            self.album_current_artist = [self.songinfo, ""]

    def handle_change_song(self):
        # Called when one of the following items are changed for the current
        # mpd song in the playlist:
        #  1. Song tags or filename (e.g. if tags are edited)
        #  2. Position in playlist (e.g. if playlist is sorted)
        # Note that the song does not have to be playing; it can reflect the
        # next song that will be played.
        self.current.on_song_change(self.status)

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
                    time = misc.convert_time(self.songinfo.time)
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
                days = None
                # FIXME _ is for localization, temporarily __
                hours, mins, __ = misc.convert_time_raw(self.current.total_time)
                # Show text:
                songs_count = int(self.status['playlistlength'])
                songs_text = ngettext('{count} song', '{count} songs',
                                     songs_count).format(count=songs_count)
                time_parts = []
                if hours >= 24:
                    days = int(hours / 24)
                    hours = hours - (days * 24)
                if days:
                    days_text = ngettext('{count} day', '{count} days',
                                         days).format(count=days)
                    time_parts.append(days_text)
                if hours:
                    hours_text = ngettext('{count} hour', '{count} hours',
                                          hours).format(count=hours)
                    time_parts.append(hours_text)
                if mins:
                    mins_text = ngettext('{count} minute', '{count} minutes',
                                         mins).format(count=mins)
                    time_parts.append(mins_text)
                time_text = ', '.join([part for part in time_parts if part])
                if int(self.status['playlistlength']) > 0:
                    status_text = "{}: {}".format(songs_text, time_text)
                else:
                    status_text = ''
                if updatingdb:
                    update_text = _('(updating mpd)')
                    status_text = "{}: {}".format(status_text, update_text)
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
                self.tray_progressbar.show()
            self.tray_current_label2.show()
            if self.config.show_covers:
                self.tray_album_image.show()

            for label in (self.cursonglabel1, self.cursonglabel2,
                          self.tray_current_label1, self.tray_current_label2):
                label.set_ellipsize(Pango.EllipsizeMode.END)


            if len(self.config.currsongformat1) > 0:
                newlabel1 = formatting.parse(self.config.currsongformat1,
                                             self.songinfo, True)
            else:
                newlabel1 = ''
            newlabel1 = '<big>{}</big>'.format(newlabel1)
            if len(self.config.currsongformat2) > 0:
                newlabel2 = formatting.parse(self.config.currsongformat2,
                                             self.songinfo, True)
            else:
                newlabel2 = ''
            newlabel2 = '<small>{}</small>'.format(newlabel2)
            if newlabel1 != self.cursonglabel1.get_label():
                self.cursonglabel1.set_markup(newlabel1)
            if newlabel2 != self.cursonglabel2.get_label():
                self.cursonglabel2.set_markup(newlabel2)
            if newlabel1 != self.tray_current_label1.get_label():
                self.tray_current_label1.set_markup(newlabel1)
            if newlabel2 != self.tray_current_label2.get_label():
                self.tray_current_label2.set_markup(newlabel2)
            self.expander.set_tooltip_text('%s\n%s' % \
                                           (self.cursonglabel1.get_text(),
                                            self.cursonglabel2.get_text(),))
        else:
            for label in (self.cursonglabel1, self.cursonglabel2,
                          self.tray_current_label1, self.cursonglabel2):
                label.set_ellipsize(Pango.EllipsizeMode.NONE)

            newlabel1 = '<big>{}</big>'.format(_('Stopped'))
            self.cursonglabel1.set_markup(newlabel1)
            if self.config.expanded:
                newlabel2 = _('Click to collapse')
            else:
                newlabel2 = _('Click to expand')
            newlabel2 = '<small>{}</small>'.format(newlabel2)
            self.cursonglabel2.set_markup(newlabel2)
            self.expander.set_tooltip_text(self.cursonglabel1.get_text())
            if not self.conn:
                traylabel1 = _('Not Connected')
            elif not self.status:
                traylabel1 = _('No Read Permission')
            else:
                traylabel1 = _('Stopped')
            traylabel1 = '<big>{}</big>'.format(traylabel1)
            self.tray_current_label1.set_markup(traylabel1)
            self.tray_progressbar.hide()
            self.tray_album_image.hide()
            self.tray_current_label2.hide()
        self.update_infofile()

    def update_wintitle(self):
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
        if self.fullscreen_window.get_property('visible'):
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
                    GLib.source_remove(self.traytips.notif_handler)
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
                            self.traytips.notif_handler = GLib.timeout_add(
                                timeout, self.traytips.hide)
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
        self.tray_progressbar.set_fraction(self.progressbar.get_fraction())

    def on_progressbar_notify_text(self, *_args):
        self.tray_progressbar.set_text(self.progressbar.get_text())

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

                if self.songinfo.artist:
                    info_file.write('Title: %s - %s\n' % (
                        self.songinfo.artist,
                        (self.songinfo.title or '')))
                else:
                    # No Artist in streams
                    try:
                        info_file.write('Title: %s\n' % (self.songinfo.title or ''))
                    except:
                        info_file.write('Title: No - ID Tag\n')
                info_file.write('Album: %s\n' % (self.songinfo.album or 'No Data'))
                info_file.write('Track: %s\n' % self.songinfo.track)
                info_file.write('File: %s\n' % (self.songinfo.file or 'No Data'))
                info_file.write('Time: %s\n' % self.songinfo.time)
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
            GLib.idle_add(self.header_save_column_widths)

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
                self.cursonglabel2.set_text(_('Click to collapse'))
            else:
                self.cursonglabel2.set_text(_('Click to expand'))
        # Now we wait for the height of the player to increase, so that
        # we know the list is visible. This is pretty hacky, but works.
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
                GLib.idle_add(self.current.center_song_in_list)

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
                GLib.source_remove(self.seekidle)
            except:
                pass
            self.seekidle = GLib.idle_add(self._seek_when_idle, event.direction)
        return True

    def _seek_when_idle(self, direction):
        at, _length = [int(c) for c in self.status['time'].split(':')]
        try:
            if direction == Gdk.ScrollDirection.UP:
                seektime = max(0, at + 5)
            elif direction == Gdk.ScrollDirection.DOWN:
                seektime = min(self.songinfo.time, at - 5)
            self.seek(int(self.status['song']), seektime)
        except:
            pass

    def on_lyrics_search(self, _event):
        artist = self.songinfo.artist or ''
        title = self.songinfo.title or ''
        if not self.lyrics_search_dialog:
            self.lyrics_search_dialog = self.builder.get_object(
                'lyrics_search_dialog')
        artist_entry = self.builder.get_object('lyrics_search_artist_entry')
        artist_entry.set_text(artist)
        title_entry = self.builder.get_object('lyrics_search_title_entry')
        title_entry.set_text(title)
        self.lyrics_search_dialog.show_all()
        response = self.lyrics_search_dialog.run()
        if response == Gtk.ResponseType.ACCEPT:
            # Search for new lyrics:
            self.info.get_lyrics_start(
                artist_entry.get_text(),
                title_entry.get_text(),
                artist,
                title,
                os.path.dirname(self.songinfo.file),
                force_fetch=True)

        self.lyrics_search_dialog.hide()

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
        GLib.idle_add(self.mainmenu.popup, None, None, None, None, 3, 0)

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
            GLib.idle_add(self.on_notebook_resize, self.notebook, None)
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
                artist = self.songinfo.artist
                album = self.songinfo.album
                stream = self.songinfo.name
            if not (artist or album or stream):
                self.UIManager.get_widget(path_localimage).hide()
                self.UIManager.get_widget(path_resetimage).hide()
                self.UIManager.get_widget(path_chooseimage).hide()
            self.imagemenu.popup(None, None, None, None, event.button, event.time)
        GLib.timeout_add(50, self.on_image_activate_after)
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
                stream = self.songinfo.name
                if stream is not None:
                    dest_filename = self.artwork.artwork_stream_filename(stream)
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
                album = self.songinfo.album or ""
            if not artist:
                artist = self.album_current_artist[1]
            album = album.replace("/", "")
            artist = artist.replace("/", "")
            if songpath is None:
                songpath = os.path.dirname(self.songinfo.file)
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
            return targetfile

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
        album = self.songinfo.album or ''
        songs, _playtime, _num_songs = \
                self.library.library_return_search_items(album=album)
        for song in songs:
            year = song.date or ''
            artist = song.artist or ''
            path = os.path.dirname(song.file)
            data = SongRecord(album=album, artist=artist, year=year, path=path)
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
                       str(self.songinfo.artist or '').lower() \
                       or dataitem.artist == library.VARIOUS_ARTISTS \
                       and dataitem.path == \
                       os.path.dirname(self.songinfo.file):

                        datalist = [dataitem]
                        break
            # Find all songs in album:
            retsongs = []
            for song in songs:
                if (song.album or '').lower() == datalist[0].album.lower() \
                   and song.date == datalist[0].year \
                   and (datalist[0].artist == library.VARIOUS_ARTISTS \
                        or datalist[0].artist.lower() ==  \
                        (song.artist or '').lower()):
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
                pixbuf = GdkPixbuf.PixbufAnimation.new_from_file(filename)
                pixbuf = pixbuf.get_static_image()
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
            pixbuf = GdkPixbuf.Pixbuf.new(GdkPixbuf.Colorspace.RGB, 1, 8,
                                          128, 128)
            pixbuf.fill(0x00000000)
        preview.set_from_pixbuf(pixbuf)
        have_preview = True
        file_chooser.set_preview_widget_active(have_preview)
        del pixbuf
        self.call_gc_collect = True

    def _image_local_init(self):
        self.image_local_dialog = self.builder.get_object(
            'local_artwork_dialog')
        filefilter = Gtk.FileFilter()
        filefilter.set_name(_("Images"))
        filefilter.add_pixbuf_formats()
        self.image_local_dialog.add_filter(filefilter)
        filefilter = Gtk.FileFilter()
        filefilter.set_name(_("All files"))
        filefilter.add_pattern("*")
        self.image_local_dialog.add_filter(filefilter)
        preview = self.builder.get_object('local_art_preview_image')
        self.image_local_dialog.connect("update-preview",
                                        self.update_preview, preview)

    def image_local(self, _widget):
        if not self.image_local_dialog:
            self._image_local_init()
        stream = self.songinfo.name
        album = (self.songinfo.album or "").replace("/", "")
        artist = self.album_current_artist[1].replace("/", "")
        songdir = os.path.dirname(self.songinfo.file)
        currdir = os.path.join(self.config.musicdir[self.config.profile_num],
                               songdir)
        if self.config.art_location != consts.ART_LOCATION_HOMECOVERS:
            dialog.set_current_folder(currdir)
        if stream is not None:
            # Allow saving an image file for a stream:
            self.local_dest_filename = self.artwork.artwork_stream_filename(
                stream)
        else:
            self.local_dest_filename = self.target_image_filename()
        self.image_local_dialog.show_all()
        response = self.image_local_dialog.run()

        if response == Gtk.ResponseType.OK:
            filename = self.image_local_dialog.get_filenames()[0]
            # Copy file to covers dir:
            if self.local_dest_filename != filename:
                shutil.copyfile(filename, self.local_dest_filename)
            # And finally, set the image in the interface:
            self.artwork.artwork_update(True)
            # Force a resize of the info labels, if needed:
            GLib.idle_add(self.on_notebook_resize, self.notebook, None)
        self.image_local_dialog.hide()

    def imagelist_append(self, elem):
        self.imagelist.append(elem)

    def remotefilelist_append(self, elem):
        self.remotefilelist.append(elem)

    def _init_choose_dialog(self):
        self.choose_dialog = self.builder.get_object('artwork_dialog')
        self.imagelist = self.builder.get_object('artwork_liststore')
        self.remote_artistentry = self.builder.get_object('artwork_artist_entry')
        self.remote_albumentry = self.builder.get_object('artwork_album_entry')
        self.image_widget = self.builder.get_object('artwork_iconview')
        refresh_button = self.builder.get_object('artwork_update_button')
        refresh_button.connect('clicked', self.image_remote_refresh,
                               self.image_widget)
        self.remotefilelist = []

    def image_remote(self, _widget):
        if not self.choose_dialog:
            self._init_choose_dialog()
        stream = self.songinfo.name
        if stream is not None:
            # Allow saving an image file for a stream:
            self.remote_dest_filename = self.artwork.artwork_stream_filename(
                stream)
        else:
            self.remote_dest_filename = self.target_image_filename()
        album = self.songinfo.album or ''
        artist = self.album_current_artist[1]
        self.image_widget.connect('item-activated', self.image_remote_replace_cover,
                            artist.replace("/", ""), album.replace("/", ""),
                            stream)
        self.choose_dialog.connect('response', self.image_remote_response,
                                   self.image_widget, artist, album, stream)
        self.remote_artistentry.set_text(artist)
        self.remote_albumentry.set_text(album)
        self.allow_art_search = True
        self.chooseimage_visible = True
        self.image_remote_refresh(None, self.image_widget)
        self.choose_dialog.show_all()
        self.choose_dialog.run()

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
        imagewidget.grab_focus()
        ui.change_cursor(Gdk.Cursor.new(Gdk.CursorType.WATCH))
        thread = threading.Thread(target=self._image_remote_refresh,
                                  args=(imagewidget, None))
        thread.daemon = True
        thread.start()

    def _image_remote_refresh(self, imagewidget, _ignore):
        self.artwork.stop_art_update = False
        # Retrieve all images from cover plugins
        artist_search = self.remote_artistentry.get_text()
        album_search = self.remote_albumentry.get_text()
        if len(artist_search) == 0 and len(album_search) == 0:
            GLib.idle_add(self.image_remote_no_tag_found, imagewidget)
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
                GLib.idle_add(self.image_remote_no_covers_found, imagewidget)
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
                GLib.idle_add(self.on_notebook_resize, self.notebook, None)
            except:
                dialog.hide()
        else:
            dialog.hide()
        ui.change_cursor(None)
        self.chooseimage_visible = False

    def image_remote_replace_cover(self, _iconview, path, _artist, _album,
                                   _stream):
        self.artwork.artwork_stop_update()
        image_num = path.get_indices()[0]
        if len(self.remotefilelist) > 0:
            filename = self.remotefilelist[image_num]
            if os.path.exists(filename):
                shutil.move(filename, self.remote_dest_filename)
                # And finally, set the image in the interface:
                self.artwork.artwork_update(True)
                # Clean up..
                misc.remove_dir_recursive(os.path.dirname(filename))
        self.chooseimage_visible = False
        self.choose_dialog.hide()
        while self.artwork.artwork_is_downloading_image():
            Gtk.main_iteration()

    def fullscreen_cover_art(self, _widget):
        if self.fullscreen_window.get_property('visible'):
            self.fullscreen_window.hide()
        else:
            self.traytips.hide()
            self.artwork.fullscreen_cover_art_set_image(force_update=True)
            self.fullscreen_window.show_all()
            # setting up invisible cursor
            window = self.fullscreen_window.get_window()
            window.set_cursor(Gdk.Cursor.new(Gdk.CursorType.BLANK_CURSOR))

    def fullscreen_cover_art_close(self, _widget, event, key_press):
        if key_press:
            shortcut = Gtk.accelerator_name(event.keyval, event.get_state())
            shortcut = shortcut.replace("<Mod2>", "")
            if shortcut != 'Escape':
                return
        self.fullscreen_window.hide()

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
            GLib.timeout_add(100, self.tooltip_set_ignore_toggle_signal_false)

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
        GLib.timeout_add(500, self.tooltip_set_ignore_toggle_signal_false)

    def tooltip_set_ignore_toggle_signal_false(self):
        self.ignore_toggle_signal = False

    # Change volume on mousewheel over systray icon:
    def systemtray_scroll(self, widget, event):
        direction = event.get_scroll_direction()[1]
        if self.conn:
            if direction == Gdk.ScrollDirection.UP:
                self.on_volume_raise()
            elif direction == Gdk.ScrollDirection.DOWN:
                self.on_volume_lower()

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
    def on_volume_lower(self, _action=None):
        new_volume = int(self.volumebutton.get_value()) - 5
        self.volumebutton.set_value(new_volume)

    def on_volume_raise(self, _action=None):
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
            self.current.initialize_columns()

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
        self.window.set_keep_above(self.config.ontop)

    def prefs_sticky_toggled(self, button):
        self.config.sticky = button.get_active()
        if self.config.sticky:
            self.window.stick()
        else:
            self.window.unstick()

    def prefs_decorated_toggled(self, button, prefs_window):
        self.config.decorated = not button.get_active()
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
        for widget in [self.progressbox, self.tray_progressbar]:
            func(widget)

    # FIXME move into prefs or elsewhere?
    def prefs_art_toggled(self, button, art_prefs):
        button_active = button.get_active()
        art_prefs.set_sensitive(button_active)

        #art_hbox2.set_sensitive(button_active)
        #art_stylized.set_sensitive(button_active)
        if button_active:
            self.traytips.set_size_request(self.notification_width, -1)
            self.artwork.artwork_set_default_icon()
            for widget in [self.imageeventbox, self.info_imagebox,
                           self.tray_album_image]:
                widget.set_no_show_all(False)
                if widget is self.tray_album_image:
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
                           self.tray_album_image]:
                widget.hide()
            self.config.show_covers = False
            self.update_cursong()

        # Force a resize of the info labels, if needed:
        GLib.idle_add(self.on_notebook_resize, self.notebook, None)

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
                GLib.source_remove(self.traytips.notif_handler)
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
                          urllib.parse.quote(self.songinfo.artist or '')),
                self.config.url_browser, self.window)
        elif linktype == 'album':
            browser_not_loaded = not misc.browser_load(
                '%s%s' % (wikipedia_search,
                          urllib.parse.quote(self.songinfo.album or '')),
                self.config.url_browser, self.window)
        elif linktype == 'edit':
            if self.songinfo:
                self.on_tags_edit(None)
        elif linktype == 'search':
            self.on_lyrics_search(None)

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

        # FIXME when new UI is done, the top branch expression wins
        if notebook.get_tab_label(tab).get_children and \
            len(notebook.get_tab_label(tab).get_children()) is 2:
            child = notebook.get_tab_label(tab).get_children()[1]
        else:
            child = notebook.get_tab_label(tab).get_child().get_children()[1]
        return child.get_text()

    def on_notebook_page_change(self, _notebook, _page, page_num):
        self.current_tab = self.notebook_get_tab_text(self.notebook, page_num)
        to_focus = self.tabname2focus.get(self.current_tab, None)
        if to_focus:
            GLib.idle_add(to_focus.grab_focus)

        GLib.idle_add(self.update_menu_visibility)
        if not self.img_clicked:
            self.last_tab = self.current_tab

    def on_window_click(self, _widget, event):
        if event.button == 3:
            self.menu_popup(self.window, event)

    def menu_popup(self, widget, event):
        if widget == self.window:
            # Prevent the popup from statusbar (if present)
            height = event.get_coords()[1]
            if height > self.notebook.get_allocation().height:
                return
        if event.button == 3:
            self.update_menu_visibility(True)
            GLib.idle_add(self.mainmenu.popup, None, None, None, None,
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
        tabnum = self.notebook_get_tab_num(self.notebook, self.tabid2name[name])
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
            # XXX this should move to the current.py module
            if not self.current.is_empty():
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

    def on_tags_edit(self, _widget):
        ui.change_cursor(Gdk.Cursor.new(Gdk.CursorType.WATCH))
        while Gtk.events_pending():
            Gtk.main_iteration()

        files = []
        temp_mpdpaths = []
        if self.current_tab == self.TAB_INFO:
            if self.status_is_play_or_pause():
                # Use current file in songinfo:
                mpdpath = self.songinfo.file
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
        about_dialog = about.About(self.window, self.config, version,
                                   __license__)

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
        self.tray_icon.update_icon('sonata')

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

