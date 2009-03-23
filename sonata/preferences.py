
"""
This module provides a user interface for changing configuration
variables.

Example usage:
import preferences
...
prefs = preferences.Preferences()
prefs.on_prefs_real(self.window, ...a huge list of callbacks..., self.prefs_window_response)
"""

import gettext, hashlib

import gtk

from consts import consts
from config import Config
from pluginsystem import pluginsystem
import ui
import misc

class Preferences():
    """This class implements a preferences dialog for changing
    configuration variables.

    Many changes are applied instantly with respective
    callbacks. Closing the dialog causes a response callback.
    """
    def __init__(self, config):

        self.config = config

        # Constants:
        self.popuplocations = [_('System tray'), _('Top Left'), _('Top Right'), _('Bottom Left'), _('Bottom Right'), _('Screen Center')]

        # These are callbacks to Main
        self.reconnect = None
        self.renotify = None
        self.reinfofile = None

        # Temporary flag:
        self.updating_nameentry = False

        self.prev_host = None
        self.prev_password = None
        self.prev_port = None

        self.window = None

    def on_prefs_real(self, parent_window, popuptimes, scrobbler, trayicon_available, trayicon_in_use, reconnect, renotify, reinfofile, prefs_notif_toggled, prefs_stylized_toggled, prefs_art_toggled, prefs_playback_toggled, prefs_progress_toggled, prefs_statusbar_toggled, prefs_lyrics_toggled, prefs_trayicon_toggled, prefs_crossfade_toggled, prefs_crossfade_changed, prefs_window_response, prefs_last_tab):
        """Display the preferences dialog"""
        self.window = parent_window
        self.scrobbler = scrobbler
        self.reconnect = reconnect
        self.renotify = renotify
        self.reinfofile = reinfofile
        self.last_tab = prefs_last_tab

        self.prefswindow = ui.dialog(title=_("Preferences"), parent=self.window, flags=gtk.DIALOG_DESTROY_WITH_PARENT, role='preferences', resizable=False, separator=False)
        hbox = gtk.HBox()
        prefsnotebook = gtk.Notebook()
        # MPD tab
        mpdlabel = ui.label(markup='<b>' + _('MPD Connection') + '</b>', y=1)
        mpd_frame = gtk.Frame()
        mpd_frame.set_label_widget(mpdlabel)
        mpd_frame.set_shadow_type(gtk.SHADOW_NONE)
        controlbox = gtk.HBox()
        profiles = ui.combo()
        add_profile = ui.button(img=ui.image(stock=gtk.STOCK_ADD))
        remove_profile = ui.button(img=ui.image(stock=gtk.STOCK_REMOVE))
        self.prefs_populate_profile_combo(profiles, self.config.profile_num, remove_profile)
        controlbox.pack_start(profiles, False, False, 2)
        controlbox.pack_start(remove_profile, False, False, 2)
        controlbox.pack_start(add_profile, False, False, 2)
        namelabel = ui.label(textmn=_("_Name") + ":")
        nameentry = ui.entry()
        namelabel.set_mnemonic_widget(nameentry)
        hostlabel = ui.label(textmn=_("_Host") + ":")
        hostentry = ui.entry()
        hostlabel.set_mnemonic_widget(hostentry)
        portlabel = ui.label(textmn=_("_Port") + ":")
        portentry = gtk.SpinButton(gtk.Adjustment(0 ,0 ,65535, 1),1)
        portentry.set_numeric(True)
        portlabel.set_mnemonic_widget(portentry)
        dirlabel = ui.label(textmn=_("_Music dir") + ":")
        direntry = gtk.FileChooserButton(_('Select a Music Directory'))
        direntry.set_action(gtk.FILE_CHOOSER_ACTION_SELECT_FOLDER)
        direntry.connect('selection-changed', self.prefs_direntry_changed, profiles)
        dirlabel.set_mnemonic_widget(direntry)
        passwordlabel = ui.label(textmn=_("Pa_ssword") + ":")
        passwordentry = ui.entry(password=True)
        passwordlabel.set_mnemonic_widget(passwordentry)
        passwordentry.set_tooltip_text(_("Leave blank if no password is required."))
        autoconnect = gtk.CheckButton(_("_Autoconnect on start"))
        autoconnect.set_active(self.config.autoconnect)
        autoconnect.connect('toggled', self.prefs_config_widget_active, 'autoconnect')
        # Fill in entries with current profile:
        self.prefs_profile_chosen(profiles, nameentry, hostentry, portentry, passwordentry, direntry)
        # Update display if $MPD_HOST or $MPD_PORT is set:
        host, port, password = misc.mpd_env_vars()
        if host or port:
            using_mpd_env_vars = True
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
            for widget in [hostentry, portentry, passwordentry, nameentry, profiles, add_profile, remove_profile]:
                widget.set_sensitive(False)
        else:
            using_mpd_env_vars = False
            nameentry.connect('changed', self.prefs_nameentry_changed, profiles, remove_profile)
            hostentry.connect('changed', self.prefs_hostentry_changed, profiles)
            portentry.connect('value-changed', self.prefs_portentry_changed, profiles)
            passwordentry.connect('changed', self.prefs_passwordentry_changed, profiles)
            profiles.connect('changed', self.prefs_profile_chosen, nameentry, hostentry, portentry, passwordentry, direntry)
            add_profile.connect('clicked', self.prefs_add_profile, nameentry, profiles, remove_profile)
            remove_profile.connect('clicked', self.prefs_remove_profile, profiles, remove_profile)

        rows = [(namelabel, nameentry),
            (hostlabel, hostentry),
            (portlabel, portentry),
            (passwordlabel, passwordentry),
            (dirlabel, direntry)]

        connection_table = gtk.Table(len(rows), 2)
        connection_table.set_col_spacings(12)
        for i, (label, entry) in enumerate(rows):
            connection_table.attach(label, 0, 1, i, i+1, gtk.FILL,
                gtk.FILL)
            connection_table.attach(entry, 1, 2, i, i+1,
                gtk.FILL|gtk.EXPAND, gtk.FILL)

        connection_alignment = gtk.Alignment(0.5, 0.5, 1.0, 1.0)
        connection_alignment.set_padding(12, 12, 12, 12)
        connection_alignment.add(connection_table)
        connection_frame = gtk.Frame()
        connection_frame.set_label_widget(controlbox)
        connection_frame.add(connection_alignment)
        mpd_table = gtk.Table(2, 1)
        mpd_table.set_row_spacings(12)
        mpd_table.attach(connection_frame, 0, 1, 0, 1,
            gtk.FILL|gtk.EXPAND, gtk.FILL)
        mpd_table.attach(autoconnect, 0, 1, 1, 2, gtk.FILL|gtk.EXPAND,
            gtk.FILL)
        mpd_alignment = gtk.Alignment(0.5, 0.5, 1.0, 1.0)
        mpd_alignment.set_padding(12, 0, 12, 0)
        mpd_alignment.add(mpd_table)
        mpd_frame.add(mpd_alignment)
        mpd_tab = gtk.Alignment(0.5, 0.5, 1.0, 1.0)
        mpd_tab.set_padding(12, 12, 12, 12)
        mpd_tab.add(mpd_frame)

        # Extras tab
        if not self.scrobbler.imported():
            self.config.as_enabled = False
        as_label = ui.label(markup='<b>' + _('Extras') + '</b>')
        extras_frame = gtk.Frame()
        extras_frame.set_label_widget(as_label)
        extras_frame.set_shadow_type(gtk.SHADOW_NONE)

        as_checkbox = gtk.CheckButton(_("Enable _Audioscrobbling (Last.fm)"))
        as_checkbox.set_active(self.config.as_enabled)
        as_user_label = ui.label(textmn=_("_Username:"))
        as_pass_label = ui.label(textmn=_("_Password:"))
        as_user_entry = ui.entry(text=self.config.as_username, changed_cb=self.prefs_as_username_changed)
        as_user_label.set_mnemonic_widget(as_user_entry)
        if len(self.config.as_password_md5) > 0:
            as_pass_entry = ui.entry(text='1234', password=True, changed_cb=self.prefs_as_password_changed)
        else:
            as_pass_entry = ui.entry(text='', password=True, changed_cb=self.prefs_as_password_changed)
        as_pass_label.set_mnemonic_widget(as_pass_entry)
        as_user_box = gtk.HBox(spacing=12)
        as_user_box.pack_end(as_user_entry, False, False)
        as_user_box.pack_end(as_user_label, False, False)
        as_pass_box = gtk.HBox(spacing=12)
        as_pass_box.pack_end(as_pass_entry, False, False)
        as_pass_box.pack_end(as_pass_label, False, False)
        as_entries = gtk.VBox()
        as_entries.pack_start(as_user_box)
        as_entries.pack_start(as_pass_box)
        display_notification = gtk.CheckButton(_("Popup _notification on song changes"))
        display_notification.set_active(self.config.show_notification)

        time_names = ["%s %s" %
            (i , gettext.ngettext('second', 'seconds', int(i)))
            for i in popuptimes if i != _('Entire song')]
        time_names.append(_('Entire song'))
        notification_options = ui.combo(items=time_names, active=self.config.popup_option, changed_cb=self.prefs_notiftime_changed)

        notification_locs = ui.combo(items=self.popuplocations, active=self.config.traytips_notifications_location, changed_cb=self.prefs_notiflocation_changed)
        notifhbox = gtk.HBox(spacing=6)
        notifhbox.pack_end(notification_locs, False, False)
        notifhbox.pack_end(notification_options, False, False)
        display_notification.connect('toggled', prefs_notif_toggled, notifhbox)
        if not self.config.show_notification:
            notifhbox.set_sensitive(False)
        crossfadespin = gtk.SpinButton()
        crossfadespin.set_range(1, 30)
        crossfadespin.set_value(self.config.xfade)
        crossfadespin.set_numeric(True)
        crossfadespin.set_increments(1, 5)
        crossfadespin.connect('value-changed', prefs_crossfade_changed)
        crossfadelabel2 = ui.label(text=_("Fade length") + ":")
        crossfadelabel2 = ui.label(textmn=_("_Fade length") + ":")
        crossfadelabel2.set_mnemonic_widget(crossfadespin)
        crossfadelabel3 = ui.label(text=_("sec"))
        crossfadebox = gtk.HBox(spacing=12)
        crossfadebox.pack_end(crossfadelabel3, False, False)
        crossfadebox.pack_end(crossfadespin, False, False)
        crossfadebox.pack_end(crossfadelabel2, False, False)
        crossfadecheck = gtk.CheckButton(_("Enable C_rossfade"))
        crossfadecheck.connect('toggled', self.prefs_crossfadecheck_toggled, crossfadespin, crossfadelabel2, crossfadelabel3)
        crossfadecheck.connect('toggled', prefs_crossfade_toggled, crossfadespin)
        crossfadecheck.set_active(self.config.xfade_enabled)
        crossfadecheck.toggled() # Force the toggled callback

        extras_widgets = (as_checkbox, as_entries, display_notification,
            notifhbox, crossfadecheck, crossfadebox)
        extras_table = gtk.Table(len(extras_widgets), 1)
        extras_table.set_col_spacings(12)
        extras_table.set_row_spacings(6)
        for i, widget in enumerate(extras_widgets):
            extras_table.attach(widget, 0, 1, i, i+1,
                gtk.FILL|gtk.EXPAND, gtk.FILL)
        extras_alignment = gtk.Alignment(0.5, 0.5, 1.0, 1.0)
        extras_alignment.set_padding(12, 0, 12, 0)
        extras_alignment.add(extras_table)
        extras_frame.add(extras_alignment)
        extras_tab = gtk.Alignment(0.5, 0.5, 1.0, 1.0)
        extras_tab.set_padding(12, 12, 12, 12)
        extras_tab.add(extras_frame)

        as_checkbox.connect('toggled', self.prefs_as_enabled_toggled, as_user_entry, as_pass_entry, as_user_label, as_pass_label)
        if not self.config.as_enabled or not self.scrobbler.imported():
            for widget in (as_user_entry, as_pass_entry,
                    as_user_label, as_pass_label):
                widget.set_sensitive(False)
        # Display tab
        displaylabel = ui.label(markup='<b>' + _('Display') + '</b>')
        display_frame = gtk.Frame()
        display_frame.set_label_widget(displaylabel)
        display_frame.set_shadow_type(gtk.SHADOW_NONE)

        display_art = gtk.CheckButton(_("Enable _album art"))
        display_art.set_active(self.config.show_covers)
        display_stylized_combo = ui.combo(items=[_("Standard"), _("Stylized")], active=self.config.covers_type, changed_cb=prefs_stylized_toggled)
        display_stylized_hbox = gtk.HBox(spacing=12)
        display_stylized_hbox.pack_end(display_stylized_combo, False, False)
        display_stylized_hbox.pack_end(ui.label(text=_("Artwork style:")), False, False)
        display_stylized_hbox.set_sensitive(self.config.show_covers)
        display_art_combo = ui.combo(items=[_("Local only"), _("Local and remote")], active=self.config.covers_pref)
        display_art_combo.connect('changed', self.prefs_config_widget_active, 'covers_pref')
        orderart_label = ui.label(text=_("Search locations:"))
        display_art_hbox = gtk.HBox(spacing=12)
        display_art_hbox.pack_end(display_art_combo, False, False)
        display_art_hbox.pack_end(orderart_label, False, False)
        display_art_hbox.set_sensitive(self.config.show_covers)

        art_paths = ["~/.covers/"]
        art_paths += ("../%s/%s" % (_("file_path"), item)
            for item in ("cover.jpg", "album.jpg", "folder.jpg",
                _("custom")))
        display_art_location = ui.combo(items=art_paths, active=self.config.art_location, changed_cb=self.prefs_art_location_changed)

        display_art_location_hbox = gtk.HBox(spacing=12)
        display_art_location_hbox.pack_end(display_art_location, False, False)
        display_art_location_hbox.pack_end(ui.label(text=_("Save art to:")), False, False)
        display_art_location_hbox.set_sensitive(self.config.show_covers)
        display_art.connect('toggled', prefs_art_toggled, display_art_hbox, display_art_location_hbox, display_stylized_hbox)
        display_playback = gtk.CheckButton(_("Enable _playback/volume buttons"))
        display_playback.set_active(self.config.show_playback)
        display_playback.connect('toggled', prefs_playback_toggled)
        display_progress = gtk.CheckButton(_("Enable pr_ogressbar"))
        display_progress.set_active(self.config.show_progress)
        display_progress.connect('toggled', prefs_progress_toggled)
        display_statusbar = gtk.CheckButton(_("Enable _statusbar"))
        display_statusbar.set_active(self.config.show_statusbar)
        display_statusbar.connect('toggled', prefs_statusbar_toggled)
        display_lyrics = gtk.CheckButton(_("Enable ly_rics"))
        display_lyrics.set_active(self.config.show_lyrics)
        savelyrics_label = ui.label(text=_("Save lyrics to:"), x=1)
        display_lyrics_location = ui.combo(items=["~/.lyrics/", "../" + _("file_path") + "/"], active=self.config.lyrics_location, changed_cb=self.prefs_lyrics_location_changed)
        display_lyrics_location_hbox = gtk.HBox(spacing=12)
        display_lyrics_location_hbox.pack_end(display_lyrics_location,
            False, False)
        display_lyrics_location_hbox.pack_end(savelyrics_label, False,
            False)
        display_lyrics_location_hbox.set_sensitive(self.config.show_lyrics)
        display_lyrics.connect('toggled', prefs_lyrics_toggled, display_lyrics_location_hbox)
        display_trayicon = gtk.CheckButton(_("Enable system _tray icon"))
        display_trayicon.set_active(self.config.show_trayicon)
        display_trayicon.set_sensitive(trayicon_available)

        display_widgets = (display_playback, display_progress,
            display_statusbar, display_trayicon, display_lyrics,
            display_lyrics_location_hbox, display_art,
            display_stylized_hbox, display_art_hbox,
            display_art_location_hbox)
        display_table = gtk.Table(len(display_widgets), 1, False)
        for i, widget in enumerate(display_widgets):
            display_table.attach(widget, 0, 1, i, i+1,
                gtk.FILL|gtk.EXPAND, gtk.FILL)
        display_alignment = gtk.Alignment(0.5, 0.5, 1.0, 1.0)
        display_alignment.set_padding(12, 0, 12, 0)
        display_alignment.add(display_table)
        display_frame.add(display_alignment)
        display_tab = gtk.Alignment(0.5, 0.5, 1.0, 1.0)
        display_tab.set_padding(12, 12, 12, 12)
        display_tab.add(display_frame)

        # Behavior tab
        windowlabel = ui.label(markup='<b>'+_('Window Behavior')+'</b>')
        window_frame = gtk.Frame()
        window_frame.set_label_widget(windowlabel)
        window_frame.set_shadow_type(gtk.SHADOW_NONE)
        win_sticky = gtk.CheckButton(_("_Show window on all workspaces"))
        win_sticky.set_active(self.config.sticky)
        win_sticky.connect('toggled', self.prefs_config_widget_active, 'sticky')
        win_ontop = gtk.CheckButton(_("_Keep window above other windows"))
        win_ontop.set_active(self.config.ontop)
        win_ontop.connect('toggled', self.prefs_config_widget_active, 'ontop')
        win_decor = gtk.CheckButton(_("_Hide window titlebar"))
        win_decor.set_active(not self.config.decorated)
        win_decor.connect('toggled',
            lambda w: setattr(self.config, 'decorated',
                not w.get_active()))
        minimize = gtk.CheckButton(_("_Minimize to system tray on close/escape"))
        minimize.set_active(self.config.minimize_to_systray)
        minimize.set_tooltip_text(_("If enabled, closing Sonata will minimize it to the system tray. Note that it's currently impossible to detect if there actually is a system tray, so only check this if you have one."))
        minimize.connect('toggled', self.prefs_config_widget_active, 'minimize_to_systray')
        display_trayicon.connect('toggled', prefs_trayicon_toggled, minimize)
        minimize.set_sensitive(trayicon_in_use)
        widgets = (win_sticky, win_ontop, win_decor, minimize)
        window_table = gtk.Table(len(widgets), 1)
        for i, widget in enumerate(widgets):
            window_table.attach(widget, 0, 1, i, i+1,
                gtk.FILL|gtk.EXPAND, gtk.FILL)
        window_alignment = gtk.Alignment()
        window_alignment.set_padding(12, 0, 12, 0)
        window_alignment.add(window_table)
        window_frame.add(window_alignment)

        misclabel = ui.label(markup='<b>' + _('Miscellaneous') + '</b>')
        misc_frame = gtk.Frame()
        misc_frame.set_label_widget(misclabel)
        misc_frame.set_shadow_type(gtk.SHADOW_NONE)
        update_start = gtk.CheckButton(_("_Update MPD library on start"))
        update_start.set_active(self.config.update_on_start)
        update_start.set_tooltip_text(_("If enabled, Sonata will automatically update your MPD library when it starts up."))
        update_start.connect('toggled', self.prefs_config_widget_active, 'update_on_start')
        exit_stop = gtk.CheckButton(_("S_top playback on exit"))
        exit_stop.set_active(self.config.stop_on_exit)
        exit_stop.set_tooltip_text(_("MPD allows playback even when the client is not open. If enabled, Sonata will behave like a more conventional music player and, instead, stop playback upon exit."))
        exit_stop.connect('toggled', self.prefs_config_widget_active, 'stop_on_exit')
        infofile_usage = gtk.CheckButton(_("_Write status file:"))
        infofile_usage.set_active(self.config.use_infofile)
        infofile_usage.set_tooltip_text(_("If enabled, Sonata will create a xmms-infopipe like file containing information about the current song. Many applications support the xmms-info file (Instant Messengers, IRC Clients...)"))
        infopath_options = ui.entry(text=self.config.infofile_path)
        infopath_options.set_tooltip_text(_("If enabled, Sonata will create a xmms-infopipe like file containing information about the current song. Many applications support the xmms-info file (Instant Messengers, IRC Clients...)"))
        if not self.config.use_infofile:
            infopath_options.set_sensitive(False)
        infofile_usage.connect('toggled', self.prefs_infofile_toggled, infopath_options)
        infofilebox = gtk.HBox(spacing=6)
        infofilebox.pack_start(infofile_usage, False, False)
        infofilebox.pack_start(infopath_options, True, True)
        widgets = (update_start, exit_stop, infofilebox)
        misc_table = gtk.Table(len(widgets), 1)
        for i, widget in enumerate(widgets):
            misc_table.attach(widget, 0, 1, i, i+1,
                gtk.FILL|gtk.EXPAND, gtk.FILL)
        misc_alignment = gtk.Alignment()
        misc_alignment.set_padding(12, 0, 12, 0)
        misc_alignment.add(misc_table)
        misc_frame.add(misc_alignment)

        behavior_table = gtk.Table(2, 1)
        behavior_table.set_row_spacings(12)
        behavior_table.attach(window_frame, 0, 1, 0, 1, gtk.FILL|gtk.EXPAND, gtk.FILL)
        behavior_table.attach(misc_frame, 0, 1, 1, 2, gtk.FILL|gtk.EXPAND, gtk.FILL)
        behavior_tab = gtk.Alignment()
        behavior_tab.set_padding(12, 12, 12, 12)
        behavior_tab.add(behavior_table)

        # Format tab
        formatlabel = ui.label(markup='<b>'+_('Song Formatting')+'</b>')
        format_frame = gtk.Frame()
        format_frame.set_label_widget(formatlabel)
        format_frame.set_shadow_type(gtk.SHADOW_NONE)

        rows = [(_("C_urrent playlist:"), self.config.currentformat),
            (_("_Library:"), self.config.libraryformat),
            (_("_Window title:"), self.config.titleformat),
            (_("Current _song line 1:"),
                self.config.currsongformat1),
            (_("Current s_ong line 2:"),
                self.config.currsongformat2)]

        format_labels = []
        format_entries = []
        for label_text, entry_text in rows:
            label = ui.label(textmn=label_text)
            entry = ui.entry(text=entry_text)

            label.set_mnemonic_widget(entry)

            format_labels.append(label)
            format_entries.append(entry)

        currentoptions = format_entries[0]
        libraryoptions = format_entries[1]
        titleoptions = format_entries[2]
        currsongoptions1 = format_entries[3]
        currsongoptions2 = format_entries[4]

        availableheading = ui.label(markup='<small>' + _('Available options') + ':</small>', y=0)
        availablevbox = gtk.VBox()
        availableformatbox = gtk.HBox()
        # XXX get these directly from the formatting function:
        formatcodes = [('A', _('Artist name')),
                   ('B', _('Album name')),
                   ('T', _('Track name')),
                   ('N', _('Track number')),
                   ('D', _('Disc number')),
                   ('Y', _('Year')),
                   ('G', _('Genre')),
                   ('P', _('File path')),
                   ('F', _('File name')),
                   ('S', _('Stream name')),
                   ('L', _('Song length')),
                   ('E', _('Elapsed time (title only)')),
                   ]
        for codes in [formatcodes[:(len(formatcodes)+1)/2],
                  formatcodes[(len(formatcodes)+1)/2:]]:
            rows = '\n'.join('<tt>%' + code + '</tt> - ' + help
                     for code, help in codes)
            markup = '<small>' + rows + '</small>'
            formattinghelp = ui.label(markup=markup, y=0)
            availableformatbox.pack_start(formattinghelp)

        availablevbox.pack_start(availableformatbox, False, False, 0)
        additionalinfo = ui.label(markup='<small><tt>{ }</tt> - ' + _('Info displayed only if all enclosed tags are defined') + '\n' + '<tt>|</tt> - ' + _('Creates columns in the current playlist') + '</small>', y=0)
        availablevbox.pack_start(additionalinfo, False, False, 4)

        num_rows = len(rows) + 2
        format_table = gtk.Table(num_rows, 2)
        format_table.set_col_spacings(12)
        label_entries = enumerate(zip(format_labels, format_entries))
        for i, (label, entry) in label_entries:
            format_table.attach(label, 0, 1, i, i+1, gtk.FILL)
            format_table.attach(entry, 1, 2, i, i+1)
        format_table.attach(availableheading, 0, 2, num_rows-2,
            num_rows-1, gtk.FILL|gtk.EXPAND, gtk.FILL|gtk.EXPAND,
            0, 6)
        format_table.attach(availablevbox, 0, 2, num_rows-1, num_rows)
        format_alignment = gtk.Alignment(0.5, 0.5, 1.0, 1.0)
        format_alignment.set_padding(12, 0, 12, 0)
        format_alignment.add(format_table)
        format_frame.add(format_alignment)
        format_tab = gtk.Alignment(0.5, 0.5, 1.0, 1.0)
        format_tab.set_padding(12, 12, 12, 12)
        format_tab.add(format_frame)

        # Plugins tab

        plugin_actions = (
            ('plugin_about', gtk.STOCK_ABOUT, _('_About'), None, None, self.plugin_about),
            ('plugin_configure', gtk.STOCK_PREFERENCES, _('_Configure...'), None, None, self.plugin_configure),
            )

        uiDescription = """
            <ui>
              <popup name="pluginmenu">
                <menuitem action="plugin_configure"/>
                <menuitem action="plugin_about"/>
              </popup>
            </ui>
            """

        self.plugin_UIManager = gtk.UIManager()
        actionGroup = gtk.ActionGroup('PluginActions')
        actionGroup.add_actions(plugin_actions)
        self.plugin_UIManager.insert_action_group(actionGroup, 0)
        self.plugin_UIManager.add_ui_from_string(uiDescription)

        self.pluginview = ui.treeview()
        self.pluginview.set_headers_visible(True)
        self.pluginselection = self.pluginview.get_selection()
        self.pluginselection.set_mode(gtk.SELECTION_SINGLE)
        self.pluginview.set_rules_hint(True)
        self.pluginview.set_property('can-focus', False)
        pluginwindow = ui.scrollwindow(add=self.pluginview)
        plugindata = gtk.ListStore(bool, gtk.gdk.Pixbuf, str)
        self.pluginview.set_model(plugindata)
        self.pluginview.connect('button-press-event', self.plugin_click)

        plugincheckcell = gtk.CellRendererToggle()
        plugincheckcell.set_property('activatable', True)
        plugincheckcell.connect('toggled', self.plugin_toggled, (plugindata, 0))
        pluginpixbufcell = gtk.CellRendererPixbuf()
        plugintextcell = gtk.CellRendererText()

        plugincol0 = gtk.TreeViewColumn()
        self.pluginview.append_column(plugincol0)
        plugincol0.pack_start(plugincheckcell, True)
        plugincol0.set_attributes(plugincheckcell, active=0)
        plugincol0.set_title("  " + _("Loaded") + "  ")

        plugincol1 = gtk.TreeViewColumn()
        self.pluginview.append_column(plugincol1)
        plugincol1.pack_start(pluginpixbufcell, False)
        plugincol1.pack_start(plugintextcell, True)
        plugincol1.set_attributes(pluginpixbufcell, pixbuf=1)
        plugincol1.set_attributes(plugintextcell, markup=2)
        plugincol1.set_title(_("Description"))

        plugindata.clear()
        for plugin in pluginsystem.get_info():
            pb = self.plugin_get_icon_pixbuf(plugin)
            plugin_text = "<b> " + plugin.longname + "</b>   " + plugin.version_string
            plugin_text += "\n " + plugin.description
            enabled = True
            plugindata.append((enabled, pb, plugin_text))

        # Set up table
        tables = [(_("MPD"), mpd_tab),
                       (_("Display"), display_tab),
                       (_("Behavior"), behavior_tab),
                       (_("Format"), format_tab),
                       (_("Extras"), extras_tab),
                       (_("Plugins"), pluginwindow)]
        for table_name, table in tables:
            tmplabel = ui.label(text=table_name)
            prefsnotebook.append_page(table, tmplabel)
        hbox.pack_start(prefsnotebook, False, False, 10)
        self.prefswindow.vbox.pack_start(hbox, False, False, 10)
        close_button = self.prefswindow.add_button(gtk.STOCK_CLOSE, gtk.RESPONSE_CLOSE)
        self.prefswindow.show_all()
        prefsnotebook.set_current_page(self.last_tab)
        close_button.grab_focus()
        self.prefswindow.connect('response', prefs_window_response, prefsnotebook, direntry, currentoptions, libraryoptions, titleoptions, currsongoptions1, currsongoptions2, infopath_options, using_mpd_env_vars, self.prev_host, self.prev_port, self.prev_password)
        # Save previous connection properties to determine if we should try to
        # connect to MPD after prefs are closed:
        self.prev_host = self.config.host[self.config.profile_num]
        self.prev_port = self.config.port[self.config.profile_num]
        self.prev_password = self.config.password[self.config.profile_num]

    def prefs_config_widget_active(self, widget, member):
        """Sets a config attribute to the widget's active value"""
        setattr(self.config, member, widget.get_active())

    def prefs_as_enabled_toggled(self, checkbox, *widgets):
        if checkbox.get_active():
            self.scrobbler.import_module(True)
        if self.scrobbler.imported():
            self.config.as_enabled = checkbox.get_active()
            self.scrobbler.init()
            for widget in widgets:
                widget.set_sensitive(self.config.as_enabled)
        elif checkbox.get_active():
            checkbox.set_active(False)

    def prefs_as_username_changed(self, entry):
        if self.scrobbler.imported():
            self.config.as_username = entry.get_text()
            self.scrobbler.auth_changed()

    def prefs_as_password_changed(self, entry):
        if self.scrobbler.imported():
            self.config.as_password_md5 = hashlib.md5(entry.get_text()).hexdigest()
            self.scrobbler.auth_changed()

    def prefs_nameentry_changed(self, entry, profile_combo, remove_profiles):
        if not self.updating_nameentry:
            prefs_profile_num = profile_combo.get_active()
            self.config.profile_names[prefs_profile_num] = entry.get_text()
            self.prefs_populate_profile_combo(profile_combo, prefs_profile_num, remove_profiles)

    def prefs_hostentry_changed(self, entry, profile_combo):
        prefs_profile_num = profile_combo.get_active()
        self.config.host[prefs_profile_num] = entry.get_text()

    def prefs_portentry_changed(self, entry, profile_combo):
        prefs_profile_num = profile_combo.get_active()
        self.config.port[prefs_profile_num] = entry.get_value_as_int()

    def prefs_passwordentry_changed(self, entry, profile_combo):
        prefs_profile_num = profile_combo.get_active()
        self.config.password[prefs_profile_num] = entry.get_text()

    def prefs_direntry_changed(self, entry, profile_combo):
        prefs_profile_num = profile_combo.get_active()
        self.config.musicdir[prefs_profile_num] = misc.sanitize_musicdir(entry.get_filename())

    def prefs_add_profile(self, _button, nameentry, profile_combo, remove_profiles):
        self.updating_nameentry = True
        prefs_profile_num = profile_combo.get_active()
        self.config.profile_names.append(_("New Profile"))
        nameentry.set_text(self.config.profile_names[-1])
        self.updating_nameentry = False
        self.config.host.append(self.config.host[prefs_profile_num])
        self.config.port.append(self.config.port[prefs_profile_num])
        self.config.password.append(self.config.password[prefs_profile_num])
        self.config.musicdir.append(self.config.musicdir[prefs_profile_num])
        self.prefs_populate_profile_combo(profile_combo, len(self.config.profile_names)-1, remove_profiles)

    def prefs_remove_profile(self, _button, profile_combo, remove_profiles):
        prefs_profile_num = profile_combo.get_active()
        if prefs_profile_num == self.config.profile_num:
            # Profile deleted, revert to first profile:
            self.config.profile_num = 0
            self.reconnect(None)
        self.config.profile_names.pop(prefs_profile_num)
        self.config.host.pop(prefs_profile_num)
        self.config.port.pop(prefs_profile_num)
        self.config.password.pop(prefs_profile_num)
        self.config.musicdir.pop(prefs_profile_num)
        if prefs_profile_num > 0:
            self.prefs_populate_profile_combo(profile_combo, prefs_profile_num-1, remove_profiles)
        else:
            self.prefs_populate_profile_combo(profile_combo, 0, remove_profiles)

    def prefs_profile_chosen(self, profile_combo, nameentry, hostentry, portentry, passwordentry, direntry):
        prefs_profile_num = profile_combo.get_active()
        self.updating_nameentry = True
        nameentry.set_text(str(self.config.profile_names[prefs_profile_num]))
        self.updating_nameentry = False
        hostentry.set_text(str(self.config.host[prefs_profile_num]))
        portentry.set_value(self.config.port[prefs_profile_num])
        passwordentry.set_text(str(self.config.password[prefs_profile_num]))
        direntry.set_filename(str(self.config.musicdir[prefs_profile_num]))

    def prefs_populate_profile_combo(self, profile_combo, active_index, remove_profiles):
        new_model = gtk.ListStore(str)
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

    def prefs_lyrics_location_changed(self, combobox):
        self.config.lyrics_location = combobox.get_active()

    def prefs_art_location_changed(self, combobox):
        if combobox.get_active() == consts.ART_LOCATION_CUSTOM:
            # Prompt user for playlist name:
            dialog = ui.dialog(title=_("Custom Artwork"), parent=self.window, flags=gtk.DIALOG_MODAL | gtk.DIALOG_DESTROY_WITH_PARENT, buttons=(gtk.STOCK_CANCEL, gtk.RESPONSE_REJECT, gtk.STOCK_OK, gtk.RESPONSE_ACCEPT), role='customArtwork', default=gtk.RESPONSE_ACCEPT)
            hbox = gtk.HBox()
            hbox.pack_start(ui.label(text=_('Artwork filename') + ':'), False, False, 5)
            entry = ui.entry()
            entry.set_activates_default(True)
            hbox.pack_start(entry, True, True, 5)
            dialog.vbox.pack_start(hbox)
            dialog.vbox.show_all()
            response = dialog.run()
            if response == gtk.RESPONSE_ACCEPT:
                self.config.art_location_custom_filename = entry.get_text().replace("/", "")
            else:
                # Revert to non-custom item in combobox:
                combobox.set_active(self.config.art_location)
            dialog.destroy()
        self.config.art_location = combobox.get_active()

    def prefs_crossfadecheck_toggled(self, button, *widgets):
        button_active = button.get_active()
        for widget in widgets:
            widget.set_sensitive(button_active)

    def prefs_notiflocation_changed(self, combobox):
        self.config.traytips_notifications_location = combobox.get_active()
        self.renotify()

    def prefs_notiftime_changed(self, combobox):
        self.config.popup_option = combobox.get_active()
        self.renotify()

    def prefs_infofile_toggled(self, button, infofileformatbox):
        self.config.use_infofile = button.get_active()
        infofileformatbox.set_sensitive(self.config.use_infofile)
        if self.config.use_infofile:
            self.reinfofile()

    def plugin_click(self, _widget, event):
        if event.button == 3:
            self.plugin_UIManager.get_widget('/pluginmenu').popup(None, None, None, event.button, event.time)

    def plugin_toggled(self, renderer, path, user_data):
        model, column = user_data
        model[path][column] = not model[path][column]
        return

    def plugin_about(self, _widget):
        plugin = self.plugin_get_selected()
        iconpb = self.plugin_get_icon_pixbuf(plugin)
        model = self.pluginview.get_model()

        about_text = plugin.longname + "\n" + plugin.author + "\n"
        if len(plugin.author_email) > 0:
            about_text += "<" + plugin.author_email + ">"

        self.about_dialog = gtk.AboutDialog()
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
            gtk.about_dialog_set_url_hook(self.plugin_show_website)
            self.about_dialog.set_website(plugin.url)
        self.about_dialog.set_logo(iconpb)

        self.about_dialog.connect('response', self.plugin_about_close)
        self.about_dialog.connect('delete_event', self.plugin_about_close)
        self.about_dialog.show_all()

    def plugin_about_close(self, _event, _data=None):
        self.about_dialog.hide()
        return True

    def plugin_show_website(self, _dialog, link):
        misc.browser_load(link, self.config.url_browser, self.window)

    def plugin_configure(self, _widget):
        plugin = self.plugin_get_selected()
        ui.show_msg(self.prefswindow, "Nothing yet implemented.", "Configure", "pluginConfigure", gtk.BUTTONS_CLOSE)

    def plugin_get_selected(self):
        model, iter = self.pluginselection.get_selected()
        plugin_num = model.get_path(iter)[0]
        return pluginsystem.get_info()[plugin_num]

    def plugin_get_icon_pixbuf(self, plugin):
        pb = plugin.iconurl
        try:
            pb = gtk.gdk.pixbuf_new_from_file(iconurl)
        except:
            pb = self.pluginview.render_icon(gtk.STOCK_EXECUTE, gtk.ICON_SIZE_LARGE_TOOLBAR)
        return pb
