import os
from subprocess import Popen, PIPE

try:
    import genversion
    build_ver = genversion.VERSION
except ImportError:
    build_ver = None

# Should be the most recent release
default_version = "v1.6.2.1"

def _version():
    '''Get the version number of the sources

    First check the build generated file, fallback to git describe if this is
    not a build, finally fallback to the default most recent release.
    '''
    if build_ver:
        version = build_ver
    else:
        try:
            dir = os.path.dirname(__file__)
            version = Popen(["git", "describe", "--abbrev=4", "HEAD"],
                             cwd=dir, stdout=PIPE,
                             stderr=PIPE).communicate()[0]
            if not version:
                raise OSError
        except OSError:
            version = default_version
    return str(version.strip()[1:])

version = _version()
