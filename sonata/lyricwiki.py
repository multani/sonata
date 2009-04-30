
import os, urllib

import threading # get_lyrics_start starts a thread get_lyrics_thread

from socket import getdefaulttimeout as socketgettimeout
from socket import setdefaulttimeout as socketsettimeout

import gobject
ServiceProxy = None # importing tried when needed

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
        lyricThread = threading.Thread(target=self.get_lyrics_thread, args=args)
        lyricThread.setDaemon(True)
        lyricThread.start()

    def lyricwiki_format(self, text):
        return urllib.quote(str(unicode(text).title()))

    def lyricwiki_editlink(self, songinfo):
        artist, title = [self.lyricwiki_format(mpdh.get(songinfo, key))
                 for key in ('artist', 'title')]
        return ("http://lyricwiki.org/index.php?title=%s:%s&action=edit" %
            (artist, title))

    def get_lyrics_thread(self, callback, artist, title):
        # FIXME locking...
        global ServiceProxy
        if ServiceProxy is None:
            try:
                from ZSI import ServiceProxy
                # Make sure we have the right version..
                if not hasattr(ServiceProxy, 'ServiceProxy'):
                    ServiceProxy = None
            except ImportError:
                ServiceProxy = None
        if ServiceProxy is None:
            self.call_back(callback, None, None, error=_("ZSI not found, fetching lyrics support disabled."))
            return

        # FIXME locking...
        if self.lyricServer is None:
            wsdlFile = "http://lyricwiki.org/server.php?wsdl"
            try:
                self.lyricServer = True
                timeout = socketgettimeout()
                socketsettimeout(consts.LYRIC_TIMEOUT)
                self.lyricServer = ServiceProxy.ServiceProxy(wsdlFile, cachedir=os.path.expanduser("~/.service_proxy_dir"))
            except:
                self.lyricServer = None
                socketsettimeout(timeout)
                error = _("Couldn't connect to LyricWiki")
                self.call_back(callback, error=error)
                return

        try:
            timeout = socketgettimeout()
            socketsettimeout(consts.LYRIC_TIMEOUT)
            lyrics = self.lyricServer.getSong(artist=self.lyricwiki_format(artist), song=self.lyricwiki_format(title))['return']["lyrics"]
            if lyrics.lower() != "not found":
                lyrics = misc.unescape_html(lyrics)
                lyrics = misc.wiki_to_html(lyrics)
                lyrics = lyrics.encode("ISO-8859-1")
                self.call_back(callback, lyrics=lyrics)
            else:
                error = _("Lyrics not found")
                self.call_back(callback, error=error)
        except:
            error = _("Fetching lyrics failed")
            self.call_back(callback, error=error)

        socketsettimeout(timeout)

    def call_back(self, callback, lyrics=None, error=None):
        gobject.timeout_add(0, callback, lyrics, error)
