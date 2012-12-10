#!/usr/bin/env python3
"""Sonata is a simple GTK+ client for the Music Player Daemon.
"""

__author__ = "Scott Horowitz"
__email__ = "stonecrest@gmail.com"
__license__ = """
Sonata, an elegant GTK+ client for the Music Player Daemon
Copyright 2006-2008 Scott Horowitz <stonecrest@gmail.com>

This file is part of Sonata.

Sonata is free software; you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation; either version 3 of the License, or
(at your option) any later version.

Sonata is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with this program.  If not, see <http://www.gnu.org/licenses/>.
"""

import sys
if sys.version_info <= (3, 2):
    sys.stderr.write("Sonata requires Python 3.2+\n")
    sys.exit(1)

import gettext
import locale
import logging
import os
import platform
import threading  # needed for interactive shell


def run():
    """Main entry point of Sonata"""

    # TODO: allow to exit the application with Ctrl+C from the terminal
    # This is a fix for https://bugzilla.gnome.org/show_bug.cgi?id=622084
    import signal
    signal.signal(signal.SIGINT, signal.SIG_DFL)

    # XXX insert the correct sonata package dir in sys.path

    logging.basicConfig(
        level=logging.WARNING,
        format="[%(asctime)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        stream=sys.stderr)

    logger = logging.getLogger(__name__)

    try:
        import sonata
    except ImportError:
        logger.critical("Python failed to find the sonata modules.")
        logger.critical("Searched in the following directories:\n%s",
                        "\n".join(sys.path))
        logger.critical("Perhaps Sonata is improperly installed?")
        sys.exit(1)

    try:
        from sonata.version import version
    except ImportError:
        logger.critical("Python failed to find the sonata modules.")
        logger.critical("An old or incomplete installation was "
                        "found in the following directory: %s",
                        os.path.dirname(sonata.__file__))
        logger.critical("Perhaps you want to delete it?")
        sys.exit(1)

    # XXX check that version.VERSION is what this script was installed for

    ## Apply global fixes:

    if platform.system() == 'Linux':
        sys.argv[0] = "sonata"
        import ctypes
        libc = ctypes.CDLL('libc.so.6')
        PR_SET_NAME = 15
        libc.prctl(PR_SET_NAME, b"sonata", 0, 0, 0)

    ## Apply locale and translation:

    from sonata import misc
    misc.setlocale()

    # let gettext install _ as a built-in for all modules to see
    # XXX what's the correct way to find the localization?
    locales_path = '/usr/share/locale'
    for path in [
        os.path.join(os.path.dirname(sonata.__file__), "share", "locale"),
        os.path.join(sonata.__file__.split('/lib')[0], 'share', 'locale'),
    ]:
        if os.path.exists(path):
            locales_path = path
            break

    gettext.install('sonata', locales_path, names=["ngettext"])
    gettext.textdomain('sonata')


    ## Check initial dependencies:
    try:
        import mpd
    except:
        logger.critical("Sonata requires python-mpd. Aborting...")
        sys.exit(1)


    ## Initialize the plugin system:

    from sonata.pluginsystem import pluginsystem
    pluginsystem.find_plugins()
    pluginsystem.notify_of('enablables',
                   lambda plugin, cb: cb(True),
                   lambda plugin, cb: cb(False))


    ## Load the command line interface:

    from sonata import cli
    args = cli.Args()
    args.parse(sys.argv)

    ## Deal with GTK:

    if not args.skip_gui:
        # importing gtk does sys.setdefaultencoding("utf-8"), sets locale etc.
        from gi.repository import Gtk, Gdk
        # fix locale
        misc.setlocale()
    else:
        class FakeModule(object):
            pass
        # make sure the ui modules aren't imported
        for m in 'gtk', 'pango', 'sonata.ui', 'sonata.breadcrumbs':
            if m in sys.modules:
                logger.warning(
                    "Module %s imported in CLI mode (it should not)", m)
            else:
                sys.modules[m] = FakeModule()


    ## Global init:

    from socket import setdefaulttimeout as socketsettimeout
    socketsettimeout(5)

    if not args.skip_gui:
        Gdk.threads_init()

    ## CLI actions:

    args.execute_cmds()

    ## Load the main application:

    from sonata import main

    app = main.Base(args)

    ## Load the shell
    # yo dawg, I heard you like python,
    # so I put a python shell in your python application
    # so you can debug while you run it.
    if args.start_shell:
        # the enviroment used for the shell
        scope = dict(list(globals().items()) + list(locals().items()))
        def run_shell():
            try:
                import IPython
                IPython.embed(user_ns=scope)
            except ImportError as e: # fallback if ipython is not avaible
                import code
                shell = code.InteractiveConsole(scope)
                shell.interact()
            # quit program if shell is closed,
            # This is the only way to close the program clone in this mode,
            # because we can't close the shell thread easily
            from gi.repository import Gtk
            Gtk.main_quit()
        threading.Thread(target=run_shell).start()

    try:
        app.main()
    except KeyboardInterrupt:
        Gtk.main_quit()
