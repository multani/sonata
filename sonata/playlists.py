
"""
This module implements a user interface for mpd playlists.

Example usage:
import playlists
self.playlists = playlists.Playlists(self.config, self.window,
self.client, lambda:self.UIManager, self.update_menu_visibility,
self.iterate_now, self.on_add_item, self.on_playlists_button_press,
self.connected, self.TAB_PLAYLISTS)
playlistswindow, playlistsevbox = self.playlists.get_widgets()
...
self.playlists.populate()
...
"""

import os

from gi.repository import Gtk, Pango, Gdk

from sonata import ui, misc, mpdhelper as mpdh

from sonata.pluginsystem import pluginsystem, BuiltinPlugin


class Playlists:

    def __init__(self, config, window, mpd, UIManager,
                 update_menu_visibility, iterate_now, on_add_item,
                 on_playlists_button_press, connected,
                 add_selected_to_playlist, TAB_PLAYLISTS, add_tab):
        self.config = config
        self.window = window
        self.mpd = mpd
        self.UIManager = UIManager
        self.update_menu_visibility = update_menu_visibility
        self.iterate_now = iterate_now # XXX Do we really need this?
        self.on_add_item = on_add_item
        self.on_playlists_button_press = on_playlists_button_press
        self.add_selected_to_playlist = add_selected_to_playlist
        self.connected = connected

        self.mergepl_id = None
        self.actionGroupPlaylists = None
        self.playlist_name_dialog = None

        self.builder = ui.builder('playlists')

        # Playlists tab
        self.playlists = self.builder.get_object('playlists_page_treeview')
        self.playlists_selection = self.playlists.get_selection()
        self.playlistswindow = self.builder.get_object('playlists_page_scrolledwindow')

        self.tab_label = self.builder.get_object('playlists_tab_label')
        self.tab_label.set_text(TAB_PLAYLISTS)

        self.tab_widget = self.builder.get_object('playlists_tab_eventbox')
        self.tab = add_tab(self.playlistswindow, self.tab_widget, TAB_PLAYLISTS,
                           self.playlists)

        self.playlists.connect('button_press_event',
                               self.on_playlists_button_press)
        self.playlists.connect('row_activated', self.playlists_activated)
        self.playlists.connect('key-press-event', self.playlists_key_press)

        # Initialize playlist data and widget
        self.playlistsdata = self.builder.get_object('playlists_liststore')
        self.playlists.set_search_column(1)

    def get_model(self):
        return self.playlistsdata

    def get_widgets(self):
        return self.playlistswindow

    def get_treeview(self):
        return self.playlists

    def get_selection(self):
        return self.playlists_selection

    def populate_playlists_for_menu(self, playlistinfo):
        if self.mergepl_id:
            self.UIManager().remove_ui(self.mergepl_id)
        if self.actionGroupPlaylists:
            self.UIManager().remove_action_group(self.actionGroupPlaylists)
            self.actionGroupPlaylists = None
        self.actionGroupPlaylists = Gtk.ActionGroup('MPDPlaylists')
        self.UIManager().ensure_update()
        actions = [
            ("Playlist: %s" % playlist.replace("&", ""),
             Gtk.STOCK_JUSTIFY_CENTER,
             ui.quote_label(misc.unescape_html(playlist)),
             None, None,
             self.on_playlist_menu_click)
            for playlist in playlistinfo]
        self.actionGroupPlaylists.add_actions(actions)
        uiDescription = """
            <ui>
              <popup name="mainmenu">
                  <menu action="plmenu">
            """
        uiDescription += "".join('<menuitem action=\"%s\"/>' % action[0]
                        for action in actions)
        uiDescription += '</menu></popup></ui>'
        self.mergepl_id = self.UIManager().add_ui_from_string(uiDescription)
        self.UIManager().insert_action_group(self.actionGroupPlaylists, 0)
        self.UIManager().get_widget('/hidden').set_property('visible', False)
        # If we're not on the Current tab, prevent additional menu items
        # from displaying:
        self.update_menu_visibility()

    def on_playlist_save(self, _action):
        plname = self.prompt_for_playlist_name(_("Save Playlist"),
                                               'savePlaylist')
        if plname:
            if self.playlist_name_exists(_("Save Playlist"),
                                         'savePlaylistError', plname):
                return
            self.playlist_create(plname)
            self.mpd.playlistclear(plname)
            self.add_selected_to_playlist(plname)

    def playlist_create(self, playlistname, oldname=None):
        self.mpd.rm(playlistname)
        if oldname is not None:
            self.mpd.rename(oldname, playlistname)
        else:
            self.mpd.save(playlistname)
        self.populate()
        self.iterate_now()

    def on_playlist_menu_click(self, action):
        plname = misc.unescape_html(action.get_name().replace("Playlist: ",
                                                              ""))
        text = ('Would you like to replace the existing playlist or append'
                'these songs?')
        response = ui.show_msg(self.window,
                               _(text), _("Existing Playlist"),
                               "existingPlaylist", (_("Replace playlist"),
                                                    1, _("Append songs"), 2),
                               default=self.config.existing_playlist_option)
        if response == 1: # Overwrite
            self.config.existing_playlist_option = response
            self.mpd.playlistclear(plname)
            self.add_selected_to_playlist(plname)
        elif response == 2: # Append songs:
            self.config.existing_playlist_option = response
            self.add_selected_to_playlist(plname)

    def playlist_name_exists(self, title, role, plname, skip_plname=""):
        # If the playlist already exists, and the user does not want to
        # replace it, return True; In all other cases, return False
        playlists = self.mpd.listplaylists()
        if playlists is None:
            playlists = self.mpd.lsinfo()
        for item in playlists:
            if 'playlist' in item:
                if item['playlist'] == plname and \
                   plname != skip_plname:
                    if ui.show_msg(self.window,
                                   _(('A playlist with this name already '
                                     'exists. Would you like to replace it?')),
                                   title, role, Gtk.ButtonsType.YES_NO) == \
                       Gtk.ResponseType.YES:
                        return False
                    else:
                        return True
        return False

    def prompt_for_playlist_name(self, title, role, oldname=None):
        """Prompt user for playlist name"""
        plname = None
        if self.connected():
            if not self.playlist_name_dialog:
                self.playlist_name_dialog = self.builder.get_object(
                    'playlist_name_dialog')
            self.playlist_name_dialog.set_transient_for(self.window)
            self.playlist_name_dialog.set_title(title)
            self.playlist_name_dialog.set_role(role)
            entry = self.builder.get_object('playlist_name_entry')
            if oldname:
                entry.set_text(oldname)
            else:
                entry.set_text("")
            self.playlist_name_dialog.show_all()
            response = self.playlist_name_dialog.run()
            if response == Gtk.ResponseType.ACCEPT:
                plname = misc.strip_all_slashes(entry.get_text())
            self.playlist_name_dialog.hide()
        return plname

    def populate(self):
        if self.connected():
            self.playlistsdata.clear()
            playlistinfo = []
            playlists = self.mpd.listplaylists()
            if playlists is None:
                playlists = self.mpd.lsinfo()
            for item in playlists:
                if 'playlist' in item:
                    playlistinfo.append(misc.escape_html(item['playlist']))

            # Remove case sensitivity
            playlistinfo.sort(key=lambda x: x.lower())
            for item in playlistinfo:
                self.playlistsdata.append([Gtk.STOCK_DIRECTORY, item])

            self.populate_playlists_for_menu(playlistinfo)

    def on_playlist_rename(self, _action):
        model, selected = self.playlists_selection.get_selected_rows()
        oldname = misc.unescape_html(
            model.get_value(model.get_iter(selected[0]), 1))
        plname = self.prompt_for_playlist_name(_("Rename Playlist"),
                                               'renamePlaylist', oldname)
        if plname:
            if self.playlist_name_exists(_("Rename Playlist"),
                                         'renamePlaylistError',
                                         plname, oldname):
                return
            self.playlist_create(plname, oldname)
            # Re-select item:
            row = 0
            for pl in self.playlistsdata:
                if pl[1] == plname:
                    self.playlists_selection.select_path((row,))
                    return
                row = row + 1

    def playlists_key_press(self, widget, event):
        if event.keyval == Gdk.keyval_from_name('Return'):
            self.playlists_activated(widget, widget.get_cursor()[0])
            return True

    def playlists_activated(self, _treeview, _path, _column=0):
        self.on_add_item(None)
