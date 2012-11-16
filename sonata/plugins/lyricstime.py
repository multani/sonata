
### BEGIN PLUGIN INFO
# [plugin]
# plugin_format: 0, 0
# name: Lyrics.time
# version: 0, 2, 0
# description: Fetch lyrics from lyricstime.com.
# author: Anton Lashkov
# author_email: Lenton_91@mail.ru
# url:
# license: GPL v3 or later
# [capabilities]
# lyrics_fetching: get_lyrics
### END PLUGIN INFO

import re
import urllib

def clear(string):
    #It should make "when-you-don-t-control-your-government-people-want-to-kill-you"
    #from "When You Don't Control Your Government, People Want to Kill You"

    string = str(string).lower()
    string = re.sub(r"[\'\ ]",'-',string)
    string = re.sub(r"[\.\,\?\!\:\;\$\(\)]",'',string)

    return string

def get_lyrics(search_artist, search_title):
    addr = "http://www.lyricstime.com/%s-%s-lyrics.html" % (
        clear(search_artist), clear(search_title))

    try:
        page = urllib.urlopen(addr).read()
        lyrics = page.split('<div id="songlyrics" >')[1].\
                 split('</div>')[0].strip()
        lyrics = lyrics.replace("<br />","").replace("<p>","").replace("</p>","")

        if lyrics == "":
            return None
        else:
            return lyrics

    except:
        return None

if __name__ == "__main__":
    print get_lyrics("anti-flag", "Death Of A Nation")
