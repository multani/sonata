#!/usr/bin/env python

# $HeadURL: http://svn.berlios.de/svnroot/repos/sonata/trunk/setup.py $
# $Id: setup.py 141 2006-09-11 04:51:07Z stonecrest $

import os

from distutils.core import setup, Extension

def capture(cmd):
    return os.popen(cmd).read().strip()

def removeall(path):
    if not os.path.isdir(path):
        return

    files=os.listdir(path)

    for x in files:
        fullpath=os.path.join(path, x)
        if os.path.isfile(fullpath):
            f=os.remove
            rmgeneric(fullpath, f)
        elif os.path.isdir(fullpath):
            removeall(fullpath)
            f=os.rmdir
            rmgeneric(fullpath, f)

def rmgeneric(path, __func__):
    try:
        __func__(path)
    except OSError, (errno, strerror):
        pass

# Create mo files:
if not os.path.exists("mo/"):
    os.mkdir("mo/")
for lang in ('de', 'pl', 'ru', 'fr', 'zh_CN', 'sv', 'es', 'fi', 'uk', 'it', 'cs', 'nl', 'pt_BR', 'da'):
    pofile = "po/" + lang + ".po"
    mofile = "mo/" + lang + "/sonata.mo"
    if not os.path.exists("mo/" + lang + "/"):
        os.mkdir("mo/" + lang + "/")
    print "generating", mofile
    os.system("msgfmt %s -o %s" % (pofile, mofile))

setup(name='Sonata',
        version='1.3',
        description='GTK+ client for the Music Player Daemon (MPD).',
        author='Scott Horowitz',
        author_email='stonecrest@gmail.com',
        url='http://sonata.berlios.de/',
        classifiers=[
            'Development Status :: 4 - Beta',
            'Environment :: X11 Applications',
            'Intended Audience :: End Users/Desktop',
            'License :: GNU General Public License (GPL)',
            'Operating System :: Linux',
            'Programming Language :: Python',
            'Topic :: Multimedia :: Sound :: Players',
            ],
        py_modules = ['sonata', 'mpdclient3', 'audioscrobbler'],
        ext_modules=[Extension(
        "mmkeys", ["mmkeys/mmkeyspy.c", "mmkeys/mmkeys.c", "mmkeys/mmkeysmodule.c"],
        extra_compile_args=capture("pkg-config --cflags gtk+-2.0 pygtk-2.0").split(),
        extra_link_args=capture("pkg-config --libs gtk+-2.0 pygtk-2.0").split()
         ),],
        scripts = ['sonata'],
        data_files=[('share/sonata', ['README', 'CHANGELOG', 'TODO', 'TRANSLATORS']),
                    ('share/applications', ['sonata.desktop']),
                    ('share/pixmaps', ['pixmaps/sonata.png', 'pixmaps/sonata_large.png', 'pixmaps/sonatacd.png', 'pixmaps/sonatacd_large.png', 'pixmaps/sonata-artist.png', 'pixmaps/sonata-album.png', 'pixmaps/sonata-stock_volume-mute.png', 'pixmaps/sonata-stock_volume-min.png', 'pixmaps/sonata-stock_volume-med.png', 'pixmaps/sonata-stock_volume-max.png', 'pixmaps/sonata_pause.png', 'pixmaps/sonata_play.png', 'pixmaps/sonata_disconnect.png']),
                    ('share/locale/de/LC_MESSAGES', ['mo/de/sonata.mo']),
                    ('share/locale/pl/LC_MESSAGES', ['mo/pl/sonata.mo']),
                    ('share/locale/ru/LC_MESSAGES', ['mo/ru/sonata.mo']),
                    ('share/locale/fr/LC_MESSAGES', ['mo/fr/sonata.mo']),
                    ('share/locale/zh_CN/LC_MESSAGES', ['mo/zh_CN/sonata.mo']),
                    ('share/locale/sv/LC_MESSAGES', ['mo/sv/sonata.mo']),
                    ('share/locale/es/LC_MESSAGES', ['mo/es/sonata.mo']),
                    ('share/locale/fi/LC_MESSAGES', ['mo/fi/sonata.mo']),
                    ('share/locale/nl/LC_MESSAGES', ['mo/nl/sonata.mo']),
                    ('share/locale/it/LC_MESSAGES', ['mo/it/sonata.mo']),
                    ('share/locale/cs/LC_MESSAGES', ['mo/cs/sonata.mo']),
                    ('share/locale/da/LC_MESSAGES', ['mo/da/sonata.mo']),
                    ('share/locale/pt_BR/LC_MESSAGES', ['mo/pt_BR/sonata.mo']),
                    ('share/locale/uk/LC_MESSAGES', ['mo/uk/sonata.mo'])],
        )

# Cleanup (remove /build, /mo, and *.pyc files:
print "Cleaning up..."
try:
    removeall("build/")
    os.rmdir("build/")
except:
    pass
try:
    removeall("mo/")
    os.rmdir("mo/")
except:
    pass
try:
    for f in os.listdir("."):
        if os.path.isfile(f):
            if os.path.splitext(os.path.basename(f))[1] == ".pyc":
                os.remove(f)
except:
    pass
