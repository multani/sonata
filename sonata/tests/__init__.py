#!/usr/bin/python
# Copyright 2006-2009 Scott Horowitz <stonecrest@gmail.com>
# Copyright 2009-2014 Jonathan Ballet <jon@multani.info>
#
# This file is part of Sonata.
#
# Sonata is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# Sonata is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with Sonata.  If not, see <http://www.gnu.org/licenses/>.

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
from sonata.mpdhelper import MPDSong

DOCTEST_FLAGS = (
    doctest.ELLIPSIS |
    doctest.NORMALIZE_WHITESPACE |
    doctest.REPORT_NDIFF
)

DOCTEST_MODULES = [
    'artwork',
    'mpdhelper',
]

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

        album = albums[0]._asdict()
        album['artist'] = library.VARIOUS_ARTISTS
        albums[0] = song.SongRecord(**album)

        self.assertEqual(various_albums, albums)

        # Test single argument
        albums2 = [song.SongRecord(artist="Tim Pritlove, Holger Klein", album="Not Safe For Work", path="podcasts/Not Save For Work", year=2012)]
        various_albums2 = library.list_mark_various_artists_albums(albums2)
        self.assertEqual(various_albums2, albums2)


class TestMPDSong(unittest.TestCase):
    def test_get_track_number(self):
        self.assertEqual(1, MPDSong({'track': '1'}).track)
        self.assertEqual(1, MPDSong({'track': '1/10'}).track)
        self.assertEqual(1, MPDSong({'track': '1,10'}).track)
        self.assertEqual(0, MPDSong({'track': '/'}).track)
        self.assertEqual(0, MPDSong({'track': ','}).track)

    def test_get_disc_number(self):
        self.assertEqual(1, MPDSong({'disc': '1'}).disc)
        self.assertEqual(1, MPDSong({'disc': '1/10'}).disc)
        self.assertEqual(1, MPDSong({'disc': '1,10'}).disc)
        self.assertEqual(0, MPDSong({'disc': '/'}).disc)
        self.assertEqual(0, MPDSong({'disc': ','}).disc)

    def test_access_attributes(self):
        song = MPDSong({'foo': 'zz', 'id': '5'})

        self.assertEqual(5, song.id)
        self.assertEqual("zz", song.foo)
        self.assertIsInstance(song.foo, str)
        self.assertEqual(song.foo, song.get("foo"))

    def test_get_unknown_attribute(self):
        song = MPDSong({})
        self.assertRaises(KeyError, lambda: song['bla'])
        self.assertEqual(None, song.get('bla'))
        self.assertEqual('foo', song.get('bla', 'foo'))
        self.assertEqual(None, song.bla)

    def test_access_list_attribute(self):
        song = MPDSong({'genre': ['a', 'b'], 'foo': ['c', 'd']})
        self.assertEqual('a', song.genre)
        self.assertEqual('c', song.foo)


def load_tests(loader, tests, ignore):
    for sub_module in DOCTEST_MODULES:
        test = doctest.DocTestSuite('sonata.%s' % sub_module,
                                    optionflags=DOCTEST_FLAGS)
        tests.addTests(test)
    return tests
