
import gtk

class CrumbBox(gtk.Box):
    """A box layout similar to gtk.HBox, but specifically for breadcrumbs.

    * Crumbs in the middle are replaced with an ellipsis if necessary.
    * The root, parent, and current element are always kept visible.
    * The root and parent are put in a condensed form if necessary.
    * The current element is truncated if necessary.
    """
    __gtype_name__ = 'CrumbBox'
    def __init__(self):
        gtk.Box.__init__(self)

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

        pad = 0 if not reqs else (len(reqs)-1)*self.props.spacing
        requisition.width  = sum(    [r[0] for r in reqs]) + pad
        requisition.height = max([0]+[r[1] for r in reqs])

    def _req_sum(self, reqs):
        pad = 0 if not reqs else (len(reqs)-1)*self.props.spacing
        return pad+sum([req[0] for req in reqs])

    def _condense(self, req):
        wr, hr = req
        return (hr, hr)

    def _truncate(self, req, amount):
        wr, hr = req
        return (wr-amount, hr)

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

        reqs = [w.get_child_requisition() for w in crumbs]

        # If necessary, condense the root crumb
        if self._req_sum(reqs) > w0:
            reqs[0] = self._condense(reqs[0])

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
            reqs[-2] = self._condense(reqs[-2])

        # If necessary, truncate the current crumb
        if self._req_sum(reqs) > w0:
            reqs[-1] = self._truncate(reqs[-1],
                                                  self._req_sum(reqs)-w0)
            # Now we are at minimum width

        x = 0
        for w, req in zip(crumbs, reqs):
            wr, _hr = req
            w.size_allocate(gtk.gdk.Rectangle(x0+x, y0, wr, h0))
            x += wr + self.props.spacing

        for w in hidden:
            w.size_allocate(gtk.gdk.Rectangle(-1, -1, 0, 0))

#		def do_forall(self, internal, callback, data):
#			callback(self.ellipsis, data)
#			for w in self.get_children():
#				callback(w, data)
