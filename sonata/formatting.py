
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
import re
import os

class FormatCode(object):
    """Implements deafult format code behavior.

    Replaces all instances of %code with the value of key or default if the
    key doesn't exist.
    """
    def __init__(self, code, description, key, default=_("Unknown")):
        self.code = code
        self.description = description
        self.key = key
        self.default = default

    def format(self, item):
        """Returns the value used in place of the format code"""
        return mpdh.get(item, self.key, self.default)

class NumFormatCode(FormatCode):
    """Implements format code behavior for numeric values.

    Used for numbers which need special padding.
    """
    def __init__(self, code, description, key, default, padding):
        FormatCode.__init__(self, code, description, key, default)
        self.padding = padding

    def format(self, item):
        return mpdh.get(item, self.key, self.default, False,
                self.padding)

class PathFormatCode(FormatCode):
    """Implements format code behavior for path values."""
    def __init__(self, code, description, key, path_func):
        """

        path_func: os.path function to apply
        """
        FormatCode.__init__(self, code, description, key)
        self.func = getattr(os.path, path_func)

    def format(self, item):
        return self.func(FormatCode.format(self, item))


class TitleFormatCode(FormatCode):
    """Implements format code behavior for track titles."""
    def format(self, item):
        path = item['file']
        full_path = re.match(r"^(http://|ftp://)", path)
        self.default = path if full_path else os.path.basename(path)
        self.default = misc.escape_html(self.default)
        return FormatCode.format(self, item)

class LenFormatCode(FormatCode):
    """Implements format code behavior for song length."""
    def format(self, item):
        time = FormatCode.format(self, item)
        if time.isdigit():
            time = misc.convert_time(int(time))
        return time

class ElapsedFormatCode(FormatCode):
    """Implements format code behavior for elapsed time."""
    def format(self, item):
        if item['wintitle'] is False:
            return "%E"
        elapsed_time = FormatCode.format(self, item).split(':')[0]
        if elapsed_time.isdigit():
            elapsed_time = misc.convert_time(int(elapsed_time))
        return elapsed_time

formatcodes = [FormatCode('A', _('Artist name'), 'artist'),
           FormatCode('B', _('Album name'), 'album'),
           TitleFormatCode('T', _('Track name'), 'title'),
           NumFormatCode('N', _('Track number'), 'track', '00', 2),
           NumFormatCode('D', _('Disc number'), 'disc', '0', 0),
           FormatCode('Y', _('Year'), 'date', '?'),
           FormatCode('G', _('Genre'), 'genre'),
           PathFormatCode('P', _('File path'), 'file', 'dirname'),
           PathFormatCode('F', _('File name'), 'file', 'basename'),
           FormatCode('S', _('Stream name'), 'name'),
           LenFormatCode('L', _('Song length'), 'time', '?'),
           ElapsedFormatCode('E', _('Elapsed time (title only)'), 'songpos',
                 '?')
           ]

replace_map = dict((code.code, code) for code in formatcodes)
replace_expr = r"%%[%s]" % "".join(k for k in replace_map.keys())

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

class EmptyBrackets(Exception):
    pass

def _format_substrings(text, item):
    has_brackets = text.startswith("{") and text.endswith("}")

    def formatter(m):
        format_code = replace_map[m.group(0)[1:]]
        if has_brackets and not item.has_key(format_code.key):
            raise EmptyBrackets
        return format_code.format(item)

    try:
        text = re.sub(replace_expr, formatter, text)
    except EmptyBrackets:
        return ""

    return text[1:-1] if has_brackets else text

def parse(format, item, use_escape_html, wintitle=False, songpos=None):
    substrings = _return_substrings(format)
    if songpos:
        item['songpos'] = songpos
    item['wintitle'] = wintitle
    text = "".join(_format_substrings(sub, item) for sub in substrings)
    return misc.escape_html(text) if use_escape_html else text
