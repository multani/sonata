import logging
import os
import pkg_resources
import sys

from gi.repository import Gtk, Gdk


logger = logging.getLogger(__name__)


def builder(ui_file, relative_to='.'):
    builder = Gtk.Builder()
    builder.set_translation_domain('sonata')
    ui_path = pkg_resources.resource_filename(
        'sonata', os.path.join(relative_to, 'ui', ui_file + ".glade"))
    logger.debug('Loading %s', ui_path)
    builder.add_from_file(ui_path)

    return builder

def css_provider(css_file, relative_to='.'):
    provider = Gtk.CssProvider()
    css_path = pkg_resources.resource_filename(
        'sonata', os.path.join(relative_to, 'ui', css_file + ".css"))
    logger.debug('Loading %s', css_path)
    provider.load_from_path(css_path)
    screen = Gdk.Screen.get_default()
    context = Gtk.StyleContext()
    context.add_provider_for_screen(screen, provider,
                                    Gtk.STYLE_PROVIDER_PRIORITY_USER)

    return provider

def builder_string(ui_file, relative_to='.'):
    ui_path = pkg_resources.resource_filename(
        'sonata', os.path.join(relative_to, 'ui', ui_file + ".glade"))
    logger.debug('Loading %s', ui_path)

    with open(ui_path, 'r') as builder_file:
        string = builder_file.read()
    return string

def show_msg(owner, message, title, role, buttons, default=None, response_cb=None):
    is_button_list = hasattr(buttons, '__getitem__')
    if not is_button_list:
        messagedialog = Gtk.MessageDialog(owner, Gtk.DialogFlags.MODAL|Gtk.DialogFlags.DESTROY_WITH_PARENT, Gtk.MessageType.WARNING, buttons, message)
    else:
        messagedialog = Gtk.MessageDialog(owner, Gtk.DialogFlags.MODAL|Gtk.DialogFlags.DESTROY_WITH_PARENT, Gtk.MessageType.WARNING, message_format=message)
        i = 0
        while i < len(buttons):
            messagedialog.add_button(buttons[i], buttons[i+1])
            i += 2
    messagedialog.set_title(title)
    messagedialog.set_role(role)
    if default is not None:
        messagedialog.set_default_response(default)
    if response_cb:
        messagedialog.connect("response", response_cb)
    response = messagedialog.run()
    value = response
    messagedialog.destroy()
    return value

def dialog_destroy(dialog_widget, _response_id):
    dialog_widget.destroy()

def show(widget):
    widget.set_no_show_all(False)
    widget.show_all()

def hide(widget):
    #widget.hide_all()
    widget.hide()
    widget.set_no_show_all(True)

def quote_label(label_value):
    """Quote the content of a label so that it's safe to display."""

    # Don't inadvertently create accelerators if the value contains a "_"
    result = label_value.replace("_", "__")

    return result

def change_cursor(cursortype):
    for w in Gtk.Window.list_toplevels():
        gdk_window = w.get_window()
        # some toplevel windows have no drawing area
        if gdk_window != None:
            gdk_window.set_cursor(cursortype)

def set_entry_invalid(editable):
    color = Gdk.RGBA()
    color.parse("red")
    editable.override_color(Gtk.StateFlags.NORMAL, color)

def reset_entry_marking(editable):
    editable.override_color(Gtk.StateFlags.NORMAL, None)


def icon(name):
    return Gtk.IconFactory.lookup_default(name)
