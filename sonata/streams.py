
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

import os

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

        self.builder = Gtk.Builder()
        self.builder.add_from_file('{0}/ui/streams.ui'.format(
            os.path.dirname(ui.__file__)))
        self.builder.set_translation_domain('sonata')

        # Streams tab
        self.streams = self.builder.get_object('streams_page_treeview')
        self.streams_selection = self.streams.get_selection()
        self.streamswindow = self.builder.get_object('streams_page_scrolledwindow')

        self.tab_widget = self.builder.get_object('streams_tab_h_box')
        self.tab_label = self.builder.get_object('streams_tab_label')
        self.tab_label.set_text(TAB_STREAMS)

        self.tab = (self.streamswindow, self.tab_widget, TAB_STREAMS,
                    self.streams)

        self.streams.connect('button_press_event', self.on_streams_button_press)
        self.streams.connect('row_activated', self.on_streams_activated)
        self.streams.connect('key-press-event', self.on_streams_key_press)

        # Initialize streams data and widget
        self.streamsdata = self.builder.get_object('streams_liststore')
        self.streams.set_search_column(1)

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
        dialog = self.builder.get_object('streams_add_dialog')
        dialog.set_transient_for(self.window)
        # FIXME GNOME 3+'s default theme doesn't show this... does Gtk+ 3+ ever?
        # If not, migrate to a label over the entries?
        if edit_mode:
            dialog.set_title(_("Edit Stream"))
        else:
            dialog.set_title(_("New Stream"))
        nameentry = self.builder.get_object('streams_add_title_entry')
        nametext = ''
        if edit_mode:
            nametext = self.config.stream_names[stream_num]
        nameentry.set_text(nametext)
        urlentry = self.builder.get_object('streams_add_url_entry')
        urltext = ''
        if edit_mode:
            urltext = self.config.stream_uris[stream_num]
        urlentry.set_text(urltext)
        vbox = self.builder.get_object('streams_add_v_box')
        vbox.show_all()
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
        dialog.hide()
