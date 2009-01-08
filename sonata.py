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

from sonata import main
import sys
# the following line is to fix python-zsi 2.0 and thus lyrics in ubuntu:
# https://bugs.launchpad.net/ubuntu/+source/zsi/+bug/208855
sys.path.append('/usr/lib/python2.5/site-packages/oldxml')
import platform

if platform.system == 'Linux':
    sys.argv[0] = 'sonata'

app = main.Base()
try:
    app.main()
except KeyboardInterrupt:
    pass
