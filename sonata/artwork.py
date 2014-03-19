import collections
import logging
import os
import re
import shutil
import threading # artwork_update starts a thread _artwork_update

from gi.repository import Gtk, Gdk, GdkPixbuf, GLib, GObject

from sonata import img, ui, misc, consts, mpdhelper as mpdh
from sonata.song import SongRecord
from sonata.pluginsystem import pluginsystem


COVERS_DIR = os.path.expanduser("~/.covers")
COVERS_TEMP_DIR = os.path.join(COVERS_DIR, 'temp')
logger = logging.getLogger(__name__)


class ArtworkLocator:
    """Find and return artwork paths requested for songs."""

    def __init__(self, config):
        self.config = config

    def _get_locations(self, artist, album, song_dir, default_kind=None):
        """Get the various possible locations for the artwork for one song."""

        artist = (artist or "").replace("/", "")
        album = (album or "").replace("/", "")
        song_dir = os.path.join(
            self.config.current_musicdir,
            get_multicd_album_root_dir(song_dir)
        )
        join = os.path.join
        custom_filename = self.config.art_location_custom_filename

        # Build a map of location kinds and actual locations. The order is
        # important and represents the most common/easiest to the least
        # common/more expensive ways of finding covers.
        # Each location is an iterable of possibly several locations.
        pre_map = [
            ('HOMECOVERS', (COVERS_DIR, "%s-%s.jpg" % (artist, album))),
            ('COVER',      (song_dir, "cover.jpg")),
            ('FOLDER',     (song_dir, "folder.jpg")),
            ('ALBUM',      (song_dir, "album.jpg")),
            ('CUSTOM',     ((song_dir, custom_filename)
                            if len(custom_filename) > 0
                            else []
                           )),
            ('MISC',       (join(song_dir, location)
                            for location in consts.ART_LOCATIONS_MISC)),
            ('SINGLE',     self._lookup_single_image(song_dir)),
        ]

        map = collections.OrderedDict()
        for (fake_key, value) in pre_map:
            key = getattr(consts, 'ART_LOCATION_%s' % fake_key)
            if isinstance(value, tuple):
                value = [join(*value)]
            map[key] = value

        # Move the default kind requested to the beginning of the map, so it has
        # priority over the other.
        if default_kind in map:
            map.move_to_end(default_kind, last=False)

        return map

    def _lookup_single_image(self, song_dir):
        """Look up a song directory to find one image to be the artwork.

        This basically loops over all the files in a song directory and returns
        something only if it found exactly one image. This will be the artwork
        image.
        """

        try:
            files = os.listdir(song_dir)
        except OSError:
            return None

        get_ext = lambda path: os.path.splitext(path)[1][1:]

        artworks = [f for f in files if get_ext(f) in img.VALID_EXTENSIONS]
        if len(artworks) != 1:
            return None

        yield os.path.join(song_dir, artworks[0])

    def path(self, artist, album, song_dir, specific_kind=None):
        """Return the artwork path from a song data (without checks)

        By default, the location of the song is made based on the preferences
        set by the user, but this can be overriden if necessary.
        No guarantees are made with the respect to the path validity.
        """

        locations_map = self._get_locations(artist, album, song_dir,
                                            self.config.art_location)

        if specific_kind is None:
            specific_kind = self.config.art_location

        try:
            result = next(iter(locations_map[specific_kind]))
        except StopIteration: # We tried an empty location :(
            result = None
        return result


    def path_from_song(self, song, specific_kind=None):
        """Same as `path()` but using a Song object."""
        return self.path(song.artist, song.album,
                         os.path.dirname(song.file), specific_kind)

    def locate(self, artist, album, song_dir):
        """Locate an actual artwork for the specified data.

        Sonata tries *very* hard to find an artwork for the specified data. It
        looks in "well-known" places and return the first artwork which actually
        exists.
        """

        # XXX: the 'kind' returned can probably be removed once the calling code
        # will be refactored. It is used only for some kind of thread
        # concurrency management, and is probably buggy and not optimal...

        locations_map = self._get_locations(artist, album, song_dir,
                                            self.config.art_location)

        for kind, locations in locations_map.items():
            for location in locations:
                if os.path.exists(location):
                    return (kind, location)

        return (None, None)


def get_multicd_album_root_dir(albumpath):
    """Go one dir upper for multicd albums

    >>> from sonata.artwork import get_multicd_album_root_dir as f
    >>> f('Moonspell/1995 - Wolfheart/cd 2')
    'Moonspell/1995 - Wolfheart'
    >>> f('2007 - Dark Passion Play/CD3')
    '2007 - Dark Passion Play'
    >>> f('Ayreon/2008 - 01011001/CD 1 - Y')
    'Ayreon/2008 - 01011001'

    """

    if re.compile(r'(?i)cd\s*\d+').match(os.path.split(albumpath)[1]):
        albumpath = os.path.split(albumpath)[0]
    return albumpath


def artwork_path(song, config):
    if song.name is not None:
        f = artwork_stream(song.name)
    else:
        f = ArtworkLocator(config).path_from_song(song)
    return f


def artwork_stream(stream_name):
    return os.path.join(os.path.expanduser('~/.covers'), "%s.jpg" %
                        stream_name.replace("/", ""))


class Artwork(GObject.GObject):

    __gsignals__ = {
        'artwork-changed': (GObject.SIGNAL_RUN_FIRST, None,
                            (GdkPixbuf.Pixbuf,)),
        'artwork-reset': (GObject.SIGNAL_RUN_FIRST, None, ()),
    }

    def __init__(self, config, is_lang_rtl, schedule_gc_collect,
                 imagelist_append, remotefilelist_append,
                 allow_art_search, status_is_play_or_pause,
                 album_image, tray_image):
        super().__init__()

        self.config = config
        self.locator = ArtworkLocator(config)
        self.album_filename = 'sonata-album'

        # constants from main
        self.is_lang_rtl = is_lang_rtl

        # callbacks to main XXX refactor to clear this list
        self.schedule_gc_collect = schedule_gc_collect
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

        self.cache = ArtworkCache(self.config)
        self.cache.load()

    def update_songinfo(self, songinfo):
        self.songinfo = songinfo

    def on_reset_image(self, _action):
        if self.songinfo:
            if 'name' in self.songinfo:
                # Stream, remove file:
                misc.remove_file(artwork_stream(self.songinfo.name))
            else:
                # Normal song:
                misc.remove_file(self.locator.path_from_song(self.songinfo))
                misc.remove_file(self.locator.path_from_song(
                    self.songinfo, consts.ART_LOCATION_HOMECOVERS))
                # Use blank cover as the artwork
                dest_filename = self.locator.path_from_song(
                    self.songinfo, consts.ART_LOCATION_HOMECOVERS)
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
        thread.name = "ArtworkLibraryUpdate"
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
            # Wait for items..
            self.lib_art_cond.acquire()
            while(len(self.lib_art_rows_local) == 0 and \
                  len(self.lib_art_rows_remote) == 0):
                self.lib_art_cond.wait()
            self.lib_art_cond.release()

            # Try first element, giving precedence to local queue:
            if self.lib_art_rows_local:
                i, data, icon = self.lib_art_rows_local.pop(0)
                cb = self._library_artwork_update_local
            elif self.lib_art_rows_remote:
                i, data, icon = self.lib_art_rows_remote.pop(0)
                cb = self._library_artwork_update_remote
            else:
                continue

            cache_key = SongRecord(artist=data.artist, album=data.album,
                                         path=data.path)
            # Try to replace default icons with cover art:
            pb = self.cache.get_pixbuf(cache_key, self.lib_art_pb_size)
            cb(i, data, icon, cache_key, pb)


    def _library_artwork_update_local(self, i, data, icon, cache_key, pb):
        filename = None

        if pb is not None:
            # Continue to rescan for local artwork if we are
            # displaying the default album image, in case the user
            # has added a local image since we first scanned.
            filename = self.cache.get(cache_key)
            if os.path.basename(filename) == os.path.basename(
                self.album_filename):
                filename = None
                pb = None

        # No cached pixbuf, try local/remote search:
        if pb is None:
            pb, filename = self.library_get_album_cover(
                data.path, data.artist, data.album, self.lib_art_pb_size)

        # Set pixbuf icon in model; add to cache
        if pb is not None and filename is not None:
            self.cache.set(cache_key, filename)
            GLib.idle_add(self.library_set_cover, i, pb, data)

        if pb is None and self.config.covers_pref == consts.ART_LOCAL_REMOTE:
            # No local art found, add to remote queue for later
            self.lib_art_rows_remote.append((i, data, icon))


    def _library_artwork_update_remote(self, i, data, icon, cache_key, pb):
        filename = None

        # No cached pixbuf, try local/remote search:
        if pb is None:
            pb, filename = self.library_get_album_cover(data.path,
                                                        data.artist,
                                                        data.album,
                                                        self.lib_art_pb_size)
            filename = self.locator.path(data.artist, data.album, data.path)
            self.artwork_download_img_to_file(data.artist, data.album,
                                              filename)

        # Set pixbuf icon in model; add to cache
        if pb is not None and filename is not None:
            self.cache.set(cache_key, filename)
            GLib.idle_add(self.library_set_cover, i, pb, data)

        if pb is None:
            # No remote art found, store self.albumpb filename in cache
            self.cache.set(cache_key, self.album_filename)


    def library_set_image_for_current_song(self, cache_key):
        # Search through the rows in the library to see
        # if we match the currently playing song:
        if cache_key.artist is None and cache_key.album is None:
            return
        for row in self.lib_model:
            if str(cache_key.artist).lower() == str(row[1].artist).lower() \
            and str(cache_key.album).lower() == str(row[1].album).lower():
                pb = self.cache.get_pixbuf(cache_key, self.lib_art_pb_size)
                if pb:
                    self.lib_model.set_value(row.iter, 0, pb)

    def library_set_cover(self, i, pb, data):
        if self.lib_model.iter_is_valid(i):
            if self.lib_model.get_value(i, 1) == data:
                self.lib_model.set_value(i, 0, pb)

    def library_get_album_cover(self, song_dir, artist, album, pb_size):
        _tmp, coverfile = self.locator.locate(artist, album, song_dir)
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
            coverpb = img.do_style_cover(self.config, coverpb, w, h)
            return (coverpb, coverfile)
        return (None, None)

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
            thread.name = "ArtworkUpdate"
            thread.daemon = True
            thread.start()
        else:
            self.artwork_set_default_icon()

    def _artwork_update(self):
        if 'name' in self.songinfo:
            # Stream
            streamfile = artwork_stream(self.songinfo.name)
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
            filename = self.locator.path_from_song(self.songinfo)
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

    def artwork_check_for_local(self, artist, album, path):
        self.artwork_set_default_icon(artist, album, path)
        self.misc_img_in_dir = None
        self.single_img_in_dir = None
        location_type, filename = self.locator.locate(
            self.songinfo.artist, self.songinfo.album,
            os.path.dirname(self.songinfo.file))

        if location_type is not None and filename:
            if location_type == consts.ART_LOCATION_MISC:
                self.misc_img_in_dir = filename
            elif location_type == consts.ART_LOCATION_SINGLE:
                self.single_img_in_dir = filename
            GLib.idle_add(self.artwork_set_image, filename, artist, album, path)
            return True

        return False

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
            cache_key = SongRecord(artist=artist, album=album, path=path)
            self.cache.set(cache_key, self.album_filename)
            GLib.idle_add(self.library_set_image_for_current_song, cache_key)

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
                    cache_key = SongRecord(artist=artist, album=album,
                                           path=path)
                    self.cache.set(cache_key, filename)

                    # Artwork for tooltip, left-top of player:
                    (pix1, w, h) = img.get_pixbuf_of_size(pix, 75)
                    pix1 = img.do_style_cover(self.config, pix1, w, h)
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

    def artwork_is_for_playing_song(self, filename):
        # Since there can be multiple threads that are getting album art,
        # this will ensure that only the artwork for the currently playing
        # song is displayed
        if self.status_is_play_or_pause() and self.songinfo:
            if 'name' in self.songinfo:
                streamfile = artwork_stream(self.songinfo.name)
                if filename == streamfile:
                    return True
            else:
                # Normal song:
                if (filename in [self.locator.path_from_song(self.songinfo, l)
                                 for l in [consts.ART_LOCATION_HOMECOVERS,
                                           consts.ART_LOCATION_COVER,
                                           consts.ART_LOCATION_ALBUM,
                                           consts.ART_LOCATION_FOLDER,
                                           consts.ART_LOCATION_CUSTOM]] or
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
            pix = img.do_style_cover(self.config, pix, 148, 148)
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


class ArtworkCache:
    def __init__(self, config, path=None):
        self.logger = logging.getLogger('sonata.artwork.cache')
        self._cache = {}
        self.config = config
        self.path = path if path is not None else \
                os.path.expanduser("~/.config/sonata/art_cache")

    def set(self, key, value):
        self.logger.debug("Setting %r to %r", key, value)
        self._cache[key] = value

    def get(self, key):
        self.logger.debug("Requesting for %r", key)
        return self._cache.get(key)

    def get_pixbuf(self, key, size, default=None):
        self.logger.debug("Requesting pixbuf for %r", key)
        try:
            path = self._cache[key]
        except KeyError:
            return default

        if not os.path.exists(path):
            self._cache.pop(key, None)
            return default

        try:
            p = GdkPixbuf.Pixbuf.new_from_file_at_size(path, size, size)
        except:
            self.logger.exception("Unable to load %r at size (%d, %d)",
                                  path, size, size)
            raise
        return img.do_style_cover(self.config, p, size, size)

    def save(self):
        self.logger.debug("Saving to %s", self.path)
        misc.create_dir(os.path.dirname(self.path))
        try:
            with open(self.path, 'w', encoding="utf8") as f:
                f.write(repr(self._cache))
        except IOError as e:
            self.logger.info("Unable to save: %s", e)

    def load(self):
        self.logger.debug("Loading from %s", self.path)
        self._cache = {}
        try:
            with open(self.path, 'r', encoding="utf8") as f:
                self._cache = eval(f.read())
        except (IOError, SyntaxError) as e:
            self.logger.info("Unable to load: %s", e)
