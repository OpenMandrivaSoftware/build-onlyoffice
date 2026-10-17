#!/bin/sh
# Launch the tree created by install.sh.
# INSTDIR defaults to /opt/oo, matching install.sh.

cd "$(dirname "$0")"
INSTDIR=${INSTDIR:-/opt/oo}

if [ ! -x "$INSTDIR/DesktopEditors" ]; then
	echo "No install found in $INSTDIR. Run ./install.sh first." >&2
	exit 1
fi

# $ORIGIN and $ORIGIN/converter cover the copied libraries. editors_helper
# still needs the distro libcef, which is not copied into the install tree.
export LD_LIBRARY_PATH="$INSTDIR:$INSTDIR/converter:/usr/lib64/cef/Release${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
exec "$INSTDIR/DesktopEditors" "$@"
