import os
import urllib
import urllib2
from xml.etree import ElementTree

from pluginsystem import pluginsystem, BuiltinPlugin

class RhapsodyCovers(object):
    def __init__(self):
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
        request = urllib2.Request(url)
        opener = urllib2.build_opener()
        try:
            body = opener.open(request).read()
            xml = ElementTree.fromstring(body)
            imgs = xml.getiterator("img")
        except:
            return False

        imglist = [img.attrib['src'] for img in imgs if img.attrib['src']]
        # Couldn't find any images
        if not imglist:
            return False

        if not all_images:
            urllib.urlretrieve(imglist[0], dest_filename)
            return True
        else:
            try:
                imgfound = False
                for i, image in enumerate(imglist):
                    dest_filename_curr = dest_filename.replace("<imagenum>", str(i+1))
                    urllib.urlretrieve(image, dest_filename_curr)
                    if not progress_callback(
                        dest_filename_curr, i):
                        return imgfound # cancelled
                    if os.path.exists(dest_filename_curr):
                        imgfound = True
            except:
                pass
            return imgfound
