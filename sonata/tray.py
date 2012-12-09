from gi.repository import Gtk, GObject


class TrayIcon(object):
    """Tray icon which use Gtk.StatusIcon"""

    def __init__(self, window, traymenu):
        self.statusicon = None
        self.window = window
        self.traymenu = traymenu

    def compute_pos(self):
        _ok, _screen, rect, _orient = self.statusicon.get_geometry()
        return (rect.x, rect.y, rect.height, rect.width)

    def initialize(self, on_click, on_scroll, on_activate):
        self.statusicon = Gtk.StatusIcon()
        self.statusicon.connect('activate', on_activate)
        self.statusicon.connect('button_press_event', on_click)
        self.statusicon.connect('scroll-event', on_scroll)

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
