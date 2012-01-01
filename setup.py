#!/usr/bin/env python

from distutils.dep_util import newer
import glob
import os
from subprocess import check_output

from setuptools import setup, Extension


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
            print "Generating %s" % mofile
            os.system("msgfmt %s -o %s" % (pofile, mofile))

    return lang_files


# Compute the version using Git.
# If the HEAD also points to a tag (say "v42.3.2"), it should returns this tag,
# otherwise the last tag+commit information (like "v42.3.2-188-gc0d1")
def compute_version():
    version = check_output(["git", "describe", "--tags", "--abbrev=4", "HEAD"],
                           cwd=os.path.dirname(os.path.abspath(__file__)))

    # Remove newlines and the "v" in front of the version, to please setuptools
    version = version.strip().lstrip("v")

    return version


data_files = [
    ('share/sonata', ['README.old', 'CHANGELOG', 'TODO', 'TRANSLATORS']),
    ('share/applications', ['sonata.desktop']),
    ('share/man/man1', ['sonata.1']),
] + generate_translation_files()

tests_require = [
    'unittest2',
]


setup(
    name='Sonata',
    version=compute_version(),
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
    ext_modules=[
        Extension(
            "mmkeys",
            ["mmkeys/mmkeyspy.c", "mmkeys/mmkeys.c",
             "mmkeys/mmkeysmodule.c"],
            extra_compile_args=capture("pkg-config --cflags gtk+-2.0 pygtk-2.0").split(),
            extra_link_args=capture("pkg-config --libs gtk+-2.0 pygtk-2.0").split()
        ),
    ],
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
    tests_require=tests_require,
    extras_require={
        'test': tests_require,
    },
)
