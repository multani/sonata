
"""
This module implements a user interface for mpd playlists.

Example usage:
import playlists
self.playlists = playlists.Playlists(self.config, self.window, self.client, lambda:self.UIManager, self.update_menu_visibility, self.iterate_now, self.on_add_item, self.on_playlists_button_press, self.get_current_songs, self.connected, self.TAB_PLAYLISTS)
playlistswindow, playlistsevbox = self.playlists.get_widgets()
...
self.playlists.populate()
...
"""

import gtk, pango

import ui, misc
import mpdhelper as mpdh

class Playlists(object):
    def __init__(self, config, window, client, UIManager, update_menu_visibility, iterate_now, on_add_item, on_playlists_button_press, get_current_songs, connected, TAB_PLAYLISTS, new_tab):
        self.config = config
        self.window = window
        self.client = client
        self.UIManager = UIManager
        self.update_menu_visibility = update_menu_visibility
        self.iterate_now = iterate_now # XXX Do we really need this?
        self.on_add_item = on_add_item
        self.on_playlists_button_press = on_playlists_button_press
        self.get_current_songs = get_current_songs
        self.connected = connected

        self.mergepl_id = None
        self.actionGroupPlaylists = None

        # Playlists tab
        self.playlists = ui.treeview()
        self.playlists_selection = self.playlists.get_selection()
        self.playlistswindow = ui.scrollwindow(add=self.playlists)

        self.tab = new_tab(self.playlistswindow, gtk.STOCK_JUSTIFY_CENTER, TAB_PLAYLISTS)

        self.playlists.connect('button_press_event', self.on_playlists_button_press)
        self.playlists.connect('row_activated', self.playlists_activated)
        self.playlists.connect('key-press-event', self.playlists_key_press)

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
        self.actionGroupPlaylists = gtk.ActionGroup('MPDPlaylists')
        self.UIManager().ensure_update()
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
        self.mergepl_id = self.UIManager().add_ui_from_string(uiDescription)
        self.UIManager().insert_action_group(self.actionGroupPlaylists, 0)
        self.UIManager().get_widget('/hidden').set_property('visible', False)
        # If we're not on the Current tab, prevent additional menu items
        # from displaying:
        self.update_menu_visibility()

    def on_playlist_save(self, _action):
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
        self.populate()
        self.iterate_now()

    def on_playlist_menu_click(self, action):
        plname = misc.unescape_html(action.get_name().replace("Playlist: ", ""))
        response = ui.show_msg(self.window, _("Would you like to replace the existing playlist or append these songs?"), _("Existing Playlist"), "existingPlaylist", (_("Replace playlist"), 1, _("Append songs"), 2), default=self.config.existing_playlist_option)
        if response == 1: # Overwrite
            self.config.existing_playlist_option = response
            self.playlist_create(plname)
        elif response == 2: # Append songs:
            self.config.existing_playlist_option = response
            mpdh.call(self.client, 'command_list_ok_begin')
            for song in self.get_current_songs():
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
            if 'playlist' in item:
                if mpdh.get(item, 'playlist') == plname and plname != skip_plname:
                    if ui.show_msg(self.window, _("A playlist with this name already exists. Would you like to replace it?"), title, role, gtk.BUTTONS_YES_NO) == gtk.RESPONSE_YES:
                        return False
                    else:
                        return True
        return False

    def prompt_for_playlist_name(self, title, role):
        plname = None
        if self.connected():
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

    def populate(self):
        if self.connected():
            self.playlistsdata.clear()
            playlistinfo = []
            playlists = mpdh.call(self.client, 'listplaylists')
            if playlists is None:
                playlists = mpdh.call(self.client, 'lsinfo')
            for item in playlists:
                if 'playlist' in item:
                    playlistinfo.append(misc.escape_html(mpdh.get(item, 'playlist')))
            playlistinfo.sort(key=lambda x: x.lower()) # Remove case sensitivity
            for item in playlistinfo:
                self.playlistsdata.append([gtk.STOCK_JUSTIFY_FILL, item])
            if mpdh.mpd_major_version(self.client) >= 0.13:
                self.populate_playlists_for_menu(playlistinfo)

    def on_playlist_rename(self, _action):
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

    def playlists_key_press(self, widget, event):
        if event.keyval == gtk.gdk.keyval_from_name('Return'):
            self.playlists_activated(widget, widget.get_cursor()[0])
            return True

    def playlists_activated(self, _treeview, _path, _column=0):
        self.on_add_item(None)

