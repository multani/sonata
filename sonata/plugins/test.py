
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
# tab_construct: tab_construct
# playing_song_observers: on_song_change
# lyrics_fetching: on_lyrics_fetch
### END PLUGIN INFO

# nothing magical from here on

from gi.repository import Gtk, Gdk, GdkPixbuf, GObject, Pango

from .misc import escape_html

songlabel = None
lyricslabel = None

# this gets called when the plugin is loaded, enabled, or disabled:
def on_enable(state):
    global songlabel, lyricslabel
    if state:
        songlabel = Gtk.Label("No song info received yet.")
        songlabel.props.ellipsize = Pango.ELLIPSIZE_END
        lyricslabel = Gtk.Label("No lyrics requests yet.")
        lyricslabel.props.ellipsize = Pango.ELLIPSIZE_END
    else:
        songlabel = None
        lyricslabel = None

# this constructs the parts of the tab when called:
def tab_construct():
    vbox = Gtk.VBox()
    vbox.pack_start(Gtk.Label("Hello world!"), True, True, 0)
    vbox.pack_start(songlabel, True, True, 0)
    vbox.pack_start(lyricslabel, True, True, 0)
    vbox.pack_start(Gtk.Label("(You can modify me at %s)" %
                  __file__.rstrip("c")), True, True, 0)
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
    GObject.timeout_add(0, callback, None,
                "%s doesn't have lyrics for %r." %
                (__name__, (artist, title)))
