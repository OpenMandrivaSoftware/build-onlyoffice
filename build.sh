#!/bin/sh

# FIXME Even once it starts up, some stuff needs to be fixed:
# * Internal copy of outdated zlib at core/OfficeUtils/src/zlib-1.2.11
# * Internal copies of multiple versions(!) of outdated freetype
#   core/DesktopEditor/freetype-2.5.2
#   core/DesktopEditor/freetype-2.10.4
#   Use of internal freetype headers in multiple places, making it
#   harder to use system freetype
# * Internal copy of agg core/DesktopEditor/agg-2.4
# * Possible internal copies of libxml/libxmlsec (are those modified?)
#   core/DesktopEditor/xml core/DesktopEditor/xmlsec
# * Internal copy of openjpeg
#   core/DesktopEditor/raster/Jp2/openjpeg/openjpeg-2.4.0
# * Internal copy of poppler/xpdf (modified?), core/PdfFile/lib
# * Internal copies of loads of stuff in core/Common/3dParty

set -e

for i in core desktop-sdk desktop-apps; do
	if ! [ -d "$i" ]; then
		git clone https://github.com/ONLYOFFICE/$i.git
		PN=1
		for p in patches/$i/*; do
			cd $i
			patch -p1 -b -z .p${PN}~ <../$p
			cd ..
			PN=$((PN+1))
		done
	fi
done

if ! [ -e core/Common/3dParty/cef/build ]; then
	# FIXME urgently: build libcef from source instead of relying
	# on the weird, unknown-origin, binaries!
	# Binary URL is taken from
	# https://github.com/ONLYOFFICE/build_tools/blob/master/scripts/core_common/modules/cef.py
	[ -e cef_binary.7z ] || wget http://d2ettrnqo7v976.cloudfront.net/cef/4280/linux_64/cef_binary.7z

	cd core/Common/3dParty/cef
	tar xf ../../../../cef_binary.7z
	ln -s cef_binary/Release build
	cd -
fi

# According to https://bitbucket.org/chromiumembedded/cef/src/4280/, 4280
# corresponds to commit 36ee304ed48f
# Still need to figure out how to build that from source -- seems to be
# incomplete
#[ -e cef.tar.gz ] || wget -O cef.tar.gz https://bitbucket.org/chromiumembedded/cef/get/36ee304ed48f.tar.gz

cd core
for i in UnicodeConverter/UnicodeConverter.pro Common/kernel.pro Common/Network/network.pro DesktopEditor/graphics/pro/graphics.pro HtmlRenderer/htmlrenderer.pro PdfFile/PdfFile.pro DjVuFile/DjVuFile.pro XpsFile/XpsFile.pro Common/cfcpp/cfcpp.pro OfficeCryptReader/ooxml_crypt/ooxml_crypt.pro DesktopEditor/xmlsec/src/ooxmlsignature.pro; do
	EXTRAOPTS=""
	cd $(dirname $i)
	[ "$(basename $i)" = graphics.pro ] && EXTRAOPTS="$(pkg-config --cflags-only-I harfbuzz |sed -e 's,-I[A-Za-z/]*freetype2,,' |sed -e 's,-I,INCLUDEPATH+=,g')"
	qmake $(basename $i) DEFINES+=_LINUX CONFIG+=core_linux $EXTRAOPTS
	make -j16
	cd -
done
cd ..

cd desktop-sdk/ChromiumBasedEditors/lib
qmake ascdocumentscore.pro CEF_SRC_PATH=$(pwd)/src/cef_87/linux $(pkg-config --cflags-only-I gtk+-2.0 |sed -e 's,-I,INCLUDEPATH+=,g') DEFINES+=_LINUX CONFIG+=core_linux QMAKE_CXXFLAGS_RELEASE-=-Werror=format-security
make -j16
cd -
cd desktop-sdk/ChromiumBasedEditors/videoplayerlib
qmake videoplayerlib.pro DEFINES+=_LINUX CONFIG+=core_linux
make -j16
cd -
cd desktop-sdk/ChromiumBasedEditors/lib/qt_wrapper
qmake qtascdocumentscore.pro DEFINES+=_LINUX CONFIG+=core_linux
make -j16
cd -


cd desktop-apps/win-linux
qmake ASCDocumentEditor.pro DEFINES+=_LINUX CONFIG+=core_linux $(pkg-config --cflags-only-I glib-2.0 |sed -e 's,-I,INCLUDEPATH+=,g')
make -j16
cd ../..
