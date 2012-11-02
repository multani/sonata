#!/usr/bin/env python
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

import gettext
import locale
import logging
import os
import platform
import sys


def run():
    """Main entry point of Sonata"""

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

    # hint for gnome.init to set the process name to 'sonata'
    if platform.system() == 'Linux':
        sys.argv[0] = 'sonata'

    # apply as well:
        try:
            import ctypes
            libc = ctypes.CDLL('libc.so.6')
            PR_SET_NAME = 15
            libc.prctl(PR_SET_NAME, sys.argv[0], 0, 0, 0)
        except Exception: # if it fails, it fails
            pass


    ## Apply locale and translation:

    from sonata import misc
    misc.setlocale()

    # let gettext install _ as a built-in for all modules to see
    # XXX what's the correct way to find the localization?
    try:
        gettext.install('sonata', os.path.join(sonata.__file__.split('/lib')[0], 'share', 'locale'), unicode=1)
    except:
        logger.warning("Trying to use an old translation")
        gettext.install('sonata', '/usr/share/locale', unicode=1)
    gettext.textdomain('sonata')


    ## Check initial dependencies:

    # Test python version:
    if sys.version_info < (2,5):
        logger.critical("Sonata requires Python 2.5 or newer. Aborting...")
        sys.exit(1)

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
        import gtk
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
        # like gtk, set utf-8 encoding of str objects
        reload(sys) # hack access to setdefaultencoding
        sys.setdefaultencoding("utf-8")


    ## Global init:

    from socket import setdefaulttimeout as socketsettimeout
    socketsettimeout(5)

    if not args.skip_gui:
        gtk.gdk.threads_init()

    ## CLI actions:

    args.execute_cmds()


    ## Load the main application:

    from sonata import main

    app = main.Base(args)
    try:
        app.main()
    except KeyboardInterrupt:
        pass
