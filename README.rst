Sonata, an elegant GTK 3 client for the `Music Player Daemon`_
==============================================================

Sonata is a client for the `Music Player Daemon`_ featuring:

+ Expanded and collapsed views, fullscreen album art mode
+ Automatic remote and local album art
+ Library browsing by folders, or by genre/artist/album
+ User-configurable columns
+ Automatic fetching of lyrics and covers
+ Playlist and stream support
+ Support for editing song tags
+ Drag-and-drop to copy files
+ Popup notification
+ Library and playlist searching, filter as you type
+ Audioscrobbler (Last.fm) 1.2 support
+ Multiple MPD profiles
+ Keyboard friendly
+ Support for multimedia keys
+ Commandline control
+ Available in 24 languages

Sonata is written using the `Python programming language`_ and uses the GTK 3
toolkit.

Sonata started as a fork of the Pygmy project and is licensed under the GPLv3.
Thanks to Andrew Conkling et al, for all their hard work on Pygmy!

Using Sonata
============

Requirements
------------

In order to run Sonata, you will need the following dependencies:

* Python >= 3.2
* `PyGObject`_ (aka Python GObject Introspection) (3.7.4 or more recommended,
  earlier versions may also work)
* GTK >= 3.4
* `python-mpd2` >= 0.4.6
* MPD >= 0.15 (possibly on another computer)
* taglib and tagpy >= 2013.1 for editing metadata (Optional)
* dbus-python for multimedia keys (Optional)

.. warning: Sonata depends on `PyGObject`_ which is still quite new and gets
    regular fixes. Although versions 3.4.x shipped in most distributions at the
    time of writing are OK most of the time, unexpected bugs may occur which are
    fixed by more recent versions.

Sonata can currently be downloaded from the Git repository using::

    $ git clone git://github.com/multani/sonata.git
    $ cd sonata

To run Sonata, you can either install it in a dedicated directory (as root)::

    # python setup.py install

Or you can run it straight from the directory (without prior installation)::

    $ ./run-sonata


Sonata in Linux distributions
-----------------------------

This version of Sonata is available in several distributions:

.. note:: For distribution-specific comments, please contact the packagers at
    the specified URLs!

* Archlinux: available in `AUR as sonata-git
  <https://aur.archlinux.org/packages/sonata-git/>`_
* Gentoo: available in the `stuff overlay`_::

    sudo layman -a stuff
    sudo emerge -av =sonata-9999


Website, documentation, help, etc.
==================================

The official documentation is located at
http://sonata.berlios.de/documentation.html

You can ask for feature requests or report bugs on Github at
https://github.com/multani/sonata/issues

There's a (somewhat alive) mailing list available at
https://lists.berlios.de/mailman/listinfo/sonata-users

Contributing
============

If you are interested to hack on Sonata, please consider the following:

#. Clone the repository or fork it on Github;
#. **For each** feature, bug fix, refactor, anything, you want to submit, create
   a branch with a name which reflects what you want to do;
#. Commit your changes related to *this* thing in this branch;
#. Signal your changes with one of the following:

   * open a pull request on Github;
   * send a mail to jon@multani.info with the URL of your repository, the
     name of the branch you want to be merged, and a meaningful description of
     your work;
   * or send me your patch(es) to jon@multani.info using ``git send-email``.

I hate, hate, *hate* having to review commits touching lot of unrelated things,
this is the easiest way for your changes not to be merged. Try to stay focus on
one clearly defined thing and it should be much easier to merge.

Translations
------------

.. note:: See the `TRANSLATORS` file for more information!

You can translate Sonata using the `dedicated Transifex project
page <https://www.transifex.com/projects/p/sonata/>`_.

Sonata's translation can be done via the `Transifex`_ plateform. You need to
subscribe to `Transifex`_ first, then to add yourself as a member of the
`Transifex Sonata`_ project under the language your are interested to translate
into.

Once a translation is done, *be sure to contact the maintainer of Sonata* to
announce there's a new translation to include!


See also
========

You can also find Sonata in other places on the Internet:

* http://sonata.berlios.de/ : this is the original Sonata website. It has not
  been updated since a while but still has interesting screenshots.
* http://codingteam.net/project/sonata/ : this is another fork with a different
  team and different perspectives. Our code bases diverge quite a bit now.

Copyright
=========

* Copyright 2006-2009 Scott Horowitz <stonecrest@gmail.com>
* Copyright 2009-2013 Jonathan Ballet <jon@multani.info>

Sonata is currently developed by Jonathan Ballet <jon@multani.info> and other
contributors. Many thanks to the past developers:

* Scott Horowitz <stonecrest@gmail.com>
* Tuukka Hastrup <Tuukka.Hastrup@iki.fi>
* Stephen Boyd <bebarino@gmail.com>

.. _Music Player Daemon: http://musicpd.org
.. _PyGObject: https://live.gnome.org/PyGObject
.. _python-mpd2: http://pypi.python.org/pypi/python-mpd2/
.. _python programming language: http://www.python.org/
.. _transifex: https://www.transifex.com
.. _transifex sonata: https://www.transifex.com/projects/p/sonata/
.. _stuff overlay: https://github.com/megabaks/stuff/tree/master/media-sound/sonata
