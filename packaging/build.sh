#!/bin/bash
# Build "AirDrop Compress.app" and a .dmg installer.
#
#   packaging/build.sh                 unsigned (ad-hoc) build - fine for testing and GitHub releases
#   SIGN_IDENTITY="Developer ID Application: Your Name (TEAMID)" \
#   NOTARY_PROFILE=airdrop-compress packaging/build.sh
#                                      signed + notarised build (no Gatekeeper warning)
#
# One-time setup for notarisation:
#   xcrun notarytool store-credentials airdrop-compress --apple-id you@example.com --team-id TEAMID
#
# The app is built for this Mac's architecture (Apple silicon -> arm64, Intel -> x86_64).

set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

PY="${PYTHON:-$ROOT/.venv/bin/python}"
APP_NAME="AirDrop Compress"
VERSION="$("$PY" -c 'import airdrop_compress; print(airdrop_compress.__version__)')"
ARCH="$(uname -m)"
APP="dist/$APP_NAME.app"
DMG="dist/AirDrop-Compress-$VERSION-$ARCH.dmg"

step() { printf '\n\033[1m==> %s\033[0m\n' "$*"; }

step "Installing build dependencies"
"$PY" -m pip install --quiet -r requirements-dev.txt

step "Running tests"
"$PY" -m pytest -q

step "Creating the app icon"
ICONSET="build/AppIcon.iconset"
rm -rf "$ICONSET" && mkdir -p "$ICONSET"
qlmanage -t -s 1024 -o build airdrop_compress/ui/web/icon.svg >/dev/null 2>&1
MASTER="build/icon.svg.png"
for size in 16 32 128 256 512; do
  sips -z $size $size "$MASTER" --out "$ICONSET/icon_${size}x${size}.png" >/dev/null
  sips -z $((size * 2)) $((size * 2)) "$MASTER" --out "$ICONSET/icon_${size}x${size}@2x.png" >/dev/null
done
iconutil -c icns "$ICONSET" -o build/AppIcon.icns

step "Building $APP_NAME $VERSION ($ARCH)"
rm -rf "$APP" "dist/$APP_NAME"
"$PY" -m PyInstaller --noconfirm --clean --log-level WARN \
  --distpath dist --workpath build/pyinstaller packaging/AirDropCompress.spec
rm -rf "dist/$APP_NAME"  # the unbundled folder; only the .app ships

step "Signing"
if [[ -n "${SIGN_IDENTITY:-}" ]]; then
  codesign --force --deep --timestamp --options runtime \
    --entitlements packaging/entitlements.plist --sign "$SIGN_IDENTITY" "$APP"
else
  echo "No SIGN_IDENTITY set - ad-hoc signing (users will see an 'unidentified developer' prompt)."
  codesign --force --deep --sign - "$APP"
fi
codesign --verify --deep --strict "$APP"

step "Smoke test"
"$APP/Contents/MacOS/$APP_NAME" --version
"$APP/Contents/MacOS/$APP_NAME" plugin validate examples/plugins/svg-minify

step "Creating $DMG"
rm -f "$DMG"
"$PY" packaging/make_dmg_background.py build/dmg-assets
# dmgbuild lays out the window (background, icon positions) without scripting Finder.
"$PY" -m dmgbuild -s packaging/dmg_settings.py \
  -D app="$APP" \
  -D guide="packaging/How to open AirDrop Compress.html" \
  -D background="build/dmg-assets/background.png" \
  -D icon="build/AppIcon.icns" \
  "$APP_NAME" "$DMG"
if [[ -n "${SIGN_IDENTITY:-}" ]]; then
  codesign --force --timestamp --sign "$SIGN_IDENTITY" "$DMG"
fi

if [[ -n "${NOTARY_PROFILE:-}" ]]; then
  step "Notarising (this takes a few minutes)"
  xcrun notarytool submit "$DMG" --keychain-profile "$NOTARY_PROFILE" --wait
  xcrun stapler staple "$DMG"
fi

step "Done"
du -sh "$APP" "$DMG"
echo "Install: open $DMG and drag $APP_NAME to Applications."
