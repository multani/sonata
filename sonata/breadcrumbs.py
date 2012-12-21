#!/usr/bin/env python

from gi.repository import Gtk, Gdk, Pango


class CrumbButton(Gtk.ToggleButton):
    """A ToggleButton tailored for use as a breadcrumb."""

    def __init__(self, image, label):
        Gtk.ToggleButton.__init__(self)

        self.set_properties(can_focus=False, relief=Gtk.ReliefStyle.NONE)
        self.label = label

        # adapt Gtk.Button internal layout code:
        hbox = Gtk.HBox(spacing=2)
        align = Gtk.Alignment.new(0.5, 0.5, 0, 0)
        hbox.pack_start(image, False, False, 0)
        hbox.pack_start(label, True, True, 0)
        align.add(hbox)

        self.add(align)

    def ellipsize(self, do_ellipsize=True):
        can_ellipsize = len(self.label.get_text()) >= 15
        if do_ellipsize and can_ellipsize:
            mode = Pango.EllipsizeMode.END
            width_chars = 15
        else:
            mode = Pango.EllipsizeMode.NONE
            width_chars = -1

        self.label.set_ellipsize(mode)
        self.label.set_max_width_chars(width_chars)
        self.label.set_width_chars(width_chars)
        return do_ellipsize and can_ellipsize


class CrumbBox(Gtk.Box):
    """A box layout similar to Gtk.HBox, but specifically for breadcrumbs.

    * Crumbs in the middle are replaced with an ellipsis if necessary.
    * The root, parent, and current element are always kept visible.
    * The root and parent are put in a condensed form if necessary.
    * The current element is truncated if necessary.
    """
    __gtype_name__ = 'CrumbBox'

    def __init__(self, *args, **kwargs):
        Gtk.Box.__init__(self, *args, **kwargs)

    def set_crumb_break(self, widget):
        self.crumb_break = widget

    def do_get_preferred_width(self):
        """This gets called to determine the size we request"""
        reqs = [w.size_request() for w in self]

        # Request "minimum" size:
        heights = [r.height for r in reqs]
        height = max([0] + heights)
        widths = [r.width for r in reqs]
        width = max([0] + widths)
        natural_width = self._req_sum(reqs)

        if len(reqs) == 0: # empty
            width = 0
        elif len(reqs) < 3: # current crumb
            width = natural_width
        elif len(reqs) == 3: # parent and current
            width = 2 * height + self.props.spacing
        elif len(reqs) == 4: # root, parent and current
            width = 3 * height + 2 * self.props.spacing
        elif len(reqs) > 4: # root, break, parent, current
            pad = 3 * self.props.spacing
            width = 3 * height + reqs[1].width + pad

        return width, natural_width

    def _req_sum(self, reqs):
        pad = 0 if not reqs else (len(reqs)-1) * self.props.spacing
        return pad + sum([req.width for req in reqs])

    def _condense(self, req, w):
# FIXME show and hide cause a fight in an infinite loop
#		try:
#			w.get_child().get_child().get_children()[1].hide()
#		except (AttributeError, IndexError):
#			pass
        return req # XXX simplistic: set square size for now

    def _uncondense(self, w):
        pass
#		try:
#			w.get_child().get_child().get_children()[1].show()
#		except (AttributeError, IndexError):

    def _truncate(self, req, amount):
        req.width -= amount
        if req.width < 0:
            req.width = 0
        return req

    def do_size_allocate(self, allocation):
        """This gets called to layout our child widgets"""
        # XXX allocation seems to stick at some width, no matter how much wider
        # the window gets, but if we go down the path and back, it goes higher?
        # Gtk bug?
        x0, y0 = allocation.x, allocation.y
        w0, h0 = allocation.width, allocation.height

        crumbs = self.get_children()

        if len(crumbs) < 2:
            if self.crumb_break:
                self.crumb_break.hide()
            Gtk.Box.do_size_allocate(self, allocation)
            return

        # Undo any earlier condensing and ellipsizing
        for crumb in crumbs:
            crumb.ellipsize(False)
        if len(crumbs) > 2:
            self._uncondense(crumbs[-2])

        reqs = [w.get_child_requisition() for w in crumbs]

        # Step 1: Try ellipsizing
        if self._req_sum(reqs) > w0:
            # We want a descending sort by widths
            # We ellipsize biggest to smallest to preserve the most crumbs
            crumbsorted = [(w.width, crumb) for w, crumb in zip(reqs, crumbs)]
            sorted(crumbsorted, key=lambda crumb: crumb[0], reverse=True)
            for x, crumb in crumbsorted:
                if crumb.ellipsize():
                    i = crumbs.index(crumb)
                    reqs[i] = crumb.get_child_requisition()
                    if self._req_sum(reqs) < w0:
                        break

        # Step 2: remove as many crumbs as needed except:
        # Never remove the parent or current
        hidden = []
        while self._req_sum(reqs) > w0:
            if len(crumbs) > 2:
                    hidden.append(crumbs.pop(0))
                    reqs.pop(0)
            else:
                break # don't remove the parent

        # If necessary, condense the parent crumb
        if self._req_sum(reqs) > w0 and len(crumbs) > 2:
            reqs[-2] = self._condense(reqs[-2], crumbs[-2])

        # If necessary, truncate the current crumb
        if self._req_sum(reqs) > w0:
            reqs[-1] = self._truncate(reqs[-1], self._req_sum(reqs) - w0)
            # Now we are at minimum width

        # Only show the break (ellipsis) if we have hidden crumbs
        if self.crumb_break:
            if len(hidden):
                self.crumb_break.show()
            else:
                self.crumb_break.hide()

        x = 0
        for w, req in zip(crumbs, reqs):
            alloc = Gdk.Rectangle()
            alloc.x = x0 + x
            alloc.y = y0
            alloc.width = req.width
            alloc.height = h0
            w.size_allocate(alloc)
            w.show()
            x += req.width + self.props.spacing

        for w in hidden:
            alloc = Gdk.Rectangle()
            alloc.x = -1
            alloc.y = -1
            alloc.width = 0
            alloc.height = 0
            w.size_allocate(alloc)
            w.hide()

        Gtk.Box.do_size_allocate(self, allocation)

# this file can be run as a simple test program:
# FIXME or XXX this is out of sync with the rest of file
if __name__ == '__main__':
    w = Gtk.Window()
    crumbs = CrumbBox(spacing=2)

    items = [
        (Gtk.STOCK_HARDDISK, "Filesystem"),
        (None, None), # XXX for ellipsis
        (Gtk.STOCK_OPEN, "home"),
        (Gtk.STOCK_OPEN, "user"),
        (Gtk.STOCK_OPEN, "music"),
        (Gtk.STOCK_OPEN, "genre"),
        (Gtk.STOCK_OPEN, "artist"),
        (Gtk.STOCK_OPEN, "album"),
        ]
    for stock, text in items:
        if stock:
            image = Gtk.Image.new_from_stock(stock,
                             Gtk.IconSize.MENU)
            crumbs.pack_start(CrumbButton(image, Gtk.Label(label=text)), False, False, 0)
        else:
            crumbs.pack_start(Gtk.Label("..."), False, False, 0)

    w.add(crumbs)
    w.connect('hide', Gtk.main_quit)
    w.show_all()

    Gtk.main()
