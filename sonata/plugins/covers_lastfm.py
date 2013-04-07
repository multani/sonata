### BEGIN PLUGIN INFO
# [plugin]
# name: Last.fm covers
# plugin_format: 0, 0
# version: 1, 0, 0
# description: Fetch album covers from www.last.fm
# author: Jonathan Ballet
# author_email: jon@multani.info
# url: https://github.com/multani/sonata
# license: GPL v3 or later
# [capabilities]
# cover_fetching: on_cover_fetch
### END PLUGIN INFO

import json
import logging
import shutil
import urllib
from urllib import error, request, parse

from sonata.version import version


API_KEY = "41a1b04ed273fe997d2fddc3823dfb0f"
logger = logging.getLogger(__name__)


def make_user_agent():
    return "Sonata/%s +https://github.com/multani/sonata/" % version


def on_cover_fetch(artist, album, on_save_cb, on_err_cb):
    handler = urllib.request.HTTPHandler()
    opener = urllib.request.build_opener(handler)
    opener.addheaders = [("User-Agent", make_user_agent())]

    # First, find the link to the master release of this album
    search_url = "http://ws.audioscrobbler.com/2.0/?%s" % (
        urllib.parse.urlencode({
            "method": "album.getInfo",
            "artist": artist,
            "album": album,
            "api_key": API_KEY,
            "format": "json",
        }))

    logger.debug("Querying %r...", search_url)
    response = opener.open(search_url)
    lastfm = json.loads(response.read().decode('utf-8'))

    if 'error' in lastfm:
        logger.warning("Can't find cover on Last.fm: %s (err=%d)",
                       lastfm['message'], lastfm['error'])
        return

    for image in lastfm['album']['image']:
        if image['size'] != 'mega':
            continue

        url = image['#text']
        if url == '':
            logger.info("Found an album on Last.fm, but no cover :( %s",
                        lastfm['album']['url'])
            continue

        logger.debug("Downloading %r", url)
        try:
            response = opener.open(url)
        except urllib.error.URLError as e:
            logger.warning("Can't download %r: %s", url, e)
            if on_err_cb("Can't download %r: %s" % (url, e)):
                break
            else:
                continue

        if not on_save_cb(response):
            break


if __name__ == '__main__':
    import os
    import subprocess
    import tempfile
    logging.basicConfig(level=logging.DEBUG)
    fp, dest = tempfile.mkstemp(".png")

    def on_save(data):
        os.write(fp, data.read())
        os.close(fp)
        return False

    def on_err():
        print("Error!")
        return True

    result = on_cover_fetch("Metallica", "Ride the lightning", on_save, on_err)
    print(dest)
    subprocess.call(['xdg-open', dest])
