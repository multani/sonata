
# in builds, the generated version module should be used instead

import os, subprocess
from xml.etree import ElementTree

import sonata
from consts import consts

def find_svnrev():
    dirname = os.path.dirname(os.path.dirname(sonata.__file__))

    if not os.path.exists(os.path.join(dirname, '.svn')):
        return "exported"

    try:
        output = subprocess.Popen(["svnversion", dirname],
                      stdout=subprocess.PIPE,
                      stderr=subprocess.PIPE
                      ).communicate()[0]
        if output.strip():
            return output.strip()
    except OSError: # svnversion fails to run
        pass # try next

    try:
        output = subprocess.Popen(["svn", "info", "--xml", dirname],
                      stdout=subprocess.PIPE,
                      stderr=subprocess.PIPE
                      ).communicate()[0]
        info = ElementTree.fromstring(output)
        return info.find("entry").get("revision")
    except (OSError, # svn fails to run
        Exception, # no repo causes parsing svn info to fail
        AttributeError): # no <entry> for some reason
        pass # try next

    return None

if "/tags/" in consts.HEAD_URL:
    VERSION = consts.HEAD_URL.split("/tags/")[1].split("/")[0]
else:
    revision = find_svnrev()
    VERSION = "svn%s" % (revision if revision else "????")
