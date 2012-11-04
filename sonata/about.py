# coding=utf-8

import gettext

import gtk

import misc
import ui

translators = '''\
ar - Ahmad Farghal <ahmad.farghal@gmail.com>
be@latin - Ihar Hrachyshka <ihar.hrachyshka@gmail.com>
ca - Franc Rodriguez <franc.rodriguez@tecob.com>
cs - Jakub Adler <jakubadler@gmail.com>
da - Martin Dybdal <dybber@dybber.dk>
de - Paul Johnson <thrillerator@googlemail.com>
el_GR - Lazaros Koromilas <koromilaz@gmail.com>
es - Xoan Sampaiño <xoansampainho@gmail.com>
et - Mihkel <turakas@gmail.com>
fi - Ilkka Tuohela <hile@hack.fi>
fr - Floreal M <florealm@gmail.com>
it - Gianni Vialetto <forgottencrow@gmail.com>
ja - Masato Hashimoto <cabezon.hashimoto@gmail.com>
ko - Jaesung BANG <jaesung@liberotown.com>
nl - Olivier Keun <litemotiv@gmail.com>
pl - Tomasz Dominikowski <dominikowski@gmail.com>
pt_BR - Alex Tercete Matos <alextercete@gmail.com>
ru - Ivan <bkb.box@bk.ru>
sk - Robert Hartl <hartl.robert@gmail.com>
sl - Alan Pepelko <alan.pepelko@gmail.com>
sv - Daniel Nylander <po@danielnylander.se>
tr - Gökmen Görgen <gkmngrgn@gmail.com>
uk - Господарисько Тарас <dogmaton@gmail.com>
zh_CN - Desmond Chang <dochang@gmail.com>
zh_TW - Ian-Xue Li <da.mi.spirit@gmail>
'''


class About(object):

    def __init__(self, parent_window, config, version, licensetext, icon_file):
        self.parent_window = parent_window
        self.config = config
        self.version = version
        self.license = licensetext
        self.icon_file = icon_file

        self.about_dialog = None

    def about_close(self, _event, _data=None):
        self.about_dialog.hide()
        return True

    def about_shortcuts(self, _button):
        # define the shortcuts and their descriptions
        # these are all gettextable
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
        dialog = ui.dialog(title=_("Shortcuts"), parent=self.about_dialog,
                           flags=gtk.DIALOG_MODAL |
                           gtk.DIALOG_DESTROY_WITH_PARENT,
                           buttons=(gtk.STOCK_CLOSE, gtk.RESPONSE_CLOSE),
                           role='shortcuts', default=gtk.RESPONSE_CLOSE, h=320)

        # each pair is a [ heading, shortcutlist ]
        vbox = gtk.VBox()
        for pair in shortcuts:
            titlelabel = ui.label(markup="<b>%s</b>" % pair[0])
            vbox.pack_start(titlelabel, False, False, 2)

            # print the items of [ shortcut, desc ]
            for item in pair[1]:
                tmphbox = gtk.HBox()

                tmplabel = ui.label(markup="<b>%s:</b>" % item[0], y=0)
                tmpdesc = ui.label(text=item[1], wrap=True, y=0)

                tmphbox.pack_start(tmplabel, False, False, 2)
                tmphbox.pack_start(tmpdesc, True, True, 2)

                vbox.pack_start(tmphbox, False, False, 2)
            vbox.pack_start(ui.label(text=" "), False, False, 2)
        scrollbox = ui.scrollwindow(policy_x=gtk.POLICY_NEVER, addvp=vbox)
        dialog.vbox.pack_start(scrollbox, True, True, 2)
        dialog.show_all()
        dialog.run()
        dialog.destroy()

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
            hours_of_playtime = misc.convert_time(db_playtime).split(':')[-3]
        except:
            hours_of_playtime = '0'
        if int(hours_of_playtime) >= 24:
            days_of_playtime = str(int(hours_of_playtime) / 24)
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
        self.about_dialog = gtk.AboutDialog()
        try:
            self.about_dialog.set_transient_for(self.parent_window)
            self.about_dialog.set_modal(True)
        except:
            pass
        self.about_dialog.set_name('Sonata')
        self.about_dialog.set_role('about')
        self.about_dialog.set_version(self.version)
        commentlabel = _('An elegant music client for MPD.')
        self.about_dialog.set_comments(commentlabel)
        if stats:
            self.about_dialog.set_copyright(self.statstext(stats))
        self.about_dialog.set_license(self.license)
        self.about_dialog.set_authors(['Scott Horowitz <stonecrest@gmail.com>',
                                       ('Tuukka Hastrup '
                                       '<Tuukka.Hastrup@iki.fi>'),
                                       'Stephen Boyd <bebarino@gmail.com>'])
        self.about_dialog.set_artists([('Adrian Chromenko <adrian@rest0re.org>'
                                       '\nhttp://oss.rest0re.org/')])
        self.about_dialog.set_translator_credits(translators)
        gtk.about_dialog_set_url_hook(self.show_website)
        self.about_dialog.set_website("http://sonata.berlios.de/")
        large_icon = gtk.gdk.pixbuf_new_from_file(self.icon_file)
        self.about_dialog.set_logo(large_icon)
        # Add button to show keybindings:
        shortcut_button = ui.button(text=_("_Shortcuts"))
        self.about_dialog.action_area.pack_start(shortcut_button)
        children = self.about_dialog.action_area.get_children()[-1]
        self.about_dialog.action_area.reorder_child(children, -2)
        # Connect to callbacks
        self.about_dialog.connect('response', self.about_close)
        self.about_dialog.connect('delete_event', self.about_close)
        shortcut_button.connect('clicked', self.about_shortcuts)
        self.about_dialog.show_all()

    def show_website(self, _dialog, link):
        if not misc.browser_load(link, self.config.url_browser,
                                 self.parent_window):
            ui.show_msg(self.about_dialog, _(('Unable to launch a '
                                             'suitable browser.')),
                        _('Launch Browser'), 'browserLoadError',
                        gtk.BUTTONS_CLOSE)
