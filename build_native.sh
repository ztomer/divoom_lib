#!/usr/bin/env bash
# build_native.sh — build the native (Rust/egui) Divoom UI + daemon.
#
#   ./build_native.sh            release binaries + C encoder dylib
#                                (ready for ./run_native.sh)
#   ./build_native.sh --app      also assemble the macOS .app bundle + .dmg
#                                (delegates to scripts/build_native_app.sh; macOS)
#   ./build_native.sh --debug    debug build (faster compile, slower runtime)
#
# Non-destructive: only builds the native artifacts; never touches the Python app.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=tui/lib.sh
source "$ROOT/tui/lib.sh"
cd "$ROOT"

PROFILE="release"; FLAG="--release"; APP=0
for a in "$@"; do
  case "$a" in
    --app)        APP=1 ;;
    --debug)      PROFILE="debug"; FLAG="" ;;
    -h|--help)    echo "usage: ./build_native.sh [--app] [--debug]"; exit 0 ;;
    *)            die "unknown option: $a (try --help)" ;;
  esac
done

require_commands cargo

if [[ "$APP" == "1" ]]; then
  [[ "$(uname -s)" == "Darwin" ]] || die "--app is macOS-only"
  section "Native .app bundle"
  bash scripts/build_native_app.sh
  exit 0
fi

section "Native binaries ($PROFILE)"

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

info "cargo build ${FLAG:-(debug)} — divoom-ui"
( cd native-port/divoom-ui && cargo build $FLAG )
ok "divoom-ui"

section "Done"
ok "binaries under native-port/*/target/$PROFILE/"
if [[ "$PROFILE" == "debug" ]]; then
  info "run it with:  ./run_native.sh --debug"
else
  info "run it with:  ./run_native.sh"
fi
