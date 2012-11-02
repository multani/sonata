"""
This module contains the configuration variables and implements their
initialisation, loading, and saving in a file.

Example usage:
import config
...
# XXX We shouldn't have the default values contain localised parts:
self.config = config.Config(_('Default Profile'), _("by") + " %A " +\
        _("from") + " %B")
"""
from __future__ import with_statement

import os
import ConfigParser

import consts
from library import library_set_data
from library import library_get_data
import misc


class Config:
    """This class contains the configuration variables as attributes.

    Each new variable should be initialised to its default value
    in __init__, loaded from a file in settings_load_real, and
    saved to a file in settings_save_real.

    XXX This is mostly ConfigParser plus some custom serialization work.
    """

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
        self.decorated = True
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
        self.currentformat = "%A - %T|%L"
        self.libraryformat = "%A - %T"
        self.titleformat = "[Sonata] %A - %T"
        self.currsongformat1 = "%T"
        self.currsongformat2 = currsongformat2
        # this mirrors Main.columns widths
        self.columnwidths = [325, 10]
        self.autoconnect = True

        self.stream_names = []
        self.stream_uris = []

        self.last_search_num = 0

        self.use_infofile = False
        self.infofile_path = '/tmp/xmms-info'
        self.lib_view = consts.VIEW_FILESYSTEM
        self.art_location = consts.ART_LOCATION_HOMECOVERS
        self.art_location_custom_filename = ""
        self.lyrics_location = consts.LYRICS_LOCATION_HOME

        self.tags_use_mpdpath = False

        self.url_browser = ""
        self.wd = library_set_data(path="/")

        self.info_song_expanded = True
        self.info_lyrics_expanded = True
        self.info_album_expanded = True
        self.info_song_more = False
        self.current_tab_visible = True
        self.library_tab_visible = True
        self.playlists_tab_visible = True
        self.streams_tab_visible = True
        self.info_tab_visible = True

        self.art_cache = []

        # these mirror Main.notebook tab nums
        self.current_tab_pos = 0
        self.library_tab_pos = 1
        self.playlists_tab_pos = 2
        self.streams_tab_pos = 3
        self.info_tab_pos = 4

        self.info_art_enlarged = False

        self.existing_playlist_option = 0

        self.traytips_notifications_location = 0

        # Plugin state
        self.autostart_plugins = []
        self.known_plugins = []

        # Local consts
        self.LIB_NODATA = "!NONE!"

    def settings_load_real(self):
        """Load configuration from file"""
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
            self.musicdir[0] = misc.sanitize_musicdir(conf.get('connection',
                                                               'musicdir'))
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
        if conf.has_option('player', 'decorated'):
            self.decorated = conf.getboolean('player', 'decorated')
        if conf.has_option('player', 'notification'):
            self.show_notification = conf.getboolean('player', 'notification')
        if conf.has_option('player', 'popup_time'):
            self.popup_option = conf.getint('player', 'popup_time')
        if conf.has_option('player', 'update_on_start'):
            self.update_on_start = conf.getboolean('player', 'update_on_start')
        if conf.has_option('player', 'notif_location'):
            self.traytips_notifications_location = conf.getint('player',
                                                              'notif_location')
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
        if conf.has_option('player', 'search_num'):
            self.last_search_num = conf.getint('player', 'search_num')
        if conf.has_option('player', 'art_location'):
            self.art_location = conf.getint('player', 'art_location')
        if conf.has_option('player', 'art_location_custom_filename'):
            self.art_location_custom_filename = conf.get('player',
                                                'art_location_custom_filename')
        if conf.has_option('player', 'lyrics_location'):
            self.lyrics_location = conf.getint('player', 'lyrics_location')
        if conf.has_option('player', 'info_song_expanded'):
            self.info_song_expanded = conf.getboolean('player',
                                                      'info_song_expanded')
        if conf.has_option('player', 'info_lyrics_expanded'):
            self.info_lyrics_expanded = conf.getboolean('player',
                                                        'info_lyrics_expanded')
        if conf.has_option('player', 'info_album_expanded'):
            self.info_album_expanded = conf.getboolean('player',
                                                       'info_album_expanded')
        if conf.has_option('player', 'info_song_more'):
            self.info_song_more = conf.getboolean('player', 'info_song_more')
        if conf.has_option('player', 'columnwidths'):
            self.columnwidths = [int(col) for col in conf.get('player',
                                                    'columnwidths').split(",")]
        if conf.has_option('player', 'show_header'):
            self.show_header = conf.getboolean('player', 'show_header')
        if conf.has_option('player', 'tabs_expanded'):
            self.tabs_expanded = conf.getboolean('player', 'tabs_expanded')
        if conf.has_option('player', 'browser'):
            self.url_browser = conf.get('player', 'browser')
        if conf.has_option('player', 'info_art_enlarged'):
            self.info_art_enlarged = conf.getboolean('player',
                                                     'info_art_enlarged')
        if conf.has_option('player', 'existing_playlist'):
            self.existing_playlist_option = conf.getint('player',
                                                        'existing_playlist')

        if conf.has_section('notebook'):
            if conf.has_option('notebook', 'current_tab_visible'):
                self.current_tab_visible = conf.getboolean('notebook',
                                                        'current_tab_visible')
            if conf.has_option('notebook', 'library_tab_visible'):
                self.library_tab_visible = conf.getboolean('notebook',
                                                        'library_tab_visible')
            if conf.has_option('notebook', 'playlists_tab_visible'):
                self.playlists_tab_visible = conf.getboolean('notebook',
                                                    'playlists_tab_visible')
            if conf.has_option('notebook', 'streams_tab_visible'):
                self.streams_tab_visible = conf.getboolean('notebook',
                                                        'streams_tab_visible')
            if conf.has_option('notebook', 'info_tab_visible'):
                self.info_tab_visible = conf.getboolean('notebook',
                                                        'info_tab_visible')
            if conf.has_option('notebook', 'current_tab_pos'):
                try:
                    self.current_tab_pos = conf.getint('notebook',
                                                        'current_tab_pos')
                except:
                    pass
            if conf.has_option('notebook', 'library_tab_pos'):
                try:
                    self.library_tab_pos = conf.getint('notebook',
                                                        'library_tab_pos')
                except:
                    pass
            if conf.has_option('notebook', 'playlists_tab_pos'):
                try:
                    self.playlists_tab_pos = conf.getint('notebook',
                                                          'playlists_tab_pos')
                except:
                    pass
            if conf.has_option('notebook', 'streams_tab_pos'):
                try:
                    self.streams_tab_pos = conf.getint('notebook',
                                                        'streams_tab_pos')
                except:
                    pass
            if conf.has_option('notebook', 'info_tab_pos'):
                try:
                    self.info_tab_pos = conf.getint('notebook', 'info_tab_pos')
                except:
                    pass

        if conf.has_section('library'):
            album = None
            artist = None
            genre = None
            year = None
            path = None
            if conf.has_option('library', 'lib_view'):
                self.lib_view = conf.getint('library', 'lib_view')
            if conf.has_option('library', 'lib_album'):
                album = conf.get('library', 'lib_album')
            if conf.has_option('library', 'lib_artist'):
                artist = conf.get('library', 'lib_artist')
            if conf.has_option('library', 'lib_genre'):
                genre = conf.get('library', 'lib_genre')
            if conf.has_option('library', 'lib_year'):
                year = conf.get('library', 'lib_year')
            if conf.has_option('library', 'lib_path'):
                path = conf.get('library', 'lib_path')
            if album == self.LIB_NODATA:
                album = None
            if artist == self.LIB_NODATA:
                artist = None
            if genre == self.LIB_NODATA:
                genre = None
            if year == self.LIB_NODATA:
                year = None
            if path == self.LIB_NODATA:
                path = None
            self.wd = library_set_data(album=album, artist=artist, genre=genre,
                                       year=year, path=path)

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

        if conf.has_section('tags'):
            if conf.has_option('tags', 'use_mpdpaths'):
                self.tags_use_mpdpath = conf.getboolean('tags', 'use_mpdpaths')

        if conf.has_option('streams', 'num_streams'):
            num_streams = conf.getint('streams', 'num_streams')
            self.stream_names = []
            self.stream_uris = []
            for i in range(num_streams):
                self.stream_names.append(conf.get('streams', 'names[' + \
                                                  str(i) + ']'))
                self.stream_uris.append(conf.get('streams', 'uris[' + \
                                                 str(i) + ']'))
        if conf.has_option('profiles', 'num_profiles'):
            num_profiles = conf.getint('profiles', 'num_profiles')
            if num_profiles > 0:
                self.profile_names = []
                self.host = []
                self.port = []
                self.password = []
                self.musicdir = []
            for i in range(num_profiles):
                self.profile_names.append(conf.get('profiles',
                                                   'names[' + str(i) + ']'))
                self.host.append(conf.get('profiles', 'hosts[' + str(i) + ']'))
                self.port.append(conf.getint('profiles',
                                             'ports[' + str(i) + ']'))
                self.password.append(conf.get('profiles',
                                              'passwords[' + str(i) + ']'))
                self.musicdir.append(misc.sanitize_musicdir(conf.get(
                    'profiles', 'musicdirs[%s]' % i)))
            # Ensure we have a valid profile number:
            self.profile_num = max(0, min(self.profile_num, num_profiles-1))

        if conf.has_section('plugins'):
            if conf.has_option('plugins', 'autostart_plugins'):
                self.autostart_plugins = conf.get('plugins',
                                                'autostart_plugins').split(',')
                self.autostart_plugins = [x.strip("[]' ") \
                                          for x in self.autostart_plugins]
            if conf.has_option('plugins', 'known_plugins'):
                self.known_plugins = conf.get('plugins',
                                              'known_plugins').split(',')
                self.known_plugins = [x.strip("[]' ") \
                                      for x in self.known_plugins]

    def settings_save_real(self):
        """Save configuration in file"""
        conf = ConfigParser.ConfigParser()

        conf.add_section('profiles')
        conf.set('profiles', 'num_profiles', len(self.profile_names))
        for (i, (name, host, port, password, musicdir)) in \
                enumerate(zip(self.profile_names, self.host,
                              self.port, self.password, self.musicdir)):
            conf.set('profiles', 'names[%s]' % i, name)
            conf.set('profiles', 'hosts[%s]' % i, host)
            conf.set('profiles', 'ports[%s]' % i, port)
            conf.set('profiles', 'passwords[%s]' % i, password)
            conf.set('profiles', 'musicdirs[%s]' % i, musicdir)
        conf.add_section('connection')
        conf.set('connection', 'auto', self.autoconnect)
        conf.set('connection', 'profile_num', self.profile_num)

        conf.add_section('player')
        attributes = ['w',
                'h',
                'x',
                'y',
                'expanded',
                'withdrawn',
                'screen',
                'covers_type',
                'stop_on_exit',
                'initial_run',
                'sticky',
                'ontop',
                'decorated',
                'update_on_start',
                'xfade',
                'xfade_enabled',
                'covers_pref',
                'use_infofile',
                'infofile_path',
                'infofile_path',
                'art_location',
                'art_location_custom_filename',
                'lyrics_location',
                'info_song_expanded',
                'info_lyrics_expanded',
                'info_album_expanded',
                'info_song_more',
                'info_art_enlarged',
                'show_header',
                'tabs_expanded']

        for attribute in attributes:
            conf.set('player', attribute, getattr(self, attribute))

        conf.set('player', 'covers', self.show_covers)
        conf.set('player', 'minimize', self.minimize_to_systray)
        conf.set('player', 'statusbar', self.show_statusbar)
        conf.set('player', 'lyrics', self.show_lyrics)
        conf.set('player', 'notification', self.show_notification)
        conf.set('player', 'popup_time', self.popup_option)
        conf.set('player', 'notif_location',
                 self.traytips_notifications_location)
        conf.set('player', 'playback', self.show_playback)
        conf.set('player', 'progressbar', self.show_progress)
        conf.set('player', 'trayicon', self.show_trayicon)
        conf.set('player', 'search_num', self.last_search_num)
        conf.set('player', 'existing_playlist', self.existing_playlist_option)
        conf.set('player', 'browser', self.url_browser)

        columnwidths = ",".join(str(w) for w in self.columnwidths)
        conf.set('player', 'columnwidths', columnwidths)


        # Save tab positions and visibility:
        conf.add_section('notebook')
        attributes = ['current_tab_visible',
                'library_tab_visible',
                'playlists_tab_visible',
                'streams_tab_visible',
                'info_tab_visible',
                'current_tab_pos',
                'library_tab_pos',
                'playlists_tab_pos',
                'streams_tab_pos',
                'info_tab_pos']

        for attribute in attributes:
            conf.set('notebook', attribute, getattr(self, attribute))

        # Save current library browsing state:
        album = library_get_data(self.wd, 'album')
        artist = library_get_data(self.wd, 'artist')
        genre = library_get_data(self.wd, 'genre')
        year = library_get_data(self.wd, 'year')
        path = library_get_data(self.wd, 'path')
        if album is None:
            album = self.LIB_NODATA
        if artist is None:
            artist = self.LIB_NODATA
        if genre is None:
            genre = self.LIB_NODATA
        if year is None:
            year = self.LIB_NODATA
        if path is None:
            path = self.LIB_NODATA
        conf.add_section('library')
        conf.set('library', 'lib_album', album)
        conf.set('library', 'lib_artist', artist)
        conf.set('library', 'lib_genre', genre)
        conf.set('library', 'lib_year', year)
        conf.set('library', 'lib_path', path)
        conf.set('library', 'lib_view', self.lib_view)

        # Save formats for current playlist, library, etc:
        conf.add_section('currformat')
        conf.set('currformat', 'current', self.currentformat)
        conf.set('currformat', 'library', self.libraryformat)
        conf.set('currformat', 'title', self.titleformat)
        conf.set('currformat', 'currsong1', self.currsongformat1)
        conf.set('currformat', 'currsong2', self.currsongformat2)

        # Save streams:
        conf.add_section('streams')
        conf.set('streams', 'num_streams', len(self.stream_names))
        for (i, (stream, stream_uri)) in enumerate(zip(self.stream_names,
                                                       self.stream_uris)):
            conf.set('streams', 'names[%s]' % i, stream)
            conf.set('streams', 'uris[%s]' % i, stream_uri)

        # Tag editor
        conf.add_section('tags')
        conf.set('tags', 'use_mpdpaths', self.tags_use_mpdpath)

        # Enabled plugins list
        conf.add_section('plugins')
        conf.set('plugins', 'autostart_plugins',
             ','.join(self.autostart_plugins))
        conf.set('plugins', 'known_plugins',
             ','.join(self.known_plugins))

        try:
            with open(os.path.expanduser('~/.config/sonata/sonatarc'), 'w')\
                    as rc:
                conf.write(rc)
        except IOError:
            pass
