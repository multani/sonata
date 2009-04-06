
import os

import gtk, gobject

def valid_image(filename):
    return bool(gtk.gdk.pixbuf_get_file_info(filename))

def get_pixbuf_of_size(pixbuf, size):
    # Creates a pixbuf that fits in the specified square of sizexsize
    # while preserving the aspect ratio
    # Returns tuple: (scaled_pixbuf, actual_width, actual_height)
    image_width = pixbuf.get_width()
    image_height = pixbuf.get_height()
    if image_width > image_height:
        if image_width > size:
            image_height = int(size/float(image_width)*image_height)
            image_width = size
    else:
        if image_height > size:
            image_width = int(size/float(image_height)*image_width)
            image_height = size
    crop_pixbuf = pixbuf.scale_simple(image_width, image_height, gtk.gdk.INTERP_HYPER)
    return (crop_pixbuf, image_width, image_height)

def pixbuf_add_border(pix):
    # Add a gray outline to pix. This will increase the pixbuf size by
    # 2 pixels lengthwise and heightwise, 1 on each side. Returns pixbuf.
    width = pix.get_width()
    height = pix.get_height()
    newpix = gtk.gdk.Pixbuf(gtk.gdk.COLORSPACE_RGB, True, 8, width+2, height+2)
    newpix.fill(0x858585ff)
    pix.copy_area(0, 0, width, height, newpix, 1, 1)
    return newpix

def pixbuf_pad(pix, w, h):
    # Adds transparent canvas so that the pixbuf is of size (w,h). Also
    # centers the pixbuf in the canvas.
    width = pix.get_width()
    height = pix.get_height()
    transpbox = gtk.gdk.Pixbuf(gtk.gdk.COLORSPACE_RGB, True, 8, w, h)
    transpbox.fill(0)
    x_pos = int((w - width)/2)
    y_pos = int((h - height)/2)
    pix.copy_area(0, 0, width, height, transpbox, x_pos, y_pos)
    return transpbox

def extension_is_valid(extension):
    for imgformat in gtk.gdk.pixbuf_get_formats():
        if extension.lower() in imgformat['extensions']:
            return True
    return False

def is_imgfile(filename):
    ext = os.path.splitext(filename)[1][1:]
    return extension_is_valid(ext)

def single_image_in_dir(dirname):
    # Returns None or a filename if there is exactly one image
    # in the dir.
    try:
        dirname = gobject.filename_from_utf8(dirname)
    except:
        pass

    try:
        files = os.listdir(dirname)
    except OSError:
        return None

    imgfiles = [f for f in files if is_imgfile(f)]
    if len(imgfiles) != 1:
        return None
    return os.path.join(dirname, imgfiles[0])
