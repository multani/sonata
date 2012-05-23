#!/usr/bin/env python

### BEGIN PLUGIN INFO
# [plugin]
# plugin_format: 0, 0
# name: Gajim tune
# version: 0, 0, 1
# description: Update the MPRIS (in Gajim etc.) tune information.
# author: Fomin Denis
# author_email: fominde@gmail.com
# url: http://sonata.berlios.de
# license: GPL v3 or later
# [capabilities]
# enablables: on_enable
# playing_song_observers: on_song_change
### END PLUGIN INFO

import gtk, pango
import dbus.service

songlabel = None
lasttune = ''
tune = None

# this gets called when the plugin is loaded, enabled, or disabled:
def on_enable(state):
    global tune
    if state and not tune:
        tune = mpdtune()
    else:
        if tune:
            title = artist = album = ''
            tune.TrackChange(dbus.Dictionary(
                        {'title' : title, 'artist' : artist, 'album' : album}
                        ))


def on_song_change(songinfo):
    global tune, lasttune
    if lasttune == songinfo:
        return
    lasttune = songinfo
    title = artist = album = ''

    if not songinfo:
        # mpd stopped
        if tune:
            tune.TrackChange(dbus.Dictionary(
                        {'title' : title, 'artist' : artist, 'album' : album}))
        return

    if 'title' in songinfo:
        title = songinfo['title']
    if 'artist' in songinfo:
        artist = songinfo['artist']
    if 'album' in songinfo:
        album = songinfo['album']
    if 'name' in songinfo and artist =='':
        artist = songinfo['name']
    if 'file' in songinfo and title =='':
        album = songinfo['file']
        if not album.startswith('http:'):
            title = album.rpartition('/')[2]
    if tune:
        tune.TrackChange(dbus.Dictionary(
                    {'title' : title, 'artist' : artist, 'album' : album}
                    ))

class mpdtune(dbus.service.Object):
    def __init__(self):
        dbus.service.Object.__init__(self, dbus.SessionBus(), '/Player')
    @dbus.service.signal(dbus_interface = 'org.freedesktop.MediaPlayer')
    def TrackChange(self, trackinfo):
        return

