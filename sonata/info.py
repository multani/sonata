from __future__ import with_statement

import sys
import os
import locale
import logging

from gi.repository import Gtk, Pango, Gdk, GdkPixbuf, GObject

from sonata import ui, misc, consts, mpdhelper as mpdh
from sonata.pluginsystem import pluginsystem


class Info(object):

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

        try:
            self.enc = locale.getpreferredencoding()
        except:
            self.logger.exception("Locale cannot be found; please set your "
                                  "system's locale. Aborting...")
            sys.exit(1)

        self.last_bitrate = None

        self.info_boxes_in_more = None
        self._editlabel = None
        self._editlyricslabel = None
        self.info_left_label = None
        self.info_lyrics = None
        self._morelabel = None
        self._searchlabel = None

        self.lyrics_text = None
        self.album_text = None

        # Info tab
        self.builder = ui.builder('info.ui')
        self.info_area = self.builder.get_object('info_page_scrolledwindow')
        self.tab_label_widget = self.builder.get_object('info_tab_eventbox')
        tab_label = self.builder.get_object('info_tab_label')
        tab_label.set_text(TAB_INFO)
        self.tab = add_tab(self.info_area, self.tab_label_widget,
                           TAB_INFO, self.info_area)

        self._imagebox = self.builder.get_object('info_page_song_eventbox')
        self.image = self.builder.get_object('info_page_song_image')

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
        self.info_boxes_in_more = []
        labels = [(_("Title"), 'title', False, "", False),
            (_("Artist"), 'artist', True,
                _("Launch artist in Wikipedia"), False),
            (_("Album"), 'album', True,
                 _("Launch album in Wikipedia"), False),
            (_("Date"), 'date', False, "", False),
            (_("Track"), 'track', False, "", False),
            (_("Genre"), 'genre', False, "", False),
            (_("File"), 'file', False, "", True),
            (_("Bitrate"), 'bitrate', False, "", True)]

        for i, (text, name, link, tooltip, in_more) in enumerate(labels):
            label = ui.label(markup="<b>%s:</b>" % text, y=0)
            self.info_song_grid.attach(label, 0, i, 1, 1)
            if i == 0:
                self.info_left_label = label
            # Using set_selectable overrides the hover cursor that
            # sonata tries to set for the links, and I can't figure
            # out how to stop that. So we'll disable set_selectable
            # for those labels until it's figured out.
            tmplabel2 = ui.label(wrap=True, y=0, select=not link)
            if link:
                tmpevbox = ui.eventbox(add=tmplabel2)
                self._apply_link_signals(tmpevbox, name, tooltip)
            to_pack = tmpevbox if link else tmplabel2
            self.info_song_grid.attach(to_pack, 1, i, 2, 1)
            self.info_labels[name] = tmplabel2
            if in_more:
                self.info_boxes_in_more.append(label)
                self.info_boxes_in_more.append(to_pack)

        self._morelabel = ui.label(y=0)
        self.toggle_more()
        moreevbox = ui.eventbox(add=self._morelabel)
        self._apply_link_signals(moreevbox, 'more', _("Toggle extra tags"))
        self._editlabel = ui.label(y=0)
        editevbox = ui.eventbox(add=self._editlabel)
        self._apply_link_signals(editevbox, 'edit', _("Edit song tags"))
        mischbox = Gtk.HBox()
        mischbox.pack_start(moreevbox, False, False, 3)
        mischbox.pack_start(editevbox, False, False, 3)
        self.info_song_grid.attach(mischbox, 0, len(labels), 3, 1)

    def _widgets_lyrics(self):
        self.info_lyrics = self.builder.get_object('info_page_lyrics_expander')
        self.info_lyrics.set_expanded(self.config.info_lyrics_expanded)
        self.info_lyrics.connect("activate", self._expanded, "lyrics")
        self.lyrics_scrolledwindow = self.builder.get_object(
            'info_page_lyrics_scrolledwindow')
        self.lyrics_text = self.builder.get_object('info_page_lyrics_textview')
        self._populate_lyrics_tag_table()
        self._searchlabel = self.builder.get_object('info_page_lyrics_search')
        self._editlyricslabel = self.builder.get_object('info_page_lyrics_edit')
        search_eventbox = self.builder.get_object(
            'info_page_lyrics_search_eventbox')
        edit_eventbox = self.builder.get_object(
            'info_page_lyrics_edit_eventbox')
        self._apply_link_signals(search_eventbox, 'search',
                                 _("Search Lyricwiki.org for lyrics"))
        self._apply_link_signals(edit_eventbox, 'editlyrics',
                                 _("Edit lyrics at Lyricwiki.org"))

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

    def get_info_image(self):
        return self.image

    def show_lyrics_updated(self):
        func = "show" if self.config.show_lyrics else "hide"
        getattr(ui, func)(self.info_lyrics)

    def _apply_link_signals(self, widget, linktype, tooltip):
        widget.connect("enter-notify-event", self.on_link_enter)
        widget.connect("leave-notify-event", self.on_link_leave)
        widget.connect("button-press-event", self.on_link_click, linktype)
        widget.set_tooltip_text(tooltip)

    def on_link_enter(self, widget, _event):
        if widget.get_children()[0].get_use_markup():
            ui.change_cursor(Gdk.Cursor.new(Gdk.CursorType.HAND2))

    def on_link_leave(self, _widget, _event):
        ui.change_cursor(None)

    def toggle_more(self):
        text = _("hide") if self.config.info_song_more else _("more")
        func = "show" if self.config.info_song_more else "hide"
        func = getattr(ui, func)
        self._morelabel.set_markup(misc.link_markup(text, True, True,
                                self.linkcolor))
        for hbox in self.info_boxes_in_more:
            func(hbox)

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
            label.set_text("")
        self._searchlabel.set_text("")
        self._editlyricslabel.set_text("")
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
            return

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
            label.set_text(mpdh.get(songinfo, name))

        tracklabel.set_text(mpdh.get(songinfo, 'track', '', False))
        artistlabel.set_markup(misc.link_markup(misc.escape_html(
            mpdh.get(songinfo, 'artist')), False, False,
            self.linkcolor))
        albumlabel.set_markup(misc.link_markup(misc.escape_html(
            mpdh.get(songinfo, 'album')), False, False,
            self.linkcolor))

        path = misc.file_from_utf8(os.path.join(
            self.config.musicdir[self.config.profile_num], mpdh.get(songinfo,
                                                                    'file')))
        if os.path.exists(path):
            filelabel.set_text(os.path.join(
                self.config.musicdir[self.config.profile_num],
                mpdh.get(songinfo, 'file')))
            self._editlabel.set_markup(misc.link_markup(_("edit tags"), True,
                                                        True, self.linkcolor))
        else:
            filelabel.set_text(mpdh.get(songinfo, 'file'))
            self._editlabel.set_text("")

    def _update_album(self, songinfo):
        if 'album' not in songinfo:
            self.album_text.get_buffer().set_text(_("Album name not set."))
            return

        artist, tracks = self.album_return_artist_and_tracks()
        albuminfo = _("Album info not found.")

        if tracks:
            tracks.sort(key=lambda x: mpdh.get(x, 'track', 0, True))
            playtime = 0
            tracklist = []
            for t in tracks:
                playtime += mpdh.get(t, 'time', 0, True)
                tracklist.append("%s. %s" %
                        (mpdh.get(t, 'track', '0',
                            False, 2),
                        mpdh.get(t, 'title',
                            os.path.basename(
                                t['file']))))

            album = mpdh.get(songinfo, 'album')
            year = mpdh.get(songinfo, 'date', None)
            playtime = misc.convert_time(playtime)
            albuminfo = "\n".join(i for i in (album, artist, year,
                              playtime) if i)
            albuminfo += "\n\n"
            albuminfo += "\n".join(t for t in tracklist)

        self.album_text.get_buffer().set_text(albuminfo)

    def _update_lyrics(self, songinfo):
        if self.config.show_lyrics:
            if 'artist' in songinfo and 'title' in songinfo:
                self.get_lyrics_start(mpdh.get(songinfo, 'artist'),
                                      mpdh.get(songinfo, 'title'),
                                      mpdh.get(songinfo, 'artist'),
                                      mpdh.get(songinfo, 'title'),
                                      os.path.dirname(mpdh.get(songinfo,
                                                               'file')))
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
                with open(filename, 'r') as f:
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
                with open(filename, 'r') as f:
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
            # Fetch lyrics from plugins
            callback = lambda * args: self.get_lyrics_response(
                filename_artist, filename_title, song_dir, *args)

            lyrics_fetchers = pluginsystem.get('lyrics_fetching')
            if lyrics_fetchers:
                msg = _("Fetching lyrics...")
                pluginsystem.emit('lyrics_fetching',
                                  callback, search_artist, search_title)
            else:
                msg = _("No lyrics plug-in enabled.")

            self._show_lyrics(filename_artist, filename_title,
                          lyrics=msg)

    def get_lyrics_response(self, artist_then, title_then, song_dir,
                lyrics=None, error=None):
        if lyrics and not error:
            filename = self.target_lyrics_filename(artist_then, title_then,
                                                   song_dir)
            # Save lyrics to file:
            misc.create_dir('~/.lyrics/')
            try:
                with open(filename, 'w') as f:
                    lyrics = misc.unescape_html(lyrics)
                    try:
                        f.write(lyrics.decode(self.enc).encode('utf8'))
                    except:
                        f.write(lyrics)
            except IOError:
                pass

        self._show_lyrics(artist_then, title_then, lyrics, error)

    def _show_lyrics(self, artist_then, title_then, lyrics=None, error=None):
        # For error messages where there is no appropriate info:
        if not artist_then or not title_then:
            self._searchlabel.set_text("")
            self._editlyricslabel.set_text("")
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
        artist_now = misc.strip_all_slashes(mpdh.get(songinfo, 'artist', None))
        title_now = misc.strip_all_slashes(mpdh.get(songinfo, 'title', None))
        if artist_now == artist_then and title_now == title_then:
            self._searchlabel.set_markup(misc.link_markup(
                _("search"), True, True, self.linkcolor))
            self._editlyricslabel.set_markup(misc.link_markup(
                _("edit"), True, True, self.linkcolor))
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

        return misc.file_from_utf8(
            misc.file_exists_insensitive(file_path))
