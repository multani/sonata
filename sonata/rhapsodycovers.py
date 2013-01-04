import logging
import os
import urllib.request
from xml.etree import ElementTree

from sonata.pluginsystem import pluginsystem, BuiltinPlugin

class RhapsodyCovers:
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        pluginsystem.plugin_infos.append(BuiltinPlugin(
                'rhapsodycovers', "Rhapsody Covers",
                "Fetch album covers from Rhapsody.com.",
                {'cover_fetching': 'get_cover'}, self))

    def _sanitize_query(self, str):
        return str.replace(" ", "").replace("'", "").replace("&","")

    def get_cover(self, progress_callback, artist, album, dest_filename,
              all_images=False):
        return self.artwork_download_img_to_file(progress_callback, artist, album, dest_filename, all_images)

    def artwork_download_img_to_file(self, progress_callback, artist, album, dest_filename, all_images=False):
        if not artist and not album:
            return False

        rhapsody_uri = "http://feeds.rhapsody.com"
        url = "%s/%s/%s/data.xml" % (rhapsody_uri, artist, album)
        url = self._sanitize_query(url)
        self.logger.debug("Finding cover from %r", url)
        try:
            request = urllib.request.urlopen(url)
            body = request.read()
            xml = ElementTree.fromstring(body)
            imgs = xml.getiterator("img")
        except Exception as e:
            self.logger.error("Unable to find cover from %r: %s", url, e)
            return False

        imglist = [img.attrib['src'] for img in imgs if img.attrib['src']]
        # Couldn't find any images
        if not imglist:
            return False

        if not all_images:
            try:
                src  = urllib.request.urlopen(imglist[-1])
                dest = open(dest_filename, "w")
                dest.write(src.read())
            except (IOError, HTTPError, URLError) as e:
                self.logger.error("Unable to fetch cover image from %r: %s", \
                                  imglist[-1], e)
                return False
            return True
        else:
            try:
                imgfound = False
                for i, image in enumerate(imglist):
                    dest_filename_curr = dest_filename.replace("<imagenum>", str(i+1))
                    src  = urllib.request.urlopen(image)
                    dest = open(dest_filename_curr, "w")
                    dest.write(src.read())
                    if not progress_callback(
                        dest_filename_curr, i):
                        return imgfound # cancelled
                    if os.path.exists(dest_filename_curr):
                        imgfound = True
            except (IOError, HTTPError, URLError) as e:
                self.logger.error("Unable to fetch cover image from %r: %s", url, e)
            return imgfound
