
"""
This plugin implements D-Bus features for Sonata:

 * Check that only one instance of Sonata is running at a time
 * Allow other programs to request the info popup, and to show or to toggle
   the main window visibility
 * Listen to Gnome 2.18+ multimedia key events

XXX Not a real plugin yet.

Example usage:
import dbus_plugin as dbus
self.dbus_service = dbus.SonataDBus(self.dbus_show, self.dbus_toggle,
                                    self.dbus_popup, self.dbus_fullscreen)
dbus.start_dbus_interface(toggle_arg, popup_arg)
dbus.init_gnome_mediakeys(self.mpd_pp, self.mpd_stop, self.mpd_prev,
                            self.mpd_next)
if not dbus.using_gnome_mediakeys():
        # do something else instead...
"""

import logging
import sys

try:
    import dbus
    import dbus.service
    import _dbus_bindings as dbus_bindings
    from dbus.mainloop.glib import DBusGMainLoop
    DBusGMainLoop(set_as_default=True)
    HAVE_DBUS = True
except:
    HAVE_DBUS = False


logger = logging.getLogger(__name__)


def using_dbus():
    return HAVE_DBUS

HAVE_GNOME_MMKEYS = False


def using_gnome_mediakeys():
    return HAVE_GNOME_MMKEYS


def init_gnome_mediakeys(mpd_pp, mpd_stop, mpd_prev, mpd_next):
    global HAVE_GNOME_MMKEYS
    if HAVE_DBUS:
        try:
            bus = dbus.SessionBus()
            dbusObj = bus.get_object('org.freedesktop.DBus',
                                     '/org/freedesktop/DBus')
            dbusInterface = dbus.Interface(dbusObj,
                                            'org.freedesktop.DBus')
            if dbusInterface.NameHasOwner('org.gnome.SettingsDaemon'):
                try:
                    # mmkeys for gnome 2.22+
                    settingsDaemonObj = bus.get_object(
                        'org.gnome.SettingsDaemon',
                        '/org/gnome/SettingsDaemon/MediaKeys')
                    settingsDaemonInterface = dbus.Interface(settingsDaemonObj,
                                        'org.gnome.SettingsDaemon.MediaKeys')
                    settingsDaemonInterface.GrabMediaPlayerKeys('Sonata', 0)
                except:
                    # mmkeys for gnome 2.18+
                    settingsDaemonObj = bus.get_object(
                        'org.gnome.SettingsDaemon',
                        '/org/gnome/SettingsDaemon')
                    settingsDaemonInterface = dbus.Interface(settingsDaemonObj,
                                                    'org.gnome.SettingsDaemon')
                    settingsDaemonInterface.GrabMediaPlayerKeys('Sonata', 0)
                settingsDaemonInterface.connect_to_signal(
                    'MediaPlayerKeyPressed', lambda app,
                    key: mediaPlayerKeysCallback(mpd_pp, mpd_stop, mpd_prev,
                                                mpd_next, app, key))
                HAVE_GNOME_MMKEYS = True
        except:
            pass


def mediaPlayerKeysCallback(mpd_pp, mpd_stop, mpd_prev, mpd_next, app, key):
    if app == 'Sonata':
        if key in ('Play', 'PlayPause', 'Pause'):
            mpd_pp(None)
        elif key == 'Stop':
            mpd_stop(None)
        elif key == 'Previous':
            mpd_prev(None)
        elif key == 'Next':
            mpd_next(None)


def get_session_bus():
    try:
        return dbus.SessionBus()
    except Exception:
        logger.error(
            _('Sonata failed to connect to the D-BUS session bus: '
              'Unable to determine the address of the message bus '
              '(try \'man dbus-launch\' and \'man dbus-daemon\' '
              'for help)")'))
        raise


def execute_remote_commands(toggle=False, popup=False, fullscreen=False,
                            start=False):
    try:
        bus = get_session_bus()
        obj = bus.get_object('org.MPD', '/org/MPD/Sonata')
        if toggle:
            obj.toggle(dbus_interface='org.MPD.SonataInterface')
        if popup:
            obj.popup(dbus_interface='org.MPD.SonataInterface')
        if fullscreen:
            obj.fullscreen(dbus_interface='org.MPD.SonataInterface')
        sys.exit()
    except Exception:
        logger.warning(_("Failed to execute remote commands."))
        if start is None or start:
            logger.info(_("Starting Sonata instead..."))
        else:
            # TODO: should we log the exception here?
            logger.critical(_("Maybe Sonata is not running?"))
            sys.exit(1)


def start_dbus_interface():
    if HAVE_DBUS:
        try:
            bus = get_session_bus()

            retval = bus.request_name("org.MPD.Sonata",
                                      dbus_bindings.NAME_FLAG_DO_NOT_QUEUE)

            if retval in (dbus_bindings.REQUEST_NAME_REPLY_PRIMARY_OWNER,
                          dbus_bindings.REQUEST_NAME_REPLY_ALREADY_OWNER):
                pass
            elif retval in (dbus_bindings.REQUEST_NAME_REPLY_EXISTS,
                            dbus_bindings.REQUEST_NAME_REPLY_IN_QUEUE):
                logger.info(
                    _('An instance of Sonata is already running. '
                      'Showing it...'))
                try:
                    obj = bus.get_object('org.MPD', '/org/MPD/Sonata')
                    obj.show(dbus_interface='org.MPD.SonataInterface')
                    sys.exit()
                except Exception:
                    # TODO: should we log the exception here?
                    logger.critical(_("Failed to execute remote command."))
                    sys.exit(1)
        except Exception:
            pass
        except SystemExit:
            raise

if HAVE_DBUS:

    class SonataDBus(dbus.service.Object):

        def __init__(self, dbus_show, dbus_toggle, dbus_popup, dbus_fullscreen):
            self.dbus_show = dbus_show
            self.dbus_toggle = dbus_toggle
            self.dbus_popup = dbus_popup
            self.dbus_fullscreen = dbus_fullscreen
            session_bus = get_session_bus()
            bus_name = dbus.service.BusName('org.MPD', bus=session_bus)
            object_path = '/org/MPD/Sonata'
            dbus.service.Object.__init__(self, bus_name, object_path)

        @dbus.service.method('org.MPD.SonataInterface')
        def show(self):
            self.dbus_show()

        @dbus.service.method('org.MPD.SonataInterface')
        def toggle(self):
            self.dbus_toggle()

        @dbus.service.method('org.MPD.SonataInterface')
        def popup(self):
            self.dbus_popup()

        @dbus.service.method('org.MPD.SonataInterface')
        def fullscreen(self):
            self.dbus_fullscreen()
