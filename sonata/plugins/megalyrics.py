
### BEGIN PLUGIN INFO
# [plugin]
# plugin_format: 0, 0
# name: Megalyrics
# version: 0, 1, 0
# description: Fetch lyrics from megalyrics.ru
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

megalyrics = None

class Megalyrics():
    def __init__(self):
        pass

    def clear(self, string):
        #It should make "when-you-don-t-control-your-government-people-want-to-kill-you"
        #from "When You Don't Control Your Government, People Want to Kill You"

        string = str(string).lower()
        string = re.sub(r"[\,\?\!\:\;\$\(\)]",'',string)
        string = re.sub(r"[\'\.\ ]",'-',string)

        return string

    def get_lyrics(self, search_artist, search_title):

        addr = "http://megalyrics.ru/lyric/%s/%s.htm" % (self.clear(search_artist), self.clear(search_title))

        try:
            page = urllib.urlopen(addr).read()
            lyrics = page.split('<pre class="lyric">')[1].split("</pre>")[0].strip()

            if lyrics == "":
                return None
        except:
            return None

        return lyrics

def on_enable(state):

    global megalyrics

    if state:
        if megalyrics is None:
            megalyrics = Megalyrics()

def get_lyrics(artist, title):

    return megalyrics.get_lyrics(artist, title)
