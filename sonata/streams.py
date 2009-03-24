
"""
This module implements a user interface for bookmarking remote music
streams.

Example usage:
import streams
self.streams = streams.Streams(self.config, self.window, self.on_streams_button_press, self.on_add_item, self.settings_save, self.iterate_now, self.TAB_STREAMS)
streamswindow, streamsevbox = self.streams.get_widgets()
...
self.streams.populate()
...
"""

import gtk, pango

import misc, ui

class Streams(object):
    def __init__(self, config, window, on_streams_button_press, on_add_item, settings_save, iterate_now, TAB_STREAMS, new_tab):
        self.config = config
        self.window = window
        self.on_streams_button_press = on_streams_button_press
        self.on_add_item = on_add_item
        self.settings_save = settings_save
        self.iterate_now = iterate_now # XXX Do we really need this?

        # Streams tab
        self.streams = ui.treeview()
        self.streams_selection = self.streams.get_selection()
        self.streamswindow = ui.scrollwindow(add=self.streams)

        self.tab = new_tab(self.streamswindow, gtk.STOCK_NETWORK, TAB_STREAMS, self.streams)

        self.streams.connect('button_press_event', self.on_streams_button_press)
        self.streams.connect('row_activated', self.on_streams_activated)
        self.streams.connect('key-press-event', self.on_streams_key_press)

        # Initialize streams data and widget
        self.streamsdata = gtk.ListStore(str, str, str)
        self.streams.set_model(self.streamsdata)
        self.streams.set_search_column(1)
        self.streamsimg = gtk.CellRendererPixbuf()
        self.streamscell = gtk.CellRendererText()
        self.streamscell.set_property("ellipsize", pango.ELLIPSIZE_END)
        self.streamscolumn = gtk.TreeViewColumn()
        self.streamscolumn.pack_start(self.streamsimg, False)
        self.streamscolumn.pack_start(self.streamscell, True)
        self.streamscolumn.set_attributes(self.streamsimg, stock_id=0)
        self.streamscolumn.set_attributes(self.streamscell, markup=1)
        self.streams.append_column(self.streamscolumn)
        self.streams_selection.set_mode(gtk.SELECTION_MULTIPLE)

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
        streamsinfo = []
        for i in range(len(self.config.stream_names)):
            record = {}
            record["name"] = misc.escape_html(self.config.stream_names[i])
            record["uri"] = misc.escape_html(self.config.stream_uris[i])
            streamsinfo.append(record)
        streamsinfo.sort(key=lambda x: x["name"].lower()) # Remove case sensitivity
        for item in streamsinfo:
            self.streamsdata.append([gtk.STOCK_NETWORK, item["name"], item["uri"]])

    def on_streams_key_press(self, widget, event):
        if event.keyval == gtk.gdk.keyval_from_name('Return'):
            self.on_streams_activated(widget, widget.get_cursor()[0])
            return True

    def on_streams_activated(self, _treeview, _path, _column=0):
        self.on_add_item(None)

    def on_streams_edit(self, action):
        model, selected = self.streams_selection.get_selected_rows()
        try:
            streamname = misc.unescape_html(model.get_value(model.get_iter(selected[0]), 1))
            for i in range(len(self.config.stream_names)):
                if self.config.stream_names[i] == streamname:
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
        dialog = ui.dialog(title=None, parent=self.window, flags=gtk.DIALOG_MODAL | gtk.DIALOG_DESTROY_WITH_PARENT, buttons=(gtk.STOCK_CANCEL, gtk.RESPONSE_REJECT, gtk.STOCK_OK, gtk.RESPONSE_ACCEPT), role="streamsNew")
        if edit_mode:
            dialog.set_title(_("Edit Stream"))
        else:
            dialog.set_title(_("New Stream"))
        hbox = gtk.HBox()
        namelabel = ui.label(text=_('Stream name') + ':')
        hbox.pack_start(namelabel, False, False, 5)
        nameentry = ui.entry()
        if edit_mode:
            nameentry.set_text(self.config.stream_names[stream_num])
        hbox.pack_start(nameentry, True, True, 5)
        hbox2 = gtk.HBox()
        urllabel = ui.label(text=_('Stream URL') + ':')
        hbox2.pack_start(urllabel, False, False, 5)
        urlentry = ui.entry()
        if edit_mode:
            urlentry.set_text(self.config.stream_uris[stream_num])
        hbox2.pack_start(urlentry, True, True, 5)
        ui.set_widths_equal([namelabel, urllabel])
        dialog.vbox.pack_start(hbox)
        dialog.vbox.pack_start(hbox2)
        ui.show(dialog.vbox)
        response = dialog.run()
        if response == gtk.RESPONSE_ACCEPT:
            name = nameentry.get_text()
            uri = urlentry.get_text()
            if len(name.decode('utf-8')) > 0 and len(uri.decode('utf-8')) > 0:
                # Make sure this stream name doesn't already exit:
                i = 0
                for item in self.config.stream_names:
                    # Prevent a name collision in edit_mode..
                    if not edit_mode or (edit_mode and i != stream_num):
                        if item == name:
                            dialog.destroy()
                            if ui.show_msg(self.window, _("A stream with this name already exists. Would you like to replace it?"), _("New Stream"), 'newStreamError', gtk.BUTTONS_YES_NO) == gtk.RESPONSE_YES:
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
        self.iterate_now()
