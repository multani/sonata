import logging
import os
import urllib.request
import re
import sys
import threading # get_lyrics_start starts a thread get_lyrics_thread

from gi.repository import GLib

from sonata import misc, consts, mpdhelper as mpdh
from sonata.pluginsystem import pluginsystem, BuiltinPlugin


class LyricWiki(object):

    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.lyricServer = None

        pluginsystem.plugin_infos.append(BuiltinPlugin(
                'lyricwiki', "LyricWiki",
                "Fetch lyrics from LyricWiki.",
                {'lyrics_fetching': 'get_lyrics_start'}, self))

    def get_lyrics_start(self, *args):
        lyric_thread = threading.Thread(target=self.get_lyrics_thread,
                                       args=args)
        lyric_thread.daemon = True
        lyric_thread.start()

    def lyricwiki_format(self, text):
        return urllib.request.quote(str(text).title())

    def lyricwiki_editlink(self, songinfo):
        artist, title = [self.lyricwiki_format(mpdh.get(songinfo, key))
                 for key in ('artist', 'title')]
        return ("http://lyrics.wikia.com/index.php?title=%s:%s&action=edit" %
            (artist, title))

    def get_lyrics_thread(self, callback, artist, title):

        NO_LYRICS = 'Not Found'

        try:
            addr = 'http://lyrics.wikia.com/api.php?artist=%s&song=%s&fmt=text' \
                    % (self.lyricwiki_format(artist), self.lyricwiki_format(title))
            self.logger.debug("Searching lyrics for %r from %r using %r",
                              title, artist, addr)
            response = urllib.request.urlopen(addr)
            lyrics = str(response.read().decode("utf-8"))

            if lyrics != NO_LYRICS:
                self.logger.debug("Found lyrics for %r from %r", title, artist)
                self.call_back(callback, lyrics=lyrics)
            else:
                self.logger.debug("No lyrics found for %r from %r", title, artist)
                error = _("Lyrics not found")
                self.call_back(callback, error=error)
        except Exception as e:
            self.logger.error(
                "Error while fetching the lyrics for %r from %r: %s",
                title, artist, e)
            error = _("Fetching lyrics failed")
            self.call_back(callback, error=error)

    def call_back(self, callback, lyrics=None, error=None):
        GLib.timeout_add(0, callback, lyrics, error)
