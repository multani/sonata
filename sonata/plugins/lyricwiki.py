
### BEGIN PLUGIN INFO
# [plugin]
# plugin_format: 0, 0
# name: LyricWiki
# version: 0, 2, 0
# description: Fetch lyrics from lyrics.wikia.com.
# author: Anton Lashkov
# author_email: Lenton_91@mail.ru
# url:
# license: GPL v3 or later
# [capabilities]
# lyrics_fetching: get_lyrics
### END PLUGIN INFO

import urllib

def lyricwiki_format(text):
    return urllib.quote(str(unicode(text).title()))

def get_lyrics(search_artist, search_title):
    addr = 'http://lyrics.wikia.com/index.php?title=%s:%s&action=edit' % (
        lyricwiki_format(search_artist), lyricwiki_format(search_title))

    try:
        content = urllib.urlopen(addr).read()
        lyrics = content.split("&lt;lyrics>")[1].split("&lt;/lyrics>")[0].strip()

        if lyrics != \
           ("&lt;!-- PUT LYRICS HERE (and delete this entire line) -->") \
        and lyrics != "":
            return lyrics.decode("utf-8")
        else:
            return None

    except Exception:
        return None

if __name__ == "__main__":
    print get_lyrics("anti-flag", "Death Of A Nation")