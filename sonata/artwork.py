import logging
import os
import shutil
import threading # artwork_update starts a thread _artwork_update

from gi.repository import Gtk, Gdk, GdkPixbuf, GLib, GObject

from sonata import img, ui, misc, consts, mpdhelper as mpdh
from sonata import library
from sonata.pluginsystem import pluginsystem


logger = logging.getLogger(__name__)


class Artwork(GObject.GObject):

    __gsignals__ = {
        'artwork-changed': (GObject.SIGNAL_RUN_FIRST, None,
                            (GdkPixbuf.Pixbuf,)),
        'artwork-reset': (GObject.SIGNAL_RUN_FIRST, None, ()),
    }

    def __init__(self, config, is_lang_rtl, schedule_gc_collect,
                 target_image_filename, imagelist_append, remotefilelist_append,
                 allow_art_search, status_is_play_or_pause,
                 album_image, tray_image):
        super().__init__()

        self.config = config
        self.album_filename = 'sonata-album'

        # constants from main
        self.is_lang_rtl = is_lang_rtl

        # callbacks to main XXX refactor to clear this list
        self.schedule_gc_collect = schedule_gc_collect
        self.target_image_filename = target_image_filename
        self.imagelist_append = imagelist_append
        self.remotefilelist_append = remotefilelist_append
        self.allow_art_search = allow_art_search
        self.status_is_play_or_pause = status_is_play_or_pause

        # local pixbufs, image file names
        self.sonatacd = Gtk.IconFactory.lookup_default('sonata-cd')
        self.sonatacd_large = Gtk.IconFactory.lookup_default('sonata-cd-large')
        self.albumpb = None
        self.currentpb = None

        # local UI widgets provided to main by getter methods
        self.albumimage = album_image
        self.albumimage.set_from_icon_set(self.sonatacd, -1)

        self.tray_album_image = tray_image

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

    def update_songinfo(self, songinfo):
        self.songinfo = songinfo

    def on_reset_image(self, _action):
        if self.songinfo:
            if 'name' in self.songinfo:
                # Stream, remove file:
                misc.remove_file(self.artwork_stream_filename(
                    self.songinfo.name))
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
        pix = pix.new_subpixbuf(0, 0, 77, 77)
        self.tray_album_image.set_from_pixbuf(pix)
        del pix

    def artwork_stop_update(self):
        self.stop_art_update = True

    def artwork_is_downloading_image(self):
        return self.downloading_image

    def library_artwork_init(self, model, pb_size):

        self.lib_model = model
        self.lib_art_pb_size = pb_size

        self.lib_art_cond = threading.Condition()
        thread = threading.Thread(target=self._library_artwork_update)
        thread.daemon = True
        thread.start()

    def library_artwork_update(self, model, start_row, end_row, albumpb):
        self.albumpb = albumpb

        # Update self.lib_art_rows_local with new rows followed
        # by the rest of the rows.
        self.lib_art_cond.acquire()
        self.lib_art_rows_local = []
        self.lib_art_rows_remote = []
        start = start_row.get_indices()[0]
        end = end_row.get_indices()[0]
        test_rows = list(range(start, end + 1)) + list(range(len(model)))
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

            # FIXME this can segfault (on iter_is_valid)
            if i is not None and self.lib_model.iter_is_valid(i):

                if data.artist is None or data.album is None:
                    if remote_art:
                        self.lib_art_rows_remote.pop(0)
                    else:
                        self.lib_art_rows_local.pop(0)

                cache_key = library.SongRecord(artist=data.artist,
                                               album=data.album,
                                               path=data.path)

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
                        pb, filename = self.library_get_album_cover(data.path,
                                                        data.artist, data.album,
                                                        self.lib_art_pb_size)
                    else:
                        filename = self.target_image_filename(None, data.path,
                                                              data.artist, data.album)
                        self.artwork_download_img_to_file(data.artist, data.album,
                                                          filename)
                        pb, filename = self.library_get_album_cover(data.path,
                                                            data.artist, data.album,
                                                        self.lib_art_pb_size)

                # Set pixbuf icon in model; add to cache
                if pb is not None:
                    if filename is not None:
                        self.set_library_artwork_cached_filename(cache_key,
                                                                 filename)
                        GLib.idle_add(self.library_set_cover, i, pb, data)

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
        if cache_key.artist is None and cache_key.album is None:
            return
        for row in self.lib_model:
            if str(cache_key.artist).lower() == str(row[1].artist).lower() \
            and str(cache_key.album).lower() == str(row[1].album).lower():
                pb = self.get_library_artwork_cached_pb(cache_key, None)
                if pb:
                    self.lib_model.set_value(row.iter, 0, pb)

    def library_set_cover(self, i, pb, data):
        if self.lib_model.iter_is_valid(i):
            if self.lib_model.get_value(i, 1) == data:
                self.lib_model.set_value(i, 0, pb)

    def library_get_album_cover(self, dirname, artist, album, pb_size):
        _tmp, coverfile = self.artwork_get_local_image(dirname, artist, album)
        if coverfile:
            try:
                coverpb = GdkPixbuf.Pixbuf.new_from_file_at_size(coverfile,
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
                pb = GdkPixbuf.Pixbuf.new_from_file_at_size(filename,
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
            with open(filename, 'w', encoding="utf8") as f:
                f.write(repr(self.cache))
        except IOError:
            pass

    def artwork_load_cache(self):
        filename = os.path.expanduser("~/.config/sonata/art_cache")
        if os.path.exists(filename):
            try:
                with open(filename, 'r', encoding="utf8") as f:
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
            thread.daemon = True
            thread.start()
        else:
            self.artwork_set_default_icon()

    def _artwork_update(self):
        if 'name' in self.songinfo:
            # Stream
            streamfile = self.artwork_stream_filename(self.songinfo.name)
            if os.path.exists(streamfile):
                GLib.idle_add(self.artwork_set_image, streamfile, None, None,
                              None)
            else:
                self.artwork_set_default_icon()
        else:
            # Normal song:
            artist = self.songinfo.artist or ""
            album = self.songinfo.album or ""
            path = os.path.dirname(self.songinfo.file)
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
            GLib.idle_add(self.artwork_set_image, filename, artist, album, path)
            return True

        return False

    def artwork_get_local_image(self, songpath=None, artist=None, album=None):
        # Returns a tuple (location_type, filename) or (None, None).
        # Only pass a songpath, artist, and album if we don't want
        # to use info from the currently playing song.

        if songpath is None:
            songpath = os.path.dirname(self.songinfo.file)

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
            GLib.idle_add(self.artwork_set_image, filename, artist, album, path)
            return True
        return False

    def artwork_set_default_icon(self, artist=None, album=None, path=None):
        GLib.idle_add(self.albumimage.set_from_icon_set,
                      self.sonatacd, -1)
        self.emit('artwork-reset')
        GLib.idle_add(self.tray_album_image.set_from_icon_set,
                      self.sonatacd, -1)

        self.lastalbumart = None

        # Also, update row in library:
        if artist is not None:
            cache_key = library.SongRecord(artist=artist, album=album, path=path)
            self.set_library_artwork_cached_filename(cache_key,
                                                     self.album_filename)
            GLib.idle_add(self.library_set_image_for_current_song, cache_key)

    def artwork_get_misc_img_in_path(self, songdir):
        path = os.path.join(self.config.musicdir[self.config.profile_num],
                            songdir)
        if os.path.exists(path):
            for name in consts.ART_LOCATIONS_MISC:
                filename = os.path.join(path, name)
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
                    pix = GdkPixbuf.Pixbuf.new_from_file(filename)
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
                    cache_key = library.SongRecord(artist=artist, album=album,
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

                self.emit('artwork-changed', pix)
                del pix

                self.lastalbumart = filename

                self.schedule_gc_collect()

    def artwork_set_image_last(self):
        self.artwork_set_image(self.lastalbumart, None, None, None, True)

    def artwork_apply_composite_case(self, pix, w, h):
        if not pix:
            return None
        if self.config.covers_type == consts.COVERS_TYPE_STYLIZED and \
           float(w) / h > 0.5:
            # Rather than merely compositing the case on top of the artwork,
            # we will scale the artwork so that it isn't covered by the case:
            spine_ratio = float(60) / 600 # From original png
            spine_width = int(w * spine_ratio)
            case_icon = Gtk.IconFactory.lookup_default('sonata-case')

            # We use the fullscreenalbumimage because it's the biggest we have
            context = self.fullscreenalbumimage.get_style_context()
            case_pb = case_icon.render_icon_pixbuf(context, -1)
            case = case_pb.scale_simple(w, h, GdkPixbuf.InterpType.BILINEAR)
            # Scale pix and shift to the right on a transparent pixbuf:
            pix = pix.scale_simple(w - spine_width, h, GdkPixbuf.InterpType.BILINEAR)
            blank = GdkPixbuf.Pixbuf.new(GdkPixbuf.Colorspace.RGB, True, 8, w, h)
            blank.fill(0x00000000)
            pix.copy_area(0, 0, pix.get_width(), pix.get_height(), blank,
                          spine_width, 0)
            # Composite case and scaled pix:
            case.composite(blank, 0, 0, w, h, 0, 0, 1, 1,
                           GdkPixbuf.InterpType.BILINEAR, 250)
            del case
            del case_pb
            return blank
        return pix

    def artwork_is_for_playing_song(self, filename):
        # Since there can be multiple threads that are getting album art,
        # this will ensure that only the artwork for the currently playing
        # song is displayed
        if self.status_is_play_or_pause() and self.songinfo:
            if 'name' in self.songinfo:
                streamfile = self.artwork_stream_filename(self.songinfo.name)
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

        downloader = CoverDownloader(dest_filename, self.download_progress,
                                     all_images)

        self.downloading_image = True
        # Fetch covers from covers websites or such...
        cover_fetchers = pluginsystem.get('cover_fetching')
        for plugin, callback in cover_fetchers:
            logger.info("Looking for covers for %r from %r (using %s)",
                        album, artist, plugin.name)

            try:
                callback(artist, album,
                         downloader.on_save_callback, downloader.on_err_cb)
            except Exception as e:
                if logger.isEnabledFor(logging.DEBUG):
                    log = logger.exception
                else:
                    log = logger.warning

                log("Error while downloading covers from %s: %s",
                    plugin.name, e)

            if downloader.found_images:
                break

        self.downloading_image = False
        return downloader.found_images

    def download_progress(self, dest_filename_curr, i):
        # This populates Main.imagelist for the remote image window
        if os.path.exists(dest_filename_curr):
            pix = GdkPixbuf.Pixbuf.new_from_file(dest_filename_curr)
            pix = pix.scale_simple(148, 148, GdkPixbuf.InterpType.HYPER)
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

            ui.change_cursor(None)

        return True # continue to next image

    def have_last(self):
        if self.lastalbumart is not None:
            return True
        return False


class CoverDownloader:
    """Download covers and store them in temporary files"""

    def __init__(self, path, progress_cb, all_images):
        self.path = path
        self.progress_cb = progress_cb
        self.max_images = 50 if all_images else 1
        self.current = 0

    @property
    def found_images(self):
        return self.current != 0

    def on_save_callback(self, content_fp):
        """Return True to continue finding covers, False to stop finding
        covers."""

        self.current += 1
        if self.max_images > 1:
            path = self.path.replace("<imagenum>", str(self.current))
        else:
            path = self.path

        with open(path, 'wb') as fp:
            shutil.copyfileobj(content_fp, fp)

        if self.max_images > 1:
            # XXX: progress_cb makes sense only if we are downloading several
            # images, since it is supposed to update the choose artwork
            # dialog...
            return self.progress_cb(path, self.current-1)

    def on_err_cb(self, reason=None):
        """Return True to stop finding, False to continue finding covers."""
        return False
