
# this is the magic interpreted by Sonata, referring to construct_tab below:

### BEGIN PLUGIN INFO
# [plugin]
# plugin_format: 0, 0
# name: Test plugin
# version: 0, 0, 0
# description: A simple test plugin.
# author: Tuukka Hastrup
# author_email: Tuukka.Hastrup@iki.fi
# url: http://sonata.berlios.de
# [capabilities]
# tabs: construct_tab
### END PLUGIN INFO

import gtk

# nothing magical here, this constructs the parts of the tab when called:
def construct_tab():
    vbox = gtk.VBox()
    vbox.pack_start(gtk.Label("Hello world!"))
    vbox.pack_start(gtk.Label("(You can modify me at %s)" %
                  __file__.rstrip("c")))
    vbox.show_all()

    # the return value goes off to Base.new_tab(page, stock, text, focus):
    # (tab content, icon name, tab name, the widget to focus on tab switch)
    return (vbox, None, "Test plugin", None)
