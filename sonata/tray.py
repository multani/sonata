
import gtk, gobject

class TrayIconTips(gtk.Window):
    """Custom tooltips derived from gtk.Window() that allow for markup text and multiple widgets, e.g. a progress bar. ;)"""
    MARGIN = 4

    def __init__(self):
        gtk.Window.__init__(self, gtk.WINDOW_POPUP)
        # from gtktooltips.c:gtk_tooltips_force_window
        self.set_app_paintable(True)
        self.set_resizable(False)
        self.set_name("gtk-tooltips")
        self.connect('expose-event', self._on__expose_event)

        self._show_timeout_id = -1
        self.timer_tag = None
        self.notif_handler = None
        self.use_notifications_location = False
        self.notifications_location = 0
        self.widget = None

    def _calculate_pos(self, widget):
        if widget is not None:
            try:
                x, y = widget.window.get_origin()
                if widget.flags() & gtk.NO_WINDOW:
                    x += widget.allocation.x
                    y += widget.allocation.y
                height = widget.allocation.height
            except:
                _icon_screen, icon_rect, _icon_orient = widget.get_geometry()
                x = icon_rect[0]
                y = icon_rect[1]
                height = icon_rect[3]
        w, h = self.size_request()

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
            # If the tooltip goes off the screen horizontally, realign it so that
            # it all displays.
            if (x + w) > monitor.x + monitor.width:
                x = monitor.x + monitor.width - w
            # If the tooltip goes off the screen vertically (i.e. the system tray
            # icon is on the bottom of the screen), realign the icon so that it
            # shows above the icon.
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
            return monitor.x + monitor.width - w, monitor.y + monitor.height - h
        elif self.notifications_location == 5:
            return monitor.x + (monitor.width - w)/2, monitor.y + (monitor.height - h)/2

    def _event_handler (self, widget):
        widget.connect_after("event-after", self._motion_cb)

    def _motion_cb (self, widget, event):
        if self.notif_handler != None:
            return
        if event.type == gtk.gdk.LEAVE_NOTIFY:
            self._remove_timer()
        if event.type == gtk.gdk.ENTER_NOTIFY:
            self._start_delay(widget)

    def _start_delay (self, widget):
        self.timer_tag = gobject.timeout_add(500, self._tips_timeout, widget)

    def _tips_timeout (self, widget):
        self.use_notifications_location = False
        self._real_display(widget)

    def _remove_timer(self):
        self.hide()
        if self.timer_tag:
            gobject.source_remove(self.timer_tag)
        self.timer_tag = None

    # from gtktooltips.c:gtk_tooltips_paint_window
    def _on__expose_event(self, window, _event):
        w, h = window.size_request()
        window.style.paint_flat_box(window.window,
                                    gtk.STATE_NORMAL, gtk.SHADOW_OUT,
                                    None, window, "tooltip",
                                    0, 0, w, h)
        return False

    def _real_display(self, widget):
        x, y = self._calculate_pos(widget)
        self.move(x, y)
        self.show()

    # Public API

    def hide(self):
        gtk.Window.hide(self)
        gobject.source_remove(self._show_timeout_id)
        self._show_timeout_id = -1
        self.notif_handler = None

    def display(self, widget):
        if not self._label.get_text():
            return

        if self._show_timeout_id != -1:
            return

        self._show_timeout_id = gobject.timeout_add(500, self._real_display, widget)

    def set_tip (self, widget):
        self.widget = widget
        self._event_handler (self.widget)

    def add_widget (self, widget_to_add):
        self.add(widget_to_add)
