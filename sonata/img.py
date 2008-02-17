# coding=utf-8
# $HeadURL: http://svn.berlios.de/svnroot/repos/sonata/trunk/img.py $
# $Id: img.py 141 2006-09-11 04:51:07Z stonecrest $

import gtk, os

def valid_image(file):
    test = gtk.gdk.pixbuf_get_file_info(file)
    if test == None:
        return False
    else:
        return True

def get_pixbuf_of_size(pixbuf, size):
    # Creates a pixbuf that fits in the specified square of sizexsize
    # while preserving the aspect ratio
    # Returns tuple: (scaled_pixbuf, actual_width, actual_height)
    image_width = pixbuf.get_width()
    image_height = pixbuf.get_height()
    if image_width-size > image_height-size:
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
    transpbox.fill(0xffff00)
    x_pos = int((w - width)/2)
    y_pos = int((h - height)/2)
    pix.copy_area(0, 0, width, height, transpbox, x_pos, y_pos)
    return transpbox

def extension_is_valid(extension):
    for ext in gtk.gdk.pixbuf_get_formats():
        if extension.lower() in ext['extensions']:
            return True
    return False

def single_image_in_dir(dir):
    # Returns None or a filename if there is exactly one image
    # in the dir.
    num = 0
    imgfile = None
    if not os.path.exists(dir):
        return None
    for file in os.listdir(dir):
        ext = os.path.splitext(file)[1][1:]
        if extension_is_valid(ext):
            num += 1
            if num == 1:
                imgfile = dir + "/" + file
            else:
                break
    if num != 1:
        return None
    return imgfile
