
"""
This module provides a user interface for editing the metadata tags of
local music files.

Example usage:
import tagedit
tageditor = tagedit.TagEditor(self.window, self.tags_mpd_update)
tageditor.on_tags_edit(files, temp_mpdpaths, self.musicdir[self.profile_num])
"""

import os
import re

import gtk, gobject
tagpy = None # module loaded when needed

import ui, misc


class TagEditor():
    """This class implements a dialog for editing music metadata tags.

    When the dialog closes, the callback gets the list of updates made.
    """
    def __init__(self, window, tags_mpd_update, tags_set_use_mpdpath):
        self.window = window
        self.tags_mpd_update = tags_mpd_update
        self.tags_set_use_mpdpath = tags_set_use_mpdpath

        self.filelabel = None
        self.curr_mpdpath = None
        self.tagnum = None
        self.use_mpdpaths = None

    def _create_label_entry_button_hbox(self, label_name, track=False):
        """Creates a label, entry, apply all button, packing them into an hbox.

        This is usually one row in the tagedit dialog, for example the title.
        """
        entry = ui.entry()
        button = ui.button()
        buttonvbox = self.tags_win_create_apply_all_button(button, entry, track)

        label = ui.label(text=label_name, x=1)
        hbox = gtk.HBox()
        hbox.pack_start(label, False, False, 2)
        hbox.pack_start(entry, True, True, 2)
        hbox.pack_start(buttonvbox, False, False, 2)

        return (label, entry, button, hbox)

    def on_tags_edit(self, files, temp_mpdpaths, music_dir):
        """Display the editing dialog"""
        # Try loading module
        global tagpy
        if tagpy is None:
            try:
                import tagpy
            except ImportError:
                ui.show_msg(self.window, _("Taglib and/or tagpy not found, tag editing support disabled."), _("Edit Tags"), 'editTagsError', gtk.BUTTONS_CLOSE, response_cb=ui.dialog_destroy)
                ui.change_cursor(None)
                return
            # Set default tag encoding to utf8.. fixes some reported bugs.
            import tagpy.id3v2 as id3v2
            id3v2.FrameFactory.instance().setDefaultTextEncoding(tagpy.StringType.UTF8)

        # Make sure tagpy is at least 0.91
        if hasattr(tagpy.Tag.title, '__call__'):
            ui.show_msg(self.window, _("Tagpy version < 0.91. Please upgrade to a newer version, tag editing support disabled."), _("Edit Tags"), 'editTagsError', gtk.BUTTONS_CLOSE, response_cb=ui.dialog_destroy)
            ui.change_cursor(None)
            return

        if not os.path.isdir(misc.file_from_utf8(music_dir)):
            ui.show_msg(self.window, _("The path %s does not exist. Please specify a valid music directory in preferences.") % music_dir, _("Edit Tags"), 'editTagsError', gtk.BUTTONS_CLOSE, response_cb=ui.dialog_destroy)
            ui.change_cursor(None)
            return

                # XXX file list was created here

        if len(files) == 0:
            ui.change_cursor(None)
            return

        # Initialize:
        self.tagnum = -1

        tags = [{'title':'', 'artist':'', 'album':'', 'year':'', 'track':'',
             'genre':'', 'comment':'', 'title-changed':False,
             'artist-changed':False, 'album-changed':False,
             'year-changed':False, 'track-changed':False,
             'genre-changed':False, 'comment-changed':False,
             'fullpath':misc.file_from_utf8(filename),
             'mpdpath':path}
            for filename, path in zip(files, temp_mpdpaths)]

        if not os.path.exists(tags[0]['fullpath']):
            ui.change_cursor(None)
            ui.show_msg(self.window, _("File '%s' not found. Please specify a valid music directory in preferences.") % tags[0]['fullpath'], _("Edit Tags"), 'editTagsError', gtk.BUTTONS_CLOSE, response_cb=ui.dialog_destroy)
            return
        if not self.tags_next_tag(tags):
            ui.change_cursor(None)
            ui.show_msg(self.window, _("No music files with editable tags found."), _("Edit Tags"), 'editTagsError', gtk.BUTTONS_CLOSE, response_cb=ui.dialog_destroy)
            return
        editwindow = ui.dialog(parent=self.window, flags=gtk.DIALOG_MODAL, role='editTags', resizable=False, separator=False)
        editwindow.set_size_request(375, -1)
        table = gtk.Table(9, 2, False)
        table.set_row_spacings(2)
        self.filelabel = ui.label(select=True, wrap=True)
        filehbox = gtk.HBox()
        sonataicon = ui.image(stock='sonata', stocksize=gtk.ICON_SIZE_DND, x=1)
        expandbutton = ui.button(" ")
        self.set_expandbutton_state(expandbutton)
        expandvbox = gtk.VBox()
        expandvbox.pack_start(ui.label(), True, True)
        expandvbox.pack_start(expandbutton, False, False)
        expandvbox.pack_start(ui.label(), True, True)
        expandbutton.connect('clicked', self.toggle_path)
        blanklabel = ui.label(w=5, h=12)
        filehbox.pack_start(sonataicon, False, False, 2)
        filehbox.pack_start(self.filelabel, True, True, 2)
        filehbox.pack_start(expandvbox, False, False, 2)
        filehbox.pack_start(blanklabel, False, False, 2)

        titlelabel, titleentry, titlebutton, titlehbox = self._create_label_entry_button_hbox(_("Title:"))
        artistlabel, artistentry, artistbutton, artisthbox = self._create_label_entry_button_hbox(_("Artist:"))
        albumlabel, albumentry, albumbutton, albumhbox = self._create_label_entry_button_hbox(_("Album:"))
        yearlabel, yearentry, yearbutton, yearhbox = self._create_label_entry_button_hbox(_("Year:"))
        yearentry.set_size_request(50,-1)
        tracklabel, trackentry, trackbutton, trackhbox = self._create_label_entry_button_hbox("  " + _("Track:"), True)
        trackentry.set_size_request(50,-1)
        yearandtrackhbox = gtk.HBox()
        yearandtrackhbox.pack_start(yearhbox, True, True, 0)
        yearandtrackhbox.pack_start(trackhbox, True, True, 0)

        yearentry.connect("insert_text", self.tags_win_entry_constraint, True)
        trackentry.connect("insert_text", self.tags_win_entry_constraint, False)

        genrelabel = ui.label(text=_("Genre:"), x=1)
        genrecombo = ui.comboentry(items=self.tags_win_genres(), wrap=2)
        genreentry = genrecombo.get_child()
        genrehbox = gtk.HBox()
        genrebutton = ui.button()
        genrebuttonvbox = self.tags_win_create_apply_all_button(genrebutton,
                                                                genreentry)
        genrehbox.pack_start(genrelabel, False, False, 2)
        genrehbox.pack_start(genrecombo, True, True, 2)
        genrehbox.pack_start(genrebuttonvbox, False, False, 2)

        commentlabel, commententry, commentbutton, commenthbox = self._create_label_entry_button_hbox(_("Comment:"))

        ui.set_widths_equal([titlelabel, artistlabel, albumlabel, yearlabel, genrelabel, commentlabel, sonataicon])
        genrecombo.set_size_request(-1, titleentry.size_request()[1])
        tablewidgets = [ui.label(), filehbox, ui.label(), titlehbox, artisthbox, albumhbox, yearandtrackhbox, genrehbox, commenthbox, ui.label()]
        for i, widget in enumerate(tablewidgets):
            table.attach(widget, 1, 2, i+1, i+2, gtk.FILL|gtk.EXPAND, gtk.FILL|gtk.EXPAND, 2, 0)
        editwindow.vbox.pack_start(table)
        saveall_button = None
        if len(files) > 1:
            # Only show save all button if more than one song being edited.
            saveall_button = ui.button(text=_("Save _All"))
            editwindow.action_area.pack_start(saveall_button)
        editwindow.add_button(gtk.STOCK_CANCEL, gtk.RESPONSE_REJECT)
        editwindow.add_button(gtk.STOCK_SAVE, gtk.RESPONSE_ACCEPT)
        editwindow.connect('delete_event', self.tags_win_hide, tags)
        entries = [titleentry, artistentry, albumentry, yearentry, trackentry, genreentry, commententry]
        buttons = [titlebutton, artistbutton, albumbutton, yearbutton, trackbutton, genrebutton, commentbutton]
        entries_names = ["title", "artist", "album", "year", "track", "genre", "comment"]
        editwindow.connect('response', self.tags_win_response, tags, entries, entries_names)
        if saveall_button:
            saveall_button.connect('clicked', self.tags_win_save_all, editwindow, tags, entries, entries_names)

        for button, name, entry in zip(buttons, entries_names, entries):
            entry.connect('changed', self.tags_win_entry_changed)
            button.connect('clicked', self.tags_win_apply_all, name, tags, entry)

        self.tags_win_update(editwindow, tags, entries, entries_names)
        ui.change_cursor(None)
        self.filelabel.set_size_request(editwindow.size_request()[0] - titlelabel.size_request()[0] - 70, -1)
        editwindow.show_all()

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

    def tags_win_entry_changed(self, editable):
        style = editable.get_style().copy()
        style.text[gtk.STATE_NORMAL] = editable.get_colormap().alloc_color("red")
        editable.set_style(style)

    def tags_win_entry_revert_color(self, editable):
        editable.set_style(None)

    def tags_win_create_apply_all_button(self, button, entry, autotrack=False):
        button.set_size_request(12, 12)
        if autotrack:
            button.set_tooltip_text(_("Increment each selected music file, starting at track 1 for this file."))
        else:
            button.set_tooltip_text(_("Apply to all selected music files."))
        padding = int((entry.size_request()[1] - button.size_request()[1])/2)+1
        vbox = gtk.VBox();
        vbox.pack_start(button, False, False, padding)
        return vbox

    def tags_win_apply_all(self, _button, item, tags, entry):
        for tagnum, tag in enumerate(tags):
            tagnum = tagnum + 1
            if item in ("title", "album", "artist", "genre", "comment"):
                tag[item] = entry.get_text()
                tag[item + '-changed'] = True
            elif item == "year":
                if len(entry.get_text()) > 0:
                    tag['year'] = int(entry.get_text())
                else:
                    tag['year'] = 0
                tag['year-changed'] = True
            elif item == "track":
                if tagnum >= self.tagnum-1:
                    # Start the current song at track 1, as opposed to the first
                    # song in the list.
                    tag['track'] = tagnum - self.tagnum
                tag['track-changed'] = True
        if item == "track":
            # Update the entry for the current song:
            entry.set_text(str(tags[self.tagnum]['track']))

    def tags_win_update(self, window, tags, entries, entries_names):
        current_tag = tags[self.tagnum]
        tag = tagpy.FileRef(current_tag['fullpath']).tag()
        # Update interface:
        for entry, entry_name in zip(entries, entries_names):
            # Only retrieve info from the file if the info hasn't changed
            if not current_tag[entry_name + "-changed"]:
                current_tag[entry_name] = getattr(tag, entry_name, '')
            tag_value = current_tag[entry_name]
            if tag_value == 0:
                tag_value = ''
            entry.set_text(str(tag_value).strip())

            # Revert text color if this tag wasn't changed by the user
            if not current_tag[entry_name + "-changed"]:
                self.tags_win_entry_revert_color(entry)

        self.curr_mpdpath = gobject.filename_display_name(current_tag['mpdpath'])
        filename = self.curr_mpdpath
        if not self.use_mpdpaths:
            filename = os.path.basename(filename)
        self.filelabel.set_text(filename)
        entries[0].grab_focus()
        window.set_title(_("Edit Tags - %s of %s") %
                    (self.tagnum+1, len(tags)))
        self.tags_win_set_sensitive(window.action_area)

    def tags_win_set_sensitive(self, action_area):
        # Hacky workaround to allow the user to click the save button again when the
        # mouse stays over the button (see http://bugzilla.gnome.org/show_bug.cgi?id=56070)
        action_area.set_sensitive(True)
        action_area.hide()
        action_area.show_all()

    def tags_win_save_all(self, _button, window, tags, entries, entries_names):
        for entry in entries:
            entry.set_property('editable', False)
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
            tag = filetag.tag()
            # Set tag fields according to entry text
            for entry, field in zip(entries, entries_names):
                tag_value = entry.get_text().strip()
                if field in ('year', 'track'):
                    if len(tag_value) == 0:
                        tag_value = '0'
                    tag_value = int(tag_value)
                if field is 'comment':
                    if len(tag_value) == 0:
                        tag_value = ' '
                setattr(tag, field, tag_value)

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

    def tags_win_hide(self, window, _data, tags):
        tag_paths = (tag['mpdpath'] for tag in tags[:self.tagnum])
        gobject.idle_add(self.tags_mpd_update, tag_paths)
        window.destroy()
        self.tags_set_use_mpdpath(self.use_mpdpaths)

    def tags_win_genres(self):
        return ["", "A Cappella", "Acid", "Acid Jazz", "Acid Punk", "Acoustic",
                "Alt. Rock", "Alternative", "Ambient", "Anime", "Avantgarde", "Ballad",
                "Bass", "Beat", "Bebob", "Big Band", "Black Metal", "Bluegrass",
                "Blues", "Booty Bass", "BritPop", "Cabaret", "Celtic", "Chamber music",
                "Chanson", "Chorus", "Christian Gangsta Rap", "Christian Rap",
                "Christian Rock", "Classic Rock", "Classical", "Club", "Club-House",
                "Comedy", "Contemporary Christian", "Country", "Crossover", "Cult",
                "Dance", "Dance Hall", "Darkwave", "Death Metal", "Disco", "Dream",
                "Drum & Bass", "Drum Solo", "Duet", "Easy Listening", "Electronic",
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
                "Punk Rock", "R&B", "Rap", "Rave", "Reggae", "Retro", "Revival",
                "Rhythmic soul", "Rock", "Rock & Roll", "Salsa", "Samba", "Satire",
                "Showtunes", "Ska", "Slow Jam", "Slow Rock", "Sonata", "Soul",
                "Sound Clip", "Soundtrack", "Southern Rock", "Space", "Speech",
                "Swing", "Symphonic Rock", "Symphony", "Synthpop", "Tango", "Techno",
                "Techno-Industrial", "Terror", "Thrash Metal", "Top 40", "Trailer"]

    def tags_win_entry_constraint(self, entry, new_text, _new_text_length, _broken_position, isyearlabel):
        entry_chars = entry.get_text()
        pos = entry.get_position()
        proposed_text = entry_chars[:pos] + new_text + entry_chars[pos:]

        # get the correct regular expression
        expr = r'(0|[1-9][0-9]{0,3})$' if isyearlabel else r'(0|[1-9][0-9]*)$'
        expr = re.compile(expr)

        if not expr.match(proposed_text):
            # deny
            entry.stop_emission("insert-text")

    def toggle_path(self, button):
        self.use_mpdpaths = not self.use_mpdpaths
        if self.use_mpdpaths:
            self.filelabel.set_text(self.curr_mpdpath)
        else:
            self.filelabel.set_text(os.path.basename(self.curr_mpdpath))
        self.set_expandbutton_state(button)

    def set_expandbutton_state(self, button):
        if self.use_mpdpaths:
            button.get_child().set_markup('<small>&lt;</small>')
            button.set_tooltip_text(_("Hide file path"))
        else:
            button.get_child().set_markup('<small>&gt;</small>')
            button.set_tooltip_text(_("Show file path"))

    def set_use_mpdpaths(self, use_mpdpaths):
        self.use_mpdpaths = use_mpdpaths
