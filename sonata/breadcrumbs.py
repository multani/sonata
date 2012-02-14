#!/usr/bin/env python

from gi.repository import Gtk, Gdk, GObject


class CrumbButton(gtk.ToggleButton):
    """A ToggleButton tailored for use as a breadcrumb."""

    def __init__(self, image, label):
        gtk.ToggleButton.__init__(self)

        self.set_properties(can_focus=False, relief=gtk.RELIEF_NONE)

        # adapt gtk.Button internal layout code:
        hbox = gtk.HBox(spacing=2)
        align = gtk.Alignment(xalign=0.5, yalign=0.5)
        hbox.pack_start(image, False, False)
        hbox.pack_start(label, True, True)
        align.add(hbox)

        self.add(align)


class CrumbBox(gtk.Box):
    """A box layout similar to gtk.HBox, but specifically for breadcrumbs.

    * Crumbs in the middle are replaced with an ellipsis if necessary.
    * The root, parent, and current element are always kept visible.
    * The root and parent are put in a condensed form if necessary.
    * The current element is truncated if necessary.
    """
    __gtype_name__ = 'CrumbBox'

    def __init__(self, *args, **kwargs):
        gtk.Box.__init__(self, *args, **kwargs)

        # FIXME i can't get an internal child ellipsis to render...
#		gtk.widget_push_composite_child()
#		self.ellipsis = gtk.Label("...")
#		self.ellipsis.props.visible = True
#		gtk.widget_pop_composite_child()
#		self.ellipsis.set_parent(self)

    def do_size_request(self, requisition):
        """This gets called to determine the size we request"""
#		ellipsis_req = self.ellipsis.size_request()
        reqs = [w.size_request() for w in self]

        # This would request "natural" size:
#		pad = 0 if not reqs else (len(reqs)-1)*self.props.spacing
#		requisition.width  = sum(    [r[0] for r in reqs]) + pad
#		requisition.height = max([0]+[r[1] for r in reqs])
#		return

        # Request "minimum" size:

        height = max([0] + [r[1] for r in reqs])

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
            width = height + reqs[1][0] + height + height + pad

        requisition.width = width
        requisition.height = height

    def _req_sum(self, reqs):
        pad = 0 if not reqs else (len(reqs)-1) * self.props.spacing
        return pad + sum([req[0] for req in reqs])

    def _condense(self, req, w):
# FIXME show and hide cause a fight in an infinite loop
#		try:
#			w.get_child().get_child().get_children()[1].hide()
#		except (AttributeError, IndexError):
#			pass
        wr, hr = req
        return (hr, hr) # XXX simplistic: set square size for now

    def _uncondense(self, w):
#		try:
#			w.get_child().get_child().get_children()[1].show()
#		except (AttributeError, IndexError):
            pass

    def _truncate(self, req, amount):
        wr, hr = req
        return (wr - amount, hr) # XXX this can be less than hr, even <0

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
            wr, _hr = req
            w.size_allocate(gtk.gdk.Rectangle(x0 + x, y0, wr, h0))
            w.show()
            x += wr + self.props.spacing

        for w in hidden:
            w.size_allocate(gtk.gdk.Rectangle(-1, -1, 0, 0))
            w.hide()

#		def do_forall(self, internal, callback, data):
#			callback(self.ellipsis, data)
#			for w in self.get_children():
#				callback(w, data)

# this file can be run as a simple test program:
if __name__ == '__main__':
    w = gtk.Window()
    crumbs = CrumbBox(spacing=2)

    items = [
        (gtk.STOCK_HARDDISK, "Filesystem"),
        (None, None), # XXX for ellipsis
        (gtk.STOCK_OPEN, "home"),
        (gtk.STOCK_OPEN, "user"),
        (gtk.STOCK_OPEN, "music"),
        (gtk.STOCK_OPEN, "genre"),
        (gtk.STOCK_OPEN, "artist"),
        (gtk.STOCK_OPEN, "album"),
        ]
    for stock, text in items:
        if stock:
            image = gtk.image_new_from_stock(stock,
                             gtk.ICON_SIZE_MENU)
            crumbs.pack_start(CrumbButton(image, gtk.Label(text)))
        else:
            crumbs.pack_start(gtk.Label("..."))

    w.add(crumbs)
    w.connect('hide', gtk.main_quit)
    w.show_all()

    gtk.main()
