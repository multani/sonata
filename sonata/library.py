import os
import re
import gettext
import locale
import threading # libsearchfilter_toggle starts thread libsearchfilter_loop
import operator

from gi.repository import Gtk, Gdk, GdkPixbuf, GObject, GLib, Pango

from sonata import ui, misc, consts, formatting, breadcrumbs, mpdhelper as mpdh
from sonata.song import SongRecord


VARIOUS_ARTISTS = _("Various Artists")


def list_mark_various_artists_albums(albums):
    for i in range(len(albums)):
        if i + consts.NUM_ARTISTS_FOR_VA - 1 > len(albums)-1:
            break
        VA = False
        for j in range(1, consts.NUM_ARTISTS_FOR_VA):
            if albums[i].album.lower() != albums[i + j].album.lower() or \
               albums[i].year  != albums[i + j].year or \
               albums[i].path  != albums[i + j].path:
                break
            if albums[i].artist == albums[i + j].artist:
                albums.pop(i + j)
                break
            if j == consts.NUM_ARTISTS_FOR_VA - 1:
                VA = True
        if VA:
            albums[i].artist = VARIOUS_ARTISTS
            j = 1
            while i + j <= len(albums) - 1:
                if albums[i].album.lower() == albums[i + j].album.lower() \
                   and albums[i].year == albums[i + j].year:
                    albums.pop(i + j)
                else:
                    break
    return albums


class Library:
    def __init__(self, config, mpd, artwork, TAB_LIBRARY, settings_save,
                 filter_key_pressed, on_add_item, connected,
                 on_library_button_press, add_tab, get_multicd_album_root_dir):
        self.artwork = artwork
        self.config = config
        self.mpd = mpd
        self.librarymenu = None # cyclic dependency, set later
        self.settings_save = settings_save
        self.filter_key_pressed = filter_key_pressed
        self.on_add_item = on_add_item
        self.connected = connected
        self.on_library_button_press = on_library_button_press
        self.get_multicd_album_root_dir = get_multicd_album_root_dir

        self.NOTAG = _("Untagged")
        self.search_terms = [_('Artist'), _('Title'), _('Album'), _('Genre'),
                             _('Filename'), _('Everything')]
        self.search_terms_mpd = ['artist', 'title', 'album', 'genre', 'file',
                                 'any']

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

        # Library tab
        self.builder = ui.builder('library')
        self.css_provider = ui.css_provider('library')

        self.libraryvbox = self.builder.get_object('library_page_v_box')
        self.library = self.builder.get_object('library_page_treeview')
        self.library_selection = self.library.get_selection()
        self.breadcrumbs = self.builder.get_object('library_crumbs_box')
        self.crumb_section = self.builder.get_object(
            'library_crumb_section_togglebutton')
        self.crumb_section_image = self.builder.get_object(
            'library_crumb_section_image')
        self.crumb_break = self.builder.get_object(
            'library_crumb_break_box')
        self.breadcrumbs.set_crumb_break(self.crumb_break)
        self.crumb_section_handler = None
        expanderwindow2 = self.builder.get_object('library_page_scrolledwindow')
        self.searchbox = self.builder.get_object('library_page_searchbox')
        self.searchcombo = self.builder.get_object('library_page_searchbox_combo')
        self.searchtext = self.builder.get_object('library_page_searchbox_entry')
        self.searchbutton = self.builder.get_object('library_page_searchbox_button')
        self.searchbutton.hide()
        self.libraryview = self.builder.get_object('library_crumb_button')
        self.tab_label_widget = self.builder.get_object('library_tab_eventbox')
        tab_label = self.builder.get_object('library_tab_label')
        tab_label.set_text(TAB_LIBRARY)

        self.tab = add_tab(self.libraryvbox, self.tab_label_widget,
                           TAB_LIBRARY, self.library)

        # Assign some pixbufs for use in self.library
        self.openpb2 = self.library.render_icon(Gtk.STOCK_OPEN,
                                                Gtk.IconSize.LARGE_TOOLBAR)
        self.harddiskpb2 = self.library.render_icon(Gtk.STOCK_HARDDISK,
                                                   Gtk.IconSize.LARGE_TOOLBAR)
        self.openpb = self.library.render_icon(Gtk.STOCK_OPEN,
                                               Gtk.IconSize.MENU)
        self.harddiskpb = self.library.render_icon(Gtk.STOCK_HARDDISK,
                                                   Gtk.IconSize.MENU)
        self.albumpb = self.library.render_icon('sonata-album',
                                                Gtk.IconSize.LARGE_TOOLBAR)
        self.genrepb = self.library.render_icon('gtk-orientation-portrait',
                                                Gtk.IconSize.LARGE_TOOLBAR)
        self.artistpb = self.library.render_icon('sonata-artist',
                                                 Gtk.IconSize.LARGE_TOOLBAR)
        self.sonatapb = self.library.render_icon('sonata',
                                                 Gtk.IconSize.LARGE_TOOLBAR)

        # list of the library views: (id, name, icon name, label)
        self.VIEWS = [
            (consts.VIEW_FILESYSTEM, 'filesystem',
             Gtk.STOCK_HARDDISK, _("Filesystem")),
            (consts.VIEW_ALBUM, 'album',
             'sonata-album', _("Albums")),
            (consts.VIEW_ARTIST, 'artist',
             'sonata-artist', _("Artists")),
            (consts.VIEW_GENRE, 'genre',
             Gtk.STOCK_ORIENTATION_PORTRAIT, _("Genres")),
            ]

        self.library.connect('row_activated', self.on_library_row_activated)
        self.library.connect('button_press_event',
                             self.on_library_button_press)
        self.library.connect('key-press-event', self.on_library_key_press)
        self.library.connect('query-tooltip', self.on_library_query_tooltip)
        expanderwindow2.connect('scroll-event', self.on_library_scrolled)
        self.libraryview.connect('clicked', self.library_view_popup)
        self.searchtext.connect('key-press-event',
                                self.libsearchfilter_key_pressed)
        self.searchtext.connect('activate', self.libsearchfilter_on_enter)
        self.searchbutton.connect('clicked', self.on_search_end)

        self.libfilter_changed_handler = self.searchtext.connect(
            'changed', self.libsearchfilter_feed_loop)
        searchcombo_changed_handler = self.searchcombo.connect(
            'changed', self.on_library_search_combo_change)

        # Initialize library data and widget
        self.libraryposition = {}
        self.libraryselectedpath = {}
        self.searchcombo.handler_block(searchcombo_changed_handler)
        self.searchcombo.set_active(self.config.last_search_num)
        self.searchcombo.handler_unblock(searchcombo_changed_handler)
        self.librarydata = Gtk.ListStore(GdkPixbuf.Pixbuf,
                                         GObject.TYPE_PYOBJECT, str)
        self.library.set_model(self.librarydata)
        self.library.set_search_column(2)
        self.librarycell = Gtk.CellRendererText()
        self.librarycell.set_property("ellipsize", Pango.EllipsizeMode.END)
        self.libraryimg = Gtk.CellRendererPixbuf()
        self.librarycolumn = Gtk.TreeViewColumn()
        self.librarycolumn.pack_start(self.libraryimg, False)
        self.librarycolumn.pack_start(self.librarycell, True)
        self.librarycolumn.add_attribute(self.libraryimg, 'pixbuf', 0)
        self.librarycolumn.add_attribute(self.librarycell, 'markup', 2)
        self.librarycolumn.set_sizing(Gtk.TreeViewColumnSizing.AUTOSIZE)
        self.library.append_column(self.librarycolumn)
        self.library_selection.set_mode(Gtk.SelectionMode.MULTIPLE)

    def get_libraryactions(self):
        return [(name + 'view', icon, label,
             None, None, self.on_libraryview_chosen)
            for _view, name, icon, label in self.VIEWS]

    def get_model(self):
        return self.librarydata

    def get_widgets(self):
        return self.libraryvbox

    def get_treeview(self):
        return self.library

    def get_selection(self):
        return self.library_selection

    def set_librarymenu(self, librarymenu):
        self.librarymenu = librarymenu
        self.librarymenu.attach_to_widget(self.libraryview, None)

    def library_view_popup(self, button):
        self.librarymenu.popup(None, None, self.library_view_position_menu,
                               button, 1, 0)

    def library_view_position_menu(self, _menu, button):
        alloc = button.get_allocation()
        return (self.config.x + alloc.x,
                self.config.y + alloc.y + alloc.height,
                True)

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
        self.libraryposition = {}
        self.libraryselectedpath = {}
        self.library_browse(root=SongRecord(path="/"))
        try:
            if len(self.librarydata) > 0:
                first = Gtk.TreePath.new_first()
                to = Gtk.TreePath.new()
                to.append_index(len(self.librarydata) - 1)
                self.library_selection.unselect_range(first, to)
        except Exception as e:
            # XXX import logger here in the future
            raise e
        GLib.idle_add(self.library.scroll_to_point, 0, 0)

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
            # Use GLib.idle_add so that we can get the visible
            # state of the treeview
            GLib.idle_add(self._on_library_scrolled)
        except:
            pass

    def _on_library_scrolled(self):
        if not self.config.show_covers:
            return

        # This avoids a warning about a NULL node in get_visible_range
        if not self.library.props.visible:
            return

        visible_range = self.library.get_visible_range()

        if visible_range is None:
            return
        else:
            start_row, end_row = visible_range

        self.artwork.library_artwork_update(self.librarydata, start_row,
                                            end_row, self.albumpb)

    def library_browse(self, _widget=None, root=None):
        # Populates the library list with entries
        if not self.connected():
            return

        if root is None or (self.config.lib_view == consts.VIEW_FILESYSTEM \
                            and root.path is None):
            root = SongRecord(path="/")
        if self.config.wd is None or (self.config.lib_view == \
                                      consts.VIEW_FILESYSTEM and \
                                      self.config.wd.path is None):
            self.config.wd = SongRecord(path="/")

        prev_selection = []
        prev_selection_root = False
        prev_selection_parent = False
        if root == self.config.wd:
            # This will happen when the database is updated. So, lets save
            # the current selection in order to try to re-select it after
            # the update is over.
            model, selected = self.library_selection.get_selected_rows()
            for path in selected:
                prev_selection.append(model.get_value(model.get_iter(path), 1))
            self.libraryposition[self.config.wd] = \
                    self.library.get_visible_rect().width
            path_updated = True
        else:
            path_updated = False

        new_level = self.library_get_data_level(root)
        curr_level = self.library_get_data_level(self.config.wd)
        # The logic below is more consistent with, e.g., thunar.
        if new_level > curr_level:
            # Save position and row for where we just were if we've
            # navigated into a sub-directory:
            self.libraryposition[self.config.wd] = \
                    self.library.get_visible_rect().width
            model, rows = self.library_selection.get_selected_rows()
            if len(rows) > 0:
                data = self.librarydata.get_value(
                    self.librarydata.get_iter(rows[0]), 2)
                self.libraryselectedpath[self.config.wd] = rows[0]
        elif (self.config.lib_view == consts.VIEW_FILESYSTEM and \
              root != self.config.wd) \
        or (self.config.lib_view != consts.VIEW_FILESYSTEM and new_level != \
            curr_level):
            # If we've navigated to a parent directory, don't save
            # anything so that the user will enter that subdirectory
            # again at the top position with nothing selected
            self.libraryposition[self.config.wd] = 0
            self.libraryselectedpath[self.config.wd] = None

        # In case sonata is killed or crashes, we'll save the library state
        # in 5 seconds (first removing any current settings_save timeouts)
        if self.config.wd != root:
            try:
                GLib.source_remove(self.save_timeout)
            except:
                pass
            self.save_timeout = GLib.timeout_add(5000, self.settings_save)

        self.config.wd = root
        self.library.freeze_child_notify()
        self.librarydata.clear()

        # Populate treeview with data:
        bd = []
        wd = self.config.wd
        while len(bd) == 0:
            if self.config.lib_view == consts.VIEW_FILESYSTEM:
                bd = self.library_populate_filesystem_data(wd.path)
            elif self.config.lib_view == consts.VIEW_ALBUM:
                if wd.album is not None:
                    bd = self.library_populate_data(artist=wd.artist,
                                                    album=wd.album,
                                                    year=wd.year)
                else:
                    bd = self.library_populate_toplevel_data(albumview=True)
            elif self.config.lib_view == consts.VIEW_ARTIST:
                if wd.artist is not None and wd.album is not None:
                    bd = self.library_populate_data(artist=wd.artist,
                                                    album=wd.album,
                                                    year=wd.year)
                elif self.config.wd.artist is not None:
                    bd = self.library_populate_data(artist=wd.artist)
                else:
                    bd = self.library_populate_toplevel_data(artistview=True)
            elif self.config.lib_view == consts.VIEW_GENRE:
                if wd.genre is not None and \
                   wd.artist is not None and \
                   wd.album is not None:
                    bd = self.library_populate_data(genre=wd.genre,
                                                    artist=wd.artist,
                                                    album=wd.album,
                                                    year=wd.year)
                elif wd.genre is not None:
                    bd = self.library_populate_data(genre=wd.genre,
                                                    artist=wd.artist)
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
        GLib.idle_add(self.library_set_view, not path_updated)
        if len(prev_selection) > 0 or prev_selection_root or \
           prev_selection_parent:
            # Retain pre-update selection:
            self.library_retain_selection(prev_selection, prev_selection_root,
                                          prev_selection_parent)

        # Update library artwork as necessary
        self.on_library_scrolled(None, None)

        self.update_breadcrumbs()

    def update_breadcrumbs(self):
        # remove previous buttons
        for b in self.breadcrumbs:
            self.breadcrumbs.remove(b)

        # find info for current view
        view, _name, icon, label = [v for v in self.VIEWS
                          if v[0] == self.config.lib_view][0]

        # the first crumb is the root of the current view
        self.crumb_section.set_label(label)
        self.crumb_section_image.set_from_stock(icon, Gtk.IconSize.MENU)
        self.crumb_section.set_tooltip_text(label)
        if self.crumb_section_handler:
            self.crumb_section.disconnect(self.crumb_section_handler)


        crumbs = []
        # crumbs are specific to the view
        if view == consts.VIEW_FILESYSTEM:
            if self.config.wd.path and self.config.wd.path != '/':
                parts = self.config.wd.path.split('/')
            else:
                parts = [] # no crumbs for /
            # append a crumb for each part
            for i, part in enumerate(parts):
                partpath = '/'.join(parts[:i + 1])
                target = SongRecord(path=partpath)
                crumbs.append((part, Gtk.STOCK_OPEN, None, target))
        else:
            parts = ()
            if view == consts.VIEW_ALBUM:
                # We don't want to show an artist button in album view
                keys = 'genre', 'album'
                nkeys = 2
                parts = (self.config.wd.genre, self.config.wd.album)
            else:
                keys = 'genre', 'artist', 'album'
                nkeys = 3
                parts = (self.config.wd.genre, self.config.wd.artist,
                         self.config.wd.album)
            # append a crumb for each part
            for i, key, part in zip(range(nkeys), keys, parts):
                if part is None:
                    continue
                partdata = dict(list(zip(keys, parts))[:i + 1])
                target = SongRecord(**partdata)
                pb, icon = None, None
                if key == 'album':
                    # Album artwork, with self.alumbpb as a backup:
                    cache_data = SongRecord(artist=self.config.wd.artist,
                                            album=self.config.wd.album,
                                            path=self.config.wd.path)
                    pb = self.artwork.get_library_artwork_cached_pb(cache_data,
                                                                    None)
                    if pb is None:
                        icon = 'album'
                elif key == 'artist':
                    icon = 'artist'
                else:
                    icon = Gtk.STOCK_ORIENTATION_PORTRAIT
                crumbs.append((part, icon, pb, target))

        if not len(crumbs):
            self.crumb_section.set_active(True)
            context = self.crumb_section.get_style_context()
            context.add_class('last_crumb')
        else:
            self.crumb_section.set_active(False)
            context = self.crumb_section.get_style_context()
            context.remove_class('last_crumb')

        self.crumb_section_handler = self.crumb_section.connect('toggled',
            self.library_browse, SongRecord(path='/'))

        # add a button for each crumb
        for crumb in crumbs:
            text, icon, pb, target = crumb
            text = misc.escape_html(text)
            label = Gtk.Label(text, use_markup=True)

            if icon:
                image = Gtk.Image.new_from_stock(icon, Gtk.IconSize.MENU)
            elif pb:
                pb = pb.scale_simple(16, 16, GdkPixbuf.InterpType.HYPER)
                image = Gtk.Image.new_from_pixbuf(pb)

            b = breadcrumbs.CrumbButton(image, label)

            if crumb is crumbs[-1]:
                # FIXME makes the button request minimal space:
                b.set_active(True)
                context = b.get_style_context()
                context.add_class('last_crumb')

            b.set_tooltip_text(label.get_label())
            b.connect('toggled', self.library_browse, target)
            self.breadcrumbs.pack_start(b, False, False, 0)
            b.show_all()

    def library_populate_filesystem_data(self, path):
        # List all dirs/files at path
        bd = []
        if path == '/' and self.lib_view_filesystem_cache is not None:
            # Use cache if possible...
            bd = self.lib_view_filesystem_cache
        else:
            for item in self.mpd.lsinfo(path):
                if 'directory' in item:
                    name = os.path.basename(item['directory'])
                    data = SongRecord(path=item["directory"])
                    bd += [('d' + str(name).lower(), [self.openpb, data,
                                                      misc.escape_html(name)])]
                elif 'file' in item:
                    data = SongRecord(path=item['file'])
                    bd += [('f' + item['file'].lower(),
                            [self.sonatapb, data,
                             formatting.parse(self.config.libraryformat, item,
                                              True)])]
            bd.sort(key=operator.itemgetter(0))
        return bd

    def library_get_toplevel_cache(self, genreview=False, artistview=False,
                                   albumview=False):
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
                key = SongRecord(path=info[1].path, artist=info[1].artist,
                                 album=info[1].album)
                pb2 = self.artwork.get_library_artwork_cached_pb(key, None)
                if pb2 is not None:
                    info[0] = pb2
        return bd

    def library_populate_toplevel_data(self, genreview=False, artistview=False,
                                       albumview=False):
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
                    data = SongRecord(genre=item)
                else:
                    playtime, num_songs = self.library_return_count(
                        artist=item)
                    data = SongRecord(artist=item)
                if num_songs > 0:
                    display = misc.escape_html(item)
                    display += self.add_display_info(num_songs, playtime)
                    bd += [(misc.lower_no_the(item), [pb, data, display])]
        elif albumview:
            albums = []
            untagged_found = False
            for item in self.mpd.listallinfo('/'):
                if 'file' in item and 'album' in item:
                    album = item['album']
                    artist = item.get('artist', self.NOTAG)
                    year = item.get('date', self.NOTAG)
                    path = self.get_multicd_album_root_dir(
                        os.path.dirname(item['file']))
                    data = SongRecord(album=album, artist=artist,
                                      year=year, path=path)
                    albums.append(data)
                    if album == self.NOTAG:
                        untagged_found = True
            if not untagged_found:
                albums.append(SongRecord(album=self.NOTAG))
            albums = misc.remove_list_duplicates(albums, case=False)
            albums = list_mark_various_artists_albums(albums)
            for item in albums:
                album, artist, _genre, year, path = item
                playtime, num_songs = self.library_return_count(artist=artist,
                                                                album=album,
                                                                year=year)
                if num_songs > 0:
                    data = SongRecord(artist=artist, album=album,
                                           year=year, path=path)
                    display = misc.escape_html(album)
                    if artist and year and len(artist) > 0 and len(year) > 0 \
                       and artist != self.NOTAG and year != self.NOTAG:
                        display += " <span weight='light'>(%s, %s)</span>" \
                                % (misc.escape_html(artist),
                                   misc.escape_html(year))
                    elif artist and len(artist) > 0 and artist != self.NOTAG:
                        display += " <span weight='light'>(%s)</span>" \
                                % misc.escape_html(artist)
                    elif year and len(year) > 0 and year != self.NOTAG:
                        display += " <span weight='light'>(%s)</span>" \
                                % misc.escape_html(year)
                    display += self.add_display_info(num_songs, playtime)
                    bd += [(misc.lower_no_the(album), [self.albumpb, data,
                                                       display])]
        bd.sort(key=lambda key: locale.strxfrm(key[0]))
        if genreview:
            self.lib_view_genre_cache = bd
        elif artistview:
            self.lib_view_artist_cache = bd
        elif albumview:
            self.lib_view_album_cache = bd
        return bd


    def library_populate_data(self, genre=None, artist=None, album=None,
                              year=None):
        # Create treeview model info
        bd = []
        if genre is not None and artist is None and album is None:
            # Artists within a genre
            artists = self.library_return_list_items('artist', genre=genre)
            if len(artists) > 0:
                if not self.NOTAG in artists:
                    artists.append(self.NOTAG)
                for artist in artists:
                    playtime, num_songs = self.library_return_count(
                        genre=genre, artist=artist)
                    if num_songs > 0:
                        display = misc.escape_html(artist)
                        display += self.add_display_info(num_songs, playtime)
                        data = SongRecord(genre=genre, artist=artist)
                        bd += [(misc.lower_no_the(artist),
                                [self.artistpb, data, display])]
        elif artist is not None and album is None:
            # Albums/songs within an artist and possibly genre
            # Albums first:
            if genre is not None:
                albums = self.library_return_list_items('album', genre=genre,
                                                        artist=artist)
            else:
                albums = self.library_return_list_items('album', artist=artist)
            for album in albums:
                if genre is not None:
                    years = self.library_return_list_items('date', genre=genre,
                                                           artist=artist,
                                                           album=album)
                else:
                    years = self.library_return_list_items('date',
                                                           artist=artist,
                                                           album=album)
                if not self.NOTAG in years:
                    years.append(self.NOTAG)
                for year in years:
                    if genre is not None:
                        playtime, num_songs = self.library_return_count(
                            genre=genre, artist=artist, album=album, year=year)
                        if num_songs > 0:
                            files = self.library_return_list_items(
                                'file', genre=genre, artist=artist,
                                album=album, year=year)
                            path = os.path.dirname(files[0])
                            data = SongRecord(genre=genre, artist=artist,
                                              album=album, year=year, path=path)
                    else:
                        playtime, num_songs = self.library_return_count(
                            artist=artist, album=album, year=year)
                        if num_songs > 0:
                            files = self.library_return_list_items(
                                'file', artist=artist, album=album, year=year)
                            path = os.path.dirname(files[0])
                        cache_data = SongRecord(artist=artist, album=album,
                                                path=path)
                        data = SongRecord(artist=artist, album=album,
                                          year=year, path=path)
                    if num_songs > 0:
                        cache_data = SongRecord(artist=artist, album=album, path=path)
                        display = misc.escape_html(album)
                        if year and len(year) > 0 and year != self.NOTAG:
                            display += " <span weight='light'>(%s)</span>" \
                                    % misc.escape_html(year)
                        display += self.add_display_info(num_songs, playtime)
                        ordered_year = year
                        if ordered_year == self.NOTAG:
                            ordered_year = '9999'
                        pb = self.artwork.get_library_artwork_cached_pb(
                            cache_data, self.albumpb)
                        bd += [(ordered_year + misc.lower_no_the(album),
                                [pb, data, display])]
            # Now, songs not in albums:
            bd += self.library_populate_data_songs(genre, artist, self.NOTAG,
                                                   None)
        else:
            # Songs within an album, artist, year, and possibly genre
            bd += self.library_populate_data_songs(genre, artist, album, year)
        bd.sort(key=lambda key: locale.strxfrm(key[0]))
        return bd

    def library_populate_data_songs(self, genre, artist, album, year):
        bd = []
        if genre is not None:
            songs, _playtime, _num_songs = \
            self.library_return_search_items(genre=genre, artist=artist,
                                             album=album, year=year)
        else:
            songs, _playtime, _num_songs = self.library_return_search_items(
                artist=artist, album=album, year=year)
        for song in songs:
            data = SongRecord(path=song.file)
            track = str(song.get('track', 99)).zfill(2)
            disc = str(song.get('disc', 99)).zfill(2)
            try:
                bd += [('f' + disc + track + misc.lower_no_the(song.title),
                        [self.sonatapb, data, formatting.parse(
                            self.config.libraryformat, song, True)])]
            except:
                bd += [('f' + disc + track + song.file.lower(),
                        [self.sonatapb, data,
                         formatting.parse(self.config.libraryformat, song,
                                          True)])]
        return bd

    def library_return_list_items(self, itemtype, genre=None, artist=None,
                                  album=None, year=None, ignore_case=True):
        # Returns all items of tag 'itemtype', in alphabetical order,
        # using mpd's 'list'. If searchtype is passed, use
        # a case insensitive search, via additional 'list'
        # queries, since using a single 'list' call will be
        # case sensitive.
        results = []
        searches = self.library_compose_list_count_searchlist(genre, artist,
                                                              album, year)
        if len(searches) > 0:
            for s in searches:
                # If we have untagged tags (''), use search instead
                # of list because list will not return anything.
                if '' in s:
                    items = []
                    songs, playtime, num_songs = \
                            self.library_return_search_items(genre, artist,
                                                             album, year)
                    for song in songs:
                        items.append(song.get(itemtype))
                else:
                    items = self.mpd.list(itemtype, *s)
                for item in items:
                    if len(item) > 0:
                        results.append(item)
        else:
            if genre is None and artist is None and album is None and year \
               is None:
                for item in self.mpd.list(itemtype):
                    if len(item) > 0:
                        results.append(item)
        if ignore_case:
            results = misc.remove_list_duplicates(results, case=False)
        results.sort(key=locale.strxfrm)
        return results

    def library_return_count(self, genre=None, artist=None, album=None,
                             year=None):
        # Because mpd's 'count' is case sensitive, we have to
        # determine all equivalent items (case insensitive) and
        # call 'count' for each of them. Using 'list' + 'count'
        # involves much less data to be transferred back and
        # forth than to use 'search' and count manually.
        searches = self.library_compose_list_count_searchlist(genre, artist,
                                                              album, year)
        playtime = 0
        num_songs = 0
        for s in searches:
            count = self.mpd.count(*s)
            playtime += count.playtime
            num_songs += count.songs

        return (playtime, num_songs)

    def library_compose_list_count_searchlist_single(self, search, typename,
                                                     cached_list, searchlist):
        s = []
        skip_type = (typename == 'artist' and search == VARIOUS_ARTISTS)
        if search is not None and not skip_type:
            if search == self.NOTAG:
                itemlist = [search, '']
            else:
                itemlist = []
                if cached_list is None:
                    cached_list = self.library_return_list_items(typename,
                                                             ignore_case=False)
                    # This allows us to match untagged items
                    cached_list.append('')
                for item in cached_list:
                    if str(item).lower() == str(search).lower():
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

    def library_compose_list_count_searchlist(self, genre=None, artist=None,
                                              album=None, year=None):
        s = []
        s, self.lib_list_genres = \
                self.library_compose_list_count_searchlist_single(
                    genre, 'genre', self.lib_list_genres, s)
        if s is None:
            return []
        s, self.lib_list_artists = \
                self.library_compose_list_count_searchlist_single(
                    artist, 'artist', self.lib_list_artists, s)
        if s is None:
            return []
        s, self.lib_list_albums = \
                self.library_compose_list_count_searchlist_single(
                    album, 'album', self.lib_list_albums, s)
        if s is None:
            return []
        s, self.lib_list_years = \
                self.library_compose_list_count_searchlist_single(
                    year, 'date', self.lib_list_years, s)
        if s is None:
            return []
        return s

    def library_compose_search_searchlist_single(self, search, typename,
                                                 searchlist):
        s = []
        skip_type = (typename == 'artist' and search == VARIOUS_ARTISTS)
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

    def library_compose_search_searchlist(self, genre=None, artist=None,
                                          album=None, year=None):
        s = []
        s = self.library_compose_search_searchlist_single(genre, 'genre', s)
        s = self.library_compose_search_searchlist_single(album, 'album', s)
        s = self.library_compose_search_searchlist_single(artist, 'artist', s)
        s = self.library_compose_search_searchlist_single(year, 'date', s)
        return s

    def library_return_search_items(self, genre=None, artist=None, album=None,
                                    year=None):
        # Returns all mpd items, using mpd's 'search', along with
        # playtime and num_songs.
        searches = self.library_compose_search_searchlist(genre, artist, album,
                                                          year)
        for s in searches:
            args_tuple = tuple(map(str, s))
            playtime = 0
            num_songs = 0
            results = []
            strip_type = None

            if len(args_tuple) == 0:
                return None, 0, 0

            items = self.mpd.search(*args_tuple)
            if items is not None:
                for item in items:
                    if strip_type is None or (strip_type is not None and not \
                                              strip_type in item.keys()):
                        match = True
                        pos = 0
                        # Ensure that if, e.g., "foo" is searched,
                        # "foobar" isn't returned too
                        for arg in args_tuple[::2]:
                            if arg in item and \
                               str(item.get(arg, '')).upper() != \
                               str(args_tuple[pos + 1]).upper():
                                match = False
                                break
                            pos += 2
                        if match:
                            results.append(item)
                            num_songs += 1
                            playtime += item.time
        return (results, int(playtime), num_songs)

    def add_display_info(self, num_songs, playtime):
        seconds = int(playtime)
        hours   = seconds // 3600
        seconds -= 3600 * hours
        minutes = seconds // 60
        seconds -= 60 * minutes
        songs_text = ngettext('{count} song', '{count} songs',
                              num_songs).format(count=num_songs)
        seconds_text = ngettext('{count} second', '{count} seconds',
                                seconds).format(count=seconds)
        minutes_text = ngettext('{count} minute', '{count} minutes',
                                minutes).format(count=minutes)
        hours_text = ngettext('{count} hour', '{count} hours',
                              hours).format(count=hours)
        time_parts = [songs_text]
        if hours > 0:
            time_parts.extend([hours_text, minutes_text])
        elif minutes > 0:
            time_parts.extend([minutes_text, seconds_text])
        else:
            time_parts.extend([seconds_text])
        display_markup = "\n<small><span weight='light'>{}</span></small>"
        display_text = ', '.join(time_parts)
        return display_markup.format(display_text)

    def library_retain_selection(self, prev_selection, prev_selection_root,
                                 prev_selection_parent):
        # Unselect everything:
        if len(self.librarydata) > 0:
            first = Gtk.TreePath.new_first()
            to = Gtk.TreePath.new()
            to.append_index(len(self.librarydata) - 1)
            self.library_selection.unselect_range(first, to)
        # Now attempt to retain the selection from before the update:
        for value in prev_selection:
            for row in self.librarydata:
                if value == row[1]:
                    self.library_selection.select_path(row.path)
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
                self.library.scroll_to_point(
                    -1, self.libraryposition[self.config.wd])
            else:
                self.library.scroll_to_point(0, 0)
        except:
            self.library.scroll_to_point(0, 0)

        # Select and focus previously selected item
        if select_items:
            if self.config.wd in self.libraryselectedpath:
                try:
                    if self.libraryselectedpath[self.config.wd]:
                        self.library_selection.select_path(
                            self.libraryselectedpath[self.config.wd])
                        self.library.grab_focus()
                except:
                    pass

    def library_get_data_level(self, data):
        if self.config.lib_view == consts.VIEW_FILESYSTEM:
            # Returns the number of directories down:
            if data.path == '/':
                # Every other path doesn't start with "/", so
                # start the level numbering at -1
                return -1
            else:
                return data.path.count("/")
        else:
            # Returns the number of items stored in data, excluding
            # the path:
            level = 0
            for item in data:
                if item is not None:
                    level += 1
            return level

    def on_library_key_press(self, widget, event):
        if event.keyval == Gdk.keyval_from_name('Return'):
            self.on_library_row_activated(widget, widget.get_cursor()[0])
            return True

    def on_library_query_tooltip(self, widget, x, y, keyboard_mode, tooltip):
        if keyboard_mode or not self.search_visible():
            widget.set_tooltip_text("")
            return False

        bin_x, bin_y = widget.convert_widget_to_bin_window_coords(x, y)

        pathinfo = widget.get_path_at_pos(bin_x, bin_y)
        if not pathinfo:
            widget.set_tooltip_text("")
            # If the user hovers over an empty row and then back to
            # a row with a search result, this will ensure the tooltip
            # shows up again:
            GLib.idle_add(self.library_search_tooltips_enable, widget, x, y,
                          keyboard_mode, None)
            return False
        treepath, _col, _x2, _y2 = pathinfo

        i = self.librarydata.get_iter(treepath.get_indices()[0])
        path = misc.escape_html(self.librarydata.get_value(i, 1).path)
        song = self.librarydata.get_value(i, 2)
        new_tooltip = "<b>%s:</b> %s\n<b>%s:</b> %s" \
                % (_("Song"), song, _("Path"), path)

        if new_tooltip != self.libsearch_last_tooltip:
            self.libsearch_last_tooltip = new_tooltip
            self.library.set_property('has-tooltip', False)
            GLib.idle_add(self.library_search_tooltips_enable, widget, x, y,
                          keyboard_mode, tooltip)
            GLib.idle_add(widget.set_tooltip_markup, new_tooltip)
            return

        self.libsearch_last_tooltip = new_tooltip

        return False #api says we should return True, but this doesn't work?

    def library_search_tooltips_enable(self, widget, x, y, keyboard_mode,
                                       tooltip):
        self.library.set_property('has-tooltip', True)
        if tooltip is not None:
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
        elif value.path == "..":
            self.library_browse_parent(None)
        else:
            self.library_browse(None, value)

    def library_get_parent(self):
        wd = self.config.wd
        if self.config.lib_view == consts.VIEW_ALBUM:
            value = SongRecord(path="/")
        elif self.config.lib_view == consts.VIEW_ARTIST:
            if wd.album is None:
                value = SongRecord(path="/")
            else:
                value = SongRecord(artist = wd.artist)
        elif self.config.lib_view == consts.VIEW_GENRE:
            if wd.album is not None:
                value = SongRecord(genre=wd.genre,
                                   artist=wd.artist)
            elif wd.artist is not None:
                value = SongRecord(genre=wd.genre)
            else:
                value = SongRecord(path="/")
        else:
            newvalue = '/'.join(wd.path.split('/')[:-1]) or '/'
            value = SongRecord(path=newvalue)
        return value

    def library_browse_parent(self, _action):
        if not self.search_visible():
            if self.library.is_focus():
                value = self.library_get_parent()
                self.library_browse(None, value)
                return True

    def not_parent_is_selected(self):
        # Returns True if something is selected and it's not
        # ".." or "/":
        model, rows = self.library_selection.get_selected_rows()
        for path in rows:
            i = model.get_iter(path)
            value = model.get_value(i, 2)
            if value != ".." and value != "/":
                return True
        return False

    def get_path_child_filenames(self, return_root, selected_only=True):
        # If return_root=True, return main directories whenever possible
        # instead of individual songs in order to reduce the number of
        # mpd calls we need to make. We won't want this behavior in some
        # instances, like when we want all end files for editing tags
        items = []
        if selected_only:
            model, rows = self.library_selection.get_selected_rows()
        else:
            model = self.librarydata
            rows = [(i,) for i in range(len(model))]
        for path in rows:
            i = model.get_iter(path)
            pb = model.get_value(i, 0)
            data = model.get_value(i, 1)
            value = model.get_value(i, 2)
            if value != ".." and value != "/":
                if data.path is not None and data.album is None and data.artist is None and \
                   data.year is None and data.genre is None:
                    if pb == self.sonatapb:
                        # File
                        items.append(data.path)
                    else:
                        # Directory
                        if not return_root:
                            items += self.library_get_path_files_recursive(
                                data.path)
                        else:
                            items.append(data.path)
                else:
                    results, _playtime, _num_songs = \
                            self.library_return_search_items(
                                genre=data.genre, artist=data.artist, album=data.album,
                                year=data.year)
                    for item in results:
                        items.append(item.file)
        # Make sure we don't have any EXACT duplicates:
        items = misc.remove_list_duplicates(items, case=True)
        return items

    def library_get_path_files_recursive(self, path):
        results = []
        for item in self.mpd.lsinfo(path):
            if 'directory' in item:
                results = results + self.library_get_path_files_recursive(
                    item['directory'])
            elif 'file' in item:
                results.append(item['file'])
        return results

    def on_library_search_combo_change(self, _combo=None):
        self.config.last_search_num = self.searchcombo.get_active()
        if not self.search_visible():
            return
        self.prevlibtodo = ""
        self.prevlibtodo_base = "__"
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
            # extra thread for background search work,
            # synchronized with a condition and its internal mutex
            self.libfilterbox_cond = threading.Condition()
            self.libfilterbox_cmd_buf = self.searchtext.get_text()
            qsearch_thread = threading.Thread(target=self.libsearchfilter_loop)
            qsearch_thread.daemon = True
            qsearch_thread.start()
        elif self.search_visible():
            ui.hide(self.searchbutton)
            self.searchtext.handler_block(self.libfilter_changed_handler)
            self.searchtext.set_text("")
            self.searchtext.handler_unblock(self.libfilter_changed_handler)
            self.libsearchfilter_stop_loop()
            # call library_browse from the main thread to avoid corruption
            # of treeview, fixes #1959
            GLib.idle_add(self.library_browse, None, self.config.wd)
            if move_focus:
                self.library.grab_focus()

    def libsearchfilter_feed_loop(self, editable):
        if not self.search_visible():
            self.libsearchfilter_toggle(None)
        # Lets only trigger the searchfilter_loop if 200ms pass
        # without a change in Gtk.Entry
        try:
            GLib.source_remove(self.libfilterbox_source)
        except:
            pass
        self.libfilterbox_source = GLib.timeout_add(
            300, self.libsearchfilter_start_loop, editable)

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
                    GLib.idle_add(ui.reset_entry_marking, self.searchtext)
                    return
                elif len(todo) > 1:
                    GLib.idle_add(self.libsearchfilter_do_search, searchby,
                                  todo)
                elif len(todo) == 0:
                    GLib.idle_add(ui.reset_entry_marking, self.searchtext)
                    self.libsearchfilter_toggle(False)
                else:
                    GLib.idle_add(ui.reset_entry_marking, self.searchtext)
            self.libfilterbox_cond.acquire()
            self.libfilterbox_cmd_buf = '$$$DONE###'
            try:
                self.libfilterbox_cond.release()
            except Exception as e:
                # XXX add logger here in the future!
                raise e
            self.prevlibtodo = todo

    def libsearchfilter_do_search(self, searchby, todo):
        if not self.prevlibtodo_base in todo:
            # Do library search based on first two letters:
            self.prevlibtodo_base = todo[:2]
            self.prevlibtodo_base_results = self.mpd.search(searchby,
                                                             self.prevlibtodo_base)
            subsearch = False
        else:
            subsearch = True

        # Now, use filtering similar to playlist filtering:
        # this make take some seconds... and we'll escape the search text
        # because we'll be searching for a match in items that are also escaped
        #
        # Note that the searching is not order specific. That is, "foo bar"
        # will match on "fools bar" and "barstool foo".

        todos = todo.split(" ")
        regexps = []
        for i in range(len(todos)):
            todos[i] = misc.escape_html(todos[i])
            todos[i] = re.escape(todos[i])
            todos[i] = '.*' + todos[i].lower()
            regexps.append(re.compile(todos[i]))
        matches = []
        if searchby != 'any':
            for row in self.prevlibtodo_base_results:
                is_match = True
                for regexp in regexps:
                    if not regexp.match(row.get(searchby, '').lower()):
                        is_match = False
                        break
                if is_match:
                    matches.append(row)
        else:
            for row in self.prevlibtodo_base_results:
                allstr = " ".join(row.values())
                is_match = True
                for regexp in regexps:
                    if not regexp.match(str(allstr).lower()):
                        is_match = False
                        break
                if is_match:
                    matches.append(row)
        if subsearch and len(matches) == len(self.librarydata):
            # nothing changed..
            return
        self.library.freeze_child_notify()
        currlen = len(self.librarydata)
        bd = [(self.sonatapb,
               SongRecord(path=item['file']),
               formatting.parse(self.config.libraryformat, item, True))
              for item in matches if 'file' in item]
        bd.sort(key=lambda key: locale.strxfrm(key[2]))
        for i, item in enumerate(bd):
            if i < currlen:
                j = self.librarydata.get_iter((i, ))
                for index in range(len(item)):
                    if item[index] != self.librarydata.get_value(j, index):
                        self.librarydata.set_value(j, index, item[index])
            else:
                self.librarydata.append(item)
        # Remove excess items...
        newlen = len(bd)
        if newlen == 0:
            self.librarydata.clear()
        else:
            for i in range(currlen - newlen):
                j = self.librarydata.get_iter((currlen - 1 - i,))
                self.librarydata.remove(j)
        self.library.thaw_child_notify()
        if len(matches) == 0:
            GLib.idle_add(ui.set_entry_invalid, self.searchtext)
        else:
            GLib.idle_add(self.library.set_cursor, Gtk.TreePath.new_first(),
                          None, False)
            GLib.idle_add(ui.reset_entry_marking, self.searchtext)

    def libsearchfilter_key_pressed(self, widget, event):
        self.filter_key_pressed(widget, event, self.library)

    def libsearchfilter_on_enter(self, _entry):
        self.on_library_row_activated(None, None)

    def libsearchfilter_set_focus(self):
        GLib.idle_add(self.searchtext.grab_focus)

    def libsearchfilter_get_style(self):
        return self.searchtext.get_style()
