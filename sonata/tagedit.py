
import os
_ = _ # install the gettext built-in from the main app as a global here, silences pylint

import gtk, gobject
tagpy = None # module loaded when needed

import ui, misc


class TagEditor():
    def __init__(self, window, tags_mpd_update):
        self.window = window
        self.tags_mpd_update = tags_mpd_update

        self.tagpy_is_91 = None
        self.edit_style_orig = None

        self.tagnum = -1
        self.updating_edit_entries = False

    def on_tags_edit(self, files, temp_mpdpaths, music_dir):
        # Try loading module
        global tagpy
        if tagpy is None:
            try:
                import tagpy
                # Set default tag encoding to utf8.. fixes some reported bugs.
                import tagpy.id3v2 as id3v2
                id3v2.FrameFactory.instance().setDefaultTextEncoding(tagpy.StringType.UTF8)
            except:
                pass
        if tagpy is None:
            ui.show_msg(self.window, _("Taglib and/or tagpy not found, tag editing support disabled."), _("Edit Tags"), 'editTagsError', gtk.BUTTONS_CLOSE, response_cb=ui.dialog_destroy)
            return
        if not os.path.isdir(misc.file_from_utf8(music_dir)):
            ui.show_msg(self.window, _("The path") + " " + music_dir + " " + _("does not exist. Please specify a valid music directory in preferences."), _("Edit Tags"), 'editTagsError', gtk.BUTTONS_CLOSE, response_cb=ui.dialog_destroy)
            return
        ui.change_cursor(gtk.gdk.Cursor(gtk.gdk.WATCH))

        while gtk.events_pending():
            gtk.main_iteration()

                # XXX file list was created here

        if len(files) == 0:
            ui.change_cursor(None)
            return

        # Initialize tags:
        tags = []
        for filenum in range(len(files)):
            tags.append({'title':'', 'artist':'', 'album':'', 'year':'',
                     'track':'', 'genre':'', 'comment':'', 'title-changed':False,
                     'artist-changed':False, 'album-changed':False, 'year-changed':False,
                     'track-changed':False, 'genre-changed':False, 'comment-changed':False,
                     'fullpath':misc.file_from_utf8(files[filenum]),
                     'mpdpath':temp_mpdpaths[filenum]})

        if not os.path.exists(tags[0]['fullpath']):
            ui.change_cursor(None)
            ui.show_msg(self.window, _("File ") + "\"" + tags[0]['fullpath'] + "\"" + _(" not found. Please specify a valid music directory in preferences."), _("Edit Tags"), 'editTagsError', gtk.BUTTONS_CLOSE, response_cb=ui.dialog_destroy)
            return
        if not self.tags_next_tag(tags):
            ui.change_cursor(None)
            ui.show_msg(self.window, _("No music files with editable tags found."), _("Edit Tags"), 'editTagsError', gtk.BUTTONS_CLOSE, response_cb=ui.dialog_destroy)
            return
        editwindow = ui.dialog(parent=self.window, flags=gtk.DIALOG_MODAL, role='editTags', resizable=False, separator=False)
        editwindow.set_size_request(375, -1)
        table = gtk.Table(9, 2, False)
        table.set_row_spacings(2)
        filelabel = ui.label(select=True, wrap=True)
        filehbox = gtk.HBox()
        sonataicon = ui.image(stock='sonata', stocksize=gtk.ICON_SIZE_DND, x=1)
        blanklabel = ui.label(w=15, h=12)
        filehbox.pack_start(sonataicon, False, False, 2)
        filehbox.pack_start(filelabel, True, True, 2)
        filehbox.pack_start(blanklabel, False, False, 2)
        titlelabel = ui.label(text=_("Title") + ":", x=1)
        titleentry = ui.entry()
        titlebutton = ui.button()
        titlebuttonvbox = gtk.VBox()
        self.tags_win_create_apply_all_button(titlebutton, titlebuttonvbox, titleentry)
        titlehbox = gtk.HBox()
        titlehbox.pack_start(titlelabel, False, False, 2)
        titlehbox.pack_start(titleentry, True, True, 2)
        titlehbox.pack_start(titlebuttonvbox, False, False, 2)
        artistlabel = ui.label(text=_("Artist") + ":", x=1)
        artistentry = ui.entry()
        artisthbox = gtk.HBox()
        artistbutton = ui.button()
        artistbuttonvbox = gtk.VBox()
        self.tags_win_create_apply_all_button(artistbutton, artistbuttonvbox, artistentry)
        artisthbox.pack_start(artistlabel, False, False, 2)
        artisthbox.pack_start(artistentry, True, True, 2)
        artisthbox.pack_start(artistbuttonvbox, False, False, 2)
        albumlabel = ui.label(text=_("Album") + ":", x=1)
        albumentry = ui.entry()
        albumhbox = gtk.HBox()
        albumbutton = ui.button()
        albumbuttonvbox = gtk.VBox()
        self.tags_win_create_apply_all_button(albumbutton, albumbuttonvbox, albumentry)
        albumhbox.pack_start(albumlabel, False, False, 2)
        albumhbox.pack_start(albumentry, True, True, 2)
        albumhbox.pack_start(albumbuttonvbox, False, False, 2)
        yearlabel = ui.label(text="  " + _("Year") + ":", x=1)
        yearentry = ui.entry(w=50)
        handlerid = yearentry.connect("insert_text", self.tags_win_entry_constraint, True)
        yearentry.set_data('handlerid', handlerid)
        tracklabel = ui.label(text="  " + _("Track") + ":", x=1)
        trackentry = ui.entry(w=50)
        handlerid2 = trackentry.connect("insert_text", self.tags_win_entry_constraint, False)
        trackentry.set_data('handlerid2', handlerid2)
        yearbutton = ui.button()
        yearbuttonvbox = gtk.VBox()
        self.tags_win_create_apply_all_button(yearbutton, yearbuttonvbox, yearentry)
        trackbutton = ui.button()
        trackbuttonvbox = gtk.VBox()
        self.tags_win_create_apply_all_button(trackbutton, trackbuttonvbox, trackentry, True)
        yearandtrackhbox = gtk.HBox()
        yearandtrackhbox.pack_start(yearlabel, False, False, 2)
        yearandtrackhbox.pack_start(yearentry, True, True, 2)
        yearandtrackhbox.pack_start(yearbuttonvbox, False, False, 2)
        yearandtrackhbox.pack_start(tracklabel, False, False, 2)
        yearandtrackhbox.pack_start(trackentry, True, True, 2)
        yearandtrackhbox.pack_start(trackbuttonvbox, False, False, 2)
        genrelabel = ui.label(text=_("Genre") + ":", x=1)
        genrecombo = ui.comboentry(list=self.tags_win_genres(), wrap=2)
        genreentry = genrecombo.get_child()
        genrehbox = gtk.HBox()
        genrebutton = ui.button()
        genrebuttonvbox = gtk.VBox()
        self.tags_win_create_apply_all_button(genrebutton, genrebuttonvbox, genreentry)
        genrehbox.pack_start(genrelabel, False, False, 2)
        genrehbox.pack_start(genrecombo, True, True, 2)
        genrehbox.pack_start(genrebuttonvbox, False, False, 2)
        commentlabel = ui.label(text=_("Comment") + ":", x=1)
        commententry = ui.entry()
        commenthbox = gtk.HBox()
        commentbutton = ui.button()
        commentbuttonvbox = gtk.VBox()
        self.tags_win_create_apply_all_button(commentbutton, commentbuttonvbox, commententry)
        commenthbox.pack_start(commentlabel, False, False, 2)
        commenthbox.pack_start(commententry, True, True, 2)
        commenthbox.pack_start(commentbuttonvbox, False, False, 2)
        ui.set_widths_equal([titlelabel, artistlabel, albumlabel, yearlabel, genrelabel, commentlabel, sonataicon])
        genrecombo.set_size_request(-1, titleentry.size_request()[1])
        tablewidgets = [ui.label(), filehbox, ui.label(), titlehbox, artisthbox, albumhbox, yearandtrackhbox, genrehbox, commenthbox, ui.label()]
        for i in range(len(tablewidgets)):
            table.attach(tablewidgets[i], 1, 2, i+1, i+2, gtk.FILL|gtk.EXPAND, gtk.FILL|gtk.EXPAND, 2, 0)
        editwindow.vbox.pack_start(table)
        saveall_button = None
        if len(files) > 1:
            # Only show save all button if more than one song being edited.
            saveall_button = ui.button(text=_("Save _All"))
            editwindow.action_area.pack_start(saveall_button)
        cancelbutton = editwindow.add_button(gtk.STOCK_CANCEL, gtk.RESPONSE_REJECT)
        savebutton = editwindow.add_button(gtk.STOCK_SAVE, gtk.RESPONSE_ACCEPT)
        editwindow.connect('delete_event', self.tags_win_hide, tags)
        entries = [titleentry, artistentry, albumentry, yearentry, trackentry, genreentry, commententry, filelabel]
        buttons = [titlebutton, artistbutton, albumbutton, yearbutton, trackbutton, genrebutton, commentbutton]
        entries_names = ["title", "artist", "album", "year", "track", "genre", "comment"]
        editwindow.connect('response', self.tags_win_response, tags, entries, entries_names)
        if saveall_button:
            saveall_button.connect('clicked', self.tags_win_save_all, editwindow, tags, entries, entries_names)
        for i in range(len(entries)-1):
            entries[i].connect('changed', self.tags_win_entry_changed)
        for i in range(len(buttons)):
            buttons[i].connect('clicked', self.tags_win_apply_all, entries_names[i], tags, entries)
        self.tags_win_update(editwindow, tags, entries, entries_names)
        ui.change_cursor(None)
        entries[7].set_size_request(editwindow.size_request()[0] - titlelabel.size_request()[0] - 50, -1)
        editwindow.show_all()
        # Need to get the entry style after the window has been shown
        self.edit_style_orig = titleentry.get_style()

    def tags_next_tag(self, tags):
        # Returns true if next tag found (and self.tagnum is updated).
        # If no next tag found, returns False.
        while self.tagnum < len(tags)-1:
            self.tagnum = self.tagnum + 1
            if os.path.exists(tags[self.tagnum]['fullpath']):
                try:
                    fileref = tagpy.FileRef(tags[self.tagnum]['fullpath'])
                    if not fileref.isNull():
                        return True
                except:
                    pass
        return False

    def tags_win_entry_changed(self, editable, force_red=False):
        if force_red or not self.updating_edit_entries:
            style = editable.get_style().copy()
            style.text[gtk.STATE_NORMAL] = editable.get_colormap().alloc_color("red")
            editable.set_style(style)

    def tags_win_entry_revert_color(self, editable):
        editable.set_style(self.edit_style_orig)

    def tags_win_create_apply_all_button(self, button, vbox, entry, autotrack=False):
        button.set_size_request(12, 12)
        if autotrack:
            button.set_tooltip_text(_("Increment each selected music file, starting at track 1 for this file."))
        else:
            button.set_tooltip_text(_("Apply to all selected music files."))
        padding = int((entry.size_request()[1] - button.size_request()[1])/2)+1
        vbox.pack_start(button, False, False, padding)

    def tags_win_apply_all(self, button, item, tags, entries):
        tagnum = 0
        for tag in tags:
            tagnum = tagnum + 1
            if item == "title":
                tag['title'] = entries[0].get_text()
                tag['title-changed'] = True
            elif item == "album":
                tag['album'] = entries[2].get_text()
                tag['album-changed'] = True
            elif item == "artist":
                tag['artist'] = entries[1].get_text()
                tag['artist-changed'] = True
            elif item == "year":
                if len(entries[3].get_text()) > 0:
                    tag['year'] = int(entries[3].get_text())
                else:
                    tag['year'] = 0
                tag['year-changed'] = True
            elif item == "track":
                if tagnum >= self.tagnum-1:
                    # Start the current song at track 1, as opposed to the first
                    # song in the list.
                    tag['track'] = tagnum - self.tagnum
                tag['track-changed'] = True
            elif item == "genre":
                tag['genre'] = entries[5].get_text()
                tag['genre-changed'] = True
            elif item == "comment":
                tag['comment'] = entries[6].get_text()
                tag['comment-changed'] = True
        if item == "track":
            # Update the entry for the current song:
            entries[4].set_text(str(tags[self.tagnum]['track']))

    def tags_win_update(self, window, tags, entries, entries_names):
        self.updating_edit_entries = True
        # Populate tags(). Note that we only retrieve info from the
        # file if the info hasn't already been changed:
        fileref = tagpy.FileRef(tags[self.tagnum]['fullpath'])
        if not tags[self.tagnum]['title-changed']:
            tags[self.tagnum]['title'] = fileref.tag().title
        if not tags[self.tagnum]['artist-changed']:
            tags[self.tagnum]['artist'] = fileref.tag().artist
        if not tags[self.tagnum]['album-changed']:
            tags[self.tagnum]['album'] = fileref.tag().album
        if not tags[self.tagnum]['year-changed']:
            tags[self.tagnum]['year'] = fileref.tag().year
        if not tags[self.tagnum]['track-changed']:
            tags[self.tagnum]['track'] = fileref.tag().track
        if not tags[self.tagnum]['genre-changed']:
            tags[self.tagnum]['genre'] = fileref.tag().genre
        if not tags[self.tagnum]['comment-changed']:
            tags[self.tagnum]['comment'] = fileref.tag().comment
        # Update interface:
        entries[0].set_text(self.tags_get_tag(tags[self.tagnum], 'title'))
        entries[1].set_text(self.tags_get_tag(tags[self.tagnum], 'artist'))
        entries[2].set_text(self.tags_get_tag(tags[self.tagnum], 'album'))
        if self.tags_get_tag(tags[self.tagnum], 'year') != 0:
            entries[3].set_text(str(self.tags_get_tag(tags[self.tagnum], 'year')))
        else:
            entries[3].set_text('')
        if self.tags_get_tag(tags[self.tagnum], 'track') != 0:
            entries[4].set_text(str(self.tags_get_tag(tags[self.tagnum], 'track')))
        else:
            entries[4].set_text('')
        entries[5].set_text(self.tags_get_tag(tags[self.tagnum], 'genre'))
        entries[6].set_text(self.tags_get_tag(tags[self.tagnum], 'comment'))
        filename = gobject.filename_display_name(tags[self.tagnum]['mpdpath'].split('/')[-1])
        entries[7].set_text(filename)
        entries[0].select_region(0, len(entries[0].get_text()))
        entries[0].grab_focus()
        window.set_title(_("Edit Tags") + " - " + str(self.tagnum+1) + " " + _("of") + " " + str(len(tags)))
        self.updating_edit_entries = False
        # Update text colors as appropriate:
        for i in range(len(entries)-1):
            if tags[self.tagnum][entries_names[i] + '-changed']:
                self.tags_win_entry_changed(entries[i])
            else:
                self.tags_win_entry_revert_color(entries[i])
        self.tags_win_set_sensitive(window.action_area)

    def tags_win_set_sensitive(self, action_area):
        # Hacky workaround to allow the user to click the save button again when the
        # mouse stays over the button (see http://bugzilla.gnome.org/show_bug.cgi?id=56070)
        action_area.set_sensitive(True)
        action_area.hide()
        action_area.show_all()

    def tags_get_tag(self, tag, field):
        # Since tagpy went through an API change from 0.90.1 to 0.91, we'll
        # implement both methods of retrieving the tag:
        if self.tagpy_is_91 is None:
            try:
                test = tag[field]()
                self.tagpy_is_91 = False
            except:
                self.tagpy_is_91 = True
        if not self.tagpy_is_91:
            try:
                return tag[field]().strip()
            except:
                return tag[field]()
        else:
            try:
                return tag[field].strip()
            except:
                return tag[field]

    def tags_set_tag(self, tag, field, value):
        # Since tagpy went through an API change from 0.90.1 to 0.91, we'll
        # implement both methods of setting the tag:
        try:
            value = value.strip()
        except:
            pass
        if field=='artist':
            if not self.tagpy_is_91:
                tag.setArtist(value)
            else:
                tag.artist = value
        elif field=='title':
            if not self.tagpy_is_91:
                tag.setTitle(value)
            else:
                tag.title = value
        elif field=='album':
            if not self.tagpy_is_91:
                tag.setAlbum(value)
            else:
                tag.album = value
        elif field=='year':
            if not self.tagpy_is_91:
                tag.setYear(int(value))
            else:
                tag.year = int(value)
        elif field=='track':
            if not self.tagpy_is_91:
                tag.setTrack(int(value))
            else:
                tag.track = int(value)
        elif field=='genre':
            if not self.tagpy_is_91:
                tag.setGenre(value)
            else:
                tag.genre = value
        elif field=='comment':
            if not self.tagpy_is_91:
                tag.setComment(value)
            else:
                tag.comment = value

    def tags_win_save_all(self, button, window, tags, entries, entries_names):
        for entry in entries:
            try: # Skip GtkLabels
                entry.set_property('editable', False)
            except:
                pass
        while window.get_property('visible'):
            self.tags_win_response(window, gtk.RESPONSE_ACCEPT, tags, entries, entries_names)

    def tags_win_response(self, window, response, tags, entries, entries_names):
        if response == gtk.RESPONSE_REJECT:
            self.tags_win_hide(window, None, tags)
        elif response == gtk.RESPONSE_ACCEPT:
            window.action_area.set_sensitive(False)
            while window.action_area.get_property("sensitive") or gtk.events_pending():
                gtk.main_iteration()
            filetag = tagpy.FileRef(tags[self.tagnum]['fullpath'])
            self.tags_set_tag(filetag.tag(), 'title', entries[0].get_text())
            self.tags_set_tag(filetag.tag(), 'artist', entries[1].get_text())
            self.tags_set_tag(filetag.tag(), 'album', entries[2].get_text())
            if len(entries[3].get_text()) > 0:
                self.tags_set_tag(filetag.tag(), 'year', entries[3].get_text())
            else:
                self.tags_set_tag(filetag.tag(), 'year', 0)
            if len(entries[4].get_text()) > 0:
                self.tags_set_tag(filetag.tag(), 'track', entries[4].get_text())
            else:
                self.tags_set_tag(filetag.tag(), 'track', 0)
            self.tags_set_tag(filetag.tag(), 'genre', entries[5].get_text())
            self.tags_set_tag(filetag.tag(), 'comment', entries[6].get_text())
            save_success = filetag.save()
            if not (save_success): # FIXME: was (save_success and self.conn and self.status):
                ui.show_msg(self.window, _("Unable to save tag to music file."), _("Edit Tags"), 'editTagsError', gtk.BUTTONS_CLOSE, response_cb=ui.dialog_destroy)
            if self.tags_next_tag(tags):
                # Next file:
                self.tags_win_update(window, tags, entries, entries_names)
            else:
                # No more (valid) files:
                self.tagnum = self.tagnum + 1 # To ensure we update the last file in tags_mpd_update
                self.tags_win_hide(window, None, tags)

    def tags_win_hide(self, window, data=None, tags=None):
        gobject.idle_add(self.tags_mpd_update, tags, self.tagnum)
        window.destroy()

    def tags_win_genres(self):
        return ["", "A Cappella", "Acid", "Acid Jazz", "Acid Punk", "Acoustic",
                "Alt. Rock", "Alternative", "Ambient", "Anime", "Avantgarde", "Ballad",
                "Bass", "Beat", "Bebob", "Big Band", "Black Metal", "Bluegrass",
                "Blues", "Booty Bass", "BritPop", "Cabaret", "Celtic", "Chamber music",
                "Chanson", "Chorus", "Christian Gangsta Rap", "Christian Rap",
                "Christian Rock", "Classic Rock", "Classical", "Club", "Club-House",
                "Comedy", "Contemporary Christian", "Country", "Crossover", "Cult",
                "Dance", "Dance Hall", "Darkwave", "Death Metal", "Disco", "Dream",
                "Drum &amp; Bass", "Drum Solo", "Duet", "Easy Listening", "Electronic",
                "Ethnic", "Euro-House", "Euro-Techno", "Eurodance", "Fast Fusion",
                "Folk", "Folk-Rock", "Folklore", "Freestyle", "Funk", "Fusion", "Game",
                "Gangsta", "Goa", "Gospel", "Gothic", "Gothic Rock", "Grunge",
                "Hard Rock", "Hardcore", "Heavy Metal", "Hip-Hop", "House", "Humour",
                "Indie", "Industrial", "Instrumental", "Instrumental pop",
                "Instrumental rock", "JPop", "Jazz", "Jazz+Funk", "Jungle", "Latin",
                "Lo-Fi", "Meditative", "Merengue", "Metal", "Musical", "National Folk",
                "Native American", "Negerpunk", "New Age", "New Wave", "Noise",
                "Oldies", "Opera", "Other", "Polka", "Polsk Punk", "Pop", "Pop-Folk",
                "Pop/Funk", "Porn Groove", "Power Ballad", "Pranks", "Primus",
                "Progressive Rock", "Psychedelic", "Psychedelic Rock", "Punk",
                "Punk Rock", "R&amp;B", "Rap", "Rave", "Reggae", "Retro", "Revival",
                "Rhythmic soul", "Rock", "Rock &amp; Roll", "Salsa", "Samba", "Satire",
                "Showtunes", "Ska", "Slow Jam", "Slow Rock", "Sonata", "Soul",
                "Sound Clip", "Soundtrack", "Southern Rock", "Space", "Speech",
                "Swing", "Symphonic Rock", "Symphony", "Synthpop", "Tango", "Techno",
                "Techno-Industrial", "Terror", "Thrash Metal", "Top 40", "Trailer"]

    def tags_win_entry_constraint(self, entry, new_text, new_text_length, position, isyearlabel):
        lst_old_string = list(entry.get_chars(0, -1))
        _pos = entry.get_position()
        lst_new_string = lst_old_string.insert(_pos, new_text)
        _string = "".join(lst_old_string)
        if isyearlabel:
            _hid = entry.get_data('handlerid')
        else:
            _hid = entry.get_data('handlerid2')
        entry.handler_block(_hid)
        try:
            _val = float(_string)
            if (isyearlabel and _val <= 9999) or not isyearlabel:
                _pos = entry.insert_text(new_text, _pos)
        except StandardError, e:
            pass
        entry.handler_unblock(_hid)
        gobject.idle_add(lambda t: t.set_position(t.get_position()+1), entry)
        entry.stop_emission("insert-text")
        pass
