
"""This module implements the format strings used to display song info.

Example usage:
import formatting
colnames = formatting.parse_colnames(self.config.currentformat)
...
newtitle = formatting.parse(self.config.titleformat, self.songinfo,
                            False, True)
...
formatcodes = formatting.formatcodes
"""

import re
import os

from sonata import mpdhelper as mpdh
from sonata import misc


class FormatCode(object):
    """Implements deafult format code behavior.

    Replaces all instances of %code with the value of key or default if the
    key doesn't exist.
    """

    def __init__(self, code, description, column, key,
            default=_("Unknown")):
        self.code = code
        self.description = description
        self.column = column
        self.key = key
        self.default = default

    def format(self, item, wintitle, songpos):
        """Returns the value used in place of the format code"""
        return str(item.get(self.key, self.default))


class NumFormatCode(FormatCode):
    """Implements format code behavior for numeric values.

    Used for numbers which need special padding.
    """

    def __init__(self, code, description, column, key, default, padding):
        FormatCode.__init__(self, code, description, column, key,
                    default)
        self.padding = padding

    def format(self, item, wintitle, songpos):
        return str(item.get(self.key, self.default)).zfill(self.padding)


class PathFormatCode(FormatCode):
    """Implements format code behavior for path values."""

    def __init__(self, code, description, column, key, path_func):
        """

        path_func: os.path function to apply
        """
        FormatCode.__init__(self, code, description, column, key)
        self.func = getattr(os.path, path_func)

    def format(self, item, wintitle, songpos):
        return self.func(FormatCode.format(self, item, wintitle,
                            songpos))


class TitleFormatCode(FormatCode):
    """Implements format code behavior for track titles."""

    def format(self, item, wintitle, songpos):
        path = item['file']
        full_path = re.match(r"^(http://|ftp://)", path)
        self.default = path if full_path else os.path.basename(path)
        self.default = misc.escape_html(self.default)
        return FormatCode.format(self, item, wintitle, songpos)


class LenFormatCode(FormatCode):
    """Implements format code behavior for song length."""

    def format(self, item, wintitle, songpos):
        time = FormatCode.format(self, item, wintitle, songpos)
        if time.isdigit():
            time = misc.convert_time(int(time))
        return time


class ElapsedFormatCode(FormatCode):
    """Implements format code behavior for elapsed time."""

    def format(self, item, wintitle, songpos):
        if not wintitle:
            return "%E"
        elapsed_time = songpos.split(':')[0] if songpos else self.default
        if elapsed_time.isdigit():
            elapsed_time = misc.convert_time(int(elapsed_time))
        return elapsed_time

formatcodes = [FormatCode('A', _('Artist name'), _("Artist"), 'artist'),
           FormatCode('B', _('Album name'), _("Album"), 'album'),
           TitleFormatCode('T', _('Track name'), _("Track"), 'title'),
           NumFormatCode('N', _('Track number'), _("#"), 'track', '00', 2),
           NumFormatCode('D', _('Disc number'), _("#"), 'disc', '0', 0),
           FormatCode('Y', _('Year'), _("Year"), 'date', '?'),
           FormatCode('G', _('Genre'), _("Genre"), 'genre'),
           PathFormatCode('P', _('File path'), _("Path"), 'file',
                'dirname'),
           PathFormatCode('F', _('File name'), _("File"), 'file',
                'basename'),
           FormatCode('S', _('Stream name'), _("Stream"), 'name'),
           LenFormatCode('L', _('Song length'), _("Len"), 'time', '?'),
           ElapsedFormatCode('E', _('Elapsed time (title only)'), None,
                 'songpos', '?')]

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

    def replace_format(m):
        format_code = replace_map.get(m.group(0)[1:])
        return format_code.column

    cols = [re.sub(replace_expr, replace_format, s).
        replace("{", "").
        replace("}", "").
        # If the user wants the format of, e.g., "#%N", we'll
        # ensure the # doesn't show up twice in a row.
        replace("##", "#")
        for s in format.split('|')]
    return cols


class EmptyBrackets(Exception):
    pass


def _format_substrings(text, item, wintitle, songpos):
    has_brackets = text.startswith("{") and text.endswith("}")

    def formatter(m):
        format_code = replace_map[m.group(0)[1:]]
        if has_brackets and format_code.key not in item:
            raise EmptyBrackets
        return format_code.format(item, wintitle, songpos)

    try:
        text = re.sub(replace_expr, formatter, text)
    except EmptyBrackets:
        return ""

    return text[1:-1] if has_brackets else text


def parse(format, item, use_escape_html, wintitle=False, songpos=None):
    substrings = _return_substrings(format)
    text = "".join(_format_substrings(sub, item, wintitle, songpos)
            for sub in substrings)
    return misc.escape_html(text) if use_escape_html else text
