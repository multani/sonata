#!/usr/bin/python

import doctest
import unittest
import gettext
import os
import sys
import operator

# This currently needed, because gettext is used in some module, i want to test
try:
    gettext.install('sonata', os.path.join(sonata.__file__.split('/lib')[0], 'share', 'locale'))
except:
    gettext.install('sonata', '/usr/share/locale')
    gettext.textdomain('sonata')

from sonata import misc, song, library

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
        record_first = song.SongRecord("a", "a", "a", "a", "a")
        record_equal = song.SongRecord(artist="a", path="b")
        record_equal2 = song.SongRecord(artist="a", path="b")
        record_last = song.SongRecord("z", "z", "z", "z", "z")
        self.assertEqual(record_equal.artist, "a")
        self.assertEqual(record_equal2.path,   "b")

        # test comparision
        self.assertEqual(record_equal, record_equal2)
        self.assertNotEqual(record_first, record_last)
        self.assertGreater(record_last, record_first)
        self.assertGreaterEqual(record_last, record_first)
        self.assertLess(record_first, record_last)
        self.assertLessEqual(record_first, record_last)

        # test hashing
        d = {}
        d[record_equal] = True
        self.assertIn(record_equal, d)
        self.assertIn(record_equal2, d) # record_equal == record_equal2

        # test sorting
        lst = [record_equal, record_equal2, record_last, record_first]
        lst.sort(key=operator.attrgetter("path"))
        self.assertEqual(lst, [record_first, record_equal, record_equal2, record_last])

        # test unpacking
        a, b, c, d, e = record_equal
        self.assertEqual(record_equal.album, a)
        self.assertEqual(record_equal.artist, b)
        self.assertEqual(record_equal.genre, c)
        self.assertEqual(record_equal.path, e)

    def test_list_identfy_VA_albums(self):
        # Test multiple arguments
        data  = [("artist1", "album1", "/",   2006),
                 ("artist2", "album1", "/",   2006),
                 ("artist1", "album1", "test",1992),
                 ("artist3", "album1", "/",   2006)]
        albums = [song.SongRecord(artist=item[0], album=item[1],
                                  path=item[2], year=item[3]) for item in data]
        various_albums = library.list_mark_various_artists_albums(albums)
        albums[0].artist = library.VARIOUS_ARTISTS
        self.assertEqual(various_albums, albums)

        # Test single argument
        albums2 = [song.SongRecord(artist="Tim Pritlove, Holger Klein", album="Not Safe For Work", path="podcasts/Not Save For Work", year=2012)]
        various_albums2 = library.list_mark_various_artists_albums(albums2)
        self.assertEqual(various_albums2, albums2)

def additional_tests():
    return unittest.TestSuite(
        # TODO: add files which use doctests here
      #  doctest.DocFileSuite('../audioscrobbler.py', optionflags=DOCTEST_FLAGS),
    )
