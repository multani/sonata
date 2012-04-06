
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

import subprocess, locale, os
from pwd import getpwuid

from gi.repository import GObject, Gtk

from sonata.misc import escape_html

class Netstat(object):
    TCP_STATE_NAMES = ("ESTABLISHED SYN_SENT SYN_RECV FIN_WAIT1 FIN_WAIT2 "
               "TIME_WAIT CLOSE CLOSE_WAIT LAST_ACK LISTEN CLOSING"
               .split())
    def __init__(self):
        self.connections = None

    def _addr(self, part):
        host, port = part.split(':')
        port = str(int(port, 16))
        if len(host) == 8:
            parts = [host[0:2], host[2:4], host[4:6], host[6:8]]
            parts = [str(int(x, 16)) for x in parts]
            host = '.'.join(reversed(parts))
        else:
            host = "IPV6" # FIXME
        if host == '0.0.0.0':
            host = '*'
        elif host == '127.0.0.1':
            host = 'localhost'
        if port == '0':
            port = '*'
        return (host, port)

    def read_connections(self):
        def fromhex(x):
            return int(x, 16)
        self.connections = []
        for name in '/proc/net/tcp', '/proc/net/tcp6':
            f = open(name,'rt')
            headings = f.readline()
            for line in f:
                parts = line.split()
                if len(parts) < 10:
                    continue # broken line
                local = self._addr(parts[1])
                remote = self._addr(parts[2])
                state = self.TCP_STATE_NAMES[
                    fromhex(parts[3])-1]
                queueparts = parts[4].split(':')
                queues = tuple(map(fromhex,queueparts))
                uid, _timeout, inode = map(int, parts[7:10])
                if len(parts[1].split(":")[0]) == 8:
                    proto = "tcp"
                else:
                    proto = "tcp6"
                self.connections += [(proto, local, remote, state, queues, uid, inode)]

    def format_connections(self):
        t = "%-5s %6s %6s %15s:%-5s %15s:%-5s  %-11s  %s"
        headings = "Proto Send-Q Recv-Q Local Port Remote Port State User".split()
        return (t % tuple(headings) + '\n' +
            '\n'.join([t % (proto, rxq, txq, localh, localp, remoteh, remotep, state, getpwuid(uid)[0])
                   for proto, (localh, localp), (remoteh, remotep), state, (txq, rxq), uid, inode in self.connections
                   if localp == '6600' or remotep == '6600'
                   or getpwuid(uid)[0] == 'mpd']))

def update(label):
    # schedule next update
    GObject.timeout_add(1000, update, label)

    # don't update if not visible
    if not hasattr(label, "window") or not label.get_window().is_viewable():
        return

    netstat = Netstat()
    netstat.read_connections()
    netstats = netstat.format_connections()

    # XXX replace the shell commands with python code
    commands = [("Processes", "ps wwu -C mpd".split()),
            ("Files", ["sh", "-c", "ls -ldh /etc/mpd.conf /var/lib/mpd /var/lib/mpd/* /var/lib/mpd/*/*"]),
            ]
    outputs = [(title, subprocess.Popen(command,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE
                        ).communicate())
           for title, command in commands]

    sections = [outputs[0], ("Networking", (netstats, "")), outputs[1]]
    text = '\n'.join(["<b>%s</b>\n<tt>%s</tt><i>%s</i>\n" %
              (title, escape_html(stdout), escape_html(stderr))
              for title, (stdout, stderr) in sections])
    label.set_markup(text.decode(locale.getpreferredencoding(),
                     'replace'))

# nothing magical here, this constructs the parts of the tab when called:
def construct_tab():
    builder = Gtk.Builder()
    builder.add_from_file('{0}/ui/localmpd.ui'.format(
        os.path.dirname(__file__)))
    builder.set_translation_domain('sonata')
    editbutton = builder.get_object('localmpd_edit_button')
    editbutton.connect('clicked', lambda *args:subprocess.Popen(
            ["gksu", "gedit", "/etc/mpd.conf"]))
    restartbutton = builder.get_object('localmpd_restart_button')
    restartbutton.connect('clicked', lambda *args:subprocess.Popen(
            ["gksu", "service", "mpd", "restart"]))

    label = builder.get_object('localmpd_data_label')
    update(label)

    window = builder.get_object('localmpd_scrolledwindow')
    window.show_all()
    tab_widget = builder.get_object('localmpd_tab_h_box')

    # (tab content, icon name, tab name, the widget to focus on tab switch)
    return (window, tab_widget, "Local MPD", None)
