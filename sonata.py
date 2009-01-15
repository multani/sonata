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

import sys, platform, locale, gettext

try:
    import sonata
except ImportError:
    sys.stderr.write("Python failed to find the sonata modules.\n")
    sys.stderr.write("Perhaps Sonata is improperly installed?\n")
    sys.exit(1)


## Apply global fixes:

# the following line is to fix python-zsi 2.0 and thus lyrics in ubuntu:
# https://bugs.launchpad.net/ubuntu/+source/zsi/+bug/208855
sys.path.append('/usr/lib/python2.5/site-packages/oldxml')

# hint for gnome.init to set the process name to 'sonata'
if platform.system() == 'Linux':
    sys.argv[0] = 'sonata'

# This is needed so that python-mpd correctly returns lowercase
# keys for, e.g., playlistinfo() with a turkish locale
try:
    locale.setlocale(locale.LC_CTYPE, "C")
except:
    pass


## Apply translation:

# let gettext install _ as a built-in for all modules to see
try:
    gettext.install('sonata', os.path.join(sonata.__file__.split('/lib')[0], 'share', 'locale'), unicode=1)
except:
    gettext.install('sonata', '/usr/share/locale', unicode=1)
gettext.textdomain('sonata')


## Check initial dependencies:

# Test python version (note that python 2.5 returns a list of
# strings while python 2.6 returns a tuple of ints):
if tuple(map(int, platform.python_version_tuple())) < (2, 5, 0):
    sys.stderr.write("Sonata requires Python 2.5 or newer. Aborting...\n")
    sys.exit(1)

try:
    import mpd
except:
    sys.stderr.write("Sonata requires python-mpd. Aborting...\n")
    sys.exit(1)


## Load the command line interface:

from sonata import cli
args = cli.Args()
args.parse(sys.argv)
args.process_options()

## Check more dependencies:

if not args.should_skip_gui():
    import gtk
    if gtk.pygtk_version < (2, 12, 0):
        sys.stderr.write("Sonata requires PyGTK 2.12.0 or newer. Aborting...\n")
        sys.exit(1)


## Global init:

from socket import setdefaulttimeout as socketsettimeout
socketsettimeout(5)

if not args.should_skip_gui():
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
