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

if [ "$1" = "-w" ]; then
	rm -rf core desktop-sdk desktop-apps sdkjs web-apps
fi

for i in core desktop-sdk desktop-apps sdkjs web-apps; do
	if ! [ -d "$i" ]; then
		git clone https://github.com/ONLYOFFICE/$i.git
		if [ -d "patches/$i" ]; then
			PN=1
			for p in patches/$i/*; do
				echo "=== Applying $(basename $p) with backup .p${PN}~ in $i... ==="
				cd $i
				patch -p1 -b -z .p${PN}~ <../$p
				cd ..
				PN=$((PN+1))
			done
		fi
	fi
done
pushd core/Common/3dParty/html
# For details like exact commit ID requested, check fetch.py in this directory.
# Patches applied with sed are from fetch.py as well
git clone https://github.com/google/gumbo-parser.git
cd gumbo-parser
git checkout -b oo aa91b27b02c0c80c482e24348a457ed7c3c088e0
sed -i -e 's,isspace(*c),isspace((unsigned char)*c),g' src/tag.c
cd ..
git clone https://github.com/jasenhuang/katana-parser.git
cd katana-parser
git checkout -b oo be6df458d4540eee375c513958dcb862a391cdd1
sed -i -e 's|static inline bool katana_is_html_space(char c);|static inline bool2 katana_is_html_space(char c);|g' src/tokenizer.c
sed -i -e 's|inline bool katana_is_html_space(char c)|static inline bool katana_is_html_space(char c)|g' src/tokenizer.c
sed -i -e 's|static inline bool2 katana_is_html_space(char c);|static inline bool katana_is_html_space(char c);|g' src/tokenizer.c
sed -i -e 's|katanaget_text(parser->scanner)|/*katanaget_text(parser->scanner)*/\"error\"|g' src/parser.c
sed -i -e 's|#define KATANA_PARSER_STRING(literal) (KatanaParserString){|#define KATANA_PARSER_STRING(literal) {|g' src/parser.c
cd ..
popd

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
