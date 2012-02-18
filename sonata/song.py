
class SongRecord():
    """A convenient class to store a song"""
    # use slots for memory efficiency
    __slots__ = ['album', 'artist', 'genre', 'year', 'path']
    def __init__(self, album=None, artist=None, genre=None, year=None, path=None):
        self.album = album
        self.artist = artist
        self.genre = genre
        self.year = year
        self.path = path
    def __repr__(self):
        """Return a nicely formatted representation string"""
        return "<SongRecord album='%s', artist='%s', genre='%s', year='%s', path='%s'>" %(
            self.album, self.artist, self.genre, self.year, self.path)
    def __key(self):
        return (self.album, self.artist, self.genre, self.year, self.path)
    def __eq__(self, y):
        return isinstance(y, SongRecord) and self.__key() == y.__key()
    def __iter__(self):
        """Make the classed iterable. useful for unpacking variables"""
        for i in (self.album, self.artist, self.genre, self.year, self.path):
            yield i
    def __hash__(self):
        return hash(self.__key())
