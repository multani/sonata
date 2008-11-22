
import os
import threading # artwork_update starts a thread _artwork_update
import urllib, urllib2
from xml.etree import ElementTree

import gtk, gobject

import img, ui, misc, mpdhelper as mpdh
from misc import iunique
from consts import consts

AMAZON_KEY = "12DR2PGAQT303YTEWP02"
AMAZON_NS = "{http://webservices.amazon.com/AWSECommerceService/2005-10-05}"
AMAZON_URI = "http://webservices.amazon.com/onca/xml?Service=AWSECommerceService&AWSAccessKeyId=%s&Operation=ItemSearch&SearchIndex=Music&Artist=%s&ResponseGroup=Images"

class Artwork(object):
    def __init__(self, config, is_lang_rtl, sonatacd, sonatacd_large, sonatacase, library_browse_update, info_imagebox_get_size_request, schedule_gc_collect, target_image_filename, imagelist_append, remotefilelist_append, notebook_get_allocation, allow_art_search, status_is_play_or_pause):
        self.config = config

        # constants from main
        self.is_lang_rtl = is_lang_rtl
        self.sonatacd = sonatacd
        self.sonatacd_large = sonatacd_large
        self.casepb = gtk.gdk.pixbuf_new_from_file(sonatacase)

        # callbacks to main XXX refactor to clear this list
        self.library_browse_update = library_browse_update
        self.info_imagebox_get_size_request = info_imagebox_get_size_request
        self.schedule_gc_collect = schedule_gc_collect
        self.target_image_filename = target_image_filename
        self.imagelist_append = imagelist_append
        self.remotefilelist_append = remotefilelist_append
        self.notebook_get_allocation = notebook_get_allocation
        self.allow_art_search = allow_art_search
        self.status_is_play_or_pause = status_is_play_or_pause

        self.stop_art_update = None # flag XXX set from main too
        self.downloading_image = False # flag XXX tested from main

        # local UI widgets provided to main by getter methods
        self.albumimage = ui.image()
        self.albumimage.set_from_file(self.sonatacd)

        self.trayalbumimage1 = ui.image(w=51, h=77, x=1)
        self.trayalbumeventbox = ui.eventbox(w=59, h=90, add=self.trayalbumimage1, state=gtk.STATE_SELECTED, visible=True)

        self.trayalbumimage2 = ui.image(w=26, h=77)

        self.fullscreenalbumimage = ui.image(w=consts.FULLSCREEN_COVER_SIZE, h=consts.FULLSCREEN_COVER_SIZE, x=1)
        self.fullscreen_cover_art_set_image(self.sonatacd_large)

        self.info_image = ui.image(y=0)

        # local version of Main.songinfo mirrored by update_songinfo
        self.songinfo = None

        # local state
        self.lastalbumart = None
        self.single_img_in_dir = None
        self.misc_img_in_dir = None

    def get_albumimage(self):
        return self.albumimage

    def get_info_image(self):
        return self.info_image

    def get_trayalbum(self):
        return self.trayalbumeventbox, self.trayalbumimage2

    def get_fullscreenalbumimage(self):
        return self.fullscreenalbumimage

    def update_songinfo(self, songinfo):
        self.songinfo = songinfo

    def on_reset_image(self, _action):
        if self.songinfo:
            if self.songinfo.has_key('name'):
                # Stream, remove file:
                misc.remove_file(self.artwork_stream_filename(mpdh.get(self.songinfo, 'name')))
            else:
                # Normal song:
                misc.remove_file(self.target_image_filename(consts.ART_LOCATION_HOMECOVERS))
                # Use blank cover as the artwork
                dest_filename = self.target_image_filename(consts.ART_LOCATION_HOMECOVERS)
                emptyfile = open(dest_filename, 'w')
                emptyfile.close()
            self.artwork_update(True)

    def artwork_set_tooltip_art(self, pix):
        # Set artwork
        if not self.is_lang_rtl:
            pix1 = pix.subpixbuf(0, 0, 51, 77)
            pix2 = pix.subpixbuf(51, 0, 26, 77)
        else:
            pix1 = pix.subpixbuf(26, 0, 51, 77)
            pix2 = pix.subpixbuf(0, 0, 26, 77)
        self.trayalbumimage1.set_from_pixbuf(pix1)
        self.trayalbumimage2.set_from_pixbuf(pix2)
        del pix1
        del pix2

    def artwork_update(self, force=False):
        if force:
            self.lastalbumart = None

        self.stop_art_update = False
        if not self.config.show_covers:
            return
        if not self.songinfo:
            self.artwork_set_default_icon()
            return

        if self.status_is_play_or_pause():
            thread = threading.Thread(target=self._artwork_update)
            thread.setDaemon(True)
            thread.start()
        else:
            self.artwork_set_default_icon()

    def _artwork_update(self):
        if self.songinfo.has_key('name'):
            # Stream
            streamfile = self.artwork_stream_filename(mpdh.get(self.songinfo, 'name'))
            if os.path.exists(streamfile):
                gobject.idle_add(self.artwork_set_image, streamfile)
            else:
                self.artwork_set_default_icon()
                return
        else:
            # Normal song:
            artist = mpdh.get(self.songinfo, 'artist', "")
            album = mpdh.get(self.songinfo, 'album', "")
            if len(artist) == 0 and len(album) == 0:
                self.artwork_set_default_icon()
                return
            filename = self.target_image_filename()
            if filename == self.lastalbumart:
                # No need to update..
                self.stop_art_update = False
                return
            self.lastalbumart = None
            imgfound = self.artwork_check_for_local()
            if not imgfound:
                if self.config.covers_pref == consts.ART_LOCAL_REMOTE:
                    imgfound = self.artwork_check_for_remote(artist, album, filename)

    def artwork_stream_filename(self, streamname):
        return os.path.expanduser('~/.covers/') + streamname.replace("/", "") + ".jpg"

    def artwork_check_for_local(self):
        self.artwork_set_default_icon()
        self.misc_img_in_dir = None
        self.single_img_in_dir = None
        location_type, filename = self.artwork_get_local_image()

        if location_type is not None and filename:
            if location_type == consts.ART_LOCATION_MISC:
                self.misc_img_in_dir = filename
            elif location_type == consts.ART_LOCATION_SINGLE:
                self.single_img_in_dir = filename
            gobject.idle_add(self.artwork_set_image, filename)
            return True

        return False

    def artwork_get_local_image(self, songpath=None, artist=None, album=None):
        # Returns a tuple (location_type, filename) or (None, None).
        # Only pass a songpath, artist, and album if we don't want
        # to use info from the currently playing song.

        if songpath is None:
            songpath = os.path.dirname(mpdh.get(self.songinfo, 'file'))

        # Give precedence to images defined by the user's current
        # art_location config (in case they have multiple valid images
        # that can be used for cover art).
        testfile = self.target_image_filename(None, songpath, artist, album)
        if os.path.exists(testfile):
            return self.config.art_location, testfile

        # Now try all local possibilities...
        simplelocations = [consts.ART_LOCATION_HOMECOVERS,
                   consts.ART_LOCATION_COVER,
                   consts.ART_LOCATION_ALBUM,
                   consts.ART_LOCATION_FOLDER]
        for location in simplelocations:
            testfile = self.target_image_filename(location, songpath, artist, album)
            if os.path.exists(testfile):
                return location, testfile

        testfile = self.target_image_filename(consts.ART_LOCATION_CUSTOM, songpath, artist, album)
        if self.config.art_location == consts.ART_LOCATION_CUSTOM and len(self.config.art_location_custom_filename) > 0 and os.path.exists(testfile):
            return consts.ART_LOCATION_CUSTOM, testfile

        if self.artwork_get_misc_img_in_path(songpath):
            return consts.ART_LOCATION_MISC, self.artwork_get_misc_img_in_path(songpath)

        testfile = img.single_image_in_dir(self.config.musicdir[self.config.profile_num] + songpath)
        if testfile is not None:
            return consts.ART_LOCATION_SINGLE, testfile

        return None, None

    def artwork_check_for_remote(self, artist, album, filename):
        self.artwork_set_default_icon()
        self.artwork_download_img_to_file(artist, album, filename)
        if os.path.exists(filename):
            gobject.idle_add(self.artwork_set_image, filename)
            return True
        return False

    def artwork_set_default_icon(self):
        if self.albumimage.get_property('file') != self.sonatacd:
            gobject.idle_add(self.albumimage.set_from_file, self.sonatacd)
            gobject.idle_add(self.info_image.set_from_file, self.sonatacd_large)
            gobject.idle_add(self.fullscreen_cover_art_set_image, self.sonatacd_large)
        gobject.idle_add(self.artwork_set_tooltip_art, gtk.gdk.pixbuf_new_from_file(self.sonatacd))
        self.lastalbumart = None

    def artwork_get_misc_img_in_path(self, songdir):
        path = misc.file_from_utf8(self.config.musicdir[self.config.profile_num] + songdir)
        if os.path.exists(path):
            for name in consts.ART_LOCATIONS_MISC:
                filename = path + "/" + name
                if os.path.exists(filename):
                    return filename
        return False

    def artwork_set_image(self, filename, info_img_only=False):
        # Note: filename arrives here is in FILESYSTEM_CHARSET, not UTF-8!
        if self.artwork_is_for_playing_song(filename):
            if os.path.exists(filename):
                # We use try here because the file might exist, but might
                # still be downloading
                try:
                    pix = gtk.gdk.pixbuf_new_from_file(filename)
                    # Artwork for tooltip, left-top of player:
                    if not info_img_only:
                        (pix1, w, h) = img.get_pixbuf_of_size(pix, 75)
                        pix1 = self.artwork_apply_composite_case(pix1, w, h)
                        pix1 = img.pixbuf_add_border(pix1)
                        pix1 = img.pixbuf_pad(pix1, 77, 77)
                        self.albumimage.set_from_pixbuf(pix1)
                        self.artwork_set_tooltip_art(pix1)
                        del pix1
                    # Artwork for info tab:
                    if self.info_imagebox_get_size_request()[0] == -1:
                        fullwidth = self.notebook_get_allocation()[2] - 50
                        (pix2, w, h) = img.get_pixbuf_of_size(pix, fullwidth)
                    else:
                        (pix2, w, h) = img.get_pixbuf_of_size(pix, 150)
                    pix2 = self.artwork_apply_composite_case(pix2, w, h)
                    pix2 = img.pixbuf_add_border(pix2)
                    self.info_image.set_from_pixbuf(pix2)
                    del pix2
                    # Artwork for fullscreen cover mode
                    (pix3, w, h) = img.get_pixbuf_of_size(pix, consts.FULLSCREEN_COVER_SIZE)
                    pix3 = self.artwork_apply_composite_case(pix3, w, h)
                    pix3 = img.pixbuf_pad(pix3, consts.FULLSCREEN_COVER_SIZE, consts.FULLSCREEN_COVER_SIZE)
                    self.fullscreenalbumimage.set_from_pixbuf(pix3)
                    del pix, pix3
                    # Artwork for albums in the library tab
                    if not info_img_only:
                        self.library_browse_update()
                    self.lastalbumart = filename
                except:
                    # If we have a 0-byte file, it should mean that
                    # sonata reset the image file. Otherwise, it's a
                    # bad file and should be removed.
                    if os.stat(filename).st_size != 0:
                        misc.remove_file(filename)

                self.schedule_gc_collect()

    def artwork_set_image_last(self, info_img_only=False):
        self.artwork_set_image(self.lastalbumart, info_img_only)

    def artwork_apply_composite_case(self, pix, w, h):
        if self.config.covers_type == consts.COVERS_TYPE_STYLIZED and float(w)/h > 0.5:
            # Rather than merely compositing the case on top of the artwork, we will
            # scale the artwork so that it isn't covered by the case:
            spine_ratio = float(60)/600 # From original png
            spine_width = int(w * spine_ratio)
            case = self.casepb.scale_simple(w, h, gtk.gdk.INTERP_BILINEAR)
            # Scale pix and shift to the right on a transparent pixbuf:
            pix = pix.scale_simple(w-spine_width, h, gtk.gdk.INTERP_BILINEAR)
            blank = gtk.gdk.Pixbuf(gtk.gdk.COLORSPACE_RGB, True, 8, w, h)
            blank.fill(0x00000000)
            pix.copy_area(0, 0, pix.get_width(), pix.get_height(), blank, spine_width, 0)
            # Composite case and scaled pix:
            case.composite(blank, 0, 0, w, h, 0, 0, 1, 1, gtk.gdk.INTERP_BILINEAR, 250)
            del case
            return blank
        return pix

    def artwork_is_for_playing_song(self, filename):
        # Since there can be multiple threads that are getting album art,
        # this will ensure that only the artwork for the currently playing
        # song is displayed
        if self.status_is_play_or_pause() and self.songinfo:
            if self.songinfo.has_key('name'):
                streamfile = self.artwork_stream_filename(mpdh.get(self.songinfo, 'name'))
                if filename == streamfile:
                    return True
            else:
                # Normal song:
                if (filename in [self.target_image_filename(consts.ART_LOCATION_HOMECOVERS),
                         self.target_image_filename(consts.ART_LOCATION_COVER),
                         self.target_image_filename(consts.ART_LOCATION_ALBUM),
                         self.target_image_filename(consts.ART_LOCATION_FOLDER),
                         self.target_image_filename(consts.ART_LOCATION_CUSTOM)] or
                    (self.misc_img_in_dir and filename == self.misc_img_in_dir) or
                    (self.single_img_in_dir and filename == self.single_img_in_dir)):
                    return True
        # If we got this far, no match:
        return False

    def artwork_download_img_to_file(self, artist, album, dest_filename, all_images=False):
        # Returns False if no images found
        if not artist and not album:
            self.downloading_image = False
            return False
        self.downloading_image = True
        # Amazon currently doesn't support utf8 and suggests latin1 encoding instead:
        artist = urllib.quote(artist.encode('latin1', 'replace'))
        album = urllib.quote(album.encode('latin1', 'replace'))

        # Try searching urls from most specific (artist, title) to least specific (artist only)
        urls = [AMAZON_URI % (AMAZON_KEY, artist) + "&Title=" + album,
            AMAZON_URI % (AMAZON_KEY, artist) + "&Keywords=" + album,
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
                self.downloading_image = False
                return False

        imgs = iunique(url.text for img in largeimgs for url in img.getiterator(AMAZON_NS + "URL"))
        imglist = list(imgs)

        if not all_images:
            urllib.urlretrieve(imglist[0], dest_filename)
            self.downloading_image = False
            return True
        else:
            try:
                imgfound = False
                for i in range(len(imglist)):
                    dest_filename_curr = dest_filename.replace("<imagenum>", str(i+1))
                    urllib.urlretrieve(imglist[i], dest_filename_curr)
                    # This populates Main.imagelist for the remote image window
                    if os.path.exists(dest_filename_curr):
                        pix = gtk.gdk.pixbuf_new_from_file(dest_filename_curr)
                        pix = pix.scale_simple(148, 148, gtk.gdk.INTERP_HYPER)
                        pix = self.artwork_apply_composite_case(pix, 148, 148)
                        pix = img.pixbuf_add_border(pix)
                        if self.stop_art_update:
                            del pix
                            self.downloading_image = False
                            return imgfound
                        self.imagelist_append([i+1, pix])
                        del pix
                        imgfound = True
                        self.remotefilelist_append(dest_filename_curr)
                        if i == 0:
                            self.allow_art_search()
                    ui.change_cursor(None)
            except:
                pass
            self.downloading_image = False
            return imgfound

    def fullscreen_cover_art_set_image(self, filename):
        pix = gtk.gdk.pixbuf_new_from_file(filename)
        pix = img.pixbuf_pad(pix, consts.FULLSCREEN_COVER_SIZE, consts.FULLSCREEN_COVER_SIZE)
        self.fullscreenalbumimage.set_from_pixbuf(pix)

    def have_last(self):
        if self.lastalbumart is not None:
            return True
        return False
