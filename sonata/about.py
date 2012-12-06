# coding=utf-8

import gettext
import os

from gi.repository import Gtk, GdkPixbuf

from sonata import misc, ui

class About(object):

    def __init__(self, parent_window, config, version, licensetext, icon_file):
        self.parent_window = parent_window
        self.config = config
        self.version = version
        self.license = licensetext
        self.icon_file = icon_file

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
        for pair in shortcuts:
            titlelabel = ui.label(markup="<b>%s</b>" % pair[0])
            vbox.pack_start(titlelabel, False, False, 2)

            # print the items of [ shortcut, desc ]
            for item in pair[1]:
                tmphbox = Gtk.HBox()

                tmplabel = ui.label(markup="<b>%s:</b>" % item[0], y=0)
                tmpdesc = ui.label(text=item[1], wrap=True, y=0)

                tmphbox.pack_start(tmplabel, False, False, 2)
                tmphbox.pack_start(tmpdesc, True, True, 2)

                vbox.pack_start(tmphbox, False, False, 2)
            vbox.pack_start(ui.label(text=" "), False, False, 2)

    def about_shortcuts(self, _button):
        if not self.shortcuts_dialog:
            self._init_shortcuts_dialog()
        self.shortcuts_dialog.show_all()
        self.shortcuts_dialog.run()

    def statstext(self, stats):
        # XXX translate expressions, not words
        statslabel = '%s %s.\n' % (stats['songs'],
                                   ngettext('song', 'songs',
                                            int(stats['songs'])))
        statslabel += '%s %s.\n' % (stats['albums'],
                                    ngettext('album', 'albums',
                                             int(stats['albums'])))
        statslabel += '%s %s.\n' % (stats['artists'],
                                   ngettext('artist', 'artists',
                                            int(stats['artists'])))

        try:
            db_playtime = float(stats['db_playtime'])
            hours_of_playtime = int(misc.convert_time(db_playtime).split(':')[-3])
        except:
            hours_of_playtime = 0
        if hours_of_playtime >= 24:
            days_of_playtime = round(hours_of_playtime / 24, 1)
            statslabel += '%s %s.' % (days_of_playtime,
                                      ngettext('day of bliss',
                                               'days of bliss',
                                               int(days_of_playtime)))
        else:
            statslabel += '%s %s.' % (hours_of_playtime,
                                      ngettext('hour of bliss',
                                               'hours of bliss',
                                               int(hours_of_playtime)))

        return statslabel

    def about_load(self, stats):
        self.builder = Gtk.Builder()
        self.builder.add_from_file('{0}/ui/about.ui'.format(
            os.path.dirname(ui.__file__)))
        self.builder.set_translation_domain('sonata')

        self.about_dialog = self.builder.get_object('about_dialog')
        try:
            self.about_dialog.set_transient_for(self.parent_window)
        except:
            pass
        self.about_dialog.set_version(self.version)
        if stats:
            self.about_dialog.set_copyright(self.statstext(stats))
        large_icon = GdkPixbuf.Pixbuf.new_from_file(self.icon_file)
        self.about_dialog.set_logo(large_icon)
        # Add button to show keybindings:
        children = self.about_dialog.action_area.get_children()[-1]
        self.about_dialog.action_area.reorder_child(children, -2)
        # Connect to callbacks
        self.about_dialog.connect('response', self.about_close)
        self.about_dialog.connect('delete_event', self.about_close)
        shortcut_button = self.builder.get_object('shortcut_button')
        shortcut_button.connect('clicked', self.about_shortcuts)
        self.about_dialog.show_all()

