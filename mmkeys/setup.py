
from distutils.core import setup, Extension
import os
import subprocess


def capture(cmd):
    return os.popen(cmd).read().strip()


class UnavailablePackage(Exception):
    """Raised if a package can't be found by pkg-config"""
    pass


def pkg_config(flag, *packages):
    """Return include flags for the specified pkg-config package name."""

    outputs = []
    for package in packages:
        pkg_config = ['pkg-config', flag, package]

        try:
            proc = subprocess.Popen(pkg_config, close_fds=True,
                                    stdout=subprocess.PIPE,
                                    stderr=subprocess.PIPE)
        except OSError, e:
            raise OSError(e.errno,
                          "Unable to execute command '%s': %s" %
                          (' '.join(pkg_config), e))

        output = proc.stdout.read()
        err = proc.stderr.read()

        if err != '':
            raise UnavailablePackage('Unable to get flags for package %r. '
                                     'pkg-config error was:\n\n%s' % (package, err))
        outputs.extend(output.strip().split())

    return outputs


HERE = os.path.dirname(os.path.abspath(__file__))


setup(
    name="mmkeys",
    description="Multimedia Key support as a PyGTK object",
    long_description=open(os.path.join(HERE, 'README')).read(),
    url='http://sonata.berlios.de',
    author='Joe Wreschnig',
    author_email='piman@sacredchao.net',
    version='1.0',
    ext_modules=[
        Extension(
            "mmkeys", ["mmkeyspy.c", "mmkeys.c", "mmkeysmodule.c"],
            extra_compile_args=pkg_config("--cflags", "gtk+-2.0", "pygtk-2.0"),
            extra_link_args=pkg_config("--libs", "gtk+-2.0", "pygtk-2.0"),
        ),
    ],
)
