from __future__ import with_statement
import os
import threading # artwork_update starts a thread _artwork_update

import gtk
import gobject

import img
import ui
import misc
import mpdhelper as mpdh
import consts
from library import library_set_data
from library import library_get_data
from pluginsystem import pluginsystem


class Artwork(object):

    def __init__(self, config, path_to_icon, is_lang_rtl,
                 info_imagebox_get_size_request, schedule_gc_collect,
                 target_image_filename, imagelist_append,
                 remotefilelist_append, notebook_get_allocation,
                 allow_art_search, status_is_play_or_pause, album_filename,
                 get_current_song_text):

        self.config = config
        self.album_filename = album_filename

        # constants from main
        self.is_lang_rtl = is_lang_rtl

        # callbacks to main XXX refactor to clear this list
        self.info_imagebox_get_size_request = info_imagebox_get_size_request
        self.schedule_gc_collect = schedule_gc_collect
        self.target_image_filename = target_image_filename
        self.imagelist_append = imagelist_append
        self.remotefilelist_append = remotefilelist_append
        self.notebook_get_allocation = notebook_get_allocation
        self.allow_art_search = allow_art_search
        self.status_is_play_or_pause = status_is_play_or_pause
        self.get_current_song_text = get_current_song_text

        # local pixbufs, image file names
        self.sonatacd = path_to_icon('sonatacd.png')
        self.sonatacd_large = path_to_icon('sonatacd_large.png')
        path = path_to_icon('sonata-case.png')
        self.casepb = gtk.gdk.pixbuf_new_from_file(path)
        self.albumpb = None
        self.currentpb = None

        # local UI widgets provided to main by getter methods
        self.albumimage = ui.image()
        self.albumimage.set_from_file(self.sonatacd)

        self.trayalbumimage1 = ui.image(w=51, h=77, x=1)
        self.trayalbumeventbox = ui.eventbox(w=59, h=90,
                                             add=self.trayalbumimage1,
                                             state=gtk.STATE_SELECTED,
                                             visible=True)

        self.trayalbumimage2 = ui.image(w=26, h=77)

        self.fullscreenalbumimage = ui.image(w=consts.FULLSCREEN_COVER_SIZE,
                                             h=consts.FULLSCREEN_COVER_SIZE,
                                             x=1)
        self.fullscreenalbumlabel = ui.label(x=0.5)
        self.fullscreenalbumlabel2 = ui.label(x=0.5)
        self.fullscreen_cover_art_reset_image()
        self.fullscreen_cover_art_reset_text()

        self.info_image = ui.image(y=0)
        self.info_image.set_from_file(self.sonatacd_large)

        # local version of Main.songinfo mirrored by update_songinfo
        self.songinfo = None

        # local state
        self.lastalbumart = None
        self.single_img_in_dir = None
        self.misc_img_in_dir = None
        self.stop_art_update = False
        self.downloading_image = False
        self.lib_art_cond = None

        # local artwork, cache for library
        self.lib_model = None
        self.lib_art_rows_local = []
        self.lib_art_rows_remote = []
        self.lib_art_pb_size = 0
        self.cache = {}

        self.artwork_load_cache()

    def get_albumimage(self):
        return self.albumimage

    def get_info_image(self):
        return self.info_image

    def get_trayalbum(self):
        return self.trayalbumeventbox, self.trayalbumimage2

    def get_fullscreenalbumimage(self):
        return self.fullscreenalbumimage

    def get_fullscreenalbumlabels(self):
        return self.fullscreenalbumlabel, self.fullscreenalbumlabel2

    def update_songinfo(self, songinfo):
        self.songinfo = songinfo

    def on_reset_image(self, _action):
        if self.songinfo:
            if 'name' in self.songinfo:
                # Stream, remove file:
                misc.remove_file(self.artwork_stream_filename(
                    mpdh.get(self.songinfo, 'name')))
            else:
                # Normal song:
                misc.remove_file(self.target_image_filename())
                misc.remove_file(self.target_image_filename(
                    consts.ART_LOCATION_HOMECOVERS))
                # Use blank cover as the artwork
                dest_filename = self.target_image_filename(
                    consts.ART_LOCATION_HOMECOVERS)
                try:
                    emptyfile = open(dest_filename, 'w')
                    emptyfile.close()
                except IOError:
                    pass
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

    def artwork_stop_update(self):
        self.stop_art_update = True

    def artwork_is_downloading_image(self):
        return self.downloading_image

    def library_artwork_init(self, model, pb_size):

        self.lib_model = model
        self.lib_art_pb_size = pb_size

        self.lib_art_cond = threading.Condition()
        thread = threading.Thread(target=self._library_artwork_update)
        thread.setDaemon(True)
        thread.start()

    def library_artwork_update(self, model, start_row, end_row, albumpb):
        self.albumpb = albumpb

        # Update self.lib_art_rows_local with new rows followed
        # by the rest of the rows.
        self.lib_art_cond.acquire()
        self.lib_art_rows_local = []
        self.lib_art_rows_remote = []
        test_rows = range(start_row, end_row + 1) + range(len(model))
        for row in test_rows:
            i = model.get_iter((row,))
            icon = model.get_value(i, 0)
            if icon == self.albumpb:
                data = model.get_value(i, 1)
                self.lib_art_rows_local.append((i, data, icon))
        self.lib_art_cond.notifyAll()
        self.lib_art_cond.release()

    def _library_artwork_update(self):

        while True:
            remote_art = False

            # Wait for items..
            self.lib_art_cond.acquire()
            while(len(self.lib_art_rows_local) == 0 and \
                  len(self.lib_art_rows_remote) == 0):
                self.lib_art_cond.wait()
            self.lib_art_cond.release()

            # Try first element, giving precedence to local queue:
            if len(self.lib_art_rows_local) > 0:
                i, data, icon = self.lib_art_rows_local[0]
                remote_art = False
            elif len(self.lib_art_rows_remote) > 0:
                i, data, icon = self.lib_art_rows_remote[0]
                remote_art = True
            else:
                i = None

            if i is not None and self.lib_model.iter_is_valid(i):

                artist, album, path = library_get_data(data, 'artist',
                                                       'album', 'path')

                if artist is None or album is None:
                    if remote_art:
                        self.lib_art_rows_remote.pop(0)
                    else:
                        self.lib_art_rows_local.pop(0)

                cache_key = library_set_data(artist=artist, album=album,
                                             path=path)

                # Try to replace default icons with cover art:
                pb = self.get_library_artwork_cached_pb(cache_key, None)

                if pb is not None and not remote_art:
                    # Continue to rescan for local artwork if we are
                    # displaying the default album image, in case the user
                    # has added a local image since we first scanned.
                    filename = self.get_library_artwork_cached_filename(
                        cache_key)
                    if os.path.basename(filename) == os.path.basename(
                        self.album_filename):
                        pb = None

                filename = None

                # No cached pixbuf, try local/remote search:
                if pb is None:
                    if not remote_art:
                        pb, filename = self.library_get_album_cover(path,
                                                        artist, album,
                                                        self.lib_art_pb_size)
                    else:
                        filename = self.target_image_filename(None, path,
                                                              artist, album)
                        self.artwork_download_img_to_file(artist, album,
                                                          filename)
                        pb, filename = self.library_get_album_cover(path,
                                                            artist, album,
                                                        self.lib_art_pb_size)

                # Set pixbuf icon in model; add to cache
                if pb is not None:
                    if filename is not None:
                        self.set_library_artwork_cached_filename(cache_key,
                                                                 filename)
                    gobject.idle_add(self.library_set_cover, i, pb, data)

                # Remote processed item from queue:
                if not remote_art:
                    if len(self.lib_art_rows_local) > 0 and \
                       (i, data, icon) == self.lib_art_rows_local[0]:
                        self.lib_art_rows_local.pop(0)
                        if pb is None and self.config.covers_pref == \
                           consts.ART_LOCAL_REMOTE:
                            # No local art found, add to remote queue for later
                            self.lib_art_rows_remote.append((i, data, icon))
                else:
                    if len(self.lib_art_rows_remote) > 0 and \
                       (i, data, icon) == self.lib_art_rows_remote[0]:
                        self.lib_art_rows_remote.pop(0)
                        if pb is None:
                            # No remote art found, store self.albumpb
                            # filename in cache
                            self.set_library_artwork_cached_filename(cache_key,
                                                        self.album_filename)

    def library_set_image_for_current_song(self, cache_key):
        # Search through the rows in the library to see
        # if we match the currently playing song:
        play_artist, play_album = library_get_data(cache_key, 'artist',
                                                   'album')
        if play_artist is None and play_album is None:
            return
        for row in self.lib_model:
            artist, album, path = library_get_data(row[1], 'artist', 'album',
                                                   'path')
            if unicode(play_artist).lower() == unicode(artist).lower() \
            and unicode(play_album).lower() == unicode(album).lower():
                pb = self.get_library_artwork_cached_pb(cache_key, None)
                self.lib_model.set_value(row.iter, 0, pb)

    def library_set_cover(self, i, pb, data):
        if self.lib_model.iter_is_valid(i):
            if self.lib_model.get_value(i, 1) == data:
                self.lib_model.set_value(i, 0, pb)

    def library_get_album_cover(self, dirname, artist, album, pb_size):
        _tmp, coverfile = self.artwork_get_local_image(dirname, artist, album)
        if coverfile:
            try:
                coverpb = gtk.gdk.pixbuf_new_from_file_at_size(coverfile,
                                                            pb_size, pb_size)
            except:
                # Delete bad image:
                misc.remove_file(coverfile)
                return (None, None)
            w = coverpb.get_width()
            h = coverpb.get_height()
            coverpb = self.artwork_apply_composite_case(coverpb, w, h)
            return (coverpb, coverfile)
        return (None, None)

    def set_library_artwork_cached_filename(self, cache_key, filename):
        self.cache[cache_key] = filename

    def get_library_artwork_cached_filename(self, cache_key):
        try:
            return self.cache[cache_key]
        except:
            return None

    def get_library_artwork_cached_pb(self, cache_key, origpb):
        filename = self.get_library_artwork_cached_filename(cache_key)
        if filename is not None:
            if os.path.exists(filename):
                pb = gtk.gdk.pixbuf_new_from_file_at_size(filename,
                                                          self.lib_art_pb_size,
                                                          self.lib_art_pb_size)
                return self.artwork_apply_composite_case(pb,
                                                         self.lib_art_pb_size,
                                                         self.lib_art_pb_size)
            else:
                self.cache.pop(cache_key)
                return origpb
        else:
            return origpb

    def artwork_save_cache(self):
        misc.create_dir('~/.config/sonata/')
        filename = os.path.expanduser("~/.config/sonata/art_cache")
        try:
            with open(filename, 'w') as f:
                f.write(repr(self.cache))
        except IOError:
            pass

    def artwork_load_cache(self):
        filename = os.path.expanduser("~/.config/sonata/art_cache")
        if os.path.exists(filename):
            try:
                with open(filename, 'r') as f:
                        self.cache = eval(f.read())
            except (IOError, SyntaxError):
                self.cache = {}
        else:
            self.cache = {}

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

        self.fullscreen_cover_art_set_text()

    def _artwork_update(self):
        if 'name' in self.songinfo:
            # Stream
            streamfile = self.artwork_stream_filename(mpdh.get(self.songinfo,
                                                               'name'))
            if os.path.exists(streamfile):
                gobject.idle_add(self.artwork_set_image, streamfile, None,
                                 None, None)
            else:
                self.artwork_set_default_icon()
        else:
            # Normal song:
            artist = mpdh.get(self.songinfo, 'artist', "")
            album = mpdh.get(self.songinfo, 'album', "")
            path = os.path.dirname(mpdh.get(self.songinfo, 'file'))
            if len(artist) == 0 and len(album) == 0:
                self.artwork_set_default_icon(artist, album, path)
                return
            filename = self.target_image_filename()
            if filename == self.lastalbumart:
                # No need to update..
                self.stop_art_update = False
                return
            self.lastalbumart = None
            imgfound = self.artwork_check_for_local(artist, album, path)
            if not imgfound:
                if self.config.covers_pref == consts.ART_LOCAL_REMOTE:
                    imgfound = self.artwork_check_for_remote(artist, album,
                                                             path, filename)

    def artwork_stream_filename(self, streamname):
        return os.path.join(os.path.expanduser('~/.covers'),
                "%s.jpg" % streamname.replace("/", ""))

    def artwork_check_for_local(self, artist, album, path):
        self.artwork_set_default_icon(artist, album, path)
        self.misc_img_in_dir = None
        self.single_img_in_dir = None
        location_type, filename = self.artwork_get_local_image()

        if location_type is not None and filename:
            if location_type == consts.ART_LOCATION_MISC:
                self.misc_img_in_dir = filename
            elif location_type == consts.ART_LOCATION_SINGLE:
                self.single_img_in_dir = filename
            gobject.idle_add(self.artwork_set_image, filename, artist, album,
                             path)
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
            testfile = self.target_image_filename(location, songpath, artist,
                                                  album)
            if os.path.exists(testfile):
                return location, testfile

        testfile = self.target_image_filename(consts.ART_LOCATION_CUSTOM,
                                              songpath, artist, album)
        if self.config.art_location == consts.ART_LOCATION_CUSTOM and \
           len(self.config.art_location_custom_filename) > 0 and \
           os.path.exists(testfile):
            return consts.ART_LOCATION_CUSTOM, testfile

        if self.artwork_get_misc_img_in_path(songpath):
            return consts.ART_LOCATION_MISC, \
                    self.artwork_get_misc_img_in_path(songpath)

        path = os.path.join(self.config.musicdir[self.config.profile_num],
                            songpath)
        testfile = img.single_image_in_dir(path)
        if testfile is not None:
            return consts.ART_LOCATION_SINGLE, testfile

        return None, None

    def artwork_check_for_remote(self, artist, album, path, filename):
        self.artwork_set_default_icon(artist, album, path)
        self.artwork_download_img_to_file(artist, album, filename)
        if os.path.exists(filename):
            gobject.idle_add(self.artwork_set_image, filename, artist, album,
                             path)
            return True
        return False

    def artwork_set_default_icon(self, artist=None, album=None, path=None):
        if self.albumimage.get_property('file') != self.sonatacd:
            gobject.idle_add(self.albumimage.set_from_file, self.sonatacd)
            gobject.idle_add(self.info_image.set_from_file,
                             self.sonatacd_large)
            gobject.idle_add(self.fullscreen_cover_art_reset_image)
        gobject.idle_add(self.artwork_set_tooltip_art,
                         gtk.gdk.pixbuf_new_from_file(self.sonatacd))
        self.lastalbumart = None

        # Also, update row in library:
        if artist is not None:
            cache_key = library_set_data(artist=artist, album=album, path=path)
            self.set_library_artwork_cached_filename(cache_key,
                                                     self.album_filename)
            gobject.idle_add(self.library_set_image_for_current_song,
                             cache_key)

    def artwork_get_misc_img_in_path(self, songdir):
        path = os.path.join(self.config.musicdir[self.config.profile_num],
                            songdir)
        dir = misc.file_from_utf8(path)
        if os.path.exists(dir):
            for name in consts.ART_LOCATIONS_MISC:
                filename = os.path.join(dir, name)
                if os.path.exists(filename):
                    return filename
        return False

    def artwork_set_image(self, filename, artist, album, path,
                          info_img_only=False):
        # Note: filename arrives here is in FILESYSTEM_CHARSET, not UTF-8!
        if self.artwork_is_for_playing_song(filename):
            if os.path.exists(filename):

                # We use try here because the file might exist, but might
                # still be downloading or corrupt:
                try:
                    pix = gtk.gdk.pixbuf_new_from_file(filename)
                except:
                    # If we have a 0-byte file, it should mean that
                    # sonata reset the image file. Otherwise, it's a
                    # bad file and should be removed.
                    if os.stat(filename).st_size != 0:
                        misc.remove_file(filename)
                    return

                self.currentpb = pix

                if not info_img_only:
                    # Store in cache
                    cache_key = library_set_data(artist=artist, album=album,
                                                 path=path)
                    self.set_library_artwork_cached_filename(cache_key,
                                                             filename)

                    # Artwork for tooltip, left-top of player:
                    (pix1, w, h) = img.get_pixbuf_of_size(pix, 75)
                    pix1 = self.artwork_apply_composite_case(pix1, w, h)
                    pix1 = img.pixbuf_add_border(pix1)
                    pix1 = img.pixbuf_pad(pix1, 77, 77)
                    self.albumimage.set_from_pixbuf(pix1)
                    self.artwork_set_tooltip_art(pix1)
                    del pix1

                    # Artwork for library, if current song matches:
                    self.library_set_image_for_current_song(cache_key)

                    # Artwork for fullscreen
                    self.fullscreen_cover_art_set_image()

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
                del pix

                self.lastalbumart = filename

                self.schedule_gc_collect()

    def artwork_set_image_last(self):
        self.artwork_set_image(self.lastalbumart, None, None, None, True)

    def artwork_apply_composite_case(self, pix, w, h):
        if self.config.covers_type == consts.COVERS_TYPE_STYLIZED and \
           float(w) / h > 0.5:
            # Rather than merely compositing the case on top of the artwork,
            # we will scale the artwork so that it isn't covered by the case:
            spine_ratio = float(60) / 600 # From original png
            spine_width = int(w * spine_ratio)
            case = self.casepb.scale_simple(w, h, gtk.gdk.INTERP_BILINEAR)
            # Scale pix and shift to the right on a transparent pixbuf:
            pix = pix.scale_simple(w - spine_width, h, gtk.gdk.INTERP_BILINEAR)
            blank = gtk.gdk.Pixbuf(gtk.gdk.COLORSPACE_RGB, True, 8, w, h)
            blank.fill(0x00000000)
            pix.copy_area(0, 0, pix.get_width(), pix.get_height(), blank,
                          spine_width, 0)
            # Composite case and scaled pix:
            case.composite(blank, 0, 0, w, h, 0, 0, 1, 1,
                           gtk.gdk.INTERP_BILINEAR, 250)
            del case
            return blank
        return pix

    def artwork_is_for_playing_song(self, filename):
        # Since there can be multiple threads that are getting album art,
        # this will ensure that only the artwork for the currently playing
        # song is displayed
        if self.status_is_play_or_pause() and self.songinfo:
            if 'name' in self.songinfo:
                value = mpdh.get(self.songinfo, 'name')
                streamfile = self.artwork_stream_filename(value)
                if filename == streamfile:
                    return True
            else:
                # Normal song:
                if (filename in \
                   [self.target_image_filename(consts.ART_LOCATION_HOMECOVERS),
                     self.target_image_filename(consts.ART_LOCATION_COVER),
                     self.target_image_filename(consts.ART_LOCATION_ALBUM),
                     self.target_image_filename(consts.ART_LOCATION_FOLDER),
                     self.target_image_filename(consts.ART_LOCATION_CUSTOM)] or
                    (self.misc_img_in_dir and \
                     filename == self.misc_img_in_dir) or
                    (self.single_img_in_dir and filename == \
                     self.single_img_in_dir)):
                    return True
        # If we got this far, no match:
        return False

    def artwork_download_img_to_file(self, artist, album, dest_filename,
                                     all_images=False):
        self.downloading_image = True
        # Fetch covers from rhapsody.com etc.
        cover_fetchers = pluginsystem.get('cover_fetching')
        imgfound = False
        for _plugin, cb in cover_fetchers:
            ret = cb(self.download_progress, artist, album, dest_filename,
                     all_images)
            if ret:
                imgfound = True
                break # XXX if all_images, merge results...

        self.downloading_image = False
        return imgfound

    def download_progress(self, dest_filename_curr, i):
        # This populates Main.imagelist for the remote image window
        if os.path.exists(dest_filename_curr):
            pix = gtk.gdk.pixbuf_new_from_file(dest_filename_curr)
            pix = pix.scale_simple(148, 148, gtk.gdk.INTERP_HYPER)
            pix = self.artwork_apply_composite_case(pix, 148, 148)
            pix = img.pixbuf_add_border(pix)
            if self.stop_art_update:
                del pix
                return False # don't continue to next image
            self.imagelist_append([i + 1, pix])
            del pix
            self.remotefilelist_append(dest_filename_curr)
            if i == 0:
                self.allow_art_search()

        ui.change_cursor(None) # XXX indented twice more?

        return True # continue to next image

    def fullscreen_cover_art_set_image(self, force_update=False):
        if self.fullscreenalbumimage.get_property('visible') or force_update:
            if self.currentpb is None:
                self.fullscreen_cover_art_reset_image()
            else:
                # Artwork for fullscreen cover mode
                (pix3, w, h) = img.get_pixbuf_of_size(self.currentpb,
                                                  consts.FULLSCREEN_COVER_SIZE)
                pix3 = self.artwork_apply_composite_case(pix3, w, h)
                pix3 = img.pixbuf_pad(pix3, consts.FULLSCREEN_COVER_SIZE,
                                      consts.FULLSCREEN_COVER_SIZE)
                self.fullscreenalbumimage.set_from_pixbuf(pix3)
                del pix3
        self.fullscreen_cover_art_set_text()

    def fullscreen_cover_art_reset_image(self):
        pix = gtk.gdk.pixbuf_new_from_file(self.sonatacd_large)
        pix = img.pixbuf_pad(pix, consts.FULLSCREEN_COVER_SIZE,
                             consts.FULLSCREEN_COVER_SIZE)
        self.fullscreenalbumimage.set_from_pixbuf(pix)
        self.currentpb = None

    def fullscreen_cover_art_set_text(self):
        if self.status_is_play_or_pause():
            line1, line2 = self.get_current_song_text()
            self.fullscreenalbumlabel.set_markup(('<span size=\'20000\' '
                                                  'color=\'white\'>%s</span>')
                                                 % (misc.escape_html(line1)))
            self.fullscreenalbumlabel2.set_markup(('<span size=\'12000\' '
                                                   'color=\'white\'>%s</span>')
                                                  % (misc.escape_html(line2)))
        else:
            self.fullscreen_cover_art_reset_text()

    def fullscreen_cover_art_reset_text(self):
        self.fullscreenalbumlabel.set_markup(('<span size=\'20000\' '
                                              'color=\'white\'> </span>'))
        self.fullscreenalbumlabel2.set_markup(('<span size=\'12000\' '
                                               'color=\'white\'> </span>'))

    def have_last(self):
        if self.lastalbumart is not None:
            return True
        return False
