
import gettext
import locale
import logging
import os
from optparse import OptionParser
import sys

from sonata import config, misc, mpdhelper as mpdh
from sonata.version import version

# the mpd commands need a connection to server and exit without gui
mpd_cmds = ["play", "pause", "stop", "next", "prev", "pp", "info",
            "status", "repeat", "random"]


class Args(object):

    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.skip_gui = False
        self.start_visibility = None
        self.start_shell = False

    def parse(self, argv):
        """Parse the command line arguments.

        Separates options and arguments from the given argument list,
        checks their validity."""

        # toggle and popup and fullscreen need d-bus and don't always need gui
        # version and help don't need anything and exit without gui
        # hidden and visible are only applicable when gui is launched
        # profile and no-start don't need anything
        _usage = "\n".join((_("%prog [OPTION]... [COMMAND]...") + "\n",
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
        _version = "%prog " + version

        parser = OptionParser(usage=_usage, version=_version)
        parser.add_option("-p", "--popup", dest="popup",
                  action="store_true",
                  help=_("popup song notification (requires D-Bus)"))
        parser.add_option("-t", "--toggle", dest="toggle",
                  action="store_true",
                  help=_("toggles whether the app is minimized to the tray or visible (requires D-Bus)"))
        parser.add_option("-f", "--fullscreen", dest="fullscreen",
                  action="store_true",
                  help=_("go fullscreen (requires D-Bus)"))
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
        parser.add_option("--shell", dest="start_shell",
                  action="store_true",
                  help=_("start app with a interactive (ipython) shell"))
        parser.add_option("-v", "--verbose", dest="log_level",
                          action="append_const", const=-10,
                          help=_("Increase log verbosity"))
        parser.add_option("-q", "--quiet", dest="log_level",
                          action="append_const", const=10,
                          help=_("Decrease log verbosity"))
        parser.set_defaults(log_level=[logging.root.level])

        options, self.cmds = parser.parse_args(argv[1:])

        # Update default log level
        logging.root.setLevel(sum(options.log_level))

        if options.toggle:
            options.start_visibility = True
        if options.popup or options.fullscreen and options.start_visibility is None:
            options.start_visibility = False
        self.start_visibility = options.start_visibility
        self.arg_profile = options.profile
        self.start_shell = options.start_shell

        for cmd in self.cmds:
            if cmd in mpd_cmds:
                self.skip_gui = True
            else:
                parser.error(_("unknown command %s") % cmd)

        if options.toggle or options.popup or options.fullscreen:
            from sonata import dbus_plugin as dbus
            if not dbus.using_dbus():
                self.logger.critical(
                    _("toggle and popup options require D-Bus.  Aborting."))
                sys.exit(1)

            dbus.execute_remote_commands(options.toggle,
                             options.popup,
                             options.fullscreen,
                             options.start)

    def execute_cmds(self):
        """If arguments were passed, perform action on them."""
        if self.cmds:
            main = CliMain(self)
            main.mpd_connect()
            for cmd in self.cmds:
                main.execute_cmd(cmd)
            sys.exit()

    def apply_profile_arg(self, config):
        if self.arg_profile:
            a = self.arg_profile
            if a > 0 and a <= len(config.profile_names):
                config.profile_num = a-1
                self.logger.info(_("Starting Sonata with profile %s...") %
                                 config.profile_names[config.profile_num])
            else:
                self.logger.critical(
                    _("%d is not an available profile number.") % a)
                self.logger.critical(
                    _("Profile numbers must be between 1 and %d.") %
                    len(config.profile_names))
                sys.exit(1)


class CliMain(object):

    def __init__(self, args):
        global os, mpd, misc, config, mpdh
        import os
        import mpd
        from sonata import config, misc, mpdhelper as mpdh

        # This should disable processing for nearly all logging messages, as
        # long as no other handlers are configured for special loggers.
        # Note that using the "-v" command line argument is mostly useless in
        # this case...
        logging.root.setLevel(logging.CRITICAL)

        self.logger = logging.getLogger(__name__)
        self.config = config.Config(_('Default Profile'),
                                    _("by") + " %A " + _("from") + " %B")
        self.config.settings_load_real()
        args.apply_profile_arg(self.config)

        c = mpd.MPDClient()
        self.mpd = mpdh.MPDHelper(c)

    def mpd_connect(self):
        host, port, password = misc.mpd_env_vars()
        if not host:
            host = self.config.host[self.config.profile_num]
        if not port:
            port = self.config.port[self.config.profile_num]
        if not password:
            password = self.config.password[self.config.profile_num]

        self.mpd.connect(host, port)
        if password:
            self.mpd.password(password)

    def execute_cmd(self, cmd):
        self.status = self.mpd.status()
        if not self.status:
            self.logger.critical(_(
                'Unable to connect to MPD.\nPlease check your Sonata '
                'preferences or MPD_HOST/MPD_PORT environment variables.'))
            sys.exit(1)

        self.songinfo = self.mpd.currentsong()
        getattr(self, "_execute_%s" % cmd)()

    def _execute_play(self):
        self.mpd.play()

    def _execute_pause(self):
        self.mpd.pause(1)

    def _execute_stop(self):
        self.mpd.stop()

    def _execute_next(self):
        self.mpd.next()

    def _execute_prev(self):
        self.mpd.previous()

    def _execute_random(self):
        opt = int(not int(self.status["random"]))
        self.mpd.random(opt)

    def _execute_repeat(self):
        opt = int(not int(self.status["repeat"]))
        self.mpd.repeat(opt)

    def _execute_pp(self):
        if self.status['state'] in ['play']:
            self.mpd.pause(1)
        elif self.status['state'] in ['pause', 'stop']:
            self.mpd.play()

    def _execute_info(self):
        if self.status['state'] in ['play', 'pause']:
            cmds = [(_("Title"), ('title',)),
                (_("Artist"), ('artist',)),
                (_("Album"), ('album',)),
                (_("Date"), ('date',)),
                (_("Track"), ('track', '0', False, 2)),
                (_("Genre"), ('genre',)),
                (_("File"), ('file',)),
                   ]
            for pretty, cmd in cmds:
                # XXX this could fail, if not all characters are supported by
                # os.stdout.encoding
                print("%s: %s" % (pretty, mpdh.get(self.songinfo, *cmd)))
            at, _length = [int(c) for c in self.status['time'].split(':')]
            at_time = misc.convert_time(at)
            try:
                time = misc.convert_time(mpdh.get(self.songinfo, 'time',
                                                  '', True))
                print("%s: %s/%s" % (_("Time"), at_time, time))
            except:
                print("%s: %s" % (_("Time"), at_time))
            print("%s: %s" % (_("Bitrate"),
                      self.status.get('bitrate', '')))
        else:
            print(_("MPD stopped"))

    def _execute_status(self):
        state_map = {
                'play': _("Playing"),
                'pause': _("Paused"),
                'stop': _("Stopped")}
        print("%s: %s" % (_("State"), state_map[self.status['state']]))

        print("%s %s" % (_("Repeat:"), _("On") \
                         if self.status['repeat'] == '1' else _("Off")))
        print("%s %s" % (_("Random:"), _("On") \
                         if self.status['random'] == '1' else _("Off")))
        print("%s: %s/100" % (_("Volume"), self.status['volume']))
        print("%s: %s %s" % (_('Crossfade'), self.status['xfade'],
                             ngettext('second', 'seconds',
                                      int(self.status['xfade']))))
