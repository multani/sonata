
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

import logging
import urllib.request


logger = logging.getLogger(__name__)
BASE_URL = 'http://lyrics.wikia.com/index.php?'
EMPTY_LYRICS = "&lt;!-- PUT LYRICS HERE (and delete this entire line) -->"


def quote(value):
    return urllib.request.quote(str(value).title())


def get_lyrics(artist, title):
    addr = BASE_URL + 'title=%s:%s&action=edit' % (quote(artist), quote(title))

    logger.info("Downloading lyrics from %r", addr)
    content = urllib.request.urlopen(addr).read().decode('utf-8')
    lyrics = content.split("&lt;lyrics>")[1].split("&lt;/lyrics>")[0].strip()

    if lyrics != "" and lyrics != EMPTY_LYRICS:
        return lyrics
    else:
        return None


if __name__ == "__main__":
    print(get_lyrics("anti-flag", "Death Of A Nation"))
