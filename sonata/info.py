# Copyright 2006-2009 Scott Horowitz <stonecrest@gmail.com>
# Copyright 2009-2014 Jonathan Ballet <jon@multani.info>
#
# This file is part of Sonata.
#
# Sonata is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# Sonata is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with Sonata.  If not, see <http://www.gnu.org/licenses/>.

import sys
import os
import locale
import logging
import threading

from gi.repository import Gtk, Pango, Gdk, GdkPixbuf, GLib

from sonata import ui, misc, consts, mpdhelper as mpdh, img
from sonata.pluginsystem import pluginsystem


def target_lyrics_filename(cfg, artist, title, song_dir, force_location=None):
    """Get the filename of the lyrics of a song"""

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

        self.pixbuf = None # Unscaled pixbuf for on_viewport_resize

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

    def on_viewport_resize(self, _widget, _event):
        self.set_lyrics_allocation()
        self.set_song_info_allocation()
        self.on_artwork_changed(None, self.pixbuf)

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

        path = os.path.join(self.config.current_musicdir, songinfo.file)
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
            filename = target_lyrics_filename(self.config, artist, title,
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
            def communicate(artist_then, title_then, lyrics=None, error=None):
                """Schedule actions from the plugin thread into the main
                thread"""
                GLib.idle_add(self._show_lyrics, artist_then, title_then,
                              lyrics, error)

            # Fetch lyrics from plugins.
            thread = threading.Thread(
                name="LyricsFetcher",
                target=FetchLyricsWorker,
                args=(self.config, communicate,
                      search_artist, search_title, song_dir))
            thread.start()

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

    def set_lyrics_allocation(self):
        notebook_width = self.info_area.get_allocation().width

        lyrics_requisition = self.lyrics_text.get_preferred_size()[1]
        lyrics_width = lyrics_requisition.width
        lyrics_height = lyrics_requisition.height

        if lyrics_width > 0.5 * notebook_width + 20:
            lyrics_width = 0.5 * notebook_width + 20
        self.lyrics_scrolledwindow.set_size_request(lyrics_width, lyrics_height)
        self.lyrics_scrolledwindow.set_min_content_width(lyrics_width)

    def set_song_info_allocation(self):
        names = ('title', 'artist', 'album', 'date',
                 'track', 'genre', 'bitrate')
        max_width = 0
        for name in names:
            text = len(self.info_labels[name].get_text())
            max_width = max(max_width, text)
        self.info_labels['file'].set_max_width_chars(2 * max_width)

    def _calculate_artwork_size(self):
        if self._imagebox.get_size_request()[0] == -1:
            notebook_allocation = self.info_area.get_allocation()
            notebook_width = notebook_allocation.width
            notebook_height = notebook_allocation.height

            lyrics_width = self.info_lyrics.get_allocation().width

            grid = self.info_song_grid
            grid_allocation = grid.get_allocation()
            grid_height = grid_allocation.height
            grid_width = grid.get_preferred_width_for_height(grid_height)[1]

            image_max_width = notebook_width - lyrics_width - grid_width - 20
            image_max_height = notebook_height - 40

            box_max_width = max(min(0.5 * notebook_width, image_max_width), 150)
            box_max_height = max(image_max_height, 150)

            return min(box_max_height, box_max_width)
        else:
            return 150

    def on_artwork_changed(self, artwork_obj, pixbuf):
        if pixbuf is not None:
            self.pixbuf = pixbuf
            image_width = pixbuf.get_width()
            image_height = pixbuf.get_height()
            box_size = self._calculate_artwork_size()
            width = min(min(image_height,image_width), box_size)

            (pix2, w, h) = img.get_pixbuf_of_size(pixbuf, width)
            pix2 = img.do_style_cover(self.config, pix2, w, h)
            pix2 = img.pixbuf_add_border(pix2)

            self.image.set_from_pixbuf(pix2)
            del pix2
            del pixbuf

    def on_artwork_reset(self, artwork_obj):
        self.pixbuf = None
        self.image.set_from_icon_set(ui.icon('sonata-cd-large'), -1)


class FetchLyricsWorker:
    """Thread worker to fetch lyrics for a song

    This must use the `communicate` method to commuicate with the main thread to
    update the GUI.
    """

    def __init__(self, config, communicate, search_artist, search_title, song_dir):
        self.config = config
        self.communicate = communicate
        self.logger = logging.getLogger(__name__)

        self.fetch_lyrics(search_artist, search_title, song_dir)

    def fetch_lyrics(self, search_artist, search_title, song_dir):
        # Homogenize search patterns, so plugins don't have to do it.
        search_artist = str(search_artist).title()
        search_title = str(search_title).title()

        lyrics_fetchers = pluginsystem.get('lyrics_fetching')
        if lyrics_fetchers:
            self.logger.info("Looking for lyrics for %r - %r...",
                             search_artist, search_title)
            self.communicate(search_artist, search_title,
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

        self.communicate(search_artist, search_title, lyrics=msg)

    def get_lyrics_response(self, artist_then, title_then, song_dir,
                lyrics=None, error=None):
        if lyrics and not error:
            filename = target_lyrics_filename(self.config, artist_then,
                                              title_then, song_dir)
            # Save lyrics to file:
            misc.create_dir('~/.lyrics/')
            self.logger.info("Saving lyrics to: %s", filename)
            try:
                with open(filename, 'w', encoding="utf-8") as f:
                    lyrics = misc.unescape_html(lyrics)
                    f.write(lyrics)
            except IOError as e:
                self.logger.warning("Can't save lyrics to %s: %s", filename, e)

        self.communicate(artist_then, title_then, lyrics, error)
