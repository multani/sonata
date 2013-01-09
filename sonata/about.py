# coding=utf-8

import gettext
import os

from gi.repository import Gtk, GdkPixbuf

from sonata import misc, ui

class About:

    def __init__(self, parent_window, config, version, licensetext):
        self.parent_window = parent_window
        self.config = config
        self.version = version
        self.license = licensetext

        self.about_dialog = None
        self.shortcuts_dialog = None

    def about_close(self, _event, _data=None):
        if _data == Gtk.ResponseType.DELETE_EVENT or \
           _data == Gtk.ResponseType.CANCEL:
            self.about_dialog.hide()
        return True

    def shortcuts_close(self, _event, _data=None):
        if _data == Gtk.ResponseType.DELETE_EVENT or \
           _data == Gtk.ResponseType.CANCEL:
            self.shortcuts_dialog.hide()
        return True

    def shortcuts_close_click_cb(self, _button):
        self.shortcuts_dialog.hide()

    def _init_shortcuts_dialog(self):
        # define the shortcuts and their descriptions
        # these are all gettextable
        # Keep them here (not as XML) as they're more convenient this way
        mainshortcuts = \
                [["F1", _("About Sonata")],
                 ["F5", _("Preferences")],
                 ["F11", _("Fullscreen Artwork Mode")],
                 ["Alt-[1-5]", _("Switch to [1st-5th] tab")],
                 ["Alt-C", _("Connect to MPD")],
                 ["Alt-D", _("Disconnect from MPD")],
                 ["Alt-R", _("Randomize current playlist")],
                 ["Alt-Down", _("Expand player")],
                 ["Alt-Left", _("Switch to previous tab")],
                 ["Alt-Right", _("Switch to next tab")],
                 ["Alt-Up", _("Collapse player")],
                 ["Ctrl-H", _("Search library")],
                 ["Ctrl-Q", _("Quit")],
                 ["Ctrl-Shift-U", _("Update entire library")],
                 ["Menu", _("Display popup menu")],
                 ["Escape", _("Minimize to system tray (if enabled)")]]
        playbackshortcuts = \
                [["Ctrl-Left", _("Previous track")],
                 ["Ctrl-Right", _("Next track")],
                 ["Ctrl-P", _("Play/Pause")],
                 ["Ctrl-S", _("Stop")],
                 ["Ctrl-Minus", _("Lower the volume")],
                 ["Ctrl-Plus", _("Raise the volume")]]
        currentshortcuts = \
                [["Enter/Space", _("Play selected song")],
                 ["Delete", _("Remove selected song(s)")],
                 ["Ctrl-I", _("Center currently playing song")],
                 ["Ctrl-T", _("Edit selected song's tags")],
                 ["Ctrl-Shift-S", _("Save to new playlist")],
                 ["Ctrl-Delete", _("Clear list")],
                 ["Alt-R", _("Randomize list")]]
        libraryshortcuts = \
                [["Enter/Space", _("Add selected song(s) or enter directory")],
                 ["Backspace", _("Go to parent directory")],
                 ["Ctrl-D", _("Add selected item(s)")],
                 ["Ctrl-R", _("Replace with selected item(s)")],
                 ["Ctrl-T", _("Edit selected song's tags")],
                 ["Ctrl-Shift-D", _("Add selected item(s) and play")],
                 ["Ctrl-Shift-R", _("Replace with selected item(s) and play")],
                 ["Ctrl-U", _("Update selected item(s)/path(s)")]]
        playlistshortcuts = \
                [["Enter/Space", _("Add selected playlist(s)")],
                 ["Delete", _("Remove selected playlist(s)")],
                 ["Ctrl-D", _("Add selected playlist(s)")],
                 ["Ctrl-R", _("Replace with selected playlist(s)")],
                 ["Ctrl-Shift-D", _("Add selected playlist(s) and play")],
                 ["Ctrl-Shift-R", _(('Replace with selected '
                                     'playlist(s) and play'))]]
        streamshortcuts = \
                [["Enter/Space", _("Add selected stream(s)")],
                 ["Delete", _("Remove selected stream(s)")],
                 ["Ctrl-D", _("Add selected stream(s)")],
                 ["Ctrl-R", _("Replace with selected stream(s)")],
                 ["Ctrl-Shift-D", _("Add selected stream(s) and play")],
                 ["Ctrl-Shift-R", _(('Replace with selected '
                                     'stream(s) and play'))]]
        infoshortcuts = \
                [["Ctrl-T", _("Edit playing song's tags")]]
        # define the main array- this adds headings to each section of
        # shortcuts that will be displayed
        shortcuts = [[_("Main Shortcuts"), mainshortcuts],
                [_("Playback Shortcuts"), playbackshortcuts],
                [_("Current Shortcuts"), currentshortcuts],
                [_("Library Shortcuts"), libraryshortcuts],
                [_("Playlist Shortcuts"), playlistshortcuts],
                [_("Stream Shortcuts"), streamshortcuts],
                [_("Info Shortcuts"), infoshortcuts]]
        self.shortcuts_dialog = self.builder.get_object('shortcuts_dialog')
        self.shortcuts_dialog.connect('response', self.shortcuts_close)
        self.shortcuts_dialog.connect('delete_event', self.shortcuts_close)
        shortcuts_close_button = self.builder.get_object(
            'shortcuts_dialog_closebutton')
        shortcuts_close_button.connect('clicked', self.shortcuts_close_click_cb)

        # each pair is a [ heading, shortcutlist ]
        vbox = self.builder.get_object('shortcuts_dialog_content_box')
        for heading, shortcutlist in shortcuts:
            titlelabel = Gtk.Label(heading, xalign=0)
            titlelabel.get_style_context().add_class('heading')
            vbox.pack_start(titlelabel, False, False, 2)

            # print the items of [ shortcut, desc ]
            for shortcut, desc in shortcutlist:
                tmphbox = Gtk.HBox()

                tmplabel = Gtk.Label('{}:'.format(shortcut), xalign=0)
                tmplabel.get_style_context().add_class('shortcut')
                tmpdesc = Gtk.Label(desc, xalign=0, wrap=False)

                tmphbox.pack_start(tmplabel, False, False, 2)
                tmphbox.pack_start(tmpdesc, True, True, 2)

                vbox.pack_start(tmphbox, False, False, 2)
            vbox.pack_start(Gtk.Label(" "), False, False, 2)

    def about_shortcuts(self, _button):
        if not self.shortcuts_dialog:
            self._init_shortcuts_dialog()
        self.shortcuts_dialog.show_all()
        self.shortcuts_dialog.run()

    def statstext(self, stats):
        song_count = int(stats['songs'])
        song_text = ngettext('{count} song.', '{count} songs.',
                             song_count).format(count=song_count)
        album_count = int(stats['albums'])
        album_text = ngettext('{count} album.', '{count} albums.',
                              album_count).format(count=album_count)
        artist_count = int(stats['artists'])
        artist_text = ngettext('{count} artist.', '{count} artists.',
                               artist_count).format(count=artist_count)

        try:
            db_playtime = float(stats['db_playtime'])
            hours = int(misc.convert_time(db_playtime).split(':')[-3])
        except:
            hours = 0
        if hours >= 24:
            days = round(hours / 24, 1)
            time_text = ngettext('{count} day of bliss.',
                                 '{count} days of bliss.',
                                 days).format(count=days)
        else:
            time_text = ngettext('{count} hour of bliss.',
                                 '{count} hours of bliss.',
                                 hours).format(count=hours)

        parts = (song_text, album_text, artist_text, time_text)
        live_parts = [part for part in parts if part is not None]
        return '\n'.join(live_parts)

    def about_load(self, stats):
        self.builder = ui.builder('about')
        self.provider = ui.css_provider('about')
        self.about_dialog = self.builder.get_object('about_dialog')
        try:
            self.about_dialog.set_transient_for(self.parent_window)
        except:
            pass
        self.about_dialog.set_version(self.version)
        if stats:
            self.about_dialog.set_copyright(self.statstext(stats))
        context = self.about_dialog.get_style_context()
        logo_icon = Gtk.IconFactory.lookup_default('sonata-large')
        logo_pb = logo_icon.render_icon_pixbuf(context, -1)
        self.about_dialog.set_logo(logo_pb)
        # Add button to show keybindings:
        children = self.about_dialog.action_area.get_children()[-1]
        self.about_dialog.action_area.reorder_child(children, -2)
        # Connect to callbacks
        self.about_dialog.connect('response', self.about_close)
        self.about_dialog.connect('delete_event', self.about_close)
        shortcut_button = self.builder.get_object('shortcut_button')
        shortcut_button.connect('clicked', self.about_shortcuts)
        self.about_dialog.show_all()

