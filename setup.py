#!/usr/bin/env python

import sys
if sys.version_info <= (3, 2):
    sys.stderr.write("Sonata requires Python 3.2+\n")
    sys.exit(1)

import os
from setuptools import setup
from sonata.version import version


tests_require = []
if sys.version_info < (3, 3):
    # Available as unittest.mock since 3.3
    tests_require.append('mock')


def newer(source, generated):
    if (
        os.path.exists(generated)
        and os.path.getmtime(source) < os.path.getmtime(generated)
    ):
        return False

    return True


def capture(cmd):
    return os.popen(cmd).read().strip()


def generate_translation_files():
    lang_files = []

    langs = (os.path.splitext(l)[0]
             for l in os.listdir('po')
             if l.endswith('po') and l != "messages.po")

    for lang in langs:
        pofile = os.path.join("po", "%s.po" % lang)
        modir = os.path.join("sonata", "share", "locale", lang, "LC_MESSAGES")
        mofile = os.path.join(modir, "sonata.mo")
        if not os.path.exists(modir):
            os.makedirs(modir)

        lang_files.append(('share/locale/%s/LC_MESSAGES' % lang, [mofile]))

        if newer(pofile, mofile):
            print("Generating %s" % mofile)
            os.system("msgfmt %s -o %s" % (pofile, mofile))

    return lang_files


versionfile = open("sonata/genversion.py", "wt")
versionfile.write("""
# generated by setup.py
VERSION = 'v%s'
""" % version)
versionfile.close()


data_files = [
    ('share/sonata', ['README.rst', 'CHANGELOG', 'TODO', 'TRANSLATORS']),
    ('share/applications', ['sonata.desktop']),
    ('share/man/man1', ['sonata.1']),
] + generate_translation_files()


setup(
    name='Sonata',
    version=version,
    description='GTK+ client for the Music Player Daemon (MPD).',
    author='Scott Horowitz',
    author_email='stonecrest@gmail.com',
    url='http://www.nongnu.org/sonata/',
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
        'sonata': [
            'pixmaps/*.*',
            'ui/*.glade',
            'ui/*.css',
            'plugins/ui/*.glade',
            'plugins/ui/*.css',
        ],
    },
    entry_points={
        'console_scripts': [
            'sonata=sonata.launcher:run',
        ]
    },
    test_suite='sonata.tests',
    tests_require=tests_require,
)
try:
    os.remove("sonata/genversion.py")
    os.remove("sonata/genversion.pyc")
except:
    pass
