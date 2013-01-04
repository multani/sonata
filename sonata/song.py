
class SongRecord:
    """
    A convenient class to store a song

    Example usage:
    import song
    one   = song.SongRecord("album", "artist", "genre", "year", "path")
    other = song.SongRecord(album="album", artist="artist",
                            genre="genre", year="year", path="path")
    # object with same content are equal, other comparision works too.
    print(one == other)  # True
    # Support unpacking
    album, artist, genre = song
    # is hashable
    mycache = {}
    mycache[song] = True
    # pretty printing
    print(song) # <SongRecord album='album', artist='artist', genre='genre', year='year', path='path'>"
    """
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
        return "<SongRecord album='%s', artist='%s', genre='%s', year='%s', path='%s'>" % (
            self.album, self.artist, self.genre, self.year, self.path)
    def __key(self):
        return (self.album, self.artist, self.genre, self.year, self.path)
    def __iter__(self):
        """Make the classed iterable. useful for unpacking variables"""
        for i in (self.album, self.artist, self.genre, self.year, self.path):
            yield i
    def __hash__(self):
        return hash(self.__key())
    def __lt__(self, other):
        return self.__key() <  other
    def __le__(self, other):
        return self.__key() <=  other
    def __eq__(self, other):
        return self.__key() == other
    def __ne__(self, other):
        return self.__key() != other
    def __gt__(self, other):
        return self.__key() > other
    def __ge__(self, other):
        return self.__key() >= other
