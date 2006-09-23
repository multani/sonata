#!/usr/bin/env python

# $HeadURL: http://svn.berlios.de/svnroot/repos/sonata/trunk/sonata.py $
# $Id: mirage.py 141 2006-09-11 04:51:07Z stonecrest $

__version__ = "0.7"

__license__ = """
Sonata, a simple GTK+ client for the Music Player Daemon
Copyright 2006 Scott Horowitz <stonecrest@gmail.com>

This file is part of Sonata.

Sonata is free software; you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation; either version 2 of the License, or
(at your option) any later version.

Sonata is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with Sonata; if not, write to the Free Software
Foundation, Inc., 51 Franklin St, Fifth Floor, Boston, MA  02110-1301  USA
"""

import sys
import os
import gobject
import ConfigParser
import urllib, urllib2, httplib
import time
import socket
import string
import gc
import subprocess
import gettext
import locale
import shutil
import mmkeys
import sys, getopt

try:
    import cPickle as pickle
except ImportError:
    import pickle

try:
    import gtk
    import pango
    import mpdclient3
except ImportError, (strerror):
    print >>sys.stderr, "%s.  Please make sure you have this library installed into a directory in Python's path or in the same directory as Sonata.\n" % strerror
    sys.exit(1)

try:
    # We'll make the system tray functionality optional...
    import egg.trayicon
    HAVE_EGG = True
except ImportError:
    # so we'll pass on any errors in loading it
    HAVE_EGG = False
    pass

try:
    import dbus
    import dbus.service
    if getattr(dbus, "version", (0,0,0)) >= (0,41,0):
        import dbus.glib
    HAVE_DBUS = True
except:
    HAVE_DBUS = False

# Test pygtk version
if gtk.pygtk_version < (2, 6, 0):
    sys.stderr.write("Sonata requires PyGTK 2.6.0 or newer.\n")
    sys.exit(1)

class Connection(mpdclient3.mpd_connection):
    """A connection to the daemon. Will use MPD_HOST/MPD_PORT in preference to the supplied config if available."""

    def __init__(self, Base):
        """Open a connection using the host/port values from the provided config. If conf is None, an empty object will be returned, suitable for comparing != to any other connection."""
        host = Base.host
        port = Base.port
        password = Base.password

        if os.environ.has_key('MPD_HOST'):
            if '@' in os.environ['MPD_HOST']:
                password, host = os.environ['MPD_HOST'].split('@')
            else:
                host = os.environ['MPD_HOST']
        if os.environ.has_key('MPD_PORT'):
            port = int(os.environ['MPD_PORT'])

        mpdclient3.mpd_connection.__init__(self, host, port, password)
        mpdclient3.connect(host=host, port=port, password=password)

    #def __repr__(self, host, port):
    #	if password:
    #		return "<Connection to %s:%s, using password>" % (host, port)
    #	else:
    #		return "<Connection to %s:%s>" % (host, port)

class Base(mpdclient3.mpd_connection):
    def __init__(self):

        try:
            gettext.install('sonata', '/usr/share/locale', unicode=1)
        except:
            gettext.install('sonata', '/usr/local/share/locale', unicode=1)

        toggle_arg = False
        # Read any passed options/arguments:
        try:
            opts, args = getopt.getopt(sys.argv[1:], "tv", ["toggle", "version"])
        except getopt.GetoptError:
            # print help information and exit:
            self.print_usage()
            sys.exit(2)
        # If options were passed, perform action on them.
        if opts != []:
            for o, a in opts:
                if o in ("-t", "--toggle"):
                    toggle_arg = True
                    if not HAVE_DBUS:
                        print _("The toggle argument requires D-Bus. Aborting.")
                        self.print_usage()
                        sys.exit(2)
                elif o in ("-v", "--version"):
                    self.print_version()
                    sys.exit(2)
                else:
                    self.print_usage()
                    sys.exit(2)

        start_dbus_interface(toggle_arg)

        # Initialize vars:
        self.host = 'localhost'
        self.port = 6600
        self.password = ''
        self.x = 0
        self.y = 0
        self.w = 400
        self.h = 300
        self.expanded = True
        self.visible = True
        self.withdrawn = False
        self.sticky = False
        self.ontop = False
        self.screen = 0
        self.prevconn = []
        self.prevstatus = None
        self.prevsonginfo = None
        self.lastalbumart = None
        self.repeat = False
        self.shuffle = False
        self.show_covers = True
        self.show_volume = True
        self.stop_on_exit = False
        self.minimize_to_systray = False
        self.exit_now = False
        self.ignore_toggle_signal = False
        self.initial_run = True
        show_prefs = False
        # If the connection to MPD times out, this will cause the
        # interface to freeze while the socket.connect() calls
        # are repeatedly executed. Therefore, if we were not
        # able to make a connection, slow down the iteration
        # check to once every 15 seconds.
        # Eventually we'd like to ues non-blocking sockets in
        # mpdclient3.py
        self.iterate_time_when_connected = 1000
        self.iterate_time_when_disconnected = 15000

        # Load config:
        conf = ConfigParser.ConfigParser()
        if os.path.exists(os.path.expanduser('~/.config/')) == False:
            os.mkdir(os.path.expanduser('~/.config/'))
        if os.path.exists(os.path.expanduser('~/.config/sonata/')) == False:
            os.mkdir(os.path.expanduser('~/.config/sonata/'))
        if os.path.exists(os.path.expanduser('~/.config/sonata/covers/')) == False:
            os.mkdir(os.path.expanduser('~/.config/sonata/covers'))
        if os.path.isfile(os.path.expanduser('~/.config/sonata/sonatarc')):
            conf.read(os.path.expanduser('~/.config/sonata/sonatarc'))
        elif os.path.isfile(os.path.expanduser('~/.sonatarc')):
            conf.read(os.path.expanduser('~/.sonatarc'))
            os.remove(os.path.expanduser('~/.sonatarc'))
        try:
            self.host = conf.get('connection', 'host')
            self.port = int(conf.get('connection', 'port'))
            self.password = conf.get('connection', 'password')
            self.x = conf.getint('player', 'x')
            self.y = conf.getint('player', 'y')
            self.w = conf.getint('player', 'w')
            self.h = conf.getint('player', 'h')
            self.expanded = conf.getboolean('player', 'expanded')
            self.withdrawn = conf.getboolean('player', 'withdrawn')
            self.screen = conf.getint('player', 'screen')
            self.repeat = conf.getboolean('player', 'repeat')
            self.shuffle = conf.getboolean('player', 'shuffle')
            self.show_covers = conf.getboolean('player', 'covers')
            self.stop_on_exit = conf.getboolean('player', 'stop_on_exit')
            self.minimize_to_systray = conf.getboolean('player', 'minimize')
            self.initial_run = conf.getboolean('player', 'initial_run')
            self.show_volume = conf.getboolean('player', 'volume')
            self.sticky = conf.getboolean('player', 'sticky')
            self.ontop = conf.getboolean('player', 'ontop')
        except:
            pass

        # Popup menus:
        actions = (
            ('chooseimage_menu', gtk.STOCK_CONVERT, _('Use _Remote Image...'), None, None, self.choose_image),
            ('localimage_menu', gtk.STOCK_OPEN, _('Use _Local Image...'), None, None, self.choose_image_local),
            ('playmenu', gtk.STOCK_MEDIA_PLAY, _('_Play'), None, None, self.pp),
            ('pausemenu', gtk.STOCK_MEDIA_PAUSE, _('_Pause'), None, None, self.pp),
            ('stopmenu', gtk.STOCK_MEDIA_STOP, _('_Stop'), None, None, self.stop),
            ('prevmenu', gtk.STOCK_MEDIA_PREVIOUS, _('_Previous'), None, None, self.prev),
            ('nextmenu', gtk.STOCK_MEDIA_NEXT, _('_Next'), None, None, self.next),
            ('quitmenu', gtk.STOCK_QUIT, _('_Quit'), None, None, self.delete_event_yes),
            ('removemenu', gtk.STOCK_REMOVE, _('_Remove'), None, None, self.remove),
            ('clearmenu', gtk.STOCK_CLEAR, _('_Clear'), '<Ctrl>c', None, self.clear),
            ('savemenu', gtk.STOCK_SAVE, _('_Save Playlist...'), '<Ctrl>s', None, self.save_playlist),
            ('updatemenu', gtk.STOCK_REFRESH, _('_Update Library'), None, None, self.updatedb),
            ('preferencemenu', gtk.STOCK_PREFERENCES, _('_Preferences...'), None, None, self.prefs),
            ('helpmenu', gtk.STOCK_HELP, _('_Help'), None, None, self.help),
            ('addmenu', gtk.STOCK_ADD, _('_Add'), 'space', None, self.add_item),
            ('replacemenu', gtk.STOCK_REDO, _('_Replace'), '<Ctrl>r', None, self.replace_item),
            ('rmmenu', gtk.STOCK_DELETE, _('_Delete'), None, None, self.remove),
            ('currentkey', None, 'Current Playlist Key', '<Alt>1', None, self.switch_to_current),
            ('librarykey', None, 'Library Key', '<Alt>2', None, self.switch_to_library),
            ('playlistskey', None, 'Playlists Key', '<Alt>3', None, self.switch_to_playlists),
            ('expandkey', None, 'Expand Key', '<Alt>Down', None, self.expand),
            ('collapsekey', None, 'Collapse Key', '<Alt>Up', None, self.collapse),
            ('ppkey', None, 'Play/Pause Key', '<Ctrl>p', None, self.pp),
            ('stopkey', None, 'Stop Key', '<Ctrl>s', None, self.stop),
            ('prevkey', None, 'Previous Key', '<Ctrl>Left', None, self.prev),
            ('nextkey', None, 'Next Key', '<Ctrl>Right', None, self.next),
            ('lowerkey', None, 'Lower Volume Key', '<Ctrl>minus', None, self.lower_volume),
            ('raisekey', None, 'Raise Volume Key', '<Ctrl>plus', None, self.raise_volume),
            ('raisekey2', None, 'Raise Volume Key 2', '<Ctrl>equal', None, self.raise_volume),
            ('quitkey', None, 'Quit Key', '<Ctrl>q', None, self.delete_event_yes),
            ('menukey', None, 'Menu Key', 'Menu', None, self.menukey_press),
            ('deletekey', None, 'Delete Key', 'Delete', None, self.remove),
            ('updatekey', None, 'Update Key', '<Ctrl>u', None, self.updatedb),
            ('updatekey2', None, 'Update Key 2', '<Ctrl><Shift>u', None, self.updatedb_path),
            ('parentdirkey', None, 'Parent Dir Key', 'BackSpace', None, self.parent_dir),
            ('hidewinkey', None, 'Hide Window Key', 'Escape', None, self.withdraw_app)
            )

        toggle_actions = (
            ('showmenu', None, _('_Show Player'), None, None, self.withdraw_app_toggle, not self.withdrawn),
            ('repeatmenu', None, _('_Repeat'), None, None, self.repeat_now, self.repeat),
            ('shufflemenu', None, _('_Shuffle'), None, None, self.shuffle_now, self.shuffle),
                )

        uiDescription = """
            <ui>
              <popup name="imagemenu">
                <menuitem action="chooseimage_menu"/>
                <menuitem action="localimage_menu"/>
              </popup>
              <popup name="traymenu">
                <menuitem action="showmenu"/>
                <separator name="FM1"/>
                <menuitem action="playmenu"/>
                <menuitem action="pausemenu"/>
                <menuitem action="stopmenu"/>
                <menuitem action="prevmenu"/>
                <menuitem action="nextmenu"/>
                <separator name="FM2"/>
                <menuitem action="quitmenu"/>
              </popup>
              <popup name="mainmenu">
                <menuitem action="addmenu"/>
                <menuitem action="replacemenu"/>
                <menuitem action="removemenu"/>
                <menuitem action="clearmenu"/>
                <menuitem action="savemenu"/>
                <menuitem action="rmmenu"/>
                <menuitem action="updatemenu"/>
                <separator name="FM1"/>
                <menuitem action="repeatmenu"/>
                <menuitem action="shufflemenu"/>
                <separator name="FM2"/>
                <menuitem action="preferencemenu"/>
                <menuitem action="helpmenu"/>
              </popup>
              <popup name="hidden">
                <menuitem action="quitkey"/>
                <menuitem action="currentkey"/>
                <menuitem action="librarykey"/>
                <menuitem action="playlistskey"/>
                <menuitem action="expandkey"/>
                <menuitem action="collapsekey"/>
                <menuitem action="ppkey"/>
                <menuitem action="stopkey"/>
                <menuitem action="nextkey"/>
                <menuitem action="prevkey"/>
                <menuitem action="lowerkey"/>
                <menuitem action="raisekey"/>
                <menuitem action="raisekey2"/>
                <menuitem action="menukey"/>
                <menuitem action="deletekey"/>
                <menuitem action="updatekey"/>
                <menuitem action="updatekey2"/>
                <menuitem action="parentdirkey"/>
                <menuitem action="hidewinkey"/>
              </popup>
            </ui>
            """

        # Try to connect to MPD:
        self.conn = self.connect()
        if self.conn:
            self.conn.do.password(self.password)
            self.iterate_time = self.iterate_time_when_connected
            self.status = self.conn.do.status()
            try:
                test = self.status.state
            except:
                self.status = None
            try:
                self.songinfo = self.conn.do.currentsong()
            except:
                self.songinfo = None
        else:
            if self.initial_run:
                show_prefs = True
            self.iterate_time = self.iterate_time_when_disconnected
            self.status = None
            self.songinfo = None

        # Add some icons:
        self.iconfactory = gtk.IconFactory()
        self.sonataset = gtk.IconSet()
        sonataicon = 'sonata.png'
        if os.path.exists(os.path.join(sys.prefix, 'share', 'pixmaps', sonataicon)):
            filename1 = [os.path.join(sys.prefix, 'share', 'pixmaps', sonataicon)]
        elif os.path.exists(os.path.join(os.path.split(__file__)[0], sonataicon)):
            filename1 = [os.path.join(os.path.split(__file__)[0], sonataicon)]
        self.icons1 = [gtk.IconSource() for i in filename1]
        for i, iconsource in enumerate(self.icons1):
            iconsource.set_filename(filename1[i])
            self.sonataset.add_source(iconsource)
        self.iconfactory.add('sonata', self.sonataset)
        self.iconfactory.add_default()

        # Main app:
        self.window = gtk.Window(gtk.WINDOW_TOPLEVEL)
        self.window.set_title('Sonata')
        self.window.set_resizable(True)
        if self.ontop:
            self.window.set_keep_above(True)
        if self.sticky:
            self.window.stick()
        self.tooltips = gtk.Tooltips()
        self.UIManager = gtk.UIManager()
        actionGroup = gtk.ActionGroup('Actions')
        actionGroup.add_actions(actions)
        actionGroup.add_toggle_actions(toggle_actions)
        self.UIManager.insert_action_group(actionGroup, 0)
        self.UIManager.add_ui_from_string(uiDescription)
        self.window.add_accel_group(self.UIManager.get_accel_group())
        mainhbox = gtk.HBox()
        mainvbox = gtk.VBox()
        tophbox = gtk.HBox()
        self.imageeventbox = gtk.EventBox()
        self.albumimage = gtk.Image()
        self.imageeventbox.add(self.albumimage)
        if not self.show_covers:
            self.imageeventbox.set_no_show_all(True)
            self.imageeventbox.hide()
        tophbox.pack_start(self.imageeventbox, False, False, 5)
        topvbox = gtk.VBox()
        toptophbox = gtk.HBox()
        self.prevbutton = gtk.Button("", gtk.STOCK_MEDIA_PREVIOUS, True)
        self.prevbutton.set_relief(gtk.RELIEF_NONE)
        self.prevbutton.set_property('can-focus', False)
        image, label = self.prevbutton.get_children()[0].get_children()[0].get_children()
        label.set_text('')
        toptophbox.pack_start(self.prevbutton, False, False, 0)
        self.ppbutton = gtk.Button("", gtk.STOCK_MEDIA_PLAY, True)
        self.ppbutton.set_relief(gtk.RELIEF_NONE)
        self.ppbutton.set_property('can-focus', False)
        image, label = self.ppbutton.get_children()[0].get_children()[0].get_children()
        label.set_text('')
        toptophbox.pack_start(self.ppbutton, False, False, 0)
        self.stopbutton = gtk.Button("", gtk.STOCK_MEDIA_STOP, True)
        self.stopbutton.set_relief(gtk.RELIEF_NONE)
        self.stopbutton.set_property('can-focus', False)
        image, label = self.stopbutton.get_children()[0].get_children()[0].get_children()
        label.set_text('')
        toptophbox.pack_start(self.stopbutton, False, False, 0)
        self.nextbutton = gtk.Button("", gtk.STOCK_MEDIA_NEXT, True)
        self.nextbutton.set_relief(gtk.RELIEF_NONE)
        self.nextbutton.set_property('can-focus', False)
        image, label = self.nextbutton.get_children()[0].get_children()[0].get_children()
        label.set_text('')
        toptophbox.pack_start(self.nextbutton, False, False, 0)
        progressbox = gtk.VBox()
        self.progresslabel = gtk.Label()
        self.progresslabel.set_markup('<span size="10"> </span>')
        progressbox.pack_start(self.progresslabel)
        self.progresseventbox = gtk.EventBox()
        self.progressbar = gtk.ProgressBar()
        self.progressbar.set_orientation(gtk.PROGRESS_LEFT_TO_RIGHT)
        self.progressbar.set_fraction(0)
        self.progressbar.set_pulse_step(0.05)
        self.progressbar.set_ellipsize(pango.ELLIPSIZE_NONE)
        self.progresseventbox.add(self.progressbar)
        progressbox.pack_start(self.progresseventbox, False, False, 0)
        self.progresslabel2 = gtk.Label()
        self.progresslabel2.set_markup('<span size="10"> </span>')
        progressbox.pack_start(self.progresslabel2)
        toptophbox.pack_start(progressbox, True, True, 0)
        self.volumebutton = gtk.ToggleButton("", True)
        self.volumebutton.set_relief(gtk.RELIEF_NONE)
        self.volumebutton.set_property('can-focus', False)
        if not self.show_volume:
            self.volumebutton.set_no_show_all(True)
            self.volumebutton.hide()
        toptophbox.pack_start(self.volumebutton, False, False, 0)
        topvbox.pack_start(toptophbox, False, False, 2)
        self.expander = gtk.Expander(_("Playlist"))
        self.expander.set_expanded(self.expanded)
        self.expander.set_property('can-focus', False)
        self.cursonglabel = gtk.Label()
        self.expander.set_label_widget(self.cursonglabel)
        topvbox.pack_start(self.expander, False, False, 2)
        tophbox.pack_start(topvbox, True, True, 3)
        mainvbox.pack_start(tophbox, False, False, 5)
        self.notebook = gtk.Notebook()
        self.notebook.set_tab_pos(gtk.POS_TOP)
        self.notebook.set_property('can-focus', False)
        self.expanderwindow = gtk.ScrolledWindow()
        self.expanderwindow.set_policy(gtk.POLICY_AUTOMATIC, gtk.POLICY_AUTOMATIC)
        self.expanderwindow.set_shadow_type(gtk.SHADOW_IN)
        self.current = gtk.TreeView()
        self.current.set_headers_visible(False)
        self.current.set_rules_hint(True)
        self.current.set_reorderable(True)
        self.current.set_enable_search(True)
        self.expanderwindow.add(self.current)
        playlisthbox = gtk.HBox()
        playlisthbox.pack_start(gtk.image_new_from_stock(gtk.STOCK_CDROM, gtk.ICON_SIZE_MENU), False, False, 2)
        playlisthbox.pack_start(gtk.Label(str=_("Current")), False, False, 2)
        playlisthbox.show_all()
        self.notebook.append_page(self.expanderwindow, playlisthbox)
        self.expanderwindow2 = gtk.ScrolledWindow()
        self.expanderwindow2.set_policy(gtk.POLICY_AUTOMATIC, gtk.POLICY_AUTOMATIC)
        self.expanderwindow2.set_shadow_type(gtk.SHADOW_IN)
        self.browser = gtk.TreeView()
        self.browser.set_headers_visible(False)
        self.browser.set_rules_hint(True)
        self.browser.set_reorderable(True)
        self.browser.set_enable_search(True)
        self.expanderwindow2.add(self.browser)
        libraryhbox = gtk.HBox()
        libraryhbox.pack_start(gtk.image_new_from_stock(gtk.STOCK_HARDDISK, gtk.ICON_SIZE_MENU), False, False, 2)
        libraryhbox.pack_start(gtk.Label(str=_("Library")), False, False, 2)
        libraryhbox.show_all()
        self.notebook.append_page(self.expanderwindow2, libraryhbox)
        self.expanderwindow3 = gtk.ScrolledWindow()
        self.expanderwindow3.set_policy(gtk.POLICY_AUTOMATIC, gtk.POLICY_AUTOMATIC)
        self.expanderwindow3.set_shadow_type(gtk.SHADOW_IN)
        self.playlists = gtk.TreeView()
        self.playlists.set_headers_visible(False)
        self.playlists.set_rules_hint(True)
        self.playlists.set_reorderable(True)
        self.playlists.set_enable_search(True)
        self.expanderwindow3.add(self.playlists)
        playlistshbox = gtk.HBox()
        playlistshbox.pack_start(gtk.image_new_from_stock(gtk.STOCK_JUSTIFY_FILL, gtk.ICON_SIZE_MENU), False, False, 2)
        playlistshbox.pack_start(gtk.Label(str=_("Playlists")), False, False, 2)
        playlistshbox.show_all()
        self.notebook.append_page(self.expanderwindow3, playlistshbox)
        mainvbox.pack_start(self.notebook, True, True, 5)
        mainhbox.pack_start(mainvbox, True, True, 3)
        self.window.add(mainhbox)
        self.window.move(self.x, self.y)
        self.window.set_size_request(270, -1)
        self.mainmenu = self.UIManager.get_widget('/mainmenu')
        self.shufflemenu = self.UIManager.get_widget('/mainmenu/shufflemenu')
        self.repeatmenu = self.UIManager.get_widget('/mainmenu/repeatmenu')
        self.imagemenu = self.UIManager.get_widget('/imagemenu')
        self.traymenu = self.UIManager.get_widget('/traymenu')
        if not self.expanded:
            self.notebook.set_no_show_all(True)
            self.notebook.hide()
            self.cursonglabel.set_markup('<big><b>' + _('Stopped') + '</b></big>\n<small>' + _('Click to expand') + '</small>')
            self.window.set_default_size(self.w, 1)
        else:
            self.cursonglabel.set_markup('<big><b>' + _('Stopped') + '</b></big>\n<small>' + _('Click to collapse') + '</small>')
            self.window.set_default_size(self.w, self.h)
        if not self.conn:
            self.progressbar.set_text(_('Not Connected'))
        if self.expanded:
            self.tooltips.set_tip(self.expander, _("Click to collapse the player"))
        else:
            self.tooltips.set_tip(self.expander, _("Click to expand the player"))

        # Systray:
        self.tipbox = gtk.HBox()
        innerbox = gtk.VBox()
        self.traycursonglabel = gtk.Label()
        self.traycursonglabel.set_markup(_("Playlist"))
        self.traycursonglabel.set_alignment(0, 1)
        innerbox.pack_start(self.traycursonglabel, True, True, 1)
        self.trayprogressbar = gtk.ProgressBar()
        self.trayprogressbar.set_orientation(gtk.PROGRESS_LEFT_TO_RIGHT)
        self.trayprogressbar.set_fraction(0)
        self.trayprogressbar.set_pulse_step(0.05)
        self.trayprogressbar.set_ellipsize(pango.ELLIPSIZE_NONE)
        innerbox.pack_start(self.trayprogressbar, True, True, 3)
        self.trayalbumimage = gtk.Image()
        self.trayalbumimage.set_size_request(50, 50)
        self.trayalbumimage.set_padding(5, 5)
        if not self.show_covers:
            self.trayalbumimage.set_no_show_all(True)
            self.trayalbumimage.hide()
        self.tipbox.pack_start(self.trayalbumimage, False, False, 6)
        self.tipbox.pack_start(innerbox, True, True, 6)
        self.traytips = TrayIconTips()
        self.traytips.add_widget(self.tipbox)
        self.tipbox.show_all()

        # Volumescale window_resized
        self.volumewindow = gtk.Window(gtk.WINDOW_POPUP)
        self.volumewindow.set_skip_taskbar_hint(True)
        self.volumewindow.set_skip_pager_hint(True)
        self.volumewindow.set_decorated(False)
        frame = gtk.Frame()
        frame.set_shadow_type(gtk.SHADOW_ETCHED_IN)
        self.volumewindow.add(frame)
        volbox = gtk.VBox()
        volbox.pack_start(gtk.Label("+"), False, False, 0)
        self.volumescale = gtk.VScale()
        self.volumescale.set_draw_value(True)
        self.volumescale.set_value_pos(gtk.POS_TOP)
        self.volumescale.set_digits(0)
        self.volumescale.set_update_policy(gtk.UPDATE_CONTINUOUS)
        self.volumescale.set_inverted(True)
        self.volumescale.set_adjustment(gtk.Adjustment(0, 0, 100, 0, 0, 0))
        self.volumescale.set_size_request(-1, 103)
        volbox.pack_start(self.volumescale, True, True, 0)
        volbox.pack_start(gtk.Label("-"), False, False, 0)
        frame.add(volbox)
        frame.show_all()

        # Connect to signals
        self.window.connect('delete_event', self.delete_event)
        self.window.connect('window_state_event', self.on_window_state_change)
        self.window.connect('configure_event', self.on_window_configure)
        self.imageeventbox.connect('button_press_event', self.image_activate)
        self.ppbutton.connect('clicked', self.pp)
        self.stopbutton.connect('clicked', self.stop)
        self.prevbutton.connect('clicked', self.prev)
        self.nextbutton.connect('clicked', self.next)
        self.progresseventbox.connect('button_press_event', self.progressbar_button_press_event)
        self.progresseventbox.connect('scroll_event', self.progressbar_scroll_event)
        self.volumebutton.connect('clicked', self.on_volumebutton_clicked)
        self.volumebutton.connect('scroll-event', self.on_volumebutton_scroll)
        self.expander.connect('activate', self.expander_activate)
        self.current.connect('drag_data_received', self.on_drag_drop)
        self.current.connect('row_activated', self.current_click)
        self.current.connect('button_press_event', self.current_button_press)
        self.current.connect('popup_menu', self.current_popup_menu)
        self.current.connect('drag_end', self.after_drag_drop)
        self.shufflemenu.connect('toggled', self.shuffle_now)
        self.repeatmenu.connect('toggled', self.repeat_now)
        self.volumewindow.connect('focus_out_event', self.on_volumewindow_unfocus)
        self.volumescale.connect('change_value', self.on_volumescale_change)
        self.volumescale.connect('scroll-event', self.on_volumescale_scroll)
        self.cursonglabel.connect('notify::label', self.labelnotify)
        self.progressbar.connect('notify::fraction', self.progressbarnotify_fraction)
        self.progressbar.connect('notify::text', self.progressbarnotify_text)
        self.browser.connect('row_activated', self.browserow)
        self.browser.connect('button_press_event', self.browser_button_press)
        self.playlists.connect('button_press_event', self.playlists_button_press)
        self.ppbutton.connect('button_press_event', self.popup_menu)
        self.prevbutton.connect('button_press_event', self.popup_menu)
        self.stopbutton.connect('button_press_event', self.popup_menu)
        self.nextbutton.connect('button_press_event', self.popup_menu)
        self.progresseventbox.connect('button_press_event', self.popup_menu)
        self.expander.connect('button_press_event', self.popup_menu)
        self.volumebutton.connect('button_press_event', self.popup_menu)
        self.window.add_events(gtk.gdk.BUTTON_PRESS_MASK)
        self.mainwinhandler = self.window.connect('button_press_event', self.popup_menu)

        # Connect to mmkeys signals
        self.keys = mmkeys.MmKeys()
        self.keys.connect("mm_prev", self.mmprev)
        self.keys.connect("mm_next", self.mmnext)
        self.keys.connect("mm_playpause", self.mmpp)
        self.keys.connect("mm_stop", self.mmstop)

        # Put blank cd to albumimage widget by default
        blankalbum = 'sonatacd.png'
        if os.path.exists(os.path.join(sys.prefix, 'share', 'pixmaps', blankalbum)):
            self.sonatacd = os.path.join(sys.prefix, 'share', 'pixmaps', blankalbum)
        elif os.path.exists(os.path.join(os.path.split(__file__)[0], blankalbum)):
            self.sonatacd = os.path.join(os.path.split(__file__)[0], blankalbum)
        self.albumimage.set_from_file(self.sonatacd)

        # Initialize current playlist data and widget
        self.currentdata = gtk.ListStore(int, str)
        self.current.set_model(self.currentdata)
        self.current.set_search_column(1)
        self.current.connect('drag-data-get',  self.current_data_get)
        self.currentdata.connect('row-changed',  self.current_changed)
        self.currentcell = gtk.CellRendererText()
        self.currentcolumn = gtk.TreeViewColumn('Pango Markup', self.currentcell, markup=1)
        self.currentcolumn.set_sizing(gtk.TREE_VIEW_COLUMN_FIXED)
        self.current.append_column(self.currentcolumn)
        self.current.get_selection().set_mode(gtk.SELECTION_MULTIPLE)
        self.current.enable_model_drag_source(gtk.gdk.BUTTON1_MASK, [('STRING', 0, 0)], gtk.gdk.ACTION_MOVE)
        self.current.enable_model_drag_dest([('STRING', 0, 0)], gtk.gdk.ACTION_MOVE)

        # Initialize playlist data and widget
        self.playlistsdata = gtk.ListStore(str, str)
        self.playlists.set_model(self.playlistsdata)
        self.playlists.set_search_column(1)
        self.playlistsimg = gtk.CellRendererPixbuf()
        self.playlistscell = gtk.CellRendererText()
        self.playlistscolumn = gtk.TreeViewColumn()
        self.playlistscolumn.pack_start(self.playlistsimg, False)
        self.playlistscolumn.pack_start(self.playlistscell, True)
        self.playlistscolumn.set_attributes(self.playlistsimg, stock_id=0)
        self.playlistscolumn.set_attributes(self.playlistscell, markup=1)
        self.playlists.append_column(self.playlistscolumn)
        self.playlists.get_selection().set_mode(gtk.SELECTION_MULTIPLE)

        # Initialize browser data and widget
        self.browserposition = {}
        self.browserselectedpath = {}
        self.root = '/'
        self.browser.wd = '/'
        self.prevstatus = None
        self.browserdata = gtk.ListStore(str, str, str)
        self.browser.set_model(self.browserdata)
        self.browser.set_search_column(2)
        self.browsercell = gtk.CellRendererText()
        self.browserimg = gtk.CellRendererPixbuf()
        self.browsercolumn = gtk.TreeViewColumn()
        self.browsercolumn.pack_start(self.browserimg, False)
        self.browsercolumn.pack_start(self.browsercell, True)
        self.browsercolumn.set_attributes(self.browserimg, stock_id=0)
        self.browsercolumn.set_attributes(self.browsercell, markup=2)
        self.browsercolumn.set_sizing(gtk.TREE_VIEW_COLUMN_FIXED)
        self.browser.append_column(self.browsercolumn)
        self.browser.get_selection().set_mode(gtk.SELECTION_MULTIPLE)

        icon = self.window.render_icon('sonata', gtk.ICON_SIZE_DIALOG)
        self.window.set_icon(icon)

        self.handle_change_status()
        if self.withdrawn:
            self.window.set_no_show_all(True)
            self.window.hide()
        self.window.show_all()

        if HAVE_EGG:
            self.initialize_systrayicon()

        self.iterate_now()

        self.notebook.set_no_show_all(False)
        self.window.set_no_show_all(False)
        self.notebook.connect('switch-page', self.notebook_clicked)

        if show_prefs:
            while gtk.events_pending():
                gtk.main_iteration()
            self.prefs(None, True)

        self.initial_run = False

    def print_version(self):
        print _("Version: Sonata"), __version__
        print _("Website: http://sonata.berlios.de")

    def print_usage(self):
        self.print_version()
        print ""
        print _("Usage: sonata [OPTION]")
        print ""
        print _("Options") + ":"
        print "  -h, --help           " + _("Show this help and exit")
        print "  -v, --version        " + _("Show version information and exit")
        print "  -t, --toggle         " + _("Toggles whether the app is minimized")
        print "                       " + _("to tray or visible (requires D-Bus)")

    def connect(self):
        try:
            return Connection(self)
        except (mpdclient3.socket.error, EOFError):
            return None

    def update_status(self):
        try:
            if not self.conn:
                self.conn = self.connect()
            if self.conn:
                self.iterate_time = self.iterate_time_when_connected
                self.status = self.conn.do.status()
                try:
                    test = self.status.state
                except:
                    self.status = None
                self.songinfo = self.conn.do.currentsong()
            else:
                self.iterate_time = self.iterate_time_when_disconnected
                self.status = None
                self.songinfo = None
        except (mpdclient3.socket.error, EOFError):
            self.prevconn = self.conn
            self.prevstatus = self.status
            self.prevsonginfo = self.songinfo
            self.conn = None
            self.status = None
            self.songinfo = None

    def iterate(self):
        self.update_status()

        if self.conn != self.prevconn:
            self.handle_change_conn()
        if self.status != self.prevstatus:
            self.handle_change_status()
        if self.songinfo != self.prevsonginfo:
            self.handle_change_song()

        self.prevconn = self.conn
        self.prevstatus = self.status
        self.prevsonginfo = self.songinfo

        self.iterate_handler = gobject.timeout_add(self.iterate_time, self.iterate) # Repeat ad infitum..

        if HAVE_EGG:
            if self.trayicon.get_property('visible') == False:
                self.initialize_systrayicon()

    def iterate_now(self):
        # Since self.iterate_time_when_connected has been
        # slowed down to 1second instead of 250ms, we'll
        # call self.iterate_now() whenever the user performs
        # an action that requires updating the client
        try:
            gobject.source_remove(self.iterate_handler)
        except:
            pass
        self.iterate()

    def save_settings(self):
        conf = ConfigParser.ConfigParser()
        conf.add_section('connection')
        conf.set('connection', 'host', self.host)
        conf.set('connection', 'port', self.port)
        conf.set('connection', 'password', self.password)
        conf.add_section('player')
        conf.set('player', 'w', self.w)
        conf.set('player', 'h', self.h)
        conf.set('player', 'x', self.x)
        conf.set('player', 'y', self.y)
        conf.set('player', 'expanded', self.expanded)
        conf.set('player', 'withdrawn', self.withdrawn)
        conf.set('player', 'screen', self.screen)
        conf.set('player', 'repeat', self.repeat)
        conf.set('player', 'shuffle', self.shuffle)
        conf.set('player', 'covers', self.show_covers)
        conf.set('player', 'stop_on_exit', self.stop_on_exit)
        conf.set('player', 'minimize', self.minimize_to_systray)
        conf.set('player', 'initial_run', self.initial_run)
        conf.set('player', 'volume', self.show_volume)
        conf.set('player', 'sticky', self.sticky)
        conf.set('player', 'ontop', self.ontop)
        conf.write(file(os.path.expanduser('~/.config/sonata/sonatarc'), 'w'))

    def handle_change_conn(self):
        if not self.conn:
            self.ppbutton.set_property('sensitive', False)
            self.stopbutton.set_property('sensitive', False)
            self.prevbutton.set_property('sensitive', False)
            self.nextbutton.set_property('sensitive', False)
            self.volumebutton.set_property('sensitive', False)
            self.trayimage.set_from_stock('sonata',  gtk.ICON_SIZE_BUTTON)
            self.currentdata.clear()
        else:
            self.ppbutton.set_property('sensitive', True)
            self.stopbutton.set_property('sensitive', True)
            self.prevbutton.set_property('sensitive', True)
            self.nextbutton.set_property('sensitive', True)
            self.volumebutton.set_property('sensitive', True)
            self.browse(root='/')
            self.playlists_populate()
            self.notebook_clicked(self.notebook, 0, self.notebook.get_current_page())

    def notebook_clicked(self, notebook, page, page_num):
        if page_num == 0:
            gobject.idle_add(self.give_widget_focus, self.current)
        elif page_num == 1:
            gobject.idle_add(self.give_widget_focus, self.browser)
        elif page_num == 2:
            gobject.idle_add(self.give_widget_focus, self.playlists)

    def give_widget_focus(self, widget):
        widget.grab_focus()

    def save_playlist(self, action):
        if self.conn:
            # Prompt user for playlist name:
            dialog = gtk.Dialog(_("Save Playlist"), self.window, gtk.DIALOG_MODAL | gtk.DIALOG_DESTROY_WITH_PARENT, (gtk.STOCK_CANCEL, gtk.RESPONSE_REJECT, gtk.STOCK_SAVE, gtk.RESPONSE_ACCEPT))
            hbox = gtk.HBox()
            hbox.pack_start(gtk.Label(_('Playlist name') + ':'), False, False, 5)
            entry = gtk.Entry()
            entry.set_activates_default(True)
            hbox.pack_start(entry, True, True, 5)
            dialog.vbox.pack_start(hbox)
            dialog.set_default_response(gtk.RESPONSE_ACCEPT)
            dialog.vbox.show_all()
            response = dialog.run()
            if response == gtk.RESPONSE_ACCEPT:
                plname = entry.get_text()
                plname = plname.replace("\\", "")
                plname = plname.replace("/", "")
                plname = plname.replace("\"", "")
                # Make sure this playlist doesn't already exit:
                for item in self.conn.do.lsinfo():
                    if item.type == 'playlist':
                        if item.playlist == plname:
                            dialog.destroy()
                            # show error here
                            error_dialog = gtk.MessageDialog(self.window, gtk.DIALOG_MODAL, gtk.MESSAGE_WARNING, gtk.BUTTONS_CLOSE, _("A playlist with this name already exists."))
                            error_dialog.set_title(_("Save Playlist"))
                            error_dialog.run()
                            error_dialog.destroy()
                            return
                self.conn.do.save(plname)
                self.playlists_populate()
            dialog.destroy()
            self.iterate_now()

    def playlists_populate(self):
        if not self.conn:
            return
        self.playlistsdata.clear()
        playlistinfo = []
        for item in self.conn.do.lsinfo():
            if item.type == 'playlist':
                playlistinfo.append(escape_html(item.playlist))
        playlistinfo.sort(key=lambda x: x.lower()) # Remove case sensitivity
        for item in playlistinfo:
            self.playlistsdata.append([gtk.STOCK_JUSTIFY_FILL, item])

    def parent_dir(self, action):
        if self.notebook.get_current_page() == 1:
            if self.browser.wd != "/":
                self.browse(None, self.browserdata.get_value(self.browserdata.get_iter((1,)), 1))

    def browse(self, widget=None, root='/'):
        if not self.conn:
            return

        # Handle special cases
        while self.conn.do.lsinfo(root) == []:
            if self.conn.do.listallinfo(root):
                # Info exists if we try to browse to a song
                self.add_item(self.browser)
                return
            elif root == '/':
                # Nothing in the library at all
                return
            else:
                # Back up and try the parent
                root = '/'.join(root.split('/')[:-1]) or '/'

        self.root = root
        # The logic below is more consistent with, e.g., thunar
        if len(root) > len(self.browser.wd):
            # Save position and row for where we just were if we've
            # navigated into a sub-directory:
            self.browserposition[self.browser.wd] = self.browser.get_visible_rect()[1]
            model, rows = self.browser.get_selection().get_selected_rows()
            if len(rows) > 0:
                value_for_selection = self.browserdata.get_value(self.browserdata.get_iter(rows[0]), 2)
                if value_for_selection != ".." and value_for_selection != "/":
                    self.browserselectedpath[self.browser.wd] = rows[0]
        else:
            # If we've navigated to a parent directory, don't save
            # anything so that the user will enter that subdirectory
            # again at the top position with nothing selected
            self.browserposition[self.browser.wd] = 0
            self.browserselectedpath[self.browser.wd] = None

        self.browser.wd = root
        self.browserdata.clear()
        if self.root != '/':
            self.browserdata.append([gtk.STOCK_HARDDISK, '/', '/'])
            self.browserdata.append([gtk.STOCK_OPEN, '/'.join(root.split('/')[:-1]) or '/', '..'])
        for item in self.conn.do.lsinfo(root):
            if item.type == 'directory':
                name = item.directory.split('/')[-1]
                self.browserdata.append([gtk.STOCK_OPEN, item.directory, escape_html(name)])
            elif item.type == 'file':
                name = item.file.split('/')[-1]
                self.browserdata.append(['sonata', item.file, escape_html(name)])

        # Scroll back to set view for current dir:
        self.browser.realize()
        while gtk.events_pending():
            gtk.main_iteration()
        try:
            self.browser.scroll_to_point(0, self.browserposition[self.browser.wd])
        except:
            self.browser.scroll_to_point(0, 0)

        # Select and focus previously selected item if it's not ".." or "/"
        if self.browser.wd in self.browserselectedpath:
            try:
                if self.browserselectedpath[self.browser.wd]:
                    self.browser.get_selection().select_path(self.browserselectedpath[self.browser.wd])
                    self.browser.grab_focus()
            except:
                pass

    def browserow(self, widget, path, column=0):
        self.browse(None, self.browserdata.get_value(self.browserdata.get_iter(path), 1))

    def browser_button_press(self, widget, event):
        if event.button == 3:
            self.set_menu_contextual_items_visible()
            self.mainmenu.popup(None, None, None, event.button, event.time)
            # Don't change the selection for a right-click. This
            # will allow the user to select multiple rows and then
            # right-click (instead of right-clicking and having
            # the current selection change to the current row)
            if self.browser.get_selection().count_selected_rows() > 1:
                return True

    def playlists_button_press(self, widget, event):
        if event.button == 3:
            self.set_menu_contextual_items_visible()
            self.mainmenu.popup(None, None, None, event.button, event.time)
            # Don't change the selection for a right-click. This
            # will allow the user to select multiple rows and then
            # right-click (instead of right-clicking and having
            # the current selection change to the current row)
            if self.playlists.get_selection().count_selected_rows() > 1:
                return True

    def add_item(self, widget):
        if self.conn:
            if self.notebook.get_current_page() == 1:
                # Library
                model, selected = self.browser.get_selection().get_selected_rows()
                if self.root == "/":
                    for path in selected:
                        self.conn.do.add(model.get_value(model.get_iter(path), 1))
                else:
                    iters = []
                    for path in selected:
                        if path[0] != 0 and path[0] != 1:
                            self.conn.do.add(model.get_value(model.get_iter(path), 1))
            else:
                # Playlist
                model, selected = self.playlists.get_selection().get_selected_rows()
                for path in selected:
                    self.conn.do.load(model.get_value(model.get_iter(path), 1))
            self.iterate_now()

    def replace_item(self, widget):
        play_after_replace = False
        if self.status and self.status.state == 'play':
            play_after_replace = True
        self.clear(None)
        self.add_item(widget)
        if play_after_replace and self.conn:
            self.conn.do.play()
        self.iterate_now()

    def position_menu(self, menu):
        if self.expanded:
            x, y, width, height = self.current.get_allocation()
            # Find first selected visible row and popup the menu
            # from there
            i = 0
            row_found = False
            row_y = 0
            if self.notebook.get_current_page() == 0:
                rows = self.current.get_selection().get_selected_rows()[1]
                visible_rect = self.current.get_visible_rect()
                while not row_found and i < len(rows):
                    row = rows[i]
                    row_rect = self.current.get_background_area(row, self.currentcolumn)
                    if row_rect.y + row_rect.height <= visible_rect.height and row_rect.y >= 0:
                        row_found = True
                        row_y = row_rect.y + 30
                    i += 1
            else:
                rows = self.browser.get_selection().get_selected_rows()[1]
                visible_rect = self.browser.get_visible_rect()
                while not row_found and i < len(rows):
                    row = rows[i]
                    row_rect = self.browser.get_background_area(row, self.browsercolumn)
                    if row_rect.y + row_rect.height <= visible_rect.height and row_rect.y >= 0:
                        row_found = True
                        row_y = row_rect.y + 30
                    i += 1
            return (self.x + width - 150, self.y + y + row_y, True)
        else:
            return (self.x + 250, self.y + 80, True)

    def menukey_press(self, action):
        self.set_menu_contextual_items_visible()
        self.mainmenu.popup(None, None, self.position_menu, 0, 0)

    def handle_change_status(self):
        if self.status == None:
            # clean up and bail out
            self.update_progressbar()
            self.update_cursong()
            self.update_wintitle()
            self.update_album_art()
            return

        # Update progress frequently if we're playing
        if self.status.state in ['play', 'pause']:
            self.update_progressbar()

        # Display current playlist
        if self.prevstatus == None or self.prevstatus.playlist != self.status.playlist:
            self.update_playlist()

        # If state changes
        if self.prevstatus == None or self.prevstatus.state != self.status.state:

            # Update progressbar if the state changes too
            self.update_progressbar()
            self.update_cursong()
            self.update_wintitle()
            if self.status.state == 'stop':
                self.ppbutton.set_image(gtk.image_new_from_stock(gtk.STOCK_MEDIA_PLAY, gtk.ICON_SIZE_BUTTON))
                image, label = self.ppbutton.get_children()[0].get_children()[0].get_children()
                label.set_text('')
                self.UIManager.get_widget('/traymenu/playmenu').show()
                self.UIManager.get_widget('/traymenu/pausemenu').hide()
                # Unbold playing song (if we were playing)
                if self.prevstatus and self.prevstatus.state == 'play':
                    oldrow = int(self.prevsonginfo.pos)
                    try:
                        self.currentdata[oldrow][1] = make_unbold(self.currentdata[oldrow][1])
                    except IndexError: # it's gone, playlist was probably cleared
                        pass
            elif self.status.state == 'pause':
                self.ppbutton.set_image(gtk.image_new_from_stock(gtk.STOCK_MEDIA_PLAY, gtk.ICON_SIZE_BUTTON))
                image, label = self.ppbutton.get_children()[0].get_children()[0].get_children()
                label.set_text('')
                self.UIManager.get_widget('/traymenu/playmenu').show()
                self.UIManager.get_widget('/traymenu/pausemenu').hide()
            elif self.status.state == 'play':
                self.ppbutton.set_image(gtk.image_new_from_stock(gtk.STOCK_MEDIA_PAUSE, gtk.ICON_SIZE_BUTTON))
                image, label = self.ppbutton.get_children()[0].get_children()[0].get_children()
                label.set_text('')
                self.UIManager.get_widget('/traymenu/playmenu').hide()
                self.UIManager.get_widget('/traymenu/pausemenu').show()
            if self.status.state in ['play', 'pause']:
                row = int(self.songinfo.pos)
                self.currentdata[row][1] = make_bold(self.currentdata[row][1])
            self.update_album_art()

        if self.prevstatus is None or self.status.volume != self.prevstatus.volume:
            self.volumescale.get_adjustment().set_value(int(self.status.volume))
            if int(self.status.volume) == 0:
                self.volumebutton.set_image(gtk.image_new_from_icon_name("stock_volume-mute", 4))
            elif int(self.status.volume) < 30:
                self.volumebutton.set_image(gtk.image_new_from_icon_name("stock_volume-min", 4))
            elif int(self.status.volume) <= 70:
                self.volumebutton.set_image(gtk.image_new_from_icon_name("stock_volume-med", 4))
            else:
                self.volumebutton.set_image(gtk.image_new_from_icon_name("stock_volume-max", 4))

        if self.conn:
            if self.prevstatus == None or self.prevstatus.get('updating_db', 0) != self.status.get('updating_db', 0):
                if not (self.status and self.status.get('updating_db', 0)):
                    self.browse(root=self.root)
                    self.playlists_populate()

    def handle_change_song(self):
        for song in self.currentdata:
            song[1] = make_unbold(song[1])

        if self.status and self.status.state in ['play', 'pause']:
            row = int(self.songinfo.pos)
            self.currentdata[row][1] = make_bold(self.currentdata[row][1])
            if self.expanded:
                visible_rect = self.current.get_visible_rect()
                row_rect = self.current.get_background_area(row, self.currentcolumn)
                if row_rect.y + row_rect.height > visible_rect.height:
                    top_coord = (row_rect.y + row_rect.height - visible_rect.height) + visible_rect.y
                    self.current.scroll_to_point(-1, top_coord)
                elif row_rect.y < 0:
                    self.current.scroll_to_cell(row)

        self.update_cursong()
        self.update_wintitle()
        self.update_album_art()

    def update_progressbar(self):
        if self.conn and self.status and self.status.state in ['play', 'pause']:
            at, len = [float(c) for c in self.status.time.split(':')]
            try:
                self.progressbar.set_fraction(at/len)
            except ZeroDivisionError:
                self.progressbar.set_fraction(0)
        else:
            self.progressbar.set_fraction(0)
        if self.conn:
            if self.status and self.status.state in ['play', 'pause']:
                at, len = [int(c) for c in self.status.time.split(':')]
                at_time = convert_time(at)
                try:
                    time = convert_time(int(self.songinfo.time))
                    self.progressbar.set_text(at_time + " / " + time)
                except AttributeError:
                    self.progressbar.set_text(at_time)
            else:
                self.progressbar.set_text('')
        else:
            self.progressbar.set_text(_('Not Connected'))
        return

    def update_cursong(self):
        if self.conn and self.status and self.status.state in ['play', 'pause']:
            try:
                self.cursonglabel.set_markup('<big><b>' + escape_html(getattr(self.songinfo, 'title', None)) + '</b></big>\n<small>' + _('by') + ' ' + escape_html(getattr(self.songinfo, 'artist', None)) + ' ' + _('from') + ' ' + escape_html(getattr(self.songinfo, 'album', None)) + '</small>')
            except:
                self.cursonglabel.set_markup('<big><b>' + escape_html(getattr(self.songinfo, 'file', None)) + '</b></big>\n<small>' + _('by Unknown') + '</small>')
        else:
            if self.expanded:
                self.cursonglabel.set_markup('<big><b>' + _('Stopped') + '</b></big>\n<small>' + _('Click to collapse') + '</small>')
            else:
                self.cursonglabel.set_markup('<big><b>' + _('Stopped') + '</b></big>\n<small>' + _('Click to expand') + '</small>')
        # Hide traytip's progressbar when stopped
        if (self.status and self.status.state == 'stop') or not self.conn:
            if not self.conn:
                self.traycursonglabel.set_label(_('Not connected'))
            else:
                self.traycursonglabel.set_label(_('Stopped'))
            self.trayprogressbar.hide()
            self.trayalbumimage.hide()
        else:
            self.trayprogressbar.show()
            if self.show_covers:
                self.trayalbumimage.show()

    def update_wintitle(self):
        if self.conn and self.status and self.status.state in ['play', 'pause']:
            try:
                self.window.set_property('title', getattr(self.songinfo, 'artist', None) + ': ' + getattr(self.songinfo, 'title', None) + ' - Sonata')
            except:
                self.window.set_property('title', getattr(self.songinfo, 'file', None) + ' - Sonata')
        else:
            self.window.set_property('title', 'Sonata')

    def update_playlist(self):
        if self.conn:
            self.songs = self.conn.do.playlistinfo()
            self.currentdata.clear()
            for track in self.songs:
                try:
                    self.currentdata.append([int(track.id), escape_html(getattr(track, 'artist', None)) + ": " + escape_html(getattr(track, 'title', None))])
                except:
                    self.currentdata.append([int(track.id), escape_html(getattr(track, 'file', None))])
            if self.status.state in ['play', 'pause']:
                row = int(self.songinfo.pos)
                self.currentdata[row][1] = make_bold(self.currentdata[row][1])
                if self.expanded:
                    while gtk.events_pending():
                        gtk.main_iteration()
                    visible_rect = self.current.get_visible_rect()
                    row_rect = self.current.get_background_area(row, self.currentcolumn)
                    if row_rect.y + row_rect.height > visible_rect.height:
                        top_coord = (row_rect.y + row_rect.height - visible_rect.height) + visible_rect.y
                        self.current.scroll_to_point(-1, top_coord)
                    elif row_rect.y < 0:
                        self.current.scroll_to_cell(row)

    def update_album_art(self):
        if not self.show_covers:
            return
        if self.conn and self.status and self.status.state in ['play', 'pause']:
            while gtk.events_pending():
                gtk.main_iteration()
            artist = getattr(self.songinfo, 'artist', None)
            if not artist: artist = ""
            album = getattr(self.songinfo, 'album', None)
            if not album: album = ""
            try:
                filename = os.path.expanduser("~/.config/sonata/covers/" + artist + "-" + album + ".jpg")
                if filename == self.lastalbumart:
                    # No need to update..
                    return
                if os.path.exists(filename):
                    pix = gtk.gdk.pixbuf_new_from_file(filename)
                    pix = pix.scale_simple(75, 75, gtk.gdk.INTERP_HYPER)
                    self.albumimage.set_from_pixbuf(pix)
                    pix = pix.scale_simple(50, 50, gtk.gdk.INTERP_HYPER)
                    self.trayalbumimage.set_from_pixbuf(pix)
                    self.lastalbumart = filename
                    del pix
                else:
                    self.download_image_to_filename(artist, album, filename)
                    if os.path.exists(filename):
                        pix = gtk.gdk.pixbuf_new_from_file(filename)
                        pix = pix.scale_simple(75, 75, gtk.gdk.INTERP_HYPER)
                        self.albumimage.set_from_pixbuf(pix)
                        pix = pix.scale_simple(50, 50, gtk.gdk.INTERP_HYPER)
                        self.trayalbumimage.set_from_pixbuf(pix)
                        self.lastalbumart = filename
                        del pix
                    else:
                        self.albumimage.set_from_file(self.sonatacd)
                        self.lastalbumart = None
            except:
                self.albumimage.set_from_file(self.sonatacd)
                self.lastalbumart = None
        else:
            self.albumimage.set_from_file(self.sonatacd)
            self.lastalbumart = None
        gc.collect()

    def download_image_to_filename(self, artist, album, dest_filename, all_images=False):
        if artist == "" and album == "":
            return
        try:
            while gtk.events_pending():
                gtk.main_iteration()
            socket.setdefaulttimeout(5)
            artist = urllib.quote(artist)
            album = urllib.quote(album)
            amazon_key = "12DR2PGAQT303YTEWP02"
            search_url = "http://webservices.amazon.com/onca/xml?Service=AWSECommerceService&AWSAccessKeyId=" + amazon_key + "&Operation=ItemSearch&SearchIndex=Music&Artist=" + artist + "&ResponseGroup=Images&Keywords=" + album
            request = urllib2.Request(search_url)
            request.add_header('Accept-encoding', 'gzip')
            opener = urllib2.build_opener()
            f = opener.open(request).read()
            curr_pos = 200    # Skip header..
            # Check if any results were returned; if not, search
            # again with just the artist name:
            img_url = f[f.find("http", curr_pos):f.find("jpg", curr_pos) + 3]
            if len(img_url) == 0:
                while gtk.events_pending():
                    gtk.main_iteration()
                search_url = "http://webservices.amazon.com/onca/xml?Service=AWSECommerceService&AWSAccessKeyId=" + amazon_key + "&Operation=ItemSearch&SearchIndex=Music&Artist=" + artist + "&ResponseGroup=Images"
                request = urllib2.Request(search_url)
                request.add_header('Accept-encoding', 'gzip')
                opener = urllib2.build_opener()
                f = opener.open(request).read()
                img_url = f[f.find("http", curr_pos):f.find("jpg", curr_pos) + 3]
                # And if that fails, try one last time with just the album name:
                if len(img_url) == 0:
                    while gtk.events_pending():
                        gtk.main_iteration()
                    search_url = "http://webservices.amazon.com/onca/xml?Service=AWSECommerceService&AWSAccessKeyId=" + amazon_key + "&Operation=ItemSearch&SearchIndex=Music&ResponseGroup=Images&Keywords=" + album
                    request = urllib2.Request(search_url)
                    request.add_header('Accept-encoding', 'gzip')
                    opener = urllib2.build_opener()
                    f = opener.open(request).read()
                    img_url = f[f.find("http", curr_pos):f.find("jpg", curr_pos) + 3]
            if all_images:
                curr_img = 1
                img_url = " "
                while len(img_url) > 0 and curr_pos > 0:
                    img_url = ""
                    curr_pos = f.find("<MediumImage>", curr_pos+10)
                    img_url = f[f.find("http", curr_pos):f.find("jpg", curr_pos) + 3]
                    if len(img_url) > 0:
                        while gtk.events_pending():
                            gtk.main_iteration()
                        urllib.urlretrieve(img_url, dest_filename.replace("<imagenum>", str(curr_img)))
                        curr_img += 1
                        # Skip the next SmallImage:
                        curr_pos = f.find("<MediumImage>", curr_pos+10)
            else:
                while gtk.events_pending():
                    gtk.main_iteration()
                curr_pos = f.find("<MediumImage>", curr_pos+10)
                img_url = f[f.find("http", curr_pos):f.find("jpg", curr_pos) + 3]
                if len(img_url) > 0:
                    urllib.urlretrieve(img_url, dest_filename)
        except:
            pass

    def labelnotify(self, *args):
        self.traycursonglabel.set_label(self.cursonglabel.get_label())
        if self.traytips.get_property('visible'):
            self.traytips._real_display(self.trayeventbox)

    def progressbarnotify_fraction(self, *args):
        self.trayprogressbar.set_fraction(self.progressbar.get_fraction())

    def progressbarnotify_text(self, *args):
        self.trayprogressbar.set_text(self.progressbar.get_text())

    #################
    # Gui Callbacks #
    #################

    def delete_event_yes(self, widget):
        self.exit_now = True
        self.delete_event(None, None)

    # This one makes sure the program exits when the window is closed
    def delete_event(self, widget, data=None):
        if not self.exit_now and self.minimize_to_systray:
            self.withdraw_app()
            return True
        self.save_settings()
        if self.conn and self.stop_on_exit:
            self.stop(None)
        gtk.main_quit()
        return False

    def on_window_state_change(self, widget, event):
        self.volume_hide()

    def on_window_configure(self, widget, event):
        width, height = self.window.get_size()
        if self.expanded: self.w, self.h = width, height
        else: self.w = width
        self.x, self.y = self.window.get_position()
        self.volume_hide()

    def expand(self, action):
        self.expander.set_expanded(False)
        self.expander_activate(None)
        self.expander.set_expanded(True)

    def collapse(self, action):
        self.expander.set_expanded(True)
        self.expander_activate(None)
        self.expander.set_expanded(False)

    def expander_activate(self, expander):
        self.expanded = False
        # Note that get_expanded() will return the state of the expander
        # before this current click
        if self.expander.get_expanded():
            self.notebook.hide()
        else:
            self.notebook.show_all()
        if not (self.conn and self.status and self.status.state in ['play', 'pause']):
            if self.expander.get_expanded():
                self.cursonglabel.set_markup('<big><b>' + _('Stopped') + '</b></big>\n<small>' + _('Click to expand') + '</small>')
            else:
                self.cursonglabel.set_markup('<big><b>' + _('Stopped') + '</b></big>\n<small>' + _('Click to collapse') + '</small>')
        while gtk.events_pending():
            gtk.main_iteration()
        # This is INCREDIBLY hackish.. but it attempts to ensure that
        # self.notebook is actually visible before resizing. If not,
        # it can cause the expanded playlist to be a smaller height
        # than self.h. If you can fix this, I'll love you forever.
        gobject.timeout_add(10, self.resize_window)
        return

    def resize_window(self):
        if self.expander.get_expanded():
            self.window.resize(self.w, self.h)
        else:
            self.window.resize(self.w, 1)
        if self.expander.get_expanded():
            self.expanded = True
            self.tooltips.set_tip(self.expander, _("Click to collapse the player"))
        else:
            self.tooltips.set_tip(self.expander, _("Click to expand the player"))
        # Put focus to the notebook:
        self.notebook_clicked(None, None, self.notebook.get_current_page())
        return

    # This callback allows the user to seek to a specific portion of the song
    def progressbar_button_press_event(self, widget, event):
        if event.button == 1:
            if self.status and self.status.state in ['play', 'pause']:
                at, len = [int(c) for c in self.status.time.split(':')]
                try:
                    progressbarsize = self.progressbar.allocation
                    seektime = int((event.x/progressbarsize.width) * len)
                    self.seek(int(self.status.song), seektime)
                except:
                    pass
            return True

    def progressbar_scroll_event(self, widget, event):
        if self.status and self.status.state in ['play', 'pause']:
            try:
                gobject.source_remove(self.seekidle)
            except:
                pass
            self.seekidle = gobject.idle_add(self.seek_when_idle, event.direction)
        return True

    def seek_when_idle(self, direction):
        at, len = [int(c) for c in self.status.time.split(':')]
        try:
            if direction == gtk.gdk.SCROLL_UP:
                seektime = int(self.status.time.split(":")[0]) - 10
                if seektime < 0: seektime = 0
            elif direction == gtk.gdk.SCROLL_DOWN:
                seektime = int(self.status.time.split(":")[0]) + 10
                if seektime > self.songinfo.time:
                    seektime = self.songinfo.time
            self.seek(int(self.status.song), seektime)
        except:
            pass

    def on_drag_drop(self, treeview, drag_context, x, y, selection, info, timestamp):
        model = treeview.get_model()
        foobar, self._selected = self.current.get_selection().get_selected_rows()
        data = pickle.loads(selection.data)
        drop_info = treeview.get_dest_row_at_pos(x, y)

        # calculate all this now before we start moving stuff
        drag_sources = []
        for path in data:
            index = path[0]
            iter = model.get_iter(path)
            id = model.get_value(iter, 0)
            text = model.get_value(iter, 1)
            drag_sources.append([index, iter, id, text])

        offset = 0
        for source in drag_sources:
            index, iter, id, text = source
            if drop_info:
                destpath, position = drop_info
                if destpath[0] > index:
                    # if moving ahead, all the subsequent indexes decrease by 1
                    dest = destpath[0] + offset - 1
                else:
                    # if moving back, next one will need to go after it
                    dest = destpath[0] + offset
                    offset += 1
                if position in (gtk.TREE_VIEW_DROP_BEFORE, gtk.TREE_VIEW_DROP_INTO_OR_BEFORE):
                    model.insert_before(iter, [index, text])
                    self.conn.do.moveid(id, dest)
                else:
                    model.insert_after(iter, [index, text])
                    self.conn.do.moveid(id, dest + 1)
            else:
                dest = len(self.conn.do.playlistinfo()) - 1
                self.conn.do.moveid(id, dest)
                model.append([0, text])
            # now fixup
            for source in drag_sources:
                if dest < index:
                    # we moved it back, so all indexes inbetween increased by 1
                    if dest < source[0] < index:
                        source[0] += 1
                else:
                    # we moved it ahead, so all indexes inbetween decreased by 1
                    if index < source[0] < dest:
                        source[0] -= 1
            model.remove(iter)

        if drag_context.action == gtk.gdk.ACTION_MOVE:
            drag_context.finish(True, True, timestamp)
        self.iterate_now()

    def after_drag_drop(self, treeview, drag_context):
        model = treeview.get_model()
        sel = treeview.get_selection()
        for path in self._selected:
            sel.select_path(path)

    def current_changed(self, treemodel, path, iter):
        pass

    def current_data_get(self, widget, drag_context, selection, info, timestamp):
        model, selected = self.current.get_selection().get_selected_rows()
        selection.set(selection.target, 8, pickle.dumps(selected))
        return

    def current_button_press(self, widget, event):
        if event.button == 3:
            self.set_menu_contextual_items_visible()
            self.mainmenu.popup(None, None, None, event.button, event.time)
            # Don't change the selection for a right-click. This
            # will allow the user to select multiple rows and then
            # right-click (instead of right-clicking and having
            # the current selection change to the current row)
            if self.current.get_selection().count_selected_rows() > 1:
                return True

    def current_popup_menu(self, widget):
        self.set_menu_contextual_items_visible()
        self.mainmenu.popup(None, None, None, 3, 0)

    def updatedb(self, widget):
        if self.conn:
            self.conn.do.update('/')
            self.iterate_now()

    def updatedb_path(self, action):
        if self.conn:
            if self.notebook.get_current_page() == 1:
                model, selected = self.browser.get_selection().get_selected_rows()
                iters = [model.get_iter(path) for path in selected]
                if len(iters) > 0:
                    # If there are selected rows, update these paths..
                    for iter in iters:
                        self.conn.do.update(self.browserdata.get_value(iter, 1))
                else:
                    # If no selection, update the current path...
                    self.conn.do.update(self.browser.wd)
                self.iterate_now()

    def image_activate(self, widget, event):
        self.window.handler_block(self.mainwinhandler)
        if event.button == 1:
            if self.lastalbumart:
                self.show_cover_large()
        elif event.button == 3:
            if self.conn and self.status and self.status.state in ['play', 'pause']:
                artist = getattr(self.songinfo, 'artist', None)
                if artist:
                    self.imagemenu.popup(None, None, None, event.button, event.time)
        gobject.timeout_add(50, self.unblock_window_popup_handler)
        return False

    def show_cover_large(self):
        artist = getattr(self.songinfo, 'artist', None)
        if not artist: artist = ""
        album = getattr(self.songinfo, 'album', None)
        if not album: album = ""
        if artist == "" and album == "":
            return
        filename = os.path.expanduser("~/.config/sonata/covers/" + artist + "-" + album + ".jpg")
        if os.path.exists(filename):
            coverwindow = gtk.Dialog(_("Cover Art"), self.window, gtk.DIALOG_DESTROY_WITH_PARENT, (gtk.STOCK_CLOSE, gtk.RESPONSE_CLOSE))
            coverwindow.set_resizable(False)
            coverwindow.set_has_separator(True)
            pix = gtk.gdk.pixbuf_new_from_file(filename)
            if pix.get_width() != 160:
                print pix.get_width(), pix.get_height()
                pix = pix.scale_simple(160, int(160/float(pix.get_width())*pix.get_height()), gtk.gdk.INTERP_HYPER)
                print pix.get_width(), pix.get_height()
            image = gtk.Image()
            image.set_from_pixbuf(pix)
            hbox = gtk.HBox()
            hbox.pack_start(image, True, True, 20)
            coverwindow.vbox.pack_start(hbox, False, False, 20)
            if artist != "":
                artistlabel = gtk.Label('  ' + artist + '  ')
            else:
                artistlabel = gtk.Label('  ' + _('Unknown Artist') + '  ')
            coverwindow.vbox.pack_start(artistlabel, False, False, 2)
            if album != "":
                albumlabel = gtk.Label('  ' + album + '  ')
            else:
                albumlabel = gtk.Label('  ' + _('Unknown Album') + '  ')
            coverwindow.vbox.pack_start(albumlabel, False, False, 2)
            coverwindow.vbox.pack_start(gtk.Label(), False, False, 0)
            coverwindow.vbox.show_all()
            coverwindow.run()
            coverwindow.destroy()

    def unblock_window_popup_handler(self):
        self.window.handler_unblock(self.mainwinhandler)

    def change_cursor(self, type):
        for i in gtk.gdk.window_get_toplevels():
            i.set_cursor(type)

    def update_preview(self, file_chooser, preview):
        filename = file_chooser.get_preview_filename()
        pixbuf = None
        try:
            pixbuf = gtk.gdk.pixbuf_new_from_file_at_size(filename, 128, 128)
        except:
            pass
        if pixbuf == None:
            try:
                pixbuf = gtk.gdk.PixbufAnimation(filename).get_static_image()
                width = pixbuf.get_width()
                height = pixbuf.get_height()
                if width > height:
                    pixbuf = pixbuf.scale_simple(128, int(float(height)/width*128), gtk.gdk.INTERP_HYPER)
                else:
                    pixbuf = pixbuf.scale_simple(int(float(width)/height*128), 128, gtk.gdk.INTERP_HYPER)
            except:
                pass
        if pixbuf == None:
            pixbuf = gtk.gdk.Pixbuf(gtk.gdk.COLORSPACE_RGB, 1, 8, 128, 128)
            pixbuf.fill(0x00000000)
        preview.set_from_pixbuf(pixbuf)
        have_preview = True
        file_chooser.set_preview_widget_active(have_preview)
        del pixbuf
        gc.collect()

    def choose_image_local(self, widget):
        dialog = gtk.FileChooserDialog(title=_("Open Image"),action=gtk.FILE_CHOOSER_ACTION_OPEN,buttons=(gtk.STOCK_CANCEL,gtk.RESPONSE_CANCEL,gtk.STOCK_OPEN,gtk.RESPONSE_OK))
        filter = gtk.FileFilter()
        filter.set_name(_("Images"))
        filter.add_pixbuf_formats()
        dialog.add_filter(filter)
        filter = gtk.FileFilter()
        filter.set_name(_("All files"))
        filter.add_pattern("*")
        dialog.add_filter(filter)
        preview = gtk.Image()
        dialog.set_preview_widget(preview)
        dialog.set_use_preview_label(False)
        dialog.connect("update-preview", self.update_preview, preview)
        dialog.set_default_response(gtk.RESPONSE_OK)
        response = dialog.run()
        if response == gtk.RESPONSE_OK:
            filename = dialog.get_filenames()[0]
            artist = getattr(self.songinfo, 'artist', None)
            if not artist: artist = ""
            album = getattr(self.songinfo, 'album', None)
            if not album: album = ""
            dest_filename = os.path.expanduser("~/.config/sonata/covers/" + artist + "-" + album + ".jpg")
            # Remove file if already set:
            if os.path.exists(dest_filename):
                os.remove(dest_filename)
            # Copy file to covers dir:
            shutil.copyfile(filename, dest_filename)
            # And finally, set the image in the interface:
            self.lastalbumart = None
            self.update_album_art()
        dialog.destroy()

    def choose_image(self, widget):
        self.change_cursor(gtk.gdk.Cursor(gtk.gdk.WATCH))
        while gtk.events_pending():
            gtk.main_iteration()
        choose_dialog = gtk.Dialog(_("Choose Cover Art"), self.window, gtk.DIALOG_MODAL, (gtk.STOCK_CANCEL, gtk.RESPONSE_REJECT))
        choosebutton = choose_dialog.add_button(_("Choose"), gtk.RESPONSE_ACCEPT)
        chooseimage = gtk.Image()
        chooseimage.set_from_stock(gtk.STOCK_CONVERT, gtk.ICON_SIZE_BUTTON)
        choosebutton.set_image(chooseimage)
        choose_dialog.set_has_separator(False)
        choose_dialog.set_default(choosebutton)
        scroll = gtk.ScrolledWindow()
        scroll.set_size_request(350, 325)
        scroll.set_policy(gtk.POLICY_NEVER, gtk.POLICY_ALWAYS)
        # Retrieve all images from amazon:
        artist = getattr(self.songinfo, 'artist', None)
        if not artist: artist = ""
        album = getattr(self.songinfo, 'album', None)
        if not album: album = ""
        imagelist = gtk.ListStore(int, gtk.gdk.Pixbuf)
        filename = os.path.expanduser("~/.config/sonata/covers/temp/<imagenum>.jpg")
        while gtk.events_pending():
            gtk.main_iteration()
        if os.path.exists(os.path.dirname(filename)):
            removeall(os.path.dirname(filename))
        if not os.path.exists(os.path.dirname(filename)):
            os.mkdir(os.path.dirname(filename))
        self.download_image_to_filename(artist, album, filename, True)
        # Put images to ListStore
        image_num = 1
        while os.path.exists(filename.replace("<imagenum>", str(image_num))):
            try:
                while gtk.events_pending():
                    gtk.main_iteration()
                pix = gtk.gdk.pixbuf_new_from_file(filename.replace("<imagenum>", str(image_num)))
                pix = pix.scale_simple(150, 150, gtk.gdk.INTERP_HYPER)
                imagelist.append([image_num, pix])
            except:
                imagelist.append([image_num, None])
            image_num += 1
        num_images = image_num - 1
        if num_images > 0:
            del pix
            imagewidget = gtk.IconView(imagelist)
            imagewidget.set_pixbuf_column(1)
            imagewidget.set_columns(2)
            imagewidget.set_item_width(150)
            imagewidget.set_spacing(5)
            imagewidget.set_margin(10)
            imagewidget.set_selection_mode(gtk.SELECTION_SINGLE)
            imagewidget.select_path("0")
            imagewidget.connect('item-activated', self.replace_cover, filename, choose_dialog, artist, album)
            scroll.add(imagewidget)
            choose_dialog.vbox.pack_start(scroll)
            choose_dialog.vbox.show_all()
            self.change_cursor(None)
            response = choose_dialog.run()
            if response == gtk.RESPONSE_ACCEPT:
                self.replace_cover(imagewidget, imagewidget.get_selected_items()[0], filename, choose_dialog, artist, album)
            else:
                choose_dialog.destroy()
        else:
            self.change_cursor(None)
            while gtk.events_pending():
                gtk.main_iteration()
            error_dialog = gtk.MessageDialog(self.window, gtk.DIALOG_MODAL, gtk.MESSAGE_WARNING, gtk.BUTTONS_CLOSE, _("No remote covers were found."))
            error_dialog.set_title(_("Choose Cover Art"))
            error_dialog.run()
            error_dialog.destroy()
        gc.collect()

    def replace_cover(self, iconview, path, filename, dialog, artist, album):
        try:
            image_num = int(path[0]) + 1
            filename = filename.replace("<imagenum>", str(image_num))
            dest_filename = os.path.expanduser("~/.config/sonata/covers/" + artist + "-" + album + ".jpg")
            if os.path.exists(filename):
                # Move temp file to actual file:
                os.remove(dest_filename)
                os.rename(filename, dest_filename)
                # And finally, set the image in the interface:
                self.lastalbumart = None
                self.update_album_art()
                # Clean up..
                if os.path.exists(os.path.dirname(filename)):
                    removeall(os.path.dirname(filename))
        except:
            pass
        dialog.destroy()

    # What happens when you click on the system tray icon?
    def trayaction(self, widget, event):
        if event.button == 1: # Left button shows/hides window(s)
            self.ignore_toggle_signal = True
            prev_state = self.UIManager.get_widget('/traymenu/showmenu').get_active()
            self.UIManager.get_widget('/traymenu/showmenu').set_active(not prev_state)
            if self.window.window.get_state() & gtk.gdk.WINDOW_STATE_WITHDRAWN: # window is hidden
                self.withdraw_app_undo()
            elif not (self.window.window.get_state() & gtk.gdk.WINDOW_STATE_WITHDRAWN): # window is showing
                self.withdraw_app()
            # This prevents the tooltip from popping up again until the user
            # leaves and enters the trayicon again
            self.traytips._remove_timer()
            while gtk.events_pending():
                gtk.main_iteration()
            gobject.timeout_add(500, self.set_ignore_toggle_signal_false)
        elif event.button == 2: # Middle button will play/pause
            self.pp(self.trayeventbox)
        elif event.button == 3: # Right button pops up menu
            self.traymenu.popup(None, None, None, event.button, event.time)
        return False

    def withdraw_app_undo(self):
        self.window.move(self.x, self.y)
        if not self.expanded:
            self.notebook.set_no_show_all(True)
        self.window.show_all()
        self.window.present() # Helps to raise the window (useful against focus stealing prevention)
        self.window.grab_focus()
        self.notebook.set_no_show_all(False)
        if self.sticky:
            self.window.stick()
        self.withdrawn = False

    def withdraw_app_on_escape(self, action):
        if self.minimize_to_systray:
            self.widthdraw_app()

    def withdraw_app(self):
        self.window.hide()
        self.withdrawn = True

    def withdraw_app_toggle(self, action):
        if self.ignore_toggle_signal:
            return
        self.ignore_toggle_signal = True
        if self.UIManager.get_widget('/traymenu/showmenu').get_active() == True:
            self.withdraw_app_undo()
        else:
            self.withdraw_app()
        while gtk.events_pending():
            gtk.main_iteration()
        gobject.timeout_add(500, self.set_ignore_toggle_signal_false)

    def set_ignore_toggle_signal_false(self):
        self.ignore_toggle_signal = False

    # Change volume on mousewheel over systray icon:
    def trayaction_scroll(self, widget, event):
        self.on_volumebutton_scroll(widget, event)

    # Tray menu callbacks, because I can't reuse all of them.
    def quit_activate(self, widget):
        self.window.destroy()

    def current_click(self, treeview, path, column):
        iter = self.currentdata.get_iter(path)
        self.conn.do.playid(self.currentdata.get_value(iter, 0))
        self.iterate_now()

    def switch_to_current(self, action):
        self.notebook.set_current_page(0)

    def switch_to_library(self, action):
        self.notebook.set_current_page(1)

    def switch_to_playlists(self, action):
        self.notebook.set_current_page(2)

    def lower_volume(self, action):
        new_volume = int(self.volumescale.get_adjustment().get_value()) - 10
        if new_volume < 0:
            new_volume = 0
        self.volumescale.get_adjustment().set_value(new_volume)
        self.on_volumescale_change(self.volumescale, 0, 0)

    def raise_volume(self, action):
        new_volume = int(self.volumescale.get_adjustment().get_value()) + 10
        if new_volume > 100:
            new_volume = 100
        self.volumescale.get_adjustment().set_value(new_volume)
        self.on_volumescale_change(self.volumescale, 0, 0)

    # Volume control
    def on_volumebutton_clicked(self, widget):
        if not self.volumewindow.get_property('visible'):
            x_win, y_win = self.volumebutton.window.get_origin()
            button_rect = self.volumebutton.get_allocation()
            x_coord, y_coord = button_rect.x + x_win, button_rect.y+y_win
            width, height = button_rect.width, button_rect.height
            self.volumewindow.set_size_request(width, -1)
            self.volumewindow.move(x_coord, y_coord+height)
            self.volumewindow.present()
        else:
            self.volume_hide()
        return

    def on_volumebutton_scroll(self, widget, event):
        if event.direction == gtk.gdk.SCROLL_UP:
            self.raise_volume(None)
        elif event.direction == gtk.gdk.SCROLL_DOWN:
            self.lower_volume(None)
        return

    def on_volumescale_scroll(self, widget, event):
        if event.direction == gtk.gdk.SCROLL_UP:
            new_volume = int(self.volumescale.get_adjustment().get_value()) + 10
            if new_volume > 100:
                new_volume = 100
            self.volumescale.get_adjustment().set_value(new_volume)
        elif event.direction == gtk.gdk.SCROLL_DOWN:
            new_volume = int(self.volumescale.get_adjustment().get_value()) - 10
            if new_volume < 0:
                new_volume = 0
            self.volumescale.get_adjustment().set_value(new_volume)
        return

    def on_volumescale_change(self, obj, value, data):
        new_volume = int(obj.get_adjustment().get_value())
        self.conn.do.setvol(new_volume)
        self.iterate_now()
        return

    def on_volumewindow_unfocus(self, obj, data):
        self.volume_hide()
        return True

    def volume_hide(self):
        self.volumebutton.set_active(False)
        self.volumewindow.hide()

    # Control callbacks
    def pp(self, widget):
        if self.status.state in ('stop', 'pause'):
            self.conn.do.play()
        elif self.status.state == 'play':
            self.conn.do.pause(1)
        self.iterate_now()
        return

    def stop(self, widget):
        self.conn.do.stop()
        self.iterate_now()
        return

    def prev(self, widget):
        self.conn.do.previous()
        self.iterate_now()
        return

    def next(self, widget):
        self.conn.do.next()
        self.iterate_now()
        return

    def mmpp(self, keys, key):
        if self.conn:
            self.pp(None)

    def mmstop(self, keys, key):
        if self.conn:
            self.stop(None)

    def mmprev(self, keys, key):
        if self.conn:
            self.prev(None)

    def mmnext(self, keys, key):
        if self.conn:
            self.next(None)

    def remove(self, widget):
        if self.notebook.get_current_page() == 0:
            model, selected = self.current.get_selection().get_selected_rows()
            iters = [model.get_iter(path) for path in selected]
            for iter in iters:
                self.conn.do.deleteid(self.currentdata.get_value(iter, 0))
        else:
            model, selected = self.playlists.get_selection().get_selected_rows()
            iters = [model.get_iter(path) for path in selected]
            for iter in iters:
                self.conn.do.rm(self.playlistsdata.get_value(iter, 1))
            self.playlists_populate()
        self.iterate_now()

    def randomize(self, widget):
        # Ironically enough, the command to turn shuffle on/off is called
        # random, and the command to randomize the playlist is called shuffle.
        self.conn.do.shuffle()
        return

    def clear(self, widget):
        if self.conn:
            self.conn.do.clear()
            self.iterate_now()
        return

    def repeat_now(self, widget):
        if self.conn:
            if self.status.repeat == '0':
                self.repeatmenu.set_active(True)
                self.repeat = True
                self.conn.do.repeat(1)
            elif self.status.repeat == '1':
                self.repeatmenu.set_active(False)
                self.repeat = False
                self.conn.do.repeat(0)

    def shuffle_now(self, widget):
        if self.conn:
            if self.status.random == '0':
                self.conn.do.random(1)
                self.shufflemenu.set_active(True)
                self.shuffle = True
            elif self.status.random == '1':
                self.conn.do.random(0)
                self.shufflemenu.set_active(False)
                self.shuffle = False

    def prefs(self, widget, show_mpd_tab=False):
        prefswindow = gtk.Dialog(_("Preferences"), self.window, flags=gtk.DIALOG_DESTROY_WITH_PARENT)
        prefswindow.set_resizable(False)
        prefswindow.set_has_separator(False)
        hbox = gtk.HBox()
        prefsnotebook = gtk.Notebook()
        table = gtk.Table(7, 2)
        table.set_row_spacings(7)
        table.set_col_spacings(3)
        table.attach(gtk.Label(), 1, 3, 1, 2, gtk.FILL|gtk.EXPAND, gtk.FILL|gtk.EXPAND, 10, 0)
        hostentry = gtk.Entry()
        hostentry.set_text(str(self.host))
        table.attach(gtk.Label(_("Host") + ":"), 1, 2, 2, 3, gtk.FILL|gtk.EXPAND, gtk.FILL|gtk.EXPAND, 10, 0)
        table.attach(hostentry, 2, 3, 2, 3, gtk.FILL|gtk.EXPAND, gtk.FILL|gtk.EXPAND, 10, 0)
        portentry = gtk.Entry()
        portentry.set_text(str(self.port))
        table.attach(gtk.Label(_("Port") + ":"), 1, 2, 3, 4, gtk.FILL|gtk.EXPAND, gtk.FILL|gtk.EXPAND, 10, 0)
        table.attach(portentry, 2, 3, 3, 4, gtk.FILL|gtk.EXPAND, gtk.FILL|gtk.EXPAND, 10, 0)
        passwordentry = gtk.Entry()
        passwordentry.set_visibility(False)
        passwordentry.set_text(str(self.password))
        table.attach(gtk.Label(_("Password") + ":"), 1, 2, 4, 5, gtk.FILL|gtk.EXPAND, gtk.FILL|gtk.EXPAND, 10, 0)
        table.attach(passwordentry, 2, 3, 4, 5, gtk.FILL|gtk.EXPAND, gtk.FILL|gtk.EXPAND, 10, 0)
        blanklabel = gtk.Label()
        blanklabel.set_markup("<small>(" + _('Leave blank if none is required') + ")</small>")
        blanklabel.set_alignment(0, 0)
        table.attach(blanklabel, 2, 3, 5, 6, gtk.FILL|gtk.EXPAND, gtk.FILL|gtk.EXPAND, 10, 0)
        table.attach(gtk.Label(), 1, 3, 6, 7, gtk.FILL|gtk.EXPAND, gtk.FILL|gtk.EXPAND, 10, 0)
        table2 = gtk.Table(7, 2)
        display_art = gtk.CheckButton(_("Show album covers"))
        display_art.set_active(self.show_covers)
        display_volume = gtk.CheckButton(_("Show volume button"))
        display_volume.set_active(self.show_volume)
        win_sticky = gtk.CheckButton(_("Show window on all workspaces"))
        win_sticky.set_active(self.sticky)
        win_ontop = gtk.CheckButton(_("Keep Sonata above other windows"))
        win_ontop.set_active(self.ontop)
        table2.attach(gtk.Label(), 1, 3, 1, 2, gtk.FILL|gtk.EXPAND, gtk.FILL|gtk.EXPAND, 15, 0)
        table2.attach(display_art, 1, 3, 2, 3, gtk.FILL|gtk.EXPAND, gtk.FILL|gtk.EXPAND, 15, 0)
        table2.attach(display_volume, 1, 3, 3, 4, gtk.FILL|gtk.EXPAND, gtk.FILL|gtk.EXPAND, 15, 0)
        table2.attach(win_sticky, 1, 3, 4, 5, gtk.FILL|gtk.EXPAND, gtk.FILL|gtk.EXPAND, 15, 0)
        table2.attach(win_ontop, 1, 3, 5, 6, gtk.FILL|gtk.EXPAND, gtk.FILL|gtk.EXPAND, 15, 0)
        table2.attach(gtk.Label(), 1, 3, 6, 7, gtk.FILL|gtk.EXPAND, gtk.FILL|gtk.EXPAND, 15, 0)
        table3 = gtk.Table(7, 2)
        exit_stop = gtk.CheckButton(_("Stop playback on exit"))
        exit_stop.set_active(self.stop_on_exit)
        self.tooltips.set_tip(exit_stop, _("MPD allows playback even when the client is not open. If enabled, Sonata will behave like a more conventional music player and, instead, stop playback upon exit."))
        minimize = gtk.CheckButton(_("Minimize to system tray on close"))
        minimize.set_active(self.minimize_to_systray)
        self.tooltips.set_tip(minimize, _("If enabled, closing Sonata will minimize it to the system tray. Note that it's currently impossible to detect if there actually is a system tray, so only check this if you have one."))
        if HAVE_EGG and self.trayicon.get_property('visible') == True:
            minimize.set_sensitive(True)
        else:
            minimize.set_sensitive(False)
        table3.attach(gtk.Label(), 1, 3, 1, 2, gtk.FILL|gtk.EXPAND, gtk.FILL|gtk.EXPAND, 15, 0)
        table3.attach(exit_stop, 1, 3, 2, 3, gtk.FILL|gtk.EXPAND, gtk.FILL|gtk.EXPAND, 15, 0)
        table3.attach(minimize, 1, 3, 3, 4, gtk.FILL|gtk.EXPAND, gtk.FILL|gtk.EXPAND, 15, 0)
        table3.attach(gtk.Label(), 1, 3, 4, 5, gtk.FILL|gtk.EXPAND, gtk.FILL|gtk.EXPAND, 15, 0)
        table3.attach(gtk.Label(), 1, 3, 5, 6, gtk.FILL|gtk.EXPAND, gtk.FILL|gtk.EXPAND, 15, 0)
        table3.attach(gtk.Label(), 1, 3, 6, 7, gtk.FILL|gtk.EXPAND, gtk.FILL|gtk.EXPAND, 15, 0)
        prefsnotebook.append_page(table2, gtk.Label(str=_("Interface")))
        prefsnotebook.append_page(table3, gtk.Label(str=_("Behavior")))
        prefsnotebook.append_page(table, gtk.Label(str=_("MPD")))
        hbox.pack_start(prefsnotebook, False, False, 10)
        prefswindow.vbox.pack_start(hbox, False, False, 10)
        close_button = prefswindow.add_button(gtk.STOCK_CLOSE, gtk.RESPONSE_CLOSE)
        prefswindow.show_all()
        while gtk.events_pending():
            gtk.main_iteration()
        if show_mpd_tab:
            prefsnotebook.set_current_page(2) # MPD page
        close_button.grab_focus()
        response = prefswindow.run()
        if response == gtk.RESPONSE_CLOSE:
            if hostentry.get_text() != self.host or portentry.get_text() != self.port or passwordentry.get_text() != self.password:
                self.host = hostentry.get_text()
                try:
                    self.port = int(portentry.get_text())
                except:
                    pass
                self.password = passwordentry.get_text()
                show_covers_prev = self.show_covers
                show_volume_prev = self.show_volume
                self.show_covers = display_art.get_active()
                self.show_volume = display_volume.get_active()
                self.stop_on_exit = exit_stop.get_active()
                self.ontop = win_ontop.get_active()
                self.sticky = win_sticky.get_active()
                self.minimize_to_systray = minimize.get_active()
                if show_covers_prev == False and self.show_covers == True:
                    self.albumimage.set_from_file(self.sonatacd)
                    self.lastalbumart = None
                    self.imageeventbox.set_no_show_all(False)
                    self.imageeventbox.show_all()
                    self.trayalbumimage.set_no_show_all(False)
                    self.trayalbumimage.show_all()
                    self.update_album_art()
                elif show_covers_prev == True and self.show_covers == False:
                    self.imageeventbox.set_no_show_all(True)
                    self.imageeventbox.hide()
                    self.trayalbumimage.set_no_show_all(True)
                    self.trayalbumimage.hide()
                if show_volume_prev == False and self.show_volume == True:
                    self.volumebutton.set_no_show_all(False)
                    self.volumebutton.show()
                elif show_volume_prev == True and self.show_volume == False:
                    self.volumebutton.set_no_show_all(True)
                    self.volumebutton.hide()
                if self.ontop:
                    self.window.set_keep_above(True)
                else:
                    self.window.set_keep_above(False)
                if self.sticky:
                    self.window.stick()
                else:
                    self.window.unstick()
                self.change_cursor(gtk.gdk.Cursor(gtk.gdk.WATCH))
                while gtk.events_pending():
                    gtk.main_iteration()
                self.conn = self.connect()
                if self.conn:
                    self.iterate_time = self.iterate_time_when_connected
                    self.conn.do.password(self.password)
                    self.iterate_now()
                else:
                    self.iterate_time = self.iterate_time_when_disconnected
                    self.browserdata.clear()
                self.change_cursor(None)
        prefswindow.destroy()

    def seek(self, song, seektime):
        self.conn.do.seek(song, seektime)
        self.iterate_now()
        return

    def popup_menu(self, widget, event):
        if widget == self.window:
            if event.get_coords()[1] > self.notebook.get_allocation()[1]:
                return
        if event.button == 3:
            self.set_menu_contextual_items_hidden()
            self.mainmenu.popup(None, None, None, event.button, event.time)

    def set_menu_contextual_items_visible(self):
        if not self.expanded:
            self.set_menu_contextual_items_hidden()
        elif self.notebook.get_current_page() == 0:
            self.UIManager.get_widget('/mainmenu/removemenu/').show()
            self.UIManager.get_widget('/mainmenu/clearmenu/').show()
            self.UIManager.get_widget('/mainmenu/savemenu/').show()
            self.UIManager.get_widget('/mainmenu/addmenu/').hide()
            self.UIManager.get_widget('/mainmenu/replacemenu/').hide()
            self.UIManager.get_widget('/mainmenu/rmmenu/').hide()
            self.UIManager.get_widget('/mainmenu/updatemenu/').hide()
        elif self.notebook.get_current_page() == 1:
            self.UIManager.get_widget('/mainmenu/removemenu/').hide()
            self.UIManager.get_widget('/mainmenu/clearmenu/').hide()
            self.UIManager.get_widget('/mainmenu/savemenu/').hide()
            self.UIManager.get_widget('/mainmenu/addmenu/').show()
            self.UIManager.get_widget('/mainmenu/replacemenu/').show()
            self.UIManager.get_widget('/mainmenu/rmmenu/').hide()
            self.UIManager.get_widget('/mainmenu/updatemenu/').show()
        else:
            self.UIManager.get_widget('/mainmenu/removemenu/').hide()
            self.UIManager.get_widget('/mainmenu/clearmenu/').hide()
            self.UIManager.get_widget('/mainmenu/savemenu/').hide()
            self.UIManager.get_widget('/mainmenu/addmenu/').show()
            self.UIManager.get_widget('/mainmenu/replacemenu/').show()
            self.UIManager.get_widget('/mainmenu/rmmenu/').show()
            self.UIManager.get_widget('/mainmenu/updatemenu/').hide()

    def set_menu_contextual_items_hidden(self):
        self.UIManager.get_widget('/mainmenu/removemenu/').hide()
        self.UIManager.get_widget('/mainmenu/clearmenu/').hide()
        self.UIManager.get_widget('/mainmenu/savemenu/').hide()
        self.UIManager.get_widget('/mainmenu/addmenu/').hide()
        self.UIManager.get_widget('/mainmenu/replacemenu/').hide()
        self.UIManager.get_widget('/mainmenu/rmmenu/').hide()
        self.UIManager.get_widget('/mainmenu/updatemenu/').hide()

    def help(self, action):
        self.browser_load("http://sonata.berlios.de/documentation.html")

    def initialize_systrayicon(self):
        # Make system tray 'icon' to sit in the system tray
        self.trayeventbox = gtk.EventBox()
        self.trayeventbox.connect('button_press_event', self.trayaction)
        self.trayeventbox.connect('scroll-event', self.trayaction_scroll)
        self.traytips.set_tip(self.trayeventbox)
        self.trayimage = gtk.Image()
        self.trayimage.set_from_stock('sonata', gtk.ICON_SIZE_BUTTON)
        self.trayeventbox.add(self.trayimage)
        try:
            self.trayicon = egg.trayicon.TrayIcon("TrayIcon")
            self.trayicon.add(self.trayeventbox)
            self.trayicon.show_all()
        except:
            pass

    def browser_load(self, docslink):
        try:
            pid = subprocess.Popen(["gnome-open", docslink]).pid
        except:
            try:
                pid = subprocess.Popen(["exo-open", docslink]).pid
            except:
                try:
                    pid = subprocess.Popen(["firefox", docslink]).pid
                except:
                    try:
                        pid = subprocess.Popen(["mozilla", docslink]).pid
                    except:
                        try:
                            pid = subprocess.Popen(["opera", docslink]).pid
                        except:
                            error_dialog = gtk.MessageDialog(self.window, gtk.DIALOG_MODAL, gtk.MESSAGE_WARNING, gtk.BUTTONS_CLOSE, _('Unable to launch a suitable browser.'))
                            error_dialog.run()
                            error_dialog.destroy()

    def main(self):
        gtk.main()

class BaseDBus(dbus.service.Object, Base):
    def __init__(self, bus_name, object_path):
        dbus.service.Object.__init__(self, bus_name, object_path)
        Base.__init__(self)

    @dbus.service.method('org.MPD.SonataInterface')
    def show(self):
        self.window.hide()
        self.withdraw_app_undo()

    @dbus.service.method('org.MPD.SonataInterface')
    def toggle(self):
        if self.window.get_property('visible'):
            self.withdraw_app()
        else:
            self.withdraw_app_undo()

class TrayIconTips(gtk.Window):
    """Custom tooltips derived from gtk.Window() that allow for markup text and multiple widgets, e.g. a progress bar. ;)"""
    MARGIN = 4

    def __init__(self, widget=None):
        gtk.Window.__init__(self, gtk.WINDOW_POPUP)
        # from gtktooltips.c:gtk_tooltips_force_window
        self.set_app_paintable(True)
        self.set_resizable(False)
        self.set_name("gtk-tooltips")
        self.connect('expose-event', self._on__expose_event)

        if widget != None:
            self._label = gtk.Label()
            self.add(self._label)

        self._show_timeout_id = -1
        self.timer_tag = None

    # from gtktooltips.c:gtk_tooltips_draw_tips
    def _calculate_pos(self, widget):
        screen = widget.get_screen()
        x, y = widget.window.get_origin()
        w, h = self.size_request()

        if widget.flags() & gtk.NO_WINDOW:
            x += widget.allocation.x
            y += widget.allocation.y

        pointer_screen, px, py, _ = screen.get_display().get_pointer()
        if pointer_screen != screen:
            px = x
            py = y

        monitor_num = screen.get_monitor_at_point(px, py)
        monitor = screen.get_monitor_geometry(monitor_num)

        # If the tooltip goes off the screen horizontally, realign it so that
        # it all displays.
        if (x + w) > monitor.width:
            x = monitor.width - w

        # If the tooltip goes off the screen vertically (i.e. the system tray
        # icon is on the bottom of the screen), realign the icon so that it
        # shows above the icon.
        if ((y + h + widget.allocation.height + self.MARGIN) >
            monitor.y + monitor.height):
            y = y - h - self.MARGIN
        else:
            y = y + widget.allocation.height + self.MARGIN

        return x, y

    def _event_handler (self, widget):
        widget.connect_after("event-after", self._motion_cb)

    def _motion_cb (self, widget, event):
        if event.type == gtk.gdk.LEAVE_NOTIFY:
            self._remove_timer()
        if event.type == gtk.gdk.ENTER_NOTIFY:
            self._start_delay(widget)

    def _start_delay (self, widget):
        self.timer_tag = gobject.timeout_add(500, self._tips_timeout, widget)

    def _tips_timeout (self, widget):
        gtk.gdk.threads_enter()
        self._real_display(widget)
        gtk.gdk.threads_leave()

    def _remove_timer(self):
        self.hide()
        if self.timer_tag:
            gobject.source_remove(self.timer_tag)
        self.timer_tag = None

    # from gtktooltips.c:gtk_tooltips_paint_window
    def _on__expose_event(self, window, event):
        w, h = window.size_request()
        window.style.paint_flat_box(window.window,
                                    gtk.STATE_NORMAL, gtk.SHADOW_OUT,
                                    None, window, "tooltip",
                                    0, 0, w, h)
        return False

    def _real_display(self, widget):
        x, y = self._calculate_pos(widget)
        w, h = self.size_request()
        self.move(x, y)
        self.resize(w, h)
        self.show()

    # Public API

    def set_text(self, text):
        self._label.set_text(text)

    def hide(self):
        gtk.Window.hide(self)
        gobject.source_remove(self._show_timeout_id)
        self._show_timeout_id = -1

    def display(self, widget):
        if not self._label.get_text():
            return

        if self._show_timeout_id != -1:
            return

        self._show_timeout_id = gobject.timeout_add(500, self._real_display, widget)

    def set_tip (self, widget):
        self.widget = widget
        self._event_handler (self.widget)

    def add_widget (self, widget_to_add):
        self.widget_to_add = widget_to_add
        self.add(self.widget_to_add)

if __name__ == "__main__":
    base = Base()
    base.main()

def convert_time(raw):
    # Converts raw time to 'hh:mm:ss' with leading zeros as appropriate
    h, m, s = ['%02d' % c for c in (raw/3600, (raw%3600)/60, raw%60)]
    if h == '00':
        return m + ':' + s
    else:
        return h + ':' + m + ':' + s

def make_bold(s):
    if not (s.startswith('<b>') and s.endswith('</b>')):
        return '<b>%s</b>' % s
    else:
        return s

def make_unbold(s):
    if s.startswith('<b>') and s.endswith('</b>'):
        return s[3:-4]
    else:
        return s

def escape_html(s):
    s = s.replace('&', '&amp;')
    s = s.replace('<', '&lt;')
    s = s.replace('>', '&gt;')
    return s

def rmgeneric(path, __func__):
    try:
        __func__(path)
    except OSError, (errno, strerror):
        pass

def removeall(path):
    if not os.path.isdir(path):
        return

    files=os.listdir(path)

    for x in files:
        fullpath=os.path.join(path, x)
        if os.path.isfile(fullpath):
            f=os.remove
            rmgeneric(fullpath, f)
        elif os.path.isdir(fullpath):
            removeall(fullpath)
            f=os.rmdir
            rmgeneric(fullpath, f)

def start_dbus_interface(toggle=False):
    if HAVE_DBUS:
        exit_now = False
        try:
            session_bus = dbus.SessionBus()
            bus = dbus.SessionBus()
            retval = dbus.dbus_bindings.bus_request_name(session_bus.get_connection(), "org.MPD.Sonata", dbus.dbus_bindings.NAME_FLAG_DO_NOT_QUEUE)
            if retval in (dbus.dbus_bindings.REQUEST_NAME_REPLY_PRIMARY_OWNER, dbus.dbus_bindings.REQUEST_NAME_REPLY_ALREADY_OWNER):
                pass
            elif retval in (dbus.dbus_bindings.REQUEST_NAME_REPLY_EXISTS, dbus.dbus_bindings.REQUEST_NAME_REPLY_IN_QUEUE):
                exit_now = True
        except:
            pass
        if exit_now:
            obj = dbus.SessionBus().get_object('org.MPD', '/org/MPD/Sonata')
            if toggle:
                obj.toggle(dbus_interface='org.MPD.SonataInterface')
            else:
                print _("An instance of Sonata is already running.")
                obj.show(dbus_interface='org.MPD.SonataInterface')
            sys.exit()
