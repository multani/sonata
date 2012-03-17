
### BEGIN PLUGIN INFO
# [plugin]
# plugin_format: 0, 0
# name: AZLyrics
# version: 0, 1, 0
# description: Fetch lyrics from AZLyrics.com.
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

azlyrics = None

class AZLyrics():
    def __init__(self):
        pass

    def clear(self, string):
        #It should make "whenyoudontcontrolyourgovernmentpeoplewanttokillyou"
        #from "When You Don't Control Your Government, People Want to Kill You"

        string = str(string).lower()
        string = re.sub(r"[\'\.\,\-\?\!\:\;\$\(\)\ ]",'',string)

        return string

    def get_lyrics(self, search_artist, search_title):

        addr = "http://www.azlyrics.com/lyrics/%s/%s.html" % (self.clear(search_artist), self.clear(search_title))

        try:
            page = urllib.urlopen(addr).read()
            lyrics = page.split("<!-- start of lyrics -->")[1].split("<!-- end of lyrics -->")[0].strip()
            lyrics = re.sub(r"<br>",'',lyrics)

            if lyrics == "":
                return None
        except:
            return None

        return lyrics

def on_enable(state):

    global azlyrics

    if state:
        if azlyrics is None:
            azlyrics = AZLyrics()

def get_lyrics(artist, title):

    return azlyrics.get_lyrics(artist, title)
