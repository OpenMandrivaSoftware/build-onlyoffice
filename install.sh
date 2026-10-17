#!/bin/sh
# Assemble the directory DesktopEditors expects.
#
# Binaries and libraries are copied. Editor pages, templates, providers and
# CEF resource files are symlinks back to this tree and to the distro CEF,
# so a rebuild is picked up by running this script again.
#
# INSTDIR defaults to /opt/oo. Set INSTDIR to install somewhere else.
# Writing outside the checkout re-runs this script through sudo.

set -e

cd "$(dirname "$0")"
ROOT=$(pwd)

BIN=desktop-apps/win-linux/build/linux_64/DesktopEditors
HELPER=core/build/bin/linux_64/editors_helper
LIBDIR=core/build/lib/linux_64
CEF_RES=/usr/lib64/cef/Resources
CEF_REL=/usr/lib64/cef/Release

if [ ! -x "$BIN" ]; then
	echo "No completed build found ($BIN). You may have to run build.sh" >&2
	exit 1
fi
if [ ! -x "$HELPER" ]; then
	echo "editors_helper is missing ($HELPER). You may have to run build.sh" >&2
	exit 1
fi
if [ ! -d "$CEF_RES" ] || [ ! -e "$CEF_REL/libcef.so" ]; then
	echo "Distro CEF was not found under /usr/lib64/cef." >&2
	exit 1
fi

INSTDIR=${INSTDIR:-/opt/oo}
if [ "$(id -u)" != 0 ]; then
	parent=$(dirname "$INSTDIR")
	if [ ! -w "$INSTDIR" ] && [ ! -w "$parent" ]; then
		exec sudo INSTDIR="$INSTDIR" "$ROOT/$(basename "$0")" "$@"
	fi
fi

link_children() {
	src=$1
	dst=$2
	skip=$3
	mkdir -p "$dst"
	for item in "$src"/*; do
		[ -e "$item" ] || continue
		base=$(basename "$item")
		if [ -n "$skip" ] && [ "$base" = "$skip" ]; then
			continue
		fi
		ln -sfn "$item" "$dst/$base"
	done
}

mkdir -p "$INSTDIR/converter" "$INSTDIR/fonts"

cp -a "$BIN" "$INSTDIR/DesktopEditors"
cp -a "$HELPER" "$INSTDIR/editors_helper"
cp -a "$LIBDIR"/lib*.so "$INSTDIR/"
cp -a "$LIBDIR"/lib*.so "$INSTDIR/converter/"

if [ -x core/build/bin/linux_64/x2t ]; then
	cp -a core/build/bin/linux_64/x2t "$INSTDIR/converter/x2t"
else
	echo "warning: converter/x2t was not built; opening and saving documents will fail" >&2
	echo "         build core/X2tConverter/build/Qt/X2tConverter.pro, then re-run install.sh" >&2
fi

cp -a desktop-apps/common/converter/DoctRenderer.config "$INSTDIR/converter/DoctRenderer.config"
echo 'package = rpm' > "$INSTDIR/converter/package.config"
rm -rf "$INSTDIR/converter/empty" "$INSTDIR/converter/templates" "$INSTDIR/providers"
# core/Common/empty only has editor binaries (docx.bin, …). DesktopEditors
# creates a file from converter/empty/<lang>/new.{docx,xlsx,pptx} and converts
# that with x2t. Those OOXML templates are not in the core checkout.
# pack-startpage.py writes them, and replaces the install-root index.html
# (the OnlyOffice tab) with the real start page. The .bin files stay
# available for anything that reads them.
mkdir -p "$INSTDIR/converter/empty"
for b in "$ROOT/core/Common/empty"/*; do
	[ -f "$b" ] || continue
	ln -sfn "$b" "$INSTDIR/converter/empty/$(basename "$b")"
done
python "$ROOT/pack-startpage.py" --instdir "$INSTDIR"
ln -sfn "$ROOT/desktop-apps/common/templates" "$INSTDIR/converter/templates"
ln -sfn "$ROOT/desktop-apps/common/loginpage/providers" "$INSTDIR/providers"

# editors/web-apps is the source tree, with index.html.desktop exposed under
# the name the binary asks for, without writing into the checkout.
rm -rf "$INSTDIR/editors"
link_children "$ROOT/web-apps" "$INSTDIR/editors/web-apps" apps
link_children "$ROOT/web-apps/apps" "$INSTDIR/editors/web-apps/apps" api
link_children "$ROOT/web-apps/apps/api" "$INSTDIR/editors/web-apps/apps/api" documents
link_children "$ROOT/web-apps/apps/api/documents" "$INSTDIR/editors/web-apps/apps/api/documents"
# A symlink to index.html.desktop makes the resolved path end in .desktop.
# CEF then refuses to render it and opens a Save As dialog instead.
cp -a "$ROOT/web-apps/apps/api/documents/index.html.desktop" "$INSTDIR/editors/web-apps/apps/api/documents/index.html"

# Debug editor pages compile app.less in the browser. The sprite stylesheets
# are grunt output and are not in the source tree. Pack them from the icon
# PNGs already in the checkout. Empty stand-ins cover any import the packer
# did not write, so less can finish without a network build.
python "$ROOT/pack-sprites.py"
find "$ROOT/web-apps/apps" -name app.less -print0 | while IFS= read -r -d '' lessfile; do
	dir=$(dirname "$lessfile")/sprites
	mkdir -p "$dir"
	sed -n 's/.*@import "sprites\/\([^"]*\)".*/\1/p' "$lessfile" | while IFS= read -r name; do
		[ -n "$name" ] || continue
		[ -e "$dir/$name.less" ] || printf '\n' > "$dir/$name.less"
	done
done

if [ -d "$ROOT/sdkjs/deploy/sdkjs" ]; then
	ln -sfn "$ROOT/sdkjs/deploy/sdkjs" "$INSTDIR/editors/sdkjs"
	# The unbuilt web-apps pages load develop/sdkjs/<product>/scripts.js and
	# then those URLs, resolved from documenteditor/main (four levels up).
	# deploy/ holds the concatenated sdk; vendor/ lives in the sdkjs source.
	ln -sfn ../../vendor "$ROOT/sdkjs/deploy/sdkjs/vendor"
	for prod in word cell slide visio; do
		dir="$ROOT/sdkjs/deploy/sdkjs/develop/sdkjs/$prod"
		mkdir -p "$dir"
		# sdk-all-min.js calls loadSdk(), which inserts sdk-all.js once.
		# Listing sdk-all.js here as well runs its font init twice. The second
		# run replaces the font map with an empty object and opening a
		# document throws in AddLoadFonts (ConvertationOpenError -82).
		cat > "$dir/scripts.js" << EOF
var sdk_scripts = [
	"../../../../sdkjs/vendor/polyfill.js",
	"../../../../sdkjs/common/AllFonts.js",
	"../../../../sdkjs/${prod}/sdk-all-min.js"
];
EOF
	done
else
	echo "warning: sdkjs is not deployed; the editors will not load their scripts" >&2
	echo "         run: python sdkjs/build/build.py --desktop" >&2
	echo "         then re-run install.sh" >&2
	ln -sfn "$ROOT/sdkjs" "$INSTDIR/editors/sdkjs"
fi

# The connection-error page is loaded as editors/webext/noconnect.html.
# index.html.deploy expects code.min.js and the svg beside that file.
# The grunt pack step only concatenates those scripts.
NOCON=$ROOT/desktop-apps/common/loginpage/noconnect
mkdir -p "$INSTDIR/editors/webext"
ln -sfn "$NOCON/index.html.deploy" "$INSTDIR/editors/webext/noconnect.html"
ln -sfn "$NOCON/connection_error.svg" "$INSTDIR/editors/webext/connection_error.svg"
cat "$NOCON/code.js" "$NOCON"/l10n/*.js "$NOCON/init.js" > "$INSTDIR/editors/webext/code.min.js"

# CEF looks for pak files, locales and icudtl.dat next to the executable.
# libcef.so stays in /usr/lib64/cef/Release; run.sh puts that directory on
# LD_LIBRARY_PATH for editors_helper, which does not have it in its rpath.
for item in "$CEF_RES"/*; do
	ln -sfn "$item" "$INSTDIR/$(basename "$item")"
done
for name in v8_context_snapshot.bin snapshot_blob.bin vk_swiftshader_icd.json libvk_swiftshader.so; do
	if [ -e "$CEF_REL/$name" ]; then
		ln -sfn "$CEF_REL/$name" "$INSTDIR/$name"
	fi
done

# Spellcheck dictionaries are dictionaries/<name>/<name>.aff and .dic.
# Names come from the hunspell table compiled into the editor.
rm -rf "$INSTDIR/dictionaries"
mkdir -p "$INSTDIR/dictionaries"
HUN=/usr/share/hunspell
RECORDS=$ROOT/core/Common/3dParty/hunspell/autogen/records.h
if [ -d "$HUN" ] && [ -f "$RECORDS" ]; then
	for name in $(sed -n 's/.*"\([^"]*\)".*/\1/p' "$RECORDS" | sort -u); do
		aff=$HUN/$name.aff
		dic=$HUN/$name.dic
		if [ ! -e "$aff" ] && [ -e "$HUN/${name}_frami.aff" ]; then
			aff=$HUN/${name}_frami.aff
			dic=$HUN/${name}_frami.dic
		fi
		if [ -e "$aff" ] && [ -e "$dic" ]; then
			mkdir -p "$INSTDIR/dictionaries/$name"
			ln -sfn "$aff" "$INSTDIR/dictionaries/$name/$name.aff"
			ln -sfn "$dic" "$INSTDIR/dictionaries/$name/$name.dic"
		fi
	done
fi

echo "Installed into $INSTDIR"
echo "Run ./run.sh"
