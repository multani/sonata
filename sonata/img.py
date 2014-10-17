# Copyright 2006-2009 Scott Horowitz <stonecrest@gmail.com>
# Copyright 2009-2014 Jonathan Ballet <jon@multani.info>
#
# This file is part of Sonata.
#
# Sonata is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# Sonata is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with Sonata.  If not, see <http://www.gnu.org/licenses/>.

import itertools
import os

from gi.repository import Gtk, Gdk, GdkPixbuf, GLib

from sonata import consts


VALID_EXTENSIONS =  set(
    itertools.chain.from_iterable(
        fmt.get_extensions()
        for fmt in GdkPixbuf.Pixbuf.get_formats()
    )
)


def valid_image(filename):
    return bool(GdkPixbuf.Pixbuf.get_file_info(filename))


def get_pixbuf_of_size(pixbuf, size):
    # Creates a pixbuf that fits in the specified square of sizexsize
    # while preserving the aspect ratio
    # Returns tuple: (scaled_pixbuf, actual_width, actual_height)
    image_width = pixbuf.get_width()
    image_height = pixbuf.get_height()
    if image_width > image_height:
        if image_width > size:
            image_height = int(size / float(image_width) * image_height)
            image_width = size
    else:
        if image_height > size:
            image_width = int(size / float(image_height) * image_width)
            image_height = size
    crop_pixbuf = pixbuf.scale_simple(image_width, image_height,
                                      GdkPixbuf.InterpType.HYPER)
    return (crop_pixbuf, image_width, image_height)


def pixbuf_add_border(pix):
    # Add a gray outline to pix. This will increase the pixbuf size by
    # 2 pixels lengthwise and heightwise, 1 on each side. Returns pixbuf.
    width = pix.get_width()
    height = pix.get_height()
    newpix = GdkPixbuf.Pixbuf.new(GdkPixbuf.Colorspace.RGB, True, 8, width + 2,
                            height + 2)
    newpix.fill(0x858585ff)
    pix.copy_area(0, 0, width, height, newpix, 1, 1)
    return newpix


def pixbuf_pad(pix, w, h):
    # Adds transparent canvas so that the pixbuf is of size (w,h). Also
    # centers the pixbuf in the canvas.
    width = pix.get_width()
    height = pix.get_height()
    transpbox = GdkPixbuf.Pixbuf.new(GdkPixbuf.Colorspace.RGB, True, 8, w, h)
    transpbox.fill(0)
    x_pos = int((w - width) / 2)
    y_pos = int((h - height) / 2)
    pix.copy_area(0, 0, width, height, transpbox, x_pos, y_pos)
    return transpbox


def do_style_cover(config, pix, w, h):
    """Style a cover, according to the specified configuration."""

    if config.covers_type == consts.COVERS_TYPE_STYLIZED:
        return composite_case(pix, w, h)
    else:
        return pix


def composite_case(pix, w, h):
    """Blend the cover with a 'case' cover, for maximum beauty."""

    if w / h <= 0.5:
        return pix

    # Rather than merely compositing the case on top of the artwork,
    # we will scale the artwork so that it isn't covered by the case:
    spine_ratio = 60 / 600 # From original png
    spine_width = int(w * spine_ratio)
    #case_icon = Gtk.IconFactory.lookup_default('sonata-case')

    ## We use the fullscreenalbumimage because it's the biggest we have
    #context = self.fullscreenalbumimage.get_style_context()
    #case_pb = case_icon.render_icon_pixbuf(context, -1)
    i = Gtk.Image.new_from_pixbuf(pix)
    case_pb = i.render_icon_pixbuf('sonata-case', -1)
    case = case_pb.scale_simple(w, h, GdkPixbuf.InterpType.BILINEAR)
    # Scale pix and shift to the right on a transparent pixbuf:
    pix = pix.scale_simple(w - spine_width, h, GdkPixbuf.InterpType.BILINEAR)
    blank = GdkPixbuf.Pixbuf.new(GdkPixbuf.Colorspace.RGB, True, 8, w, h)
    blank.fill(0x00000000)
    pix.copy_area(0, 0, pix.get_width(), pix.get_height(), blank,
                  spine_width, 0)
    # Composite case and scaled pix:
    case.composite(blank, 0, 0, w, h, 0, 0, 1, 1,
                   GdkPixbuf.InterpType.BILINEAR, 250)
    del case
    del case_pb
    return blank
