import os
import urllib
import re
import sys
import threading # get_lyrics_start starts a thread get_lyrics_thread

import gobject

import misc
import mpdhelper as mpdh
from consts import consts
from pluginsystem import pluginsystem, BuiltinPlugin


class LyricWiki(object):

    def __init__(self):
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
        NO_LYRICS = '&lt;!-- PUT LYRICS HERE (and delete this entire line) --&gt;'

        def get_content(page):
            content = page.read()
            content = re_textarea.split(content)[1].split("</textarea>")[0]
            return content.strip()

        try:
            addr = 'http://lyrics.wikia.com/index.php?title=%s:%s&action=edit' \
                    % (self.lyricwiki_format(artist), self.lyricwiki_format(title))
            content = get_content(urllib.urlopen(addr))

            if content.lower().startswith("#redirect"):
                addr = "http://lyrics.wikia.com/index.php?title=%s&action=edit" \
                        % urllib.quote(content.split("[[")[1].split("]]")[0])
                content = get_content(urllib.urlopen(addr))

            lyrics = content.split("&lt;lyrics&gt;")[1].split("&lt;/lyrics&gt;")[0].strip()
            if lyrics != NO_LYRICS:
                lyrics = misc.unescape_html(lyrics)
                lyrics = misc.wiki_to_html(lyrics)
                lyrics = lyrics.decode("utf-8")
                self.call_back(callback, lyrics=lyrics)
            else:
                error = _("Lyrics not found")
                self.call_back(callback, error=error)
        except Exception, e:
            print >> sys.stderr, "Error while fetching the lyrics:\n%s" % e
            error = _("Fetching lyrics failed")
            self.call_back(callback, error=error)

    def call_back(self, callback, lyrics=None, error=None):
        gobject.timeout_add(0, callback, lyrics, error)
