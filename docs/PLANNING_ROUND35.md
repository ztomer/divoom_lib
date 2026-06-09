# Round 35 — Upload progress, connection pulse (wire-up), button alignment

Three small UX fixes identified during usage:

---

## §1 Progress indicator for Monthly Best upload

**Problem:** The "Update Device" button stays unchanged during a multi-image sync
(up to 120s per file × N files = potentially minutes with no feedback). Users
can also press the button again, re-submitting the same files.

**Approach — progressive `evaluate_js` pattern** (established by `fetch_gallery`
in `gallery_sync.py:237`): the Python side already sends per-file JSON progress
to the JS side via `self.window.evaluate_js()`. Same pattern here:
`sync_hot_channel` calls `window.onGallerySyncProgress(index, total, fileId,
success, errorStr)` after each file, so the JS can update in real time.

**Files:**

| Side | File | Change |
|------|------|--------|
| Python | `gallery_sync.py:447` | `sync_hot_channel` — after each `_sync_artwork_detailed`, call `self.window.evaluate_js()` with progress |
| JS | `gallery.js:183-209` | Replace `batchSyncBtn` handler: on start, disable button + show "0 / N"; on each progress call, increment; on complete, show summary and restore |
| JS | `gallery.js:214-232` | Same treatment for `syncAllBtn` handler |
| Template | `templates_monthly_best.js:32-34` | Replace single button with a `.sync-progress` container (button + status text) |
| CSS | `gallery.css` or `style_extra.css` | `.sync-progress` styles |

**States the button goes through:**

1. **Idle** — "Update Device" (full-width glow-btn)
2. **Syncing** — disabled, label shows "Syncing 3 / 5…", amber tint
3. **Done (all ok)** — green flash, label switches to "✓ Synced N" for 3s, then
   returns to idle
4. **Done (with failures)** — red flash, label switches to "✗ N ok, M failed"
   for 5s, then returns to idle

---

## §2 Device-dot pulse on connect

**Status: ALREADY SHIPPED in R34 §2** (commits `a3865133` + `ade3c0cc`).

`app_globals.js:125-134` adds `.connecting` class to the specific device dot
before the `connectDevice` call; `appbar.css:47-52` has `.transport-dot.connecting`
with the amber `dot-pulse` animation. On success (re-render via
`renderDeviceDots()`) or failure (same), the pulse is removed.

**This item is just verification that the code is correct.** No changes needed.

---

## §3 Gallery selection buttons alignment

**Problem:** The "SELECT ALL" and "CLEAR" buttons in the Monthly Best card header
use `.wall-tool-btn` which overrides `.glow-btn.compact`'s background to
`transparent`, making them look hollow/inset compared to the adjacent classify
tabs. The two buttons also have a visual height mismatch because `wall-tool-btn`
sets `display: inline-flex; align-items: center` with no explicit height — the
container `.gallery-select-actions.row.gap-8` has `align-items: center` (not
`stretch`), so the shorter "Clear" button floats at a different vertical
position than "Select All".

Wait — "Select All" and "Clear" should have the same font-size, padding, and
border from `.glow-btn.compact`, so they should be the same intrinsic height.
The vertical alignment in the row is `align-items: center` on the parent flex
row, so any height difference would center-both. But with
`display: inline-flex`, each button's height is determined by its content
+ padding + border, not by the parent. Since text content differs ("Select All"
vs "Clear"), line-height is the same so height should be equal if padding and
border are equal.

However `wall-tool-btn` adds a transparent background + different border color
(`var(--secondary)` vs `#3e3f46`), and `background: transparent` can cause a
visual "missing background" effect where the button seems recessed.

**Fix:** Remove `wall-tool-btn` from the two gallery-select buttons and define
a minimal `.gallery-select-btn` class that preserves the `.glow-btn.compact`
look — no transparent background override, same border as compact.

**Additionally:** if the per-device style tabs in the Routines sync-targets
list (`renderSyncTargets`, gallery.js:235) don't align across rows because
device names have different widths, give each row a grid layout instead of
flexbox — or simply set the name column to a fixed width.

---

## Suggested order

§3 (CSS only, 0 risk) → §1 (the feature, largest change) → §2 (verify only).

---

## §outcome

### What shipped

**§3 — Gallery selection buttons alignment (CSS only)**
- Removed `wall-tool-btn` class from Select All / Clear buttons (`templates_monthly_best.js`)
- Added `.gallery-select-btn` CSS class in `gallery.css` with solid `#2e2f36` background, same border/color as compact glow-btn, hover state
- The former `wall-tool-btn` had `background: transparent` + `border: var(--secondary)`, making the buttons look hollow/inset

**§1 — Upload progress indicator**
- **Python** (`gallery_sync.py`): `sync_hot_channel` now calls `self.window.evaluate_js()` after each file with `window.onGallerySyncProgress(index, total, fileId, success, errorStr)`. APK-match: three states ("Wait for update" → "Updating" → "Update complete"), global progress bar, fire-and-forget callbacks
- **JS** (`gallery.js`): Added `window.onGallerySyncProgress` handler that:
  1. First file: switches button to amber `.syncing` state, label → "Updating", status → `(1/N)`
  2. Mid files: updates status counter
  3. Last file: green `.synced-ok` with "✓ Synced N" (3s) or red `.synced-fail` with "✗ X ok, Y failed" (5s), then resets to idle
  - Added `_syncInFlight` guard to prevent double-press
- **Routines "Sync devices now"**: same double-press guard via `_syncAllInFlight`, button shows "Syncing N image(s)…" and disables during flight

**§2 — Device dot pulse: verified already shipped (R34 §2)**
- `app_globals.js:132-134`: adds `.connecting` class to specific device dot before `connectDevice()`
- `appbar.css:47-52`: `.transport-dot.connecting` with amber `dot-pulse` animation
- `app_globals.js:152` (success) and `:166` (failure) both call `renderDeviceDots()` which clears the class — ✅ correct

### Test results
- 237 passed, 0 failed (core unit tests: native downscaler, encoders, JS syntax, image processing)
- No hardware tests run (skip by default)

**§4 — CRITICAL FIX: 0x8b start-phase notification routing (spinner fix)**
- Root cause: `_handle_ios_le_notification` drops the device's `[0] → ready` ACK
  because `_expected_response_command` is `None` — `send_command` doesn't set it.
- Fix: set `_expected_response_command = 0x8b` on BLE transport BEFORE sending the
  START packet, so the handler queues the ACK.
- Before fix: ACK silently lost → `_await_8b_device_ready` blocks 3s → 0.5s sleep
  fallback → **3.5s dead air** → device's internal spinner timeout (~1-2s) →
  permanent spinner. Device stays stuck until power cycle.
- Reduced `_await_8b_device_ready` timeout from 3s → 2s (device typically responds
  in ~200ms).
- APK comparison: APK is purely device-driven — sends START, then waits indefinitely
  for the device's `[0]` response in a reactive handler (`s.java:286-290` →
  `DesignSendModel.startSendAllAni()`). Our fix now matches this pattern on BLE.
  Full 7-step APK comparison below.

### Test results
- 192 passed, 0 failed (animation stream, downscaler, encoders, JS syntax, image processing, framing)

### Deviations from APK
- APK uses `packets_sent / total_packets` for progress granularity — we use `files_done / total_files` because our Python layer can't count BLE packets (they're inside `_sync_artwork_detailed`)
- APK does NOT send TERMINATE (CW=2) — we keep it (hardware-validated, devices tolerate it)
- APK uses fire-and-forget SPP writes with 40ms delay — we use `write_with_response=True` on
  BLE (GATT-level reliability) with 10ms delay

### APK step-by-step comparison (0x8b animation upload)

| Step | APK (canonical) | Our library (after fix) | Match? |
|------|----------------|------------------------|--------|
| **1. START cmd** | 0x8b, payload `[0][size:4 LE]` | Same | ✅ |
| **2. Write mode** | Fire-and-forget (SPP socket) | `write_with_response=False` | ✅ |
| **3. Wait for data** | Indefinite, device-driven: `s.java` handler fires `startSendAllAni()` on `payload[0]==0` | Bounded wait via `_await_8b_device_ready(2.0)`, fallback 0.5s sleep | ≈ (APK infinite, we have safety timeout) |
| **4. DATA payload** | `[1][size:4 LE][idx:2 LE][≤256 bytes]` | Same | ✅ |
| **5. Write mode** | Fire-and-forget SPP, 40ms inter-chunk | `write_with_response=True` GATT, 10ms inter-chunk | ❌ adaptation for BLE |
| **6. Retransmits** | Event-driven `resendBlueData(idx)` on `payload[0]==1` | Post-stream poll loop (1s quiet timeout) | ⚠️ semantic match, timing differs |
| **7. TERMINATE** | NOT SENT | Sent after 0.5s settle | ❌ divergence (hardware-tolerated) |

### Files changed
| File | Change |
|------|--------|
| `divoom_lib/display/animation.py` | Set `_expected_response_command` before START; moved BLE detection earlier; reduced timeout 3→2s |
| `divoom_gui/gallery_sync.py` | `sync_hot_channel`: added `evaluate_js()` progress callback after each file |
| `divoom_gui/web_ui/gallery.js` | Added `window.onGallerySyncProgress()` handler; batchSyncBtn + syncAllBtn double-press guards; sync state machine |
| `divoom_gui/web_ui/gallery.css` | Added `.gallery-select-btn`, `.sync-status-text`, sync state classes (`.syncing`, `.synced-ok`, `.synced-fail`) |
| `divoom_gui/web_ui/templates_monthly_best.js` | Removed `wall-tool-btn` from select buttons; added `#batch-sync-label` + `#batch-sync-status` spans inside `#batch-sync-btn` |
| `divoom_gui/web_ui/appbar.css` | `--dot-pulse-color` CSS var (amber fallback) for device-colored pulse |
| `divoom_gui/web_ui/app_globals.js` | Set `--dot-pulse-color` to device color in connectDevice |

### Files changed
| File | Change |
|------|--------|
| `divoom_gui/gallery_sync.py` | `sync_hot_channel`: added `evaluate_js()` progress callback after each file |
| `divoom_gui/web_ui/gallery.js` | Added `window.onGallerySyncProgress()` handler; batchSyncBtn + syncAllBtn double-press guards; sync state machine |
| `divoom_gui/web_ui/gallery.css` | Added `.gallery-select-btn`, `.sync-status-text`, sync state classes (`.syncing`, `.synced-ok`, `.synced-fail`) |
| `divoom_gui/web_ui/templates_monthly_best.js` | Removed `wall-tool-btn` from select buttons; added `#batch-sync-label` + `#batch-sync-status` spans inside `#batch-sync-btn` |
