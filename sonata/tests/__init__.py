import doctest
import unittest
import gettext

# This currently needed, because gettext is used in some module, i want to test
try:
    gettext.install('sonata', os.path.join(sonata.__file__.split('/lib')[0], 'share', 'locale'))
except:
    gettext.install('sonata', '/usr/share/locale')
    gettext.textdomain('sonata')

from sonata import misc, library

DOCTEST_FLAGS = (
    doctest.ELLIPSIS |
    doctest.NORMALIZE_WHITESPACE |
    doctest.REPORT_NDIFF
)


class TestSonata(unittest.TestCase):
    def test_convert_time(self):
        self.assertEqual(misc.convert_time(60*4+4), "04:04")
        self.assertEqual(misc.convert_time(3600*3+60*2), "03:02:00")
    def test_song_record(self):
        record1 = library.SongRecord(artist="a", path="b")
        record2 = library.SongRecord(artist="a", path="b")
        self.assertEqual(record1.artist, "a")
        self.assertEqual(record2.path,   "b")

        # test equality
        self.assertEqual(record1, record2)

        # test hashing
        d = {}
        d[record1] = True
        self.assertIn(record1, d)
        self.assertIn(record2, d) # record1 == record2

        # test unpacking
        a, b, c, d, e = record1
        self.assertEqual(record1.album, a)
        self.assertEqual(record1.artist, b)
        self.assertEqual(record1.genre, c)
        self.assertEqual(record1.path, e)

    def test_list_identfy_VA_albums(self):
        # Test multiple arguments
        data  = [("artist1", "album1", "/",   2006),
                 ("artist2", "album1", "/",   2006),
                 ("artist1", "album1", "test",1992),
                 ("artist3", "album1", "/",   2006)]
        albums = [library.SongRecord(artist=item[0], album=item[1],
                                  path=item[2], year=item[3]) for item in data]
        various_albums = library.list_mark_various_artists_albums(albums)
        albums[0].artist = library.VARIOUS_ARTISTS
        self.assertEqual(various_albums, albums)

        # Test single argument
        albums2 = [library.SongRecord(artist="Tim Pritlove, Holger Klein", album="Not Safe For Work", path="podcasts/Not Save For Work", year=2012)]
        various_albums2 = library.list_mark_various_artists_albums(albums2)
        self.assertEqual(various_albums2, albums2)

def additional_tests():
    return unittest.TestSuite(
        # TODO: add files which use doctests here
      #  doctest.DocFileSuite('../audioscrobbler.py', optionflags=DOCTEST_FLAGS),
    )
