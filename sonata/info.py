import sys
import os
import locale
import logging
import threading

from gi.repository import Gtk, Pango, Gdk, GdkPixbuf

from sonata import ui, misc, consts, mpdhelper as mpdh, img
from sonata.pluginsystem import pluginsystem


class Info:

    def __init__(self, config, linkcolor, on_link_click_cb,
                 get_playing_song, TAB_INFO, on_image_activate,
                 on_image_motion_cb, on_image_drop_cb,
                 album_return_artist_and_tracks, add_tab):
        self.logger = logging.getLogger(__name__)
        self.config = config
        self.linkcolor = linkcolor
        self.on_link_click_cb = on_link_click_cb
        self.get_playing_song = get_playing_song
        self.album_return_artist_and_tracks = album_return_artist_and_tracks

        self.last_bitrate = None

        self.info_boxes_in_more = None
        self._editlabel = None
        self.info_left_label = None
        self.info_lyrics = None
        self._morelabel = None
        self._searchlabel = None

        self.lyrics_text = None
        self.album_text = None

        self.active = False

        # Info tab
        self.builder = ui.builder('info')
        self.css_provider = ui.css_provider('info')
        self.info_area = self.builder.get_object('info_page_scrolledwindow')
        self.tab_label_widget = self.builder.get_object('info_tab_eventbox')
        tab_label = self.builder.get_object('info_tab_label')
        tab_label.set_text(TAB_INFO)
        self.tab = add_tab(self.info_area, self.tab_label_widget,
                           TAB_INFO, self.info_area)

        self._imagebox = self.builder.get_object('info_page_song_eventbox')
        self.image = self.builder.get_object('info_page_song_image')
        self.image.set_from_icon_set(ui.icon('sonata-cd-large'), -1)

        self._imagebox.drag_dest_set(Gtk.DestDefaults.HIGHLIGHT |
                                     Gtk.DestDefaults.DROP,
                                     [Gtk.TargetEntry.new("text/uri-list", 0, 80),
                                      Gtk.TargetEntry.new("text/plain", 0, 80)],
                                      Gdk.DragAction.DEFAULT)
        self._imagebox.connect('button_press_event', on_image_activate)
        self._imagebox.connect('drag_motion', on_image_motion_cb)
        self._imagebox.connect('drag_data_received', on_image_drop_cb)

        self._widgets_initialize()

    def _widgets_initialize(self):
        self._widgets_song()
        self._widgets_lyrics()
        self._widgets_album()

        # Finish..
        if not self.config.show_lyrics:
            ui.hide(self.info_lyrics)
        if not self.config.show_covers:
            ui.hide(self._imagebox)

    def _widgets_song(self):
        self.info_song = self.builder.get_object('info_page_song_expander')
        self.info_song.set_expanded(self.config.info_song_expanded)
        self.info_song_grid = self.builder.get_object('info_page_song_grid')

        self.info_song.connect("activate", self._expanded, "song")

        self.info_labels = {}
        names = ('title', 'artist', 'album', 'date',
                 'track', 'genre', 'file', 'bitrate')
        for name in names:
            self.info_labels[name] = self.builder.get_object(
                'info_song_{}_label'.format(name))
        artist_eventbox = self.builder.get_object('info_song_artist_eventbox')
        album_eventbox = self.builder.get_object('info_song_album_eventbox')
        links = {
            'artist': artist_eventbox,
            'album': album_eventbox,}
        for name, widget in links.items():
            self._apply_link_signals(widget, name)

        file_label = self.builder.get_object('info_song_file_label_label')
        bitrate_label = self.builder.get_object('info_song_bitrate_label_label')
        self.info_boxes_in_more = {
            'values': (self.info_labels['file'], self.info_labels['bitrate'],),
            'labels': (file_label, bitrate_label,),}

        self._morelabel = self.builder.get_object('info_song_links_more_label')
        self.toggle_more()
        moreevbox = self.builder.get_object('info_song_links_more_eventbox')
        self._apply_link_signals(moreevbox, 'more')
        self._editlabel = self.builder.get_object('info_song_links_edit_label')
        editevbox = self.builder.get_object('info_song_links_edit_eventbox')
        self._apply_link_signals(editevbox, 'edit')

    def _widgets_lyrics(self):
        self.info_lyrics = self.builder.get_object('info_page_lyrics_expander')
        self.info_lyrics.set_expanded(self.config.info_lyrics_expanded)
        self.info_lyrics.connect("activate", self._expanded, "lyrics")
        self.lyrics_scrolledwindow = self.builder.get_object(
            'info_page_lyrics_scrolledwindow')
        self.lyrics_text = self.builder.get_object('info_page_lyrics_textview')
        self._populate_lyrics_tag_table()
        self._searchlabel = self.builder.get_object('info_page_lyrics_search')
        search_eventbox = self.builder.get_object(
            'info_page_lyrics_search_eventbox')
        self._apply_link_signals(search_eventbox, 'search')

    def _widgets_album(self):
        self.info_album = self.builder.get_object('info_page_album_expander')
        self.info_album.set_expanded(self.config.info_album_expanded)
        self.album_text = self.builder.get_object('info_page_album_textview')
        self.album_scrolledwindow = self.builder.get_object(
            'info_page_album_scrolledwindow')
        self.info_album.connect("activate", self._expanded, "album")

    def get_widgets(self):
        return self.info_area

    def get_info_imagebox(self):
        return self._imagebox

    def show_lyrics_updated(self):
        func = "show" if self.config.show_lyrics else "hide"
        getattr(ui, func)(self.info_lyrics)

    def _apply_link_signals(self, widget, linktype):
        widget.connect("enter-notify-event", self.on_link_enter)
        widget.connect("leave-notify-event", self.on_link_leave)
        widget.connect("button-press-event", self.on_link_click, linktype)

    def on_link_enter(self, widget, _event):
        ui.change_cursor(Gdk.Cursor.new(Gdk.CursorType.HAND2))

    def on_link_leave(self, _widget, _event):
        ui.change_cursor(None)

    def toggle_more(self):
        if self.config.info_song_more:
            text = _("hide")
            func = "show"
        else:
            text = _("more")
            func = "hide"
        text = "({})".format(text)
        self._morelabel.set_text(text)

        func = getattr(ui, func)
        for widget in self.info_boxes_in_more['labels']:
            func(widget)

        if not self.active and self.config.info_song_more:
            return

        for widget in self.info_boxes_in_more['values']:
            func(widget)

    def on_link_click(self, _widget, _event, linktype):
        if linktype == 'more':
            self.config.info_song_more = not self.config.info_song_more
            self.toggle_more()
        else:
            self.on_link_click_cb(linktype)

    def _expanded(self, expander, infotype):
        setattr(self.config, "info_%s_expanded" % infotype,
                not expander.get_expanded())

    def clear_info(self):
        """Clear the info widgets of any information"""
        for label in self.info_labels.values():
            label.hide()
        self._searchlabel.hide()
        self._show_lyrics(None, None)
        self.album_text.get_buffer().set_text("")
        self.last_bitrate = ""

    def update(self, playing_or_paused, newbitrate, songinfo, update_all):
        # update_all = True means that every tag should update. This is
        # only the case on song and status changes. Otherwise we only
        # want to update the minimum number of widgets so the user can
        # do things like select label text.
        if not playing_or_paused:
            self.clear_info()
            self.active = False
            return

        self.active = True

        for label in self.info_labels.values():
            if self.config.info_song_more or \
               not label in self.info_boxes_in_more['values']:
                label.show()
        bitratelabel = self.info_labels['bitrate']
        if self.last_bitrate != newbitrate:
            bitratelabel.set_text(newbitrate)
            self.last_bitrate = newbitrate

        if update_all:
            for func in ["song", "album", "lyrics"]:
                getattr(self, "_update_%s" % func)(songinfo)

    def _update_song(self, songinfo):
        artistlabel = self.info_labels['artist']
        tracklabel = self.info_labels['track']
        albumlabel = self.info_labels['album']
        filelabel = self.info_labels['file']

        for name in ['title', 'date', 'genre']:
            label = self.info_labels[name]
            label.set_text(songinfo.get(name, ''))

        tracklabel.set_text(str(songinfo.track))
        artistlabel.set_text(misc.escape_html(songinfo.artist))
        albumlabel.set_text(misc.escape_html(songinfo.album))

        path = os.path.join(self.config.musicdir[self.config.profile_num],
                            songinfo.file)
        if os.path.exists(path):
            filelabel.set_text(path)
            self._editlabel.show()
        else:
            filelabel.set_text(songinfo.file)
            self._editlabel.hide()

    def _update_album(self, songinfo):
        if 'album' not in songinfo:
            self.album_text.get_buffer().set_text(_("Album name not set."))
            return

        artist, tracks = self.album_return_artist_and_tracks()
        albuminfo = _("Album info not found.")

        if tracks:
            tracks.sort(key=lambda x: x.track)
            playtime = 0
            tracklist = []
            for t in tracks:
                playtime += t.time
                tracklist.append("%s. %s" % (
                    str(t.track).zfill(2),
                    t.get('title', os.path.basename(t.file))))

            album = songinfo.album
            year = songinfo.date
            playtime = misc.convert_time(playtime)
            albuminfo = "\n".join(i for i in (album, artist, year,
                              playtime) if i)
            albuminfo += "\n\n"
            albuminfo += "\n".join(t for t in tracklist)

        self.album_text.get_buffer().set_text(albuminfo)

    def _update_lyrics(self, songinfo):
        if self.config.show_lyrics:
            if 'artist' in songinfo and 'title' in songinfo:
                self.get_lyrics_start(songinfo.artist, songinfo.title,
                                      songinfo.artist, songinfo.title,
                                      os.path.dirname(songinfo.file))
            else:
                self._show_lyrics(None, None, error=_(('Artist or song title '
                                                       'not set.')))

    def _check_for_local_lyrics(self, artist, title, song_dir):
        locations = [
            consts.LYRICS_LOCATION_HOME,
            consts.LYRICS_LOCATION_PATH,
            consts.LYRICS_LOCATION_HOME_ALT,
            consts.LYRICS_LOCATION_PATH_ALT]
        for location in locations:
            filename = self.target_lyrics_filename(artist, title,
                                song_dir, location)
            if os.path.exists(filename):
                return filename

    def get_lyrics_start(self, search_artist, search_title, filename_artist,
                         filename_title, song_dir, force_fetch=False):
        filename_artist = misc.strip_all_slashes(filename_artist)
        filename_title = misc.strip_all_slashes(filename_title)
        filename = self._check_for_local_lyrics(filename_artist,
                                                filename_title, song_dir)
        lyrics = ""
        if filename:
            # If the lyrics only contain "not found", delete the file and try
            # to fetch new lyrics. If there is a bug in Sonata/SZI/LyricWiki
            # that prevents lyrics from being found, storing the "not found"
            # will prevent a future release from correctly fetching the lyrics.
            try:
                with open(filename, 'r', encoding="utf-8") as f:
                    lyrics = f.read()
            except IOError:
                pass

            if lyrics == _("Lyrics not found"):
                force_fetch = True

        if force_fetch:
            # Remove all lyrics for this song
            while filename is not None:
                filename = self._check_for_local_lyrics(filename_artist,
                                                        filename_title,
                                                        song_dir)
                if filename is not None:
                    misc.remove_file(filename)

        if filename:
            # Re-use lyrics from file:
            try:
                with open(filename, 'r', encoding="utf-8") as f:
                    lyrics = f.read()
            except IOError:
                pass
            # Strip artist - title line from file if it exists, since we
            # now have that information visible elsewhere.
            header = "%s - %s\n\n" % (filename_artist, filename_title)
            if lyrics[:len(header)] == header:
                lyrics = lyrics[len(header):]
            self._show_lyrics(filename_artist, filename_title, lyrics=lyrics)
        else:
            # Fetch lyrics from plugins.
            thread = threading.Thread(target=self.fetch_lyrics_from_plugins,
                                      args=(search_artist, search_title,
                                            song_dir))
            thread.start()

    def fetch_lyrics_from_plugins(self, search_artist, search_title, song_dir):
        # Homogenize search patterns, so plugins don't have to do it.
        search_artist = str(search_artist).title()
        search_title = str(search_title).title()

        lyrics_fetchers = pluginsystem.get('lyrics_fetching')
        if lyrics_fetchers:
            self.logger.info("Looking for lyrics for %r - %r...",
                             search_artist, search_title)
            self._show_lyrics(search_artist, search_title,
                              lyrics=_("Fetching lyrics..."))
            for plugin, get_lyrics in lyrics_fetchers:
                try:
                    lyrics = get_lyrics(search_artist, search_title)
                except Exception as e:
                    if self.logger.isEnabledFor(logging.DEBUG):
                        # Be more verbose if we want something verbose
                        log = self.logger.exception
                    else:
                        log = self.logger.warning

                    log("Plugin %s: unable to fetch lyrics (%s)",
                        plugin.name, e)
                    continue

                if lyrics:
                    self.logger.info("Lyrics for %r - %r fetched by %r plugin.",
                                     search_artist, search_title, plugin.name)
                    self.get_lyrics_response(search_artist, search_title,
                                             song_dir, lyrics=lyrics)
                    return
            msg = _("Lyrics not found.")
        else:
            self.logger.info("Can't look for lyrics, no plugin enabled.")
            msg = _("No lyrics plug-in enabled.")

        self._show_lyrics(search_artist, search_title, lyrics=msg)

    def get_lyrics_response(self, artist_then, title_then, song_dir,
                lyrics=None, error=None):
        if lyrics and not error:
            filename = self.target_lyrics_filename(artist_then, title_then,
                                                   song_dir)
            # Save lyrics to file:
            misc.create_dir('~/.lyrics/')
            try:
                with open(filename, 'w', encoding="utf-8") as f:
                    lyrics = misc.unescape_html(lyrics)
                    f.write(lyrics)
            except IOError:
                pass

        self._show_lyrics(artist_then, title_then, lyrics, error)

    def _show_lyrics(self, artist_then, title_then, lyrics=None, error=None):
        # For error messages where there is no appropriate info:
        if not artist_then or not title_then:
            self._searchlabel.hide()
            if error:
                self.lyrics_text.get_buffer().set_text(error)
            elif lyrics:
                self.lyrics_text.get_buffer().set_text(lyrics)
            else:
                self.lyrics_text.get_buffer().set_text("")
            return

        # Verify that we are displaying the correct lyrics:
        songinfo = self.get_playing_song()
        if not songinfo:
            return
        artist_now = misc.strip_all_slashes(songinfo.artist)
        title_now = misc.strip_all_slashes(songinfo.title)
        if artist_now == artist_then and title_now == title_then:
            self._searchlabel.show()
            if error:
                self.lyrics_text.get_buffer().set_text(error)
            elif lyrics:
                self._set_lyrics(lyrics)
            else:
                self.lyrics_text.get_buffer().set_text("")

    def _set_lyrics(self, lyrics):
        if lyrics is None:
            return

        lyrics_buf = self.lyrics_text.get_buffer()
        lyrics_buf.set_text('')

        # pango needs only ampersand to be escaped
        lyrics = misc.unescape_html(lyrics).replace('&', '&amp;')

        try:
            attr_list, plain_text, accel_marker = Pango.parse_markup(lyrics)
        except:
            # failed to parse, use lyrics as it is
            lyrics_buf.set_text(lyrics)
            return

        attr_iter = attr_list.get_iterator()

        while True:
            range = attr_iter.range()
            font = attr_iter.get_font()[0]
            text = plain_text[range[0]:range[1]]

            tags = []
            if font.get_weight() == Pango.Weight.BOLD:
                tags.append('bold')
            if font.get_style() == Pango.Style.ITALIC:
                tags.append('italic')

            if tags:
                lyrics_buf.insert_with_tags_by_name(lyrics_buf.get_end_iter(),
                                                    text, *tags)
            else:
                lyrics_buf.insert(lyrics_buf.get_end_iter(), text)

            if not attr_iter.next():
                break

    def _populate_lyrics_tag_table(self):
        tag_table = self.lyrics_text.get_buffer().get_tag_table()

        bold_tag = Gtk.TextTag.new('bold')
        bold_tag.set_property('weight', Pango.Weight.BOLD)
        tag_table.add(bold_tag)

        italic_tag = Gtk.TextTag.new('italic')
        italic_tag.set_property('style', Pango.Style.ITALIC)
        tag_table.add(italic_tag)

    def target_lyrics_filename(self, artist, title, song_dir,
                               force_location=None):
        """get the filename of the lyrics of a song"""

        cfg = self.config # alias for easier access

        # FIXME Why did we have this condition here: if self.conn:
        lyrics_loc = force_location if force_location else cfg.lyrics_location

        if song_dir is not None:
            song_dir.replace('%', '%%')

        music_dir = cfg.musicdir[cfg.profile_num].replace('%', '%%')
        pattern1 = "%s-%s.txt"
        pattern2 = "%s - %s.txt"

        # Note: *_ALT searching is for compatibility with other mpd clients
        # (like ncmpcpp):
        file_map = {
            consts.LYRICS_LOCATION_HOME: ("~/.lyrics", pattern1),
            consts.LYRICS_LOCATION_PATH: (music_dir, song_dir, pattern1),
            consts.LYRICS_LOCATION_HOME_ALT: ("~/.lyrics", pattern2),
            consts.LYRICS_LOCATION_PATH_ALT: (music_dir, song_dir, pattern2),
        }

        file_path = os.path.join(*file_map[lyrics_loc])
        file_path = os.path.expanduser(file_path) % (artist, title)

        return misc.file_exists_insensitive(file_path)

    def on_artwork_changed(self, artwork_obj, pixbuf):
        if self._imagebox.get_size_request()[0] == -1:
            notebook_width = self.info_song_grid.get_parent().get_allocation().width
            grid = self.info_song_grid
            grid_allocation = grid.get_allocation()
            grid_height = grid_allocation.height
            grid_width = grid.get_preferred_width_for_height(grid_height)[0]
            fullwidth = notebook_width - (grid_width + 120)
            new_width = max(fullwidth, 150)
        else:
            new_width = 150

        (pix2, w, h) = img.get_pixbuf_of_size(pixbuf, new_width)
        # XXX apply composite cover on top of pix2
        pix2 = img.pixbuf_add_border(pix2)

        self.image.set_from_pixbuf(pix2)
        del pix2
        del pixbuf

    def on_artwork_reset(self, artwork_obj):
        self.image.set_from_icon_set(ui.icon('sonata-cd-large'), -1)
