
import os
import subprocess
import re
import locale
import logging
import sys

from gi.repository import GLib


logger = logging.getLogger(__name__)


def convert_time(seconds):
    """
    Converts time in seconds to 'hh:mm:ss' format
    with leading zeros as appropriate and optional hours
    """
    hours, minutes, seconds = convert_time_raw(seconds)
    if hours == 0:
       return "%02d:%02d" %(minutes, seconds)
    return "%02d:%02d:%02d" %(hours, minutes, seconds)

def convert_time_raw(seconds):
    hours = seconds // 3600
    seconds -= 3600 * hours
    minutes = seconds // 60
    seconds -= 60 * minutes
    return hours, minutes, seconds

def escape_html(s):
    if not s: # None or ""
        return ""

    # & needs to be escaped first, before more are introduced:
    s = s.replace('&', '&amp;')
    s = s.replace('<', '&lt;')
    s = s.replace('>', '&gt;')
    s = s.replace('"', '&quot;')
    return s


def unescape_html(s):
    s = s.replace('&lt;', '<')
    s = s.replace('&gt;', '>')
    s = s.replace('&quot;', '"')
    s = s.replace('&nbsp;', ' ')
    # & needs to be unescaped last, so it can't get unescaped twice
    s = s.replace('&amp;', '&')
    # FIXME why did we have this too? s = s.replace('amp;', '&')
    return s


def wiki_to_html(s):
    # XXX Should we depend on a library to do this or get
    # html from the services?
    s = re.sub(r"'''''(.*?)'''''", r"<i><b>\1</b></i>", s)
    s = re.sub(r"'''(.*?)'''", r"<b>\1</b>", s)
    s = re.sub(r"''(.*?)''", r"<i>\1</i>", s)
    return s


def strip_all_slashes(s):
    if not s: # None or ""
        return ""
    s = s.replace("\\", "")
    s = s.replace("/", "")
    s = s.replace("\"", "")
    return s


def _rmgeneric(path, __func__):
    try:
        __func__(path)
    except OSError:
        pass


def link_markup(s, enclose_in_parentheses, small, linkcolor):
    if enclose_in_parentheses:
        s = "(%s)" % s
    if small:
        s = "<small>%s</small>" % s
    if linkcolor:
        color = linkcolor
    else:
        color = "blue" #no theme color, default to blue..
    s = "<span color='%s'>%s</span>" % (color, s)
    return s


def iunique(iterable, key=id):
    seen = set()
    for i in iterable:
        if key(i) not in seen:
            seen.add(key(i))
            yield i


def remove_list_duplicates(inputlist, case=True):
    # Note that we can't use list(set(inputlist))
    # because we want the inputlist order preserved.
    if case:
        key = lambda x: x
    else:
        # repr() allows inputlist to be a list of tuples
        # FIXME: Doesn't correctly compare uppercase and
        # lowercase unicode
        key = lambda x: repr(x).lower()
    return list(iunique(inputlist, key))

the_re = re.compile('^the ')


def lower_no_the(s):
    s = the_re.sub('', s.lower())
    s = str(s)
    return s


def create_dir(dirname):
    if not os.path.exists(os.path.expanduser(dirname)):
        try:
            os.makedirs(os.path.expanduser(dirname))
        except (IOError, OSError):
            pass


def remove_file(filename):
    if os.path.exists(filename):
        try:
            os.remove(filename)
        except:
            pass


def remove_dir_recursive(path):
    if not os.path.isdir(path):
        return

    files = os.listdir(path)

    for x in files:
        fullpath = os.path.join(path, x)
        if os.path.isfile(fullpath):
            f = os.remove
            _rmgeneric(fullpath, f)
        elif os.path.isdir(fullpath):
            remove_dir_recursive(fullpath)
            f = os.rmdir
            _rmgeneric(fullpath, f)


def file_exists_insensitive(filename):
    # Returns an updated filename that exists on the
    # user's filesystem; checks all possible combinations
    # of case.
    if os.path.exists(filename):
        return filename

    regexp = re.compile(re.escape(filename), re.IGNORECASE)

    path = os.path.dirname(filename)

    try:
        files = os.listdir(path)
    except OSError:
        return filename

    for x in files:
        fullpath = os.path.join(path, x)
        if regexp.match(fullpath):
            return fullpath

    return filename


def browser_load(docslink, browser, window):
    if browser and browser.strip():
        browsers = [browser.strip()]
    else:
        browsers = ["xdg-open",    # default, this respect the used DE
                "x-www-browser", # default on Debian-based systems
                "gnome-open",
                "kde-open",
                "exo-open",
                "firefox",
                "opera",
                "chromium"]
    for browser in browsers:
        try:
            subprocess.Popen(browser.split() + [docslink])
            break # done
        except OSError:
            pass  # try next
    else: # none worked
        return False
    return True


def file_from_utf8(filename):
    try:
        return GLib.filename_from_utf8(filename)
    except:
        return filename


def is_lang_rtl(window):
    from gi.repository import Pango
    # Check if a RTL (right-to-left) language:
    return window.get_pango_context().get_base_dir() == Pango.Direction.RTL


def sanitize_musicdir(mdir):
    return os.path.expanduser(mdir) if mdir else ''


def mpd_env_vars():
    host = None
    port = None
    password = None
    if 'MPD_HOST' in os.environ:
        if '@' in os.environ['MPD_HOST']:
            password, host = os.environ['MPD_HOST'].split('@')
        else:
            host = os.environ['MPD_HOST']
    if 'MPD_PORT' in os.environ:
        port = int(os.environ['MPD_PORT'])
    return (host, port, password)


def get_files_recursively(dirname):
    filenames = []
    os.walk(dirname, _get_files_recursively, filenames)
    return filenames


def _get_files_recursively(filenames, dirname, files):
    filenames.extend([os.path.join(dirname, f) for f in files])
