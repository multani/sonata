
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

from sonata.config import Config
from sonata.pluginsystem import pluginsystem
from sonata import ui, misc, consts, formatting
import os

class Extras_cbs(object):
    """Callbacks and data specific to the extras tab"""
    popuptimes = []
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

        self.builder = ui.builder('preferences.ui')
        self.provider = ui.provider('preferences.css')
        self.prefswindow = self.builder.get_object('preferences_dialog')
        self.prefswindow.set_transient_for(self.window)
        self.prefsnotebook = self.builder.get_object('preferences_notebook')

        tabs = ('mpd', 'display', 'behavior', 'format', 'extras', 'plugins')

        for name in tabs:
            func = getattr(self, '%s_tab' % name)
            cbs = globals().get('%s_cbs' % name.capitalize())
            func(cbs)

        close_button = self.builder.get_object('preferences_closebutton')
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
        #frame.set_shadow_type(Gtk.ShadowType.NONE)
        controlbox = self.builder.get_object('connection_frame_label_widget')
        profiles = self.builder.get_object('connection_profiles')
        add_profile = self.builder.get_object('connection_add_profile')
        remove_profile = self.builder.get_object('connection_remove_profile')
        self._populate_profile_combo(profiles, self.config.profile_num,
            remove_profile)
        nameentry = self.builder.get_object('connection_name')
        hostentry = self.builder.get_object('connection_host')
        portentry = self.builder.get_object('connection_port')
        direntry = self.builder.get_object('connection_dir')
        self.direntry = direntry
        direntry.connect('selection-changed', self._direntry_changed,
            profiles)
        passwordentry = self.builder.get_object('connection_password')
        autoconnect = self.builder.get_object('connection_autoconnect')
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

    def extras_tab(self, cbs):
        """Construct and layout the extras tab"""
        if not self.scrobbler.imported():
            self.config.as_enabled = False

        as_checkbox = self.builder.get_object('scrobbler_check')
        as_checkbox.set_active(self.config.as_enabled)
        as_user_label = self.builder.get_object('scrobbler_username_label')
        as_user_entry = self.builder.get_object('scrobbler_username_entry')
        as_user_entry.set_text(self.config.as_username)
        as_user_entry.connect('changed', self._as_username_changed)
        as_pass_label = self.builder.get_object('scrobbler_password_label')
        as_pass_entry = self.builder.get_object('scrobbler_password_entry')
        as_pass_entry.set_text(self.config.as_password_md5)
        as_pass_entry.connect('changed', self._as_password_changed)
        display_notification = self.builder.get_object('notification_check')
        display_notification.set_active(self.config.show_notification)

        time_names = ["%s %s" %
            (i , ngettext('second', 'seconds', int(i)))
            for i in cbs.popuptimes if i != _('Entire song')]
        notification_options = self.builder.get_object('notification_time_combo')
        for time in time_names:
            notification_options.append_text(time)
        notification_options.connect('changed', self._notiftime_changed)
        notification_options.set_active(self.config.popup_option)
        notification_locs = self.builder.get_object('notification_loc_combo')
        notification_locs.set_active(self.config.traytips_notifications_location)
        notification_locs.connect('changed', self._notiflocation_changed)
        notifhbox = self.builder.get_object('notification_box')
        display_notification.connect('toggled', cbs.notif_toggled,
            notifhbox)
        if not self.config.show_notification:
            notifhbox.set_sensitive(False)

        crossfadespin = self.builder.get_object('crossfade_time')
        crossfadespin.set_value(self.config.xfade)
        crossfadespin.connect('value-changed', cbs.crossfade_changed)
        crossfadelabel2 = self.builder.get_object('crossfade_label')
        crossfadelabel3 = self.builder.get_object('crossfade_extra_label')
        crossfadecheck = self.builder.get_object('crossfade_check')
        crossfadecheck.connect('toggled',
            self._crossfadecheck_toggled, crossfadespin,
            crossfadelabel2, crossfadelabel3)
        crossfadecheck.connect('toggled', cbs.crossfade_toggled,
            crossfadespin)
        crossfadecheck.set_active(self.config.xfade_enabled)
        crossfadecheck.toggled() # Force the toggled callback

        as_checkbox.connect('toggled', self._as_enabled_toggled,
            as_user_entry, as_pass_entry, as_user_label,
            as_pass_label)
        if not self.config.as_enabled or not self.scrobbler.imported():
            for widget in (as_user_entry, as_pass_entry,
                    as_user_label, as_pass_label):
                widget.set_sensitive(False)

    def display_tab(self, cbs):
        """Construct and layout the display tab"""

        art = self.builder.get_object('art_check')
        art.set_active(self.config.show_covers)
        stylized_combo = self.builder.get_object('art_style_combo')
        stylized_combo.set_active(self.config.covers_type)
        stylized_combo.connect('changed', cbs.stylized_toggled)
        art_prefs = self.builder.get_object('art_preferences')
        art_prefs.set_sensitive(self.config.show_covers)
        art_combo = self.builder.get_object('art_search_combo')
        art_combo.set_active(self.config.covers_pref)
        art_combo.connect('changed', self._config_widget_active, 'covers_pref')

        #FIXME move into preferences_display.ui?
        art_location = self.builder.get_object('art_save_combo')
        for item in ["%s/%s" % (_("SONG_DIR"), item)
            for item in ("cover.jpg", "album.jpg", "folder.jpg",
                self.config.art_location_custom_filename or _("custom"))]:
            art_location.append_text(item)
        art_location.set_active(self.config.art_location)
        art_location.connect('changed', self._art_location_changed)

        art.connect('toggled', cbs.art_toggled, art_prefs)
        playback = self.builder.get_object('playback_buttons_check')
        playback.set_active(self.config.show_playback)
        playback.connect('toggled', cbs.playback_toggled)
        progress = self.builder.get_object('progressbar_check')
        progress.set_active(self.config.show_progress)
        progress.connect('toggled', cbs.progress_toggled)
        statusbar = self.builder.get_object('statusbar_check')
        statusbar.set_active(self.config.show_statusbar)
        statusbar.connect('toggled', cbs.statusbar_toggled)
        lyrics = self.builder.get_object('lyrics_check')
        lyrics.set_active(self.config.show_lyrics)
        lyrics_location = self.builder.get_object('lyrics_save_combo')
        lyrics_location.set_active(self.config.lyrics_location)
        lyrics_location.connect('changed', self._lyrics_location_changed)
        lyrics_location_hbox = self.builder.get_object('lyrics_preferences')
        lyrics_location_hbox.set_sensitive(self.config.show_lyrics)
        lyrics.connect('toggled', cbs.lyrics_toggled, lyrics_location_hbox)
        trayicon = self.builder.get_object('tray_icon_check')
        self.display_trayicon = trayicon
        trayicon.set_active(self.config.show_trayicon)
        trayicon.set_sensitive(cbs.trayicon_available)

    def behavior_tab(self, cbs):
        """Construct and layout the behavior tab"""

        frame = self.builder.get_object('behavior_frame')
        sticky = self.builder.get_object('behavior_sticky_check')
        sticky.set_active(self.config.sticky)
        sticky.connect('toggled', cbs.sticky_toggled)
        ontop = self.builder.get_object('behavior_ontop_check')
        ontop.set_active(self.config.ontop)
        ontop.connect('toggled', cbs.ontop_toggled)
        decor = self.builder.get_object('behavior_decor_check')
        decor.set_active(not self.config.decorated)
        decor.connect('toggled', cbs.decorated_toggled, self.prefswindow)
        minimize = self.builder.get_object('behavior_minimize_check')
        minimize.set_active(self.config.minimize_to_systray)
        minimize.connect('toggled', self._config_widget_active,
            'minimize_to_systray')
        self.display_trayicon.connect('toggled', cbs.trayicon_toggled,
            minimize)
        minimize.set_sensitive(cbs.trayicon_in_use)

        update_start = self.builder.get_object('misc_updatestart_check')
        update_start.set_active(self.config.update_on_start)
        update_start.connect('toggled', self._config_widget_active,
            'update_on_start')
        exit_stop = self.builder.get_object('misc_exit_stop_check')
        exit_stop.set_active(self.config.stop_on_exit)
        exit_stop.connect('toggled', self._config_widget_active,
            'stop_on_exit')
        infofile_usage = self.builder.get_object('misc_infofile_usage_check')
        infofile_usage.set_active(self.config.use_infofile)
        infopath_options = self.builder.get_object('misc_infofile_entry')
        infopath_options.set_text(self.config.infofile_path)
        infopath_options.connect('focus_out_event',
                    cbs.infofile_changed)
        infopath_options.connect('activate', cbs.infofile_changed, None)
        if not self.config.use_infofile:
            infopath_options.set_sensitive(False)
        infofile_usage.connect('toggled', self._infofile_toggled,
            infopath_options)

    def format_tab(self, cbs):
        """Construct and layout the format tab"""

        playlist_entry = self.builder.get_object('format_playlist_entry')
        playlist_entry.set_text(self.config.currentformat)
        library_entry = self.builder.get_object('format_library_entry')
        library_entry.set_text(self.config.libraryformat)
        window_entry = self.builder.get_object('format_window_entry')
        window_entry.set_text(self.config.titleformat)
        current1_entry = self.builder.get_object('format_current1_entry')
        current1_entry.set_text(self.config.currsongformat1)
        current2_entry = self.builder.get_object('format_current2_entry')
        current2_entry.set_text(self.config.currsongformat2)
        entries = [playlist_entry, library_entry, window_entry, current1_entry,
                   current2_entry]

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

        format_grid = self.builder.get_object('format_avail_descs')
        codeset = formatting.formatcodes
        codes = (codeset[:len(codeset) // 2],
                 codeset[len(codeset) // 2:])
        for column_base, codegroup in enumerate(codes):
            column = column_base * 2
            for row, code in enumerate(codegroup):
                format_code = ui.label(text='%{}'.format(code.code))
                context = format_code.get_style_context()
                context.add_class('format_code')
                format_desc = ui.label(text=code.description)
                format_grid.attach(format_code, column, row, 1, 1)
                format_grid.attach(format_desc, column + 1, row, 1, 1)

        additionalinfo = self.builder.get_object('format_additional_label')
        # FIXME need to either separate markup from localized strings OR
        # include markup in the strings and let the translators work around them
        row = len(codes[0])
        enclosed_code = ui.label(text='{ }')
        context = enclosed_code.get_style_context()
        context.add_class('format_code')
        enclosed_desc = ui.label(
            text=_('Info displayed only if all enclosed tags are defined'))
        column_code = ui.label(text='|')
        context = column_code.get_style_context()
        context.add_class('format_code')
        column_desc = ui.label(
            text=_('Creates columns in the current playlist'))

        # Dummy row
        format_grid.attach(ui.label(), 0, row, 4, 1)
        row += 1
        format_grid.attach(enclosed_code, 0, row, 1, 1)
        format_grid.attach(enclosed_desc, 1, row, 3, 1)
        row += 1
        format_grid.attach(column_code, 0, row, 1, 1)
        format_grid.attach(column_desc, 1, row, 3, 1)

    def plugins_tab(self, cbs=None):
        """Construct and layout the plugins tab"""

        self.plugin_UIManager = self.builder.get_object('plugins_ui_manager')
        menu_handlers = {
            "plugin_configure": self.plugin_configure,
            "plugin_about": self.plugin_about
        }
        self.builder.connect_signals(menu_handlers)

        self.pluginview = self.builder.get_object('plugins_treeview')
        self.pluginselection = self.pluginview.get_selection()
        plugindata = self.builder.get_object('plugins_store')
        self.pluginview.connect('button-press-event', self.plugin_click)

        plugincheckcell = self.builder.get_object('plugins_check_renderer')
        plugincheckcell.connect('toggled', self.plugin_toggled,
            (plugindata, 0))

        plugindata.clear()
        for plugin in pluginsystem.get_info():
            pb = self.plugin_get_icon_pixbuf(plugin)
            plugin_text = "<b>" + plugin.longname + "</b> " + plugin.version_string
            plugin_text += "\n" + plugin.description
            enabled = plugin.get_enabled()
            plugindata.append((enabled, pb, plugin_text))

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
            dialog = self.builder.get_object('custom_art_dialog')
            # Prompt user for playlist name:
            entry = self.builder.get_object('custom_art_entry')
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
            dialog.hide()
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
