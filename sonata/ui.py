import logging

import sys
from gi.repository import Gtk, Pango, Gdk, GdkPixbuf, GObject


logger = logging.getLogger(__name__)


def label(text=None, textmn=None, markup=None, x=0, y=0.5, \
          wrap=False, select=False, w=-1, h=-1):
    # Defaults to left-aligned, vertically centered
    tmplabel = Gtk.Label()
    if text:
        tmplabel.set_text(text)
    elif markup:
        tmplabel.set_markup(markup)
    elif textmn:
        tmplabel.set_text_with_mnemonic(textmn)
    tmplabel.set_alignment(x, y)
    tmplabel.set_size_request(w, h)
    tmplabel.set_line_wrap(wrap)
    tmplabel.set_line_wrap_mode(Pango.WrapMode.WORD_CHAR)
    tmplabel.set_selectable(select)
    return tmplabel

def textview(text=None, edit=True, wrap=False):
    buf = Gtk.TextBuffer()
    tmptv = Gtk.TextView.new_with_buffer(buf)
    if text:
        buf.set_text(text)
    if wrap:
        tmptv.set_wrap_mode(Gtk.WrapMode.CHAR)
    tmptv.set_editable(edit)
    return tmptv

def expander(text=None, markup=None, expand=False, can_focus=True):
    tmpexp = Gtk.Expander()
    if text:
        tmpexp.set_label(text)
    elif markup:
        tmpexp.set_label(markup)
        tmpexp.set_use_markup(True)
    tmpexp.set_expanded(expand)
    tmpexp.set_property('can-focus', can_focus)
    return tmpexp

def eventbox(visible=False, add=None, w=-1, h=-1, state=None):
    tmpevbox = Gtk.EventBox()
    tmpevbox.set_visible_window(visible)
    tmpevbox.set_size_request(w, h)
    if state:
        tmpevbox.set_state(state)
    if add:
        tmpevbox.add(add)
    return tmpevbox

def button(text=None, stock=None, relief=None, can_focus=True, \
           hidetxt=False, img=None, w=-1, h=-1):
    tmpbut = Gtk.Button()
    if text:
        tmpbut.set_label(text)
    elif stock:
        tmpbut.set_label(stock)
        tmpbut.set_use_stock(True)
    tmpbut.set_use_underline(True)
    if img:
        tmpbut.set_image(img)
    if relief:
        tmpbut.set_relief(relief)
    tmpbut.set_property('can-focus', can_focus)
    if hidetxt:
        tmpbut.get_child().get_child().get_children()[1].set_text('')
    tmpbut.set_size_request(w, h)
    return tmpbut

def combo(items=None, active=None, changed_cb=None, wrap=1):
    tmpcb = Gtk.ComboBoxText.new()
    tmpcb = _combo_common(tmpcb, items, active, changed_cb, wrap)
    return tmpcb

def comboentry(items=None, active=None, changed_cb=None, wrap=1):
    tmpcbe = Gtk.combo_box_entry_new_text()
    tmpcbe = _combo_common(tmpcbe, items, active, changed_cb, wrap)
    return tmpcbe

def _combo_common(combobox, items, active, changed_cb, wrap):
    if items:
        for item in items:
            combobox.append_text(item)
    if active is not None:
        combobox.set_active(active)
    if changed_cb:
        combobox.connect('changed', changed_cb)
    combobox.set_wrap_width(wrap)
    return combobox

def togglebutton(text=None, underline=False, \
                 can_focus=True):
    tmptbut = Gtk.ToggleButton()
    if text:
        tmptbut.set_label(text)
    tmptbut.set_use_underline(underline)
    tmptbut.set_property('can-focus', can_focus)
    return tmptbut

def image(stock=None, stocksize=Gtk.IconSize.MENU, w=-1, h=-1, \
          x=0.5, y=0.5, pb=None):
    if stock:
        tmpimg = Gtk.Image.new_from_stock(stock, stocksize)
    elif pb:
        tmpimg = Gtk.Image.new_from_pixbuf(pb)
    else:
        tmpimg = Gtk.Image()
    tmpimg.set_size_request(w, h)
    tmpimg.set_alignment(x, y)
    return tmpimg

def scrollwindow(policy_x=Gtk.PolicyType.AUTOMATIC, policy_y=Gtk.PolicyType.AUTOMATIC, \
                 shadow=Gtk.ShadowType.IN, w=-1, h=-1, add=None, addvp=None):
    tmpsw = Gtk.ScrolledWindow()
    tmpsw.set_policy(policy_x, policy_y)
    tmpsw.set_shadow_type(shadow)
    tmpsw.set_size_request(w, h)
    if add:
        tmpsw.add(add)
    elif addvp:
        tmpsw.add_with_viewport(addvp)
    return tmpsw

def dialog(title=None, parent=None, flags=0, buttons=None, default=None, \
           resizable=True, w=-1, h=-1, role=None):
    tmpdialog = Gtk.Dialog(title, parent, flags, buttons)
    if default is not None:
        tmpdialog.set_default_response(default)
    tmpdialog.set_resizable(resizable)
    tmpdialog.set_size_request(w, h)
    if role:
        tmpdialog.set_role(role)
    return tmpdialog

def entry(text=None, password=False, w=-1, h=-1, changed_cb=None):
    tmpentry = Gtk.Entry()
    if text:
        tmpentry.set_text(text)
    if password:
        tmpentry.set_visibility(False)
    tmpentry.set_size_request(w, h)
    if changed_cb:
        tmpentry.connect('changed', changed_cb)
    return tmpentry

def treeview(hint=True, reorder=False, search=True, headers=False):
    tmptv = Gtk.TreeView()
    tmptv.set_rules_hint(hint)
    tmptv.set_reorderable(reorder)
    tmptv.set_enable_search(search)
    tmptv.set_headers_visible(headers)
    return tmptv

def iconview(col=None, space=None, margin=None, itemw=None, selmode=None):
    tmpiv = Gtk.IconView()
    if col:
        tmpiv.set_columns(col)
    if space:
        tmpiv.set_spacing(space)
    if margin:
        tmpiv.set_margin(margin)
    if itemw:
        tmpiv.set_item_width(itemw)
    if selmode:
        tmpiv.set_selection_mode(selmode)
    return tmpiv

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

def focus(widget):
    widget.grab_focus()

def quote_label(label_value):
    """Quote the content of a label so that it's safe to display."""

    # Don't inadvertently create accelerators if the value contains a "_"
    result = label_value.replace("_", "__")

    return result

def set_widths_equal(widgets):
    # Assigns the same width to all passed widgets in the list, where
    # the width is the maximum width across widgets.
    max_width = 0
    for widget in widgets:
        if widget.size_request().width > max_width:
            max_width = widget.size_request().width
    for widget in widgets:
        widget.set_size_request(max_width, -1)

def icon(factory, icon_name, path):
    # Either the file or fullpath must be supplied, but not both:
    sonataset = Gtk.IconSet()
    filename = [path]
    icons = [Gtk.IconSource() for i in filename]
    for i, iconsource in enumerate(icons):
        iconsource.set_filename(filename[i])
        sonataset.add_source(iconsource)
    factory.add(icon_name, sonataset)
    factory.add_default()

def change_cursor(cursortype):
    for w in Gtk.Window.list_toplevels():
        gdk_window = w.get_window()
        # some toplevel windows have no drawing area
        if gdk_window != None:
            gdk_window.set_cursor(cursortype)
