
import functools
import logging
import os
import socket

from gi.repository import GObject
import mpd

from sonata.misc import remove_list_duplicates


class MPDClient:
    def __init__(self, client=None):
        if client is None:
            # Yeah, we really want some unicode returned, otherwise we'll have
            # to do it by ourselves.
            client = mpd.MPDClient(use_unicode=True)
        else:
            client.use_unicode = True
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
        elif cmd_name in ['plchanges', 'search']:
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
    # track and disc can be oddly formatted (eg, '4/10')
    value = str(value).replace(',', ' ').replace('/', ' ').split()[0]
    return int(value) if value.isdigit() else 0

# XXX to be move when we can handle status change in the main interface
def mpd_is_updating(status):
    return status and status.get('updating_db', 0)
