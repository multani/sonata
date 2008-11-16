
class Constants:
    def __init__(self):
        self.ART_LOCAL = 0
        self.ART_LOCAL_REMOTE = 1
        self.VIEW_FILESYSTEM = 0
        self.VIEW_ARTIST = 1
        self.VIEW_GENRE = 2
        self.LYRIC_TIMEOUT = 10
        self.NOTIFICATION_WIDTH_MAX = 500
        self.NOTIFICATION_WIDTH_MIN = 350
        self.FULLSCREEN_COVER_SIZE = 500
        self.ART_LOCATION_HOMECOVERS = 0		# ~/.covers/[artist]-[album].jpg
        self.ART_LOCATION_COVER = 1				# file_dir/cover.jpg
        self.ART_LOCATION_ALBUM = 2				# file_dir/album.jpg
        self.ART_LOCATION_FOLDER = 3			# file_dir/folder.jpg
        self.ART_LOCATION_CUSTOM = 4			# file_dir/[custom]
        self.ART_LOCATION_SINGLE = 6
        self.ART_LOCATION_MISC = 7
        self.ART_LOCATIONS_MISC = ['front.jpg', '.folder.jpg', '.folder.png', 'AlbumArt.jpg', 'AlbumArtSmall.jpg']
        self.LYRICS_LOCATION_HOME = 0			# ~/.lyrics/[artist]-[song].txt
        self.LYRICS_LOCATION_PATH = 1			# file_dir/[artist]-[song].txt
        self.LIB_COVER_SIZE = 16
        self.COVERS_TYPE_STANDARD = 0
        self.COVERS_TYPE_STYLIZED = 1
        self.LIB_LEVEL_GENRE = 0
        self.LIB_LEVEL_ARTIST = 1
        self.LIB_LEVEL_ALBUM = 2
        self.LIB_LEVEL_SONG = 3

consts = Constants()
