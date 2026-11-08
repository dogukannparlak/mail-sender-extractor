#!/bin/sh
# Render packaging/macos/icon.svg into packaging/macos/icon.icns (macOS only).
# Optional: build.sh skips the icon if this file does not exist.
set -eu
cd "$(dirname "$0")"
SVG=icon.svg
WORK=$(mktemp -d)
trap 'rm -rf "$WORK"' EXIT
qlmanage -t -s 1024 -o "$WORK" "$SVG" >/dev/null 2>&1
PNG="$WORK/icon.svg.png"
[ -f "$PNG" ] || { echo "Could not render the SVG with qlmanage" >&2; exit 1; }
SET="$WORK/icon.iconset"
mkdir "$SET"
for s in 16 32 128 256 512; do
  sips -z $s $s "$PNG" --out "$SET/icon_${s}x${s}.png" >/dev/null
  sips -z $((s * 2)) $((s * 2)) "$PNG" --out "$SET/icon_${s}x${s}@2x.png" >/dev/null
done
iconutil -c icns "$SET" -o icon.icns
echo "Wrote $(pwd)/icon.icns"
