#!/usr/bin/env python

from dogtail.procedural import *

def shoot(window, name):
        import os

        os.system("import -window \"%s\" -frame %s" % (window, name))


# Start sonata
run('sonata', appName='sonata')

for tab in 'Current', 'Info', 'Library', 'Playlists', 'Streams':
    click(tab)
    shoot("Sonata", "%s-tab.png" % tab)

# XXX take more screenshots

# FIXME how to open the popup and quit?
