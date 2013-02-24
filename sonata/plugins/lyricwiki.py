
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
import re
from urllib.request import quote, urlopen


logger = logging.getLogger(__name__)
BASE_URL = 'http://lyrics.wikia.com/index.php?'
EMPTY_LYRICS = "&lt;!-- PUT LYRICS HERE (and delete this entire line) -->"

# Redirect marker such as "#REDIRECT [[The Clash:Police And Thieves]]"
RE_REDIRECT = re.compile(r"#REDIRECT \[\[(.*):(.*)\]\]")


def get_lyrics(artist, title, recurse_count=0):
    addr = BASE_URL + 'title=%s:%s&action=edit' % (quote(artist), quote(title))

    logger.info("Downloading lyrics from %r", addr)
    content = urlopen(addr).read().decode('utf-8')

    if RE_REDIRECT.search(content):
        if recurse_count >= 10:
            # OK, we looped a bit too much, just suppose we couldn't find any
            # lyrics
            logger.info("Too many redirects to find lyrics for %r: %r",
                        artist, title)
            return None

        new_artist, new_title = RE_REDIRECT.search(content).groups()
        logger.debug("Lyrics for '%s: %s' redirects to '%s: %s'",
                     artist, title, new_artist, new_title)
        return get_lyrics(new_artist, new_title, recurse_count + 1)

    lyrics = content.split("&lt;lyrics>")[1].split("&lt;/lyrics>")[0].strip()

    if lyrics != "" and lyrics != EMPTY_LYRICS:
        return lyrics
    else:
        return None


if __name__ == "__main__":
    print(get_lyrics("Anti-Flag", "Death Of A Nation"))
