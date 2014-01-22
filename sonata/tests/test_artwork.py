from os.path import expanduser
import unittest

from mock import Mock, patch

from sonata.artwork import artwork_path_from_data
from sonata.artwork import artwork_path_from_song
from sonata.artwork import artwork_path
from sonata import consts


class TestArtworkPathFinder(unittest.TestCase):
    def setUp(self):
        self.config = Mock('Config', current_musicdir="/foo")

    # artwork_path_from_data
    def _call_artwork_path_from_data(self,  location_type=None,
                                     artist="Toto",
                                     album="Tata",
                                     song_dir="To/Ta"):

        return artwork_path_from_data(artist, album, song_dir, self.config,
                                      location_type)

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
        res = artwork_path_from_song(song, self.config)
        self.assertEqual('/foo/Foo/Bar/cover.jpg', res)

    def test_find_path_from_song_with_home_cover(self):
        song = Mock('Song', artist='Toto', album='Tata', file='Foo/Bar/1.ogg')
        res = artwork_path_from_song(song, self.config,
                                     consts.ART_LOCATION_HOMECOVERS)
        self.assertEqual(expanduser('~/.covers/Toto-Tata.jpg'), res)

    # artwork_path
    def test_artwork_path_with_song_name(self):
        song = Mock('Song')
        song.configure_mock(name="plop", artist='Toto', album='Tata',
                            file='F/B/1.ogg')
        res = artwork_path(song, self.config)
        self.assertEqual(expanduser("~/.covers/plop.jpg"), res)

    @patch('sonata.artwork.artwork_path_from_song')
    def test_artwork_path_without_song_name(self, mock_artwork_path_from_song):
        mock_artwork_path_from_song.return_value = 'foo'
        song = Mock('Song')
        song.configure_mock(name=None)

        res = artwork_path(song, self.config)
        mock_artwork_path_from_song.assert_called_with(song, self.config)
        self.assertEqual('foo', res)
