### BEGIN PLUGIN INFO
# [plugin]
# plugin_format: 0, 0
# name: Last.fm Scrobbler
# version: 0, 2, 0
# description: This plugin submit the songs played to a Last.fm account.
# author: Lashkov Anton
# author_email: lenton_91@mail.ru
# url: 
# license: GPL v3 and LGPL in scrobbler
# [capabilities]
# enablables: on_enable
# handle_change_status: handle_change_status
# plugin_configure: configure
### END PLUGIN INFO

import threading
import os
import gettext
import sys
import urllib, urllib2
from time import mktime
from hashlib import md5
import time
from datetime import datetime, timedelta
import ConfigParser
import sonata.ui as ui
import sonata.mpdhelper as mpdh
import gtk

#
# Scrobbler from: http://exhuma.wicked.lu/projects/python/scrobbler/
# by Michel Albert <exhuma@users.sourceforge.net>
# with changes by Lashkov Anton <lenton_91@mail.ru>
#

class BackendError(Exception):
    """Raised if the AS backend does something funny"""
    pass
class AuthError(Exception):
    """Raised on authentication errors"""
    pass
class PostError(Exception):
    """Raised if something goes wrong when posting data to AS"""
    pass
class SessionError(Exception):
    """Raised when problems with the session exist"""
    pass
class ProtocolError(Exception):
    """Raised on general Protocol errors"""
    pass

class Scrobbler():

    def __init__(self):

        self.SESSION_ID = None
        self.POST_URL   = None
        self.NOW_URL    = None
        self.HARD_FAILS = 0
        self.LAST_HS    = None   # Last handshake time
        self.HS_DELAY   = 0      # wait this many seconds until next handshake
        self.SUBMIT_CACHE = []
        self.MAX_CACHE  = 5      # keep only this many songs in the cache
        self.PROTOCOL_VERSION = '1.2'
        self.LOGIN      = {}     # data required to login

        self.scrob_start_time = ""
        self.scrob_playing_duration = 0
        self.scrob_last_prepared = ""
        self.elapsed_now = None

    def login(self, user, password, client=('tst', '1.0') ):

        self.LOGIN['u'] = user
        self.LOGIN['p'] = password
        self.LOGIN['c'] = client

        if self.LAST_HS is not None:
            next_allowed_hs = self.LAST_HS + timedelta(seconds=self.HS_DELAY)
            if datetime.now() < next_allowed_hs:
                delta = next_allowed_hs - datetime.now()
                raise ProtocolError(_("Please wait another %d seconds until \
                next handshake (login) attempt." % delta.seconds))

        self.LAST_HS = datetime.now()

        tstamp = int(mktime(datetime.now().timetuple()))
        url = "http://post.audioscrobbler.com/"

        token = md5("%s%d" % (self.LOGIN['p'], int(tstamp))).hexdigest()
        values = {'hs': 'true',
                  'p' : self.PROTOCOL_VERSION,
                  'c' : client[0],
                  'v' : client[1],
                  'u' : user,
                  't' : tstamp,
                  'a' : token}

        data = urllib.urlencode(values)
        req = urllib2.Request("%s?%s" % (url, data))
        response = urllib2.urlopen(req)
        result = response.read()
        lines = result.split('\n')

        if lines[0] == 'BADAUTH':
            raise AuthError(_("Bad username/password"))

        elif lines[0] == 'BANNED':
            raise Exception(_("This client-version was banned by \
            Audioscrobbler. Please contact the author of this module!"))

        elif lines[0] == 'BADTIME':
            raise ValueError(_("Your system time is out of sync with \
            Audioscrobbler. Consider using an NTP-client to keep you system \
            time in sync."))

        elif lines[0].startswith('FAILED'):
            self.handle_hard_error()
            raise BackendError(_("Authentication with AS failed. \
            Reason: %s" % lines[0]))

        elif lines[0] == 'OK':
            # wooooooohooooooo. We made it!
            self.SESSION_ID = lines[1]
            self.NOW_URL    = lines[2]
            self.POST_URL   = lines[3]
            self.HARD_FAILS = 0

        else:
            # some hard error
            self.handle_hard_error()

    def handle_hard_error(self):
        """Handles hard errors."""

        if not self.HS_DELAY:
            self.HS_DELAY = 60
        elif self.HS_DELAY < 120*60:
            self.HS_DELAY *= 2
        if self.HS_DELAY > 120*60:
            self.HS_DELAY = 120*60

        self.HARD_FAILS += 1
        if self.HARD_FAILS == 3:
            self.SESSION_ID = None

    def now_playing(self, artist, track, album="", length="", trackno="",
                    mbid="" ):

        if self.SESSION_ID is None:
            raise AuthError(_("Please 'login()' first. (No session available)"))

        if self.POST_URL is None:
            raise PostError(_("Unable to post data. Post URL was empty!"))

        values = {'s': self.SESSION_ID,
                  'a': unicode(artist).encode('utf-8'),
                  't': unicode(track).encode('utf-8'),
                  'b': unicode(album).encode('utf-8'),
                  'l': length,
                  'n': trackno,
                  'm': mbid }
        
        data = urllib.urlencode(values)
        req = urllib2.Request(self.NOW_URL, data)
        response = urllib2.urlopen(req)
        result = response.read()

        i = 0
        while result.strip() == "BADSESSION" and i < 5:
            # retry to login
            self.login(self.LOGIN['u'], self.LOGIN['p'])

            # retry to submit the data
            req = urllib2.Request(self.NOW_URL, data)
            response = urllib2.urlopen(req)
            result = response.read()

            if result.strip() == "OK":
                return True

            i += 1

        # either we tried 5 times, or we still have a bad session
        if result.strip() == "BADSESSION":
            raise SessionError(_('Invalid session after 5 retries!'))
        else:
            return False

    def submit(self, artist, track, time, source = 'P', rating = "",
               length = "", album = "", trackno = "", mbid = "",
               autoflush = False):

        source = source.upper()
        rating = rating.upper()

        if source == 'L' and (rating == 'B' or rating == 'S'):
            raise ProtocolError(_("You can only use rating 'B' or 'S' on \
            source 'L'. See the docs!"))

        if source == 'P' and length == '':
            raise ProtocolError(_("Song length must be specified when \
            using 'P' as source!"))

        self.SUBMIT_CACHE.append({'a': unicode(artist).encode('utf-8'),
                                  't': unicode(track).encode('utf-8'),
                                  'i': time,
                                  'o': source,
                                  'r': rating,
                                  'l': length,
                                  'b': unicode(album).encode('utf-8'),
                                  'n': trackno,
                                  'm': mbid})

        if autoflush or len(self.SUBMIT_CACHE) >= self.MAX_CACHE:
            return self.flush()
        else:
            return True

    def flush(self, inner_call = False):
        if self.POST_URL is None:
            raise ProtocolError(_('Cannot submit without having a valid \
            post-URL. Did you login?'))

        values = {}

        for i, item in enumerate(self.SUBMIT_CACHE):
            for key in item:
                values[key + "[%d]" % i] = item[key]

        values['s'] = self.SESSION_ID

        data = urllib.urlencode(values)
        req = urllib2.Request(self.POST_URL, data)
        response = urllib2.urlopen(req)
        result = response.read()
        lines = result.split('\n')

        if lines[0] == "OK":
            self.SUBMIT_CACHE = []
            return True
        elif lines[0] == "BADSESSION":
            if inner_call is False:
                self.login(self.LOGIN['u'], self.LOGIN['p'], self.LOGIN['c'])
                self.flush(inner_call = True)
            else:
                raise Warning(_("Infinite loop prevented"))
        elif lines[0].startswith('FAILED'):
            self.handle_hard_error()
            raise BackendError(_("Submission to AS failed. Reason: %s" %
                                 lines[0]))
        else:
            # some hard error
            self.handle_hard_error()
            return False

    def handle_change_status(self, state, prevstate, prevsonginfo,
                             songinfo=None, mpd_time_now=None):
        """Handle changes to play status, submitting info as appropriate"""
        if prevsonginfo and 'time' in prevsonginfo:
            prevsong_time = mpdh.get(prevsonginfo, 'time')
        else:
            prevsong_time = None

        if state in ('play', 'pause'):
            elapsed_prev = self.elapsed_now
            self.elapsed_now, length = [float(c) for c in
                                        mpd_time_now.split(':')]
            current_file = mpdh.get(songinfo, 'file')
            if prevstate == 'stop':
                # Switched from stop to play, prepare current track:
                self.prepare(songinfo)
            elif (prevsong_time and
                  (self.scrob_last_prepared != current_file or
                   (self.scrob_last_prepared == current_file and
                    elapsed_prev and self.elapsed_now <= 1 and
                    self.elapsed_now < elapsed_prev and length > 0))):
                # New song is playing, post previous track if time criteria is
                # met. In order to account for the situation where the same
                # song is played twice in a row, we will check if previous
                # elapsed time was larger than current and we're at the
                # beginning of the same song now
                if self.scrob_playing_duration > 4 * 60 or \
                   self.scrob_playing_duration > int(prevsong_time) / 2:
                    if self.scrob_start_time != "":
                        self.post(prevsonginfo)
                # Prepare current track:
                self.prepare(songinfo)
            # Keep track of the total amount of time that the current song
            # has been playing:
            now = time.time()
            if prevstate != 'pause':
                self.scrob_playing_duration += now - self.scrob_prev_time
            self.scrob_prev_time = now
        else: # stopped:
            self.elapsed_now = 0
            if prevsong_time:
                if self.scrob_playing_duration > 4 * 60 or \
                   self.scrob_playing_duration > int(prevsong_time) / 2:
                    # User stopped the client, post previous track if time
                    # criteria is met:
                    if self.scrob_start_time != "":
                        self.post(prevsonginfo)

    def prepare(self, songinfo):
        self.scrob_start_time = ""
        self.scrob_last_prepared = ""
        self.scrob_playing_duration = 0
        self.scrob_prev_time = time.time()

        if songinfo:
            # No need to check if the song is 30 seconds or longer,
            # audioscrobbler.py takes care of that.
            if 'time' in songinfo:
                self.np(songinfo)

                self.scrob_start_time = str(int(time.time()))
                self.scrob_last_prepared = mpdh.get(songinfo, 'file')

    def np(self, songinfo):
        thread = threading.Thread(target=self.do_np, args=(songinfo,))
        thread.setDaemon(True)
        thread.start()

    def do_np(self, songinfo):
        if songinfo:
            if 'artist' in songinfo and \
               'title' in songinfo and \
               'time' in songinfo:
                if not 'album' in songinfo:
                    album = u''
                else:
                    album = mpdh.get(songinfo, 'album')
                if not 'track' in songinfo:
                    tracknumber = u''
                else:
                    tracknumber = mpdh.get(songinfo, 'track')
                try:
                    self.now_playing(artist=mpdh.get(songinfo, 'artist'),
                                    track=mpdh.get(songinfo, 'title'),
                                    length=mpdh.get(songinfo, 'time'),
                                    trackno=tracknumber,
                                    album=album)
                except:
                    print sys.exc_info()[1]
        time.sleep(10)

    def post(self, prevsonginfo):
        if prevsonginfo:
            if 'artist' in prevsonginfo and \
               'title' in prevsonginfo and \
               'time' in prevsonginfo:
                if not 'album' in prevsonginfo:
                    album = u''
                else:
                    album = mpdh.get(prevsonginfo, 'album')
                if not 'track' in prevsonginfo:
                    tracknumber = u''
                else:
                    tracknumber = mpdh.get(prevsonginfo, 'track')
                try:
                    self.submit(mpdh.get(prevsonginfo, 'artist'),
                              mpdh.get(prevsonginfo , 'title'),
                              self.scrob_start_time,
                              length = mpdh.get(prevsonginfo, 'time'),
                              album = album,
                              trackno=tracknumber)
                except:
                    print sys.exc_info()[1]

                thread = threading.Thread(target=self.do_post)
                thread.setDaemon(True)
                thread.start()
        self.scrob_start_time = ""

    def do_post(self):
        for _i in range(0, 3):
            try:
                self.flush()
                return
            except BackendError, e:
                print e
            time.sleep(10)

#
# end of scrobbler 
#

scrobl = None
username = ""
password_md5 = ""
config_file = "~/.config/sonata/scrobbler"

def on_enable(state):
    global scrobl

    if state:
        read_settings()

        if username != "" and password_md5 != "":
            if scrobl is None:
                scrobl = Scrobbler()

            scrobl.login(username, password_md5)

def handle_change_status(state, prevstate, prevsonginfo, songinfo=None,
                         mpd_time_now=None):
    scrobl.handle_change_status(state, prevstate, prevsonginfo, songinfo,
                                      mpd_time_now)


def configure():
    global password_md5, username

    window = gtk.Window()
    window.set_title(_("Last.fm scrobbler preferences."))

    grid = gtk.Table(2, 3, False)
    window.add(grid)

    title = ui.label(markup = '<b>' + _("Last.fm login:") + '</b>')
    grid.attach(title, 0, 2, 0, 1)

    label1 = ui.label(_("Username:"))
    grid.attach(label1, 0, 1, 1, 2)
    label2 = ui.label(_("Password:"))
    grid.attach(label2, 0, 1, 2, 3)

    user_edit = ui.entry(text = username)
    grid.attach(user_edit, 1, 2, 1, 2)

    pass_edit = ui.entry(text = password_md5, password = True)
    grid.attach(pass_edit, 1, 2, 2, 3)

    window.connect('destroy', settings_changed, user_edit, pass_edit)

    window.show_all()

    window.present()


def settings_changed(obj, entry1, entry2):
    global username, password_md5

    username = entry1.get_text()
    if entry2.get_text() != password_md5:
        password_md5 = md5(entry2.get_text()).hexdigest()
    save_settings()
    scrobl.login(username, password_md5)


def read_settings():
    global password_md5, username

    if os.path.isfile(os.path.expanduser(config_file)):
        config = ConfigParser.ConfigParser()
        config.read(os.path.expanduser(config_file))
        if config.has_option("scrobbler", "username"):
            if config.has_option("scrobbler", "password_md5"):
                username = config.get("scrobbler", "username")
                password_md5 = config.get("scrobbler", "password_md5")
            else:
                print _("Scrobbler don't know your last.fm password.")
        else:
            print _("Scrobbler don't know your last.fm username.")
    else:
        print _("Scrobbler don't have config, it must be in %s") % config_file


def save_settings():
    config = ConfigParser.ConfigParser()
    config.add_section('scrobbler')
    config.set('scrobbler', 'username', username)
    config.set('scrobbler', 'password_md5', password_md5)

    with open(os.path.expanduser(config_file), 'wb') as file:
        config.write(file)

