Sonata, an elegant GTK+ client for the Music Player Daemon (MPD)
================================================================

Copyright 2006-2009 Scott Horowitz <stonecrest@gmail.com>

Thanks to Andrew Conkling et al, for all their hard work on Pygmy!
Sonata started as a fork of the Pygmy project and is licensed under the GPLv3.

FEATURES:
    + Expanded and collapsed views, fullscreen album art mode
    + Automatic remote and local album art
    + Library browsing by folders, or by genre/artist/album
    + User-configurable columns
    + Automatic fetching of lyrics
    + Playlist and stream support
    + Support for editing song tags
    + Drag-and-drop to copy files
    + Popup notification
    + Library and playlist searching, filter as you type
    + Audioscrobbler (last.fm) 1.2 support
    + Multiple MPD profiles
    + Keyboard friendly
    + Support for multimedia keys
    + Commandline control
    + Available in 24 languages

RUNNING:
    Sonata can be run from source without installation. Simply
    run './run-sonata' as your user.

DOCUMENTATION/FAQ:
    http://sonata.berlios.de/documentation.html

REQUIREMENTS:
    (Required) Python 3.2 or newer
    (Required) Python GObject Introspection 3.2 or newer
    (Required) GTK 3.4 or newer
    (Required) python-mpd 0.4.4 or newer
    (Required) MPD 0.15 or newer, possibly on another computer
    (Optional) taglib and tagpy for editing metadata
    (Optional) dbus-python for multimedia keys, single instance support

INSTALLATION:
    Run 'python3 setup.py install' as root.

DEVELOPERS:
    Jonathan Ballet <jon+sonata@multani.info>

PAST DEVELOPERS
    Scott Horowitz <stonecrest@gmail.com>
    Tuukka Hastrup <Tuukka.Hastrup@iki.fi>
    Stephen Boyd <bebarino@gmail.com>
