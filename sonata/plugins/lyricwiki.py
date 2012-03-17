
### BEGIN PLUGIN INFO
# [plugin]
# plugin_format: 0, 0
# name: LyricWiki
# version: 0, 1, 0
# description: Fetch lyrics from lyrics.wikia.com.
# author: Anton Lashkov
# author_email: Lenton_91@mail.ru
# url:
# license: GPL v3 or later
# [capabilities]
# enablables: on_enable
# lyrics_fetching: get_lyrics
### END PLUGIN INFO


import urllib

lyricwiki = None

class LyricWiki(object):

    def __init__(self):
        pass

    def lyricwiki_format(self, text):
        return urllib.quote(str(unicode(text).title()))

    def get_lyrics(self, search_artist, search_title):

        try:
            addr = 'http://lyrics.wikia.com/index.php?title=%s:%s&action=edit' % (self.lyricwiki_format(search_artist), self.lyricwiki_format(search_title))
            content = urllib.urlopen(addr).read()

            lyrics = content.split("&lt;lyrics>")[1].split("&lt;/lyrics>")[0].strip()
            if lyrics != ("&lt;!-- PUT LYRICS HERE (and delete this entire line) -->") and lyrics != "":
                return lyrics.decode("utf-8")
            else:
                return None
        except Exception:
            return None


def on_enable(state):

    global lyricwiki

    if state:
        if lyricwiki is None:
            lyricwiki = LyricWiki()

def get_lyrics(artist, title):

    return lyricwiki.get_lyrics(artist, title)
