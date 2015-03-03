# Copyright 2006-2009 Scott Horowitz <stonecrest@gmail.com>
# Copyright 2009-2014 Jonathan Ballet <jon@multani.info>
#
# This file is part of Sonata.
#
# Sonata is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# Sonata is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with Sonata.  If not, see <http://www.gnu.org/licenses/>.

import os
from subprocess import Popen, PIPE

try:
    from sonata.genversion import VERSION
    build_ver = VERSION
except ImportError:
    build_ver = None

# Should be the most recent release
default_version = "v1.7a2"

def _version():
    '''Get the version number of the sources

    First check the build generated file, fallback to git describe if this is
    not a build, finally fallback to the default most recent release.
    '''
    if build_ver:
        version = build_ver
    else:
        try:
            dir = os.path.dirname(__file__)
            version = Popen(["git", "describe", "--abbrev=4", "HEAD"],
                             cwd=dir, stdout=PIPE,
                             stderr=PIPE).communicate()[0].decode('utf-8')
            if not version:
                raise OSError
        except OSError:
            version = default_version
    return version.strip()[1:]

version = _version()
