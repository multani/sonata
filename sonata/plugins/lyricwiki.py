
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

import html
import logging
import re
from urllib.request import quote, urlopen
from urllib.error import HTTPError


logger = logging.getLogger(__name__)
BASE_URL = 'http://lyrics.wikia.com/index.php?'
EMPTY_LYRICS = "&lt;!-- PUT LYRICS HERE (and delete this entire line) -->"

START_MARK = "<div class='lyricbox'>"
END_MARK = "<div class='lyricsbreak'>"


# Redirect marker such as "#REDIRECT [[The Clash:Police And Thieves]]"
RE_REDIRECT = re.compile(r"#REDIRECT \[\[(.*):(.*)\]\]")


def get_lyrics(artist, title, recurse_count=0):
    url = BASE_URL + 'title=%s:%s' % (quote(artist), quote(title))

    logger.info("Downloading lyrics from %r", url)
    try:
        content = urlopen(url).read().decode('utf-8')
    except HTTPError as exc:
        logger.warning("Unable to download lyrics from %r: %s", url, exc)
        return None

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

    if START_MARK in content and END_MARK in content:
        lyrics = content.split(START_MARK)[1].split(END_MARK)[0].strip()
        lyrics = html.unescape(lyrics)
        lyrics = lyrics.replace("<br />", "\n")

        if lyrics != "" and lyrics != EMPTY_LYRICS:
            return lyrics
    else:
        logger.warning("Unable to find LyricsWiki lyrics markers delimitations")

    return None


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("artist")
    parser.add_argument("title")
    args = parser.parse_args()

    logging.basicConfig(level=logging.DEBUG)
    print(get_lyrics(args.artist, args.title))
