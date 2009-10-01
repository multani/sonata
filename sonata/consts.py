
"""
This module contains various constant definitions that any other
module can import without risk of cyclic imports.

Most of the constants are enum-like, that is, they provide symbolic
names for a set of values.

XXX Should some of these be moved to be private in some module, or
into config?

Example usage:
from consts import consts
...
if view == consts.VIEW_ALBUM: ...
"""

class Constants:
    """This class contains the constant definitions as attributes."""
    def __init__(self):
        self.ART_LOCAL = 0
        self.ART_LOCAL_REMOTE = 1
        self.VIEW_FILESYSTEM = 0
        self.VIEW_ARTIST = 1
        self.VIEW_GENRE = 2
        self.VIEW_ALBUM = 3
        self.LYRIC_TIMEOUT = 10
        self.NOTIFICATION_WIDTH_MAX = 500
        self.NOTIFICATION_WIDTH_MIN = 350
        self.FULLSCREEN_COVER_SIZE = 500
        self.ART_LOCATION_HOMECOVERS = 0      # ~/.covers/[artist]-[album].jpg
        self.ART_LOCATION_COVER = 1           # file_dir/cover.jpg
        self.ART_LOCATION_ALBUM = 2           # file_dir/album.jpg
        self.ART_LOCATION_FOLDER = 3          # file_dir/folder.jpg
        self.ART_LOCATION_CUSTOM = 4          # file_dir/[custom]
        self.ART_LOCATION_SINGLE = 6
        self.ART_LOCATION_MISC = 7
        self.ART_LOCATIONS_MISC = ['front.jpg', '.folder.jpg', '.folder.png', 'AlbumArt.jpg', 'AlbumArtSmall.jpg']
        self.LYRICS_LOCATION_HOME = 0         # ~/.lyrics/[artist]-[song].txt
        self.LYRICS_LOCATION_PATH = 1         # file_dir/[artist]-[song].txt
        self.LYRICS_LOCATION_HOME_ALT = 2     # ~/.lyrics/[artist] - [song].txt
        self.LYRICS_LOCATION_PATH_ALT = 3     # file_dir/[artist] - [song].txt
        self.LIB_COVER_SIZE = 32
        self.COVERS_TYPE_STANDARD = 0
        self.COVERS_TYPE_STYLIZED = 1
        self.LIB_LEVEL_GENRE = 0
        self.LIB_LEVEL_ARTIST = 1
        self.LIB_LEVEL_ALBUM = 2
        self.LIB_LEVEL_SONG = 3
        self.NUM_ARTISTS_FOR_VA = 2

consts = Constants()
