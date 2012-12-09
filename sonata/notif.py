from sonata import ui


class TooltipNotification(object):
    def __init__(self):
        builder = ui.builder('sonata.ui')
        self.traytips = TrayIconTips()

        # FIXME: connection to artwork
        self.artwork.set_tray_album_image(self.tray_album_image)

        # Song notification window:

        self.tray_album_image = builder.get_object('tray_album_image')
        self.tray_current_label1 = builder.get_object('tray_label_1')
        self.tray_current_label2 = builder.get_object('tray_label_2')
        self.tray_progressbar = builder.get_object('tray_progressbar')

        # FIXME: config
        #if not self.config.show_covers:
            #ui.hide(self.tray_album_image)
        #if not self.config.show_progress:
            #ui.hide(self.tray_progressbar)

        tray_v_box = builder.get_object('tray_v_box')
        tray_v_box.show_all()
        self.traytips.add_widget(tray_v_box)

        # FIXME: Width of notification is 30% of screen's width
        self.notification_width = 300
        #screen = self.window.get_screen()
        #_pscreen, px, py, _mods = screen.get_display().get_pointer()
        #monitor_num = screen.get_monitor_at_point(px, py)
        #monitor = screen.get_monitor_geometry(monitor_num)
        #self.notification_width = int(monitor.width * 0.30)
        #if self.notification_width > consts.NOTIFICATION_WIDTH_MAX:
            #self.notification_width = consts.NOTIFICATION_WIDTH_MAX
        #elif self.notification_width < consts.NOTIFICATION_WIDTH_MIN:
            #self.notification_width = consts.NOTIFICATION_WIDTH_MIN


        self.traytips.add_events(Gdk.EventMask.BUTTON_PRESS_MASK)
        self.traytips.connect('button-press-event', self.on_traytips_press)

    def on_traytips_press(self, _widget, _event):
        if self.traytips.get_property('visible'):
            self.traytips._remove_timer()


    # FIXME: save location in config
    #notification_locs.connect('changed', self._notiflocation_changed)
    #notification_locs.set_active(self.config.traytips_notifications_location)
    #self.config.traytips_notifications_location = combobox.get_active()


    def on_currsong_notify(self, force_popup=False):
        if self.fullscreen_window.get_property('visible'):
            return

        if not self.sonata_loaded:
            return

        if self.status_is_play_or_pause():
            if self.config.show_covers:
                self.traytips.set_size_request(self.notification_width, -1)
            else:
                self.traytips.set_size_request(
                    self.notification_width - 100, -1)
        else:
            self.traytips.set_size_request(-1, -1)

        if self.config.show_notification or force_popup:
            GObject.source_remove(self.traytips.notif_handler)

            if self.status_is_play_or_pause():
                self.traytips.notifications_location = \
                        self.config.traytips_notifications_location
                self.traytips.use_notifications_location = True
                if self.tray_icon.is_visible():
                    self.traytips._real_display(self.tray_icon)
                else:
                    self.traytips._real_display(None)
                if self.config.popup_option != len(self.popuptimes)-1:
                    if force_popup and \
                       not self.config.show_notification:
                        # Used -p argument and notification is disabled
                        # in player; default to 3 seconds
                        timeout = 3000
                    else:
                        timeout = \
                                int(self.popuptimes[
                                    self.config.popup_option]) * 1000
                    self.traytips.notif_handler = \
                            GObject.timeout_add(timeout,
                                                self.traytips.hide)
                else:
                    # -1 indicates that the timeout should be forever.
                    # We don't want to pass None, because then Sonata
                    # would think that there is no current notification
                    self.traytips.notif_handler = -1
            else:
                self.traytips.hide()
        elif self.traytips.get_property('visible'):
            self.traytips._real_display(self.tray_icon)








class TrayIconTips(Gtk.Window):
    """Custom tooltips derived from Gtk.Window() that allow for markup text and
    multiple widgets, e.g. a progress bar. ;)"""
    MARGIN = 4

    def __init__(self):
        GObject.GObject.__init__(self, type=Gtk.WindowType.POPUP)
        # from gtktooltips.c:gtk_tooltips_force_window
        self.set_app_paintable(True)
        self.set_resizable(False)
        self.set_name("gtk-tooltips")

        self._show_timeout_id = -1
        self.timer_tag = None
        self.notif_handler = None
        self.use_notifications_location = False
        self.notifications_location = 0

    def _calculate_pos(self, tray_icon):
        if tray_icon is not None:
            x, y, _, height = tray_icon.compute_pos()
        size = self.size_request()
        w = size.width
        h = size.height

        screen = self.get_screen()
        pointer_screen, px, py, _ = screen.get_display().get_pointer()
        if pointer_screen != screen:
            px = x
            py = y
        try:
            # Use the monitor that the systemtray icon is on
            monitor_num = screen.get_monitor_at_point(x, y)
        except:
            # No systemtray icon, use the monitor that the pointer is on
            monitor_num = screen.get_monitor_at_point(px, py)
        monitor = screen.get_monitor_geometry(monitor_num)

        try:
            # If the tooltip goes off the screen horizontally, realign it so
            # that it all displays.
            if (x + w) > monitor.x + monitor.width:
                x = monitor.x + monitor.width - w
            # If the tooltip goes off the screen vertically (i.e. the system
            # tray icon is on the bottom of the screen), realign the icon so
            # that it shows above the icon.
            if ((y + h + height + self.MARGIN) >
                monitor.y + monitor.height):
                y = y - h - self.MARGIN
            else:
                y = y + height + self.MARGIN
        except:
            pass

        if not self.use_notifications_location:
            try:
                return x, y
            except:
                #Fallback to top-left:
                return monitor.x, monitor.y
        elif self.notifications_location == 0:
            try:
                return x, y
            except:
                #Fallback to top-left:
                return monitor.x, monitor.y
        elif self.notifications_location == 1:
            return monitor.x, monitor.y
        elif self.notifications_location == 2:
            return monitor.x + monitor.width - w, monitor.y
        elif self.notifications_location == 3:
            return monitor.x, monitor.y + monitor.height - h
        elif self.notifications_location == 4:
            return monitor.x + monitor.width - w, \
                    monitor.y + monitor.height - h
        elif self.notifications_location == 5:
            return monitor.x + (monitor.width - w) / 2, \
                    monitor.y + (monitor.height - h) / 2

    def _start_delay(self, tray_icon):
        self.timer_tag = GObject.timeout_add(500, self._tips_timeout,
                                             tray_icon)

    def _tips_timeout(self, tray_icon):
        self.use_notifications_location = False
        self._real_display(tray_icon)

    def _remove_timer(self):
        self.hide()
        if self.timer_tag:
            GObject.source_remove(self.timer_tag)
        self.timer_tag = None

    def _real_display(self, tray_icon):
        x, y = self._calculate_pos(tray_icon)
        self.move(x, y)
        self.show()

    # Public API

    def hide(self):
        Gtk.Window.hide(self)
        GObject.source_remove(self._show_timeout_id)
        self._show_timeout_id = -1
        self.notif_handler = None

    def add_widget(self, widget_to_add):
        self.add(widget_to_add)



    def _tooltip_show_manually(self):
        # Since there is no signal to connect to when the user puts their
        # mouse over the trayicon, we will check the mouse position
        # manually and show/hide the window as appropriate. This is called
        # every iteration. Note: This should not occur if self.traytips.notif_
        # handler has a value, because that means that the tooltip is already
        # visible, and we don't want to override that setting simply because
        # the user's cursor is not over the tooltip.
        if self.traymenu.get_property('visible') and \
           self.traytips.notif_handler != -1:
            self.traytips._remove_timer()
        elif not self.traytips.notif_handler:
            _pscreen, px, py, _mods = \
                    self.window.get_screen().get_display().get_pointer()
            x, y, width, height = self.compute_pos()
            if px >= x and px <= x + width and py >= y and py <= y + height:
                self.traytips._start_delay(self)
            else:
                self.traytips._remove_timer()






# FIXME in main.update_cursong(self):
            # We must show the trayprogressbar and trayalbumeventbox
            # before changing self.cursonglabel (and consequently calling
            # self.playing_song_change()) in order to ensure that the
            # notification popup will have the correct height when being
            # displayed for the first time after a stopped state.
            if self.config.show_progress:
                self.tray_progressbar.show()
