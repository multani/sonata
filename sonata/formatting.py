
"""This module implements the format strings used to display song info.

Example usage:
import formatting
colnames = formatting.parse_colnames(self.config.currentformat)
...
newtitle = formatting.parse(self.config.titleformat, self.songinfo, False, True)
...
formatcodes = formatting.formatcodes
"""

import mpdhelper as mpdh
import misc

formatcodes = [('A', _('Artist name')),
           ('B', _('Album name')),
           ('T', _('Track name')),
           ('N', _('Track number')),
           ('D', _('Disc number')),
           ('Y', _('Year')),
           ('G', _('Genre')),
           ('P', _('File path')),
           ('F', _('File name')),
           ('S', _('Stream name')),
           ('L', _('Song length')),
           ('E', _('Elapsed time (title only)'))
           ]

def _return_substrings(format):
    """Split format along the { and } characters.

    For example: %A{-%T} {%L} -> ['%A', '{-%T} ', '{%L}']"""
    substrings = []
    end = format
    while len(end) > 0:
        begin, sep1, end = end.partition('{')
        substrings.append(begin)
        if len(end) == 0:
            substrings.append(sep1)
            break
        begin, sep2, end = end.partition('}')
        substrings.append(sep1 + begin + sep2)
    return substrings

def parse_colnames(format):
    text = format.split("|")
    for i in range(len(text)):
        text[i] = text[i].replace("%A", _("Artist"))
        text[i] = text[i].replace("%B", _("Album"))
        text[i] = text[i].replace("%T", _("Track"))
        text[i] = text[i].replace("%N", _("#"))
        text[i] = text[i].replace("%Y", _("Year"))
        text[i] = text[i].replace("%G", _("Genre"))
        text[i] = text[i].replace("%P", _("Path"))
        text[i] = text[i].replace("%F", _("File"))
        text[i] = text[i].replace("%S", _("Stream"))
        text[i] = text[i].replace("%L", _("Len"))
        text[i] = text[i].replace("%D", _("#"))
        if text[i].count("{") == text[i].count("}"):
            text[i] = text[i].replace("{","").replace("}","")
        # If the user wants the format of, e.g., "#%N", we'll
        # ensure the # doesn't show up twice in a row.
        text[i] = text[i].replace("##", "#")
    return text

def _parse_substrings(subformat, item, wintitle, songpos):
    text = subformat
    if subformat.startswith("{") and subformat.endswith("}"):
        has_brackets = True
    else:
        has_brackets = False
    flag = "89syufd8sdhf9hsdf"
    if "%A" in text:
        artist = mpdh.get(item, 'artist', flag)
        if artist != flag:
            text = text.replace("%A", artist)
        else:
            if not has_brackets: text = text.replace("%A", _('Unknown'))
            else: return ""
    if "%B" in text:
        album = mpdh.get(item, 'album', flag)
        if album != flag:
            text = text.replace("%B", album)
        else:
            if not has_brackets: text = text.replace("%B", _('Unknown'))
            else: return ""
    if "%T" in text:
        title = mpdh.get(item, 'title', flag)
        if title != flag:
            text = text.replace("%T", title)
        else:
            if not has_brackets:
                if len(item['file'].split('/')[-1]) == 0 or item['file'][:7] == 'http://' or item['file'][:6] == 'ftp://':
                    # Use path and file name:
                    text = misc.escape_html(item['file'])
                else:
                    # Use file name only:
                    text = misc.escape_html(item['file'].split('/')[-1])
                if wintitle:
                    return "[Sonata] " + text
                else:
                    return text
            else:
                return ""
    if "%N" in text:
        track = mpdh.get(item, 'track', flag)
        if track != flag:
            track = mpdh.getnum(item, 'track', flag, False, 2)
            text = text.replace("%N", track)
        else:
            if not has_brackets: text = text.replace("%N", "00")
            else: return ""
    if "%D" in text:
        disc = mpdh.get(item, 'disc', flag)
        if disc != flag:
            disc = mpdh.getnum(item, 'disc', flag, False, 0)
            text = text.replace("%D", disc)
        else:
            if not has_brackets: text = text.replace("%D", "0")
            else: return ""
    if "%S" in text:
        name = mpdh.get(item, 'name', flag)
        if name != flag:
            text = text.replace("%S", name)
        else:
            if not has_brackets: text = text.replace("%S", _('Unknown'))
            else: return ""
    if "%G" in text:
        genre = mpdh.get(item, 'genre', flag)
        if genre != flag:
            text = text.replace("%G", genre)
        else:
            if not has_brackets: text = text.replace("%G", _('Unknown'))
            else: return ""
    if "%Y" in text:
        date = mpdh.get(item, 'date', flag)
        if date != flag:
            text = text.replace("%Y", date)
        else:
            if not has_brackets: text = text.replace("%Y", "?")
            else: return ""

    pathname = mpdh.get(item, 'file')
    try:
        dirname, filename = pathname.rsplit('/', 1)
    except ValueError: # Occurs for a file in the music_dir root
        dirname, filename = "", pathname
    if "%P" in text:
        text = text.replace("%P", dirname)
    if "%F" in text:
        text = text.replace("%F", filename)

    if "%L" in text:
        time = mpdh.get(item, 'time', flag)
        if time != flag:
            time = misc.convert_time(int(time))
            text = text.replace("%L", time)
        else:
            if not has_brackets: text = text.replace("%L", "?")
            else: return ""
    if wintitle:
        if "%E" in text:
            try:
                at, length = [int(c) for c in songpos.split(':')]
                at_time = misc.convert_time(at)
                text = text.replace("%E", at_time)
            except:
                if not has_brackets: text = text.replace("%E", "?")
                else: return ""
    if text.startswith("{") and text.endswith("}"):
        return text[1:-1]
    else:
        return text

def parse(format, item, use_escape_html, wintitle=False, songpos=None):
    substrings = _return_substrings(format)
    text = "".join(_parse_substrings(sub, item, wintitle, songpos)
               for sub in substrings)
    return misc.escape_html(text) if use_escape_html else text
