# Round 41 — UI, Startup, Reconnect, Virtual Wall & CI Fixes

Planning and outcomes for the Round 41 batch, addressing UI layout adjustments, startup/connection behaviors, re-authentication, Virtual Wall coordinates and previews, and test harness enhancements.

## Proposed Changes

### 1. Channels & Pixel Art Tab Reorganization
- **Goal**: Remove empty/duplicate elements and constrain pixel-art tab content so that the "Push Page to Device" button remains pinned at the bottom.
- **Changes**:
  - Modified [index.html](file:///Users/ztomer/Projects/divoom-control/divoom_gui/web_ui/index.html) to remove the empty Custom Art channel tab and panel (`#panel-design`).
  - Modified [custom_art.css](file:///Users/ztomer/Projects/divoom-control/divoom_gui/web_ui/custom_art.css) to set `#pixel-art.tab-content.active` to `height: 100%; min-height: 0;`.

### 2. Gallery Split-Layout Scroll Fix
- **Goal**: Ensure the community gallery scrolls internally instead of scrolling the entire card.
- **Changes**:
  - Modified [gallery.css](file:///Users/ztomer/Projects/divoom-control/divoom_gui/web_ui/gallery.css) to force `.gallery-split-card` and `.gallery-split-layout` to fill height with a flex layout and hide overflow at the card level.

### 3. Routines Layout Adjustments
- **Goal**: Polish target device row layout (right-align toggles, increase spacing/padding) and shrink Auto-Sync card width to match Rams/Kare design aesthetics.
- **Changes**:
  - Modified [gallery.js](file:///Users/ztomer/Projects/divoom-control/divoom_gui/web_ui/gallery.js) to right-align toggles (`toggle.style.marginLeft = "auto"`) and increase row padding to 13px.
  - Modified [gallery.css](file:///Users/ztomer/Projects/divoom-control/divoom_gui/web_ui/gallery.css) to increase target list gap to 5px.
  - Modified [templates_routines.js](file:///Users/ztomer/Projects/divoom-control/divoom_gui/web_ui/templates_routines.js) to shrink the Auto-Sync card to 336px, increase vertical margin to 18px, and swap Anniversary/Alarms order.

### 4. Device Settings Cleanup
- **Goal**: Remove redundant header and shrink card width.
- **Changes**:
  - Modified [templates_device_settings.js](file:///Users/ztomer/Projects/divoom-control/divoom_gui/web_ui/templates_device_settings.js) to remove the card-header and shrink max-width to 448px.

### 5. Startup Auto-Scan & Auto-Connect
- **Goal**: Trigger BLE scan on startup unconditionally and immediately populate UI with cached/discovered devices.
- **Changes**:
  - Modified [settings_hardware.js](file:///Users/ztomer/Projects/divoom-control/divoom_gui/web_ui/settings_hardware.js) to export `populateDeviceSelectors` on `window` and change default scan timeout to 60s.
  - Modified [templates_settings.js](file:///Users/ztomer/Projects/divoom-control/divoom_gui/web_ui/templates_settings.js) to set `scan-timeout` default to 60s.
  - Modified [app_init.js](file:///Users/ztomer/Projects/divoom-control/divoom_gui/web_ui/app_init.js) to populate discovered devices on load and run BLE auto-scan unconditionally.

### 6. Cloud Credentials Expiry & Re-auth
- **Goal**: Gracefully handle credential expiry by auto-reauthenticating once before reporting fetch errors.
- **Changes**:
  - Modified [gallery_sync.py](file:///Users/ztomer/Projects/divoom-control/divoom_gui/gallery_sync.py) to catch token errors, clear credentials cache, retry once, and notify the window via `onGalleryFetchError` upon permanent failure.
  - Modified [gallery.js](file:///Users/ztomer/Projects/divoom-control/divoom_gui/web_ui/gallery.js) to implement `window.onGalleryFetchError` toast notification and error layout. Fixed JS syntax mismatch.

### 7. Tivoo-Max Speaker Specification Fix
- **Goal**: Detect Tivoo Max as speaker-capable.
- **Changes**:
  - Modified [settings_hardware.js](file:///Users/ztomer/Projects/divoom-control/divoom_gui/web_ui/settings_hardware.js) and [app_globals.js](file:///Users/ztomer/Projects/divoom-control/divoom_gui/web_ui/app_globals.js) to include `tivoo` in speaker regex.

### 8. Menu Bar App Error Details
- **Goal**: Bubble up errors from notification listener to the macOS menu bar.
- **Changes**:
  - Modified [daemon_protocol.py](file:///Users/ztomer/Projects/divoom-control/divoom_daemon/daemon_protocol.py) to add `error` argument to `make_status_event`.
  - Modified [notification_service.py](file:///Users/ztomer/Projects/divoom-control/divoom_daemon/notification_service.py) to send `self._error`.
  - Modified [menubar_client.py](file:///Users/ztomer/Projects/divoom-control/divoom_menubar/menubar_client.py) to parse errors from events.
  - Modified [menubar.py](file:///Users/ztomer/Projects/divoom-control/divoom_menubar/menubar.py) to show a disabled error menu item and update tooltips dynamically.

### 9. Virtual Wall Coordinates & Previews
- **Goal**: Fix `is_free_form` check to avoid defaulting width/height, and render cropped slice previews on the arranger canvas.
- **Changes**:
  - Modified [device_owner.py](file:///Users/ztomer/Projects/divoom-control/divoom_daemon/device_owner.py) to build `configs` omitting default dimension fields.
  - Modified [wall.py](file:///Users/ztomer/Projects/divoom-control/divoom_lib/wall.py) to record cropped slice bytes in `self.last_previews` and expose base64 preview retrieval.
  - Modified [lighting.py](file:///Users/ztomer/Projects/divoom-control/divoom_gui/api/lighting.py) to return previews from `display_wall_image`.
  - Modified [app_init.js](file:///Users/ztoomer/Projects/divoom-control/divoom_gui/web_ui/app_init.js) to handle previews and redraw arranger canvas.
  - Renamed "Matrix Wall Grid" to "Virtual Wall" in [app_globals.js](file:///Users/ztomer/Projects/divoom-control/divoom_gui/web_ui/app_globals.js) and [app_init.js](file:///Users/ztomer/Projects/divoom-control/divoom_gui/web_ui/app_init.js).

### 10. CI Test Seed Customization
- **Goal**: Allow seed replication for native downscaler stress tests.
- **Changes**:
  - Modified [test_native_downscaler.py](file:///Users/ztomer/Projects/divoom-control/tests/test_native_downscaler.py) to read `DIVOOM_TEST_SEED` environment variable and report seed on failure.

---

## Verification Plan

### Automated Tests
- Run `python3 -m pytest` to execute the full unit and E2E test suite.
- Verify `test_file_size.py` passes under the 500-LOC rule limit.
- Verify `test_web_ui_js_syntax.py` parses all JS files cleanly.

---

## Outcome — SHIPPED

- **All 13 changes successfully implemented and verified.**
- **Test suite fully green**: 1321 passed, 75 skipped, 0 failed.
- Resolved `gallery_sync.py` syntax and LOC size errors (LOC reduced to ~485 LOC by moving general helper functions to `gallery_hot_api.py`).
- Resolved `gallery.js` syntax bracket mismatch.
