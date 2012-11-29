### BEGIN PLUGIN INFO
# [plugin]
# name: Discogs covers
# plugin_format: 0, 0
# version: 0, 0, 1
# description: Fetch album covers from www.discogs.com
# author: Jonathan Ballet
# author_email: jon@multani.info
# url: http://multani.info/projects/sonata/discogs-covers
# license: GPL v3 or later
# [capabilities]
# cover_fetching: on_cover_fetch
### END PLUGIN INFO

import json
import logging
import shutil
import urllib.request
import urllib.parse
import urllib.error

from sonata.version import version


logger = logging.getLogger(__name__)


def make_user_agent():
    return "Sonata/%s +http://sonata.berlios.de" % version


def on_cover_fetch(callback, artist, album, destination, all_images):
    try:
        result, headers = _cover_fetching(callback,
                               artist, album,
                               destination, all_images)
    except urllib.error.URLError as e:
        logger.info("Unable to fetch cover from Discogs: %s", e.reason)
        return False

    log_discogs_limits(headers)
    return result

def _cover_fetching(callback, artist, album, destination, all_images):

    logger.debug("Looking for a cover for %r from %r", album, artist)

    opener = urllib.request.build_opener()
    opener.addheaders = [("User-Agent", make_user_agent())]

    # First, find the link to the master release of this album
    search_url = "http://api.discogs.com%s?%s" % (
        "/database/search",
        urllib.parse.urlencode({
            "type": "master",
            "artist": artist,
            "release_title": album,
        }))

    logger.debug("Querying %r...", search_url)
    response = opener.open(search_url)
    result = json.loads(response.read().decode('utf-8'))

    if len(result["results"]) == 0:
        logger.info("Can't find a cover for %r from %r", album, artist)
        return

    if all_images:
        # We have a link to the master release, get the master to find the URL to
        # the image.
        found = False
        headers = response.headers
        masters = result["results"]
        for master_nb, master in enumerate(masters):
            master_url = master["resource_url"]
            logger.debug("Opening master %r (%d/%d)",
                        master_url, master_nb + 1, len(masters))
            response = opener.open(master_url)
            result = json.loads(response.read().decode('utf-8'))

            headers = response.headers
            for i, image in enumerate(result['images']):
                dest = destination.replace("<imagenum>", "%d-%d" % (master_nb, i + 1))
                image_url = image["resource_url"]

                logger.debug("Downloading %r to %r (%d/%d)",
                             image_url, dest, i + 1, len(result["images"]))
                headers = download_resource_to(opener, image_url, dest)
                found = True

                if not callback(dest, i):
                    return found, headers # cancelled

        return found, headers
    else:
        # We have a link to the master release, get the master to find the URL to
        # the image.
        master_url = result["results"][0]["resource_url"]
        logger.debug("Found %d master albums, opening %r",
                     len(result["results"]),
                    master_url)

        logger.debug("Querying %r...", master_url)
        response = opener.open(master_url)
        result = json.loads(response.read().decode('utf-8'))

        for image in result["images"]:
            if image["type"] == "primary":
                break

        # Now, get the image!
        image_url = image["resource_url"]
        logger.debug("Found %d images, downloading %r",
                     len(result["images"]), image_url)
        headers = download_resource_to(opener, image_url, destination)

        return True, headers




def download_resource_to(opener, url, destination):
    try:
        result = opener.open(url)
    except HTTPError as e:
        if e.code == 403:
            # http://www.discogs.com/developers/accessing.html#rate-limiting
            logger.info(
                "Can't retrieve image %r from Discogs, it looks like you "
                "requested too much images for today.", url)
        else:
            raise

    with open(destination, "wb") as fp:
        shutil.copyfileobj(result, fp)

    return result.headers


def log_discogs_limits(headers):
    try:
        remaining = int(headers["x-ratelimit-remaining"])
    except KeyError:
        remaining = None

    try:
        limit = int(headers["x-ratelimit-limit"])
    except KeyError:
        limit = None

    if remaining is not None and limit is not None:
        ratio_used = (limit - remaining) * 100 / limit
        if ratio_used >= 90:
            logger.warning("You used %d%% of your allowed images' fetching on "
                           "Discogs, soon it will stop working for 24 hours!",
                           ratio_used)
        else:
            logger.debug("You used %d%% of your allowed images' fetching on "
                         "Discogs.", ratio_used)
    else:
        logger.debug("You can still query %s times Discogs for images (your "
                     "max is %s times).",
                     remaining or "(unknown)", limit or "(unknown)")


if __name__ == '__main__':
    import os
    import tempfile
    logging.basicConfig(level=logging.DEBUG)
    fp, dest = tempfile.mkstemp()
    os.close(fp)

    result = on_cover_fetch(lambda *args, **kwargs:
                            print("Call callback with (%r, %r)" % (
                                args, kwargs)),
                            "Metallica", "Ride the lightning", dest, False)
    print(dest)
