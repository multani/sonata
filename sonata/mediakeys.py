import logging


def MultimediaKeys():
    logger = logging.getLogger(__name__)
    for handler in [GnomeSettingsDaemonHandler,
                   MMKeysHandler,
                   NullHandler]:
        if handler.is_supported():
            logger.info("Using multimedia keys handler: %s", handler)
            return handler()


class MMKeysHandler(object):
    @staticmethod
    def is_supported():
        try:
            import mmkeys
        except ImportError:
            return False
        return True

    def __init__(self):
        import mmkeys
        self._keys = mmkeys.MmKeys()
        self._callbacks = []

    def _connect(self, signal, cb):
        self._keys.connect(signal, cb)
        self._callbacks.append(cb)

    def enable(self, cb_play_pause, cb_stop, cb_prev, cb_next):
        if self.is_enabled():
            return
        self._connect("mm_prev", cb_prev)
        self._connect("mm_next", cp_next)
        self._connect("mm_playpause", cb_play_pause)
        self._connect("mm_stop", cb_stop)

    def is_enabled(self):
        return len(self._callbacks) > 0

    def disable(self):
        while self._callbacks:
            self.keys.disconnect_by_func(self._callbacks.pop())


class GnomeSettingsDaemonHandler(object):
    APP_NAME = "Sonata"
    DBUS_NAME = 'org.gnome.SettingsDaemon'

    @classmethod
    def is_supported(cls):
        try:
            import dbus
        except ImportError:
            return False

        bus = dbus.SessionBus()
        obj = bus.get_object('org.freedesktop.DBus', '/org/freedesktop/DBus')
        interface = dbus.Interface(obj, 'org.freedesktop.DBus')
        return interface.NameHasOwner(cls.DBUS_NAME)

    def __init__(self):
        self._callbacks = {}
        import dbus
        bus = dbus.SessionBus()
        obj = bus.get_object(self.DBUS_NAME, "/%s/MediaKeys" %
                             self.DBUS_NAME.replace('.', '/'))
        self._interface = dbus.Interface(obj, self.DBUS_NAME + '.MediaKeys')

    def enable(self, cb_pp, cb_stop, cb_prev, cb_next):
        if self.is_enabled():
            return
        self._callbacks = {
            'Play': cb_pp, 'PlayPause': cb_pp, 'Pause': cb_pp,
            'Stop': cb_stop,
            'Previous': cb_prev,
            'Next': cb_next,
        }
        self._interface.GrabMediaPlayerKeys(self.APP_NAME, 0)
        self._interface.connect_to_signal('MediaPlayerKeyPressed',
                                          self._handle_keys)

    def disable(self):
        self._interface.ReleaseMediaPlayerKeys(self.APP_NAME)
        self._callbacks.clear()

    def is_enabled(self):
        return len(self._callbacks) > 0

    def _handle_keys(self, app, key):
        if app != self.APP_NAME:
            return

        if key in self._callbacks:
            self._callbacks[key](None)


class NullHandler(object):
    @staticmethod
    def is_supported(): return True
    def enable(self, *args): pass
    def disable(self): pass
    def is_enabled(self): return True
