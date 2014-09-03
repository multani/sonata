"""
This module contains the AlbumList class which represents a list of all
albums in the playlist. An album is identified by it's album tag.
The Albumlist can then be sorted randomly.
"""
import random
import logging


class AlbumList:
    """
    Class which wraps functionality to maintain a list of all albums in the
    current playlist.
    It also contains functionality to randomly sort or choose an album.
    """

    def __init__(self, client):
        self.logger = logging.getLogger(__name__)
        self.client = client
        self.albums = None
        self.refresh()

    def refresh(self):
        """fetch a set of albums from the mpd playlist"""
        # fetch albums
        self.albums = {}
        for song in self.client.playlistinfo():
            if "album" in song:
                k = song["album"]
            else:
                # we consider a song without album info to be a one song
                # album and use the title as album name.
                k = song["title"]
                #else:
                # if there is not even a title in the song we ignore it, which
                # which will cause it to end up at the end of the playlist,
                # during shuffling.
            if k not in self.albums:
                self.albums[k] = []
            self.albums[k].append(song)

    def shuffle_albums(self, sortalbumbytrack=True):
        """Essentially do a shuffle over a list of all albums and sort the
        playlist accordingly.
        """
        albumlist = list(self.albums.keys())
        random.shuffle(albumlist)
        for album in albumlist:
            songs = self.albums[album]
            if sortalbumbytrack:
                try:
                    kf = lambda x: int(x["track"].replace("/", " ").split()[0])
                    songs.sort(key=kf)
                except (KeyError, ValueError, TypeError):
                    self.logger.debug("cannot sort album by track: {}"
                                      .format(album))
            for song in reversed(songs):
                self.client.moveid(song["id"], 0)
