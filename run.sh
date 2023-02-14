#!/bin/sh
cd "$(dirname $0)"
if ! [ -e desktop-apps/win-linux/build/DesktopEditors ]; then
	echo "No completed build found. You may have to run build.sh"
	exit 1
fi
LIBS=$(for i in $(find . -name "*.so*"); do
	dirname $i
done |sort |uniq)
for i in $LIBS; do
	export LD_LIBRARY_PATH=$(realpath $i):$LD_LIBRARY_PATH
done
exec desktop-apps/win-linux/build/DesktopEditors
