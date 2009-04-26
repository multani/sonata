
import sys, getopt

try:
    import version
except ImportError:
    import svnversion as version

# the mpd commands need a connection to server and exit without gui
mpd_cmds = ["play", "pause", "stop", "next", "prev", "pp", "info",
            "status", "repeat", "random"]
# toggle and popup need d-bus and don't always need gui
# version and help don't need anything and exit without gui
# hidden and visible are only applicable when gui is launched
# profile and no-start don't need anything
short_opts = "tpnvh"
long_opts = ["toggle", "popup", "no-start", "version", "help", "hidden", "visible", "profile="]

class Args(object):
    def __init__(self):
        self.skip_gui = False

        self.opts = []
        self.args = []

        self.toggle_arg = None
        self.popup_arg = None
        self.start_arg = None
        self.start_visibility = None
        self.arg_profile = None

    def should_skip_gui(self):
        return self.skip_gui

    def parse(self, argv):
        """Parse the command line arguments.

        Separates options and arguments from the given argument list,
        checks their validity."""
        try:
            self.opts, self.args = getopt.getopt(argv[1:], short_opts, long_opts)
            for a in self.args:
                if a in mpd_cmds:
                    self.skip_gui = True
                else:
                    self.print_usage()
                    sys.exit(1)
        except getopt.GetoptError:
            # print help information and exit:
            self.print_usage()
            sys.exit(1)

    def process_options(self):
        """If options were passed, perform action on them."""
        for o, a in self.opts:
            if o in ("-t", "--toggle"):
                self.toggle_arg = True
                self.start_visibility = True
            elif o in ("-p", "--popup"):
                self.popup_arg = True
                if self.start_visibility is None:
                    self.start_visibility = False
            elif o in ("-n", "--no-start"):
                self.start_arg = False
            elif o in ("-v", "--version"):
                self.print_version()
                sys.exit()
            elif o in ("-h", "--help"):
                self.print_usage()
                sys.exit()
            elif o in ("--visible"):
                self.start_visibility = True
            elif o in ("--hidden"):
                self.start_visibility = False
            elif o in ("--profile"):
                self.arg_profile = a

        if self.toggle_arg or self.popup_arg:
            import dbus_plugin as dbus
            if not dbus.using_dbus():
                print _("The toggle and popup arguments require D-Bus. Aborting.")
                sys.exit(1)

            dbus.execute_remote_commands(self.toggle_arg, self.popup_arg, self.start_arg)

    def execute_cmds(self):
        """If arguments were passed, perform action on them."""
        if self.args:
            main = CliMain(self)
            mpdh.suppress_mpd_errors(True)
            main.mpd_connect()
            for a in self.args:
                main.execute_cmd(a)
            sys.exit()

    def print_version(self):
        print _("Version") + ": Sonata", (version.VERSION)
        print _("Website") + ": http://sonata.berlios.de/"

    def print_usage(self):
        self.print_version()
        print ""
        print _("Usage: sonata [OPTION]... [COMMAND]...")
        print ""
        print _("Options:")
        print "  -h, --help           " + _("Show this help and exit")
        print "  -p, --popup          " + _("Popup song notification (requires D-Bus)")
        print "  -t, --toggle         " + _("Toggles whether the app is minimized")
        print "                       " + _("to tray or visible (requires D-Bus)")
        print "  -n, --no-start       " + _("Don't start app if D-Bus commands fail")
        print "  -v, --version        " + _("Show version information and exit")
        print "  --hidden             " + _("Start app hidden (requires systray)")
        print "  --visible            " + _("Start app visible (requires systray)")
        print "  --profile=[NUM]      " + _("Start with profile [NUM]")
        print ""
        print _("Commands:")
        print "  play                 " + _("Play song in playlist")
        print "  pause                " + _("Pause currently playing song")
        print "  stop                 " + _("Stop currently playing song")
        print "  next                 " + _("Play next song in playlist")
        print "  prev                 " + _("Play previous song in playlist")
        print "  pp                   " + _("Toggle play/pause; plays if stopped")
        print "  repeat               " + _("Toggle repeat mode")
        print "  random               " + _("Toggle random mode")
        print "  info                 " + _("Display current song info")
        print "  status               " + _("Display MPD status")

    def apply_profile_arg(self, config):
        if self.arg_profile:
            try:
                a = int(self.arg_profile)
                if a > 0 and a <= len(config.profile_names):
                    config.profile_num = a-1
                    print _("Starting Sonata with profile %s...") % config.profile_names[config.profile_num]
                else:
                    print _("%d is not an available profile number.") % a
                    print _("Profile numbers must be between 1 and %d.") % len(config.profile_names)
                    sys.exit(1)
            except ValueError:
                print _("Python is unable to interpret %s as a number.") % self.arg_profile
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
                    time = misc.convert_time(int(mpdh.get(self.songinfo, 'time')))
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
