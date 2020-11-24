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

import functools
import logging
import operator
import os
import socket
import sys

from gi.repository import GObject
import mpd

from sonata.misc import remove_list_duplicates


class MPDClient:
    def __init__(self, client=None):

        if sys.version_info < (3, 0):
            if client is None:
                # Yeah, we really want some unicode returned, otherwise
                # we'll have to do it by ourselves.
                client = mpd.MPDClient(use_unicode=True)
            else:
                client.use_unicode = True
        elif client is None:
            # On Python 3, python-mpd2 always uses Unicode
            client = mpd.MPDClient()

        self._client = client
        self.logger = logging.getLogger(__name__)

    def __getattr__(self, attr):
        """
        Wraps all calls from mpd client into a proper function,
        which catches all MPDClient related exceptions and log them.
        """
        cmd = getattr(self._client, attr)
        # save result, so function have to be constructed only once
        wrapped_cmd = functools.partial(self._call, cmd, attr)
        setattr(self, attr, wrapped_cmd)
        return wrapped_cmd

    def _call(self, cmd, cmd_name, *args):
        try:
            retval = cmd(*args)
        except (socket.error, mpd.MPDError) as e:
            if cmd_name in ['lsinfo', 'list']:
                # return sane values, which could be used afterwards
                return []
            elif cmd_name == 'status':
                return {}
            else:
                self.logger.error("%s", e)
                return None

        if cmd_name in ['songinfo', 'currentsong']:
            return MPDSong(retval)
        elif cmd_name in ['plchanges', 'search', 'playlistinfo']:
            return [MPDSong(s) for s in retval]
        elif cmd_name in ['count']:
            return MPDCount(retval)
        else:
            return retval

    @property
    def version(self):
        return tuple(int(part) for part in self._client.mpd_version.split("."))

    def update(self, paths):
        if mpd_is_updating(self.status()):
            return

        # Updating paths seems to be faster than updating files for
        # some reason:
        dirs = []
        for path in paths:
            dirs.append(os.path.dirname(path))
        dirs = remove_list_duplicates(dirs, True)

        self._client.command_list_ok_begin()
        for directory in dirs:
            self._client.update(directory)
        self._client.command_list_end()


class MPDCount:
    """Represent the result of the 'count' MPD command"""

    __slots__ = ['playtime', 'songs']

    def __init__(self, m):
        self.playtime = int(m['playtime'])
        self.songs = int(m['songs'])


# Inherits from GObject for to be stored in Gtk's ListStore
class MPDSong(GObject.GObject):
    """Provide information about a song in a convenient format"""

    def __init__(self, mapping):
        self._mapping = {}
        for key, value in mapping.items():
            # Some attributes may be present several times, which is translated
            # into a list of values by python-mpd. We keep only the first one,
            # since Sonata doesn't really support multi-valued attributes at the
            # moment.
            if isinstance(value, list):
                value = value[0]
            self._mapping[key] = value
        super().__init__()

    def __eq__(self, other):
        return isinstance(other, self.__class__) and \
                self._mapping == other._mapping

    def __ne__(self, other):
        return not (self == other)

    def __contains__(self, key):
        return key in self._mapping

    def __getitem__(self, key):
        if key not in self:
            raise KeyError(key)
        return self.get(key)

    def get(self, key, alt=None):
        if key in self._mapping and hasattr(self, key):
            return getattr(self, key)
        else:
            return self._mapping.get(key, alt)

    def __getattr__(self, attr):
        # Get the attribute's value directly into the internal mapping.
        # This function is not called if the current object has a "real"
        # attribute set.
        return self._mapping.get(attr)

    def values(self):
        return self._mapping.values()

    @property
    def id(self):
        return int(self._mapping.get('id', 0))

    @property
    def track(self):
        return cleanup_numeric(self._mapping.get('track', '0'))

    @property
    def pos(self):
        v = self._mapping.get('pos', '0')
        return int(v) if v.isdigit() else 0

    @property
    def time(self):
        return int(self._mapping.get('time', 0))

    @property
    def disc(self):
        return cleanup_numeric(self._mapping.get('disc', 0))

    @property
    def file(self):
        return self._mapping.get('file', '') # XXX should be always here?


def cleanup_numeric(value):
    """Return a integer value from some not-so-integer values

    For example, a track number can have the value ``4/10`` (the fourth track of
    on a 10 songs album), so we want in this case to get the value ``4``:

    >>> cleanup_numeric('4/10')
    4

    or:

    >>> cleanup_numeric('5,12')
    5

    Of course, a simple value is correctly retrieved:

    >>> cleanup_numeric('42')
    42

    All the other cases basically return 0:

    >>> cleanup_numeric('/')
    0
    >>> cleanup_numeric(',')
    0
    >>> cleanup_numeric('')
    0

    """
    # track and disc can be oddly formatted (eg, '4/10')
    value = str(value).replace(',', ' ').replace('/', ' ').strip()
    if value:
        value = value.split()[0]
    return int(value) if value.isdigit() else 0


# XXX to be move when we can handle status change in the main interface
def mpd_is_updating(status):
    return status and status.get('updating_db', 0)
