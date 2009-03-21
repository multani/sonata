
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

        # These mirror the audioscrobbler module in Main
        self.as_imported = None
        self.as_import = None
        self.as_init = None
        self.as_reauth = None

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

    def on_prefs_real(self, parent_window, popuptimes, as_imported, as_import, as_init, as_reauth, trayicon_available, trayicon_in_use, reconnect, renotify, reinfofile, prefs_notif_toggled, prefs_stylized_toggled, prefs_art_toggled, prefs_playback_toggled, prefs_progress_toggled, prefs_statusbar_toggled, prefs_lyrics_toggled, prefs_trayicon_toggled, prefs_window_response):
        """Display the preferences dialog"""
        self.window = parent_window
        self.as_imported = as_imported
        self.as_import = as_import
        self.as_init = as_init
        self.as_reauth = as_reauth
        self.reconnect = reconnect
        self.renotify = renotify
        self.reinfofile = reinfofile

        self.prefswindow = ui.dialog(title=_("Preferences"), parent=self.window, flags=gtk.DIALOG_DESTROY_WITH_PARENT, role='preferences', resizable=False, separator=False)
        hbox = gtk.HBox()
        prefsnotebook = gtk.Notebook()
        # MPD tab
        mpdlabel = ui.label(markup='<b>' + _('MPD Connection') + '</b>', y=1)
        controlbox = gtk.HBox()
        profiles = ui.combo()
        add_profile = ui.button(img=ui.image(stock=gtk.STOCK_ADD))
        remove_profile = ui.button(img=ui.image(stock=gtk.STOCK_REMOVE))
        self.prefs_populate_profile_combo(profiles, self.config.profile_num, remove_profile)
        controlbox.pack_start(profiles, False, False, 2)
        controlbox.pack_start(remove_profile, False, False, 2)
        controlbox.pack_start(add_profile, False, False, 2)
        namebox = gtk.HBox()
        namelabel = ui.label(text=_("Name") + ":")
        namebox.pack_start(namelabel, False, False, 0)
        nameentry = ui.entry()
        namebox.pack_start(nameentry, True, True, 10)
        hostbox = gtk.HBox()
        hostlabel = ui.label(text=_("Host") + ":")
        hostbox.pack_start(hostlabel, False, False, 0)
        hostentry = ui.entry()
        hostbox.pack_start(hostentry, True, True, 10)
        portbox = gtk.HBox()
        portlabel = ui.label(text=_("Port") + ":")
        portbox.pack_start(portlabel, False, False, 0)
        portentry = ui.entry()
        portbox.pack_start(portentry, True, True, 10)
        dirbox = gtk.HBox()
        dirlabel = ui.label(text=_("Music dir") + ":")
        dirbox.pack_start(dirlabel, False, False, 0)
        direntry = ui.entry()
        direntry.connect('changed', self.prefs_direntry_changed, profiles)
        dirbox.pack_start(direntry, True, True, 10)
        passwordbox = gtk.HBox()
        passwordlabel = ui.label(text=_("Password") + ":")
        passwordbox.pack_start(passwordlabel, False, False, 0)
        passwordentry = ui.entry(password=True)
        passwordentry.set_tooltip_text(_("Leave blank if no password is required."))
        passwordbox.pack_start(passwordentry, True, True, 10)
        mpd_labels = [namelabel, hostlabel, portlabel, passwordlabel, dirlabel]
        ui.set_widths_equal(mpd_labels)
        autoconnect = gtk.CheckButton(_("Autoconnect on start"))
        autoconnect.set_active(self.config.autoconnect)
        # Fill in entries with current profile:
        self.prefs_profile_chosen(profiles, nameentry, hostentry, portentry, passwordentry, direntry)
        # Update display if $MPD_HOST or $MPD_PORT is set:
        host, port, password = misc.mpd_env_vars()
        if host or port:
            using_mpd_env_vars = True
            if not host:
                host = ""
            if not port:
                port = ""
            if not password:
                password = ""
            hostentry.set_text(str(host))
            portentry.set_text(str(port))
            passwordentry.set_text(str(password))
            nameentry.set_text(_("Using MPD_HOST/PORT"))
            for widget in [hostentry, portentry, passwordentry, nameentry, profiles, add_profile, remove_profile]:
                widget.set_sensitive(False)
        else:
            using_mpd_env_vars = False
            nameentry.connect('changed', self.prefs_nameentry_changed, profiles, remove_profile)
            hostentry.connect('changed', self.prefs_hostentry_changed, profiles)
            portentry.connect('changed', self.prefs_portentry_changed, profiles)
            passwordentry.connect('changed', self.prefs_passwordentry_changed, profiles)
            profiles.connect('changed', self.prefs_profile_chosen, nameentry, hostentry, portentry, passwordentry, direntry)
            add_profile.connect('clicked', self.prefs_add_profile, nameentry, profiles, remove_profile)
            remove_profile.connect('clicked', self.prefs_remove_profile, profiles, remove_profile)
        mpd_frame = gtk.Frame()
        table = gtk.Table(6, 2, False)
        table.set_col_spacings(3)
        table.attach(ui.label(), 1, 3, 1, 2, gtk.FILL|gtk.EXPAND, gtk.FILL|gtk.EXPAND, 10, 0)
        table.attach(namebox, 1, 3, 2, 3, gtk.FILL|gtk.EXPAND, gtk.FILL|gtk.EXPAND, 10, 0)
        table.attach(hostbox, 1, 3, 3, 4, gtk.FILL|gtk.EXPAND, gtk.FILL|gtk.EXPAND, 10, 0)
        table.attach(portbox, 1, 3, 4, 5, gtk.FILL|gtk.EXPAND, gtk.FILL|gtk.EXPAND, 10, 0)
        table.attach(passwordbox, 1, 3, 5, 6, gtk.FILL|gtk.EXPAND, gtk.FILL|gtk.EXPAND, 10, 0)
        table.attach(dirbox, 1, 3, 6, 7, gtk.FILL|gtk.EXPAND, gtk.FILL|gtk.EXPAND, 10, 0)
        table.attach(ui.label(), 1, 3, 7, 8, gtk.FILL|gtk.EXPAND, gtk.FILL|gtk.EXPAND, 10, 0)
        mpd_frame.add(table)
        mpd_frame.set_label_widget(controlbox)
        mpd_table = gtk.Table(9, 2, False)
        mpd_table.set_col_spacings(3)
        mpd_table.attach(ui.label(), 1, 3, 1, 2, gtk.FILL|gtk.EXPAND, gtk.FILL|gtk.EXPAND, 10, 0)
        mpd_table.attach(mpdlabel, 1, 3, 2, 3, gtk.FILL|gtk.EXPAND, gtk.FILL|gtk.EXPAND, 15, 0)
        mpd_table.attach(ui.label(), 1, 3, 3, 4, gtk.FILL|gtk.EXPAND, gtk.FILL|gtk.EXPAND, 10, 0)
        mpd_table.attach(mpd_frame, 1, 3, 4, 10, gtk.FILL|gtk.EXPAND, gtk.FILL|gtk.EXPAND, 30, 0)
        mpd_table.attach(ui.label(), 1, 3, 10, 11, gtk.FILL|gtk.EXPAND, gtk.FILL|gtk.EXPAND, 30, 0)
        mpd_table.attach(autoconnect, 1, 3, 11, 12, gtk.FILL|gtk.EXPAND, gtk.FILL|gtk.EXPAND, 30, 0)
        mpd_table.attach(ui.label(), 1, 3, 12, 13, gtk.FILL|gtk.EXPAND, gtk.FILL|gtk.EXPAND, 30, 0)
        mpd_table.attach(ui.label(), 1, 3, 13, 14, gtk.FILL|gtk.EXPAND, gtk.FILL|gtk.EXPAND, 30, 0)
        mpd_table.attach(ui.label(), 1, 3, 14, 15, gtk.FILL|gtk.EXPAND, gtk.FILL|gtk.EXPAND, 30, 0)
        # Extras tab
        if not as_imported:
            self.config.as_enabled = False
        as_label = ui.label(markup='<b>' + _('Extras') + '</b>')
        as_frame = gtk.Frame()
        as_frame.set_label_widget(as_label)
        as_frame.set_shadow_type(gtk.SHADOW_NONE)
        as_frame.set_border_width(15)
        as_vbox = gtk.VBox()
        as_vbox.set_border_width(15)
        as_checkbox = gtk.CheckButton(_("Enable Audioscrobbling (Last.fm)"))
        as_checkbox.set_active(self.config.as_enabled)
        as_vbox.pack_start(as_checkbox, False)
        as_table = gtk.Table(2, 2)
        as_table.set_col_spacings(3)
        as_user_label = ui.label(text="          " + _("Username:"))
        as_pass_label = ui.label(text="          " + _("Password:"))
        as_user_entry = ui.entry(text=self.config.as_username, changed_cb=self.prefs_as_username_changed)
        if len(self.config.as_password_md5) > 0:
            as_pass_entry = ui.entry(text='1234', password=True, changed_cb=self.prefs_as_password_changed)
        else:
            as_pass_entry = ui.entry(text='', password=True, changed_cb=self.prefs_as_password_changed)
        display_notification = gtk.CheckButton(_("Popup notification on song changes"))
        display_notification.set_active(self.config.show_notification)
        notifhbox = gtk.HBox()
        notif_blank = ui.label(x=1)
        notifhbox.pack_start(notif_blank)

        time_names = []
        for i in popuptimes:
            if i != _('Entire song'):
                time_names.append(i + ' ' + gettext.ngettext('second', 'seconds', int(i)))
            else:
                time_names.append(i)
        notification_options = ui.combo(items=time_names, active=self.config.popup_option, changed_cb=self.prefs_notiftime_changed)

        notification_locs = ui.combo(items=self.popuplocations, active=self.config.traytips_notifications_location, changed_cb=self.prefs_notiflocation_changed)
        display_notification.connect('toggled', prefs_notif_toggled, notifhbox)
        notifhbox.pack_start(notification_options, False, False, 2)
        notifhbox.pack_start(notification_locs, False, False, 2)
        if not self.config.show_notification:
            notifhbox.set_sensitive(False)
        crossfadecheck = gtk.CheckButton(_("Enable Crossfade"))
        crossfadespin = gtk.SpinButton()
        crossfadespin.set_digits(0)
        crossfadespin.set_range(1, 30)
        crossfadespin.set_value(self.config.xfade)
        crossfadespin.set_numeric(True)
        crossfadespin.set_increments(1, 5)
        crossfadespin.set_size_request(70, -1)
        crossfadelabel2 = ui.label(text=_("Fade length") + ":", x=1)
        crossfadelabel3 = ui.label(text=_("sec"))
        if not self.config.xfade_enabled:
            crossfadespin.set_sensitive(False)
            crossfadelabel2.set_sensitive(False)
            crossfadelabel3.set_sensitive(False)
            crossfadecheck.set_active(False)
        else:
            crossfadespin.set_sensitive(True)
            crossfadelabel2.set_sensitive(True)
            crossfadelabel3.set_sensitive(True)
            crossfadecheck.set_active(True)
        crossfadebox = gtk.HBox()
        crossfadebox.pack_start(crossfadelabel2)
        crossfadebox.pack_start(crossfadespin, False, False, 5)
        crossfadebox.pack_start(crossfadelabel3, False, False, 0)
        crossfadecheck.connect('toggled', self.prefs_crossfadecheck_toggled, crossfadespin, crossfadelabel2, crossfadelabel3)
        as_table.attach(as_user_label, 0, 1, 0, 1)
        as_table.attach(as_user_entry, 1, 2, 0, 1)
        as_table.attach(as_pass_label, 0, 1, 1, 2)
        as_table.attach(as_pass_entry, 1, 2, 1, 2)
        as_table.attach(ui.label(), 0, 2, 2, 3)
        as_table.attach(display_notification, 0, 2, 3, 4)
        as_table.attach(notifhbox, 0, 2, 4, 5)
        as_table.attach(ui.label(), 0, 2, 5, 6)
        as_table.attach(crossfadecheck, 0, 2, 6, 7)
        as_table.attach(crossfadebox, 0, 2, 7, 8)
        as_table.attach(ui.label(), 0, 2, 8, 9)
        as_vbox.pack_start(as_table, False)
        as_frame.add(as_vbox)
        as_checkbox.connect('toggled', self.prefs_as_enabled_toggled, as_user_entry, as_pass_entry, as_user_label, as_pass_label)
        if not self.config.as_enabled or not as_imported:
            as_user_entry.set_sensitive(False)
            as_pass_entry.set_sensitive(False)
            as_user_label.set_sensitive(False)
            as_pass_label.set_sensitive(False)
        # Display tab
        table2 = gtk.Table(7, 2, False)
        displaylabel = ui.label(markup='<b>' + _('Display') + '</b>', y=1)
        display_art_hbox = gtk.HBox()
        display_art = gtk.CheckButton(_("Enable album art"))
        display_art.set_active(self.config.show_covers)
        display_stylized_combo = ui.combo(items=[_("Standard"), _("Stylized")], active=self.config.covers_type, changed_cb=prefs_stylized_toggled)
        display_stylized_hbox = gtk.HBox()
        display_stylized_hbox.pack_start(ui.label(text=_("Artwork style:"), x=1))
        display_stylized_hbox.pack_start(display_stylized_combo, False, False, 5)
        display_stylized_hbox.set_sensitive(self.config.show_covers)
        display_art_combo = ui.combo(items=[_("Local only"), _("Local and remote")], active=self.config.covers_pref)
        orderart_label = ui.label(text=_("Search locations:"), x=1)
        display_art_hbox.pack_start(orderart_label)
        display_art_hbox.pack_start(display_art_combo, False, False, 5)
        display_art_hbox.set_sensitive(self.config.show_covers)
        display_art_location_hbox = gtk.HBox()
        display_art_location_hbox.pack_start(ui.label(text=_("Save art to:"), x=1))

        art_paths = ["~/.covers/"]
        for item in ["/cover.jpg", "/album.jpg", "/folder.jpg", "/" + _("custom")]:
            art_paths.append("../" + _("file_path") + item)
        display_art_location = ui.combo(items=art_paths, active=self.config.art_location, changed_cb=self.prefs_art_location_changed)

        display_art_location_hbox.pack_start(display_art_location, False, False, 5)
        display_art_location_hbox.set_sensitive(self.config.show_covers)
        display_art.connect('toggled', prefs_art_toggled, display_art_hbox, display_art_location_hbox, display_stylized_hbox)
        display_playback = gtk.CheckButton(_("Enable playback/volume buttons"))
        display_playback.set_active(self.config.show_playback)
        display_playback.connect('toggled', prefs_playback_toggled)
        display_progress = gtk.CheckButton(_("Enable progressbar"))
        display_progress.set_active(self.config.show_progress)
        display_progress.connect('toggled', prefs_progress_toggled)
        display_statusbar = gtk.CheckButton(_("Enable statusbar"))
        display_statusbar.set_active(self.config.show_statusbar)
        display_statusbar.connect('toggled', prefs_statusbar_toggled)
        display_lyrics = gtk.CheckButton(_("Enable lyrics"))
        display_lyrics.set_active(self.config.show_lyrics)
        display_lyrics_location_hbox = gtk.HBox()
        savelyrics_label = ui.label(text=_("Save lyrics to:"), x=1)
        display_lyrics_location_hbox.pack_start(savelyrics_label)
        display_lyrics_location = ui.combo(items=["~/.lyrics/", "../" + _("file_path") + "/"], active=self.config.lyrics_location, changed_cb=self.prefs_lyrics_location_changed)
        display_lyrics_location_hbox.pack_start(display_lyrics_location, False, False, 5)
        display_lyrics_location_hbox.set_sensitive(self.config.show_lyrics)
        display_lyrics.connect('toggled', prefs_lyrics_toggled, display_lyrics_location_hbox)
        display_trayicon = gtk.CheckButton(_("Enable system tray icon"))
        display_trayicon.set_active(self.config.show_trayicon)
        display_trayicon.set_sensitive(trayicon_available)
        table2.attach(ui.label(), 1, 3, 1, 2, gtk.FILL|gtk.EXPAND, gtk.FILL|gtk.EXPAND, 15, 0)
        table2.attach(displaylabel, 1, 3, 2, 3, gtk.FILL|gtk.EXPAND, gtk.FILL|gtk.EXPAND, 15, 0)
        table2.attach(ui.label(), 1, 3, 3, 4, gtk.FILL|gtk.EXPAND, gtk.FILL|gtk.EXPAND, 15, 0)
        table2.attach(display_playback, 1, 3, 4, 5, gtk.FILL|gtk.EXPAND, gtk.FILL|gtk.EXPAND, 30, 0)
        table2.attach(display_progress, 1, 3, 5, 6, gtk.FILL|gtk.EXPAND, gtk.FILL|gtk.EXPAND, 30, 0)
        table2.attach(display_statusbar, 1, 3, 6, 7, gtk.FILL|gtk.EXPAND, gtk.FILL|gtk.EXPAND, 30, 0)
        table2.attach(display_trayicon, 1, 3, 7, 8, gtk.FILL|gtk.EXPAND, gtk.FILL|gtk.EXPAND, 30, 0)
        table2.attach(display_lyrics, 1, 3, 8, 9, gtk.FILL|gtk.EXPAND, gtk.FILL|gtk.EXPAND, 30, 0)
        table2.attach(display_lyrics_location_hbox, 1, 3, 9, 10, gtk.FILL|gtk.EXPAND, gtk.FILL|gtk.EXPAND, 30, 0)
        table2.attach(display_art, 1, 3, 10, 11, gtk.FILL|gtk.EXPAND, gtk.FILL|gtk.EXPAND, 30, 0)
        table2.attach(display_stylized_hbox, 1, 3, 11, 12, gtk.FILL|gtk.EXPAND, gtk.FILL|gtk.EXPAND, 30, 0)
        table2.attach(display_art_hbox, 1, 3, 12, 13, gtk.FILL|gtk.EXPAND, gtk.FILL|gtk.EXPAND, 30, 0)
        table2.attach(display_art_location_hbox, 1, 3, 13, 14, gtk.FILL|gtk.EXPAND, gtk.FILL|gtk.EXPAND, 30, 0)
        table2.attach(ui.label(), 1, 3, 14, 15, gtk.FILL|gtk.EXPAND, gtk.FILL|gtk.EXPAND, 75, 0)
        # Behavior tab
        table3 = gtk.Table()
        behaviorlabel = ui.label(markup='<b>' + _('Window Behavior') + '</b>', y=1)
        win_sticky = gtk.CheckButton(_("Show window on all workspaces"))
        win_sticky.set_active(self.config.sticky)
        win_ontop = gtk.CheckButton(_("Keep window above other windows"))
        win_ontop.set_active(self.config.ontop)
        win_decor = gtk.CheckButton(_("Hide window titlebar"))
        win_decor.set_active(not self.config.decorated)
        update_start = gtk.CheckButton(_("Update MPD library on start"))
        update_start.set_active(self.config.update_on_start)
        update_start.set_tooltip_text(_("If enabled, Sonata will automatically update your MPD library when it starts up."))
        exit_stop = gtk.CheckButton(_("Stop playback on exit"))
        exit_stop.set_active(self.config.stop_on_exit)
        exit_stop.set_tooltip_text(_("MPD allows playback even when the client is not open. If enabled, Sonata will behave like a more conventional music player and, instead, stop playback upon exit."))
        minimize = gtk.CheckButton(_("Minimize to system tray on close/escape"))
        minimize.set_active(self.config.minimize_to_systray)
        minimize.set_tooltip_text(_("If enabled, closing Sonata will minimize it to the system tray. Note that it's currently impossible to detect if there actually is a system tray, so only check this if you have one."))
        display_trayicon.connect('toggled', prefs_trayicon_toggled, minimize)
        minimize.set_sensitive(trayicon_in_use)
        infofilebox = gtk.HBox()
        infofile_usage = gtk.CheckButton(_("Write status file:"))
        infofile_usage.set_active(self.config.use_infofile)
        infofile_usage.set_tooltip_text(_("If enabled, Sonata will create a xmms-infopipe like file containing information about the current song. Many applications support the xmms-info file (Instant Messengers, IRC Clients...)"))
        infopath_options = ui.entry(text=self.config.infofile_path)
        infopath_options.set_tooltip_text(_("If enabled, Sonata will create a xmms-infopipe like file containing information about the current song. Many applications support the xmms-info file (Instant Messengers, IRC Clients...)"))
        if not self.config.use_infofile:
            infopath_options.set_sensitive(False)
        infofile_usage.connect('toggled', self.prefs_infofile_toggled, infopath_options)
        infofilebox.pack_start(infofile_usage, False, False, 0)
        infofilebox.pack_start(infopath_options, True, True, 5)
        behaviorlabel2 = ui.label(markup='<b>' + _('Miscellaneous') + '</b>', y=1)
        table3.attach(ui.label(), 1, 3, 1, 2, gtk.FILL|gtk.EXPAND, gtk.FILL|gtk.EXPAND, 15, 0)
        table3.attach(behaviorlabel, 1, 3, 2, 3, gtk.FILL|gtk.EXPAND, gtk.FILL|gtk.EXPAND, 15, 0)
        table3.attach(ui.label(), 1, 3, 3, 4, gtk.FILL|gtk.EXPAND, gtk.FILL|gtk.EXPAND, 15, 0)
        table3.attach(win_sticky, 1, 3, 4, 5, gtk.FILL|gtk.EXPAND, gtk.FILL|gtk.EXPAND, 30, 0)
        table3.attach(win_ontop, 1, 3, 5, 6, gtk.FILL|gtk.EXPAND, gtk.FILL|gtk.EXPAND, 30, 0)
        table3.attach(win_decor, 1, 3, 6, 7, gtk.FILL|gtk.EXPAND, gtk.FILL|gtk.EXPAND, 30, 0)
        table3.attach(minimize, 1, 3, 7, 8, gtk.FILL|gtk.EXPAND, gtk.FILL|gtk.EXPAND, 30, 0)
        table3.attach(ui.label(), 1, 3, 8, 9, gtk.FILL|gtk.EXPAND, gtk.FILL|gtk.EXPAND, 15, 0)
        table3.attach(behaviorlabel2, 1, 3, 9, 10, gtk.FILL|gtk.EXPAND, gtk.FILL|gtk.EXPAND, 15, 0)
        table3.attach(ui.label(), 1, 3, 10, 11, gtk.FILL|gtk.EXPAND, gtk.FILL|gtk.EXPAND, 15, 0)
        table3.attach(update_start, 1, 3, 11, 12, gtk.FILL|gtk.EXPAND, gtk.FILL|gtk.EXPAND, 30, 0)
        table3.attach(exit_stop, 1, 3, 12, 13, gtk.FILL|gtk.EXPAND, gtk.FILL|gtk.EXPAND, 30, 0)
        table3.attach(infofilebox, 1, 3, 13, 14, gtk.FILL|gtk.EXPAND, gtk.FILL|gtk.EXPAND, 30, 0)
        table3.attach(ui.label(), 1, 3, 14, 15, gtk.FILL|gtk.EXPAND, gtk.FILL|gtk.EXPAND, 30, 0)
        table3.attach(ui.label(), 1, 3, 15, 16, gtk.FILL|gtk.EXPAND, gtk.FILL|gtk.EXPAND, 30, 0)
        table3.attach(ui.label(), 1, 3, 16, 17, gtk.FILL|gtk.EXPAND, gtk.FILL|gtk.EXPAND, 30, 0)
        table3.attach(ui.label(), 1, 3, 17, 18, gtk.FILL|gtk.EXPAND, gtk.FILL|gtk.EXPAND, 30, 0)
        table3.attach(ui.label(), 1, 3, 18, 19, gtk.FILL|gtk.EXPAND, gtk.FILL|gtk.EXPAND, 30, 0)
        # Format tab
        table4 = gtk.Table(9, 2, False)
        table4.set_col_spacings(3)
        formatlabel = ui.label(markup='<b>' + _('Song Formatting') + '</b>', y=1)
        currentformatbox = gtk.HBox()
        currentlabel = ui.label(text=_("Current playlist:"))
        currentoptions = ui.entry(text=self.config.currentformat)
        currentformatbox.pack_start(currentlabel, False, False, 0)
        currentformatbox.pack_start(currentoptions, False, False, 10)
        libraryformatbox = gtk.HBox()
        librarylabel = ui.label(text=_("Library:"))
        libraryoptions = ui.entry(text=self.config.libraryformat)
        libraryformatbox.pack_start(librarylabel, False, False, 0)
        libraryformatbox.pack_start(libraryoptions, False, False, 10)
        titleformatbox = gtk.HBox()
        titlelabel = ui.label(text=_("Window title:"))
        titleoptions = ui.entry(text=self.config.titleformat)
        titleoptions.set_text(self.config.titleformat)
        titleformatbox.pack_start(titlelabel, False, False, 0)
        titleformatbox.pack_start(titleoptions, False, False, 10)
        currsongformatbox1 = gtk.HBox()
        currsonglabel1 = ui.label(text=_("Current song line 1:"))
        currsongoptions1 = ui.entry(text=self.config.currsongformat1)
        currsongformatbox1.pack_start(currsonglabel1, False, False, 0)
        currsongformatbox1.pack_start(currsongoptions1, False, False, 10)
        currsongformatbox2 = gtk.HBox()
        currsonglabel2 = ui.label(text=_("Current song line 2:"))
        currsongoptions2 = ui.entry(text=self.config.currsongformat2)
        currsongformatbox2.pack_start(currsonglabel2, False, False, 0)
        currsongformatbox2.pack_start(currsongoptions2, False, False, 10)
        formatlabels = [currentlabel, librarylabel, titlelabel, currsonglabel1, currsonglabel2]
        for label in formatlabels:
            label.set_alignment(0, 0.5)
        ui.set_widths_equal(formatlabels)

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

        table4.attach(ui.label(), 1, 3, 1, 2, gtk.FILL|gtk.EXPAND, gtk.FILL|gtk.EXPAND, 15, 0)
        table4.attach(formatlabel, 1, 3, 2, 3, gtk.FILL|gtk.EXPAND, gtk.FILL|gtk.EXPAND, 15, 0)
        table4.attach(ui.label(), 1, 3, 3, 4, gtk.FILL|gtk.EXPAND, gtk.FILL|gtk.EXPAND, 15, 0)
        table4.attach(currentformatbox, 1, 3, 4, 5, gtk.FILL|gtk.EXPAND, gtk.FILL|gtk.EXPAND, 30, 0)
        table4.attach(libraryformatbox, 1, 3, 5, 6, gtk.FILL|gtk.EXPAND, gtk.FILL|gtk.EXPAND, 30, 0)
        table4.attach(titleformatbox, 1, 3, 6, 7, gtk.FILL|gtk.EXPAND, gtk.FILL|gtk.EXPAND, 30, 0)
        table4.attach(currsongformatbox1, 1, 3, 7, 8, gtk.FILL|gtk.EXPAND, gtk.FILL|gtk.EXPAND, 30, 0)
        table4.attach(currsongformatbox2, 1, 3, 8, 9, gtk.FILL|gtk.EXPAND, gtk.FILL|gtk.EXPAND, 30, 0)
        table4.attach(ui.label(), 1, 3, 9, 10, gtk.FILL|gtk.EXPAND, gtk.FILL|gtk.EXPAND, 30, 0)
        table4.attach(availableheading, 1, 3, 10, 11, gtk.FILL|gtk.EXPAND, gtk.FILL|gtk.EXPAND, 30, 0)
        table4.attach(availablevbox, 1, 3, 11, 12, gtk.FILL|gtk.EXPAND, gtk.FILL|gtk.EXPAND, 45, 0)
        table4.attach(ui.label(), 1, 3, 12, 13, gtk.FILL|gtk.EXPAND, gtk.FILL|gtk.EXPAND, 30, 0)

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
        tables = [(_("_MPD"), mpd_table),
                       (_("_Display"), table2),
                       (_("_Behavior"), table3),
                       (_("_Format"), table4),
                       (_("_Extras"), as_frame),
                       (_("_Plugins"), pluginwindow)]
        for table_name, table in tables:
            tmplabel = ui.label(textmn=table_name)
            prefsnotebook.append_page(table, tmplabel)
        hbox.pack_start(prefsnotebook, False, False, 10)
        self.prefswindow.vbox.pack_start(hbox, False, False, 10)
        close_button = self.prefswindow.add_button(gtk.STOCK_CLOSE, gtk.RESPONSE_CLOSE)
        self.prefswindow.show_all()
        close_button.grab_focus()
        self.prefswindow.connect('response', prefs_window_response, prefsnotebook, exit_stop, win_ontop, win_decor, display_art_combo, win_sticky, direntry, minimize, update_start, autoconnect, currentoptions, libraryoptions, titleoptions, currsongoptions1, currsongoptions2, crossfadecheck, crossfadespin, infopath_options, using_mpd_env_vars, self.prev_host, self.prev_port, self.prev_password)
        # Save previous connection properties to determine if we should try to
        # connect to MPD after prefs are closed:
        self.prev_host = self.config.host[self.config.profile_num]
        self.prev_port = self.config.port[self.config.profile_num]
        self.prev_password = self.config.password[self.config.profile_num]

    def prefs_as_enabled_toggled(self, checkbox, userentry, passentry, userlabel, passlabel):
        if checkbox.get_active():
            self.as_import(True)
            self.as_imported = True
        if self.as_imported:
            self.config.as_enabled = checkbox.get_active()
            self.as_init()
            for widget in [userlabel, passlabel, userentry, passentry]:
                widget.set_sensitive(self.config.as_enabled)
        elif checkbox.get_active():
            checkbox.set_active(False)

    def prefs_as_username_changed(self, entry):
        if self.as_imported:
            self.config.as_username = entry.get_text()
            self.as_reauth()

    def prefs_as_password_changed(self, entry):
        if self.as_imported:
            self.config.as_password_md5 = hashlib.md5(entry.get_text()).hexdigest()
            self.as_reauth()

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
        try:
            self.config.port[prefs_profile_num] = int(entry.get_text())
        except:
            pass

    def prefs_passwordentry_changed(self, entry, profile_combo):
        prefs_profile_num = profile_combo.get_active()
        self.config.password[prefs_profile_num] = entry.get_text()

    def prefs_direntry_changed(self, entry, profile_combo):
        prefs_profile_num = profile_combo.get_active()
        self.config.musicdir[prefs_profile_num] = misc.sanitize_musicdir(entry.get_text())

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
        portentry.set_text(str(self.config.port[prefs_profile_num]))
        passwordentry.set_text(str(self.config.password[prefs_profile_num]))
        direntry.set_text(str(self.config.musicdir[prefs_profile_num]))

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

    def prefs_crossfadecheck_toggled(self, button, combobox, label1, label2):
        button_active = button.get_active()
        for widget in [combobox, label1, label2]:
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
