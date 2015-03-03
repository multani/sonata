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

ART_LOCAL = 0
ART_LOCAL_REMOTE = 1
VIEW_FILESYSTEM = 0
VIEW_ARTIST = 1
VIEW_GENRE = 2
VIEW_ALBUM = 3
LYRIC_TIMEOUT = 10
NOTIFICATION_WIDTH_MAX = 500
NOTIFICATION_WIDTH_MIN = 350
FULLSCREEN_COVER_SIZE = 500
ART_LOCATION_HOMECOVERS = 0      # ~/.covers/[artist]-[album].jpg
ART_LOCATION_COVER = 1           # file_dir/cover.jpg
ART_LOCATION_ALBUM = 2           # file_dir/album.jpg
ART_LOCATION_FOLDER = 3          # file_dir/folder.jpg
ART_LOCATION_CUSTOM = 4          # file_dir/[custom]
ART_LOCATION_SINGLE = 6
ART_LOCATION_MISC = 7
ART_LOCATIONS_MISC = ['front.jpg', '.folder.jpg',
                      '.folder.png', 'AlbumArt.jpg',
                      'AlbumArtSmall.jpg']
LYRICS_LOCATION_HOME = 0         # ~/.lyrics/[artist]-[song].txt
LYRICS_LOCATION_PATH = 1         # file_dir/[artist]-[song].txt
LYRICS_LOCATION_HOME_ALT = 2     # ~/.lyrics/[artist] - [song].txt
LYRICS_LOCATION_PATH_ALT = 3     # file_dir/[artist] - [song].txt
LIB_COVER_SIZE = 32
COVERS_TYPE_STANDARD = 0
COVERS_TYPE_STYLIZED = 1
LIB_LEVEL_GENRE = 0
LIB_LEVEL_ARTIST = 1
LIB_LEVEL_ALBUM = 2
LIB_LEVEL_SONG = 3
NUM_ARTISTS_FOR_VA = 2

# the names of the plug-ins that will be enabled by default
DEFAULT_PLUGINS = [
    'playlists',
    'streams',
    'lyricwiki',
    'localmpd',
]
