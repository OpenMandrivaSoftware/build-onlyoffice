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

for i in core desktop-sdk desktop-apps sdkjs web-apps; do
	if ! [ -d "$i" ]; then
		git clone https://github.com/ONLYOFFICE/$i.git
		if [ -d "patches/$i" ]; then
			PN=1
			for p in patches/$i/*; do
				echo "=== Applying $(basename $p) in $i... ==="
				cd $i
				patch -p1 -b -z .p${PN}~ <../$p
				cd ..
				PN=$((PN+1))
			done
		fi
	fi
done

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

# Drop internal cef prebuilt binaries, and pull in ours
# (correct architecture, ungoogled and no GTK dep)
rm -rf desktop-sdk/ChromiumBasedEditors/lib/src/cef/linux
mkdir -p desktop-sdk/ChromiumBasedEditors/lib/src/cef/linux
cp -a /usr/lib64/cef/* desktop-sdk/ChromiumBasedEditors/lib/src/cef/linux/
rm -rf core/Common/3dParty/cef
mkdir -p core/Common/3dParty/cef/build
ln -s /usr/lib64/cef/Release/libcef.so core/Common/3dParty/cef/build/

cd desktop-sdk/ChromiumBasedEditors/lib
qmake ascdocumentscore.pro CEF_SRC_PATH=$(pwd)/src/cef/linux $(pkg-config --cflags-only-I gtk+-3.0 |sed -e 's,-I,INCLUDEPATH+=,g') DEFINES+=_LINUX CONFIG+=core_linux QMAKE_CXXFLAGS_RELEASE-=-Werror=format-security
make -j16
qmake ascdocumentscore_helper.pro CEF_SRC_PATH=$(pwd)/src/cef/linux $(pkg-config --cflags-only-I gtk+-3.0 |sed -e 's,-I,INCLUDEPATH+=,g') DEFINES+=_LINUX CONFIG+=core_linux QMAKE_CXXFLAGS_RELEASE-=-Werror=format-security
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
