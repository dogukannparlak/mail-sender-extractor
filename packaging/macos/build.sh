#!/bin/sh
# "Mail Sender Extractor.app" üretir (PyInstaller).
#   packaging/macos/build.sh          -> dist/Mail Sender Extractor.app
#   packaging/macos/build.sh dmg      -> also dist/Mail-Sender-Extractor-<version>.dmg
#   packaging/macos/build.sh install  -> /Applications'a kopyalar (açıksa kapatır)
# Geçici sanal ortam build/venv'de kurulur; sistem Python'una bir şey kurulmaz.
set -eu
ROOT=$(cd "$(dirname "$0")/../.." && pwd)
cd "$ROOT"
PY=${PYTHON:-python3}
VENV=build/venv
NAME="Mail Sender Extractor"
VERSION=$(sed -n 's/^__version__ = "\(.*\)"/\1/p' mail_cleaner/__init__.py)
WANT_DMG=0
for arg in "$@"; do [ "$arg" = dmg ] && WANT_DMG=1; done
WANT_INSTALL=0
for arg in "$@"; do [ "$arg" = install ] && WANT_INSTALL=1; done

mkdir -p dist build
touch dist/.metadata_never_index build/.metadata_never_index
LSREGISTER=/System/Library/Frameworks/CoreServices.framework/Frameworks/LaunchServices.framework/Support/lsregister

[ -d "$VENV" ] || "$PY" -m venv "$VENV"
"$VENV/bin/python" -m pip install --quiet --upgrade pip
"$VENV/bin/python" -m pip install --quiet -r requirements.txt -r requirements-desktop.txt

# --icon yolu boşluk içerebilir (proje klasörü "Mail Sender Extractor"): argümanlar tırnaklı kalsın.
ICON_FILE="$ROOT/packaging/macos/icon.icns"
[ -f "$ICON_FILE" ] || ICON_FILE=""

set -- --noconfirm --clean --windowed --specpath build \
  --name "$NAME" \
  --osx-bundle-identifier io.github.dogukannparlak.mail-sender-extractor \
  --paths "$ROOT" \
  --add-data "$ROOT/mail_cleaner/static:mail_cleaner/static" \
  --add-data "$ROOT/mail_cleaner/templates:mail_cleaner/templates" \
  --add-data "$ROOT/mail_cleaner/locales:mail_cleaner/locales" \
  --add-data "$ROOT/doc:doc" \
  --add-data "$ROOT/doc-tr:doc-tr" \
  packaging/macos/entry.py
[ -n "$ICON_FILE" ] && set -- --icon "$ICON_FILE" "$@"
"$VENV/bin/pyinstaller" "$@"

APP="dist/$NAME.app"
/usr/libexec/PlistBuddy -c "Set :CFBundleShortVersionString $VERSION" "$APP/Contents/Info.plist" 2>/dev/null \
  || /usr/libexec/PlistBuddy -c "Add :CFBundleShortVersionString string $VERSION" "$APP/Contents/Info.plist"
"$LSREGISTER" -u "$APP" 2>/dev/null || true
echo "Built: $ROOT/$APP"

if [ "$WANT_DMG" = 1 ]; then
  DMG="dist/Mail-Sender-Extractor-$VERSION.dmg"
  STAGE=$(mktemp -d)
  trap 'rm -rf "$STAGE"' EXIT
  cp -R "$APP" "$STAGE/"
  ln -s /Applications "$STAGE/Applications"
  rm -f "$DMG"
  hdiutil create -quiet -volname "$NAME" -srcfolder "$STAGE" -format UDZO "$DMG"
  echo "Built: $ROOT/$DMG"
fi

if [ "$WANT_INSTALL" = 1 ]; then
  pkill -f "/$NAME.app/Contents/MacOS" 2>/dev/null || true
  sleep 1
  rm -rf "/Applications/$NAME.app"
  cp -R "$APP" /Applications/
  rm -rf "$APP"
  echo "Installed: /Applications/$NAME.app"
fi
