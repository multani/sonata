
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
### END PLUGIN INFO

# nothing magical from here on

import gtk, pango

from sonata.misc import escape_html

songlabel = None

# this gets called when the plugin is loaded, enabled, or disabled:
def on_enable(state):
    global songlabel
    if state:
        songlabel = gtk.Label("No song info received yet.")
        songlabel.props.ellipsize = pango.ELLIPSIZE_END
    else:
        songlabel = None

# this constructs the parts of the tab when called:
def construct_tab():
    vbox = gtk.VBox()
    vbox.pack_start(gtk.Label("Hello world!"))
    vbox.pack_start(songlabel)
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
