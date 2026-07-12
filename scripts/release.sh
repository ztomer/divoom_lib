#!/usr/bin/env bash
#
# release.sh — one-shot release for divoom-control. In order:
#   1. build the DMG (scripts/build_release.sh)  [skippable]
#   2. git tag vX.Y.Z (annotated, notes from CHANGELOG) + push to origin
#   3. GitHub release on the code repo with the DMG attached
#   4. bump the Homebrew cask (version + sha256) in the tap repo
#
# The version is read from pyproject.toml — bump it there first. Idempotent:
# re-running clobbers the DMG asset and re-PUTs the cask, so a partial run is
# safe to resume.
#
#   scripts/release.sh                # full run
#   scripts/release.sh --skip-build   # reuse an existing dist/ DMG (faster)
#
# Requires: gh (authenticated: `gh auth login`), the macOS build toolchain that
# scripts/build_release.sh needs, and push access to both repos below.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

REPO="ztomer/divoom_lib"          # code repo — hosts the tag + release + DMG asset
TAP="ztomer/homebrew-tap"         # cask repo
CASK_PATH="Casks/divoom-control.rb"

SKIP_BUILD=0
[ "${1:-}" = "--skip-build" ] && SKIP_BUILD=1

VERSION="$(python3 -c "import tomllib; print(tomllib.load(open('pyproject.toml','rb'))['project']['version'])")"
TAG="v${VERSION}"
DMG="dist/Divoom-${TAG}.dmg"      # name MUST match the cask url (Divoom-v#{version}.dmg)

echo "→ release ${TAG}  (repo ${REPO}, tap ${TAP})"

# ── preflight ───────────────────────────────────────────────────────────────
command -v gh >/dev/null || { echo "ERROR: gh CLI required (brew install gh)" >&2; exit 1; }
gh auth status >/dev/null 2>&1 || { echo "ERROR: gh not authenticated — run: gh auth login" >&2; exit 1; }
if [ -n "$(git status --porcelain --untracked-files=no)" ]; then
  echo "⚠ working tree has uncommitted TRACKED changes — the tag will point at HEAD," >&2
  echo "  which does not include them. Commit or stash first, or press Ctrl-C." >&2
  sleep 3
fi
BRANCH="$(git rev-parse --abbrev-ref HEAD)"
[ "$BRANCH" = "main" ] || echo "⚠ tagging from branch '${BRANCH}', not main (the tag captures HEAD regardless)."

# ── 1. build DMG ────────────────────────────────────────────────────────────
if [ "$SKIP_BUILD" -eq 1 ] && [ -f "$DMG" ]; then
  echo "→ reusing existing ${DMG}"
else
  echo "→ building ${DMG}"
  bash scripts/build_release.sh
fi
[ -f "$DMG" ] || { echo "ERROR: ${DMG} not found after build" >&2; exit 1; }
SHA="$(shasum -a 256 "$DMG" | awk '{print $1}')"
echo "  sha256 ${SHA}"

# ── 2. release notes: every CHANGELOG section newer than the last published
#      release (so a catch-up release covers all of it; a normal release is just
#      the one new section). ──────────────────────────────────────────────────
LAST="$(gh release list --repo "$REPO" -L 1 --json tagName --jq '.[0].tagName' 2>/dev/null || true)"
NOTES="$(mktemp)"
trap 'rm -f "$NOTES"' EXIT
VER="$VERSION" LAST="${LAST#v}" python3 - > "$NOTES" <<'PY'
import os, re
ver = os.environ["VER"]; last = os.environ.get("LAST", "")
text = open("CHANGELOG.md").read()
start = re.search(r'^## v%s\b' % re.escape(ver), text, re.M)
if not start:
    print(f"Release {ver}"); raise SystemExit
end = None
if last:
    e = re.search(r'^## v%s\b' % re.escape(last), text, re.M)
    if e:
        end = e.start()
if end is None:  # no known prior release → just this one section
    nxt = re.search(r'(?m)^## v', text[start.end():])
    end = start.end() + nxt.start() if nxt else len(text)
print(text[start.start():end].strip())
PY

# ── 3. git tag + push ───────────────────────────────────────────────────────
if git rev-parse "$TAG" >/dev/null 2>&1; then
  echo "→ tag ${TAG} already exists (leaving it)"
else
  echo "→ tagging ${TAG} at $(git rev-parse --short HEAD)"
  git tag -a "$TAG" -F "$NOTES"
fi
echo "→ pushing tag to origin"
git push origin "$TAG"

# ── 4. GitHub release (+ DMG asset) ─────────────────────────────────────────
if gh release view "$TAG" --repo "$REPO" >/dev/null 2>&1; then
  echo "→ release ${TAG} exists — clobbering the DMG asset"
  gh release upload "$TAG" "$DMG" --repo "$REPO" --clobber
else
  echo "→ creating GitHub release ${TAG}"
  gh release create "$TAG" "$DMG" --repo "$REPO" --title "$TAG" --notes-file "$NOTES"
fi

# ── 5. bump the Homebrew cask (version + sha256) ────────────────────────────
echo "→ bumping cask ${TAP}/${CASK_PATH} → ${VERSION}"
CUR_SHA="$(gh api "repos/${TAP}/contents/${CASK_PATH}" --jq .sha)"
CUR_CASK="$(gh api "repos/${TAP}/contents/${CASK_PATH}" --jq .content | base64 --decode)"
NEW_CASK="$(printf '%s' "$CUR_CASK" | VER="$VERSION" SHA="$SHA" python3 -c "
import os, re, sys
s = sys.stdin.read()
s = re.sub(r'version \"[^\"]+\"', 'version \"%s\"' % os.environ['VER'], s, count=1)
s = re.sub(r'sha256 \"[0-9a-fA-F]+\"', 'sha256 \"%s\"' % os.environ['SHA'], s, count=1)
sys.stdout.write(s)
")"
if [ "$NEW_CASK" = "$CUR_CASK" ]; then
  echo "  cask already at ${VERSION} with this sha — no change"
else
  gh api -X PUT "repos/${TAP}/contents/${CASK_PATH}" \
    -f message="divoom-control ${VERSION}" \
    -f content="$(printf '%s' "$NEW_CASK" | base64 | tr -d '\n')" \
    -f sha="$CUR_SHA" >/dev/null
  echo "  cask updated"
fi

echo ""
echo "✓ released ${TAG}"
echo "  release: https://github.com/${REPO}/releases/tag/${TAG}"
echo "  install: brew install --cask ztomer/tap/divoom-control"
