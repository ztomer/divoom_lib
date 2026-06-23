# Releasing Divoom Control

The app ships as a self-contained `Divoom.app` inside a `.dmg`, installed via the
Homebrew cask in `ztomer/homebrew-tap` (`brew install --cask ztomer/tap/divoom-control`).

**The release artifact must never contain the reverse-engineered APK / `references/`.**
`setup_app.py` only bundles the four runtime packages + their data; `build_release.sh`
hard-fails if anything matching `*smali*`/`references`/`*.apk` is found in the bundle.

## 1. Bump the version

- `pyproject.toml` → `version = "X.Y.Z"` — this is the **single source of truth**.
  `setup_app.py` reads it (via `DIVOOM_BUILD_VERSION`, which `build_release.sh`
  exports, with a `pyproject.toml` fallback), so the bundle's CFBundleVersion can
  never drift from the package version. Do NOT hardcode the version elsewhere.
- Add a CHANGELOG entry + a `docs/release_notes_vX.Y.Z.md`.

## 2. Build the `.dmg`

py2app needs a supported Python. (Built successfully on 3.14 with py2app 0.28.10.)

```bash
python3 -m venv .buildvenv
.buildvenv/bin/pip install -e '.[gui]' py2app
scripts/build_release.sh .buildvenv/bin/python
```

Produces `dist/Divoom-vX.Y.Z.dmg` + `.dmg.sha256`. The script builds the native
dylib, runs py2app (hiding `pyproject.toml` so setuptools doesn't inject
`install_requires`, which py2app rejects), packages the `.dmg`, and runs the
no-leak guard.

## 3. Verify the `.app` on hardware (one-time BT grant)

```bash
open dist/Divoom.app
```

- First scan prompts for Bluetooth — **grant it once** (the bundle declares
  `NSBluetoothAlwaysUsageDescription`, so macOS shows the normal dialog).
- Confirm: device scan finds screens, connect + push works, the menu-bar agent
  appears, and the daemon spawns (`/tmp/divoom_daemon.log`). In a bundle the GUI
  spawns the daemon/menubar with the bundled `Contents/MacOS/python` and does NOT
  TCC-disclaim (the `.app` is already the BT-responsible process).

## 4. Tag + GitHub release (outward-facing — do once verified)

```bash
git tag vX.Y.Z && git push origin vX.Y.Z
gh release create vX.Y.Z dist/Divoom-vX.Y.Z.dmg \
  --title "vX.Y.Z" --notes-file <release-notes.md>
```

## 5. Update the Homebrew cask

In `ztomer/homebrew-tap`, `Casks/divoom-control.rb`:
- `version "X.Y.Z"`
- `sha256 "<contents of dist/Divoom-vX.Y.Z.dmg.sha256>"`

```bash
cd ../homebrew-tap
git add Casks/divoom-control.rb && git commit -m "divoom-control X.Y.Z" && git push
```

Verify: `brew install --cask ztomer/tap/divoom-control`.
