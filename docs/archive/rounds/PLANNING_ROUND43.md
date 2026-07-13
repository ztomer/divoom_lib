# Round 43 — Permissions Dialog, Settings Backup/Restore, Preset Files, and Wall Split Cache

Planning and outcomes for Round 43 batch, addressing macOS Notification permissions feedback, settings and preset file backup/restore, and display wall split caching.

## Proposed Changes

### 1. macOS Notification Center Full Disk Access Permissions Check & Dialog
- **Goal**: Guide the Mac user on how to resolve sqlite3.OperationalError or database blocked/permission errors due to TCC sandbox Full Disk Access restrictions.
- **Changes**:
  - Modified [settings_features.js](file:///Users/ztomer/Projects/divoom-control/divoom_gui/web_ui/settings_features.js) to define a modal dialog `window.showMacPermissionsDialog(errorMessage)` with step-by-step instructions.
  - Updated `renderMacNotifStatus(s)` to check for permission errors, set status to `Permission Error` (red), append a `Fix Permissions...` button to open the modal, and automatically trigger the modal once per session.
  - Updated `macToggle` change listener to show the modal if starting the listener returns a permission error.

### 2. General Settings Backup & Restore
- **Goal**: Allow the user to export and import all configuration and settings files (`presets.json`, `config.ini`, `alarms.json`, `hotchannel.json`, `notification_routing.json`) to/from a single JSON file.
- **Changes**:
  - Backend handlers (`export_settings_dialog`, `export_settings_to_path`, `import_settings_dialog`, and `import_settings_from_path`) were already implemented in [presets_manager.py](file:///Users/ztomer/Projects/divoom-control/divoom_gui/presets_manager.py).
  - Modified [templates_settings.js](file:///Users/ztomer/Projects/divoom-control/divoom_gui/web_ui/templates_settings.js) to add a "Backup & Restore" card in Settings -> Appearance containing "Export to File..." and "Import from File..." buttons.
  - Modified [settings_hardware.js](file:///Users/ztomer/Projects/divoom-control/divoom_gui/web_ui/settings_hardware.js) to wire these buttons to the backend dialogs, showing a toast on export and reloading the window on import.

### 3. Display Wall Presets Export & Import Files
- **Goal**: Allow saving and loading Virtual Wall layout presets to/from JSON files. Also immediately sync selected presets when chosen from the dropdown.
- **Changes**:
  - Backend handlers (`save_preset_file` and `load_preset_file`) were already implemented in [presets_manager.py](file:///Users/ztomer/Projects/divoom-control/divoom_gui/presets_manager.py).
  - Modified [index.html](file:///Users/ztomer/Projects/divoom-control/divoom_gui/web_ui/index.html) to add "Save File..." and "Load File..." buttons in the arranger toolbar.
  - Modified [app_init.js](file:///Users/ztomer/Projects/divoom-control/divoom_gui/web_ui/app_init.js) to wire these buttons to call the backend APIs.
  - Updated `#presets-select` change listener in `app_init.js` to trigger `window.syncArrangerToPython()` immediately after applying a preset to ensure the backend is in sync.

### 4. Display Wall Image Downscaling & Crop Cache
- **Goal**: Resolve the `'Divoom' object has no attribute 'show_image'` crash on push, crop/split quadrants, and cache the resulting files to avoid redundant resizing.
- **Changes**:
  - Modified [wall.py](file:///Users/ztomer/Projects/divoom-control/divoom_lib/wall.py) to save cropped slice quadrants under `~/.config/divoom-control/cache_wall/` using a deterministic MD5-based key. Reuses cached splits if they exist.
  - Modified [lighting.py](file:///Users/ztomer/Projects/divoom-control/divoom_gui/api/lighting.py) to rebuild the wall instance and correctly distinguish wall targets from single active device targets.
  - Modified [gallery.css](file:///Users/ztomer/Projects/divoom-control/divoom_gui/web_ui/gallery.css) to fix flex layout selectors for `#pixel-hot-channel` and `#pixel-gallery` sub-tabs, repairing the hot-channel button layout when many preview items are present.
  - Modified [test_wall.py](file:///Users/ztomer/Projects/divoom-control/tests/test_wall.py) to make the `Path.exists` mock conditional so that cache file checks do not falsely report as existing.

## Verification Plan

### Automated Tests
- Created a new test file [test_r42_backup_restore.py](file:///Users/ztomer/Projects/divoom-control/tests/test_r42_backup_restore.py) containing tests for:
  - Settings backup/restore export and import serialization/deserialization.
  - Layout presets saving and loading to/from JSON files.
  - Display wall image split caching.
- Run `python3 -m pytest` to verify the entire test suite passes.

### Manual Verification
- **macOS notification permissions modal**: Toggling notification mirroring when database permission is blocked correctly displays the permissions instructions modal.
- **Settings Backup/Restore**: Settings can be exported to a JSON file, and importing a valid backup JSON file restores configurations and reloads the window.
- **Save/Load Preset File**: Virtual wall layouts can be exported to JSON files, cleared, and restored successfully.
- **Display wall caching**: Image pushes to a wall target successfully crop and save slices under the `cache_wall` folder on disk.

## Outcome — SHIPPED

- **All implemented changes verified and functional.**
- **Custom Art empty screen race condition resolved**: Fixed race condition in `custom_art.js` initialization that sometimes left the Custom Art grid and buttons uninitialized/blank by replacing the readyState bootstrap check with a direct element existence check.
- **Coroutine warning fixes**: Closed the coroutines explicitly on exceptions in `owner_art.py` custom art push and query page handlers, resolving the `RuntimeWarning` from unawaited coroutines during unit tests.
- **Test suite fully green**: Local and GitHub Actions CI suites passed cleanly (1331 passed, 75 skipped, 0 warnings/failures).
