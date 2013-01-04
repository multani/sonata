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


def on_cover_fetch(callback, artist, album, destination, all_images):
    try:
        return _cover_fetching(callback,
                               artist, album,
                               destination, all_images)
    except urllib.error.URLError as e:
        logger.info("Unable to fetch cover from Last.fm: %s", e.reason)
    except Exception as e:
        logger.info("Unable to fetch cover from Last.fm: %s", e)

    return False

def _cover_fetching(callback, artist, album, destination, all_images):

    logger.debug("Looking for a cover for %r from %r", album, artist)

    handler = urllib.request.HTTPHandler()
    opener = urllib.request.build_opener(handler)
    opener.addheaders = [("User-Agent", make_user_agent())]

    def urlretrieve(url, dest):
        logger.debug("Downloading %r into %r", url, dest)
        u = opener.open(url)
        with open(dest, "wb") as fp:
            shutil.copyfileobj(u, fp)

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

    if all_images:
        image_found = False

        for i, image in enumerate(lastfm['album']['image']):
            filename = destination.replace("<imagenum>", str(i + 1))
            try:
                urlretrieve(image['#text'], filename)
            except urllib.error.URLError as e:
                logger.warning("Can't download %r: %s", image.text, e)
                continue

            image_found = True

            if not callback(filename, i):
                # Cancelled
                break

        return image_found

    else:
        image = [i['#text'] for i in lastfm['album']['image']
                 if i['size'] == 'large']
        if len(image) == 0:
            return False
        else:
            urlretrieve(image[0], destination)
            return True


if __name__ == '__main__':
    import os
    import subprocess
    import tempfile
    logging.basicConfig(level=logging.DEBUG)
    fp, dest = tempfile.mkstemp(".png")
    os.close(fp)

    def callback(*args, **kwargs):
        print("Call callback with (%r, %r)" % (args, kwargs))

    result = on_cover_fetch(callback,
                            "Metallica", "Ride the lightning",
                            dest, False)
    print(dest)
    subprocess.call(['xdg-open', dest])
