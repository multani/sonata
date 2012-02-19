
"""
This module provides a user interface for changing configuration
variables.

Example usage:
import preferences
...
prefs = preferences.Preferences()
prefs.on_prefs_real(self.window, self.prefs_window_response, tab callbacks...)
"""

import gettext, hashlib

from gi.repository import Gtk, Gdk, GdkPixbuf, GObject

from sonata.consts import consts
from sonata.config import Config
from sonata.pluginsystem import pluginsystem
from sonata import ui, misc, formatting
import os

class Extras_cbs(object):
    """Callbacks and data specific to the extras tab"""
    popuptimes = []
    popuplocations = [_('System tray'), _('Top Left'), _('Top Right'),
              _('Bottom Left'), _('Bottom Right'),
              _('Screen Center')]
    notif_toggled = None
    crossfade_changed = None
    crossfade_toggled = None

class Display_cbs(object):
    """Callbacks specific to the display tab"""
    stylized_toggled = None
    art_toggled = None
    playback_toggled = None
    progress_toggled = None
    statusbar_toggled = None
    lyrics_toggled = None
    trayicon_available = None

class Behavior_cbs(object):
    """Callbacks and data specific to the behavior tab"""
    trayicon_toggled = None
    trayicon_in_use = None
    sticky_toggled = None
    ontop_toggled = None
    decorated_toggled = None
    infofile_changed = None

class Format_cbs(object):
    """Callbacks specific to the format tab"""
    currentoptions_changed = None
    libraryoptions_changed = None
    titleoptions_changed = None
    currsongoptions1_changed = None
    currsongoptions2_changed = None

class Preferences():
    """This class implements a preferences dialog for changing
    configuration variables.

    Many changes are applied instantly with respective
    callbacks. Closing the dialog causes a response callback.
    """
    def __init__(self, config, reconnect, renotify, reinfofile,
             settings_save, populate_profiles_for_menu):

        self.config = config

        # These are callbacks to Main
        self.reconnect = reconnect
        self.renotify = renotify
        self.reinfofile = reinfofile
        self.settings_save = settings_save
        self.populate_profiles_for_menu = populate_profiles_for_menu

        # Temporary flag:
        self.updating_nameentry = False

        self.prev_host = None
        self.prev_password = None
        self.prev_port = None

        self.window = None
        self.last_tab = 0
        self.display_trayicon = None
        self.direntry = None
        self.using_mpd_env_vars = False

    def on_prefs_real(self):
        """Display the preferences dialog"""

        self.prefswindow = ui.dialog(title=_("Preferences"), parent=self.window, flags=Gtk.DialogFlags.DESTROY_WITH_PARENT, role='preferences', resizable=False)
        self.prefsnotebook = Gtk.Notebook()

        tabs = [(_("MPD"), 'mpd'),
                (_("Display"), 'display'),
                (_("Behavior"), 'behavior'),
                (_("Format"), 'format'),
                (_("Extras"), 'extras'),
                (_("Plugins"), 'plugins'),
                ]

        for display_name, name in tabs:
            label = ui.label(text=display_name)
            func = getattr(self, '%s_tab' % name)
            cbs = globals().get('%s_cbs' % name.capitalize())
            tab = func(cbs)
            self.prefsnotebook.append_page(tab, label)
        hbox = Gtk.HBox()
        hbox.pack_start(self.prefsnotebook, False, False, 10)
        self.prefswindow.vbox.pack_start(hbox, False, False, 10)
        close_button = self.prefswindow.add_button(Gtk.STOCK_CLOSE, Gtk.ResponseType.CLOSE)
        self.prefswindow.show_all()
        self.prefsnotebook.set_current_page(self.last_tab)
        close_button.grab_focus()
        self.prefswindow.connect('response', self._window_response)
        # Save previous connection properties to determine if we should try to
        # connect to MPD after prefs are closed:
        self.prev_host = self.config.host[self.config.profile_num]
        self.prev_port = self.config.port[self.config.profile_num]
        self.prev_password = self.config.password[self.config.profile_num]

    def mpd_tab(self, cbs=None):
        """Construct and layout the MPD tab"""
        mpdlabel = ui.label(markup='<b>' + _('MPD Connection') + '</b>')
        frame = Gtk.Frame()
        frame.set_label_widget(mpdlabel)
        frame.set_shadow_type(Gtk.ShadowType.NONE)
        controlbox = Gtk.HBox()
        profiles = ui.combo()
        add_profile = ui.button(img=ui.image(stock=Gtk.STOCK_ADD))
        remove_profile = ui.button(img=ui.image(stock=Gtk.STOCK_REMOVE))
        self._populate_profile_combo(profiles, self.config.profile_num,
            remove_profile)
        controlbox.pack_start(profiles, False, False, 2)
        controlbox.pack_start(remove_profile, False, False, 2)
        controlbox.pack_start(add_profile, False, False, 2)
        namelabel = ui.label(textmn=_("_Name:"))
        nameentry = ui.entry()
        namelabel.set_mnemonic_widget(nameentry)
        hostlabel = ui.label(textmn=_("_Host:"))
        hostentry = ui.entry()
        hostlabel.set_mnemonic_widget(hostentry)
        portlabel = ui.label(textmn=_("_Port:"))
        portentry = Gtk.SpinButton.new(Gtk.Adjustment.new(0 ,0 ,65535, 1, 0, 0),1,0)
        portentry.set_numeric(True)
        portlabel.set_mnemonic_widget(portentry)
        dirlabel = ui.label(textmn=_("_Music dir:"))
        direntry = Gtk.FileChooserButton(_('Select a Music Directory'))
        self.direntry = direntry
        direntry.set_action(Gtk.FileChooserAction.SELECT_FOLDER)
        direntry.connect('selection-changed', self._direntry_changed,
            profiles)
        dirlabel.set_mnemonic_widget(direntry)
        passwordlabel = ui.label(textmn=_("Pa_ssword:"))
        passwordentry = ui.entry(password=True)
        passwordlabel.set_mnemonic_widget(passwordentry)
        passwordentry.set_tooltip_text(_("Leave blank if no password is required."))
        autoconnect = Gtk.CheckButton(_("_Autoconnect on start"))
        autoconnect.set_active(self.config.autoconnect)
        autoconnect.connect('toggled', self._config_widget_active,
            'autoconnect')
        # Fill in entries with current profile:
        self._profile_chosen(profiles, nameentry, hostentry,
            portentry, passwordentry, direntry)
        # Update display if $MPD_HOST or $MPD_PORT is set:
        host, port, password = misc.mpd_env_vars()
        if host or port:
            self.using_mpd_env_vars = True
            if not host:
                host = ""
            if not port:
                port = 0
            if not password:
                password = ""
            hostentry.set_text(str(host))
            portentry.set_value(port)
            passwordentry.set_text(str(password))
            nameentry.set_text(_("Using MPD_HOST/PORT"))
            for widget in [hostentry, portentry, passwordentry,
                       nameentry, profiles, add_profile,
                       remove_profile]:
                widget.set_sensitive(False)
        else:
            self.using_mpd_env_vars = False
            nameentry.connect('changed', self._nameentry_changed,
                profiles, remove_profile)
            hostentry.connect('changed', self._hostentry_changed,
                profiles)
            portentry.connect('value-changed',
                self._portentry_changed, profiles)
            passwordentry.connect('changed',
                self._passwordentry_changed, profiles)
            profiles.connect('changed',
                self._profile_chosen, nameentry, hostentry,
                portentry, passwordentry, direntry)
            add_profile.connect('clicked', self._add_profile,
                nameentry, profiles, remove_profile)
            remove_profile.connect('clicked', self._remove_profile,
                profiles, remove_profile)

        rows = [(namelabel, nameentry),
            (hostlabel, hostentry),
            (portlabel, portentry),
            (passwordlabel, passwordentry),
            (dirlabel, direntry)]

        connection_table = Gtk.Table(len(rows), 2)
        connection_table.set_col_spacings(12)
        for i, (label, entry) in enumerate(rows):
            connection_table.attach(label, 0, 1, i, i+1, Gtk.AttachOptions.FILL,
                Gtk.AttachOptions.FILL)
            connection_table.attach(entry, 1, 2, i, i+1,
                Gtk.AttachOptions.FILL|Gtk.AttachOptions.EXPAND, Gtk.AttachOptions.FILL)

        connection_alignment = Gtk.Alignment.new(0.5, 0.5, 1.0, 1.0)
        connection_alignment.set_padding(12, 12, 12, 12)
        connection_alignment.add(connection_table)
        connection_frame = Gtk.Frame()
        connection_frame.set_label_widget(controlbox)
        connection_frame.add(connection_alignment)
        table = Gtk.Table(2, 1)
        table.set_row_spacings(12)
        table.attach(connection_frame, 0, 1, 0, 1,
            Gtk.AttachOptions.FILL|Gtk.AttachOptions.EXPAND, Gtk.AttachOptions.FILL)
        table.attach(autoconnect, 0, 1, 1, 2, Gtk.AttachOptions.FILL|Gtk.AttachOptions.EXPAND,
            Gtk.AttachOptions.FILL)
        alignment = Gtk.Alignment.new(0.5, 0.5, 1.0, 1.0)
        alignment.set_padding(12, 0, 12, 0)
        alignment.add(table)
        frame.add(alignment)
        tab = Gtk.Alignment.new(0.5, 0.5, 1.0, 1.0)
        tab.set_padding(12, 12, 12, 12)
        tab.add(frame)

        return tab

    def extras_tab(self, cbs):
        """Construct and layout the extras tab"""
        if not self.scrobbler.imported():
            self.config.as_enabled = False
        extraslabel = ui.label(markup='<b>' + _('Extras') + '</b>')
        frame = Gtk.Frame()
        frame.set_label_widget(extraslabel)
        frame.set_shadow_type(Gtk.ShadowType.NONE)

        as_checkbox = Gtk.CheckButton(_("_Audioscrobbling (Last.fm)"))
        as_checkbox.set_active(self.config.as_enabled)
        as_user_label = ui.label(textmn=_("_Username:"))
        as_pass_label = ui.label(textmn=_("_Password:"))
        as_user_entry = ui.entry(text=self.config.as_username,
            changed_cb=self._as_username_changed)
        as_user_label.set_mnemonic_widget(as_user_entry)
        if len(self.config.as_password_md5) > 0:
            as_pass_entry = ui.entry(text='1234', password=True,
                changed_cb=self._as_password_changed)
        else:
            as_pass_entry = ui.entry(text='', password=True,
                changed_cb=self._as_password_changed)
        as_pass_label.set_mnemonic_widget(as_pass_entry)
        as_user_box = Gtk.HBox(spacing=12)
        as_user_box.pack_end(as_user_entry, False, False, 0)
        as_user_box.pack_end(as_user_label, False, False, 0)
        as_pass_box = Gtk.HBox(spacing=12)
        as_pass_box.pack_end(as_pass_entry, False, False, 0)
        as_pass_box.pack_end(as_pass_label, False, False, 0)
        as_entries = Gtk.VBox()
        as_entries.pack_start(as_user_box, True, True, 0)
        as_entries.pack_start(as_pass_box, True, True, 0)
        display_notification = Gtk.CheckButton(_("Popup _notification on song changes"))
        display_notification.set_active(self.config.show_notification)

        time_names = ["%s %s" %
            (i , gettext.ngettext('second', 'seconds', int(i)))
            for i in cbs.popuptimes if i != _('Entire song')]
        time_names.append(_('Entire song'))
        notification_options = ui.combo(items=time_names,
            active=self.config.popup_option,
            changed_cb=self._notiftime_changed)
        notification_locs = ui.combo(items=cbs.popuplocations,
            active=self.config.traytips_notifications_location,
            changed_cb=self._notiflocation_changed)
        notifhbox = Gtk.HBox(spacing=6)
        notifhbox.pack_end(notification_locs, False, False, 0)
        notifhbox.pack_end(notification_options, False, False, 0)
        display_notification.connect('toggled', cbs.notif_toggled,
            notifhbox)
        if not self.config.show_notification:
            notifhbox.set_sensitive(False)
        crossfadespin = Gtk.SpinButton()
        crossfadespin.set_range(1, 30)
        crossfadespin.set_value(self.config.xfade)
        crossfadespin.set_numeric(True)
        crossfadespin.set_increments(1, 5)
        crossfadespin.connect('value-changed', cbs.crossfade_changed)
        crossfadelabel2 = ui.label(textmn=_("_Fade length:"))
        crossfadelabel2.set_mnemonic_widget(crossfadespin)
        crossfadelabel3 = ui.label(text=_("sec"))
        crossfadebox = Gtk.HBox(spacing=12)
        crossfadebox.pack_end(crossfadelabel3, False, False, 0)
        crossfadebox.pack_end(crossfadespin, False, False, 0)
        crossfadebox.pack_end(crossfadelabel2, False, False, 0)
        crossfadecheck = Gtk.CheckButton(_("C_rossfade"))
        crossfadecheck.connect('toggled',
            self._crossfadecheck_toggled, crossfadespin,
            crossfadelabel2, crossfadelabel3)
        crossfadecheck.connect('toggled', cbs.crossfade_toggled,
            crossfadespin)
        crossfadecheck.set_active(self.config.xfade_enabled)
        crossfadecheck.toggled() # Force the toggled callback

        widgets = (as_checkbox, as_entries, display_notification,
            notifhbox, crossfadecheck, crossfadebox)
        table = Gtk.Table(len(widgets), 1)
        table.set_col_spacings(12)
        table.set_row_spacings(6)
        for i, widget in enumerate(widgets):
            table.attach(widget, 0, 1, i, i+1,
                Gtk.AttachOptions.FILL|Gtk.AttachOptions.EXPAND, Gtk.AttachOptions.FILL)
        alignment = Gtk.Alignment.new(0.5, 0.5, 1.0, 1.0)
        alignment.set_padding(12, 0, 12, 0)
        alignment.add(table)
        frame.add(alignment)
        tab = Gtk.Alignment.new(0.5, 0.5, 1.0, 1.0)
        tab.set_padding(12, 12, 12, 12)
        tab.add(frame)

        as_checkbox.connect('toggled', self._as_enabled_toggled,
            as_user_entry, as_pass_entry, as_user_label,
            as_pass_label)
        if not self.config.as_enabled or not self.scrobbler.imported():
            for widget in (as_user_entry, as_pass_entry,
                    as_user_label, as_pass_label):
                widget.set_sensitive(False)
        return tab

    def display_tab(self, cbs):
        """Construct and layout the display tab"""
        displaylabel = ui.label(markup='<b>' + _('Display') + '</b>')
        frame = Gtk.Frame()
        frame.set_label_widget(displaylabel)
        frame.set_shadow_type(Gtk.ShadowType.NONE)

        art = Gtk.CheckButton(_("_Album art"))
        art.set_active(self.config.show_covers)
        stylized_combo = ui.combo(items=[_("Standard"),
            _("Stylized")], active=self.config.covers_type,
            changed_cb=cbs.stylized_toggled)
        stylized_hbox = Gtk.HBox(spacing=12)
        stylized_hbox.pack_end(stylized_combo, False, False, 0)
        stylized_hbox.pack_end(ui.label(
            text=_("Artwork style:")), False, False, 0)
        stylized_hbox.set_sensitive(self.config.show_covers)
        art_combo = ui.combo(items=[_("Local only"),
            _("Local and remote")], active=self.config.covers_pref)
        art_combo.connect('changed',
            self._config_widget_active, 'covers_pref')
        orderart_label = ui.label(text=_("Search locations:"))
        art_hbox = Gtk.HBox(spacing=12)
        art_hbox.pack_end(art_combo, False, False, 0)
        art_hbox.pack_end(orderart_label, False, False, 0)
        art_hbox.set_sensitive(self.config.show_covers)

        art_paths = ["~/.covers/"]
        art_paths += ("%s/%s" % (_("SONG_DIR"), item)
            for item in ("cover.jpg", "album.jpg", "folder.jpg",
                self.config.art_location_custom_filename or _("custom")))
        art_location = ui.combo(items=art_paths,
            active=self.config.art_location,
            changed_cb=self._art_location_changed)

        art_location_hbox = Gtk.HBox(spacing=12)
        art_location_hbox.pack_end(art_location, False, False, 0)
        art_location_hbox.pack_end(ui.label(text=_("Save art to:")),
            False, False, 0)
        art_location_hbox.set_sensitive(self.config.show_covers)
        art.connect('toggled', cbs.art_toggled, art_hbox,
            art_location_hbox, stylized_hbox)
        playback = Gtk.CheckButton(_("_Playback/volume buttons"))
        playback.set_active(self.config.show_playback)
        playback.connect('toggled', cbs.playback_toggled)
        progress = Gtk.CheckButton(_("Pr_ogressbar"))
        progress.set_active(self.config.show_progress)
        progress.connect('toggled', cbs.progress_toggled)
        statusbar = Gtk.CheckButton(_("_Statusbar"))
        statusbar.set_active(self.config.show_statusbar)
        statusbar.connect('toggled', cbs.statusbar_toggled)
        lyrics = Gtk.CheckButton(_("Song Ly_rics"))
        lyrics.set_active(self.config.show_lyrics)
        savelyrics_label = ui.label(text=_("Save lyrics to:"), x=1)
        lyrics_location = ui.combo(
            items=["~/.lyrics/", _("SONG_DIR") + "/"],
            active=self.config.lyrics_location,
            changed_cb=self._lyrics_location_changed)
        lyrics_location_hbox = Gtk.HBox(spacing=12)
        lyrics_location_hbox.pack_end(lyrics_location, False, False, 0)
        lyrics_location_hbox.pack_end(savelyrics_label, False, False, 0)
        lyrics_location_hbox.set_sensitive(self.config.show_lyrics)
        lyrics.connect('toggled', cbs.lyrics_toggled,
            lyrics_location_hbox)
        trayicon = Gtk.CheckButton(_("System _tray icon"))
        self.display_trayicon = trayicon
        trayicon.set_active(self.config.show_trayicon)
        trayicon.set_sensitive(cbs.trayicon_available)

        widgets = (playback, progress, statusbar, trayicon, lyrics,
               lyrics_location_hbox, art, stylized_hbox, art_hbox,
               art_location_hbox)
        table = Gtk.Table(len(widgets), 1, False)
        for i, widget in enumerate(widgets):
            table.attach(widget, 0, 1, i, i+1, Gtk.AttachOptions.FILL|Gtk.AttachOptions.EXPAND,
                Gtk.AttachOptions.FILL)
        alignment = Gtk.Alignment.new(0.5, 0.5, 1.0, 1.0)
        alignment.set_padding(12, 0, 12, 0)
        alignment.add(table)
        frame.add(alignment)
        tab = Gtk.Alignment.new(0.5, 0.5, 1.0, 1.0)
        tab.set_padding(12, 12, 12, 12)
        tab.add(frame)

        return tab

    def behavior_tab(self, cbs):
        """Construct and layout the behavior tab"""
        windowlabel = ui.label(markup='<b>'+_('Window Behavior')+'</b>')
        frame = Gtk.Frame()
        frame.set_label_widget(windowlabel)
        frame.set_shadow_type(Gtk.ShadowType.NONE)
        sticky = Gtk.CheckButton(_("_Show window on all workspaces"))
        sticky.set_active(self.config.sticky)
        sticky.connect('toggled', cbs.sticky_toggled)
        ontop = Gtk.CheckButton(_("_Keep window above other windows"))
        ontop.set_active(self.config.ontop)
        ontop.connect('toggled', cbs.ontop_toggled)
        decor = Gtk.CheckButton(_("_Hide window titlebar"))
        decor.set_active(not self.config.decorated)
        decor.connect('toggled', cbs.decorated_toggled, self.prefswindow)
        minimize = Gtk.CheckButton(_("_Minimize to system tray on close/escape"))
        minimize.set_active(self.config.minimize_to_systray)
        minimize.set_tooltip_text(_("If enabled, closing Sonata will minimize it to the system tray. Note that it's currently impossible to detect if there actually is a system tray, so only check this if you have one."))
        minimize.connect('toggled', self._config_widget_active,
            'minimize_to_systray')
        self.display_trayicon.connect('toggled', cbs.trayicon_toggled,
            minimize)
        minimize.set_sensitive(cbs.trayicon_in_use)
        widgets = (sticky, ontop, decor, minimize)
        table = Gtk.Table(len(widgets), 1)
        for i, widget in enumerate(widgets):
            table.attach(widget, 0, 1, i, i+1,
                Gtk.AttachOptions.FILL|Gtk.AttachOptions.EXPAND, Gtk.AttachOptions.FILL)
        alignment = Gtk.Alignment.new(0, 0, 0, 0)
        alignment.set_padding(12, 0, 12, 0)
        alignment.add(table)
        frame.add(alignment)

        misclabel = ui.label(markup='<b>' + _('Miscellaneous') + '</b>')
        misc_frame = Gtk.Frame()
        misc_frame.set_label_widget(misclabel)
        misc_frame.set_shadow_type(Gtk.ShadowType.NONE)
        update_start = Gtk.CheckButton(_("_Update MPD library on start"))
        update_start.set_active(self.config.update_on_start)
        update_start.set_tooltip_text(_("If enabled, Sonata will automatically update your MPD library when it starts up."))
        update_start.connect('toggled', self._config_widget_active,
            'update_on_start')
        exit_stop = Gtk.CheckButton(_("S_top playback on exit"))
        exit_stop.set_active(self.config.stop_on_exit)
        exit_stop.set_tooltip_text(_("MPD allows playback even when the client is not open. If enabled, Sonata will behave like a more conventional music player and, instead, stop playback upon exit."))
        exit_stop.connect('toggled', self._config_widget_active,
            'stop_on_exit')
        infofile_usage = Gtk.CheckButton(_("_Write status file:"))
        infofile_usage.set_active(self.config.use_infofile)
        infofile_usage.set_tooltip_text(_("If enabled, Sonata will create a xmms-infopipe like file containing information about the current song. Many applications support the xmms-info file (Instant Messengers, IRC Clients...)"))
        infopath_options = ui.entry(text=self.config.infofile_path)
        infopath_options.set_tooltip_text(_("If enabled, Sonata will create a xmms-infopipe like file containing information about the current song. Many applications support the xmms-info file (Instant Messengers, IRC Clients...)"))
        infopath_options.connect('focus_out_event',
                    cbs.infofile_changed)
        infopath_options.connect('activate', cbs.infofile_changed, None)
        if not self.config.use_infofile:
            infopath_options.set_sensitive(False)
        infofile_usage.connect('toggled', self._infofile_toggled,
            infopath_options)
        infofilebox = Gtk.HBox(spacing=6)
        infofilebox.pack_start(infofile_usage, False, False, 0)
        infofilebox.pack_start(infopath_options, True, True, 0)
        widgets = (update_start, exit_stop, infofilebox)
        misc_table = Gtk.Table(len(widgets), 1)
        for i, widget in enumerate(widgets):
            misc_table.attach(widget, 0, 1, i, i+1,
                Gtk.AttachOptions.FILL|Gtk.AttachOptions.EXPAND, Gtk.AttachOptions.FILL)
        misc_alignment = Gtk.Alignment.new(0, 0, 0, 0)
        misc_alignment.set_padding(12, 0, 12, 0)
        misc_alignment.add(misc_table)
        misc_frame.add(misc_alignment)

        table = Gtk.Table(2, 1)
        table.set_row_spacings(12)
        table.attach(frame, 0, 1, 0, 1,
            Gtk.AttachOptions.FILL|Gtk.AttachOptions.EXPAND, Gtk.AttachOptions.FILL)
        table.attach(misc_frame, 0, 1, 1, 2,
            Gtk.AttachOptions.FILL|Gtk.AttachOptions.EXPAND, Gtk.AttachOptions.FILL)
        tab = Gtk.Alignment.new(0, 0, 0, 0)
        tab.set_padding(12, 12, 12, 12)
        tab.add(table)
        return tab

    def format_tab(self, cbs):
        """Construct and layout the format tab"""
        formatlabel = ui.label(markup='<b>'+_('Song Formatting')+'</b>')
        frame = Gtk.Frame()
        frame.set_label_widget(formatlabel)
        frame.set_shadow_type(Gtk.ShadowType.NONE)

        rows = [(_("C_urrent playlist:"), self.config.currentformat),
            (_("_Library:"), self.config.libraryformat),
            (_("_Window title:"), self.config.titleformat),
            (_("Current _song line 1:"),
                self.config.currsongformat1),
            (_("Current s_ong line 2:"),
                self.config.currsongformat2)]

        labels = []
        entries = []
        for label_text, entry_text in rows:
            label = ui.label(textmn=label_text)
            entry = ui.entry(text=entry_text)

            label.set_mnemonic_widget(entry)

            labels.append(label)
            entries.append(entry)

        entry_cbs = (cbs.currentoptions_changed,
                 cbs.libraryoptions_changed,
                 cbs.titleoptions_changed,
                 cbs.currsongoptions1_changed,
                 cbs.currsongoptions2_changed)
        for entry, cb, next in zip(entries, entry_cbs,
                entries[1:] + entries[:1]):
            entry.connect('focus_out_event', cb)
            entry.connect('activate', lambda _, n: n.grab_focus(),
                    next)

        availableheading = ui.label(markup='<small>' + _('Available options') + ':</small>')
        availablevbox = Gtk.VBox()
        availableformatbox = Gtk.HBox()
        formatcodes = formatting.formatcodes
        for codes in [formatcodes[:int((len(formatcodes)+1)/2)],
                  formatcodes[int((len(formatcodes)+1)/2):]]:
            rows = '\n'.join('<tt>%%%s</tt> - %s' %
                    (code.code, code.description)
                    for code in codes)
            markup = '<small>' + rows + '</small>'
            formattinghelp = ui.label(markup=markup)
            availableformatbox.pack_start(formattinghelp, True, True, 0)

        availablevbox.pack_start(availableformatbox, False, False, 0)
        additionalinfo = ui.label(markup='<small><tt>{ }</tt> - ' + _('Info displayed only if all enclosed tags are defined') + '\n<tt>|</tt> - ' + _('Creates columns in the current playlist') + '</small>')
        availablevbox.pack_start(additionalinfo, False, False, 4)

        num_rows = len(rows) + 2
        table = Gtk.Table(num_rows, 2)
        table.set_col_spacings(12)
        label_entries = enumerate(zip(labels, entries))
        for i, (label, entry) in label_entries:
            table.attach(label, 0, 1, i, i+1, Gtk.AttachOptions.FILL)
            table.attach(entry, 1, 2, i, i+1)
        table.attach(availableheading, 0, 2, num_rows-2,
            num_rows-1, Gtk.AttachOptions.FILL|Gtk.AttachOptions.EXPAND, Gtk.AttachOptions.FILL|Gtk.AttachOptions.EXPAND,
            0, 6)
        table.attach(availablevbox, 0, 2, num_rows-1, num_rows)
        alignment = Gtk.Alignment.new(0.5, 0.5, 1.0, 1.0)
        alignment.set_padding(12, 0, 12, 0)
        alignment.add(table)
        frame.add(alignment)
        tab = Gtk.Alignment.new(0.5, 0.5, 1.0, 1.0)
        tab.set_padding(12, 12, 12, 12)
        tab.add(frame)
        return tab

    def plugins_tab(self, cbs=None):
        """Construct and layout the plugins tab"""
        plugin_actions = (
            ('plugin_about', Gtk.STOCK_ABOUT, _('_About'), None,
                None, self.plugin_about),
            ('plugin_configure', Gtk.STOCK_PREFERENCES,
                _('_Configure...'), None, None,
                self.plugin_configure))

        uiDescription = """
            <ui>
              <popup name="pluginmenu">
                <menuitem action="plugin_configure"/>
                <menuitem action="plugin_about"/>
              </popup>
            </ui>
            """

        self.plugin_UIManager = Gtk.UIManager()
        actionGroup = Gtk.ActionGroup('PluginActions')
        actionGroup.add_actions(plugin_actions)
        self.plugin_UIManager.insert_action_group(actionGroup, 0)
        self.plugin_UIManager.add_ui_from_string(uiDescription)

        self.pluginview = ui.treeview()
        self.pluginview.set_headers_visible(True)
        self.pluginselection = self.pluginview.get_selection()
        self.pluginselection.set_mode(Gtk.SelectionMode.SINGLE)
        self.pluginview.set_rules_hint(True)
        self.pluginview.set_property('can-focus', False)
        pluginwindow = ui.scrollwindow(add=self.pluginview)
        plugindata = Gtk.ListStore(bool, GdkPixbuf.Pixbuf, str)
        self.pluginview.set_model(plugindata)
        self.pluginview.connect('button-press-event', self.plugin_click)

        plugincheckcell = Gtk.CellRendererToggle()
        plugincheckcell.set_property('activatable', True)
        plugincheckcell.connect('toggled', self.plugin_toggled,
            (plugindata, 0))
        pluginpixbufcell = Gtk.CellRendererPixbuf()
        plugintextcell = Gtk.CellRendererText()

        plugincol0 = Gtk.TreeViewColumn()
        self.pluginview.append_column(plugincol0)
        plugincol0.pack_start(plugincheckcell, True)
        plugincol0.add_attribute(plugincheckcell, 'active', 0)
        plugincol0.set_title(_("Enabled"))

        plugincol1 = Gtk.TreeViewColumn()
        plugincol1.set_properties(
            max_width=0, # will expand to fill view and not more
            spacing=10) # space between icon and text
        self.pluginview.append_column(plugincol1)
        plugincol1.pack_start(pluginpixbufcell, False)
        plugincol1.pack_start(plugintextcell, True)
        plugincol1.add_attribute(pluginpixbufcell, 'pixbuf', 1)
        plugincol1.add_attribute(plugintextcell, 'markup', 2)
        plugincol1.set_title(_("Description"))

        plugindata.clear()
        for plugin in pluginsystem.get_info():
            pb = self.plugin_get_icon_pixbuf(plugin)
            plugin_text = "<b>" + plugin.longname + "</b> " + plugin.version_string
            plugin_text += "\n" + plugin.description
            enabled = plugin.get_enabled()
            plugindata.append((enabled, pb, plugin_text))
        return pluginwindow

    def _window_response(self, window, response):
        if response == Gtk.ResponseType.CLOSE:
            self.last_tab = self.prefsnotebook.get_current_page()
            #XXX: These two are probably never triggered
            if self.config.show_lyrics and self.config.lyrics_location != consts.LYRICS_LOCATION_HOME:
                if not os.path.isdir(misc.file_from_utf8(self.config.musicdir[self.config.profile_num])):
                    ui.show_msg(self.window, _("To save lyrics to the music file's directory, you must specify a valid music directory."), _("Music Dir Verification"), 'musicdirVerificationError', Gtk.ButtonsType.CLOSE)
                    # Set music_dir entry focused:
                    self.prefsnotebook.set_current_page(0)
                    self.direntry.grab_focus()
                    return
            if self.config.show_covers and self.config.art_location != consts.ART_LOCATION_HOMECOVERS:
                if not os.path.isdir(misc.file_from_utf8(self.config.musicdir[self.config.profile_num])):
                    ui.show_msg(self.window, _("To save artwork to the music file's directory, you must specify a valid music directory."), _("Music Dir Verification"), 'musicdirVerificationError', Gtk.ButtonsType.CLOSE)
                    # Set music_dir entry focused:
                    self.prefsnotebook.set_current_page(0)
                    self.direntry.grab_focus()
                    return
            if not self.using_mpd_env_vars:
                if self.prev_host != self.config.host[self.config.profile_num] or self.prev_port != self.config.port[self.config.profile_num] or self.prev_password != self.config.password[self.config.profile_num]:
                    # Try to connect if mpd connection info has been updated:
                    ui.change_cursor(Gdk.Cursor.new(Gdk.CursorType.WATCH))
                    self.reconnect()
            self.settings_save()
            self.populate_profiles_for_menu()
            ui.change_cursor(None)
        window.destroy()

    def _config_widget_active(self, widget, member):
        """Sets a config attribute to the widget's active value"""
        setattr(self.config, member, widget.get_active())

    def _as_enabled_toggled(self, checkbox, *widgets):
        if checkbox.get_active():
            self.scrobbler.import_module(True)
        if self.scrobbler.imported():
            self.config.as_enabled = checkbox.get_active()
            self.scrobbler.init()
            for widget in widgets:
                widget.set_sensitive(self.config.as_enabled)
        elif checkbox.get_active():
            checkbox.set_active(False)

    def _as_username_changed(self, entry):
        if self.scrobbler.imported():
            self.config.as_username = entry.get_text()
            self.scrobbler.auth_changed()

    def _as_password_changed(self, entry):
        if self.scrobbler.imported():
            self.config.as_password_md5 = hashlib.md5(entry.get_text()).hexdigest()
            self.scrobbler.auth_changed()

    def _nameentry_changed(self, entry, profile_combo, remove_profiles):
        if not self.updating_nameentry:
            profile_num = profile_combo.get_active()
            self.config.profile_names[profile_num] = entry.get_text()
            self._populate_profile_combo(profile_combo, profile_num, remove_profiles)

    def _hostentry_changed(self, entry, profile_combo):
        profile_num = profile_combo.get_active()
        self.config.host[profile_num] = entry.get_text()

    def _portentry_changed(self, entry, profile_combo):
        profile_num = profile_combo.get_active()
        self.config.port[profile_num] = entry.get_value_as_int()

    def _passwordentry_changed(self, entry, profile_combo):
        profile_num = profile_combo.get_active()
        self.config.password[profile_num] = entry.get_text()

    def _direntry_changed(self, entry, profile_combo):
        profile_num = profile_combo.get_active()
        self.config.musicdir[profile_num] = misc.sanitize_musicdir(entry.get_filename())

    def _add_profile(self, _button, nameentry, profile_combo, remove_profiles):
        self.updating_nameentry = True
        profile_num = profile_combo.get_active()
        self.config.profile_names.append(_("New Profile"))
        nameentry.set_text(self.config.profile_names[-1])
        self.updating_nameentry = False
        self.config.host.append(self.config.host[profile_num])
        self.config.port.append(self.config.port[profile_num])
        self.config.password.append(self.config.password[profile_num])
        self.config.musicdir.append(self.config.musicdir[profile_num])
        self._populate_profile_combo(profile_combo, len(self.config.profile_names)-1, remove_profiles)

    def _remove_profile(self, _button, profile_combo, remove_profiles):
        profile_num = profile_combo.get_active()
        if profile_num == self.config.profile_num:
            # Profile deleted, revert to first profile:
            self.config.profile_num = 0
            self.reconnect(None)
        self.config.profile_names.pop(profile_num)
        self.config.host.pop(profile_num)
        self.config.port.pop(profile_num)
        self.config.password.pop(profile_num)
        self.config.musicdir.pop(profile_num)
        if profile_num > 0:
            self._populate_profile_combo(profile_combo, profile_num-1, remove_profiles)
        else:
            self._populate_profile_combo(profile_combo, 0, remove_profiles)

    def _profile_chosen(self, profile_combo, nameentry, hostentry, portentry, passwordentry, direntry):
        profile_num = profile_combo.get_active()
        self.updating_nameentry = True
        nameentry.set_text(str(self.config.profile_names[profile_num]))
        self.updating_nameentry = False
        hostentry.set_text(str(self.config.host[profile_num]))
        portentry.set_value(self.config.port[profile_num])
        passwordentry.set_text(str(self.config.password[profile_num]))
        direntry.set_current_folder(misc.sanitize_musicdir(self.config.musicdir[profile_num]))

    def _populate_profile_combo(self, profile_combo, active_index, remove_profiles):
        new_model = Gtk.ListStore(str)
        new_model.clear()
        profile_combo.set_model(new_model)
        for i, profile_name in enumerate(self.config.profile_names):
            combo_text = "[%s] %s" % (i+1, profile_name[:15])
            if len(profile_name) > 15:
                combo_text += "..."
            profile_combo.append_text(combo_text)
        profile_combo.set_active(active_index)
        # Enable remove button if there is more than one profile
        remove_profiles.set_sensitive(len(self.config.profile_names) > 1)

    def _lyrics_location_changed(self, combobox):
        self.config.lyrics_location = combobox.get_active()

    def _art_location_changed(self, combobox):
        if combobox.get_active() == consts.ART_LOCATION_CUSTOM:
            # Prompt user for playlist name:
            dialog = ui.dialog(title=_("Custom Artwork"), parent=self.window, flags=Gtk.DialogFlags.MODAL | Gtk.DialogFlags.DESTROY_WITH_PARENT, buttons=(Gtk.STOCK_CANCEL, Gtk.ResponseType.REJECT, Gtk.STOCK_OK, Gtk.ResponseType.ACCEPT), role='customArtwork', default=Gtk.ResponseType.ACCEPT)
            hbox = Gtk.HBox()
            hbox.pack_start(ui.label(text=_('Artwork filename:')), False, False, 5)
            entry = ui.entry(self.config.art_location_custom_filename)
            entry.set_activates_default(True)
            hbox.pack_start(entry, True, True, 5)
            dialog.vbox.pack_start(hbox, True, True, 0)
            dialog.vbox.show_all()
            response = dialog.run()
            if response == Gtk.ResponseType.ACCEPT:
                self.config.art_location_custom_filename = entry.get_text().replace("/", "")
                iter = combobox.get_active_iter()
                model = combobox.get_model()
                model.set(iter, 0, "SONG_DIR/" + (self.config.art_location_custom_filename or _("custom")))
            else:
                # Revert to non-custom item in combobox:
                combobox.set_active(self.config.art_location)
            dialog.destroy()
        self.config.art_location = combobox.get_active()

    def _crossfadecheck_toggled(self, button, *widgets):
        button_active = button.get_active()
        for widget in widgets:
            widget.set_sensitive(button_active)

    def _notiflocation_changed(self, combobox):
        self.config.traytips_notifications_location = combobox.get_active()
        self.renotify()

    def _notiftime_changed(self, combobox):
        self.config.popup_option = combobox.get_active()
        self.renotify()

    def _infofile_toggled(self, button, infofileformatbox):
        self.config.use_infofile = button.get_active()
        infofileformatbox.set_sensitive(self.config.use_infofile)
        if self.config.use_infofile:
            self.reinfofile()

    def plugin_click(self, _widget, event):
        if event.button == 3:
            self.plugin_UIManager.get_widget('/pluginmenu').popup(None, None, None, None, event.button, event.time)

    def plugin_toggled(self, _renderer, path, user_data):
        model, column = user_data
        enabled = not model[path][column]
        plugin = pluginsystem.get_info()[int(path)]
        pluginsystem.set_enabled(plugin, enabled)

        if enabled:
            # test that the plugin loads or already was loaded
            if not plugin.force_loaded():
                enabled = False
                pluginsystem.set_enabled(plugin, enabled)

        model[path][column] = enabled

    def plugin_about(self, _widget):
        plugin = self.plugin_get_selected()
        iconpb = self.plugin_get_icon_pixbuf(plugin)

        about_text = plugin.longname + "\n" + plugin.author + "\n"
        if len(plugin.author_email) > 0:
            about_text += "<" + plugin.author_email + ">"

        self.about_dialog = Gtk.AboutDialog()
        self.about_dialog.set_name(plugin.longname)
        self.about_dialog.set_role('about')
        self.about_dialog.set_version(plugin.version_string)
        if len(plugin.description.strip()) > 0:
            self.about_dialog.set_comments(plugin.description)
        if len(plugin.author.strip()) > 0:
            author = plugin.author
            if len(plugin.author.strip()) > 0:
                author += ' <' + plugin.author_email + '>'
            self.about_dialog.set_authors([author])
        if len(plugin.url.strip()) > 0:
            self.about_dialog.connect("activate-link", self.plugin_show_website)
            self.about_dialog.set_website(plugin.url)
        self.about_dialog.set_logo(iconpb)

        self.about_dialog.connect('response', self.plugin_about_close)
        self.about_dialog.connect('delete_event', self.plugin_about_close)
        self.about_dialog.show_all()

    def plugin_about_close(self, _event, _data=None):
        self.about_dialog.hide()
        return True

    def plugin_show_website(self, _dialog, link):
        return misc.browser_load(link, self.config.url_browser, \
                                 self.window)

    def plugin_configure(self, _widget):
        plugin = self.plugin_get_selected()
        ui.show_msg(self.prefswindow, "Nothing yet implemented.", "Configure", "pluginConfigure", Gtk.ButtonsType.CLOSE)

    def plugin_get_selected(self):
        model, i = self.pluginselection.get_selected()
        plugin_num = model.get_path(i).get_indices()[0]
        return pluginsystem.get_info()[plugin_num]

    def plugin_get_icon_pixbuf(self, plugin):
        pb = plugin.iconurl
        try:
            pb = GdkPixbuf.Pixbuf.new_from_file(pb)
        except:
            pb = self.pluginview.render_icon(Gtk.STOCK_EXECUTE, Gtk.IconSize.LARGE_TOOLBAR)
        return pb
