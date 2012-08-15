### BEGIN PLUGIN INFO
# [plugin]
# plugin_format: 0, 0
# name: Last.fm integration
# version: 0, 0, 1
# description: This plugin integrate Sonata with Last.fm: scrobbler, "add to favorites" button.
# author: Lashkov Anton
# author_email: lenton_91@mail.ru
# url: http://onto.co.cc
# license: GPL v3
# [capabilities]
# enablables: on_enable
# handle_change_status: handle_change_status
# plugin_configure: configure
# add_toolbar_button: add_toolbar_button
# playing_song_observers: playing_song_observers
### END PLUGIN INFO

import pylast
import os
import ConfigParser
import gtk
import logging
import sonata.mpdhelper as mpdh
import sonata.ui as ui
import time
import threading
import sys


API_KEY = "5b69a6c2184032a9908434bb157a6f58"
API_SECRET = "7710f994b19163d225d8a2f44b3fa0bf"

CONFIG_FILE = "~/.config/sonata/scrobbler"

username = ""
password_md5 = ""

network = None

logger = logging.getLogger(__name__)

current_state = None

scrob_start_time = ""
scrob_playing_duration = 0
scrob_last_prepared = ""
scrob_prev_time = ""
elapsed_now = None

def on_enable(state):
    if state:
        read_settings()
        try:
            login()
        except:
            pass


def login():
    global network, username, password_md5

    if username != "" and password_md5 != "":
        if network is None:
            network = pylast.LastFMNetwork(api_key=API_KEY,
                                           api_secret=API_SECRET,
                                           username=username,
                                           password_hash=password_md5)
    else:
        configure()


def playing_song_observers(songinfo):
    global current_state

    current_state = songinfo


def add_toolbar_button():
    button = ui.button(relief=gtk.RELIEF_NONE, can_focus=False)
    button.props.image = gtk.image_new_from_icon_name('emblem-favorite',
                                                      gtk.ICON_SIZE_BUTTON)
    button.set_tooltip_text(_("Add to favorites on Last.Fm"))
    button.connect("clicked", add_to_favorites)

    return button


def add_to_favorites(obj):
    if current_state and network:
        network.get_track(mpdh.get(current_state, 'artist'),
                          mpdh.get(current_state, 'title')).love()


def handle_change_status(state, prevstate, prevsonginfo,
                         songinfo = None, mpd_time_now = None):
    """Handle changes to play status, submitting info as appropriate"""

    global scrob_start_time, scrob_playing_duration, scrob_last_prepared,\
    elapsed_now, scrob_prev_time, network

    if not network:
        try:
            login()
        except:
            return

    if prevsonginfo and 'time' in prevsonginfo:
        prevsong_time = mpdh.get(prevsonginfo, 'time')
    else:
        prevsong_time = None

    if state in ('play', 'pause'):
        elapsed_prev = elapsed_now
        elapsed_now, length = [float(c) for c in
                               mpd_time_now.split(':')]
        current_file = mpdh.get(songinfo, 'file')
        if prevstate == 'stop':
            # Switched from stop to play, prepare current track:
            prepare(songinfo)
        elif (prevsong_time and
              (scrob_last_prepared != current_file or
               (scrob_last_prepared == current_file and
                elapsed_prev and elapsed_now <= 1 and
                elapsed_now < elapsed_prev and length > 0))):
            # New song is playing, post previous track if time criteria is
            # met. In order to account for the situation where the same
            # song is played twice in a row, we will check if previous
            # elapsed time was larger than current and we're at the
            # beginning of the same song now
            if scrob_playing_duration > 4 * 60 or\
               scrob_playing_duration > int(prevsong_time) / 2:
                if scrob_start_time != "":
                    post(prevsonginfo)
                # Prepare current track:
            prepare(songinfo)
            # Keep track of the total amount of time that the current song
        # has been playing:
        now = time.time()
        if prevstate != 'pause':
            scrob_playing_duration += now - scrob_prev_time
        scrob_prev_time = now
    else: # stopped:
        elapsed_now = 0
        if prevsong_time:
            if scrob_playing_duration > 4 * 60 or\
               scrob_playing_duration > int(prevsong_time) / 2:
                # User stopped the client, post previous track if time
                # criteria is met:
                if scrob_start_time != "":
                    post(prevsonginfo)


def prepare(songinfo):
    global scrob_start_time, scrob_playing_duration, scrob_last_prepared,\
    scrob_prev_time

    scrob_start_time = ""
    scrob_last_prepared = ""
    scrob_playing_duration = 0
    scrob_prev_time = time.time()

    if songinfo:
        # No need to check if the song is 30 seconds or longer,
        if 'time' in songinfo:
            np(songinfo)

            scrob_start_time = str(int(time.time()))
            scrob_last_prepared = mpdh.get(songinfo, 'file')


def post(prevsonginfo):
    global scrob_start_time, network

    if prevsonginfo:
        if 'artist' in prevsonginfo and\
           'title' in prevsonginfo and\
           'time' in prevsonginfo:
            if not 'album' in prevsonginfo:
                album = u''
            else:
                album = mpdh.get(prevsonginfo, 'album')
            if not 'track' in prevsonginfo:
                tracknumber = u''
            else:
                tracknumber = mpdh.get(prevsonginfo, 'track').split('/')[0]
            try:
                network.scrobble(mpdh.get(prevsonginfo, 'artist'),
                                 mpdh.get(prevsonginfo, 'title'),
                                 scrob_start_time, album=album,
                                 duration=mpdh.get(prevsonginfo, 'time'),
                                 track_number=tracknumber)
            except:
                logger.error(sys.exc_info()[1])

    scrob_start_time = ""


def np(songinfo):
    thread = threading.Thread(target=do_np, args=(songinfo,))
    thread.setDaemon(True)
    thread.start()


def do_np(songinfo):
    global network

    if songinfo:
        if 'artist' in songinfo and\
           'title' in songinfo and\
           'time' in songinfo:
            if not 'album' in songinfo:
                album = u''
            else:
                album = mpdh.get(songinfo, 'album')
            if not 'track' in songinfo:
                tracknumber = u''
            else:
                tracknumber = mpdh.get(songinfo, 'track').split('/')[0]
            try:
                network.update_now_playing(mpdh.get(songinfo, 'artist'),
                                           mpdh.get(songinfo, 'title'),
                                           album=album,
                                           duration=mpdh.get(songinfo, 'time'),
                                           track_number=tracknumber)
            except:
                logger.error(sys.exc_info()[1])
    time.sleep(10)


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

    user_edit = ui.entry(text=username)
    grid.attach(user_edit, 1, 2, 1, 2)

    pass_edit = ui.entry(text=password_md5, password=True)
    grid.attach(pass_edit, 1, 2, 2, 3)

    window.connect('destroy', settings_changed, user_edit, pass_edit)

    window.show_all()

    window.present()


def settings_changed(obj, entry1, entry2):
    global username, password_md5, network

    username = entry1.get_text()
    if entry2.get_text() != password_md5:
        password_md5 = pylast.md5(entry2.get_text()).hexdigest()

    config = ConfigParser.ConfigParser()
    config.add_section('scrobbler')
    config.set('scrobbler', 'username', username)
    config.set('scrobbler', 'password_md5', password_md5)

    with open(os.path.expanduser(CONFIG_FILE), 'wb') as file:
        config.write(file)

    #(re)connect
    try:
        login()
    except:
        pass


def read_settings():
    global password_md5, username

    if os.path.isfile(os.path.expanduser(CONFIG_FILE)):
        config = ConfigParser.ConfigParser()
        config.read(os.path.expanduser(CONFIG_FILE))
        if config.has_option("scrobbler", "username"):
            if config.has_option("scrobbler", "password_md5"):
                username = config.get("scrobbler", "username")
                password_md5 = config.get("scrobbler", "password_md5")
            else:
                logger.warning(_("Scrobbler don't know your last.fm password."))
        else:
            logger.warning(_("Scrobbler don't know your last.fm username."))
    else:
        logger.warning(_("Scrobbler don't have config, it must be in %s") %
                       CONFIG_FILE)
