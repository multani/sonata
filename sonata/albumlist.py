"""
This module contains functionality
"""
import random


class AlbumList(object):
    """
    Class which wraps functionality to maintain a list of all albums in the
    current playlist.
    It also contains functionality to randomly sort or choose an album.
    """

    def __init__(self, client):
        self.client = client
        self.albums = None
        self.refresh()

    def refresh(self):
        """fetch a list of albums from the mpd playlist"""
        # newly seed the rng for less predictibility
        random.seed()
        # fetch albums
        self.albums = set()
        for song in self.client.playlistinfo():
            if "album" in song and "artist" in song:
                self.albums.add((song["album"], song["artist"]))
            else:
                #TODO: How to deal with songs without album info?
                # Probably every song without album info should be considered
                # to be in a separate album.
                # Let's leave it for now...
                #if "artist" in song:
                #    self.albums.add((None, song["artist"]))
                pass

    def find_album_boundaries(self, albumname):
        """Get a tuple of the positions of the first and last song of the
        passed album name. If the album isn't found (None, None) is returned.
        """
        # TODO: also search for artist?
        entries = self.client.playlistfind("album", albumname)
        if entries:
            return int(entries[0]["pos"]), int(entries[-1]["pos"])
        else:
            return None, None

    def get_current_album(self):
        """returns the name of the current album"""
        return self.client.currentsong()["album"]

    def choose_random_album(self, current):
        """picks a random album from the current playlist, while trying to
        avoid the current album.
        """
        if self.albums:
            if len(self.albums) == 1:
                return current
            else:
                l = list(self.albums)
                new = random.choice(l)
                while new == current:
                    new = random.choice(l)
                return new
        else:
            # No albums found
            return None

    def play_random(self):
        """Play first song of a random album in the current playlist."""
        current = self.get_current_album()
        new = self.choose_random_album(current)
        if new is not None:
            # Choosing random album
            entries = self.client.playlistfind("album", new)
            if entries:
                self.client.play(entries[0]["pos"])
            else:
                # Couldn't find entry for album, choose another one
                self.refresh()
                self.play_random()
        #else:
            # Playlist seems to be empty

    def shuffle_albums(self):
        """Essentially do a random.shuffle over all albums and sort the
        playlist accordingly. This assumes that the playlist is already
        sorted by albums.
        """
        albumlist = list(self.albums)
        random.shuffle(albumlist)
        for album, artist in albumlist:
            first, last = self.find_album_boundaries(album)
            if first is None or last is None:
                # No boundaries for album
                pass
            else:
                # get the songrange and move it to playlist position 0
                songrange = "{}:{}".format(first, last + 1)
                self.client.move(songrange, 0)

    def __iter__(self):
        """iterate over all album names"""
        self.refresh()
        for album, artist in self.albums:
            yield album
