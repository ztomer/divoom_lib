#!/usr/bin/env bash
# run_native.sh — run divoom-control locally: the Python pywebview GUI, which
# spawns the native Rust daemon (divoomd) and the native Rust menubar
# (divoom-menubar) automatically. Build the Rust bits first with ./build_native.sh.
#
#   ./run_native.sh            launch the GUI (auto-spawns daemon + menubar)
#   ./run_native.sh --menubar  run ONLY the Rust menubar agent in the foreground
#                              (quick tray smoke; needs a daemon for live status)
#   ./run_native.sh --debug    prefer the debug Rust binaries
#
# Socket defaults to /tmp/divoom.sock; override with DIVOOM_SOCKET.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=tui/lib.sh
source "$ROOT/tui/lib.sh"
cd "$ROOT"

PROFILE="release"; MODE="gui"
for a in "$@"; do
  case "$a" in
    --menubar)  MODE="menubar" ;;
    --debug)    PROFILE="debug" ;;
    -h|--help)  echo "usage: ./run_native.sh [--menubar] [--debug]"; exit 0 ;;
    *)          die "unknown option: $a (try --help)" ;;
  esac
done

MENUBAR="native-port/divoom-menubar/target/$PROFILE/divoom-menubar"

if [[ "$MODE" == "menubar" ]]; then
  [[ -x "$MENUBAR" ]] || die "menubar not built — run ./build_native.sh${PROFILE/release/} first"
  section "Rust menubar (foreground)"
  info "Ctrl-C to quit. Launch Dashboard needs DIVOOM_GUI_PYTHON/SCRIPT (the GUI sets these)."
  export DIVOOM_GUI_PYTHON="${DIVOOM_GUI_PYTHON:-$(command -v python3)}"
  export DIVOOM_GUI_SCRIPT="${DIVOOM_GUI_SCRIPT:-$ROOT/divoom_gui/gui_main.py}"
  exec "$MENUBAR"
fi

# Default: launch the Python GUI (it spawns the daemon + menubar itself).
require_commands python3
[[ -x "$MENUBAR" ]] || warn "menubar not built (no tray this run) — ./build_native.sh to enable it"
section "Divoom GUI (Python) + native daemon/menubar"
info "the GUI spawns divoomd + divoom-menubar; first BLE use prompts for Bluetooth"
exec python3 -m divoom_gui.gui_main
