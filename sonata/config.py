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

import logging
import os
import hashlib
from configparser import RawConfigParser

from sonata import misc, consts
from sonata.song import SongRecord

# Constant to express a None value
LIB_NODATA = "!NONE!"

logger = logging.getLogger(__name__)


class ConfigParser(RawConfigParser):
    """Override the default configuration parser with specific loader"""

    def getlist(self, section, name, sep=","):
        """Get a list of values, separated by `sep`"""
        value = self.get(section, name)
        return [v.strip() for v in value.split(sep)]

    def getlistint(self, section, name, sep=","):
        """Load a list of integer values, separated by `sep`."""
        return [int(v) for v in self.getlist(section, name, sep)]


class Serializer:
    """Helper to serialize specific values.

    Those methods can be function, but it makes easier to locate and load them
    if they are stored here."""

    @staticmethod
    def list(value, sep=","):
        return ",".join(str(s) for s in value)
    listint = list


class Config:
    """This class contains the configuration variables as attributes.

    Each new variable should be initialised to its default value
    in __init__, loaded from a file in settings_load_real, and
    saved to a file in settings_save_real.

    XXX This is mostly ConfigParser plus some custom serialization work.
    """

    CONFIG_PATH = os.path.expanduser('~/.config/sonata/sonatarc')

    def __init__(self, default_profile_name, currsongformat2):
        self.wd = SongRecord(path="/")

        self._options = {
            'audioscrobbler': {
                'as_enabled': ('use_audioscrobbler', 'boolean', False),
                'as_password_md5': ('password_md5', '', ''),
                'as_username': ('username', '', '')},
            'connection': {
                'autoconnect': ('auto', 'boolean', True),
                'profile_num': ('profile_num', 'int', 0)},
            'currformat': {
                'currentformat': ('current', '', '%A - %T|%L'),
                'currsongformat1': ('currsong1', '', '%T'),
                'currsongformat2': ('currsong2', '', currsongformat2),
                'libraryformat': ('library', '', '%A - %T'),
                'titleformat': ('title', '', '[Sonata] %A - %T')},
            'library': {
                'lib_view': ('lib_view', 'int', consts.VIEW_FILESYSTEM)},
            'notebook': {
                'current_tab_pos': ('current_tab_pos', 'int', 0),
                'current_tab_visible': ('current_tab_visible', 'boolean', True),
                'info_tab_pos': ('info_tab_pos', 'int', 4),
                'info_tab_visible': ('info_tab_visible', 'boolean', True),
                'library_tab_pos': ('library_tab_pos', 'int', 1),
                'library_tab_visible': ('library_tab_visible', 'boolean', True),
                'playlists_tab_pos': ('playlists_tab_pos', 'int', 2),
                'playlists_tab_visible': ('playlists_tab_visible', 'boolean', True),
                'streams_tab_pos': ('streams_tab_pos', 'int', 3),
                'streams_tab_visible': ('streams_tab_visible', 'boolean', True)},
            'player': {
                'art_location': ('art_location', 'int', consts.ART_LOCATION_HOMECOVERS),
                'art_location_custom_filename': ('art_location_custom_filename', '', ''),
                'columnwidths': ('columnwidths', 'listint', [325, 10]),
                'covers_pref': ('covers_pref', 'int', consts.ART_LOCAL_REMOTE),
                'covers_type': ('covers_type', 'int', 1),
                'decorated': ('decorated', 'boolean', True),
                'existing_playlist_option': ('existing_playlist', 'int', 0),
                'expanded': ('expanded', 'boolean', True),
                'h': ('h', 'int', 300),
                'info_album_expanded': ('info_album_expanded', 'boolean', True),
                'info_art_enlarged': ('info_art_enlarged', 'boolean', False),
                'info_lyrics_expanded': ('info_lyrics_expanded', 'boolean', True),
                'info_song_expanded': ('info_song_expanded', 'boolean', True),
                'info_song_more': ('info_song_more', 'boolean', False),
                'infofile_path': ('infofile_path', '', '/tmp/xmms-info'),
                'initial_run': ('initial_run', 'boolean', True),
                'last_search_num': ('search_num', 'int', 0),
                'lyrics_location': ('lyrics_location', 'int', consts.LYRICS_LOCATION_HOME),
                'minimize_to_systray': ('minimize', 'boolean', False),
                'ontop': ('ontop', 'boolean', False),
                'popup_option': ('popup_time', 'int', 2),
                'screen': ('screen', 'int', 0),
                'show_covers': ('covers', 'boolean', True),
                'show_header': ('show_header', 'boolean', True),
                'show_lyrics': ('lyrics', 'boolean', True),
                'show_notification': ('notification', 'boolean', False),
                'show_playback': ('playback', 'boolean', True),
                'show_progress': ('progressbar', 'boolean', True),
                'show_statusbar': ('statusbar', 'boolean', False),
                'show_trayicon': ('trayicon', 'boolean', True),
                'sticky': ('sticky', 'boolean', False),
                'stop_on_exit': ('stop_on_exit', 'boolean', False),
                'tabs_expanded': ('tabs_expanded', 'boolean', False),
                'traytips_notifications_location': ('notif_location', 'int', 0),
                'update_on_start': ('update_on_start', 'boolean', False),
                'url_browser': ('browser', '', ''),
                'use_infofile': ('use_infofile', 'boolean', False),
                'w': ('w', 'int', 400),
                'withdrawn': ('withdrawn', 'boolean', False),
                'x': ('x', 'int', 0),
                'xfade': ('xfade', 'int', 0),
                'xfade_enabled': ('xfade_enabled', 'boolean', False),
                'y': ('y', 'int', 0)},
            'plugins': {
                'autostart_plugins': ('autostart_plugins', 'list', []),
                'known_plugins': ('known_plugins', 'list', [])},
            'tags': {
                'tags_use_mpdpath': ('use_mpdpaths', 'boolean', False)}
        }

        self._indexed_options = {
            'streams': ('num_streams', {
                'stream_names': ('names', '', []),
                'stream_uris': ('uris', '', []),
            }),
            'profiles': ('num_profiles', {
                'profile_names': ('names', '', [default_profile_name]),
                'musicdir': ('musicdirs', '', ["~/music"]),
                'host': ('hosts', '', ['localhost']),
                'port': ('ports', 'int', [6600]),
                'password': ('passwords', '', ['']),
            })
        }

    @property
    def current_musicdir(self):
        return self.musicdir[self.profile_num]

    def settings_load_real(self):
        """Load configuration from file"""

        conf = ConfigParser()
        misc.create_dir(os.path.dirname(self.CONFIG_PATH))
        conf.read(self.CONFIG_PATH)

        # Load all the "simple" options, as described in self._options, and set
        # them as instance attribute.
        for section, attributes in self._options.items():
            for attribute, (opt_key, type, default) in attributes.items():
                if conf.has_option(section, opt_key):
                    try:
                        value = getattr(conf, 'get' + type)(section, opt_key)
                    except Exception as e:
                        # BBB: we need to expect some errors since Sonata uses
                        # to write None values for "int"-type settings, which
                        # fail to be loaded when using getint(). The new code
                        # should write better values each time. Consider
                        # removing this try/except clause when configuration
                        # files are "clean".
                        value = default
                        # This should be safe in all cases
                        faulty_value = conf.get(section, opt_key)
                        logger.warning(
                            "Can't load %r from section %r (as %s). Value is %r",
                            opt_key, section, type if type else "str",
                            faulty_value)
                else:
                    value = default
                setattr(self, attribute, value)

        # Load all the attributes which have several values and are indexed.
        for section, (index_name, attributes) in self._indexed_options.items():
            if not conf.has_option(section, index_name):
                num = 0
            else:
                num = conf.getint(section, index_name)

            for attribute, (key, type, default) in attributes.items():
                if num == 0:
                    setattr(self, attribute, default)
                else:
                    setattr(self, attribute, [])

                for i in range(num):
                    opt_key = "%s[%d]" % (key, i)
                    value = getattr(conf, 'get' + type)(section, opt_key)
                    getattr(self, attribute).append(value)

        # Finally, load attributes related to the library. This is a bit weird
        # so we use an helper function to make it easier:
        def lib_get(name):
            # Helper function to load attributes related to the library.
            value = None
            if conf.has_option('library', name):
                value = conf.get('library', name)
            if value == LIB_NODATA:
                value = None
            return value

        if conf.has_section('library'):
            album  = lib_get('lib_album')
            artist = lib_get('lib_artist')
            genre  = lib_get('lib_genre')
            year   = lib_get('lib_year')
            path   = lib_get('lib_path')
            self.wd = SongRecord(album, artist, genre, year, path)

        # Finally, patch some values:
        self.musicdir = [misc.sanitize_musicdir(v) for v in self.musicdir]
        # Ensure we have a valid profile number:
        self.profile_num = max(0, min(self.profile_num,
                                      len(self.profile_names) - 1))

        # Specifying remote artwork first is too confusing and probably
        # rarely used, so we're removing this option and defaulting users
        # back to the default 'local, then remote' option.
        # Backward compatibility
        if self.covers_pref > consts.ART_LOCAL_REMOTE:
            self.covers_pref = consts.ART_LOCAL_REMOTE

    def settings_save_real(self):
        """Save configuration in file"""

        conf = ConfigParser()

        # First, write all the "simple" attributes in their respective section:
        for section, attributes in self._options.items():
            if not conf.has_section(section):
                conf.add_section(section)

            for attribute, (name, type, default) in attributes.items():
                value = getattr(self, attribute)
                if hasattr(Serializer, type):
                    value = getattr(Serializer, type)(value)
                conf.set(section, name, value)

        # Then, write all the attributes which are grouped together, and index
        # them.
        for section, (index_name, attributes) in self._indexed_options.items():
            if not conf.has_section(section):
                conf.add_section(section)
            value_index = 0

            for attribute, (name, type, default) in attributes.items():
                for i, value in enumerate(getattr(self, attribute)):
                    conf.set(section, "%s[%d]" % (name, i), value)
                    value_index = i + 1

            conf.set(section, index_name, value_index)

        # Finally, save the settings related to the library. Again, we use an
        # helper function to help us to do the job:
        def lib_set(name):
            value = getattr(self.wd, name)
            conf.set('library', 'lib_' + name,
                     value if value is not None else LIB_NODATA)

        if not conf.has_section('library'):
            conf.add_section('library')
        lib_set('album')
        lib_set('artist')
        lib_set('genre')
        lib_set('year')
        lib_set('path')

        # Now, we can properly save the configuration file:
        try:
            with open(self.CONFIG_PATH, 'w', encoding="utf-8") as rc:
                conf.write(rc)
        except IOError as e:
            self.logger.warning("Couldn't write configuration into %r: %s",
                                self.CONFIG_PATH, e)
