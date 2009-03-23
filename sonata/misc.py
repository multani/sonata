
import os, subprocess, re, locale, sys, ui, gtk


def convert_time(raw):
    # Converts raw time to 'hh:mm:ss' with leading zeros as appropriate
    h, m, s = ['%02d' % c for c in (raw/3600, (raw%3600)/60, raw%60)]
    if h == '00':
        if m.startswith('0'):
            m = m[1:]
        return m + ':' + s
    else:
        if h.startswith('0'):
            h = h[1:]
        return h + ':' + m + ':' + s

def bold(s):
    if not (str(s).startswith('<b>') and str(s).endswith('</b>')):
        return '<b>%s</b>' % s
    else:
        return s

def unbold(s):
    if str(s).startswith('<b>') and str(s).endswith('</b>'):
        return s[3:-4]
    else:
        return s

def escape_html(s):
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

# XXX Should we depend on a library to do this or get html from the services?
def wiki_to_html(s):
    s = re.sub(r"'''(.*?)'''", r"<b>\1</b>", s)
    s = re.sub(r"''(.*?)''",   r"<i>\1</i>", s)
    return s

def strip_all_slashes(s):
    s = s.replace("\\", "")
    s = s.replace("/", "")
    s = s.replace("\"", "")
    return s

def _rmgeneric(path, __func__):
    try:
        __func__(path)
    except OSError:
        pass

def is_binary(f):
    if '\0' in f: # found null byte
        return True
    return False

def link_markup(s, enclose_in_parentheses, small, linkcolor):
    if enclose_in_parentheses:
        s = "(" + s + ")"
    if small:
        s = "<small>" + s + "</small>"
    if linkcolor:
        color = linkcolor
    else:
        color = "blue" #no theme color, default to blue..
    s = "<span color='" + color + "'>" + s + "</span>"
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
        key = lambda x:x
    else:
        # repr() allows inputlist to be a list of tuples
        # FIXME: Doesn't correctly compare uppercase and
        # lowercase unicode
        key = lambda x:repr(x).lower()
    return list(iunique(inputlist, key))

the_re = re.compile('^the ')
def lower_no_the(s):
    s = unicode(s)
    s = the_re.sub('', s.lower())
    s = str(s)
    return s

def create_dir(dirname):
    if not os.path.exists(os.path.expanduser(dirname)):
        os.makedirs(os.path.expanduser(dirname))

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
    if not os.path.exists(path):
        return filename
    files = os.listdir(path)

    for x in files:
        fullpath = os.path.join(path, x)
        if regexp.match(fullpath):
            return fullpath

    return filename

def browser_load(docslink, browser, window):
    if browser and browser.strip():
        browsers = [browser.strip()]
    else:
        browsers = ["gnome-open",    # default, we are a "gnome" app
                "x-www-browser", # default on Debian-based systems
                "exo-open",
                "kfmclient openURL",
                "firefox",
                "mozilla",
                "opera"]
    for browser in browsers:
        try:
            subprocess.Popen(browser.split()+[docslink])
            break # done
        except OSError:
            pass  # try next
    else: # none worked
        ui.show_msg(window, _('Unable to launch a suitable browser.'), _('Launch Browser'), 'browserLoadError', gtk.BUTTONS_CLOSE)

def file_from_utf8(filename):
    import gobject
    try:
        return gobject.filename_from_utf8(filename)
    except:
        return filename

def is_lang_rtl(window):
    import pango
    # Check if a RTL (right-to-left) language:
    return window.get_pango_context().get_base_dir() == pango.DIRECTION_RTL

def sanitize_musicdir(mdir):
    mdir = os.path.expanduser(mdir)
    if mdir and not mdir.endswith("/"):
        mdir = mdir + "/"
    return mdir

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
    os.path.walk(dirname, _get_files_recursively, filenames)
    return filenames

def _get_files_recursively(filenames, dirname, files):
    filenames.extend([os.path.join(dirname, f) for f in files])

def setlocale():
    try:
        locale.setlocale(locale.LC_ALL, "")
        # XXX this makes python-mpd correctly return lowercase
        # keys for, e.g., playlistinfo() with a turkish locale:
        locale.setlocale(locale.LC_CTYPE, "C")
    except:
        print "Failed to set locale"
        sys.exit(1)
