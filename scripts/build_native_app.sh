#!/usr/bin/env bash
# build_native_app.sh — assemble the fully-native (Python-free) macOS app:
#   dist-native/Divoom Native.app
#     Contents/MacOS/divoom-ui            (eframe/egui GUI + tray menubar)
#     Contents/MacOS/divoomd              (native daemon — spawned by the UI)
#     Contents/MacOS/libdivoom_compact.dylib  (C image encoder, FFI)
#     Contents/Info.plist                 (BT usage strings, LSUIElement off)
#
# NON-DESTRUCTIVE: this is a SEPARATE artifact under dist-native/. It does NOT
# touch the Python py2app build (scripts/build_release.sh), the shipped Homebrew
# cask, or any default — i.e. no cutover. macOS only.
#
# The bundle is self-contained: divoom-ui spawns the sibling divoomd and points
# DIVOOMD_ENCODER_LIB at the sibling dylib. BLE still needs a one-time Bluetooth
# grant on first launch (the embedded Info.plist makes macOS show the prompt).
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "${ROOT}"

if [[ "$(uname -s)" != "Darwin" ]]; then
  echo "build_native_app.sh is macOS-only." >&2
  exit 1
fi

if ! command -v cargo >/dev/null 2>&1 && [[ -x "${HOME}/.cargo/bin/cargo" ]]; then
  export PATH="${HOME}/.cargo/bin:${PATH}"
fi
command -v cargo >/dev/null 2>&1 || { echo "cargo not found" >&2; exit 1; }

VERSION="$(grep -m1 '^version' pyproject.toml | sed -E 's/.*"(.*)".*/\1/')"
APP="dist-native/Divoom Native.app"
echo "Building fully-native Divoom Native.app v${VERSION}"

# 1. C encoder dylib (palette quantizer / framing) — reused via FFI.
echo "-> building libdivoom_compact.dylib"
bash scripts/build_libdivoom.sh

# 2. Native binaries (release).
echo "-> cargo build --release (divoomd)"
( cd native-port/divoomd && cargo build --release )
echo "-> cargo build --release (divoom-ui)"
( cd native-port/divoom-ui && cargo build --release )

DAEMON="native-port/divoomd/target/release/divoomd"
UI="native-port/divoom-ui/target/release/divoom-ui"
DYLIB="divoom_lib/libdivoom_compact.dylib"
for f in "${DAEMON}" "${UI}" "${DYLIB}"; do
  [[ -f "$f" ]] || { echo "missing build artifact: $f" >&2; exit 1; }
done

# 3. Assemble the .app.
echo "-> assembling ${APP}"
rm -rf "${APP}"
mkdir -p "${APP}/Contents/MacOS" "${APP}/Contents/Resources"
cp "${UI}" "${APP}/Contents/MacOS/divoom-ui"
cp "${DAEMON}" "${APP}/Contents/MacOS/divoomd"        # sibling: UI spawns it
cp "${DYLIB}" "${APP}/Contents/MacOS/libdivoom_compact.dylib"  # sibling: encoder
chmod +x "${APP}/Contents/MacOS/divoom-ui" "${APP}/Contents/MacOS/divoomd"

cat > "${APP}/Contents/Info.plist" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>CFBundleName</key><string>Divoom Native</string>
  <key>CFBundleDisplayName</key><string>Divoom Native</string>
  <key>CFBundleIdentifier</key><string>com.divoom.control.native</string>
  <key>CFBundleExecutable</key><string>divoom-ui</string>
  <key>CFBundlePackageType</key><string>APPL</string>
  <key>CFBundleShortVersionString</key><string>${VERSION}</string>
  <key>CFBundleVersion</key><string>${VERSION}</string>
  <key>LSMinimumSystemVersion</key><string>11.0</string>
  <key>NSHighResolutionCapable</key><true/>
  <key>LSUIElement</key><false/>
  <key>NSBluetoothAlwaysUsageDescription</key>
  <string>Divoom Control connects to your Divoom pixel displays over Bluetooth.</string>
  <key>NSBluetoothPeripheralUsageDescription</key>
  <string>Divoom Control connects to your Divoom pixel displays over Bluetooth.</string>
</dict>
</plist>
PLIST

# 4. Adhoc codesign (so the embedded Info.plist is honored for the TCC BT prompt).
echo "-> codesigning (adhoc)"
codesign --force --deep --sign - "${APP}" 2>/dev/null \
  && echo "   signed" || echo "   WARN: codesign failed (unsigned bundle still runs locally)"

# 5. Guard: no reverse-engineered references leaked in.
if find "${APP}" \( -iname '*smali*' -o -path '*references*' -o -iname '*.apk' \) | grep -q .; then
  echo "ERROR: reverse-engineered references leaked into the bundle." >&2
  exit 1
fi

echo "Done: ${APP}"
echo "Launch:  open '${APP}'    (first BLE use prompts for Bluetooth)"
