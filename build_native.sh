#!/usr/bin/env bash
# build_native.sh — build the native (Rust) pieces of divoom-control:
#   - divoomd        (the daemon)
#   - divoom-menubar (the menubar/tray agent)
#   - libdivoom_compact.dylib (C image encoder, macOS, via FFI)
#
# The desktop UI is the Python pywebview GUI (build it for release with
# scripts/build_release.sh / py2app). This script only builds the Rust binaries
# the GUI spawns at runtime.
#
#   ./build_native.sh           release binaries + encoder dylib
#   ./build_native.sh --debug   debug build (faster compile, slower runtime)
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=tui/lib.sh
source "$ROOT/tui/lib.sh"
cd "$ROOT"

PROFILE="release"; FLAG="--release"
for a in "$@"; do
  case "$a" in
    --debug)   PROFILE="debug"; FLAG="" ;;
    -h|--help) echo "usage: ./build_native.sh [--debug]"; exit 0 ;;
    *)         die "unknown option: $a (try --help)" ;;
  esac
done

require_commands cargo

section "Native Rust binaries ($PROFILE)"

# C encoder dylib (image / pixel-art / text encoding via FFI). macOS → .dylib.
if [[ "$(uname -s)" == "Darwin" ]]; then
  info "building C encoder dylib"
  if bash scripts/build_libdivoom.sh >/dev/null 2>&1; then
    ok "libdivoom_compact.dylib"
  else
    warn "encoder dylib build failed — image push won't encode (UI/control still work)"
  fi
fi

info "cargo build ${FLAG:-(debug)} — divoomd"
( cd native-port/divoomd && cargo build $FLAG )
ok "divoomd"

info "cargo build ${FLAG:-(debug)} — divoom-menubar"
( cd native-port/divoom-menubar && cargo build $FLAG )
ok "divoom-menubar"

section "Done"
ok "binaries under native-port/*/target/$PROFILE/"
if [[ "$PROFILE" == "debug" ]]; then
  info "run the app with:  ./run_native.sh --debug"
else
  info "run the app with:  ./run_native.sh"
fi
