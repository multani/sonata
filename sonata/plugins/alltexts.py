# -*- coding: utf-8 -*-

### BEGIN PLUGIN INFO
# [plugin]
# plugin_format: 0, 0
# name: AllTexts
# version: 0, 1, 0
# description: Fetch lyrics from alltexts.ru
# author: Anton Lashkov
# author_email: Lenton_91@mail.ru
# url:
# license: GPL v3 or later
# [capabilities]
# enablables: on_enable
# lyrics_fetching: get_lyrics
### END PLUGIN INFO

import re
import urllib

alltexts = None

class AllTexts():
    def __init__(self):
        pass

    def format(self, string):
        #It should make "when_you_don't_control_your_government_people_want_to_kill_you"
        #from "When You Don't Control Your Government, People Want to Kill You"
        #and translite cyrilic letters.

        string = self.cyr2lat(string)
        string = re.sub(r"[\,\?\!\:\;]",'',string)
        string = string.replace(' ','_')
        string = str(string).lower()

        return string

    def cyr2lat(self, s):
        conversion = {
            'а' : 'a',
            'б' : 'b',
            'в' : 'v',
            'г' : 'g',
            'д' : 'd',
            'е' : 'e',
            'ё' : 'jo',
            'ж' : 'zh',
            'з' : 'z',
            'и' : 'i',
            'й' : 'j',
            'к' : 'k',
            'л' : 'l',
            'м' : 'm',
            'н' : 'n',
            'о' : 'o',
            'п' : 'p',
            'р' : 'r',
            'с' : 's',
            'т' : 't',
            'у' : 'u',
            'ф' : 'f',
            'х' : 'h',
            'ц' : 'c',
            'ч' : 'ch',
            'ш' : 'sh',
            'щ' : 'sch',
            'ь' : "",
            'ы' : 'y',
            'ъ' : "",
            'э' : 'e',
            'ю' : 'ju',
            'я' : 'ja',
            'А' : 'A',
            'Б' : 'B',
            'В' : 'V',
            'Г' : 'G',
            'Д' : 'D',
            'Е' : 'E',
            'Ё' : 'J',
            'Ж' : 'ZH',
            'З' : 'Z',
            'И' : 'I',
            'Й' : 'JO',
            'К' : 'K',
            'Л' : 'L',
            'М' : 'M',
            'Н' : 'N',
            'О' : 'O',
            'П' : 'P',
            'Р' : 'R',
            'С' : 'S',
            'Т' : 'T',
            'У' : 'U',
            'Ф' : 'F',
            'Х' : 'H',
            'Ц' : 'C',
            'Ч' : 'CH',
            'Ш' : 'SH',
            'Щ' : 'SCH',
            'Ъ' : "",
            'Ы' : 'Y',
            'Ь' : "",
            'Э' : 'E',
            'Ю' : 'JU',
            'Я' : 'JA',
            }
        for c in conversion:
            try:
                s = s.replace(c,conversion[c])
            except KeyError:
                pass
        return s

    def get_lyrics(self, search_artist, search_title):

        addr = "http://alltexts.ru/text/%s/%s.php" % (self.format(search_artist), self.format(search_title))
        try:
            page = urllib.urlopen(addr).read()
            lyrics = page.split('<pre class="text">')[1].split("</pre>")[0].strip()
            lyrics = lyrics.decode('cp1251').encode('utf8')
            lyrics = lyrics.replace("\n\n","\n")
            if lyrics == "":
                return None
        except Exception:
            return None

        return lyrics

def on_enable(state):

    global alltexts

    if state:
        if alltexts is None:
            alltexts = AllTexts()

def get_lyrics(artist, title):

    return alltexts.get_lyrics(artist, title)

