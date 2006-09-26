#!/usr/bin/env python

# py-libmpdclient2 is written by Nick Welch <mack@incise.org>, 2005.
#
# This software is in the public domain
# and is provided AS IS, with NO WARRANTY.

import socket
import sys

# a line is either:
#
# key:val pair
# OK
# ACK

class socket_talker(object):

    def __init__(self, host, port):
        self.host = host
        self.port = port
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.settimeout(2)
        self.sock.connect((host, port))
        self.file = self.sock.makefile("rb+")
        self.current_line = ''
        self.ack = ''
        self.done = True
        self.sock.close()

    # this SUCKS

    def get_line(self):
        if not self.current_line:
            self.current_line = self.file.readline().rstrip("\n")
        if not self.current_line:
            raise EOFError
        if self.current_line == "OK" or self.current_line.startswith("ACK"):
            self.done = True
        return self.current_line

    def putline(self, line):
        self.file.write("%s\n" % line)
        self.file.flush()
        self.done = False

    def get_pair(self):
        line = self.get_line()
        self.ack = ''

        if self.done:
            if line.startswith("ACK"):
                self.ack = line.split(None, 1)[1]
            return ()

        pair = line.split(": ", 1)
        if len(pair) != 2:
            raise RuntimeError("bogus response: ``%s''" % line)

        return pair

ZERO = 0
ONE = 1
MANY = 2

plitem_delim = ["file", "directory", "playlist"]

commands = {
    # (name, nargs): (format string, nresults, results_type_name, delimiter_key)

    # delimiter key is for commands that return multiple results.  we use this
    # string to detect the beginning of a new result object.

    # if results_type_name is empty, the result object's .type will be set to
    # the key of the first key/val pair in it; otherwise, it will be set to
    # results_type_name.

    ("kill",          0): ('%s', ZERO, '', []),
    ("outputs",       0): ('%s', MANY, 'outputs', ['outputid']),
    ("clear",         0): ('%s', ZERO, '', []),
    ("currentsong",   0): ('%s', ONE, '', []),
    ("shuffle",       0): ('%s', ZERO, '', []),
    ("next",          0): ('%s', ZERO, '', []),
    ("previous",      0): ('%s', ZERO, '', []),
    ("stop",          0): ('%s', ZERO, '', []),
    ("clearerror",    0): ('%s', ZERO, '', []),
    ("close",         0): ('%s', ZERO, '', []),
    ("commands",      0): ('%s', MANY, 'commands', ['command']),
    ("notcommands",   0): ('%s', MANY, 'notcommands', ['command']),
    ("ping",          0): ('%s', ZERO, '', []),
    ("stats",         0): ('%s', ONE, 'stats', []),
    ("status",        0): ('%s', ONE, 'status', []),
    ("play",          0): ('%s', ZERO, '', []),
    ("playlistinfo",  0): ('%s', MANY, '', plitem_delim),
    ("playlistid",    0): ('%s', MANY, '', plitem_delim),
    ("lsinfo",        0): ('%s', MANY, '', plitem_delim),
    ("update",        0): ('%s', ZERO, '', []),
    ("listall",       0): ('%s', MANY, '', plitem_delim),
    ("listallinfo",   0): ('%s', MANY, '', plitem_delim),

    ("disableoutput", 1): ("%s %d", ZERO, '', []),
    ("enableoutput",  1): ("%s %d", ZERO, '', []),
    ("delete",        1): ('%s %d', ZERO, '', []), # <int song>
    ("deleteid",      1): ('%s %d', ZERO, '', []), # <int songid>
    ("playlistinfo",  1): ('%s %d', MANY, '', plitem_delim), # <int song>
    ("playlistid",    1): ('%s %d', MANY, '', plitem_delim), # <int songid>
    ("crossfade",     1): ('%s %d', ZERO, '', []), # <int seconds>
    ("play",          1): ('%s %d', ZERO, '', []), # <int song>
    ("playid",        1): ('%s %d', ZERO, '', []), # <int songid>
    ("random",        1): ('%s %d', ZERO, '', []), # <int state>
    ("repeat",        1): ('%s %d', ZERO, '', []), # <int state>
    ("setvol",        1): ('%s %d', ZERO, '', []), # <int vol>
    ("plchanges",     1): ('%s %d', MANY, '', plitem_delim), # <playlist version>
    ("pause",         1): ('%s %d', ZERO, '', []), # <bool pause>

    ("update",      1): ('%s "%s"', ONE, 'update', []), # <string path>
    ("listall",     1): ('%s "%s"', MANY, '', plitem_delim), # <string path>
    ("listallinfo", 1): ('%s "%s"', MANY, '', plitem_delim), # <string path>
    ("lsinfo",      1): ('%s "%s"', MANY, '', plitem_delim), # <string directory>
    ("add",         1): ('%s "%s"', ZERO, '', []), # <string>
    ("load",        1): ('%s "%s"', ZERO, '', []), # <string name>
    ("rm",          1): ('%s "%s"', ZERO, '', []), # <string name>
    ("save",        1): ('%s "%s"', ZERO, '', []), # <string playlist name>
    ("password",    1): ('%s "%s"', ZERO, '', []), # <string password>

    ("move",   2): ("%s %d %d", ZERO, '', []), # <int from> <int to>
    ("moveid", 2): ("%s %d %d", ZERO, '', []), # <int songid from> <int to>
    ("swap",   2): ("%s %d %d", ZERO, '', []), # <int song1> <int song2>
    ("swapid", 2): ("%s %d %d", ZERO, '', []), # <int songid1> <int songid2>
    ("seek",   2): ("%s %d %d", ZERO, '', []), # <int song> <int time>
    ("seekid", 2): ("%s %d %d", ZERO, '', []), # <int songid> <int time>

    # <string type> <string what>
    ("find",   2): ('%s "%s" "%s"', MANY, '', plitem_delim),

    # <string type> <string what>
    ("search", 2): ('%s "%s" "%s"', MANY, '', plitem_delim),

    # list <metadata arg1> [<metadata arg2> <search term>]

    # <metadata arg1>
    ("list", 1): ('%s "%s"', MANY, '', plitem_delim),

    # <metadata arg1> <metadata arg2> <search term>
    ("list", 3): ('%s "%s" "%s" "%s"', MANY, '', plitem_delim),
}

def is_command(cmd):
    return cmd in [ k[0] for k in commands.keys() ]

def escape(text):
    # join/split is faster than replace
    text = '\\\\'.join(text.split('\\')) # \ -> \\
    text = '\\"'.join(text.split('"')) # " -> \"
    return text

def get_command(cmd, args):
    try:
        return commands[(cmd, len(args))]
    except KeyError:
        raise RuntimeError("no such command: %s (%d args)" % (cmd, len(args)))

def send_command(talker, cmd, args):
    args = list(args[:])
    for i, arg in enumerate(args):
        if not isinstance(arg, int):
            args[i] = escape(str(arg))
    format = get_command(cmd, args)[0]
    talker.putline(format % tuple([cmd] + list(args)))

class sender_n_fetcher(object):
    def __init__(self, sender, fetcher):
        self.sender = sender
        self.fetcher = fetcher
        self.iterate = False

    def __getattr__(self, cmd):
        return lambda *args: self.send_n_fetch(cmd, args)

    def send_n_fetch(self, cmd, args):
        getattr(self.sender, cmd)(*args)
        junk, howmany, type, keywords = get_command(cmd, args)

        if howmany == ZERO:
            self.fetcher.clear()
            return

        if howmany == ONE:
            return self.fetcher.one_object(keywords, type)

        assert howmany == MANY
        result = self.fetcher.all_objects(keywords, type)

        if not self.iterate:
            result = list(result)
            self.fetcher.clear()
            return result

        # stupid hack because you apparently can't return non-None and yield
        # within the same function
        def yield_then_clear(it):
            for x in it:
                yield x
            self.fetcher.clear()
        return yield_then_clear(result)


class command_sender(object):
    def __init__(self, talker):
        self.talker = talker
    def __getattr__(self, cmd):
        return lambda *args: send_command(self.talker, cmd, args)

class response_fetcher(object):
    def __init__(self, talker):
        self.talker = talker
        self.converters = {}

    def clear(self):
        while not self.talker.done:
            self.talker.current_line = ''
            self.talker.get_line()
        self.talker.current_line = ''

    def one_object(self, keywords, type):
        # if type isn't empty, then the object's type is set to it.  otherwise
        # the type is set to the key of the first key/val pair.

        # keywords lists the keys that indicate a new object -- like for the
        # 'outputs' command, keywords would be ['outputid'].
        entity = dictobj()
        if type:
            entity['type'] = type

        while not self.talker.done:
            self.talker.get_line()
            pair = self.talker.get_pair()

            if not pair:
                self.talker.current_line = ''
                return entity

            key, val = pair
            key = key.lower()

            if key in keywords and key in entity.keys():
                return entity

            if key in 'file' and 'type' in entity.keys():
                return entity

            if key in 'playlist' and ('directory' in entity.keys() or 'file' in entity.keys()):
                return entity

            if not type and 'type' not in entity.keys():
                entity['type'] = key

            entity[key] = self.convert(entity['type'], key, val)
            self.talker.current_line = ''

        return entity

    def all_objects(self, keywords, type):
        while 1:
            obj = self.one_object(keywords, type)
            if not obj:
                raise StopIteration
            yield obj
            if self.talker.done:
                raise StopIteration

    def convert(self, cmd, key, val):
        # if there's a converter, convert it, otherwise return it the same
        return self.converters.get(cmd, {}).get(key, lambda x: x)(val)

class dictobj(dict):
    def __getattr__(self, attr):
        try:
            return self[attr]
        except KeyError:
            raise AttributeError
    def __repr__(self):
        # <mpdclient2.dictobj at 0x12345678 ..
        #   {
        #     key: val,
        #     key2: val2
        #   }>
        return (object.__repr__(self).rstrip('>') + ' ..\n' +
                '  {\n    ' +
                ',\n    '.join([ '%s: %s' % (k, v) for k, v in self.items() ]) +
                '\n  }>')

class mpd_connection(object):
    def __init__(self, host, port, password):
        self.talker = socket_talker(host, port)
        self.send = command_sender(self.talker)
        self.fetch = response_fetcher(self.talker)
        self.do = sender_n_fetcher(self.send, self.fetch)

        self._hello()

    def _hello(self):
        line = self.talker.get_line()
        if not line.startswith("OK MPD "):
            raise RuntimeError("this ain't mpd")
        self.mpd_version = line[len("OK MPD "):].strip()
        self.talker.current_line = ''

    # conn.foo() is equivalent to conn.do.foo(), but nicer
    #def __getattr__(self, attr):
    #    print attr
    #    if is_command(attr):
    #        return getattr(self.do, attr)
    #    raise AttributeError(attr)

def parse_host(host):
    if '@' in host:
        return host.split('@', 1)
    return '', host

def connect(**kw):
    import os

    port = int(os.environ.get('MPD_PORT', 6600))
    password, host = parse_host(os.environ.get('MPD_HOST', 'localhost'))

    kw_port = kw.get('port', 0)
    kw_password = kw.get('password', '')
    kw_host = kw.get('host', '')

    if kw_port:
        port = kw_port
    if kw_password:
        password = kw_password
    if kw_host:
        host = kw_host

    conn = mpd_connection(host, port, password)
    #if password:
    #    conn.password(password)
    return conn

