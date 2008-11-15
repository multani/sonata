# coding=utf-8
# $HeadURL: http://svn.berlios.de/svnroot/repos/sonata/trunk/mpdhelper.py $
# $Id: mpdhelper.py 141 2006-09-11 04:51:07Z stonecrest $

import string, locale, sys
from time import strftime

def status(client):
    try:
        status = client.status()
    except:
        return None
    try:
        test = status['state']
    except:
        return {}
    return status

def currsong(client):
    try:
        return client.currentsong()
    except:
        return None

def get(dict, type, alt=''):
    # Returns either the value in the dict or, currently, the
    # first list's values. e.g. this will return 'foo' if genres
    # is ['foo' 'bar']. This should always be used to retrieve
    # values from a mpd song.
    value = dict.get(type, alt)
    if isinstance(value, list):
        return value[0]
    else:
        return value

def getnum(dict, type, alt='0', return_int=False, str_padding=0):
    # Same as get(), but sanitizes the number before returning
    tag = get(dict, type, alt)
    return sanitize(tag, return_int, str_padding)

def sanitize(tag, return_int, str_padding):
    # Sanitizes a mpd tag; used for numerical tags. Known forms
    # for the mpd tag can be "4", "4/10", and "4,10".
    try:
        ret = int(tag.split('/')[0])
    except:
        try:
            ret = int(tag.split(',')[0])
        except:
            ret = 0
    # Don't allow negative numbers:
    if ret < 0:
        ret = 0
    if not return_int:
        ret = str(ret).zfill(str_padding)
    return ret

def conout(s):
    # A kind of 'print' which does not throw exceptions if the string
    # to print cannot be converted to console encoding; instead it
    # does a "readable" conversion
    print s.encode(locale.getpreferredencoding(), "replace")

def call(mpdclient, *args):
    # Note: first argument in *args should be the mpd command.
    # Additional items are the arguments to the command.
    mpd_cmd = args[0]
    mpd_args = args[1:]
    try:
        retval = getattr(mpdclient, mpd_cmd)(*mpd_args)
        return retval
    except:
        if not mpd_cmd in ['disconnect', 'lsinfo', 'listplaylists']:
            print strftime("%Y-%m-%d %H:%M:%S") + "  " + str(sys.exc_info()[1])
        return None
