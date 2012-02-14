import doctest
import unittest
from sonata import misc


DOCTEST_FLAGS = (
    doctest.ELLIPSIS |
    doctest.NORMALIZE_WHITESPACE |
    doctest.REPORT_NDIFF
)


class TestSonata(unittest.TestCase):
    def test_convert_time(self):
        self.assertEqual(misc.convert_time(60*4+4), "04:04")
        self.assertEqual(misc.convert_time(3600*3+60*2), "03:02:00")

def additional_tests():
    return unittest.TestSuite(
        # TODO: add files which use doctests here
        #doctest.DocFileSuite('../audioscrobbler.py', optionflags=DOCTEST_FLAGS),
    )
