"""Handle the mpd current playlist and provides a user interface for it."""

import os
import re
import urllib.parse, urllib.request

from gi.repository import Gtk, Gdk, Pango, GLib

from sonata import ui, misc, formatting
from sonata.mpdhelper import MPDSong


class Current:
    def __init__(self, config, mpd, name, on_button_press,
                 connected, sonata_loaded, songinfo, update_statusbar,
                 iterate_now, add_tab):
        self.config = config
        self.mpd = mpd
        self.on_button_press = on_button_press
        self.connected = connected
        self.sonata_loaded = sonata_loaded
        self.songinfo = songinfo
        self.update_statusbar = update_statusbar
        self.iterate_now = iterate_now

        self.store = None
        self.filterbox_visible = False
        self.update_skip = False
        self.columnformat = None
        self.columns = None

        self.refilter_handler_id = None
        # TreeViewColumn, order
        self.column_sorted = (None, Gtk.SortType.DESCENDING)
        self.total_time = 0
        self.resizing_columns = None
        self.prev_boldrow = -1
        self.playlist_pos_before_filter = None
        self.sel_rows = None

        # Current tab
        builder = ui.builder('current')
        self.view = builder.get_object('current_page_treeview')
        self.selection = self.view.get_selection()
        self.filterpattern = builder.get_object('current_page_filterbox_entry')
        self.filterbox = builder.get_object('current_page_filterbox')
        self.vbox = builder.get_object('current_page_v_box')
        builder.get_object('current_tab_label').set_text(name)

        tab_label_widget = builder.get_object('current_tab_eventbox')
        self.tab = add_tab(self.vbox, tab_label_widget, name, self.view)

        self.view.connect('drag-data-received', self.on_dnd_received)
        self.view.connect('row-activated', self.on_click)
        self.view.connect('button-press-event', self.on_button_press)
        self.view.connect('drag-begin', self.on_drag_begin)
        self.view.connect_after('drag-begin', self.on_dnd_after_drag_begin)
        self.view.connect('button-release-event', self.on_button_release)

        self.filter_changed_handler = self.filterpattern.connect(
            'changed', self.searchfilter_key_pressed)
        self.filterpattern.connect('activate', self.searchfilter_on_enter)
        filterclosebutton = builder.get_object(
            'current_page_filterbox_closebutton')
        filterclosebutton.connect('clicked', self.searchfilter_toggle)

        # Set up current view
        self.initialize_columns()
        self.selection.set_mode(Gtk.SelectionMode.MULTIPLE)

        target_reorder = ('MY_TREE_MODEL_ROW', Gtk.TargetFlags.SAME_WIDGET, 0)
        target_file_managers = ('text/uri-list', 0, 0)

        self.view.enable_model_drag_source(
            Gdk.ModifierType.BUTTON1_MASK,
            [target_reorder, target_file_managers],
            Gdk.DragAction.COPY | Gdk.DragAction.DEFAULT)
        self.view.enable_model_drag_dest(
            [target_reorder, target_file_managers],
            Gdk.DragAction.MOVE | Gdk.DragAction.DEFAULT)

        self.view.connect('drag-data-get', self.dnd_get_data_for_file_managers)

    def get_widgets(self):
        return self.vbox

    def is_empty(self):
        return len(self.store) == 0

    def clear(self):
        self.store.clear()

    def on_song_change(self, status):
        self.unbold_boldrow(self.prev_boldrow)

        if status and 'song' in status:
            row = int(status['song'])
            self.boldrow(row)
            self.center_song_in_list()
            self.prev_boldrow = row

    def try_keep_position(func):
        """Decorator to keep the position of the view while updating it"""

        def do_try_keep_position(self, *args, **kwargs):
            realized = self.view.get_realized()
            if realized:
                position = self.view.get_visible_rect()

            result = func(self, *args, **kwargs)

            if realized:
                self.view.scroll_to_point(-1, position.y)

            return result
        return do_try_keep_position

    def get_treeview(self):
        return self.view

    def get_selection(self):
        return self.selection

    def get_filterbox_visible(self):
        return self.filterbox_visible

    @try_keep_position
    def initialize_columns(self):
        # Initialize current playlist data and widget
        self.resizing_columns = False
        self.columnformat = self.config.currentformat.split("|")
        current_columns = [MPDSong] + [str] * len(self.columnformat) + [int]
        previous_tracks = (item[0] for item in (self.store or []))
        self.store = Gtk.ListStore(*(current_columns))
        cellrenderer = Gtk.CellRendererText()
        cellrenderer.set_property("ellipsize", Pango.EllipsizeMode.END)
        cellrenderer.set_property("weight-set", True)

        num_columns = len(self.columnformat)
        if num_columns != len(self.config.columnwidths):
            # Number of columns changed, set columns equally spaced:
            self.config.columnwidths = [self.view.get_allocation().width / \
                                        num_columns] * num_columns

        colnames = formatting.parse_colnames(self.config.currentformat)
        for column in self.view.get_columns():
            self.view.remove_column(column)
        self.columns = [Gtk.TreeViewColumn(name, cellrenderer, markup=(i + 1))
                for i, name in enumerate(colnames)]
        for tree in self.columns:
            tree.add_attribute(cellrenderer, "weight", len(current_columns) - 1)

        for column, width in zip(self.columns, self.config.columnwidths):
            column.set_sizing(Gtk.TreeViewColumnSizing.FIXED)
            # If just one column, we want it to expand with the tree, so
            # don't set a fixed_width; if multiple columns, size accordingly:
            if num_columns > 1:
                column.set_resizable(True)
                try:
                    column.set_fixed_width(max(width, 10))
                except:
                    column.set_fixed_width(150)
            column.connect('clicked', self.on_column_click)
            self.view.append_column(column)

        self.view.set_fixed_height_mode(True)
        self.view.set_headers_visible(num_columns > 1 and \
                                         self.config.show_header)
        self.view.set_headers_clickable(not self.filterbox_visible)
        self.update_format(previous_tracks)
        self.view.set_model(self.store)

    def dnd_get_data_for_file_managers(self, _treeview, context, selection,
                                       _info, timestamp):

        if not os.path.isdir(self.config.musicdir[self.config.profile_num]):
            # Prevent the DND mouse cursor from looking like we can DND
            # when we clearly can't.
            return

        Gdk.drag_status(context, Gdk.DragAction.COPY, timestamp)

        filenames = self.get_selected_filenames(True)
        uris = ["file://%s" % urllib.parse.quote(filename)
            for filename in filenames]

        selection.set_uris(uris)

    def get_selected_filenames(self, return_abs_paths):
        _model, selected = self.selection.get_selected_rows()
        filenames = []

        for path in selected:
            index = path.get_indices()[0]
            item = self.store[index][0].file
            if return_abs_paths:
                filenames.append(
                    os.path.join(self.config.musicdir[self.config.profile_num],
                                 item))
            else:
                filenames.append(item)
        return filenames

    def update_format(self, tracks):
        for i, track in enumerate(tracks):
            items = [formatting.parse(part, track, True)
                     for part in self.columnformat]

            if self.songinfo().pos == i:
                weight = [Pango.Weight.BOLD]
            else:
                weight = [Pango.Weight.NORMAL]

            self.store.append([track] + items + weight)

    @try_keep_position
    def current_update(self, prevstatus_playlist, new_playlist_length):
        if self.connected():
            self.view.freeze_child_notify()
            self.unbold_boldrow(self.prev_boldrow)

            if not self.update_skip:
                save_model = self.view.get_model()
                self.view.set_model(None)
                if prevstatus_playlist:
                    changed_songs = self.mpd.plchanges(prevstatus_playlist)
                else:
                    changed_songs = self.mpd.plchanges(0)


                newlen = int(new_playlist_length)
                currlen = len(self.store)

                for track in changed_songs:
                    pos = track.pos

                    items = [formatting.parse(part, track, True)
                             for part in self.columnformat]

                    if pos < currlen:
                        # Update attributes for item:
                        i = self.store.get_iter((pos, ))
                        if track.id != self.store.get_value(i, 0).id:
                            self.store.set_value(i, 0, track)
                        for index in range(len(items)):
                            if items[index] != self.store.get_value(i, index+1):
                                self.store.set_value(i, index + 1, items[index])
                    else:
                        # Add new item:
                        self.store.append(
                            [track] + items + [Pango.Weight.NORMAL])

                if newlen == 0:
                    self.store.clear()
                else:
                    # Remove excess songs:
                    for i in range(currlen - newlen):
                        it = self.store.get_iter((currlen - 1 - i,))
                        self.store.remove(it)

                self.view.set_model(save_model)
            self.update_skip = False

            # Update statusbar time:
            self.total_time = sum(item[0].time for item in self.store)

            if 'pos' in self.songinfo():
                currsong = self.songinfo().pos
                self.boldrow(currsong)
                self.prev_boldrow = currsong

            self.view.thaw_child_notify()
            self.header_update_column_indicators()
            self.update_statusbar()
            ui.change_cursor(None)

    def header_update_column_indicators(self):
        # If we just sorted a column, display the sorting arrow:
        if self.column_sorted[0]:
            if self.column_sorted[1] == Gtk.SortType.DESCENDING:
                self.header_hide_all_indicators(self.view, True)
                self.column_sorted[0].set_sort_order(Gtk.SortType.ASCENDING)
                self.column_sorted = (None, Gtk.SortType.ASCENDING)
            else:
                self.header_hide_all_indicators(self.view, True)
                self.column_sorted[0].set_sort_order(Gtk.SortType.DESCENDING)
                self.column_sorted = (None, Gtk.SortType.DESCENDING)

    def header_hide_all_indicators(self, treeview, show_sorted_column):
        if not show_sorted_column:
            self.column_sorted = (None, Gtk.SortType.descending)
        for column in treeview.get_columns():
            if show_sorted_column and column == self.column_sorted[0]:
                column.set_sort_indicator(True)
            else:
                column.set_sort_indicator(False)

    def center_song_in_list(self, _event=None):
        if not self.filterbox_visible and self.config.expanded and \
           len(self.store) > 0:
            row_path = Gtk.TreePath(self.songinfo().pos)
            self.view.scroll_to_cell(row_path, None, True, 0.5, 0.5)

    def get_songid(self, i, model):
        return model.get_value(i, 0).id

    def on_drag_begin(self, _widget, _context):
        self.sel_rows = False

    def on_dnd_after_drag_begin(self, _widget, context):
        # Override default image of selected row with sonata icon:
        Gtk.drag_set_icon_stock(context, 'sonata', 0, 0)

    def on_button_release(self, widget, event):
        if self.sel_rows:
            self.sel_rows = False
            # User released mouse, select single row:
            selection = widget.get_selection()
            selection.unselect_all()
            path, _col, _x, _y = widget.get_path_at_pos(int(event.x),
                                                        int(event.y))
            selection.select_path(path)

    def on_column_click(self, column):
        columns = self.view.get_columns()
        col_num = 0
        for col in columns:
            col_num = col_num + 1
            if column == col:
                self.sort('col' + str(col_num), column)
                return

    def on_sort_by_artist(self, _action):
        self.sort('artist')

    def on_sort_by_album(self, _action):
        self.sort('album')

    def on_sort_by_title(self, _action):
        self.sort('title')

    def on_sort_by_file(self, _action):
        self.sort('file')

    def on_sort_by_dirfile(self, _action):
        self.sort('dirfile')

    def sort(self, mode, column=None):
        if self.connected():
            if not self.store:
                return

            while Gtk.events_pending():
                Gtk.main_iteration()
            songs = []
            track_num = 0

            if mode[0:3] == 'col':
                col_num = int(mode.replace('col', ''))
                if column.get_sort_indicator():
                    # If this column was already sorted, reverse list:
                    self.column_sorted = (column, self.column_sorted[1])
                    self.on_sort_reverse(None)
                    return
                else:
                    self.column_sorted = (column, Gtk.SortType.DESCENDING)
                mode = "col"

            # If the first tag in the format is song length, we will make
            # sure to compare the same number of items in the song length
            # string (e.g. always use ##:##:##) and pad the first item to two
            # (e.g. #:##:## -> ##:##:##)
            custom_sort = False
            if mode == 'col':
                custom_sort, custom_pos = self.sort_get_first_format_tag(
                    self.config.currentformat, col_num, 'L')

            for track in (item[0] for item in self.store):
                record = {}
                # Those items that don't have the specified tag will be put at
                # the end of the list (hence the 'zzzzzzz'):
                zzz = 'zzzzzzzz'
                if mode == 'artist':
                    record["sortby"] = (
                        misc.lower_no_the(track.artist or zzz),
                        (track.album or zzz).lower(),
                        track.disc,
                        track.track)
                elif mode == 'album':
                    record["sortby"] = ((track.album or zzz).lower(),
                                        track.disc,
                                        track.track)
                elif mode == 'file':
                    record["sortby"] = os.path.basename(track.file or
                                                        zzz).lower()
                elif mode == 'dirfile':
                    record["sortby"] = (track.file or zzz).lower()
                elif mode == 'col':
                    # Sort by column:
                    record["sortby"] = self.store.get_value(
                        self.store.get_iter((track_num, 0)),
                        col_num).lower()
                    if custom_sort:
                        record["sortby"] = self.sanitize_songlen_for_sorting(
                            record["sortby"], custom_pos)
                else:
                    record["sortby"] = track.get(mode, zzz).lower()

                record["id"] = track.id
                songs.append(record)
                track_num = track_num + 1

            songs.sort(key=lambda x: x["sortby"])

            pos = 0
            self.mpd.command_list_ok_begin()
            for item in songs:
                self.mpd.moveid(item["id"], pos)
                pos += 1
            self.mpd.command_list_end()
            self.iterate_now()

            self.header_update_column_indicators()

    def sort_get_first_format_tag(self, format, colnum, tag_letter):
        # Returns a tuple with whether the first tag of the format
        # includes tag_letter and the position of the tag in the string:
        formats = format.split('|')
        format = formats[colnum-1]
        prev_letter = None
        for letter in format:
            if letter == tag_letter and prev_letter == '%':
                return (True, pos)
            else:
                break
            prev_letter = letter
        return (False, 0)

    def sanitize_songlen_for_sorting(self, songlength, pos_of_string):
        songlength = songlength[pos_of_string:]
        items = [item.zfill(2) for item in songlength.split(':')]
        for i in range(3 - len(items)):
            items.insert(0, "00")
        return ":".join(item for item in items[:3])

    def on_sort_reverse(self, _action):
        if self.connected():
            if not self.store:
                return
            while Gtk.events_pending():
                Gtk.main_iteration()
            top = 0
            bot = len(self.store)-1
            self.mpd.command_list_ok_begin()
            while top < bot:
                self.mpd.swap(top, bot)
                top = top + 1
                bot = bot - 1
            self.mpd.command_list_end()
            self.iterate_now()

    def on_dnd_received(self, treeview, drag_context, x, y, selection, _info, timestamp):
        drop_info = treeview.get_dest_row_at_pos(x, y)

        if selection.get_data():
            if not os.path.isdir(self.config.musicdir[self.config.profile_num]):
                return
            # DND from outside sonata:
            uri = selection.get_data().strip().decode('utf-8')
            path = urllib.request.url2pathname(uri)
            paths = path.rsplit('\n')
            mpdpaths = []
            # Strip off paranthesis so that we can DND entire music dir
            # if we wish.
            musicdir = self.config.musicdir[self.config.profile_num][:-1]
            for i, path in enumerate(paths):
                paths[i] = path.rstrip('\r')
                if paths[i].startswith('file://'):
                    paths[i] = paths[i][7:]
                elif paths[i].startswith('file:'):
                    paths[i] = paths[i][5:]
                if paths[i].startswith(musicdir):
                    paths[i] = paths[i][len(musicdir):]
                    if len(paths[i]) == 0:
                        paths[i] = "/"
                    listallinfo = self.mpd.listallinfo(paths[i])
                    for item in listallinfo:
                        if 'file' in item:
                            mpdpaths.append(item['file'])

                # Add local file, available in mpd 0.14. This currently
                # work because python-mpd does not support unix socket
                # paths, won't which is needed for authentication for
                # local files. It's also therefore untested.
                if os.path.isdir(paths[i]):
                    filenames = misc.get_files_recursively(paths[i])
                else:
                    filenames = [paths[i]]
                for filename in filenames:
                    if os.path.exists(filename):
                        mpdpaths.append("file://" + urllib.parse.quote(filename))
            if len(mpdpaths) > 0:
                # Items found, add to list at drop position:
                if drop_info:
                    destpath, position = drop_info
                    if position in (Gtk.TreeViewDropPosition.BEFORE,
                                    Gtk.TreeViewDropPosition.INTO_OR_BEFORE):
                        songid = destpath[0]
                    else:
                        songid = destpath[0] + 1
                else:
                    songid = len(self.store)
                for mpdpath in mpdpaths:
                    self.mpd.addid(mpdpath, songid)
            self.iterate_now()
            return

        # Otherwise, it's a DND just within the current playlist
        model = self.store
        _foobar, selected = self.selection.get_selected_rows()

        # calculate all this now before we start moving stuff
        drag_sources = []
        for path in selected:
            index = path[0]
            treeiter = model.get_iter(path)
            songid = self.get_songid(treeiter, model)
            drag_sources.append([index, treeiter, songid])

        # Keep track of the moved iters so we can select them afterwards
        moved_iters = []

        # Will manipulate model to prevent the entire playlist from refreshing
        offset = 0
        self.mpd.command_list_ok_begin()
        for index, treeiter, songid in drag_sources:
            if drop_info:
                destpath, position = drop_info
                dest = destpath[0] + offset
                if dest < index:
                    offset = offset + 1
                pop_from = index
                move_to = dest
                if position in (Gtk.TreeViewDropPosition.BEFORE,
                                Gtk.TreeViewDropPosition.INTO_OR_BEFORE):
                    insert_to = dest
                    if dest < index + 1:
                        pop_from = index + 1
                    else:
                        move_to = dest - 1
                else:
                    insert_to = dest + 1
                    if dest < index:
                        pop_from = index + 1
                        move_to = insert_to
            else:
                dest = len(self.store) - 1
                insert_to = dest + 1

            self.mpd.moveid(songid, move_to)
            moved_iters.append(model.insert(insert_to, tuple(model[index])))
            model.remove(treeiter)

            # now fixup
            for source in drag_sources:
                if dest < index:
                    # we moved it back, so all indexes inbetween increased by 1
                    if dest < source[0] < index:
                        source[0] += 1
                else:
                    # we moved it ahead, so all indexes inbetween
                    # decreased by 1
                    if index < source[0] < dest:
                        source[0] -= 1
        self.mpd.command_list_end()

        # we are manipulating the model manually for speed, so...
        self.update_skip = True

        # Gdk.DragContext.get_action() returns a bitmask of actions
        if drag_context.get_actions() & Gdk.DragAction.MOVE:
            Gdk.drag_finish(drag_context, True, True, timestamp)
            self.header_hide_all_indicators(self.view, False)
        self.iterate_now()

        selection = treeview.get_selection()
        selection.unselect_all()
        for i in moved_iters:
            selection.select_iter(i)

        if moved_iters:
            treeview.scroll_to_cell(model.get_path(moved_iters[0]), None)

    def on_click(self, _treeview, path, _column):
        model = self.view.get_model()
        if self.filterbox_visible:
            self.searchfilter_on_enter(None)
            return
        try:
            i = model.get_iter(path)
            self.mpd.playid(self.get_songid(i, model))
        except:
            pass
        self.sel_rows = False
        self.iterate_now()

    def searchfilter_toggle(self, _widget, initial_text=""):
        if self.filterbox_visible:
            ui.hide(self.filterbox)
            self.filterbox_visible = False
            self.filterpattern.set_text("")
            self.view.set_model(self.store)
        elif self.connected():
            self.playlist_pos_before_filter = \
                    self.view.get_visible_rect().height
            self.filterbox_visible = True
            with self.filterpattern.handler_block(self.filter_changed_handler):
                self.filterpattern.set_text(initial_text)
            ui.show(self.filterbox)
            self.filterpattern.grab_focus()
        self.view.set_headers_clickable(not self.filterbox_visible)

    def model_filter_func(self, model, iter, regex):
        row = model.get(iter, 1, *range(len(self.columnformat)- 1)[1:])
        for cell in row:
            if regex.match(cell.lower()):
                return True
        return False

    def searchfilter_on_enter(self, _entry):
        model, selected = self.view.get_selection().get_selected_rows()
        song_id = None
        if len(selected) > 0:
            # If items are selected, play the first selected item:
            song_id = self.get_songid(model.get_iter(selected[0]), model)
        elif len(model) > 0:
            # If nothing is selected: play the first item:
            song_id = self.get_songid(model.get_iter_first(), model)
        if song_id:
            self.searchfilter_toggle(None)
            self.mpd.playid(song_id)

    def searchfilter_key_pressed(self, widget):
        # We have something new to search, try first to cancel the previous
        # search.
        try:
            GLib.source_remove(self.refilter_handler_id)
        except TypeError: # self.refilter_handler_id is None
            pass

        text = widget.get_text()
        if text == '':
            # Nothing to search for, just display the whole model.
            self.view.set_model(self.store)
            return

        regex = misc.escape_html(text)
        regex = re.escape(regex)
        regex = '.*' + regex.replace(' ', ' .*').lower()
        filter_regex = re.compile(regex)

        def set_filtering_function(regex):
            # Creates a Gtk.TreeModelFilter
            filter_model = self.store.filter_new()
            filter_model.set_visible_func(self.model_filter_func, regex)
            self.view.set_model(filter_model)

        # Delay slightly the new search, in case something else is coming.
        self.refilter_handler_id = GLib.timeout_add(
            250, set_filtering_function, filter_regex)

    def filter_key_pressed(self, widget, event, treeview):
        if event.keyval == Gdk.keyval_from_name('Down') or \
           event.keyval == Gdk.keyval_from_name('Up') or \
           event.keyval == Gdk.keyval_from_name('Page_Down') or \
           event.keyval == Gdk.keyval_from_name('Page_Up'):

            treeview.grab_focus()
            treeview.emit("key-press-event", event)
            GLib.idle_add(self.filter_entry_grab_focus, widget)

    def boldrow(self, row):
        if row > -1:
            try:
                self.store[row][-1] = Pango.Weight.BOLD
            except IndexError:
                # The row might not exist anymore
                pass

    def unbold_boldrow(self, row):
        if row > -1:
            try:
                self.store[row][-1] = Pango.Weight.NORMAL
            except IndexError:
                # The row might not exist anymore
                pass

    def on_remove(self):
        model, selected = self.selection.get_selected_rows()
        if len(selected) == len(self.store) and not self.filterbox_visible:
            # Everything is selected, clear:
            self.mpd.clear()
        elif len(selected) > 0:
            # we are manipulating the model manually for speed, so...
            self.update_skip = True
            self.mpd.command_list_ok_begin()
            for i in (model.get_iter(path) for path in reversed(selected)):
                self.mpd.deleteid(model.get(i, 0)[0].id)
                if model != self.store:
                    # model is different if there is a filter currently applied.
                    # So we retrieve the iter of the wrapped model...
                    i = model.convert_iter_to_child_iter(i)
                self.store.remove(i)
            self.mpd.command_list_end()
