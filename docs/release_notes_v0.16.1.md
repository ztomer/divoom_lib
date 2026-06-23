# Divoom Control v0.16.1 — packaged app startup fix (2026-06-22)

This patch release fixes a startup crash when running the packaged macOS app bundle `Divoom.app` installed via the Homebrew cask.

## Fixes

- **Fixed `ModuleNotFoundError: No module named 'gui_api'` on startup.** 
  The app bundle uses `py2app` to package Python dependencies. `py2app` copies the main launcher script `gui_main.py` directly to the `Contents/Resources/` directory while putting the remaining `divoom_gui` package under `Contents/Resources/lib/python3.14/divoom_gui/`. 
  
  Because of this, the folder-relative imports inside the GUI package (e.g. `from gui_api import DivoomGuiAPI`, `from presets_manager import ...`, etc.) failed to resolve, as the subfolder `divoom_gui` was no longer on `sys.path`.
  
  All GUI imports have been updated to use the standard package prefix `divoom_gui.` (e.g., `from divoom_gui.gui_api import DivoomGuiAPI`), which correctly resolves within both the packaged app bundle and the local development environment.
  
- **Cleaned up Test `sys.path` Hacks.**
  Cleaned up tests that manipulated `sys.path` to import GUI modules directly as top-level files, updating them to standard package-prefixed imports.

## Verification

- Rebuilt the app bundle (`scripts/build_release.sh`) and confirmed successful startup of `dist/Divoom.app` without crashes.
- Ran the full test suite (`python3 -m pytest`) and verified all 1700 tests passed successfully.
