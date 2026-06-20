#!/usr/bin/env bash
# make_dev_daemon_app.sh — build a minimal .app that runs the SOURCE daemon with
# a Bluetooth usage description, so it can be `open`ed (LaunchServices re-parents
# the TCC responsible process to the bundle) and granted BLE once, then reused.
#
# Why: macOS attributes Bluetooth TCC by *responsible process*. A bare
# `python -m divoom_lib.cli daemon` launched from an un-granted shell is
# attributed to that shell and HARD-CRASHES on first CoreBluetooth touch
# (no NSBluetoothAlwaysUsageDescription). Wrapping it in a .app launched via
# `open` makes the .app the responsible process; its Info.plist supplies the
# usage string, so the first BT touch PROMPTS instead of crashing, and the grant
# (bundle id com.divoom.devdaemon) persists.
#
# Usage:
#   scripts/make_dev_daemon_app.sh            # build into dist/
#   open "dist/Divoom Dev Daemon.app"         # launch granted source daemon
#                                             # (click Allow on the BT prompt once)
# The daemon listens on /tmp/divoom.sock (the default) — drive it with
# scripts/hw_smoke.py or any DaemonClient.
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PY="${1:-$(command -v python3.14 || command -v python3)}"
APP="$REPO/dist/Divoom Dev Daemon.app"
SOCK="${DIVOOM_DEV_SOCKET:-/tmp/divoom.sock}"

rm -rf "$APP"
mkdir -p "$APP/Contents/MacOS"

cat > "$APP/Contents/Info.plist" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>CFBundleName</key><string>Divoom Dev Daemon</string>
  <key>CFBundleDisplayName</key><string>Divoom Dev Daemon</string>
  <key>CFBundleIdentifier</key><string>com.divoom.devdaemon</string>
  <key>CFBundleVersion</key><string>1</string>
  <key>CFBundleShortVersionString</key><string>1.0</string>
  <key>CFBundlePackageType</key><string>APPL</string>
  <key>CFBundleExecutable</key><string>run</string>
  <key>LSUIElement</key><true/>
  <key>NSBluetoothAlwaysUsageDescription</key>
  <string>Divoom Dev Daemon uses Bluetooth to test connecting to and controlling Divoom pixel displays.</string>
</dict>
</plist>
PLIST

cat > "$APP/Contents/MacOS/run" <<RUN
#!/bin/bash
# The SOURCE daemon — picks up live edits in $REPO every launch.
cd "$REPO"
export PYTHONPATH="$REPO"
exec "$PY" -m divoom_lib.cli daemon --socket "$SOCK" >> /tmp/divoom_dev_daemon.log 2>&1
RUN
chmod +x "$APP/Contents/MacOS/run"

# Register with LaunchServices so `open` finds it by bundle id.
/System/Library/Frameworks/CoreServices.framework/Frameworks/LaunchServices.framework/Support/lsregister -f "$APP" 2>/dev/null || true

echo "built: $APP"
echo "python: $PY"
echo "socket: $SOCK"
echo "launch: open \"$APP\"   (click Allow on the first Bluetooth prompt)"
