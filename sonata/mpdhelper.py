
import locale, sys, os
from time import strftime
from misc import remove_list_duplicates

suppress_errors = False

def suppress_mpd_errors(val):
    global suppress_errors
    suppress_errors = val

def status(client):
    result = call(client, 'status')
    if result and 'state' in result:
        return result
    else:
        return {}

def currsong(client):
    return call(client, 'currentsong')

def get(mapping, key, alt=''):
    # Returns either the value in the dict or, currently, the
    # first list's values. e.g. this will return 'foo' if genres
    # is ['foo' 'bar']. This should always be used to retrieve
    # values from a mpd song.
    value = mapping.get(key, alt)
    if isinstance(value, list):
        return value[0]
    else:
        return value

def getnum(mapping, key, alt='0', return_int=False, str_padding=0):
    # Same as get(), but sanitizes the number before returning
    tag = get(mapping, key, alt)
    return sanitize(tag, return_int, str_padding)

def sanitize(tag, return_int, str_padding):
    # Sanitizes a mpd tag; used for numerical tags. Known forms
    # for the mpd tag can be "4", "4/10", and "4,10".
    ret = 0

    split_tag = tag.replace(',',' ',1).replace('/',' ',1).split()
    if split_tag[0].isdigit():
        ret = int(split_tag[0])

    return ret if return_int else str(ret).zfill(str_padding)

def conout(s):
    # A kind of 'print' which does not throw exceptions if the string
    # to print cannot be converted to console encoding; instead it
    # does a "readable" conversion
    print s.encode(locale.getpreferredencoding(), "replace")

def call(mpdclient, mpd_cmd, *mpd_args):
    try:
        retval = getattr(mpdclient, mpd_cmd)(*mpd_args)
    except:
        if not mpd_cmd in ['disconnect', 'lsinfo', 'listplaylists']:
            if not suppress_errors:
                print strftime("%Y-%m-%d %H:%M:%S") + "  " + str(sys.exc_info()[1])
        if mpd_cmd in ['lsinfo', 'list']:
            return []
        else:
            return None

    return retval

def mpd_major_version(client):
    try:
        version = getattr(client, "mpd_version", 0.0)
        parts = version.split(".")
        return float(parts[0] + "." + parts[1])
    except:
        return 0.0

def mpd_is_updating(status):
    return status and status.get('updating_db', 0)

def update(mpdclient, paths, status):
    # mpd 0.14.x limits the number of paths that can be
    # updated within a command_list at 32. If we have
    # >32 directories, we bail and update the entire library.
    #
    # If we want to get trickier in the future, we can find
    # the 32 most specific parents that cover the set of files.
    # This would lower the possibility of resorting to a full
    # library update.
    #
    # Note: If a future version of mpd relaxes this limit,
    # we should make the version check more specific to 0.14.x

    if mpd_is_updating(status):
        return

    # Updating paths seems to be faster than updating files for
    # some reason:
    dirs = []
    for path in paths:
        dirs.append(os.path.dirname(path))
    dirs = remove_list_duplicates(dirs, True)

    if len(dirs) > 32 and mpd_major_version(mpdclient) >= 0.14:
        call(mpdclient, 'update', '/')
    else:
        call(mpdclient, 'command_list_ok_begin')
        for directory in dirs:
            call(mpdclient, 'update', directory)
        call(mpdclient, 'command_list_end')
