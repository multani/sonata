#!/usr/bin/env python

# $HeadURL: http://svn.berlios.de/svnroot/repos/sonata/trunk/setup.py $
# $Id: setup.py 141 2006-09-11 04:51:07Z stonecrest $

from distutils.core import setup

setup(name='Sonata',
        version='0.5',
        description='GTK+ client for the Music Player Daemon (MPD).',
        author='Scott Horowitz',
        author_email='stonecrest@gmail.com',
        url='http://sonata.berlios.de',
        classifiers=[
            'Development Status :: 4 - Beta',
            'Environment :: X11 Applications',
            'Intended Audience :: End Users/Desktop',
            'License :: GNU General Public License (GPL)',
            'Operating System :: Linux',
            'Programming Language :: Python',
            'Topic :: Multimedia :: Sound :: Players',
            ],
        py_modules = ['sonata'],
        scripts = ['sonata', 'mpdclient3.py'],
        data_files=[('share/sonata',
                        ['README', 'CHANGELOG', 'TODO']),
                    ('share/applications',
                        ['sonata.desktop']),
                    ('share/pixmaps',
                        ['sonata.png', 'sonataplaylist.png', 'sonatacd.png'])],
        )
