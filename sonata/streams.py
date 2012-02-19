
"""
This module implements a user interface for bookmarking remote music
streams.

Example usage:
import streams
self.streams = streams.Streams(self.config, self.window, self.on_streams_button_press, self.on_add_item, self.settings_save, self.TAB_STREAMS)
streamswindow, streamsevbox = self.streams.get_widgets()
...
self.streams.populate()
...
"""

from gi.repository import Gtk, Gdk, Pango

from sonata import misc, ui

from sonata.pluginsystem import pluginsystem, BuiltinPlugin

class Streams(object):
    def __init__(self, config, window, on_streams_button_press, on_add_item, settings_save, TAB_STREAMS):
        self.config = config
        self.window = window
        self.on_streams_button_press = on_streams_button_press
        self.on_add_item = on_add_item
        self.settings_save = settings_save

        # Streams tab
        self.streams = ui.treeview()
        self.streams_selection = self.streams.get_selection()
        self.streamswindow = ui.scrollwindow(add=self.streams)

        self.tab = (self.streamswindow, Gtk.STOCK_NETWORK, TAB_STREAMS, self.streams)

        self.streams.connect('button_press_event', self.on_streams_button_press)
        self.streams.connect('row_activated', self.on_streams_activated)
        self.streams.connect('key-press-event', self.on_streams_key_press)

        # Initialize streams data and widget
        self.streamsdata = Gtk.ListStore(str, str, str)
        self.streams.set_model(self.streamsdata)
        self.streams.set_search_column(1)
        self.streamsimg = Gtk.CellRendererPixbuf()
        self.streamscell = Gtk.CellRendererText()
        self.streamscell.set_property("ellipsize", Pango.EllipsizeMode.END)
        self.streamscolumn = Gtk.TreeViewColumn()
        self.streamscolumn.pack_start(self.streamsimg, False)
        self.streamscolumn.pack_start(self.streamscell, True)
        self.streamscolumn.add_attribute(self.streamsimg, "stock_id", 0)
        self.streamscolumn.add_attribute(self.streamscell, "markup", 1)
        self.streams.append_column(self.streamscolumn)
        self.streams_selection.set_mode(Gtk.SelectionMode.MULTIPLE)

        pluginsystem.plugin_infos.append(BuiltinPlugin(
                'streams', "Streams", "A tab for streams.",
                {'tabs': 'construct_tab'}, self))

    def construct_tab(self):
        self.streamswindow.show_all()
        return self.tab

    def get_model(self):
        return self.streamsdata

    def get_widgets(self):
        return self.streamswindow

    def get_treeview(self):
        return self.streams

    def get_selection(self):
        return self.streams_selection

    def populate(self):
        self.streamsdata.clear()
        streamsinfo = [{'name' : misc.escape_html(name),
                'uri' : misc.escape_html(uri)}
                for name, uri in zip(self.config.stream_names,
                             self.config.stream_uris)]
        streamsinfo.sort(key=lambda x: x["name"].lower()) # Remove case sensitivity
        for item in streamsinfo:
            self.streamsdata.append([Gtk.STOCK_NETWORK, item["name"], item["uri"]])

    def on_streams_key_press(self, widget, event):
        if event.keyval == Gdk.keyval_from_name('Return'):
            self.on_streams_activated(widget, widget.get_cursor()[0])
            return True

    def on_streams_activated(self, _treeview, _path, _column=0):
        self.on_add_item(None)

    def on_streams_edit(self, action):
        model, selected = self.streams_selection.get_selected_rows()
        try:
            streamname = misc.unescape_html(model.get_value(model.get_iter(selected[0]), 1))
            for i, name in enumerate(self.config.stream_names):
                if name == streamname:
                    self.on_streams_new(action, i)
                    return
        except:
            pass

    def on_streams_new(self, _action, stream_num=-1):
        if stream_num > -1:
            edit_mode = True
        else:
            edit_mode = False
        # Prompt user for playlist name:
        dialog = ui.dialog(title=None, parent=self.window, flags=Gtk.DialogFlags.MODAL | Gtk.DialogFlags.DESTROY_WITH_PARENT, buttons=(Gtk.STOCK_CANCEL, Gtk.ResponseType.REJECT, Gtk.STOCK_OK, Gtk.ResponseType.ACCEPT), role="streamsNew")
        if edit_mode:
            dialog.set_title(_("Edit Stream"))
        else:
            dialog.set_title(_("New Stream"))
        hbox = Gtk.HBox()
        namelabel = ui.label(text=_('Stream name:'))
        hbox.pack_start(namelabel, False, False, 5)
        nameentry = ui.entry()
        if edit_mode:
            nameentry.set_text(self.config.stream_names[stream_num])
        hbox.pack_start(nameentry, True, True, 5)
        hbox2 = Gtk.HBox()
        urllabel = ui.label(text=_('Stream URL:'))
        hbox2.pack_start(urllabel, False, False, 5)
        urlentry = ui.entry()
        if edit_mode:
            urlentry.set_text(self.config.stream_uris[stream_num])
        hbox2.pack_start(urlentry, True, True, 5)
        ui.set_widths_equal([namelabel, urllabel])
        dialog.vbox.pack_start(hbox, True, True, 0)
        dialog.vbox.pack_start(hbox2, True, True, 0)
        ui.show(dialog.vbox)
        response = dialog.run()
        if response == Gtk.ResponseType.ACCEPT:
            name = nameentry.get_text()
            uri = urlentry.get_text()
            if len(name) > 0 and len(uri) > 0:
                # Make sure this stream name doesn't already exit:
                i = 0
                for item in self.config.stream_names:
                    # Prevent a name collision in edit_mode..
                    if not edit_mode or (edit_mode and i != stream_num):
                        if item == name:
                            dialog.destroy()
                            if ui.show_msg(self.window, _("A stream with this name already exists. Would you like to replace it?"), _("New Stream"), 'newStreamError', Gtk.ButtonsType.YES_NO) == Gtk.ResponseType.YES:
                                # Pop existing stream:
                                self.config.stream_names.pop(i)
                                self.config.stream_uris.pop(i)
                            else:
                                return
                    i = i + 1
                if edit_mode:
                    self.config.stream_names.pop(stream_num)
                    self.config.stream_uris.pop(stream_num)
                self.config.stream_names.append(name)
                self.config.stream_uris.append(uri)
                self.populate()
                self.settings_save()
        dialog.destroy()
