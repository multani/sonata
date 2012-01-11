### BEGIN PLUGIN INFO
# [plugin]
# name: Last.fm covers
# plugin_format: 0, 0
# version: 0, 0, 1
# description: Fetch album covers from www.last.fm
# author: Jonathan Ballet
# author_email: jon@multani.info
# url: http://multani.info/projects/sonata/lastfm-covers
# license: GPL v3 or later
# [capabilities]
# cover_fetching: on_cover_fetch
### END PLUGIN INFO

# TODO: API key specific to Sonata
# TODO: errore checking (see http://www.last.fm/api/show?service=290)
# TODO: handle malformed XML

import logging
import shutil
import urllib
import urllib2
from xml.etree import ElementTree

from sonata.pluginsystem import pluginsystem, BuiltinPlugin
from sonata.version import version


API_KEY = "166213f4a8ec2e428923dbd9ea9c87b7"
logger = logging.getLogger(__name__)


def make_user_agent():
    return "Sonata/%s +http://sonata.berlios.de" % version


def on_cover_fetch(callback, artist, album, destination, all_images):
    try:
        return _cover_fetching(callback,
                               artist, album,
                               destination, all_images)
    except urllib2.URLError, e:
        logger.info("Unable to fetch cover from Last.fm: %s", e.reason)
        return False


def _cover_fetching(callback, artist, album, destination, all_images):

    logger.debug("Looking for a cover for %r from %r", album, artist)

    opener = urllib2.build_opener()
    opener.addheaders = [("User-Agent", make_user_agent())]

    # First, find the link to the master release of this album
    search_url = "http://ws.audioscrobbler.com/2.0/?%s" % (
        urllib.urlencode({
            "method": "album.getInfo",
            "artist": artist,
            "album": album,
            "api_key": API_KEY,
        }))

    logger.debug("Querying %r...", search_url)
    response = opener.open(search_url)

    tree = ElementTree.parse(response)
    image = tree.find('album/image[@size="large"]')

    logger.debug("Downloading image from %s", image.text)
    image_response = opener.open(image.text)

    with open(destination, "w") as fp:
        shutil.copyfileobj(image_response, fp)
