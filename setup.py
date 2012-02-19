#!/usr/bin/env python

from distutils.dep_util import newer
import glob
import os
from setuptools import setup, Extension
from sonata.version import version


def capture(cmd):
    return os.popen(cmd).read().strip()


def generate_translation_files():
    lang_files = []

    if not os.path.exists("mo"):
        os.mkdir("mo")

    langs = (os.path.splitext(l)[0]
             for l in os.listdir('po')
             if l.endswith('po') and l != "messages.po")

    for lang in langs:
        pofile = os.path.join("po", "%s.po" % lang)
        modir = os.path.join("mo", lang)
        mofile = os.path.join(modir, "sonata.mo")
        if not os.path.exists(modir):
            os.mkdir(modir)

        lang_files.append(('share/locale/%s/LC_MESSAGES' % lang, [mofile]))

        if newer(pofile, mofile):
            print("Generating %s" % mofile)
            os.system("msgfmt %s -o %s" % (pofile, mofile))

    return lang_files

versionfile = open("sonata/genversion.py","wt")
versionfile.write("""
# generated by setup.py
VERSION = 'v%s'
""" % version)
versionfile.close()



data_files = [
    ('share/sonata', ['README.old', 'CHANGELOG', 'TODO', 'TRANSLATORS']),
    ('share/applications', ['sonata.desktop']),
    ('share/man/man1', ['sonata.1']),
] + generate_translation_files()


setup(
    name='Sonata',
    version=version,
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
    packages=["sonata", "sonata.plugins"],
    package_dir={"sonata": "sonata"},
    data_files=data_files,
    package_data={
        'sonata': ['pixmaps/*.*'],
    },
    entry_points={
        'console_scripts': [
            'sonata=sonata.launcher:run',
        ]
    },
    test_suite='sonata.tests',
)
try:
    os.remove("sonata/genversion.py")
    os.remove("sonata/genversion.pyc")
except:
    pass
