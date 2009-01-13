import os
import re, gettext, locale
import threading # libsearchfilter_toggle starts thread libsearchfilter_loop

import gtk, gobject, pango

import ui, misc
import mpdhelper as mpdh
from consts import consts

name_to_index = {'album':0, 'artist':1, 'genre':2, 'year':3, 'path':4}

def library_set_data(album=None, artist=None, genre=None, year=None, path=None):
    d = consts.LIB_DELIM
    nd = consts.LIB_NODATA
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
    if path is not None:
        ret += d + path
    else:
        ret += d + nd
    return ret

def library_get_data(data, *args):
    # Data retrieved from the gtktreeview model is not in
    # unicode anymore, so convert it.
    dl = data.split(consts.LIB_DELIM)
    retlist = []
    for arg in list(args):
        ret = unicode(dl[name_to_index[arg]])
        if ret == consts.LIB_NODATA:
            ret = None
        retlist.append(ret)
    if len(retlist) == 1:
        return retlist[0]
    else:
        return retlist

class Library(object):
    def __init__(self, config, client, artwork, TAB_LIBRARY, album_filename, settings_save, filtering_entry_make_red, filtering_entry_revert_color, filter_key_pressed, on_add_item, parse_formatting, connected, on_library_button_press, on_library_search_text_click):
        self.artwork = artwork
        self.config = config
        self.client = client
        self.librarymenu = None # cyclic dependency, set later
        self.TAB_LIBRARY = TAB_LIBRARY
        self.album_filename = album_filename
        self.settings_save = settings_save
        self.filtering_entry_make_red = filtering_entry_make_red
        self.filtering_entry_revert_color = filtering_entry_revert_color
        self.filter_key_pressed = filter_key_pressed
        self.on_add_item = on_add_item
        self.parse_formatting = parse_formatting
        self.connected = connected
        self.on_library_button_press = on_library_button_press
        self.on_library_search_text_click = on_library_search_text_click

        self.NOTAG = _("Untagged")
        self.VAstr = _("Various Artists")
        self.search_terms = [_('Artist'), _('Title'), _('Album'), _('Genre'), _('Filename'), _('Everything')]
        self.search_terms_mpd = ['artist', 'title', 'album', 'genre', 'file', 'any']

        self.libfilterbox_cmd_buf = None
        self.libfilterbox_cond = None
        self.libfilterbox_source = None

        self.prevlibtodo_base = None
        self.prevlibtodo_base_results = None
        self.prevlibtodo = None

        self.save_timeout = None
        self.libsearch_last_tooltip = None

        self.lib_view_filesystem_cache = None
        self.lib_view_artist_cache = None
        self.lib_view_genre_cache = None
        self.lib_view_album_cache = None
        self.lib_list_genres = None
        self.lib_list_artists = None
        self.lib_list_albums = None
        self.lib_list_years = None
        self.view_caches_reset()

        self.libraryvbox = gtk.VBox()
        self.library = ui.treeview()
        self.library_selection = self.library.get_selection()
        expanderwindow2 = ui.scrollwindow(add=self.library)
        self.searchbox = gtk.HBox()
        self.searchcombo = ui.combo(items=self.search_terms)
        self.searchtext = ui.entry()
        self.searchbutton = ui.button(text=_('_End Search'), img=ui.image(stock=gtk.STOCK_CLOSE), h=self.searchcombo.size_request()[1])
        self.searchbutton.set_no_show_all(True)
        self.searchbutton.hide()
        self.libraryview = ui.button(relief=gtk.RELIEF_NONE)
        self.libraryview.set_tooltip_text(_("Library browsing view"))
        self.library_view_assign_image()
        self.searchbox.pack_start(self.libraryview, False, False, 1)
        self.searchbox.pack_start(gtk.VSeparator(), False, False, 0)
        self.searchbox.pack_start(self.searchcombo, False, False, 2)
        self.searchbox.pack_start(self.searchtext, True, True, 2)
        self.searchbox.pack_start(self.searchbutton, False, False, 2)
        self.libraryvbox.pack_start(expanderwindow2, True, True, 2)
        self.libraryvbox.pack_start(self.searchbox, False, False, 2)
        libraryhbox = gtk.HBox()
        libraryhbox.pack_start(ui.image(stock=gtk.STOCK_HARDDISK), False, False, 2)
        libraryhbox.pack_start(ui.label(text=self.TAB_LIBRARY), False, False, 2)
        self.libraryevbox = ui.eventbox(add=libraryhbox)
        self.libraryevbox.show_all()

        # Assign some pixbufs for use in self.library
        self.openpb = self.library.render_icon(gtk.STOCK_OPEN, gtk.ICON_SIZE_LARGE_TOOLBAR)
        self.harddiskpb = self.library.render_icon(gtk.STOCK_HARDDISK, gtk.ICON_SIZE_LARGE_TOOLBAR)
        self.albumpb = gtk.gdk.pixbuf_new_from_file_at_size(album_filename, consts.LIB_COVER_SIZE, consts.LIB_COVER_SIZE)
        self.genrepb = self.library.render_icon('gtk-orientation-portrait', gtk.ICON_SIZE_LARGE_TOOLBAR)
        self.artistpb = self.library.render_icon('artist', gtk.ICON_SIZE_LARGE_TOOLBAR)
        self.sonatapb = self.library.render_icon('sonata', gtk.ICON_SIZE_MENU)

        self.library.connect('row_activated', self.on_library_row_activated)
        self.library.connect('button_press_event', self.on_library_button_press)
        self.library.connect('key-press-event', self.on_library_key_press)
        self.library.connect('query-tooltip', self.on_library_query_tooltip)
        expanderwindow2.connect('scroll-event', self.on_library_scrolled)
        self.libraryview.connect('clicked', self.library_view_popup)
        self.searchtext.connect('button_press_event', self.on_library_search_text_click)
        self.searchtext.connect('key-press-event', self.libsearchfilter_key_pressed)
        self.searchtext.connect('activate', self.libsearchfilter_on_enter)
        self.searchbutton.connect('clicked', self.on_search_end)

        self.libfilter_changed_handler = self.searchtext.connect('changed', self.libsearchfilter_feed_loop)
        searchcombo_changed_handler = self.searchcombo.connect('changed', self.on_library_search_combo_change)

        # Initialize library data and widget
        self.libraryposition = {}
        self.libraryselectedpath = {}
        self.searchcombo.handler_block(searchcombo_changed_handler)
        self.searchcombo.set_active(self.config.last_search_num)
        self.searchcombo.handler_unblock(searchcombo_changed_handler)
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

    def get_model(self):
        return self.librarydata

    def get_widgets(self):
        return self.libraryvbox, self.libraryevbox

    def get_treeview(self):
        return self.library

    def get_selection(self):
        return self.library_selection

    def set_librarymenu(self, librarymenu):
        self.librarymenu = librarymenu
        self.librarymenu.attach_to_widget(self.libraryview, None)

    def library_view_popup(self, _button):
        self.librarymenu.popup(None, None, self.library_view_position_menu, 1, 0)

    def library_view_position_menu(self, _menu):
        x, y, _width, height = self.libraryview.get_allocation()
        return (self.config.x + x, self.config.y + y + height, True)

    def on_libraryview_chosen(self, action):
        if self.search_visible():
            self.on_search_end(None)
        if action.get_name() == 'filesystemview':
            self.config.lib_view = consts.VIEW_FILESYSTEM
        elif action.get_name() == 'artistview':
            self.config.lib_view = consts.VIEW_ARTIST
        elif action.get_name() == 'genreview':
            self.config.lib_view = consts.VIEW_GENRE
        elif action.get_name() == 'albumview':
            self.config.lib_view = consts.VIEW_ALBUM
        self.library.grab_focus()
        self.library_view_assign_image()
        self.libraryposition = {}
        self.libraryselectedpath = {}
        self.library_browse(self.library_set_data(path="/"))
        try:
            if len(self.librarydata) > 0:
                self.library_selection.unselect_range((0,), (len(self.librarydata)-1,))
        except:
            pass
        gobject.idle_add(self.library.scroll_to_point, 0, 0)

    def library_view_assign_image(self):
        if self.config.lib_view == consts.VIEW_FILESYSTEM:
            self.libraryview.set_image(ui.image(stock=gtk.STOCK_HARDDISK))
        elif self.config.lib_view == consts.VIEW_ARTIST:
            self.libraryview.set_image(ui.image(stock='artist'))
        elif self.config.lib_view == consts.VIEW_GENRE:
            self.libraryview.set_image(ui.image(stock='gtk-orientation-portrait'))
        elif self.config.lib_view == consts.VIEW_ALBUM:
            self.libraryview.set_image(ui.image(stock='album'))

    def view_caches_reset(self):
        # We should call this on first load and whenever mpd is
        # updated.
        self.lib_view_filesystem_cache = None
        self.lib_view_artist_cache = None
        self.lib_view_genre_cache = None
        self.lib_view_album_cache = None
        self.lib_list_genres = None
        self.lib_list_artists = None
        self.lib_list_albums = None
        self.lib_list_years = None

    def on_library_scrolled(self, _widget, _event):
        try:
            # Use gobject.idle_add so that we can get the visible state of the treeview
            gobject.idle_add(self._on_library_scrolled)
        except:
            pass

    def _on_library_scrolled(self):
        if not self.config.show_covers:
            return

        # This avoids a warning about a NULL node in get_visible_range
        if not self.library.props.visible:
            return

        vis_range = self.library.get_visible_range()
        if vis_range is None:
            return
        try:
            start_row = int(vis_range[0][0])
            end_row = int(vis_range[1][0])
        except IndexError:
            # get_visible_range failed
            return

        self.artwork.library_artwork_update(self.librarydata, start_row, end_row, self.albumpb)

    def library_browse(self, _widget=None, root=None):
        # Populates the library list with entries
        if not self.connected():
            return

        if root is None or (self.config.lib_view == consts.VIEW_FILESYSTEM and self.library_get_data(root, 'path') is None):
            root = self.library_set_data(path="/")
        if self.config.wd is None or (self.config.lib_view == consts.VIEW_FILESYSTEM and self.library_get_data(self.config.wd, 'path') is None):
            self.config.wd = self.library_set_data(path="/")

        prev_selection = []
        prev_selection_root = False
        prev_selection_parent = False
        if root == self.config.wd:
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
            self.libraryposition[self.config.wd] = self.library.get_visible_rect()[1]
            path_updated = True
        else:
            path_updated = False

        new_level = self.library_get_data_level(root)
        curr_level = self.library_get_data_level(self.config.wd)
        # The logic below is more consistent with, e.g., thunar.
        if new_level > curr_level:
            # Save position and row for where we just were if we've
            # navigated into a sub-directory:
            self.libraryposition[self.config.wd] = self.library.get_visible_rect()[1]
            model, rows = self.library_selection.get_selected_rows()
            if len(rows) > 0:
                data = self.librarydata.get_value(self.librarydata.get_iter(rows[0]), 2)
                if not data in ("..", "/"):
                    self.libraryselectedpath[self.config.wd] = rows[0]
        elif (self.config.lib_view == consts.VIEW_FILESYSTEM and root != self.config.wd) \
        or (self.config.lib_view != consts.VIEW_FILESYSTEM and new_level != curr_level):
            # If we've navigated to a parent directory, don't save
            # anything so that the user will enter that subdirectory
            # again at the top position with nothing selected
            self.libraryposition[self.config.wd] = 0
            self.libraryselectedpath[self.config.wd] = None

        # In case sonata is killed or crashes, we'll save the library state
        # in 5 seconds (first removing any current settings_save timeouts)
        if self.config.wd != root:
            try:
                gobject.source_remove(self.save_timeout)
            except:
                pass
            self.save_timeout = gobject.timeout_add(5000, self.settings_save)

        self.config.wd = root
        self.library.freeze_child_notify()
        self.librarydata.clear()

        # Populate treeview with data:
        bd = []
        while len(bd) == 0:
            if self.config.lib_view == consts.VIEW_FILESYSTEM:
                bd = self.library_populate_filesystem_data(self.library_get_data(self.config.wd, 'path'))
            elif self.config.lib_view == consts.VIEW_ALBUM:
                album, artist, year = self.library_get_data(self.config.wd, 'album', 'artist', 'year')
                if album is not None:
                    bd = self.library_populate_data(artist=artist, album=album, year=year)
                else:
                    bd = self.library_populate_toplevel_data(albumview=True)
            elif self.config.lib_view == consts.VIEW_ARTIST:
                artist, album, year = self.library_get_data(self.config.wd, 'artist', 'album', 'year')
                if artist is not None and album is not None:
                    bd = self.library_populate_data(artist=artist, album=album, year=year)
                elif artist is not None:
                    bd = self.library_populate_data(artist=artist)
                else:
                    bd = self.library_populate_toplevel_data(artistview=True)
            elif self.config.lib_view == consts.VIEW_GENRE:
                genre, artist, album, year = self.library_get_data(self.config.wd, 'genre', 'artist', 'album', 'year')
                if genre is not None and artist is not None and album is not None:
                    bd = self.library_populate_data(genre=genre, artist=artist, album=album, year=year)
                elif genre is not None and artist is not None:
                    bd = self.library_populate_data(genre=genre, artist=artist)
                elif genre is not None:
                    bd = self.library_populate_data(genre=genre)
                else:
                    bd = self.library_populate_toplevel_data(genreview=True)

            if len(bd) == 0:
                # Nothing found; go up a level until we reach the top level
                # or results are found
                last_wd = self.config.wd
                self.config.wd = self.library_get_parent()
                if self.config.wd == last_wd:
                    break

        for _sort, path in bd:
            self.librarydata.append(path)

        self.library.thaw_child_notify()

        # Scroll back to set view for current dir:
        self.library.realize()
        gobject.idle_add(self.library_set_view, not path_updated)
        if len(prev_selection) > 0 or prev_selection_root or prev_selection_parent:
            # Retain pre-update selection:
            self.library_retain_selection(prev_selection, prev_selection_root, prev_selection_parent)

        # Update library artwork as necessary
        self.on_library_scrolled(None, None)

    def library_populate_add_parent_rows(self):
        bd = [('0', [self.harddiskpb, self.library_set_data(path='/'), '/'])]
        bd += [('1', [self.openpb, self.library_set_data(path='..'), '..'])]
        return bd

    def library_populate_filesystem_data(self, path):
        # List all dirs/files at path
        bd = []
        if path == '/' and self.lib_view_filesystem_cache is not None:
            # Use cache if possible...
            bd = self.lib_view_filesystem_cache
        else:
            for item in mpdh.call(self.client, 'lsinfo', path):
                if 'directory' in item:
                    name = mpdh.get(item, 'directory').split('/')[-1]
                    data = self.library_set_data(path=mpdh.get(item, 'directory'))
                    bd += [('d' + unicode(name).lower(), [self.openpb, data, misc.escape_html(name)])]
                elif 'file' in item:
                    data = self.library_set_data(path=mpdh.get(item, 'file'))
                    bd += [('f' + unicode(mpdh.get(item, 'file')).lower(), [self.sonatapb, data, self.parse_formatting(self.config.libraryformat, item, True)])]
            bd.sort(key=misc.first_of_2tuple)
            if path != '/' and len(bd) > 0:
                bd = self.library_populate_add_parent_rows() + bd
            if path == '/':
                self.lib_view_filesystem_cache = bd
        return bd

    def library_get_toplevel_cache(self, genreview=False, artistview=False, albumview=False):
        if genreview and self.lib_view_genre_cache is not None:
            bd = self.lib_view_genre_cache
        elif artistview and self.lib_view_artist_cache is not None:
            bd = self.lib_view_artist_cache
        elif albumview and self.lib_view_album_cache is not None:
            bd = self.lib_view_album_cache
        else:
            return None
        # Check if we can update any artwork:
        for _sort, info in bd:
            pb = info[0]
            if pb == self.albumpb:
                artist, album, path = self.library_get_data(info[1], 'artist', 'album', 'path')
                key = self.library_set_data(path=path, artist=artist, album=album)
                pb2 = self.artwork.get_library_artwork_cached_pb(key, None)
                if pb2 is not None:
                    info[0] = pb2
        return bd

    def library_populate_toplevel_data(self, genreview=False, artistview=False, albumview=False):
        bd = self.library_get_toplevel_cache(genreview, artistview, albumview)
        if bd is not None:
            # We have our cached data, woot.
            return bd
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
            if not (self.NOTAG in items):
                items.append(self.NOTAG)
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
            albums = []
            untagged_found = False
            for item in mpdh.call(self.client, 'listallinfo', '/'):
                if 'file' in item and 'album' in item:
                    album = mpdh.get(item, 'album')
                    artist = mpdh.get(item, 'artist', self.NOTAG)
                    year = mpdh.get(item, 'date', self.NOTAG)
                    filepath = os.path.dirname(mpdh.get(item, 'file'))
                    data = self.library_set_data(album=album, artist=artist, year=year, path=filepath)
                    albums.append(data)
                    if album == self.NOTAG:
                        untagged_found = True
            if not untagged_found:
                albums.append(self.library_set_data(album=self.NOTAG))
            albums = misc.remove_list_duplicates(albums, case=False)
            albums = self.list_identify_VA_albums(albums)
            for item in albums:
                album, artist, year, path = self.library_get_data(item, 'album', 'artist', 'year', 'path')
                playtime, num_songs = self.library_return_count(artist=artist, album=album, year=year)
                if num_songs > 0:
                    data = self.library_set_data(artist=artist, album=album, year=year, path=path)
                    cache_data = self.library_set_data(artist=artist, album=album, path=path)
                    display = misc.escape_html(album)
                    if artist and year and len(artist) > 0 and len(year) > 0 and artist != self.NOTAG and year != self.NOTAG:
                        display += " <span weight='light'>(" + misc.escape_html(artist) + ", " + misc.escape_html(year) + ")</span>"
                    elif artist and len(artist) > 0 and artist != self.NOTAG:
                        display += " <span weight='light'>(" + misc.escape_html(artist) + ")</span>"
                    elif year and len(year) > 0 and year != self.NOTAG:
                        display += " <span weight='light'>(" + misc.escape_html(year) + ")</span>"
                    display += self.add_display_info(num_songs, int(playtime)/60)
                    pb = self.artwork.get_library_artwork_cached_pb(cache_data, self.albumpb)
                    bd += [(misc.lower_no_the(album), [pb, data, display])]
        bd.sort(locale.strcoll, key=misc.first_of_2tuple)
        if genreview:
            self.lib_view_genre_cache = bd
        elif artistview:
            self.lib_view_artist_cache = bd
        elif albumview:
            self.lib_view_album_cache = bd
        return bd

    def list_identify_VA_albums(self, albums):
        for i in range(len(albums)):
            if i + consts.NUM_ARTISTS_FOR_VA - 1 > len(albums)-1:
                break
            VA = False
            for j in range(1, consts.NUM_ARTISTS_FOR_VA):
                if unicode(self.library_get_data(albums[i], 'album')).lower() != unicode(self.library_get_data(albums[i+j], 'album')).lower() \
                or self.library_get_data(albums[i], 'year') != self.library_get_data(albums[i+j], 'year'):
                    break
                if j == consts.NUM_ARTISTS_FOR_VA - 1:
                    VA = True
            if VA:
                album, year, path = self.library_get_data(albums[i], 'album', 'year', 'path')
                artist = self.VAstr
                albums[i] = self.library_set_data(album=album, artist=artist, year=year, path=path)
                j = 1
                while i+j <= len(albums)-1:
                    if unicode(self.library_get_data(albums[i], 'album')).lower() == unicode(self.library_get_data(albums[i+j], 'album')).lower() \
                    and self.library_get_data(albums[i], 'year') == self.library_get_data(albums[i+j], 'year'):
                        albums.pop(i+j)
                    else:
                        break
        return albums

    def library_populate_data(self, genre=None, artist=None, album=None, year=None):
        # Create treeview model info
        bd = []
        if genre is not None and artist is None and album is None:
            # Artists within a genre
            artists = self.library_return_list_items('artist', genre=genre)
            if len(artists) > 0:
                if not self.NOTAG in artists:
                    artists.append(self.NOTAG)
                for artist in artists:
                    playtime, num_songs = self.library_return_count(genre=genre, artist=artist)
                    if num_songs > 0:
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
                if not self.NOTAG in years:
                    years.append(self.NOTAG)
                for year in years:
                    if genre is not None:
                        playtime, num_songs = self.library_return_count(genre=genre, artist=artist, album=album, year=year)
                        if num_songs > 0:
                            files = self.library_return_list_items('file', genre=genre, artist=artist, album=album, year=year)
                            path = os.path.dirname(files[0])
                            data = self.library_set_data(genre=genre, artist=artist, album=album, year=year, path=path)
                    else:
                        playtime, num_songs = self.library_return_count(artist=artist, album=album, year=year)
                        if num_songs > 0:
                            files = self.library_return_list_items('file', artist=artist, album=album, year=year)
                            path = os.path.dirname(files[0])
                            data = self.library_set_data(artist=artist, album=album, year=year, path=path)
                    if num_songs > 0:
                        cache_data = self.library_set_data(artist=artist, album=album, path=path)
                        display = misc.escape_html(album)
                        if year and len(year) > 0 and year != self.NOTAG:
                            display += " <span weight='light'>(" + misc.escape_html(year) + ")</span>"
                        display += self.add_display_info(num_songs, int(playtime)/60)
                        ordered_year = year
                        if ordered_year == self.NOTAG:
                            ordered_year = '9999'
                        pb = self.artwork.get_library_artwork_cached_pb(cache_data, self.albumpb)
                        bd += [(ordered_year + misc.lower_no_the(album), [pb, data, display])]
            # Now, songs not in albums:
            bd += self.library_populate_data_songs(genre, artist, self.NOTAG, None)
        else:
            # Songs within an album, artist, year, and possibly genre
            bd += self.library_populate_data_songs(genre, artist, album, year)
        if len(bd) > 0:
            bd = self.library_populate_add_parent_rows() + bd
        bd.sort(locale.strcoll, key=misc.first_of_2tuple)
        return bd

    def library_populate_data_songs(self, genre, artist, album, year):
        bd = []
        if genre is not None:
            songs, _playtime, _num_songs = self.library_return_search_items(genre=genre, artist=artist, album=album, year=year)
        else:
            songs, _playtime, _num_songs = self.library_return_search_items(artist=artist, album=album, year=year)
        for song in songs:
            data = self.library_set_data(path=mpdh.get(song, 'file'))
            track = mpdh.getnum(song, 'track', '99', False, 2)
            disc = mpdh.getnum(song, 'disc', '99', False, 2)
            try:
                bd += [('f' + disc + track + misc.lower_no_the(mpdh.get(song, 'title')), [self.sonatapb, data, self.parse_formatting(self.config.libraryformat, song, True)])]
            except:
                bd += [('f' + disc + track + unicode(mpdh.get(song, 'file')).lower(), [self.sonatapb, data, self.parse_formatting(self.config.libraryformat, song, True)])]
        return bd

    def library_return_list_items(self, itemtype, genre=None, artist=None, album=None, year=None, ignore_case=True):
        # Returns all items of tag 'itemtype', in alphabetical order,
        # using mpd's 'list'. If searchtype is passed, use
        # a case insensitive search, via additional 'list'
        # queries, since using a single 'list' call will be
        # case sensitive.
        results = []
        searches = self.library_compose_list_count_searchlist(genre, artist, album, year)
        if len(searches) > 0:
            for s in searches:
                # If we have untagged tags (''), use search instead
                # of list because list will not return anything.
                if '' in s:
                    items = []
                    songs, playtime, num_songs = self.library_return_search_items(genre, artist, album, year)
                    for song in songs:
                        items.append(mpdh.get(song, itemtype))
                else:
                    items = mpdh.call(self.client, 'list', itemtype, *s)
                for item in items:
                    if len(item) > 0:
                        results.append(item)
        else:
            if genre is None and artist is None and album is None and year is None:
                for item in mpdh.call(self.client, 'list', itemtype):
                    if len(item) > 0:
                        results.append(item)
        if ignore_case:
            results = misc.remove_list_duplicates(results, case=False)
        results.sort(locale.strcoll)
        return results

    def library_return_count(self, genre=None, artist=None, album=None, year=None):
        # Because mpd's 'count' is case sensitive, we have to
        # determine all equivalent items (case insensitive) and
        # call 'count' for each of them. Using 'list' + 'count'
        # involves much less data to be transferred back and
        # forth than to use 'search' and count manually.
        searches = self.library_compose_list_count_searchlist(genre, artist, album, year)
        playtime = 0
        num_songs = 0
        for s in searches:
            count = mpdh.call(self.client, 'count', *s)
            playtime += int(mpdh.get(count, 'playtime'))
            num_songs += int(mpdh.get(count, 'songs'))
        return (playtime, num_songs)

    def library_compose_list_count_searchlist_single(self, search, typename, cached_list, searchlist):
        s = []
        skip_type = (typename == 'artist' and search == self.VAstr)
        if search is not None and not skip_type:
            if search == self.NOTAG:
                itemlist = [search, '']
            else:
                itemlist = []
                if cached_list is None:
                    cached_list = self.library_return_list_items(typename, ignore_case=False)
                    cached_list.append('') # This allows us to match untagged items
                for item in cached_list:
                    if unicode(item).lower() == unicode(search).lower():
                        itemlist.append(item)
            if len(itemlist) == 0:
                # There should be no results!
                return None, cached_list
            for item in itemlist:
                if len(searchlist) > 0:
                    for item2 in searchlist:
                        s.append(item2 + (typename, item))
                else:
                    s.append((typename, item))
        else:
            s = searchlist
        return s, cached_list

    def library_compose_list_count_searchlist(self, genre=None, artist=None, album=None, year=None):
        s = []
        s, self.lib_list_genres = self.library_compose_list_count_searchlist_single(genre, 'genre', self.lib_list_genres, s)
        if s is None:
            return []
        s, self.lib_list_artists = self.library_compose_list_count_searchlist_single(artist, 'artist', self.lib_list_artists, s)
        if s is None:
            return []
        s, self.lib_list_albums = self.library_compose_list_count_searchlist_single(album, 'album', self.lib_list_albums, s)
        if s is None:
            return []
        s, self.lib_list_years = self.library_compose_list_count_searchlist_single(year, 'date', self.lib_list_years, s)
        if s is None:
            return []
        return s

    def library_compose_search_searchlist_single(self, search, typename, searchlist):
        s = []
        skip_type = (typename == 'artist' and search == self.VAstr)
        if search is not None and not skip_type:
            if search == self.NOTAG:
                itemlist = [search, '']
            else:
                itemlist = [search]
            for item in itemlist:
                if len(searchlist) > 0:
                    for item2 in searchlist:
                        s.append(item2 + (typename, item))
                else:
                    s.append((typename, item))
        else:
            s = searchlist
        return s

    def library_compose_search_searchlist(self, genre=None, artist=None, album=None, year=None):
        s = []
        s = self.library_compose_search_searchlist_single(genre, 'genre', s)
        s = self.library_compose_search_searchlist_single(album, 'album', s)
        s = self.library_compose_search_searchlist_single(artist, 'artist', s)
        s = self.library_compose_search_searchlist_single(year, 'date', s)
        return s

    def library_return_search_items(self, genre=None, artist=None, album=None, year=None):
        # Returns all mpd items, using mpd's 'search', along with
        # playtime and num_songs. Note that if one of the args is
        # '', the search results will only be correct for mpd=0.14
        searches = self.library_compose_search_searchlist(genre, artist, album, year)
        for s in searches:
            args_tuple = tuple(map(str, s))
            playtime = 0
            num_songs = 0
            results = []
            items = mpdh.call(self.client, 'search', *args_tuple)
            if items is not None:
                for item in items:
                    results.append(item)
                    num_songs += 1
                    playtime += int(mpdh.get(item, 'time', '0'))
        return (results, int(playtime), num_songs)

    def add_display_info(self, num_songs, playtime):
        return "\n<small><span weight='light'>" + str(num_songs) + " " + gettext.ngettext('song', 'songs', num_songs) + ", " + str(playtime) + " " + gettext.ngettext('minute', 'minutes', playtime) + "</span></small>"

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
            if self.config.wd in self.libraryposition:
                self.library.scroll_to_point(-1, self.libraryposition[self.config.wd])
            else:
                self.library.scroll_to_point(0, 0)
        except:
            self.library.scroll_to_point(0, 0)

        # Select and focus previously selected item
        if select_items:
            if self.config.wd in self.libraryselectedpath:
                try:
                    if self.libraryselectedpath[self.config.wd]:
                        self.library_selection.select_path(self.libraryselectedpath[self.config.wd])
                        self.library.grab_focus()
                except:
                    pass

    def library_set_data(self, *args, **kwargs):
        return library_set_data(*args, **kwargs)

    def library_get_data(self, data, *args):
        return library_get_data(data, *args)

    def library_get_data_level(self, data):
        dl = data.split(consts.LIB_DELIM)
        if self.config.lib_view == consts.VIEW_FILESYSTEM:
            # Returns the number of directories down:
            if dl[name_to_index['path']] == '/':
                # Every other path doesn't start with "/", so
                # start the level numbering at -1
                return -1
            else:
                return dl[name_to_index['path']].count("/")
        else:
            # Returns the number of items stored in data, excluding
            # the path:
            level = 0
            for i, item in enumerate(dl):
                if item != consts.LIB_NODATA and i != name_to_index['path']:
                    level += 1
            return level

    def on_library_key_press(self, widget, event):
        if event.keyval == gtk.gdk.keyval_from_name('Return'):
            self.on_library_row_activated(widget, widget.get_cursor()[0])
            return True

    def on_library_query_tooltip(self, widget, x, y, keyboard_mode, tooltip):
        if keyboard_mode or not self.search_visible():
            widget.set_tooltip_text(None)
            return False

        bin_x, bin_y = widget.convert_widget_to_bin_window_coords(x, y)

        path, _col, _x2, _y2 = widget.get_path_at_pos(bin_x, bin_y)
        if not path:
            widget.set_tooltip_text(None)
            return False

        i = self.librarydata.get_iter(path[0])
        path = misc.escape_html(self.librarydata.get_value(i, 1))
        song = self.librarydata.get_value(i, 2)
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

    def on_library_row_activated(self, _widget, path, _column=0):
        if path is None:
            # Default to last item in selection:
            _model, selected = self.library_selection.get_selected_rows()
            if len(selected) >= 1:
                path = selected[0]
            else:
                return
        value = self.librarydata.get_value(self.librarydata.get_iter(path), 1)
        icon = self.librarydata.get_value(self.librarydata.get_iter(path), 0)
        if icon == self.sonatapb:
            # Song found, add item
            self.on_add_item(self.library)
        elif value == self.library_set_data(path=".."):
            self.library_browse_parent(None)
        else:
            self.library_browse(None, value)

    def library_get_parent(self):
        if self.config.lib_view == consts.VIEW_ALBUM:
            value = self.library_set_data(path="/")
        elif self.config.lib_view == consts.VIEW_ARTIST:
            album, artist = self.library_get_data(self.config.wd, 'album', 'artist')
            if album is not None:
                value = self.library_set_data(artist=artist)
            else:
                value = self.library_set_data(path="/")
        elif self.config.lib_view == consts.VIEW_GENRE:
            album, artist, genre = self.library_get_data(self.config.wd, 'album', 'artist', 'genre')
            if album is not None:
                value = self.library_set_data(genre=genre, artist=artist)
            elif artist is not None:
                value = self.library_set_data(genre=genre)
            else:
                value = self.library_set_data(path="/")
        else:
            newvalue = '/'.join(self.library_get_data(self.config.wd, 'path').split('/')[:-1]) or '/'
            value = self.library_set_data(path=newvalue)
        return value

    def library_browse_parent(self, _action):
        if not self.search_visible():
            if self.library.is_focus():
                value = self.library_get_parent()
                self.library_browse(None, value)
                return True

    def get_path_child_filenames(self, return_root):
        # If return_root=True, return main directories whenever possible
        # instead of individual songs in order to reduce the number of
        # mpd calls we need to make. We won't want this behavior in some
        # instances, like when we want all end files for editing tags
        items = []
        model, selected = self.library_selection.get_selected_rows()
        for path in selected:
            i = model.get_iter(path)
            pb = model.get_value(i, 0)
            data = model.get_value(i, 1)
            value = model.get_value(i, 2)
            if value != ".." and value != "/":
                album, artist, year, genre, path = self.library_get_data(data, 'album', 'artist', 'year', 'genre', 'path')
                if path is not None and album is None and artist is None and year is None and genre is None:
                    if pb == self.sonatapb:
                        # File
                        items.append(path)
                    else:
                        # Directory
                        if not return_root:
                            items = items + self.library_get_path_files_recursive(path)
                        else:
                            items.append(path)
                else:
                    results, _playtime, _num_songs = self.library_return_search_items(genre=genre, artist=artist, album=album, year=year)
                    results.sort(key=lambda x: (unicode(mpdh.get(x, 'genre', 'zzz')).lower(), unicode(mpdh.get(x, 'artist', 'zzz')).lower(), unicode(mpdh.get(x, 'album', 'zzz')).lower(), mpdh.getnum(x, 'disc', '0', True, 0), mpdh.getnum(x, 'track', '0', True, 0), mpdh.get(x, 'file')))
                    for item in results:
                        items.append(mpdh.get(item, 'file'))
        # Make sure we don't have any EXACT duplicates:
        items = misc.remove_list_duplicates(items, case=True)
        return items

    def library_get_path_files_recursive(self, path):
        results = []
        for item in mpdh.call(self.client, 'lsinfo', path):
            if 'directory' in item:
                results = results + self.library_get_path_files_recursive(mpdh.get(item, 'directory'))
            elif 'file' in item:
                results.append(mpdh.get(item, 'file'))
        return results

    def on_library_search_combo_change(self, combo):
        self.config.last_search_num = combo.get_active()
        self.prevlibtodo = ""
        self.libsearchfilter_feed_loop(self.searchtext)

    def on_search_end(self, _button, move_focus=True):
        if self.search_visible():
            self.libsearchfilter_toggle(move_focus)

    def search_visible(self):
        return self.searchbutton.get_property('visible')


    def libsearchfilter_toggle(self, move_focus):
        if not self.search_visible() and self.connected():
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
        elif self.search_visible():
            ui.hide(self.searchbutton)
            self.searchtext.handler_block(self.libfilter_changed_handler)
            self.searchtext.set_text("")
            self.searchtext.handler_unblock(self.libfilter_changed_handler)
            self.libsearchfilter_stop_loop()
            self.library_browse(root=self.config.wd)
            if move_focus:
                self.library.grab_focus()

    def libsearchfilter_feed_loop(self, editable):
        if not self.search_visible():
            self.libsearchfilter_toggle(None)
        # Lets only trigger the searchfilter_loop if 200ms pass without a change
        # in gtk.Entry
        try:
            gobject.source_remove(self.libfilterbox_source)
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
        self.libfilterbox_cmd_buf = '$$$QUIT###'
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
            searchby = self.search_terms_mpd[self.config.last_search_num]
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
            self.libfilterbox_cmd_buf = '$$$DONE###'
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
                if regexp.match(unicode(mpdh.get(row, searchby)).lower()):
                    matches.append(row)
        else:
            for row in self.prevlibtodo_base_results:
                for meta in row:
                    if regexp.match(unicode(mpdh.get(row, meta)).lower()):
                        matches.append(row)
                        break
        if subsearch and len(matches) == len(self.librarydata):
            # nothing changed..
            return
        self.library.freeze_child_notify()
        currlen = len(self.librarydata)
        newlist = []
        for item in matches:
            if 'file' in item:
                newlist.append([self.sonatapb, self.library_set_data(path=mpdh.get(item, 'file')), self.parse_formatting(self.config.libraryformat, item, True)])
        for i, item in enumerate(newlist):
            if i < currlen:
                j = self.librarydata.get_iter((i, ))
                for index in range(len(item)):
                    if item[index] != self.librarydata.get_value(j, index):
                        self.librarydata.set_value(j, index, item[index])
            else:
                self.librarydata.append(item)
        # Remove excess items...
        newlen = len(newlist)
        if newlen == 0:
            self.librarydata.clear()
        else:
            for i in range(currlen-newlen):
                j = self.librarydata.get_iter((currlen-1-i,))
                self.librarydata.remove(j)
        self.library.thaw_child_notify()
        if len(matches) == 0:
            gobject.idle_add(self.filtering_entry_make_red, self.searchtext)
        else:
            gobject.idle_add(self.library.set_cursor,'0')
            gobject.idle_add(self.filtering_entry_revert_color, self.searchtext)

    def libsearchfilter_key_pressed(self, widget, event):
        self.filter_key_pressed(widget, event, self.library)

    def libsearchfilter_on_enter(self, _entry):
        self.on_library_row_activated(None, None)

    def libsearchfilter_set_focus(self):
        gobject.idle_add(self.searchtext.grab_focus)

    def libsearchfilter_get_style(self):
        return self.searchtext.get_style()
