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

which qmake || export PATH=$PATH:/usr/lib64/qt6/bin

if [ "$1" = "-w" ]; then
	rm -rf core desktop-sdk desktop-apps sdkjs web-apps
fi

for i in core desktop-sdk desktop-apps sdkjs web-apps; do
	echo "=== Checking out $i ==="
	if ! [ -d "$i" ]; then
		git clone -b develop https://github.com/ONLYOFFICE/$i.git
		if [ "$i" = "core" ]; then
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
			# This seems to be required as well, but not retrieved anywhere
			cd core/Common/3dParty/hyphen
			git clone https://github.com/hunspell/hyphen.git
			cd -
		fi
		if [ -d "patches/$i" ]; then
			PN=1
			for p in patches/$i/*; do
				[ -d $p ] && continue
				echo "=== Applying $(basename $p) with backup .p${PN}~ in $i... ==="
				cd $i
				patch -p1 -b -z .p${PN}~ <../$p
				cd ..
				PN=$((PN+1))
			done
		fi
	fi
done

# gumbo, katana and hyphen are cloned only while checking out a missing core
# tree. The compile below does not download them.
for req in \
	core/Common/3dParty/html/gumbo-parser/src \
	core/Common/3dParty/html/katana-parser/src \
	core/Common/3dParty/hyphen/hyphen/hyphen.h
do
	if [ ! -e "$req" ]; then
		echo "missing $req" >&2
		echo "It is vendored at checkout. The compile does not download it." >&2
		exit 1
	fi
done

cd core
# qmake/make only. Upstream fetch scripts clone md4c, brotli, harfbuzz and the
# iWork stack; those are linked from the distro instead. This loop does not
# download.
for i in UnicodeConverter/UnicodeConverter.pro Common/kernel.pro Common/Network/network.pro DesktopEditor/graphics/pro/graphics.pro PdfFile/PdfFile.pro DjVuFile/DjVuFile.pro XpsFile/XpsFile.pro Common/cfcpp/cfcpp.pro OfficeCryptReader/ooxml_crypt/ooxml_crypt.pro DesktopEditor/xmlsec/src/ooxmlsignature.pro OFDFile/OFDFile.pro DocxRenderer/DocxRenderer.pro DesktopEditor/doctrenderer/doctrenderer.pro \
	MsBinaryFile/Projects/VbaFormatLib/Linux/VbaFormatLib.pro \
	OOXML/Projects/Linux/DocxFormatLib/DocxFormatLib.pro \
	OOXML/Projects/Linux/XlsbFormatLib/XlsbFormatLib.pro \
	OOXML/Projects/Linux/PPTXFormatLib/PPTXFormatLib.pro \
	OOXML/Projects/Linux/BinDocument/BinDocument.pro \
	MsBinaryFile/Projects/DocFormatLib/Linux/DocFormatLib.pro \
	MsBinaryFile/Projects/PPTFormatLib/Linux/PPTFormatLib.pro \
	MsBinaryFile/Projects/XlsFormatLib/Linux/XlsFormatLib.pro \
	OdfFile/Projects/Linux/OdfFormatLib.pro \
	RtfFile/Projects/Linux/RtfFormatLib.pro \
	TxtFile/Projects/Linux/TxtXmlFormatLib.pro \
	Fb2File/Fb2File.pro \
	HtmlFile2/HtmlFile2.pro \
	EpubFile/CEpubFile.pro \
	Apple/IWork.pro \
	OdfFile/Reader/Converter/StarMath2OOXML/StarMath2OOXML.pro \
	HwpFile/HWPFile.pro \
	X2tConverter/build/Qt/X2tConverter.pro; do
	echo "=== Building core/$(dirname $i) ==="
	EXTRAOPTS=""
	cd $(dirname $i)
	[ "$(basename $i)" = graphics.pro ] && EXTRAOPTS="$(pkg-config --cflags-only-I harfbuzz |sed -e 's,-I[A-Za-z/]*freetype2,,' |sed -e 's,-I,INCLUDEPATH+=,g')"
	qmake $(basename $i) DEFINES+=_LINUX CONFIG+=core_linux CONFIG+=c++2a $EXTRAOPTS
	make -j16
	cd -
done
cd ..

# ChromiumBasedEditors links the distro CEF (see cef_pri/cef_system.pri).
# cef_base.pri used to overwrite CEF_SRC_PATH with the bundled 109 tree.

echo '=== Building ChromiumBasedEditors ==='
cd desktop-sdk/ChromiumBasedEditors/lib
qmake ascdocumentscore.pro CONFIG+=core_linux CONFIG+=c++2a DEFINES+=_LINUX CONFIG+=core_linux QMAKE_CXXFLAGS_RELEASE-=-Werror=format-security
make -j16

echo '=== Building ascdocumentscore_helpers ==='
qmake ascdocumentscore_helper.pro CONFIG+=core_linux CONFIG+=c++2a DEFINES+=_LINUX CONFIG+=core_linux QMAKE_CXXFLAGS_RELEASE-=-Werror=format-security
make -j16
cd -
cd desktop-sdk/ChromiumBasedEditors/videoplayerlib
qmake videoplayerlib.pro DEFINES+=_LINUX CONFIG+=core_linux CONFIG+=c++2a
make -j16
cd -
cd desktop-sdk/ChromiumBasedEditors/lib/qt_wrapper
qmake qtascdocumentscore.pro DEFINES+=_LINUX CONFIG+=core_linux CONFIG+=c++2a
make -j16
cd -


cd desktop-apps/win-linux
qmake ASCDocumentEditor.pro DEFINES+=_LINUX CONFIG+=core_linux CONFIG+=c++2a $(pkg-config --cflags-only-I glib-2.0 |sed -e 's,-I,INCLUDEPATH+=,g')
make -j16
cd ../..

# Concatenates sources already in the sdkjs tree. It does not fetch or minify.
echo '=== Deploying sdkjs ==='
python sdkjs/build/build.py --desktop

echo '=== DONE ==='
