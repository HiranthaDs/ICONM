#!/bin/zsh
set -euo pipefail

APP_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$APP_DIR"

echo "Building ICON MOBILE ERP macOS .app"

if ! command -v python3 >/dev/null 2>&1; then
  echo "python3 is not installed. Install Python 3 for macOS first."
  exit 1
fi

python3 - <<'PY'
import sys
if sys.version_info < (3, 12):
    raise SystemExit("Python 3.12 or newer is required to build this app.")
PY

python3 -m venv .venv-build
source .venv-build/bin/activate
python -m pip install --upgrade pip setuptools wheel
python -m pip install -r requirements.txt
python -m pip install -r requirements-mac-build.txt

python diagnose.py

ICON_SOURCE="assets/app_icon_1024.png"
ICON_FILE="assets/ICON_MOBILE_ERP.icns"
ICONSET_DIR="assets/ICON_MOBILE_ERP.iconset"
if [ -f "$ICON_SOURCE" ]; then
  rm -rf "$ICONSET_DIR"
  mkdir -p "$ICONSET_DIR"
  sips -z 16 16     "$ICON_SOURCE" --out "$ICONSET_DIR/icon_16x16.png" >/dev/null
  sips -z 32 32     "$ICON_SOURCE" --out "$ICONSET_DIR/icon_16x16@2x.png" >/dev/null
  sips -z 32 32     "$ICON_SOURCE" --out "$ICONSET_DIR/icon_32x32.png" >/dev/null
  sips -z 64 64     "$ICON_SOURCE" --out "$ICONSET_DIR/icon_32x32@2x.png" >/dev/null
  sips -z 128 128   "$ICON_SOURCE" --out "$ICONSET_DIR/icon_128x128.png" >/dev/null
  sips -z 256 256   "$ICON_SOURCE" --out "$ICONSET_DIR/icon_128x128@2x.png" >/dev/null
  sips -z 256 256   "$ICON_SOURCE" --out "$ICONSET_DIR/icon_256x256.png" >/dev/null
  sips -z 512 512   "$ICON_SOURCE" --out "$ICONSET_DIR/icon_256x256@2x.png" >/dev/null
  sips -z 512 512   "$ICON_SOURCE" --out "$ICONSET_DIR/icon_512x512.png" >/dev/null
  sips -z 1024 1024 "$ICON_SOURCE" --out "$ICONSET_DIR/icon_512x512@2x.png" >/dev/null
  iconutil -c icns "$ICONSET_DIR" -o "$ICON_FILE"
  rm -rf "$ICONSET_DIR"
fi

rm -rf build dist
pyinstaller --noconfirm --clean IMERP_V_GM.spec

APP_PATH="dist/ICON MOBILE ERP.app"
if [ -d "$APP_PATH" ]; then
  if command -v codesign >/dev/null 2>&1; then
    codesign --force --deep --sign - "$APP_PATH" || true
  fi
  if command -v hdiutil >/dev/null 2>&1; then
    DMG_STAGE="dist/dmg-stage"
    rm -rf "$DMG_STAGE"
    mkdir -p "$DMG_STAGE"
    cp -R "$APP_PATH" "$DMG_STAGE/"
    ln -s /Applications "$DMG_STAGE/Applications"
    rm -f "dist/ICON_MOBILE_ERP_macOS.dmg"
    hdiutil create -volname "ICON MOBILE ERP" -srcfolder "$DMG_STAGE" -ov -format UDZO "dist/ICON_MOBILE_ERP_macOS.dmg"
    rm -rf "$DMG_STAGE"
    hdiutil verify "dist/ICON_MOBILE_ERP_macOS.dmg"
  fi
  echo ""
  echo "Build complete:"
  echo "  $APP_PATH"
  echo "  dist/ICON_MOBILE_ERP_macOS.dmg"
  echo ""
  echo "Open the DMG and drag ICON MOBILE ERP to Applications."
else
  echo "Build failed: .app was not created."
  exit 1
fi
