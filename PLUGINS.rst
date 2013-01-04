================================
Plugins documentation for Sonata
================================

This document explains how to write plugins for Sonata, a Gtk client for the
`Music Player Daemon`_.

Plugin metadata
===============

TODO


Plugin entr-points
==================

This is the list of entry-points that plugins can hook into Sonata

``cover_fetching(artist, album, on_save_callback, on_error_callback)``
----------------------------------------------------------------------

* ``on_save_callback(fp)``: takes a file-like object as argument, and will save
  its content in a place known by Sonata. However successful the saving was, it
  returns ``True`` if the plugin should *continue* to download more covers, or
  ``False`` if the plugin should *stop* to download covers.

* ``on_error_callback(reason=None)``: takes an optionnal `reason` as argument.
  This must be call if something wrong happens while fetching a cover. This
  returns ``True`` to indicate that the plugin shoud *stop* fetching new covers,
  or ``False`` if the plugin should *continue* fetching new covers.

This entry-point is called when Sonata is requesting a plugin to get a cover for
the specified ``album`` played by the ``artist``. On finding new covers, the
plugin has to call the ``on_save_callback`` callback, passing the content of the
cover as a file-like object. If finding a specific cover fails, the plugin
should call ``on_error_callback``, passing a possible `reason` why it fails.

Depending on the return value of the callbacks, the plugin should continue or
stop fetching new covers.

.. note::
    The reasoning behind both callbacks are as follow:

    * the plugin doesn't have to be responsible of saving the content of the
      cover on the file system, Sonata will do it.
    * the plugin should be told when there are enough covers fetched. This can
      be a hard limit, ranging from 1 (get me the first cover) to (currently) 50
      (get me all the covers that you can find and the user will choose the
      right one). This can also be a way to tell the plugin that the user has
      enough covers and there's no need to download more (the user already
      picked up the right cover).
    * the plugin should not stop in an "infinite", un-stoppable loop. Hence,
      even if fetching a cover fails, the plugin should notify Sonata it tried
      to get one, so it can either be stopped, or get a chance to find more.



``lyrics_fetching``
-------------------

TODO


``playing_song_observers``
--------------------------

TODO

.. _Music Player Daemon: http://musicpd.org
