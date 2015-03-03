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

from gi.repository import Gtk, GLib
tagpy = None # module loaded when needed

from sonata import ui, misc


class TagEditor:
    """This class implements a dialog for editing music metadata tags.

    When the dialog closes, the callback gets the list of updates made.
    """
    def __init__(self, window, tags_mpd_update, tags_set_use_mpdpath):
        self.window = window
        self.tags_mpd_update = tags_mpd_update
        self.tags_set_use_mpdpath = tags_set_use_mpdpath

        self.file_label = None
        self.curr_mpdpath = None
        self.tagnum = None
        self.use_mpdpaths = None

        self.edit_window = None
        self.entries = None
        self.tags = None

        self.builder = ui.builder('tagedit')
        self.css_provider = ui.css_provider('tagedit')


    def _init_edit_window(self):
        self.edit_window = self.builder.get_object('tags_dialog')
        self.edit_window.set_transient_for(self.window)
        self.file_label = self.builder.get_object('tags_file_label')
        genre_combo = self.builder.get_object('tags_genre_comboboxtext')
        for genre in self.tags_win_genres():
            genre_combo.append_text(genre)
        expand_arrow = self.builder.get_object('tags_expand_arrow')
        expand_button = self.builder.get_object('tags_expand_file_button')
        self.set_expandbutton_state(expand_button, expand_arrow)
        expand_button.connect('clicked', self.toggle_path, expand_arrow)

        year_entry = self.builder.get_object('tags_year_entry')
        year_entry.connect('insert_text', self.tags_win_entry_constraint, True)
        track_entry = self.builder.get_object('tags_track_entry')
        track_entry.connect('insert_text', self.tags_win_entry_constraint, False)
        artist_entry = self.builder.get_object('tags_artist_entry')
        album_entry = self.builder.get_object('tags_album_entry')
        title_entry = self.builder.get_object('tags_title_entry')
        genre_entry = self.builder.get_object('tags_genre_entry')
        comment_entry = self.builder.get_object('tags_comment_entry')
        self.entries = {
            'title': title_entry,
            'artist': artist_entry,
            'album': album_entry,
            'year': year_entry,
            'track': track_entry,
            'genre': genre_entry,
            'comment': comment_entry,}

        year_button = self.builder.get_object('tags_save_year_button')
        track_button = self.builder.get_object('tags_save_track_button')
        artist_button = self.builder.get_object('tags_save_artist_button')
        album_button = self.builder.get_object('tags_save_album_button')
        title_button = self.builder.get_object('tags_save_title_button')
        genre_button = self.builder.get_object('tags_save_genre_button')
        comment_button = self.builder.get_object('tags_save_comment_button')
        buttons = (title_button, artist_button, album_button, year_button,
                   track_button, genre_button, comment_button)
        names = ('title', 'artist', 'album', 'year',
                 'track', 'genre', 'comment')
        for name, button in zip(names, buttons):
            entry = self.entries[name]
            entry.connect('changed', self.tags_win_entry_changed)
            button.connect('clicked', self.tags_win_apply_all, name, entry)

    def on_tags_edit(self, files, temp_mpdpaths, music_dir):
        """Display the editing dialog"""
        # Try loading module
        global tagpy
        if tagpy is None:
            try:
                import tagpy
            except ImportError:
                ui.show_msg(self.window, _("Taglib and/or tagpy not found, tag editing support disabled."), _("Edit Tags"), 'editTagsError', Gtk.ButtonsType.CLOSE, response_cb=ui.dialog_destroy)
                ui.change_cursor(None)
                return
            # Set default tag encoding to utf8.. fixes some reported bugs.
            import tagpy.id3v2 as id3v2
            id3v2.FrameFactory.instance().setDefaultTextEncoding(tagpy.StringType.UTF8)

        # Make sure tagpy is at least 0.91
        if hasattr(tagpy.Tag.title, '__call__'):
            ui.show_msg(self.window, _("Tagpy version < 0.91. Please upgrade to a newer version, tag editing support disabled."), _("Edit Tags"), 'editTagsError', Gtk.ButtonsType.CLOSE, response_cb=ui.dialog_destroy)
            ui.change_cursor(None)
            return

        if not os.path.isdir(music_dir):
            ui.show_msg(self.window, _("The path %s does not exist. Please specify a valid music directory in preferences.") % music_dir, _("Edit Tags"), 'editTagsError', Gtk.ButtonsType.CLOSE, response_cb=ui.dialog_destroy)
            ui.change_cursor(None)
            return

                # XXX file list was created here

        if len(files) == 0:
            ui.change_cursor(None)
            return

        # Initialize:
        self.tagnum = -1

        self.tags = [{
             'title': '', 'artist': '', 'album': '', 'year': '', 'track': '',
             'genre': '', 'comment': '', 'title-changed': False,
             'artist-changed': False, 'album-changed': False,
             'year-changed': False, 'track-changed': False,
             'genre-changed': False, 'comment-changed': False,
             'fullpath': filename,
             'mpdpath': path,}
            for filename, path in zip(files, temp_mpdpaths)]

        if not os.path.exists(self.tags[0]['fullpath']):
            ui.change_cursor(None)
            ui.show_msg(self.window, _("File '%s' not found. Please specify a valid music directory in preferences.") % self.tags[0]['fullpath'], _("Edit Tags"), 'editTagsError', Gtk.ButtonsType.CLOSE, response_cb=ui.dialog_destroy)
            return
        if not self.tags_next_tag():
            ui.change_cursor(None)
            ui.show_msg(self.window, _("No music files with editable tags found."), _("Edit Tags"), 'editTagsError', Gtk.ButtonsType.CLOSE, response_cb=ui.dialog_destroy)
            return
        if not self.edit_window:
            self._init_edit_window()

        saveall_button = self.builder.get_object('tags_saveall_button')
        if len(files) > 1:
            # Only show save all button if more than one song being edited.
            saveall_button.show()
            saveall_button.set_property("visible", True)
        else:
            saveall_button.hide()
            saveall_button.set_property("visible", False)

        self.tags_win_update()
        self.edit_window.show_all()
        SAVE_ALL = -12
        done = False

        while not done:
            # Next file:
            self.tags_win_update()
            response = self.edit_window.run()
            if response == SAVE_ALL:
                self.save_tag()
                while self.tags_next_tag():
                    self.tags_win_update()
                    self.save_tag()
                done = True
            elif response == Gtk.ResponseType.ACCEPT:
                self.save_tag()
                done = not self.tags_next_tag()
                if done:
                    # To ensure we update the last file in tags_mpd_update
                    self.tagnum = self.tagnum + 1
            elif response == Gtk.ResponseType.REJECT:
                done = True

        tag_paths = (tag['mpdpath'] for tag in self.tags[:self.tagnum])
        GLib.idle_add(self.tags_mpd_update, tag_paths)
        self.tags_set_use_mpdpath(self.use_mpdpaths)

        self.tags = None
        ui.change_cursor(None)
        self.edit_window.hide()

    def tags_next_tag(self):
        # Returns true if next tag found (and self.tagnum is updated).
        # If no next tag found, returns False.
        while self.tagnum < len(self.tags) - 1:
            self.tagnum = self.tagnum + 1
            if os.path.exists(self.tags[self.tagnum]['fullpath']):
                fileref = tagpy.FileRef(self.tags[self.tagnum]['fullpath'])
                if not fileref.isNull():
                    return True
        return False

    def tags_win_entry_changed(self, entry):
        style_context = entry.get_style_context()
        style_context.add_class('modified')

    def tags_win_entry_revert_color(self, entry):
        style_context = entry.get_style_context()
        style_context.remove_class('modified')

    def tags_win_apply_all(self, _button, item, entry):
        for tagnum, tag in enumerate(self.tags):
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
                if tagnum >= self.tagnum - 1:
                    # Start the current song at track 1, as opposed to the first
                    # song in the list.
                    tag['track'] = tagnum - self.tagnum
                tag['track-changed'] = True
        if item == "track":
            # Update the entry for the current song:
            entry.set_text(str(self.tags[self.tagnum]['track']))

    def tags_win_update(self):
        current_tag = self.tags[self.tagnum]
        tag = tagpy.FileRef(current_tag['fullpath']).tag()
        # Update interface:
        for entry_name, entry in self.entries.items():
            # Only retrieve info from the file if the info hasn't changed
            if not current_tag[entry_name + "-changed"]:
                current_tag[entry_name] = getattr(tag, entry_name, '')
            tag_value = current_tag[entry_name]
            if tag_value == 0:
                tag_value = ''
            try:
                entry.set_text(str(tag_value).strip())
            except AttributeError:
                pass

            # Revert text color if this tag wasn't changed by the user
            if not current_tag[entry_name + "-changed"]:
                self.tags_win_entry_revert_color(entry)

        self.curr_mpdpath = GLib.filename_display_name(current_tag['mpdpath'])
        filename = self.curr_mpdpath
        if not self.use_mpdpaths:
            filename = os.path.basename(filename)
        self.file_label.set_text(filename)
        self.entries['title'].grab_focus()
        self.edit_window.set_title(_("Edit Tags - %s of %s") %
            (self.tagnum + 1, len(self.tags)))

    def save_tag(self):
        filetag = tagpy.FileRef(self.tags[self.tagnum]['fullpath'])
        tag = filetag.tag()
        # Set tag fields according to entry text
        for field, entry in self.entries.items():
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
            ui.show_msg(self.window,
                        _("Unable to save tag to music file."),
                        _("Edit Tags"), 'editTagsError',
                        Gtk.ButtonsType.CLOSE,
                        response_cb=ui.dialog_destroy)

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

    def toggle_path(self, button, arrow):
        self.use_mpdpaths = not self.use_mpdpaths
        if self.use_mpdpaths:
            self.file_label.set_text(self.curr_mpdpath)
        else:
            self.file_label.set_text(os.path.basename(self.curr_mpdpath))
        self.set_expandbutton_state(button, arrow)

    def set_expandbutton_state(self, button, arrow):
        if self.use_mpdpaths:
            arrow.set_property("arrow-type", Gtk.ArrowType.LEFT)
            button.set_tooltip_text(_("Hide file path"))
        else:
            arrow.set_property("arrow-type", Gtk.ArrowType.RIGHT)
            button.set_tooltip_text(_("Show file path"))

    def set_use_mpdpaths(self, use_mpdpaths):
        self.use_mpdpaths = use_mpdpaths

