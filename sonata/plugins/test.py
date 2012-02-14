
# this is the magic interpreted by Sonata, referring to on_enable etc. below:

### BEGIN PLUGIN INFO
# [plugin]
# plugin_format: 0, 0
# name: Test plugin
# version: 0, 0, 1
# description: A simple test plugin.
# author: Tuukka Hastrup
# author_email: Tuukka.Hastrup@iki.fi
# url: http://sonata.berlios.de
# license: GPL v3 or later
# [capabilities]
# enablables: on_enable
# tabs: construct_tab
# playing_song_observers: on_song_change
# lyrics_fetching: on_lyrics_fetch
### END PLUGIN INFO

# nothing magical from here on

from gi.repository import Gtk, Gdk, GdkPixbuf, GObject, Pango

from sonata.misc import escape_html

songlabel = None
lyricslabel = None

# this gets called when the plugin is loaded, enabled, or disabled:
def on_enable(state):
    global songlabel, lyricslabel
    if state:
        songlabel = gtk.Label("No song info received yet.")
        songlabel.props.ellipsize = pango.ELLIPSIZE_END
        lyricslabel = gtk.Label("No lyrics requests yet.")
        lyricslabel.props.ellipsize = pango.ELLIPSIZE_END
    else:
        songlabel = None
        lyricslabel = None

# this constructs the parts of the tab when called:
def construct_tab():
    vbox = gtk.VBox()
    vbox.pack_start(gtk.Label("Hello world!"))
    vbox.pack_start(songlabel)
    vbox.pack_start(lyricslabel)
    vbox.pack_start(gtk.Label("(You can modify me at %s)" %
                  __file__.rstrip("c")))
    vbox.show_all()

    # the return value goes off to Base.new_tab(page, stock, text, focus):
    # (tab content, icon name, tab name, the widget to focus on tab switch)
    return (vbox, None, "Test plugin", None)

# this gets called when a new song is playing:
def on_song_change(songinfo):
    if songinfo:
        songlabel.set_markup("<b>Info for currently playing song:</b>"+
                     "\n%s" % escape_html(repr(songinfo)))
    else:
        songlabel.set_text("Currently not playing any song.")
    songlabel.show()

# this gets requests for lyrics:
def on_lyrics_fetch(callback, artist, title):
    lyricslabel.set_markup(
        "Got request for lyrics for artist %r title %r." %
        (artist, title))

    # callback(lyrics, error)
    gobject.timeout_add(0, callback, None,
                "%s doesn't have lyrics for %r." %
                (__name__, (artist, title)))
