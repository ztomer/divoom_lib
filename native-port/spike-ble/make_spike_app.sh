#!/usr/bin/env bash
# make_spike_app.sh — wrap the built spike binary in a minimal .app so macOS
# attributes the CoreBluetooth TCC grant to a stable bundle identity (com.divoom
# .spikeble) instead of to the terminal. Mirrors scripts/make_dev_daemon_app.sh,
# which is the pattern that reliably owns Bluetooth for the Python dev daemon.
#
# Usage:
#   cargo build --release
#   ./make_spike_app.sh
#   open "dist/Divoom Spike BLE.app"        # first run: macOS prompts for Bluetooth
#   # logs: the app is LSUIElement (no dock icon); run the binary directly to see stdout:
#   "dist/Divoom Spike BLE.app/Contents/MacOS/divoom-spike-ble"
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BIN="${HERE}/target/release/divoom-spike-ble"
APP="${HERE}/dist/Divoom Spike BLE.app"

if [[ ! -x "${BIN}" ]]; then
  echo "build first:  cargo build --release   (missing ${BIN})" >&2
  exit 1
fi

rm -rf "${APP}"
mkdir -p "${APP}/Contents/MacOS"
cp "${HERE}/Info.plist" "${APP}/Contents/Info.plist"
cp "${BIN}" "${APP}/Contents/MacOS/divoom-spike-ble"
chmod +x "${APP}/Contents/MacOS/divoom-spike-ble"

# Ad-hoc codesign so the bundle has a stable identity for TCC. A real release
# would sign with a Developer ID; ad-hoc is enough to test the grant locally.
codesign --force --sign - --identifier com.divoom.spikeble "${APP}" 2>/dev/null \
  && echo "signed (ad-hoc): ${APP}" \
  || echo "WARN: codesign failed (TCC may still prompt, attributed to the terminal)"

echo "built: ${APP}"
echo "run:   open \"${APP}\"   (then check Bluetooth in System Settings > Privacy)"
echo "stdout: \"${APP}/Contents/MacOS/divoom-spike-ble\""
