
import os

from gi.repository import Gtk, GObject, Pango

from sonata import ui, img


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


class TrayIcon(object):
    """Tray icon which use Gtk.StatusIcon"""

    def __init__(self, window, traymenu, traytips):
        self.statusicon = None
        self.window = window
        self.traymenu = traymenu
        self.traytips = traytips

    def compute_pos(self):
        _ok, _screen, rect, _orient = self.statusicon.get_geometry()
        return (rect.x, rect.y, rect.height, rect.width)

    def initialize(self, on_click, on_scroll, on_activate):
        self.statusicon = Gtk.StatusIcon()
        self.statusicon.connect('activate', on_activate)
        self.statusicon.connect('button_press_event', on_click)
        self.statusicon.connect('scroll-event', on_scroll)
        GObject.timeout_add(250, self._iterate_status_icon)

    def is_visible(self):
        """Visible and/or notification activated"""
        return self.statusicon.is_embedded() and \
                self.statusicon.get_visible()

    def update_icon(self, icon_path):
        self.statusicon.set_from_file(icon_path)

    def show(self):
        self.statusicon.set_visible(True)

    def hide(self):
        self.statusicon.set_visible(False)

    def is_available(self):
        return self.statusicon.is_embedded()

    def _iterate_status_icon(self):
        if self.is_visible():
            self._tooltip_show_manually()
        GObject.timeout_add(250, self._iterate_status_icon)

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
