
# this is the magic interpreted by Sonata, referring to construct_tab below:

### BEGIN PLUGIN INFO
# [plugin]
# plugin_format: 0, 0
# name: Test plugin
# version: 0, 0, 0
# [capabilities]
# tabs: construct_tab
### END PLUGIN INFO

import gtk

# nothing magical here, this constructs a tab as arguments to Base.new_tab:
def construct_tab():
    vbox = gtk.VBox()
    vbox.pack_start(gtk.Label("Hello world!"))
    vbox.pack_start(gtk.Label("(You can remove me at %s)" %
                  __file__.rstrip("c")))
    vbox.show_all()
    return (vbox, None, "Test plugin", None)
