
### BEGIN PLUGIN INFO
# [plugin]
# plugin_format: 0, 0
# name: Lyrics.time
# version: 0, 1, 0
# description: Fetch lyrics from lyricstime.com.
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

lyricstime = None

class Lyricstime():
    def __init__(self):
        pass

    def clear(self, string):
        #It should make "when-you-don-t-control-your-government-people-want-to-kill-you"
        #from "When You Don't Control Your Government, People Want to Kill You"

        string = str(string).lower()
        string = re.sub(r"[\'\ ]",'-',string)
        string = re.sub(r"[\.\,\?\!\:\;\$\(\)]",'',string)

        return string

    def get_lyrics(self, search_artist, search_title):

        addr = "http://www.lyricstime.com/%s-%s-lyrics.html" % (self.clear(search_artist), self.clear(search_title))

        try:
            page = urllib.urlopen(addr).read()
            lyrics = page.split('<div id="songlyrics" >')[1].split('</div>')[0].strip()
            lyrics = lyrics.replace("<br />","").replace("<p>","").replace("</p>","")

            if lyrics == "":
                return None
        except:
            return None

        return lyrics

def on_enable(state):

    global lyricstime

    if state:
        if lyricstime is None:
            lyricstime = Lyricstime()

def get_lyrics(artist, title):

    return lyricstime.get_lyrics(artist, title)
