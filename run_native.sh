#!/usr/bin/env bash
# run_native.sh — run the native (Rust/egui) Divoom UI locally.
#
#   ./run_native.sh           dev: start divoomd (BLE) on a shared socket, then the
#                             UI; the daemon is stopped when the UI exits.
#   ./run_native.sh --app     open the built macOS .app bundle instead
#                             (the only path where the Bluetooth prompt works).
#   ./run_native.sh --fake    UI only, no daemon — fake devices + seeded previews
#                             (headless visual check; no hardware needed).
#   ./run_native.sh --debug   use the debug binaries (pair with build --debug).
#
# Socket defaults to /tmp/divoom.sock; override with DIVOOM_SOCKET.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=tui/lib.sh
source "$ROOT/tui/lib.sh"
cd "$ROOT"

PROFILE="release"; MODE="dev"
for a in "$@"; do
  case "$a" in
    --app)             MODE="app" ;;
    --fake|--headless) MODE="fake" ;;
    --debug)           PROFILE="debug" ;;
    -h|--help)         echo "usage: ./run_native.sh [--app|--fake] [--debug]"; exit 0 ;;
    *)                 die "unknown option: $a (try --help)" ;;
  esac
done

UI="native-port/divoom-ui/target/$PROFILE/divoom-ui"
DAEMON="native-port/divoomd/target/$PROFILE/divoomd"
DYLIB="$ROOT/divoom_lib/libdivoom_compact.dylib"
ASSETS="$ROOT/divoom_gui/web_ui/assets"
SOCKET="${DIVOOM_SOCKET:-/tmp/divoom.sock}"

# --- open the packaged .app -------------------------------------------------
if [[ "$MODE" == "app" ]]; then
  APP="dist-native/Divoom Native.app"
  [[ -d "$APP" ]] || die "no bundle — build it first:  ./build_native.sh --app"
  ok "opening $APP"
  open "$APP"
  exit 0
fi

if [[ ! -x "$UI" ]]; then
  if [[ "$PROFILE" == "debug" ]]; then
    die "UI not built — run ./build_native.sh --debug first"
  else
    die "UI not built — run ./build_native.sh first"
  fi
fi

# --- headless / fake-devices UI (no daemon) --------------------------------
if [[ "$MODE" == "fake" ]]; then
  section "Native UI — fake devices (no daemon)"
  export DIVOOM_UI_NO_TRAY=1 DIVOOM_UI_FAKE_DEVICES="Pixoo64" DIVOOM_UI_FAKE_PREVIEW=1
  [[ -d "$ASSETS" ]] && export DIVOOM_UI_ASSETS="$ASSETS"
  exec "$UI"
fi

# --- dev: daemon + UI -------------------------------------------------------
[[ -x "$DAEMON" ]] || die "daemon not built — run ./build_native.sh first"
section "Native UI — dev (daemon + UI)"

if [[ -f "$DYLIB" ]]; then
  export DIVOOMD_ENCODER_LIB="$DYLIB"
else
  warn "encoder dylib missing — image/pixel-art push won't encode (run ./build_native.sh)"
fi
[[ -d "$ASSETS" ]] && export DIVOOM_UI_ASSETS="$ASSETS"

# Start the daemon we manage. If another instance already owns the socket, the
# daemon self-guards and exits immediately — the UI just uses the existing one.
LOG="/tmp/divoomd-dev.log"
info "starting divoomd on $SOCKET (BLE; logs: $LOG)"
"$DAEMON" --socket "$SOCKET" >"$LOG" 2>&1 &
DAEMON_PID=$!
cleanup() { kill "$DAEMON_PID" 2>/dev/null || true; }
trap cleanup EXIT INT TERM

# Wait up to ~5s for the socket to appear.
for _ in $(seq 1 50); do [[ -S "$SOCKET" ]] && break; sleep 0.1; done
if [[ -S "$SOCKET" ]]; then ok "daemon ready"; else warn "daemon socket not up — see $LOG"; fi

info "launching UI — Ctrl-C or close the window to quit"
DIVOOM_SOCKET="$SOCKET" "$UI" || true
ok "UI exited; stopping daemon"
