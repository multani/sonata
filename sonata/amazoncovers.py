
import os
import urllib, urllib2
from xml.etree import ElementTree

import misc
from pluginsystem import pluginsystem, BuiltinPlugin

AMAZON_KEY = "12DR2PGAQT303YTEWP02"
AMAZON_NS = "{http://webservices.amazon.com/AWSECommerceService/2005-10-05}"
AMAZON_URI = "http://webservices.amazon.com/onca/xml?Service=AWSECommerceService&AWSAccessKeyId=%s&Operation=ItemSearch&SearchIndex=Music&Artist=%s&ResponseGroup=Images"

class AmazonCovers(object):
    def __init__(self):
        pluginsystem.plugin_infos.append(BuiltinPlugin(
                'amazoncovers', "Amazon Covers",
                "Fetch album covers from Amazon.com.",
                {'cover_fetching': 'get_cover'}, self))

    def get_cover(self, progress_callback, artist, album, dest_filename,
              all_images=False):
        return self.artwork_download_img_to_file(progress_callback, artist, album, dest_filename, all_images)

    def artwork_download_img_to_file(self, progress_callback, artist, album, dest_filename, all_images=False):
        # Returns False if no images found
        if not artist and not album:
            return False

        # Amazon currently doesn't support utf8 and suggests latin1 encoding instead:
        artist = urllib.quote(artist.encode('latin1', 'replace'))
        album = urllib.quote(album.encode('latin1', 'replace'))

        # Try searching urls from most specific (artist, title) to least specific (artist only)
        urls = [(AMAZON_URI + "&Title=%s") % (AMAZON_KEY, artist, album),
            (AMAZON_URI + "&Keywords=%s") % (AMAZON_KEY, artist, album),
            AMAZON_URI % (AMAZON_KEY, artist)]

        for url in urls:
            request = urllib2.Request(url)
            opener = urllib2.build_opener()
            try:
                body = opener.open(request).read()
                xml = ElementTree.fromstring(body)
                largeimgs = xml.getiterator(AMAZON_NS + "LargeImage")
            except:
                largeimgs = None

            if largeimgs:
                break
            elif url == urls[-1]:
                return False

        imgs = misc.iunique(url.text for img in largeimgs for url in img.getiterator(AMAZON_NS + "URL"))
        # Prevent duplicate images in remote art window:
        # FIXME the line above should already accomplish this
        # FIXME this loses the order of the results
        imglist = list(set(list(imgs)))

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
