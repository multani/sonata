# Copyright 1999-2013 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

EAPI="4"
PYTHON_DEPEND="3:3.2"
SUPPORT_PYTHON_ABIS="1"
RESTRICT_PYTHON_ABIS="2.* *-jython"

inherit distutils python git-2

DESCRIPTION="an elegant GTK 3 client for the Music Player Daemon"
HOMEPAGE="https://github.com/multani/sonata"
EGIT_REPO_URI="git://github.com/multani/sonata.git"

LICENSE="GPL-3"
SLOT="0"
KEYWORDS="~amd64 ~x86"
IUSE="dbus mpd taglib"

RDEPEND=">=dev-python/python-mpd-0.4.6
	>=dev-python/pygobject-3.4.2
	>=x11-libs/gtk+-3.4
	mpd? ( >=media-sound/mpd-0.15 )
	dbus? ( dev-python/dbus-python )
	taglib? ( >=dev-python/tagpy-0.93 )"
DEPEND="${RDEPEND}
	virtual/pkgconfig"

DOCS="CHANGELOG README.rst TODO TRANSLATORS"

src_install() {
	distutils_src_install
	rm -rf "${D}"/usr/share/sonata
}

pkg_postinst() {
	elog ""
	elog "In order to work correctly Sonata,"
	elog "you will need PyGObject 3.7.4 or more,"
	elog "earlier versions may also work... but it's not recommended"
}
