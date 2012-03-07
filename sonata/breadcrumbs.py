#!/usr/bin/env python

from gi.repository import Gtk, Gdk, GObject


class CrumbButton(Gtk.ToggleButton):
    """A ToggleButton tailored for use as a breadcrumb."""

    def __init__(self, image, label):
        GObject.GObject.__init__(self)

        self.set_properties(can_focus=False, relief=Gtk.ReliefStyle.NONE)

        # adapt Gtk.Button internal layout code:
        hbox = Gtk.HBox(spacing=2)
        align = Gtk.Alignment.new(0.5, 0.5, 0, 0)
        hbox.pack_start(image, False, False, 0)
        hbox.pack_start(label, True, True, 0)
        align.add(hbox)

        self.add(align)


class CrumbBox(Gtk.Box):
    """A box layout similar to Gtk.HBox, but specifically for breadcrumbs.

    * Crumbs in the middle are replaced with an ellipsis if necessary.
    * The root, parent, and current element are always kept visible.
    * The root and parent are put in a condensed form if necessary.
    * The current element is truncated if necessary.
    """
    __gtype_name__ = 'CrumbBox'

    def __init__(self, *args, **kwargs):
        GObject.GObject.__init__(self, *args, **kwargs)

        # FIXME i can't get an internal child ellipsis to render...
#		Gtk.widget_push_composite_child()
#		self.ellipsis = Gtk.Label(label="...")
#		self.ellipsis.props.visible = True
#		Gtk.widget_pop_composite_child()
#		self.ellipsis.set_parent(self)

    def do_get_preferred_width(self):
        """This gets called to determine the size we request"""
#		ellipsis_req = self.ellipsis.size_request()
        reqs = [w.size_request() for w in self]

        # This would request "natural" size:
#		pad = 0 if not reqs else (len(reqs)-1)*self.props.spacing
#		requisition.width  = sum(    [r[0] for r in reqs]) + pad
#		requisition.height = max([0]+[r[1] for r in reqs])
#		return

        # Request "minimum" size:
        height = max([0]+[r.height for r in reqs])

        if len(reqs) == 0: # empty
            width = 0
        elif len(reqs) < 3: # current crumb
            width = height
        elif len(reqs) == 3: # parent and current
            width = height + height + self.props.spacing
        elif len(reqs) == 4: # root, parent and current
            width = height + height + height + 2 * self.props.spacing
        elif len(reqs) > 4: # root, ellipsis, parent, current
            pad = 3 * self.props.spacing
            width = height + reqs[1].width + height + height + pad

        return width, width

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
        return req # XXX this can be less than hr, even <0

    def do_size_allocate(self, allocation):
        """This gets called to layout our child widgets"""
        x0, y0 = allocation.x, allocation.y
        w0, h0 = allocation.width, allocation.height

        crumbs = self.get_children()

        if len(crumbs) < 2:
            return

        # FIXME:
        self.ellipsis = crumbs.pop(1)
        hidden = [self.ellipsis]

        # Undo any earlier condensing
        if len(crumbs) > 0:
            self._uncondense(crumbs[0])
        if len(crumbs) > 1:
            self._uncondense(crumbs[-2])

        reqs = [w.get_child_requisition() for w in crumbs]

        # If necessary, condense the root crumb
        if self._req_sum(reqs) > w0 and len(crumbs) > 2:
            reqs[0] = self._condense(reqs[0], crumbs[0])

        # If necessary, replace an increasing amount of the
        # crumbs after the root with the ellipsis
        while self._req_sum(reqs) > w0:
            if self.ellipsis in hidden and len(crumbs) > 3:
                hidden = [crumbs.pop(1)]
                reqs.pop(1)
                crumbs.insert(1, self.ellipsis)
                req = self.ellipsis.get_child_requisition()
                reqs.insert(1, req)
            elif self.ellipsis in crumbs and len(crumbs) > 4:
                hidden.append(crumbs.pop(2))
                reqs.pop(2)
            else:
                break # don't remove the parent

        # If necessary, condense the parent crumb
        if self._req_sum(reqs) > w0 and len(crumbs) > 1:
            reqs[-2] = self._condense(reqs[-2], crumbs[-2])

        # If necessary, truncate the current crumb
        if self._req_sum(reqs) > w0:
            reqs[-1] = self._truncate(reqs[-1], self._req_sum(reqs) - w0)
            # Now we are at minimum width

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

#		def do_forall(self, internal, callback, data):
#			callback(self.ellipsis, data)
#			for w in self.get_children():
#				callback(w, data)

# this file can be run as a simple test program:
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
