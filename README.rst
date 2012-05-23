Sonata, an elegant GTK+ client for the Music Player Daemon
==========================================================

This is my personal repository for Sonata containing various fixes.

See the ``README.old`` for the official README of the project.

All the following fixes are available in the `integration` branch.

How to contribute?
------------------

If you are interested to send me some changes, please consider the following:

#. Clone my repository or fork it on Github;
#. **For each** feature, bug fix, refactor, anything, you want to submit to me,
   create a branch with a name which reflects what you want to do;
#. Commit your changes related to *this* thing in this branch;
#. Signal your changes with one of the following
   * send a mail to jon+sonata@multani.info with the URL of your repository, the
     name of the branch you want to be merged, and a meaningful description of
     your work;
   * send me your patch(es) to jon+sonata@multani.info using ``git send-email``;
   * open a pull request on Github.

I hate, hate, *hate* having to review 20 unrelated commits with 1000+ lines
changed, this is the easiest way for your changes not to be merged.

Changelog
---------

Currently, the following things have been changed since the Berlios's version:

* GTK+'s StatusIcon is fully supported and should provide the same features as
  the old eggtrayicon module.

  eggtrayicon is still the 'preferred' way of displaying the status icon, if you
  have it installed, I suppose this is for good reasons. If you don't have it,
  Sonata will use the GTK+ StatusIcon and everything should be fine.

  This is the `refactor-tray-icon` branch.

* it fixes some UI problems if Sonata tries to reconnect to MPD in some weird
  cases.

  I had the problem when MPD was brutally shut down and then relaunch, but I
  heard some users had the same problem in other cases as well, but bugs can be
  tricky to reproduce.

  This is the `fix-ui-connection` branch.

* There is a whole set of patches I merged:

  * reindentation and PEP8-fication by Francois "Paco" Ribemont and Kirill
    "KL-7" Lashuk;
  * some UI fixes related to artists and lyrics and album info (Yann Boulanger);
  * Sonata only loads the latest version of each plugins;
  * lyricwiki fixes: etter parsing and presentation (Kirill Lashuk);
  * more items in the tray menu (Kirill Lashuk);
  * scrobble after seeking to the beginning (Kirill Lashuk);
  * improve handling of multi-CD albums: prevent multiple
    entries and improve art search (Kirill Lashuk);
  * better fullscreen support (Kirill Lashuk);
  * fixes weird show up if Sonata is not on the current workspace (Kirill
    Lashuk);

* I refactored a bit how the lyricwiki plugin works to make it more readable and
  I fixed the following issues:

  * ``AttributeError: 'NoneType' object has no attribute 'startswith'`` when
    trying to search for lyrics;
  * retrieving lyrics from lyrics.wikia.com now works again

  This is the `fix-fetch-lyrics` branch.


* Sonata can now by launched by a much proper script. There also a script to
  launch *all* the unit tests of Sonata (which is zero (well, one dummy test, to
  be sure it works)), but the infrastructure is there.

  This is the `refactor-launcher` branch.

* "Daniel <quite@hack.org>" added support to toggle fullscreen status from the
  command line.

* Sonata now use the Python's `logging` module to log things instead of
  print/sys.std[out|err].write/custom thing, which should render things more
  uniform and customizable.

  This is the `logging-support` branch.

* I refactored how the MPD object is accessed in the code: the MPD client is now
  a plain object with nice methods to access MPD functionality, which makes the
  code sightly better to read. There's still some (hard) work to do to provide a
  good looking and *uniform* access to the song's info (it's currently a
  gigantic mess).

  This is the `cleanup-mpd-object` branch.

* Improved the packaging of the application: use `pkg_resources` to access
  data files, and stop doing so much work when running `python setup.py ...`.

* Transform the ``consts`` module into a more simple constant module, thanks to
  Jörg Thalheim  (Mic92).

  This is the `refactor-consts` branch.

* Fix the population of the "Save to playlist" context menu, which didn't
  contain the current playlist of MPD.
  Fix also the name of the playlists in this menu, if their were containing an
  underscore. There are now displayed correctly.

  Thanks to Zhihao Yuan for the fixes!

* Remove a bunch of code used for old or deprecated components (MPD, pyGtk,
  DBus, etc.)

  This is the `remove-deprecated` branch.

* Fix the initialization of DBus, due to the removal of deprecated stuff in
  `remove-deprecated`. Thanks to Zhihao Yuan!


Personal todo list
------------------

Those are the things I want to work on (as far as I can remember):

* remove Sugar support (what is the status of Sugar actually?);
* contact the quodlibet team to externalize the mmkeys module;
* externalisation of code:
    * remove the scrobbler implementation and use an external, dedicated module
      to hande Last.fm/Libre.fm protocol and add a dependency on it;
    * remove the lyrics modules and use an external, dedicated and well tested
      module to handle lyrics fetching, and add a dependency on it;
    * remove the covers module and use an external, dedicated and well tested
      module to handle covers fetching, and add a dependency on it;
* remove eggtrayicon support (gtk.StatusIcon should be sufficient)
* port to Python 3 and the new GIR modules
* BIG code cleanup to simplify many things (remove useless
  variables/attributes/methods, simplify objects communication, etc. too long to
  list exhaustingly here I guess and quite subjective).
* have a look at the performance/memory issues when using a "big" library:
  Sonata is supposed to be a lightweight music player.


Also, I should have a look there:

* sort bugs from Debian: http://bugs.debian.org/cgi-bin/pkgreport.cgi?package=sonata
* sort bugs from Launchpad: https://bugs.launchpad.net/ubuntu/+source/sonata
* bugs/patches/feature requests from Berlios/CT
