"""
This module contains the AlbumList class which represents a list of all
albums in the playlist. An album is identified by it's album tag.
The Albumlist can then be sorted randomly.
"""

import collections
import operator
import random


class AlbumList:
    """
    Class which wraps functionality to maintain a list of all albums in the
    current playlist.
    It also contains functionality to randomly sort or choose an album.
    """

    def __init__(self, client):
        self.client = client
        self.albums = collections.defaultdict(lambda: [])
        self.refresh()

    def refresh(self):
        """fetch a set of albums from the mpd playlist"""
        # fetch albums
        for song in self.client.playlistinfo():
            if "album" in song:
                k = song.album
            else:
                # We consider a song without album info to be a one song
                # album and use the title as album name.
                if 'title' in song:
                    k = song.title
                else:
                    # If there is not even a title in the song we ignore it,
                    # which which will cause it to end up at the end of the
                    # playlist, during shuffling.
                    continue
            self.albums[k].append(song)

    def shuffle_albums(self):
        """Essentially do a shuffle over a list of all albums and sort the
        playlist accordingly.
        """
        album_names = list(self.albums.keys())
        random.shuffle(album_names)
        for album in album_names:
            for song in sorted(albums[album], key=operator.attrgetter('track'),
                               reverse=True):
                self.client.moveid(song["id"], 0)
