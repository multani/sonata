# coding=utf-8
# $HeadURL: http://svn.berlios.de/svnroot/repos/sonata/trunk/misc.py $
# $Id: misc.py 141 2006-09-11 04:51:07Z stonecrest $

import os, subprocess, re, ui, gobject

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
    s = s.replace('&', '&amp;')
    s = s.replace('<', '&lt;')
    s = s.replace('>', '&gt;')
    s = s.replace('"', '&quot;')
    return s

def unescape_html(s):
    s = s.replace('&amp;', '&')
    s = s.replace('amp;', '&')
    s = s.replace('&lt;', '<')
    s = s.replace('&gt;', '>')
    s = s.replace('&quot;', '"')
    s = s.replace('&nbsp;', ' ')
    return s

def wiki_to_html(s):
    tag_pairs = [["'''", "<b>", "</b>"], ["''", "<i>", "</i>"]]
    for tag in tag_pairs:
        tag_start = True
        pos = 0
        while pos > -1:
            pos = s.find(tag[0], pos)
            if pos > -1:
                if tag_start:
                    s = s[:pos] + tag[1] + s[pos+3:]
                else:
                    s = s[:pos] + tag[2] + s[pos+3:]
                pos += 1
                tag_start = not tag_start
    return s

def strip_all_slashes(s):
    s = s.replace("\\", "")
    s = s.replace("/", "")
    s = s.replace("\"", "")
    return s

def _rmgeneric(path, __func__):
    try:
        __func__(path)
    except OSError, (errno, strerror):
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

def remove_list_duplicates(inputlist, inputlist2=[], inputlist3=[], case=True):
    # If inputlist2 is provided, keep it synced with inputlist.
    # Note that this is only implemented if case=False.
    # Also note that we do this manually instead of using list(set(x))
    # so that the inputlist order is preserved.
    sync2 = (len(inputlist2) > 0)
    sync3 = (len(inputlist3) > 0)
    outputlist = []
    outputlist2 = []
    outputlist3 = []
    for i in range(len(inputlist)):
        dup = False
        # Search outputlist from the end, since the inputlist is typically in
        # alphabetical order
        j = len(outputlist)-1
        if case:
            while j >= 0:
                if inputlist[i] == outputlist[j]:
                    dup = True
                    break
                j = j - 1
        elif sync2:
            while j >= 0:
                if inputlist[i].lower() == outputlist[j].lower() and inputlist2[i].lower() == outputlist2[j].lower():
                    dup = True
                    break
                j = j - 1
        else:
            while j >= 0:
                if inputlist[i].lower() == outputlist[j].lower():
                    dup = True
                    break
                j = j - 1
        if not dup:
            outputlist.append(inputlist[i])
            if sync2:
                outputlist2.append(inputlist2[i])
            if sync3:
                outputlist3.append(inputlist3[i])
    return (outputlist, outputlist2, outputlist3)

the_re = re.compile('^the ')
def lower_no_the(s):
    return the_re.sub('', s.lower())

def first_of_2tuple(t):
    fst, snd = t
    return fst

def create_dir(dir):
    if os.path.exists(os.path.expanduser(dir)) == False:
        os.makedirs(os.path.expanduser(dir))

def remove_file(file):
    if os.path.exists(file):
        os.remove(file)

def remove_dir(path):
    if not os.path.isdir(path):
        return

    files=os.listdir(path)

    for x in files:
        fullpath=os.path.join(path, x)
        if os.path.isfile(fullpath):
            f=os.remove
            _rmgeneric(fullpath, f)
        elif os.path.isdir(fullpath):
            removeall(fullpath)
            f=os.rmdir
            _rmgeneric(fullpath, f)

def browser_load(docslink, browser, window):
    browser_error = False
    if len(browser.strip()) > 0:
        try:
            pid = subprocess.Popen([browser, docslink]).pid
        except:
            browser_error = True
    else:
        try:
            pid = subprocess.Popen(["gnome-open", docslink]).pid
        except:
            try:
                pid = subprocess.Popen(["exo-open", docslink]).pid
            except:
                try:
                    pid = subprocess.Popen(["kfmclient", "openURL", docslink]).pid
                except:
                    try:
                        pid = subprocess.Popen(["firefox", docslink]).pid
                    except:
                        try:
                            pid = subprocess.Popen(["mozilla", docslink]).pid
                        except:
                            try:
                                pid = subprocess.Popen(["opera", docslink]).pid
                            except:
                                browser_error = True
    if browser_error:
        ui.show_error_msg(window, _('Unable to launch a suitable browser.'), _('Launch Browser'), 'browserLoadError')

def file_from_utf8(filename):
    try:
        return gobject.filename_from_utf8(filename)
    except:
        return ""
