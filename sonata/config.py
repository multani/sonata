
import os, hashlib
import ConfigParser

from consts import consts
import misc

class Config:
    def __init__(self, default_profile_name, currsongformat2):
        # the config settings:
        self.profile_num = 0
        self.profile_names = [default_profile_name]
        self.musicdir = [misc.sanitize_musicdir("~/music")]
        self.host = ['localhost']
        self.port = [6600]
        self.password = ['']

        self.x = 0
        self.y = 0
        self.w = 400
        self.h = 300
        self.expanded = True
        self.withdrawn = False
        self.sticky = False
        self.ontop = False
        self.screen = 0

        self.xfade = 0
        self.xfade_enabled = False
        self.show_covers = True
        self.covers_type = 1
        self.covers_pref = consts.ART_LOCAL_REMOTE

        self.show_notification = False
        self.show_playback = True
        self.show_progress = True
        self.show_statusbar = False
        self.show_trayicon = True
        self.show_lyrics = True
        self.stop_on_exit = False
        self.update_on_start = False
        self.minimize_to_systray = False

        self.popup_option = 2

        self.initial_run = True
        self.show_header = True
        self.tabs_expanded = False
        self.currentformat = "%A - %T"
        self.libraryformat = "%A - %T"
        self.titleformat = "[Sonata] %A - %T"
        self.currsongformat1 = "%T"
        self.currsongformat2 = currsongformat2
        # this mirrors Main.columns widths
        self.columnwidths = []
        self.colwidthpercents = []
        self.autoconnect = True

        self.stream_names = []
        self.stream_uris = []

        self.last_search_num = 0

        self.use_infofile = False
        self.infofile_path = '/tmp/xmms-info'
        self.lib_view = consts.VIEW_FILESYSTEM
        self.lib_level = 0
        self.lib_level_prev = -1
        self.lib_genre = ''
        self.lib_artist = ''
        self.lib_album = ''
        self.art_location = consts.ART_LOCATION_HOMECOVERS
        self.art_location_custom_filename = ""
        self.lyrics_location = consts.LYRICS_LOCATION_HOME

        self.as_enabled = False
        self.as_username = ""
        self.as_password_md5 = ""

        self.url_browser = ""
        self.wd = None

        self.info_song_expanded = True
        self.info_lyrics_expanded = True
        self.info_album_expanded = True
        self.info_song_more = False
        self.current_tab_visible = True
        self.library_tab_visible = True
        self.playlists_tab_visible = True
        self.streams_tab_visible = True
        self.info_tab_visible = True

        # these mirror Main.notebook tab nums
        self.current_tab_pos = 0
        self.library_tab_pos = 1
        self.playlists_tab_pos = 2
        self.streams_tab_pos = 3
        self.info_tab_pos = 4

        self.info_art_enlarged = False

        self.existing_playlist_option = 0

        self.traytips_notifications_location = 0

    def settings_load_real(self):
        # Load config
        conf = ConfigParser.ConfigParser()
        misc.create_dir('~/.config/sonata/')
        if os.path.isfile(os.path.expanduser('~/.config/sonata/sonatarc')):
            conf.read(os.path.expanduser('~/.config/sonata/sonatarc'))
        else:
            return
        # Compatibility with previous versions of Sonata:
        # --------------------------------------------------------------------
        if conf.has_option('connection', 'host'):
            self.host[0] = conf.get('connection', 'host')
        if conf.has_option('connection', 'port'):
            self.port[0] = int(conf.get('connection', 'port'))
        if conf.has_option('connection', 'password'):
            self.password[0] = conf.get('connection', 'password')
        if conf.has_option('connection', 'musicdir'):
            self.musicdir[0] = misc.sanitize_musicdir(conf.get('connection', 'musicdir'))
        # --------------------------------------------------------------------
        if conf.has_option('connection', 'auto'):
            self.autoconnect = conf.getboolean('connection', 'auto')
        if conf.has_option('connection', 'profile_num'):
            self.profile_num = conf.getint('connection', 'profile_num')
        if conf.has_option('player', 'x'):
            self.x = conf.getint('player', 'x')
        if conf.has_option('player', 'y'):
            self.y = conf.getint('player', 'y')
        if conf.has_option('player', 'w'):
            self.w = conf.getint('player', 'w')
        if conf.has_option('player', 'h'):
            self.h = conf.getint('player', 'h')
        if conf.has_option('player', 'expanded'):
            self.expanded = conf.getboolean('player', 'expanded')
        if conf.has_option('player', 'withdrawn'):
            self.withdrawn = conf.getboolean('player', 'withdrawn')
        if conf.has_option('player', 'screen'):
            self.screen = conf.getint('player', 'screen')
        if conf.has_option('player', 'covers'):
            self.show_covers = conf.getboolean('player', 'covers')
        if conf.has_option('player', 'covers_type'):
            self.covers_type = conf.getint('player', 'covers_type')
        if conf.has_option('player', 'stop_on_exit'):
            self.stop_on_exit = conf.getboolean('player', 'stop_on_exit')
        if conf.has_option('player', 'minimize'):
            self.minimize_to_systray = conf.getboolean('player', 'minimize')
        if conf.has_option('player', 'initial_run'):
            self.initial_run = conf.getboolean('player', 'initial_run')
        if conf.has_option('player', 'statusbar'):
            self.show_statusbar = conf.getboolean('player', 'statusbar')
        if conf.has_option('player', 'lyrics'):
            self.show_lyrics = conf.getboolean('player', 'lyrics')
        if conf.has_option('player', 'sticky'):
            self.sticky = conf.getboolean('player', 'sticky')
        if conf.has_option('player', 'ontop'):
            self.ontop = conf.getboolean('player', 'ontop')
        if conf.has_option('player', 'notification'):
            self.show_notification = conf.getboolean('player', 'notification')
        if conf.has_option('player', 'popup_time'):
            self.popup_option = conf.getint('player', 'popup_time')
        if conf.has_option('player', 'update_on_start'):
            self.update_on_start = conf.getboolean('player', 'update_on_start')
        if conf.has_option('player', 'notif_location'):
            self.traytips_notifications_location = conf.getint('player', 'notif_location')
        if conf.has_option('player', 'playback'):
            self.show_playback = conf.getboolean('player', 'playback')
        if conf.has_option('player', 'progressbar'):
            self.show_progress = conf.getboolean('player', 'progressbar')
        if conf.has_option('player', 'crossfade'):
            crossfade = conf.getint('player', 'crossfade')
            # Backwards compatibility:
            self.xfade = crossfade
        if conf.has_option('player', 'xfade'):
            self.xfade = conf.getint('player', 'xfade')
        if conf.has_option('player', 'xfade_enabled'):
            self.xfade_enabled = conf.getboolean('player', 'xfade_enabled')
        if conf.has_option('player', 'covers_pref'):
            self.covers_pref = conf.getint('player', 'covers_pref')
            # Specifying remote artwork first is too confusing and probably
            # rarely used, so we're removing this option and defaulting users
            # back to the default 'local, then remote' option.
            if self.covers_pref > consts.ART_LOCAL_REMOTE:
                self.covers_pref = consts.ART_LOCAL_REMOTE
        if conf.has_option('player', 'use_infofile'):
            self.use_infofile = conf.getboolean('player', 'use_infofile')
        if conf.has_option('player', 'infofile_path'):
            self.infofile_path = conf.get('player', 'infofile_path')
        if conf.has_option('player', 'trayicon'):
            self.show_trayicon = conf.getboolean('player', 'trayicon')
        if conf.has_option('player', 'view'):
            self.lib_view = conf.getint('player', 'view')
        if conf.has_option('player', 'search_num'):
            self.last_search_num = conf.getint('player', 'search_num')
        if conf.has_option('player', 'art_location'):
            self.art_location = conf.getint('player', 'art_location')
        if conf.has_option('player', 'art_location_custom_filename'):
            self.art_location_custom_filename = conf.get('player', 'art_location_custom_filename')
        if conf.has_option('player', 'lyrics_location'):
            self.lyrics_location = conf.getint('player', 'lyrics_location')
        if conf.has_option('player', 'info_song_expanded'):
            self.info_song_expanded = conf.getboolean('player', 'info_song_expanded')
        if conf.has_option('player', 'info_lyrics_expanded'):
            self.info_lyrics_expanded = conf.getboolean('player', 'info_lyrics_expanded')
        if conf.has_option('player', 'info_album_expanded'):
            self.info_album_expanded = conf.getboolean('player', 'info_album_expanded')
        if conf.has_option('player', 'info_song_more'):
            self.info_song_more = conf.getboolean('player', 'info_song_more')
        if conf.has_option('player', 'columnwidths'):
            self.columnwidths = conf.get('player', 'columnwidths').split(",")
            for col in range(len(self.columnwidths)):
                self.columnwidths[col] = int(self.columnwidths[col])
            self.colwidthpercents = [0] * len(self.columnwidths)
        if conf.has_option('player', 'show_header'):
            self.show_header = conf.getboolean('player', 'show_header')
        if conf.has_option('player', 'tabs_expanded'):
            self.tabs_expanded = conf.getboolean('player', 'tabs_expanded')
        if conf.has_option('player', 'browser'):
            self.url_browser = conf.get('player', 'browser')
        if conf.has_option('player', 'info_art_enlarged'):
            self.info_art_enlarged = conf.getboolean('player', 'info_art_enlarged')
        if conf.has_option('player', 'existing_playlist'):
            self.existing_playlist_option = conf.getint('player', 'existing_playlist')
        if conf.has_section('notebook'):
            if conf.has_option('notebook', 'current_tab_visible'):
                self.current_tab_visible = conf.getboolean('notebook', 'current_tab_visible')
            if conf.has_option('notebook', 'library_tab_visible'):
                self.library_tab_visible = conf.getboolean('notebook', 'library_tab_visible')
            if conf.has_option('notebook', 'playlists_tab_visible'):
                self.playlists_tab_visible = conf.getboolean('notebook', 'playlists_tab_visible')
            if conf.has_option('notebook', 'streams_tab_visible'):
                self.streams_tab_visible = conf.getboolean('notebook', 'streams_tab_visible')
            if conf.has_option('notebook', 'info_tab_visible'):
                self.info_tab_visible = conf.getboolean('notebook', 'info_tab_visible')
            if conf.has_option('notebook', 'current_tab_pos'):
                try: self.current_tab_pos = conf.getint('notebook', 'current_tab_pos')
                except: pass
            if conf.has_option('notebook', 'library_tab_pos'):
                try: self.library_tab_pos = conf.getint('notebook', 'library_tab_pos')
                except: pass
            if conf.has_option('notebook', 'playlists_tab_pos'):
                try: self.playlists_tab_pos = conf.getint('notebook', 'playlists_tab_pos')
                except: pass
            if conf.has_option('notebook', 'streams_tab_pos'):
                try: self.streams_tab_pos = conf.getint('notebook', 'streams_tab_pos')
                except: pass
            if conf.has_option('notebook', 'info_tab_pos'):
                try: self.info_tab_pos = conf.getint('notebook', 'info_tab_pos')
                except: pass
        if conf.has_section('library'):
            if conf.has_option('library', 'lib_wd'):
                self.wd = conf.get('library', 'lib_wd')
            if conf.has_option('library', 'lib_level'):
                self.lib_level = conf.getint('library', 'lib_level')
        if conf.has_section('currformat'):
            if conf.has_option('currformat', 'current'):
                self.currentformat = conf.get('currformat', 'current')
            if conf.has_option('currformat', 'library'):
                self.libraryformat = conf.get('currformat', 'library')
            if conf.has_option('currformat', 'title'):
                self.titleformat = conf.get('currformat', 'title')
            if conf.has_option('currformat', 'currsong1'):
                self.currsongformat1 = conf.get('currformat', 'currsong1')
            if conf.has_option('currformat', 'currsong2'):
                self.currsongformat2 = conf.get('currformat', 'currsong2')
        if conf.has_option('streams', 'num_streams'):
            num_streams = conf.getint('streams', 'num_streams')
            self.stream_names = []
            self.stream_uris = []
            for i in range(num_streams):
                self.stream_names.append(conf.get('streams', 'names[' + str(i) + ']'))
                self.stream_uris.append(conf.get('streams', 'uris[' + str(i) + ']'))
        if conf.has_option('audioscrobbler', 'use_audioscrobbler'):
            self.as_enabled = conf.getboolean('audioscrobbler', 'use_audioscrobbler')
        if conf.has_option('audioscrobbler', 'username'):
            self.as_username = conf.get('audioscrobbler', 'username')
        if conf.has_option('audioscrobbler', 'password'): # old...
            self.as_password_md5 = hashlib.md5(conf.get('audioscrobbler', 'password')).hexdigest()
        if conf.has_option('audioscrobbler', 'password_md5'):
            self.as_password_md5 = conf.get('audioscrobbler', 'password_md5')
        if conf.has_option('profiles', 'num_profiles'):
            num_profiles = conf.getint('profiles', 'num_profiles')
            if num_profiles > 0:
                self.profile_names = []
                self.host = []
                self.port = []
                self.password = []
                self.musicdir = []
            for i in range(num_profiles):
                self.profile_names.append(conf.get('profiles', 'names[' + str(i) + ']'))
                self.host.append(conf.get('profiles', 'hosts[' + str(i) + ']'))
                self.port.append(conf.getint('profiles', 'ports[' + str(i) + ']'))
                self.password.append(conf.get('profiles', 'passwords[' + str(i) + ']'))
                self.musicdir.append(misc.sanitize_musicdir(conf.get('profiles', 'musicdirs[' + str(i) + ']')))
            # Ensure we have a valid profile number:
            if self.profile_num < 0 or self.profile_num > num_profiles-1:
                self.profile_num = 0

    def settings_save_real(self):
        conf = ConfigParser.ConfigParser()
        conf.add_section('profiles')
        conf.set('profiles', 'num_profiles', len(self.profile_names))
        for i in range(len(self.profile_names)):
            conf.set('profiles', 'names[' + str(i) + ']', self.profile_names[i])
            conf.set('profiles', 'hosts[' + str(i) + ']', self.host[i])
            conf.set('profiles', 'ports[' + str(i) + ']', self.port[i])
            conf.set('profiles', 'passwords[' + str(i) + ']', self.password[i])
            conf.set('profiles', 'musicdirs[' + str(i) + ']', self.musicdir[i])
        conf.add_section('connection')
        conf.set('connection', 'auto', self.autoconnect)
        conf.set('connection', 'profile_num', self.profile_num)
        conf.add_section('player')
        conf.set('player', 'w', self.w)
        conf.set('player', 'h', self.h)
        conf.set('player', 'x', self.x)
        conf.set('player', 'y', self.y)
        conf.set('player', 'expanded', self.expanded)
        conf.set('player', 'withdrawn', self.withdrawn)
        conf.set('player', 'screen', self.screen)
        conf.set('player', 'covers', self.show_covers)
        conf.set('player', 'covers_type', self.covers_type)
        conf.set('player', 'stop_on_exit', self.stop_on_exit)
        conf.set('player', 'minimize', self.minimize_to_systray)
        conf.set('player', 'initial_run', self.initial_run)
        conf.set('player', 'statusbar', self.show_statusbar)
        conf.set('player', 'lyrics', self.show_lyrics)
        conf.set('player', 'sticky', self.sticky)
        conf.set('player', 'ontop', self.ontop)
        conf.set('player', 'notification', self.show_notification)
        conf.set('player', 'popup_time', self.popup_option)
        conf.set('player', 'update_on_start', self.update_on_start)
        conf.set('player', 'notif_location', self.traytips_notifications_location)
        conf.set('player', 'playback', self.show_playback)
        conf.set('player', 'progressbar', self.show_progress)
        conf.set('player', 'xfade', self.xfade)
        conf.set('player', 'xfade_enabled', self.xfade_enabled)
        conf.set('player', 'covers_pref', self.covers_pref)
        conf.set('player', 'use_infofile', self.use_infofile)
        conf.set('player', 'infofile_path', self.infofile_path)
        conf.set('player', 'trayicon', self.show_trayicon)
        conf.set('player', 'view', self.lib_view)
        conf.set('player', 'search_num', self.last_search_num)
        conf.set('player', 'art_location', self.art_location)
        conf.set('player', 'art_location_custom_filename', self.art_location_custom_filename)
        conf.set('player', 'lyrics_location', self.lyrics_location)
        conf.set('player', 'info_song_expanded', self.info_song_expanded)
        conf.set('player', 'info_lyrics_expanded', self.info_lyrics_expanded)
        conf.set('player', 'info_album_expanded', self.info_album_expanded)
        conf.set('player', 'info_song_more', self.info_song_more)
        conf.set('player', 'info_art_enlarged', self.info_art_enlarged)
        conf.set('player', 'existing_playlist', self.existing_playlist_option)

        tmp = ""
        for i in range(len(self.columnwidths)-1):
            tmp += str(self.columnwidths[i]) + ","
        tmp += str(self.columnwidths[len(self.columns)-1])
        conf.set('player', 'columnwidths', tmp)

        conf.set('player', 'show_header', self.show_header)
        conf.set('player', 'tabs_expanded', self.tabs_expanded)
        conf.set('player', 'browser', self.url_browser)
        conf.add_section('notebook')
        # Save tab positions:
        conf.set('notebook', 'current_tab_visible', self.current_tab_visible)
        conf.set('notebook', 'library_tab_visible', self.library_tab_visible)
        conf.set('notebook', 'playlists_tab_visible', self.playlists_tab_visible)
        conf.set('notebook', 'streams_tab_visible', self.streams_tab_visible)
        conf.set('notebook', 'info_tab_visible', self.info_tab_visible)

        conf.set('notebook', 'current_tab_pos', self.current_tab_pos)
        conf.set('notebook', 'library_tab_pos', self.library_tab_pos)
        conf.set('notebook', 'playlists_tab_pos', self.playlists_tab_pos)
        conf.set('notebook', 'streams_tab_pos', self.streams_tab_pos)
        conf.set('notebook', 'info_tab_pos', self.info_tab_pos)
        conf.add_section('library')
        conf.set('library', 'lib_wd', self.wd)
        conf.set('library', 'lib_level', self.lib_level)
        # New format
        conf.add_section('currformat')
        conf.set('currformat', 'current', self.currentformat)
        conf.set('currformat', 'library', self.libraryformat)
        conf.set('currformat', 'title', self.titleformat)
        conf.set('currformat', 'currsong1', self.currsongformat1)
        conf.set('currformat', 'currsong2', self.currsongformat2)
        conf.add_section('streams')
        conf.set('streams', 'num_streams', len(self.stream_names))
        for i in range(len(self.stream_names)):
            conf.set('streams', 'names[' + str(i) + ']', self.stream_names[i])
            conf.set('streams', 'uris[' + str(i) + ']', self.stream_uris[i])
        conf.add_section('audioscrobbler')
        conf.set('audioscrobbler', 'use_audioscrobbler', self.as_enabled)
        conf.set('audioscrobbler', 'username', self.as_username)
        conf.set('audioscrobbler', 'password_md5', self.as_password_md5)
        conf.write(file(os.path.expanduser('~/.config/sonata/sonatarc'), 'w'))

