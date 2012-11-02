
"""
This module handles the mpd current playlist and provides a user
interface for it.

Example usage:
import current
self.current = current.Current(self.config, self.client, self.TAB_CURRENT,
    self.on_current_button_press, self.connected, lambda:self.sonata_loaded,
    lambda:self.songinfo, self.update_statusbar, self.iterate_now,
    lambda:self.library.libsearchfilter_get_style())
vbox_current, playlistevbox = self.current.get_widgets()
...
self.current.current_update(prevstatus_playlist, self.status['playlistlength'])
...
"""

import os
import re
import urllib
import threading # searchfilter_toggle starts thread searchfilter_loop

import gtk
import pango
import gobject

import ui
import misc
import formatting
import mpdhelper as mpdh


class Current(object):

    def __init__(self, config, mpd, TAB_CURRENT, on_current_button_press,
                 connected, sonata_loaded, songinfo, update_statusbar,
                 iterate_now, libsearchfilter_get_style, new_tab):
        self.config = config
        self.mpd = mpd
        self.on_current_button_press = on_current_button_press
        self.connected = connected
        self.sonata_loaded = sonata_loaded
        self.songinfo = songinfo
        self.update_statusbar = update_statusbar
        self.iterate_now = iterate_now
        self.libsearchfilter_get_style = libsearchfilter_get_style

        self.currentdata = None
        self.filterbox_visible = False
        self.current_update_skip = False
        # Mapping between filter rows and self.currentdata rows
        self.filter_row_mapping = []
        self.columnformat = None
        self.columns = None

        self.current_songs = None
        self.filterbox_cmd_buf = None
        self.filterbox_cond = None
        self.filterbox_source = None
        # TreeViewColumn, order
        self.column_sorted = (None, gtk.SORT_DESCENDING)
        self.total_time = 0
        self.edit_style_orig = None
        self.resizing_columns = None
        self.prev_boldrow = -1
        self.prevtodo = None
        self.plpos = None
        self.playlist_pos_before_filter = None
        self.sel_rows = None

        # Current tab
        self.current = ui.treeview(reorder=True, search=False, headers=True)
        self.current_selection = self.current.get_selection()
        self.expanderwindow = ui.scrollwindow(shadow=gtk.SHADOW_IN,
                                              add=self.current)
        self.filterpattern = ui.entry()
        self.filterbox = gtk.HBox()
        self.filterbox.pack_start(ui.label(text=_("Filter:")), False, False, 5)
        self.filterbox.pack_start(self.filterpattern, True, True, 5)
        filterclosebutton = ui.button(img=ui.image(stock=gtk.STOCK_CLOSE),
                                      relief=gtk.RELIEF_NONE)
        self.filterbox.pack_start(filterclosebutton, False, False, 0)
        self.filterbox.set_no_show_all(True)
        self.vbox_current = gtk.VBox()
        self.vbox_current.pack_start(self.expanderwindow, True, True)
        self.vbox_current.pack_start(self.filterbox, False, False, 5)

        self.tab = new_tab(self.vbox_current, gtk.STOCK_CDROM, TAB_CURRENT,
                           self.current)

        self.current.connect('drag_data_received', self.on_dnd)
        self.current.connect('row_activated', self.on_current_click)
        self.current.connect('button_press_event',
                             self.on_current_button_press)
        self.current.connect('drag-begin', self.on_current_drag_begin)
        self.current.connect_after('drag-begin',
                                   self.dnd_after_current_drag_begin)
        self.current.connect('button_release_event',
                             self.on_current_button_release)

        self.filter_changed_handler = self.filterpattern.connect('changed',
                                                self.searchfilter_feed_loop)
        self.filterpattern.connect('activate', self.searchfilter_on_enter)
        self.filterpattern.connect('key-press-event',
                                   self.searchfilter_key_pressed)
        filterclosebutton.connect('clicked', self.searchfilter_toggle)

        # Set up current view
        self.initialize_columns()
        self.current_selection.set_mode(gtk.SELECTION_MULTIPLE)
        target_reorder = ('MY_TREE_MODEL_ROW', gtk.TARGET_SAME_WIDGET, 0)
        target_file_managers = ('text/uri-list', 0, 0)
        self.current.enable_model_drag_source(gtk.gdk.BUTTON1_MASK,
                                              [target_reorder,
                                               target_file_managers],
                                              gtk.gdk.ACTION_COPY |
                                              gtk.gdk.ACTION_DEFAULT)
        self.current.enable_model_drag_dest([target_reorder,
                                             target_file_managers],
                                            gtk.gdk.ACTION_MOVE |
                                            gtk.gdk.ACTION_DEFAULT)
        self.current.connect('drag-data-get',
                             self.dnd_get_data_for_file_managers)

    def get_model(self):
        return self.currentdata

    def get_widgets(self):
        return self.vbox_current

    def get_treeview(self):
        return self.current

    def get_selection(self):
        return self.current_selection

    def get_filterbox_visible(self):
        return self.filterbox_visible

    def initialize_columns(self):
        # Initialize current playlist data and widget
        self.resizing_columns = False
        self.columnformat = self.config.currentformat.split("|")
        self.currentdata = gtk.ListStore(*([int] + [str] * \
                                           len(self.columnformat)))
        self.current.set_model(self.currentdata)
        cellrenderer = gtk.CellRendererText()
        cellrenderer.set_property("ellipsize", pango.ELLIPSIZE_END)

        num_columns = len(self.columnformat)
        if num_columns != len(self.config.columnwidths):
            # Number of columns changed, set columns equally spaced:
            self.config.columnwidths = [self.current.allocation.width / \
                                        num_columns] * num_columns

        colnames = formatting.parse_colnames(
            self.config.currentformat)
        self.columns = [gtk.TreeViewColumn(name, cellrenderer,
                markup=(i + 1))
                for i, name in enumerate(colnames)]

        for column, width in zip(self.columns, self.config.columnwidths):
            column.set_sizing(gtk.TREE_VIEW_COLUMN_FIXED)
            # If just one column, we want it to expand with the tree, so
            # don't set a fixed_width; if multiple columns, size accordingly:
            if num_columns > 1:
                column.set_resizable(True)
                try:
                    column.set_fixed_width(max(width, 10))
                except:
                    column.set_fixed_width(150)
            column.connect('clicked', self.on_current_column_click)
            self.current.append_column(column)

        self.current.set_fixed_height_mode(True)
        self.current.set_headers_visible(num_columns > 1 and \
                                         self.config.show_header)
        self.current.set_headers_clickable(not self.filterbox_visible)

    def get_current_songs(self):
        return self.current_songs

    def dnd_get_data_for_file_managers(self, _treeview, context, selection,
                                       _info, _timestamp):

        if not os.path.isdir(self.config.musicdir[self.config.profile_num]):
            # Prevent the DND mouse cursor from looking like we can DND
            # when we clearly can't.
            return

        context.drag_status(gtk.gdk.ACTION_COPY, context.start_time)

        filenames = self.get_selected_filenames(True)
        uris = ["file://%s" % urllib.quote(filename)
            for filename in filenames]

        selection.set_uris(uris)

    def get_selected_filenames(self, return_abs_paths):
        _model, selected = self.current_selection.get_selected_rows()
        filenames = []

        for path in selected:
            if not self.filterbox_visible:
                item = mpdh.get(self.current_songs[path[0]], 'file')
            else:
                item = mpdh.get(
                    self.current_songs[self.filter_row_mapping[path[0]]],
                    'file')
            if return_abs_paths:
                filenames.append(
                    os.path.join(self.config.musicdir[self.config.profile_num],
                                 item))
            else:
                filenames.append(item)
        return filenames

    def update_format(self):
        for track in self.current_songs:
            items = [formatting.parse(part, track, True)
                 for part in self.columnformat]

            self.currentdata.append([mpdh.get(track, 'id', 0, True)] + items)

    def current_update(self, prevstatus_playlist, new_playlist_length):
        if self.connected():

            if self.sonata_loaded():
                playlistposition = self.current.get_visible_rect()[1]

            self.current.freeze_child_notify()

            if not self.current_update_skip:

                if not self.filterbox_visible:
                    self.current.set_model(None)

                if prevstatus_playlist:
                    changed_songs = self.mpd.plchanges(prevstatus_playlist)
                else:
                    changed_songs = self.mpd.plchanges(0)
                    self.current_songs = []

                newlen = int(new_playlist_length)
                currlen = len(self.currentdata)

                for track in changed_songs:
                    pos = mpdh.get(track, 'pos', 0, True)

                    items = [formatting.parse(part, track,
                                  True)
                         for part in self.columnformat]

                    if pos < currlen:
                        # Update attributes for item:
                        i = self.currentdata.get_iter((pos, ))
                        trackid = mpdh.get(track, 'id',
                                    0, True)
                        if trackid != self.currentdata.get_value(i, 0):
                            self.currentdata.set_value(i, 0, trackid)
                        for index in range(len(items)):
                            if items[index] != self.currentdata.get_value(i,
                                                                    index + 1):
                                self.currentdata.set_value(i, index + 1,
                                                           items[index])
                        self.current_songs[pos] = track
                    else:
                        # Add new item:
                        self.currentdata.append([mpdh.get(track, 'id', 0,
                                                          True)] + items)
                        self.current_songs.append(track)

                if newlen == 0:
                    self.currentdata.clear()
                    self.current_songs = []
                else:
                    # Remove excess songs:
                    for i in range(currlen - newlen):
                        it = self.currentdata.get_iter((currlen - 1 - i,))
                        self.currentdata.remove(it)
                    self.current_songs = self.current_songs[:newlen]

                if not self.filterbox_visible:
                    self.current.set_model(self.currentdata)

            self.current_update_skip = False

            # Update statusbar time:
            self.total_time = 0
            for track in self.current_songs:
                try:
                    self.total_time = self.total_time + mpdh.get(track, 'time',
                                                                 0, True)
                except:
                    pass

            if 'pos' in self.songinfo():
                currsong = mpdh.get(self.songinfo(), 'pos', 0, True)
                self.boldrow(currsong)
                self.prev_boldrow = currsong

            if self.filterbox_visible:
                # Refresh filtered results:
                # Hacky, but this ensures we retain the
                # self.current position/selection
                self.prevtodo = "RETAIN_POS_AND_SEL"
                self.plpos = playlistposition
                self.searchfilter_feed_loop(self.filterpattern)
            elif self.sonata_loaded():
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

    def center_song_in_list(self, _event=None):
        if self.filterbox_visible:
            return
        if self.config.expanded and len(self.currentdata) > 0:
            self.current.realize()
            try:
                row = mpdh.get(self.songinfo(), 'pos', None)
                if row is None:
                    return
                visible_rect = self.current.get_visible_rect()
                row_rect = self.current.get_background_area(row,
                                                            self.columns[0])
                top_coord = (row_rect.y + row_rect.height - \
                             int(visible_rect.height / 2)) + visible_rect.y
                self.current.scroll_to_point(-1, top_coord)
            except:
                pass

    def current_get_songid(self, i, model):
        return int(model.get_value(i, 0))

    def on_current_drag_begin(self, _widget, _context):
        self.sel_rows = False

    def dnd_after_current_drag_begin(self, _widget, context):
        # Override default image of selected row with sonata icon:
        context.set_icon_stock('sonata', 0, 0)

    def on_current_button_release(self, widget, event):
        if self.sel_rows:
            self.sel_rows = False
            # User released mouse, select single row:
            selection = widget.get_selection()
            selection.unselect_all()
            path, _col, _x, _y = widget.get_path_at_pos(int(event.x),
                                                        int(event.y))
            selection.select_path(path)

    def on_current_column_click(self, column):
        columns = self.current.get_columns()
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
            if not self.currentdata:
                return

            while gtk.events_pending():
                gtk.main_iteration()
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
                    self.column_sorted = (column, gtk.SORT_DESCENDING)
                mode = "col"

            # If the first tag in the format is song length, we will make
            # sure to compare the same number of items in the song length
            # string (e.g. always use ##:##:##) and pad the first item to two
            # (e.g. #:##:## -> ##:##:##)
            custom_sort = False
            if mode == 'col':
                custom_sort, custom_pos = self.sort_get_first_format_tag(
                    self.config.currentformat, col_num, 'L')

            for track in self.current_songs:
                record = {}
                # Those items that don't have the specified tag will be put at
                # the end of the list (hence the 'zzzzzzz'):
                zzz = 'zzzzzzzz'
                if mode == 'artist':
                    record["sortby"] = (misc.lower_no_the(mpdh.get(track,
                                                                    'artist',
                                                                    zzz)),
                                mpdh.get(track, 'album', zzz).lower(),
                                mpdh.get(track, 'disc', '0', True, 0),
                                mpdh.get(track, 'track', '0', True, 0))
                elif mode == 'album':
                    record["sortby"] = (mpdh.get(track, 'album', zzz).lower(),
                                mpdh.get(track, 'disc', '0', True, 0),
                                mpdh.get(track, 'track', '0', True, 0))
                elif mode == 'file':
                    record["sortby"] = mpdh.get(track, 'file',
                                                zzz).lower().split('/')[-1]
                elif mode == 'dirfile':
                    record["sortby"] = mpdh.get(track, 'file', zzz).lower()
                elif mode == 'col':
                    # Sort by column:
                    record["sortby"] = misc.unbold(self.currentdata.get_value(
                        self.currentdata.get_iter((track_num, 0)),
                        col_num).lower())
                    if custom_sort:
                        record["sortby"] = self.sanitize_songlen_for_sorting(
                            record["sortby"], custom_pos)
                else:
                    record["sortby"] = mpdh.get(track, mode, zzz).lower()
                record["id"] = int(track["id"])
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
            if not self.currentdata:
                return
            while gtk.events_pending():
                gtk.main_iteration()
            top = 0
            bot = len(self.currentdata)-1
            self.mpd.command_list_ok_begin()
            while top < bot:
                self.mpd.swap(top, bot)
                top = top + 1
                bot = bot - 1
            self.mpd.command_list_end()
            self.iterate_now()

    def on_dnd(self, treeview, drag_context, x, y, selection, _info,
               timestamp):
        drop_info = treeview.get_dest_row_at_pos(x, y)

        if selection.data is not None:
            if not os.path.isdir(misc.file_from_utf8(
                self.config.musicdir[self.config.profile_num])):
                return
            # DND from outside sonata:
            uri = selection.data.strip()
            path = urllib.url2pathname(uri)
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
                            mpdpaths.append(mpdh.get(item, 'file'))

                # Add local file, available in mpd 0.14. This currently
                # work because python-mpd does not support unix socket
                # paths, won't which is needed for authentication for
                # local files. It's also therefore untested.
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
                    if position in (gtk.TREE_VIEW_DROP_BEFORE,
                                    gtk.TREE_VIEW_DROP_INTO_OR_BEFORE):
                        songid = destpath[0]
                    else:
                        songid = destpath[0] + 1
                else:
                    songid = len(self.currentdata)
                for mpdpath in mpdpaths:
                    self.mpd.addid(mpdpath, songid)
            self.iterate_now()
            return

        # Otherwise, it's a DND just within the current playlist
        model = treeview.get_model()
        _foobar, selected = self.current_selection.get_selected_rows()

        # calculate all this now before we start moving stuff
        drag_sources = []
        for path in selected:
            index = path[0]
            i = model.get_iter(path)
            songid = self.current_get_songid(i, model)
            text = model.get_value(i, 1)
            drag_sources.append([index, i, songid, text])

        # Keep track of the moved iters so we can select them afterwards
        moved_iters = []

        # We will manipulate self.current_songs and model to prevent
        # the entire playlist from refreshing
        offset = 0
        self.mpd.command_list_ok_begin()
        for source in drag_sources:
            index, i, songid, text = source
            if drop_info:
                destpath, position = drop_info
                dest = destpath[0] + offset
                if dest < index:
                    offset = offset + 1
                if position in (gtk.TREE_VIEW_DROP_BEFORE,
                                gtk.TREE_VIEW_DROP_INTO_OR_BEFORE):
                    self.current_songs.insert(dest, self.current_songs[index])
                    if dest < index + 1:
                        self.current_songs.pop(index + 1)
                        self.mpd.moveid(songid, dest)
                    else:
                        self.current_songs.pop(index)
                        self.mpd.moveid(songid, dest - 1)
                    model.insert(dest, model[index])
                    moved_iters += [model.get_iter((dest,))]
                    model.remove(i)
                else:
                    self.current_songs.insert(dest + 1,
                                              self.current_songs[index])
                    if dest < index:
                        self.current_songs.pop(index + 1)
                        self.mpd.moveid(songid, dest + 1)
                    else:
                        self.current_songs.pop(index)
                        self.mpd.moveid(songid, dest)
                    model.insert(dest + 1, model[index])
                    moved_iters += [model.get_iter((dest + 1,))]
                    model.remove(i)
            else:
                #dest = int(self.status['playlistlength']) - 1
                dest = len(self.currentdata) - 1
                self.mpd.moveid(songid, dest)
                self.current_songs.insert(dest + 1, self.current_songs[index])
                self.current_songs.pop(index)
                model.insert(dest + 1, model[index])
                moved_iters += [model.get_iter((dest + 1,))]
                model.remove(i)
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
        self.current_update_skip = True

        if drag_context.action == gtk.gdk.ACTION_MOVE:
            drag_context.finish(True, True, timestamp)
            self.header_hide_all_indicators(self.current, False)
        self.iterate_now()

        gobject.idle_add(self.dnd_retain_selection, treeview.get_selection(),
                         moved_iters)

    def dnd_retain_selection(self, treeselection, moved_iters):
        treeselection.unselect_all()
        for i in moved_iters:
            treeselection.select_iter(i)

    def on_current_click(self, _treeview, path, _column):
        model = self.current.get_model()
        if self.filterbox_visible:
            self.searchfilter_on_enter(None)
            return
        try:
            i = model.get_iter(path)
            self.mpd.playid(self.current_get_songid(i, model))
        except:
            pass
        self.sel_rows = False
        self.iterate_now()

    def searchfilter_toggle(self, _widget, initial_text=""):
        if self.filterbox_visible:
            ui.hide(self.filterbox)
            self.filterbox_visible = False
            self.edit_style_orig = self.libsearchfilter_get_style()
            self.filterpattern.set_text("")
            self.searchfilter_stop_loop()
        elif self.connected():
            self.playlist_pos_before_filter = \
                    self.current.get_visible_rect()[1]
            self.filterbox_visible = True
            self.filterpattern.handler_block(self.filter_changed_handler)
            self.filterpattern.set_text(initial_text)
            self.filterpattern.handler_unblock(self.filter_changed_handler)
            self.prevtodo = 'foo'
            ui.show(self.filterbox)
            # extra thread for background search work, synchronized
            # with a condition and its internal mutex
            self.filterbox_cond = threading.Condition()
            self.filterbox_cmd_buf = initial_text
            qsearch_thread = threading.Thread(target=self.searchfilter_loop)
            qsearch_thread.setDaemon(True)
            qsearch_thread.start()
            gobject.idle_add(self.filter_entry_grab_focus, self.filterpattern)
        self.current.set_headers_clickable(not self.filterbox_visible)

    def searchfilter_on_enter(self, _entry):
        model, selected = self.current.get_selection().get_selected_rows()
        song_id = None
        if len(selected) > 0:
            # If items are selected, play the first selected item:
            song_id = self.current_get_songid(model.get_iter(selected[0]),
                                              model)
        elif len(model) > 0:
            # If nothing is selected: play the first item:
            song_id = self.current_get_songid(model.get_iter_first(), model)
        if song_id:
            self.searchfilter_toggle(None)
            self.mpd.playid(song_id)

    def searchfilter_feed_loop(self, editable):
        # Lets only trigger the searchfilter_loop if 200ms pass
        # without a change in gtk.Entry
        try:
            gobject.source_remove(self.filterbox_source)
        except:
            pass
        self.filterbox_source = gobject.timeout_add(200,
                                                self.searchfilter_start_loop,
                                                editable)

    def searchfilter_start_loop(self, editable):
        self.filterbox_cond.acquire()
        self.filterbox_cmd_buf = editable.get_text()
        self.filterbox_cond.notifyAll()
        self.filterbox_cond.release()

    def searchfilter_stop_loop(self):
        self.filterbox_cond.acquire()
        self.filterbox_cmd_buf = '$$$QUIT###'
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
            self.current.freeze_child_notify()
            matches = gtk.ListStore(*([int] + [str] * len(self.columnformat)))
            matches.clear()
            filterposition = self.current.get_visible_rect()[1]
            _model, selected = self.current_selection.get_selected_rows()
            filterselected = [path for path in selected]
            rownum = 0
            # Store previous rownums in temporary list, in case we are
            # about to populate the songfilter with a subset of the
            # current filter. This will allow us to preserve the mapping.
            prev_rownums = [song for song in self.filter_row_mapping]
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
                        song_info.append(misc.unbold(row[i + 1]))
                    matches.append(song_info)
            else:
                # this make take some seconds... and we'll escape the search
                # text because we'll be searching for a match in items
                # that are also escaped.
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
                        song_info.append(misc.unbold(row[i + 1]))
                    # Search for matches in all columns:
                    for i in range(len(self.columnformat)):
                        if regexp.match(unicode(song_info[i + 1]).lower()):
                            matches.append(song_info)
                            if subset:
                                self.filter_row_mapping.append(
                                    prev_rownums[rownum])
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
            self.filterbox_cmd_buf = '$$$DONE###'
            try:
                self.filterbox_cond.release()
            except:
                pass
            gobject.idle_add(self.searchfilter_set_matches, matches,
                             filterposition, filterselected,
                             retain_position_and_selection)
            self.prevtodo = todo

    def searchfilter_revert_model(self):
        self.current.set_model(self.currentdata)
        self.center_song_in_list()
        self.current.thaw_child_notify()
        gobject.idle_add(self.center_song_in_list)
        gobject.idle_add(self.current.grab_focus)

    def searchfilter_set_matches(self, matches, filterposition,
                                 filterselected,
                                 retain_position_and_selection):
        self.filterbox_cond.acquire()
        flag = self.filterbox_cmd_buf
        self.filterbox_cond.release()
        # blit only when widget is still ok (segfault candidate, Gtk bug?)
        # and no other search is running, avoid pointless work and don't
        # confuse the user
        if (self.current.get_property('visible') and flag == '$$$DONE###'):
            self.current.set_model(matches)
            if retain_position_and_selection and filterposition:
                self.playlist_retain_view(self.current, filterposition)
                for path in filterselected:
                    self.current_selection.select_path(path)
            elif len(matches) > 0:
                self.current.set_cursor('0')
            if len(matches) == 0:
                gobject.idle_add(self.filtering_entry_make_red,
                                 self.filterpattern)
            else:
                gobject.idle_add(self.filtering_entry_revert_color,
                                 self.filterpattern)
            self.current.thaw_child_notify()

    def searchfilter_key_pressed(self, widget, event):
        self.filter_key_pressed(widget, event, self.current)

    def filter_key_pressed(self, widget, event, treeview):
        if event.keyval == gtk.gdk.keyval_from_name('Down') or \
           event.keyval == gtk.gdk.keyval_from_name('Up') or \
           event.keyval == gtk.gdk.keyval_from_name('Page_Down') or \
           event.keyval == gtk.gdk.keyval_from_name('Page_Up'):

            treeview.grab_focus()
            treeview.emit("key-press-event", event)
            gobject.idle_add(self.filter_entry_grab_focus, widget)

    def filter_entry_grab_focus(self, widget):
        widget.grab_focus()
        widget.set_position(-1)

    def filtering_entry_make_red(self, editable):
        style = editable.get_style().copy()
        style.text[gtk.STATE_NORMAL] = editable.get_colormap().alloc_color(
            "red")
        editable.set_style(style)

    def filtering_entry_revert_color(self, editable):
        editable.set_style(self.edit_style_orig)

    def boldrow(self, row):
        if row > -1:
            try:
                for i in range(len(self.currentdata[row]) - 1):
                    self.currentdata[row][i + 1] = misc.bold(
                        self.currentdata[row][i + 1])
            except:
                pass

    def unbold_boldrow(self, row):
        if row > -1:
            try:
                for i in range(len(self.currentdata[row]) - 1):
                    self.currentdata[row][i + 1] = misc.unbold(
                        self.currentdata[row][i + 1])
            except:
                pass

    def on_remove(self):
        treeviewsel = self.current_selection
        model, selected = treeviewsel.get_selected_rows()
        if len(selected) == len(self.currentdata) and \
           not self.filterbox_visible:
            # Everything is selected, clear:
            self.mpd.clear()
        elif len(selected) > 0:
            # we are manipulating the model manually for speed, so...
            self.current_update_skip = True
            selected.reverse()
            if not self.filterbox_visible:
                # If we remove an item from the filtered results, this
                # causes a visual refresh in the interface.
                self.current.set_model(None)
            self.mpd.command_list_ok_begin()
            for path in selected:
                if not self.filterbox_visible:
                    rownum = path[0]
                else:
                    rownum = self.filter_row_mapping[path[0]]
                i = self.currentdata.get_iter((rownum, 0))
                self.mpd.deleteid(
                    self.current_get_songid(i, self.currentdata))
                # Prevents the entire playlist from refreshing:
                self.current_songs.pop(rownum)
                self.currentdata.remove(i)
            self.mpd.command_list_end()
            if not self.filterbox_visible:
                self.current.set_model(model)
