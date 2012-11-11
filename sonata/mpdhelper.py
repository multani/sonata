
import functools
import logging
import os
import socket

from mpd import MPDError

from sonata.misc import remove_list_duplicates


class MPDHelper(object):
    def __init__(self, client):
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
        except (socket.error, MPDError) as e:
            if cmd_name in ['lsinfo', 'list']:
                # return sane values, which could be used afterwards
                return []
            elif cmd_name == 'status':
                return {}
            else:
                self.logger.error("%s", e)
                return None

        if cmd_name == 'songinfo':
            return SongResult(retval)
        elif cmd_name == 'plchanges':
            return [SongResult(s) for s in retval]
        else:
            return retval

    def connect(self, host, port):
        self.disconnect()
        try:
            self._client.connect(host, port)
            self._version = self._client.mpd_version.split(".")
            self._commands = self._client.commands()
            self._urlhandlers = self._client.urlhandlers()
        except (socket.error, MPDError) as e:
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


class SongResult(object):
    """Provide information about a song in a convenient format"""

    def __init__(self, mapping):
        self._mapping = mapping

    def __getitem__(self, key):
        return self._mapping[key]

    def get(self, key, alt=None):
        return getattr(self, key, alt)

    @property
    def id(self):
        return int(self._mapping.get('id', 0))


def get(mapping, key, alt='', *sanitize_args):
    """Get a value from a mpd song and sanitize appropriately.

    sanitize_args: Arguments to pass to sanitize

    If the value is a list, only the first element is returned.
    Examples:
        get({'baz':['foo', 'bar']}, 'baz', '') -> 'foo'
        get({'baz':34}, 'baz', '', True) -> 34
    """

    value = mapping.get(key, alt)
    if isinstance(value, list):
        value = value[0]
    return _sanitize(value, *sanitize_args) if sanitize_args else value


def _sanitize(tag, return_int=False, str_padding=0):
    # Sanitizes a mpd tag; used for numerical tags. Known forms
    # for the mpd tag can be "4", "4/10", and "4,10".
    if not tag:
        return tag
    tag = str(tag).replace(',', ' ', 1).replace('/', ' ', 1).split()

    # fix #2842: tag only consist of '/' or ','
    if len(tag) == 0:
        tag = ''
    else:
        tag = tag[0]

    if return_int:
        return int(tag) if tag.isdigit() else 0

    return tag.zfill(str_padding)


# XXX to be move when we can handle status change in the main interface
def mpd_is_updating(status):
    return status and status.get('updating_db', 0)
