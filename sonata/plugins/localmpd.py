
# this is the magic interpreted by Sonata, referring to construct_tab below:

### BEGIN PLUGIN INFO
# [plugin]
# plugin_format: 0, 0
# name: Local MPD
# version: 0, 0, 1
# description: A tab for controlling local MPD.
# author: Tuukka Hastrup
# author_email: Tuukka.Hastrup@iki.fi
# url: http://sonata.berlios.de
# license: GPL v3 or later
# [capabilities]
# tabs: construct_tab
### END PLUGIN INFO

import subprocess, locale

import gobject, gtk

from sonata.misc import escape_html

def update(label):
    # schedule next update
    gobject.timeout_add(1000, update, label)

    # don't update if not visible
    if not label.window or not label.window.is_viewable():
        return

    # XXX replace the shell commands with python code
    commands = [("Processes", ["sh", "-c", "ps wwu -C mpd"]),
            ("Networking", ["sh", "-c", "netstat -atue --numeric-hosts | egrep ':6600|^Proto'"]),
            ("Files", ["sh", "-c", "ls -lRh /etc/mpd.conf /var/lib/mpd"]),
            ]
    outputs = [(title, subprocess.Popen(command,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE
                        ).communicate())
           for title, command in commands]
    text = '\n'.join(["<b>%s</b>\n<tt>%s</tt><i>%s</i>\n" %
              (title, escape_html(stdout), escape_html(stderr))
              for title, (stdout, stderr) in outputs])
    label.set_markup(text.decode(locale.getpreferredencoding(),
                     'replace'))

# nothing magical here, this constructs the parts of the tab when called:
def construct_tab():
    vbox = gtk.VBox()
    label = gtk.Label()
    label.set_properties(xalign=0.0, xpad=5, yalign=0.0, ypad=5,
                 selectable=True)
    vbox.pack_start(label)

    update(label)

    window = gtk.ScrolledWindow()
    window.set_properties(hscrollbar_policy=gtk.POLICY_AUTOMATIC,
                  vscrollbar_policy=gtk.POLICY_AUTOMATIC)
    window.add_with_viewport(vbox)
    window.show_all()

    # (tab content, icon name, tab name, the widget to focus on tab switch)
    return (window, None, "Local MPD", None)
