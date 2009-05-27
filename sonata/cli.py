
import sys
from optparse import OptionParser

try:
    import version
except ImportError:
    import svnversion as version

# the mpd commands need a connection to server and exit without gui
mpd_cmds = ["play", "pause", "stop", "next", "prev", "pp", "info",
            "status", "repeat", "random"]

class Args(object):
    def __init__(self):
        self.skip_gui = False
        self.start_visibility = None

    def should_skip_gui(self):
        return self.skip_gui

    def parse(self, argv):
        """Parse the command line arguments.

        Separates options and arguments from the given argument list,
        checks their validity."""

        # toggle and popup need d-bus and don't always need gui
        # version and help don't need anything and exit without gui
        # hidden and visible are only applicable when gui is launched
        # profile and no-start don't need anything
        _usage = "\n".join((_("%prog [OPTION]... [COMMAND]...")+"\n",
         _("Commands:"),
        "  play            %s" % _("play song in playlist"),
        "  pause           %s" % _("pause currently playing song"),
        "  stop            %s" % _("stop currently playing song"),
        "  next            %s" % _("play next song in playlist"),
        "  prev            %s" % _("play previous song in playlist"),
        "  pp              %s" % _("toggle play/pause; plays if stopped"),
        "  repeat          %s" % _("toggle repeat mode"),
        "  random          %s" % _("toggle random mode"),
        "  info            %s" % _("display current song info"),
        "  status          %s" % _("display MPD status"),
        ))
        _version = "%prog " + version.VERSION

        parser = OptionParser(usage=_usage, version=_version)
        parser.add_option("-p", "--popup", dest="popup",
                  action="store_true",
                  help=_("popup song notification (requires D-Bus)"))
        parser.add_option("-t", "--toggle", dest="toggle",
                  action="store_true",
                  help=_("toggles whether the app is minimized to the tray or visible (requires D-Bus)"))
        parser.add_option("-n", "--no-start", dest="start",
                  action="store_false",
                  help=_("don't start app if D-Bus commands fail"))
        parser.add_option("--hidden", dest="start_visibility",
                  action="store_false",
                  help=_("start app hidden (requires systray)"))
        parser.add_option("--visible", dest="start_visibility",
                  action="store_true",
                  help=_("start app visible (requires systray)"))
        parser.add_option("--profile", dest="profile", metavar="NUM",
                  help=_("start with profile NUM"), type=int)

        options, self.cmds = parser.parse_args(argv[1:])

        if options.toggle:
            options.start_visibility = True
        if options.popup and options.start_visibility is None:
            options.start_visibility = False
        self.start_visibility = options.start_visibility
        self.arg_profile = options.profile

        for cmd in self.cmds:
            if cmd in mpd_cmds:
                self.skip_gui = True
            else:
                parser.error(_("unknown command %s") % cmd)

        if options.toggle or options.popup:
            import dbus_plugin as dbus
            if not dbus.using_dbus():
                print _("toggle and popup options require D-Bus. Aborting.")
                sys.exit(1)

            dbus.execute_remote_commands(options.toggle,
                             options.popup,
                             options.start)


    def execute_cmds(self):
        """If arguments were passed, perform action on them."""
        if self.cmds:
            main = CliMain(self)
            mpdh.suppress_mpd_errors(True)
            main.mpd_connect()
            for cmd in self.cmds:
                main.execute_cmd(cmd)
            sys.exit()

    def apply_profile_arg(self, config):
        if self.arg_profile:
            a = self.arg_profile
            if a > 0 and a <= len(config.profile_names):
                config.profile_num = a-1
                print _("Starting Sonata with profile %s...") % config.profile_names[config.profile_num]
            else:
                print _("%d is not an available profile number.") % a
                print _("Profile numbers must be between 1 and %d.") % len(config.profile_names)
                sys.exit(1)

class CliMain(object):
    def __init__(self, args):
        global os, mpd, config, library, mpdh, misc
        import os
        import mpd
        import config
        import library
        import mpdhelper as mpdh
        import misc

        self.config = config.Config(_('Default Profile'), _("by") + " %A " + _("from") + " %B", library.library_set_data)
        self.config.settings_load_real(library.library_set_data)
        args.apply_profile_arg(self.config)

        self.client = mpd.MPDClient()

    def mpd_connect(self):
        host, port, password = misc.mpd_env_vars()
        if not host:
            host = self.config.host[self.config.profile_num]
        if not port:
            port = self.config.port[self.config.profile_num]
        if not password:
            password = self.config.password[self.config.profile_num]

        mpdh.call(self.client, 'connect', host, port)
        if len(password) > 0:
            mpdh.call(self.client, 'password', password)

    def execute_cmd(self, cmd):
        self.status = mpdh.status(self.client)
        if not self.status:
            print _("Unable to connect to MPD.\nPlease check your Sonata preferences or MPD_HOST/MPD_PORT environment variables.")
            sys.exit(1)

        self.songinfo = mpdh.currsong(self.client)

        if cmd == "play":
            mpdh.call(self.client, 'play')
        elif cmd == "pause":
            mpdh.call(self.client, 'pause', 1)
        elif cmd == "stop":
            mpdh.call(self.client, 'stop')
        elif cmd == "next":
            mpdh.call(self.client, 'next')
        elif cmd == "prev":
            mpdh.call(self.client, 'previous')
        elif cmd == "random":
            if self.status['random'] == '0':
                mpdh.call(self.client, 'random', 1)
            else:
                mpdh.call(self.client, 'random', 0)
        elif cmd == "repeat":
            if self.status['repeat'] == '0':
                mpdh.call(self.client, 'repeat', 1)
            else:
                mpdh.call(self.client, 'repeat', 0)
        elif cmd == "pp":
            if self.status['state'] in ['play']:
                mpdh.call(self.client, 'pause', 1)
            elif self.status['state'] in ['pause', 'stop']:
                mpdh.call(self.client, 'play')
        elif cmd == "info":
            if self.status['state'] in ['play', 'pause']:
                mpdh.conout (_("Title") + ": " + mpdh.get(self.songinfo, 'title'))
                mpdh.conout (_("Artist") + ": " + mpdh.get(self.songinfo, 'artist'))
                mpdh.conout (_("Album") + ": " + mpdh.get(self.songinfo, 'album'))
                mpdh.conout (_("Date") + ": " + mpdh.get(self.songinfo, 'date'))
                mpdh.conout (_("Track") + ": " + mpdh.get(self.songinfo, 'track', '0', False, 2))
                mpdh.conout (_("Genre") + ": " + mpdh.get(self.songinfo, 'genre'))
                mpdh.conout (_("File") + ": " + os.path.basename(mpdh.get(self.songinfo, 'file')))
                at, _length = [int(c) for c in self.status['time'].split(':')]
                at_time = misc.convert_time(at)
                try:
                    time = misc.convert_time(mpdh.get(self.songinfo, 'time', '', True))
                    print _("Time") + ": " + at_time + " / " + time
                except:
                    print _("Time") + ": " + at_time
                print _("Bitrate") + ": " + self.status.get('bitrate', '')
            else:
                print _("MPD stopped")
        elif cmd == "status":
            try:
                if self.status['state'] == 'play':
                    print _("State") + ": " + _("Playing")
                elif self.status['state'] == 'pause':
                    print _("State") + ": " + _("Paused")
                elif self.status['state'] == 'stop':
                    print _("State") + ": " + _("Stopped")
                if self.status['repeat'] == '0':
                    print _("Repeat") + ": " + _("Off")
                else:
                    print _("Repeat") + ": " + _("On")
                if self.status['random'] == '0':
                    print _("Random") + ": " + _("Off")
                else:
                    print _("Random") + ": " + _("On")
                print _("Volume") + ": " + self.status['volume'] + "/100"
                print _('Crossfade') + ": " + self.status['xfade'] + ' ' + gettext.ngettext('second', 'seconds', int(self.status['xfade']))
            except:
                pass
