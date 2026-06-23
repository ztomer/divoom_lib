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
