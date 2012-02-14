from HTMLParser import HTMLParser
import logging
import os
import urllib
import re
import sys
import threading # get_lyrics_start starts a thread get_lyrics_thread

from gi.repository import GObject

from sonata import misc, mpdhelper as mpdh
from sonata.consts import consts
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
        lyricThread = threading.Thread(target=self.get_lyrics_thread,
                                       args=args)
        lyricThread.setDaemon(True)
        lyricThread.start()

    def lyricwiki_format(self, text):
        return urllib.quote(str(unicode(text).title()))

    def lyricwiki_editlink(self, songinfo):
        artist, title = [self.lyricwiki_format(mpdh.get(songinfo, key))
                 for key in ('artist', 'title')]
        return ("http://lyrics.wikia.com/index.php?title=%s:%s&action=edit" %
            (artist, title))

    def get_lyrics_thread(self, callback, artist, title):

        re_textarea = re.compile(r'<textarea[^>]*>')
        NO_LYRICS = '<!-- PUT LYRICS HERE (and delete this entire line) -->'

        def get_content(page):
            content = page.read()
            content = re_textarea.split(content)[1].split("</textarea>")[0]
            # Transform HTML entities, like '&lt;' into '<', of the textarea
            # content.
            content = HTMLParser().unescape(content)
            return content.strip()

        try:
            addr = 'http://lyrics.wikia.com/index.php?title=%s:%s&action=edit' \
                    % (self.lyricwiki_format(artist), self.lyricwiki_format(title))
            self.logger.debug("Searching lyrics for %r from %r using %r",
                              title, artist, addr)
            content = get_content(urllib.urlopen(addr))

            if content.lower().startswith("#redirect"):
                addr = "http://lyrics.wikia.com/index.php?title=%s&action=edit" \
                        % urllib.quote(content.split("[[")[1].split("]]")[0])
                self.logger.debug("Redirected to %r", addr)
                content = get_content(urllib.urlopen(addr))

            lyrics = content.split("<lyrics>")[1].split("</lyrics>")[0].strip()
            if lyrics != NO_LYRICS:
                lyrics = misc.unescape_html(lyrics)
                lyrics = misc.wiki_to_html(lyrics)
                lyrics = lyrics.decode("utf-8")
                self.logger.debug("Found lyrics for %r from %r", title, artist)
                self.call_back(callback, lyrics=lyrics)
            else:
                self.logger.debug("No lyrics found for %r from %r", title, artist)
                error = _("Lyrics not found")
                self.call_back(callback, error=error)
        except:
            self.logger.exception(
                "Error while fetching the lyrics for %r from %r", title, artist)
            error = _("Fetching lyrics failed")
            self.call_back(callback, error=error)

    def call_back(self, callback, lyrics=None, error=None):
        gobject.timeout_add(0, callback, lyrics, error)
