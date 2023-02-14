#!/bin/sh

set -e

cd "$(dirname $0)"
if ! [ -e desktop-apps/win-linux/build/DesktopEditors ]; then
	echo "No completed build found. You may have to run build.sh"
	exit 1
fi

if [ `id -u` != 0 ]; then
	exec sudo $0 "$@"
fi

INSTDIR=/opt/oo

mkdir -p $INSTDIR/converter
cp -a desktop-apps/win-linux/build/DesktopEditors $INSTDIR/
cp -a core/build/bin/editors_helper $INSTDIR/
cp -a core/build/lib/libascdocumentscore.so $INSTDIR/
cp -a core/build/lib/libooxmlsignature.so $INSTDIR/
cp -a core/build/lib/libqtascdocumentscore.so $INSTDIR/
cp -a core/build/lib/libvideoplayer.so $INSTDIR/
cp -a desktop-apps/win-linux/package/linux/branding/common/opt/desktopeditors/* $INSTDIR/

cp -a desktop-apps/common/converter/DoctRenderer.config $INSTDIR/converter/
cp -a core/build/lib/libDjVuFile.so $INSTDIR/converter/
cp -a core/build/lib/libgraphics.so $INSTDIR/converter/
cp -a core/build/lib/libHtmlRenderer.so $INSTDIR/converter/
cp -a core/build/lib/libkernel_network.so $INSTDIR/converter/
cp -a core/build/lib/libkernel.so $INSTDIR/converter/
cp -a core/build/lib/libPdfFile.so $INSTDIR/converter/
cp -a core/build/lib/libUnicodeConverter.so $INSTDIR/converter/
cp -a core/build/lib/libXpsFile.so $INSTDIR/converter/
cp -a desktop-apps/common/converter/empty $INSTDIR/converter/
cp -a desktop-apps/common/package/mimetypes $INSTDIR/
echo 'package = rpm' >$INSTDIR/converter/package.config

cp -a core/Common/3dParty/cef/cef_binary/Resources/* $INSTDIR/
cp -a core/Common/3dParty/cef/cef_binary/Release/* $INSTDIR/
