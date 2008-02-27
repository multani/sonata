# coding=utf-8
# $HeadURL: http://svn.berlios.de/svnroot/repos/sonata/trunk/mpdfuncs.py $
# $Id: mpdfuncs.py 141 2006-09-11 04:51:07Z stonecrest $

def status(client):
    try:
        status = client.status()
    except:
        return None
    try:
        test = status['state']
    except:
        return {}
    return status

def currsong(client):
    try:
        return client.currentsong()
    except:
        return None
