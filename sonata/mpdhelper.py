
import functools
import logging
import os
import socket

import mpd

from sonata.misc import remove_list_duplicates


class MPDClient(object):
    def __init__(self, client=None):
        if client is None:
            # Yeah, we really want some unicode returned, otherwise we'll have
            # to do it by ourselves.
            client = mpd.MPDClient(use_unicode=True)
        else:
            client.use_unicode = True
        self._client = client
        self.logger = logging.getLogger(__name__)
        self._version = None
        self._commands = None
        self._urlhandlers = None

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
        elif cmd_name in ['plchanges', 'search']:
            return [MPDSong(s) for s in retval]
        elif cmd_name in ['count']:
            return MPDCount(retval)
        else:
            return retval

    def connect(self, host, port):
        self.disconnect()
        try:
            self._client.connect(host, port)
            self._version = self._client.mpd_version.split(".")
            self._commands = self._client.commands()
            self._urlhandlers = self._client.urlhandlers()
        except (socket.error, mpd.MPDError) as e:
            self.logger.error("Error while connecting to MPD: %s", e)

    def disconnect(self):
        # Reset to default values
        self._version = None
        self._commands = None
        self._urlhandlers = None
        try:
            # We really don't care, if connections breaks, before we
            # could disconnect.
            self._client.close()
            return self._client.disconnect()
        except:
            pass

    @property
    def version(self):
        return self._version

    @property
    def commands(self):
        return self._commands

    @property
    def urlhandlers(self):
        return self._urlhandlers

    def update(self,  paths):
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


class MPDCount(object):
    """Represent the result of the 'count' MPD command"""

    __slots__ = ['playtime', 'songs']

    def __init__(self, m):
        self.playtime = int(m['playtime'])
        self.songs = int(m['songs'])


class MPDSong(object):
    """Provide information about a song in a convenient format"""

    def __init__(self, mapping):
        self._mapping = mapping

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

    @property
    def id(self):
        return int(self._mapping.get('id', 0))

    @property
    def track(self):
        value = self._mapping.get('track', '0')

        # The track number can be a bit funky sometimes and contains value like
        # "4/10" or "4,10" instead of only "4". We tr to clean it up a bit...
        value = str(value).replace(',', ' ').replace('/', ' ').split()[0]
        return int(value) if value.isdigit() else 0

    @property
    def pos(self):
        v = self._mapping.get('pos', '0')
        return int(v) if v.isdigit() else 0

    @property
    def time(self):
        return int(self._mapping.get('time', 0))

    @property
    def disc(self):
        return int(self._mapping.get('disc', 0))

    @property
    def file(self):
        return self._mapping.get('file', '') # XXX should be always here?


# XXX to be move when we can handle status change in the main interface
def mpd_is_updating(status):
    return status and status.get('updating_db', 0)
