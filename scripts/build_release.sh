#!/usr/bin/env bash
# build_release.sh — build the self-contained Divoom.app + Divoom-v<version>.dmg
# for the Homebrew cask. macOS only.
#
# Produces (under dist/):
#   Divoom.app                — self-contained (bundled Python + deps)
#   Divoom-v<version>.dmg      — the cask artifact
#   Divoom-v<version>.dmg.sha256
#
# It does NOT ship references/ (the decompiled APK), tests/, or scripts/ — see
# setup_app.py's explicit package list + excludes.
#
# Usage:
#   python3 -m venv .buildvenv
#   .buildvenv/bin/pip install -e '.[gui]' py2app
#   .buildvenv/bin/python -V    # must be a py2app-supported Python
#   scripts/build_release.sh [path-to-build-venv-python]
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "${ROOT}"

if [[ "$(uname -s)" != "Darwin" ]]; then
  echo "build_release.sh is macOS-only." >&2
  exit 1
fi

PYBUILD="${1:-${ROOT}/.buildvenv/bin/python}"
if [[ ! -x "${PYBUILD}" ]]; then
  echo "Build venv python not found at ${PYBUILD}." >&2
  echo "Create it:  python3 -m venv .buildvenv && .buildvenv/bin/pip install -e '.[gui]' py2app" >&2
  exit 1
fi

VERSION="$(grep -m1 '^version' pyproject.toml | sed -E 's/.*"(.*)".*/\1/')"
# setup_app.py reads the version from this env override because the py2app step
# below renames pyproject.toml out of the way (so setup_app can't read it then).
export DIVOOM_BUILD_VERSION="${VERSION}"
echo "Building Divoom Control v${VERSION}"

# 1. Native dylib (palette encoder / downsampler / framing).
echo "→ building native dylib"
bash scripts/build_libdivoom.sh

# 1b. Native Rust daemon — shipped INSIDE the bundle (setup_app.py data_files) so
#     the app runs the native `divoomd` (now at full parity with the Python daemon),
#     not the Python fallback. setup_app skips it if the binary is absent.
echo "→ building native rust daemon (divoomd)"
if ! command -v cargo >/dev/null 2>&1 && [ -x "${HOME}/.cargo/bin/cargo" ]; then
  export PATH="${HOME}/.cargo/bin:${PATH}"
fi
if command -v cargo >/dev/null 2>&1; then
  ( cd native-port/divoomd && cargo build --release )
  echo "→ building native rust menubar (divoom-menubar)"
  ( cd native-port/divoom-menubar && cargo build --release )
else
  echo "ERROR: cargo not found — needed to bundle the native daemon (divoomd)." >&2
  exit 1
fi

# 2. py2app. setuptools auto-merges pyproject's [project] deps into the py2app
#    setup() → "install_requires is no longer supported"; hide it for the build.
echo "→ py2app build"
rm -rf build dist
mv pyproject.toml .pyproject.toml.hidden
restore_pyproject() { mv -f .pyproject.toml.hidden pyproject.toml 2>/dev/null || true; }
trap restore_pyproject EXIT
"${PYBUILD}" setup_app.py py2app
restore_pyproject
trap - EXIT

# 2b. Ensure the native daemon landed in the bundle + is executable (a data_files
#     copy can drop the +x bit).
DIVOOMD_IN_APP="dist/Divoom.app/Contents/Resources/divoomd"
if [[ -f "${DIVOOMD_IN_APP}" ]]; then
  chmod +x "${DIVOOMD_IN_APP}"
  # Re-sign the bundled copy so the adhoc signature covers the binary as shipped
  # (py2app copies it post-build). The embedded __info_plist (NSBluetoothAlways…)
  # lets macOS TCC attribute a Bluetooth grant to the daemon.
  codesign --force --sign - "${DIVOOMD_IN_APP}" 2>/dev/null \
    && echo "→ bundled native daemon: $(ls -lh "${DIVOOMD_IN_APP}" | awk '{print $5}') (re-signed)" \
    || echo "WARN: codesign of ${DIVOOMD_IN_APP} failed"
  if ! otool -s __TEXT __info_plist "${DIVOOMD_IN_APP}" | grep -q .; then
    echo "ERROR: bundled divoomd is missing the embedded __info_plist (TCC BT grant won't work)." >&2
    exit 1
  fi
else
  echo "ERROR: divoomd was not bundled into the .app (expected ${DIVOOMD_IN_APP})." >&2
  exit 1
fi

# 2c. Same for the native menubar agent (spawned by the GUI; +x can be dropped by
#     the data_files copy). Adhoc re-sign so it runs under the bundle's signature.
MENUBAR_IN_APP="dist/Divoom.app/Contents/Resources/divoom-menubar"
if [[ -f "${MENUBAR_IN_APP}" ]]; then
  chmod +x "${MENUBAR_IN_APP}"
  codesign --force --sign - "${MENUBAR_IN_APP}" 2>/dev/null \
    && echo "→ bundled native menubar: $(ls -lh "${MENUBAR_IN_APP}" | awk '{print $5}') (re-signed)" \
    || echo "WARN: codesign of ${MENUBAR_IN_APP} failed"
else
  echo "WARN: divoom-menubar not bundled (expected ${MENUBAR_IN_APP}) — no menu-bar in this build." >&2
fi

# 3. Guard: the reverse-engineered APK / references must never be in the bundle.
if find dist/Divoom.app \( -iname '*smali*' -o -path '*references*' -o -iname '*.apk' \) | grep -q .; then
  echo "ERROR: reverse-engineered references leaked into the bundle — aborting." >&2
  exit 1
fi

# 4. .dmg (plain folder image with an /Applications symlink for drag-install).
DMG="dist/Divoom-v${VERSION}.dmg"
echo "→ packaging ${DMG}"
STAGE="$(mktemp -d)"
cp -R "dist/Divoom.app" "${STAGE}/"
ln -s /Applications "${STAGE}/Applications"
rm -f "${DMG}"
hdiutil create -volname "Divoom Control" -srcfolder "${STAGE}" -ov -format UDZO "${DMG}" >/dev/null
rm -rf "${STAGE}"

# 5. sha256 for the cask.
shasum -a 256 "${DMG}" | tee "${DMG}.sha256"
echo "Done: ${DMG}"
