from os.path import expanduser
import unittest

try:
    from unittest.mock import Mock, patch, call
except ImportError: # pragma: nocover
    from mock import Mock, patch, call

import os
import shutil
import tempfile

from sonata.artwork import artwork_path
from sonata.artwork import ArtworkLocator
from sonata import consts


class _MixinTestDirectory:
    def mkdir(self, *paths):
        path = os.path.join(self.music_dir, *paths)
        os.makedirs(path, exist_ok=True)
        return path

    def touch(self, *paths):
        path = os.path.join(self.music_dir, *paths)
        with open(path, 'wb') as fp:
            pass
        return path

    def assertDirEqual(self, expected, got):
        expected = expected.replace('/TMP', self.music_dir)
        self.assertEqual(expected, got)

    def setUp(self):
        super().setUp()
        self.music_dir = tempfile.mkdtemp(prefix="sonata-tests-")
        self.config = Mock('Config', current_musicdir=self.music_dir)

    def tearDown(self):
        super().tearDown()
        shutil.rmtree(self.music_dir)


class TestArtworkPathFinder(unittest.TestCase):
    def setUp(self):
        self.config = Mock('Config',
                           current_musicdir="/foo",
                           art_location=1,
                           art_location_custom_filename="bla")
        self.locator = ArtworkLocator(self.config)

    # artwork_path_from_data
    def _call_artwork_path_from_data(self,  location_type=None,
                                     artist="Toto",
                                     album="Tata",
                                     song_dir="To/Ta"):

        return self.locator.path(artist, album, song_dir, location_type)

    def test_find_path_from_data_in_home_covers(self):
        self.config.art_location = consts.ART_LOCATION_HOMECOVERS

        res = self._call_artwork_path_from_data()
        self.assertEqual(expanduser('~/.covers/Toto-Tata.jpg'), res)

    def test_find_path_from_data_as_cover_dot_jpg(self):
        self.config.art_location = consts.ART_LOCATION_COVER

        res = self._call_artwork_path_from_data()
        self.assertEqual('/foo/To/Ta/cover.jpg', res)

    def test_find_path_from_data_as_folder_dot_jpg(self):
        self.config.art_location = consts.ART_LOCATION_FOLDER

        res = self._call_artwork_path_from_data()
        self.assertEqual('/foo/To/Ta/folder.jpg', res)

    def test_find_path_from_data_as_album_dot_jpg(self):
        self.config.art_location = consts.ART_LOCATION_ALBUM

        res = self._call_artwork_path_from_data()
        self.assertEqual('/foo/To/Ta/album.jpg', res)

    def test_find_path_from_data_as_custom_dot_jpg(self):
        self.config.art_location_custom_filename = "bar.png"
        self.config.art_location = consts.ART_LOCATION_CUSTOM

        res = self._call_artwork_path_from_data()
        self.assertEqual('/foo/To/Ta/bar.png', res)

    def test_find_path_from_data_force_location_type(self):
        self.config.art_location = "foo bar" # Should not be used

        res = self._call_artwork_path_from_data(consts.ART_LOCATION_COVER)
        self.assertEqual('/foo/To/Ta/cover.jpg', res)

    # artwork_path_from_song
    def test_find_path_from_song(self):
        self.config.art_location = consts.ART_LOCATION_COVER
        song = Mock('Song', artist='', album='', file='Foo/Bar/1.ogg')
        res = self.locator.path_from_song(song)
        self.assertEqual('/foo/Foo/Bar/cover.jpg', res)

    def test_find_path_from_song_with_home_cover(self):
        song = Mock('Song', artist='Toto', album='Tata', file='Foo/Bar/1.ogg')
        res = self.locator.path_from_song(song,
                                          consts.ART_LOCATION_HOMECOVERS)
        self.assertEqual(expanduser('~/.covers/Toto-Tata.jpg'), res)

    # artwork_path
    def test_artwork_path_with_song_name(self):
        song = Mock('Song')
        song.configure_mock(name="plop", artist='Toto', album='Tata',
                            file='F/B/1.ogg')
        res = artwork_path(song, self.config)
        self.assertEqual(expanduser("~/.covers/plop.jpg"), res)


class TestArtworkLookupSingleImage(_MixinTestDirectory, unittest.TestCase):
    def setUp(self):
        super().setUp()
        self.locator = ArtworkLocator(self.config)

    def func(self, path):
        path = os.path.join(self.music_dir, path)
        return self.locator._lookup_single_image(path)

    def test_path_doesnt_exists(self):
        res = list(self.func("bar/baz"))
        self.assertEqual(0, len(res))

    def test_no_images(self):
        self.mkdir("bar", "baz")

        res = list(self.func("bar/baz"))
        self.assertEqual(0, len(res))

    def test_one_image(self):
        self.mkdir("bar", "baz")
        self.touch("bar", "baz", "loc2.jpg")

        res = list(self.func("bar/baz"))
        self.assertEqual(1, len(res))
        self.assertDirEqual("/TMP/bar/baz/loc2.jpg", res[0])

    def test_several_images_no_artwork(self):
        self.mkdir("bar", "baz")
        self.touch("bar", "baz", "loc1.jpg")
        self.touch("bar", "baz", "loc2.jpg")

        res = list(self.func("bar/baz"))
        self.assertEqual(0, len(res))


class TestArtworkLocator(unittest.TestCase):
    def setUp(self):
        self.music_dir = "/foo"
        self.config = Mock('Config',
                           current_musicdir=self.music_dir,
                           art_location_custom_filename="")
        self.locator = ArtworkLocator(self.config)

    def get_locations(self, artist="Toto", album="Tata", song_dir="To/Ta",
                      default_kind=None):
        return self.locator._get_locations(artist, album,
                                           song_dir, default_kind)

    def test_simple_locations(self):
        l = self.get_locations()

        for key in dir(consts):
            if not key.startswith('ART_LOCATION_'):
                continue

            self.assertIn(getattr(consts, key), l)

    def test_home_covers(self):
        l = self.get_locations()[consts.ART_LOCATION_HOMECOVERS]
        self.assertEqual(1, len(l))
        self.assertEqual(os.path.expanduser("~/.covers/Toto-Tata.jpg"), l[0])

    def test_cover_jpg(self):
        l = self.get_locations()[consts.ART_LOCATION_COVER]
        self.assertEqual(1, len(l))
        self.assertEqual("/foo/To/Ta/cover.jpg", l[0])

    def test_folder_jpg(self):
        l = self.get_locations()[consts.ART_LOCATION_FOLDER]
        self.assertEqual(1, len(l))
        self.assertEqual("/foo/To/Ta/folder.jpg", l[0])

    def test_album_jpg(self):
        l = self.get_locations()[consts.ART_LOCATION_ALBUM]
        self.assertEqual(1, len(l))
        self.assertEqual("/foo/To/Ta/album.jpg", l[0])

    def test_custom_valid(self):
        self.config.art_location_custom_filename = "pouet.jpg"

        l = self.get_locations()[consts.ART_LOCATION_CUSTOM]
        self.assertEqual(1, len(l))
        self.assertEqual("/foo/To/Ta/pouet.jpg", l[0])

    def test_custom_but_empty_custom_file(self):
        self.config.art_location_custom_filename = ""

        l = self.get_locations()[consts.ART_LOCATION_CUSTOM]
        self.assertEqual(0, len(l))

    def test_misc_location(self):
        old_misc = consts.ART_LOCATIONS_MISC
        consts.ART_LOCATIONS_MISC = files = ['1.jpg', '2.jpg', '3.jpg']

        try:
            l = list(self.get_locations()[consts.ART_LOCATION_MISC])
        finally:
            consts.ART_LOCATIONS_MISC = old_misc

        expected = ["/foo/To/Ta/%s" % f for f in files]
        self.assertEqual(expected, l)


class TestArtworkLocatorPathChecks(_MixinTestDirectory, unittest.TestCase):
    def setUp(self):
        super().setUp()
        self.config = Mock('Config',
                           current_musicdir=self.music_dir,
                           art_location_custom_filename="")
        self.locator = ArtworkLocator(self.config)

    def test_locate_existing(self):
        self.mkdir('To', 'Ta')
        cover_path = self.touch('To', 'Ta', 'cover.jpg')
        self.config.art_location = consts.ART_LOCATION_COVER

        res = self.locator.locate('Toto', 'Tata', 'To/Ta')

        self.assertEqual((self.config.art_location, cover_path), res)

    def test_locate_config_has_priority(self):
        self.mkdir('To', 'Ta')
        cover_path  = self.touch('To', 'Ta', 'cover.jpg')
        folder_path = self.touch('To', 'Ta', 'folder.jpg')

        # We request "cover.jpg", it exists, we got it
        self.config.art_location = consts.ART_LOCATION_COVER
        res = self.locator.locate('Toto', 'Tata', 'To/Ta')
        self.assertEqual((self.config.art_location, cover_path), res)

        # If we request now "folder.jpg", we get it before "cover.jpg"
        self.config.art_location = consts.ART_LOCATION_FOLDER
        res = self.locator.locate('Toto', 'Tata', 'To/Ta')
        self.assertEqual((self.config.art_location, folder_path), res)

    def test_locate_nothing_valid(self):
        self.mkdir('To', 'Ta')
        self.config.art_location = consts.ART_LOCATION_COVER

        res = self.locator.locate('Toto', 'Tata', 'To/Ta')

        self.assertEqual((None, None), res)
