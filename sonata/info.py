
import sys, os, locale

import gtk

import ui, misc
import mpdhelper as mpdh
from consts import consts
from pluginsystem import pluginsystem

class Info(object):
    def __init__(self, config, info_image, linkcolor, on_link_click_cb, get_playing_song, TAB_INFO, on_image_activate, on_image_motion_cb, on_image_drop_cb, album_return_artist_and_tracks, new_tab):
        self.config = config
        self.linkcolor = linkcolor
        self.on_link_click_cb = on_link_click_cb
        self.get_playing_song = get_playing_song
        self.album_return_artist_and_tracks = album_return_artist_and_tracks

        try:
            self.enc = locale.getpreferredencoding()
        except:
            print "Locale cannot be found; please set your system's locale. Aborting..."
            sys.exit(1)

        self.last_bitrate = None

        self.info_boxes_in_more = None
        self._editlabel = None
        self._editlyricslabel = None
        self.info_labels = None
        self.info_left_label = None
        self.info_lyrics = None
        self._morelabel = None
        self._searchlabel = None
        self.info_tagbox = None
        self.info_type = None

        self.lyricsText = None
        self.albumText = None

        self.info_area = ui.scrollwindow(shadow=gtk.SHADOW_NONE)
        self.tab = new_tab(self.info_area, gtk.STOCK_JUSTIFY_FILL, TAB_INFO, self.info_area)

        image_width = -1 if self.config.info_art_enlarged else 152
        imagebox = ui.eventbox(w=image_width, add=info_image)
        imagebox.drag_dest_set(gtk.DEST_DEFAULT_HIGHLIGHT |
                gtk.DEST_DEFAULT_DROP,
                [("text/uri-list", 0, 80),
                 ("text/plain", 0, 80)], gtk.gdk.ACTION_DEFAULT)
        imagebox.connect('button_press_event', on_image_activate)
        imagebox.connect('drag_motion', on_image_motion_cb)
        imagebox.connect('drag_data_received', on_image_drop_cb)
        self._imagebox = imagebox

        self.widgets_initialize(self.info_area)

    def widgets_initialize(self, info_scrollwindow):

        vert_spacing = 1
        horiz_spacing = 2
        margin = 5
        outter_hbox = gtk.HBox()
        outter_vbox = gtk.VBox()

        # Song info
        info_song = ui.expander(markup="<b>%s</b>" % _("Song Info"),
                expand=self.config.info_song_expanded,
                can_focus=False)
        info_song.connect("activate", self._expanded, "song")
        inner_hbox = gtk.HBox()

        inner_hbox.pack_start(self._imagebox, False, False, horiz_spacing)

        self.info_tagbox = gtk.VBox()

        labels_left = []
        self.info_type = {}
        self.info_labels = []
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

        for i,(text, name, link, tooltip, in_more) in enumerate(labels):
            self.info_type[name] = i
            tmphbox = gtk.HBox()
            if in_more:
                self.info_boxes_in_more += [tmphbox]
            tmplabel = ui.label(markup="<b>%s:</b>" % text, y=0)
            if i == 0:
                self.info_left_label = tmplabel
            # Using set_selectable overrides the hover cursor that
            # sonata tries to set for the links, and I can't figure
            # out how to stop that. So we'll disable set_selectable
            # for those labels until it's figured out.
            tmplabel2 = ui.label(wrap=True, y=0, select=not link)
            if link:
                tmpevbox = ui.eventbox(add=tmplabel2)
                self._apply_link_signals(tmpevbox, name, tooltip)
            tmphbox.pack_start(tmplabel, False, False, horiz_spacing)
            to_pack = tmpevbox if link else tmplabel2
            tmphbox.pack_start(to_pack, False, False, horiz_spacing)
            self.info_labels += [tmplabel2]
            labels_left += [tmplabel]
            self.info_tagbox.pack_start(tmphbox, False, False, vert_spacing)
        ui.set_widths_equal(labels_left)

        mischbox = gtk.HBox()
        self._morelabel = ui.label(y=0)
        moreevbox = ui.eventbox(add=self._morelabel)
        self._apply_link_signals(moreevbox, 'more', _("Toggle extra tags"))
        self._editlabel = ui.label(y=0)
        editevbox = ui.eventbox(add=self._editlabel)
        self._apply_link_signals(editevbox, 'edit', _("Edit song tags"))
        mischbox.pack_start(moreevbox, False, False, horiz_spacing)
        mischbox.pack_start(editevbox, False, False, horiz_spacing)

        self.info_tagbox.pack_start(mischbox, False, False, vert_spacing)
        inner_hbox.pack_start(self.info_tagbox, False, False, horiz_spacing)
        info_song.add(inner_hbox)
        outter_vbox.pack_start(info_song, False, False, margin)

        # Lyrics
        self.info_lyrics = ui.expander(markup="<b>%s</b>" % _("Lyrics"),
                    expand=self.config.info_lyrics_expanded,
                    can_focus=False)
        self.info_lyrics.connect("activate", self._expanded, "lyrics")
        lyricsbox = gtk.VBox()
        lyricsbox_top = gtk.HBox()
        self.lyricsText = ui.label(markup=" ", y=0, select=True, wrap=True)
        lyricsbox_top.pack_start(self.lyricsText, True, True, horiz_spacing)
        lyricsbox.pack_start(lyricsbox_top, True, True, vert_spacing)
        lyricsbox_bottom = gtk.HBox()
        self._searchlabel = ui.label(y=0)
        self._editlyricslabel = ui.label(y=0)
        searchevbox = ui.eventbox(add=self._searchlabel)
        editlyricsevbox = ui.eventbox(add=self._editlyricslabel)
        self._apply_link_signals(searchevbox, 'search', _("Search Lyricwiki.org for lyrics"))
        self._apply_link_signals(editlyricsevbox, 'editlyrics', _("Edit lyrics at Lyricwiki.org"))
        lyricsbox_bottom.pack_start(searchevbox, False, False, horiz_spacing)
        lyricsbox_bottom.pack_start(editlyricsevbox, False, False, horiz_spacing)
        lyricsbox.pack_start(lyricsbox_bottom, False, False, vert_spacing)
        self.info_lyrics.add(lyricsbox)
        outter_vbox.pack_start(self.info_lyrics, False, False, margin)

        # Album info
        info_album = ui.expander(markup="<b>%s</b>" % _("Album Info"),
                expand=self.config.info_album_expanded,
                can_focus=False)
        info_album.connect("activate", self._expanded, "album")
        albumbox = gtk.VBox()
        albumbox_top = gtk.HBox()
        self.albumText = ui.label(markup=" ", y=0, select=True, wrap=True)
        albumbox_top.pack_start(self.albumText, False, False, horiz_spacing)
        albumbox.pack_start(albumbox_top, False, False, vert_spacing)
        info_album.add(albumbox)
        outter_vbox.pack_start(info_album, False, False, margin)

        # Finish..
        if not self.config.show_lyrics:
            ui.hide(self.info_lyrics)
        if not self.config.show_covers:
            ui.hide(self._imagebox)
        # self.config.info_song_more will be overridden on on_link_click, so
        # store it in a temporary var..
        temp = self.config.info_song_more
        self.on_link_click(moreevbox, None, 'more')
        self.config.info_song_more = temp
        if self.config.info_song_more:
            self.on_link_click(moreevbox, None, 'more')
        outter_hbox.pack_start(outter_vbox, False, False, margin)
        info_scrollwindow.add_with_viewport(outter_hbox)

    def get_widgets(self):
        return self.info_area

    def get_info_imagebox(self):
        return self._imagebox

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
            ui.change_cursor(gtk.gdk.Cursor(gtk.gdk.HAND2))

    def on_link_leave(self, _widget, _event):
        ui.change_cursor(None)

    def on_link_click(self, _widget, _event, linktype):
        if linktype == 'more':
            previous_is_more = (self._morelabel.get_text() == "(%s)" % _("more"))
            if previous_is_more:
                self._morelabel.set_markup(misc.link_markup(_("hide"), True, True, self.linkcolor))
                self.config.info_song_more = True
            else:
                self._morelabel.set_markup(misc.link_markup(_("more"), True, True, self.linkcolor))
                self.config.info_song_more = False
            if self.config.info_song_more:
                for hbox in self.info_boxes_in_more:
                    ui.show(hbox)
            else:
                for hbox in self.info_boxes_in_more:
                    ui.hide(hbox)
        else:
            self.on_link_click_cb(linktype)

    def _expanded(self, expander, infotype):
        setattr(self.config, "info_%s_expanded" % infotype,
                not expander.get_expanded())

    def update(self, playing_or_paused, newbitrate, songinfo, update_all):
        # update_all = True means that every tag should update. This is
        # only the case on song and status changes. Otherwise we only
        # want to update the minimum number of widgets so the user can
        # do things like select label text.
        if not playing_or_paused:
            for label in self.info_labels:
                label.set_text("")
            self._editlabel.set_text("")
            if self.config.show_lyrics:
                self._searchlabel.set_text("")
                self._editlyricslabel.set_text("")
                self._show_lyrics(None, None)
            self.albumText.set_text("")
            self.last_bitrate = ""
            return

        bitratelabel = self.info_labels[self.info_type['bitrate']]
        if self.last_bitrate != newbitrate:
            bitratelabel.set_text(newbitrate)
            self.last_bitrate = newbitrate

        if not update_all:
            return

        artistlabel = self.info_labels[self.info_type['artist']]
        tracklabel = self.info_labels[self.info_type['track']]
        albumlabel = self.info_labels[self.info_type['album']]
        filelabel = self.info_labels[self.info_type['file']]

        for name in ['title', 'date', 'genre']:
            label = self.info_labels[self.info_type[name]]
            label.set_text(mpdh.get(songinfo, name))

        tracklabel.set_text(mpdh.get(songinfo, 'track', '', False))
        artistlabel.set_markup(misc.link_markup(misc.escape_html(
            mpdh.get(songinfo, 'artist')), False, False,
            self.linkcolor))
        albumlabel.set_markup(misc.link_markup(misc.escape_html(
            mpdh.get(songinfo, 'album')), False, False,
            self.linkcolor))

        path = misc.file_from_utf8(os.path.join(self.config.musicdir[self.config.profile_num], mpdh.get(songinfo, 'file')))
        if os.path.exists(path):
            filelabel.set_text(os.path.join(self.config.musicdir[self.config.profile_num], mpdh.get(songinfo, 'file')))
            self._editlabel.set_markup(misc.link_markup(_("edit tags"), True, True, self.linkcolor))
        else:
            filelabel.set_text(mpdh.get(songinfo, 'file'))
            self._editlabel.set_text("")

        albuminfo = _("Album name not set.")
        if 'album' in songinfo:
            # Update album info:
            album = mpdh.get(songinfo, 'album')
            year = mpdh.get(songinfo, 'date', None)
            artist, tracks = self.album_return_artist_and_tracks()

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

            playtime = misc.convert_time(playtime)
            albuminfo = "\n".join(i for i in (album, artist, year,
                              playtime) if i)
            albuminfo += "\n\n"
            albuminfo += "\n".join(t for t in tracklist)
            if len(albuminfo) == 0:
                albuminfo = _("Album info not found.")
        self.albumText.set_text(albuminfo)
        # Update lyrics:
        if self.config.show_lyrics:
            if 'artist' in songinfo and 'title' in songinfo:
                self.get_lyrics_start(mpdh.get(songinfo, 'artist'), mpdh.get(songinfo, 'title'), mpdh.get(songinfo, 'artist'), mpdh.get(songinfo, 'title'), os.path.dirname(mpdh.get(songinfo, 'file')))
            else:
                self._show_lyrics(None, None, error=_("Artist or song title not set."))

    def _check_for_local_lyrics(self, artist, title, song_dir):
        locations = [consts.LYRICS_LOCATION_HOME,
                consts.LYRICS_LOCATION_PATH,
                consts.LYRICS_LOCATION_HOME_ALT,
                consts.LYRICS_LOCATION_PATH_ALT]
        for location in locations:
            filename = self.target_lyrics_filename(artist, title,
                                song_dir, location)
            if os.path.exists(filename):
                return filename

    def get_lyrics_start(self, search_artist, search_title, filename_artist, filename_title, song_dir):
        filename_artist = misc.strip_all_slashes(filename_artist)
        filename_title = misc.strip_all_slashes(filename_title)
        filename = self._check_for_local_lyrics(filename_artist, filename_title, song_dir)
        if filename:
            # If the lyrics only contain "not found", delete the file and try to
            # fetch new lyrics. If there is a bug in Sonata/SZI/LyricWiki that
            # prevents lyrics from being found, storing the "not found" will
            # prevent a future release from correctly fetching the lyrics.
            f = open(filename, 'r')
            lyrics = f.read()
            f.close()
            if lyrics == _("Lyrics not found"):
                misc.remove_file(filename)
                filename = self._check_for_local_lyrics(filename_artist, filename_title, song_dir)
        if filename:
            # Re-use lyrics from file:
            f = open(filename, 'r')
            lyrics = f.read()
            f.close()
            # Strip artist - title line from file if it exists, since we
            # now have that information visible elsewhere.
            header = "%s - %s\n\n" % (filename_artist, filename_title)
            if lyrics[:len(header)] == header:
                lyrics = lyrics[len(header):]
            self._show_lyrics(filename_artist, filename_title, lyrics=lyrics)
        else:
            # Fetch lyrics from lyricwiki.org etc.
            lyrics_fetchers = pluginsystem.get('lyrics_fetching')
            callback = lambda *args: self.get_lyrics_response(
                filename_artist, filename_title, song_dir, *args)
            if lyrics_fetchers:
                msg = _("Fetching lyrics...")
                for _plugin, cb in lyrics_fetchers:
                    cb(callback, search_artist, search_title)
            else:
                msg = _("No lyrics plug-in enabled.")
            self._show_lyrics(filename_artist, filename_title,
                          lyrics=msg)

    def get_lyrics_response(self, artist_then, title_then, song_dir,
                lyrics=None, error=None):
        if lyrics and not error:
            filename = self.target_lyrics_filename(artist_then, title_then, song_dir)
            # Save lyrics to file:
            misc.create_dir('~/.lyrics/')
            f = open(filename, 'w')
            lyrics = misc.unescape_html(lyrics)
            try:
                f.write(lyrics.decode(self.enc).encode('utf8'))
            except:
                f.write(lyrics)
            f.close()

        self._show_lyrics(artist_then, title_then, lyrics, error)

    def _show_lyrics(self, artist_then, title_then, lyrics=None, error=None):
        # For error messages where there is no appropriate info:
        if not artist_then or not title_then:
            self._searchlabel.set_markup("")
            self._editlyricslabel.set_markup("")
            if error:
                self.lyricsText.set_markup(error)
            elif lyrics:
                self.lyricsText.set_markup(lyrics)
            else:
                self.lyricsText.set_markup("")
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
                self.lyricsText.set_markup(error)
            elif lyrics:
                try:
                    self.lyricsText.set_markup(misc.escape_html(lyrics))
                except: ### XXX why would this happen?
                    self.lyricsText.set_text(lyrics)
            else:
                self.lyricsText.set_markup("")

    def resize_elements(self, notebook_allocation):
        # Resize labels in info tab to prevent horiz scrollbar:
        if self.config.show_covers:
            labelwidth = notebook_allocation.width - self.info_left_label.allocation.width - self._imagebox.allocation.width - 60 # 60 accounts for vert scrollbar, box paddings, etc..
        else:
            labelwidth = notebook_allocation.width - self.info_left_label.allocation.width - 60 # 60 accounts for vert scrollbar, box paddings, etc..
        if labelwidth > 100:
            for label in self.info_labels:
                label.set_size_request(labelwidth, -1)
        # Resize lyrics/album gtk labels:
        labelwidth = notebook_allocation.width - 45 # 45 accounts for vert scrollbar, box paddings, etc..
        self.lyricsText.set_size_request(labelwidth, -1)
        self.albumText.set_size_request(labelwidth, -1)

    def target_lyrics_filename(self, artist, title, song_dir, force_location=None):
        # FIXME Why did we have this condition here: if self.conn:
        lyrics_loc = force_location if force_location else self.config.lyrics_location
        # Note: *_ALT searching is for compatibility with other mpd clients (like ncmpcpp):
        file_map = {
            consts.LYRICS_LOCATION_HOME : ("~/.lyrics", "%s-%s.txt"),
            consts.LYRICS_LOCATION_PATH : (self.config.musicdir[self.config.profile_num], song_dir, "%s-%s.txt"),
            consts.LYRICS_LOCATION_HOME_ALT : ("~/.lyrics", "%s - %s.txt"),
            consts.LYRICS_LOCATION_PATH_ALT : (self.config.musicdir[self.config.profile_num], song_dir, "%s - %s.txt"),
               }
        return misc.file_from_utf8(misc.file_exists_insensitive(
                    os.path.expanduser(
                    os.path.join(*file_map[lyrics_loc]))
                         % (artist, title)))
