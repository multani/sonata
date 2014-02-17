from collections import namedtuple

_SongRecord = namedtuple('SongRecord',
                        ['album', 'artist', 'genre', 'year', 'path'])

def SongRecord(album=None, artist=None, genre=None, year=None, path=None):
    return _SongRecord(album, artist, genre, year, path)
