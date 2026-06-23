#!/usr/bin/env bash
# make_divoomd_app.sh — wrap the divoomd binary in a signed .app so macOS
# attributes the CoreBluetooth TCC grant to a stable identity (com.divoom.divoomd).
# The daemon runs in the background (LSUIElement) on /tmp/divoomd.sock; drive it
# over that socket with the existing Python DaemonClient.
#
# Usage:
#   cargo build --release            # builds with the `ble` feature (default)
#   ./make_divoomd_app.sh
#   open "dist/Divoom Daemon (rs).app"     # first run: macOS prompts for Bluetooth
#   tail -f /tmp/divoomd.log               # daemon logs
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BIN="${HERE}/target/release/divoomd"
APP="${HERE}/dist/Divoom Daemon (rs).app"
SOCK="${DIVOOMD_SOCKET:-/tmp/divoomd.sock}"

if [[ ! -x "${BIN}" ]]; then
  echo "build first:  cargo build --release   (missing ${BIN})" >&2
  exit 1
fi

rm -rf "${APP}"
mkdir -p "${APP}/Contents/MacOS"
cp "${HERE}/Info.plist" "${APP}/Contents/Info.plist"
cp "${BIN}" "${APP}/Contents/MacOS/divoomd"
# launcher: run the daemon on the socket, logging to /tmp/divoomd.log
cat > "${APP}/Contents/MacOS/run" <<RUN
#!/usr/bin/env bash
exec "\$(dirname "\$0")/divoomd" --socket "${SOCK}" >> /tmp/divoomd.log 2>&1
RUN
chmod +x "${APP}/Contents/MacOS/run" "${APP}/Contents/MacOS/divoomd"

codesign --force --sign - --identifier com.divoom.divoomd "${APP}" 2>/dev/null \
  && echo "signed (ad-hoc): ${APP}" \
  || echo "WARN: codesign failed (TCC may prompt attributed to the terminal)"

echo "built: ${APP}"
echo "run:   open \"${APP}\"   (grant Bluetooth on first launch)"
echo "socket: ${SOCK}   logs: /tmp/divoomd.log"
