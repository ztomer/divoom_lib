"""Playwright + static-analysis regression tests for the Round 6 layout
changes documented in `docs/PLANNING_ROUND5.md` §3 and §4.

What this test file covers:

1. **Monthly Best layout (Option B):** the right card is now 23% width
   (grid `1.6fr 0.6fr`), the MAC address is gone from the sync-target
   rows, and the schedule block is removed from Monthly Best.
2. **Routines sub-tab:** Settings has a new "Routines" sub-tab that
   contains the auto-sync schedule, renamed from "Hot-Channel Schedule"
   to "Auto-Sync Gallery" per user pick.
3. **Volume slider in appbar:** the new appbar volume slider exists
   with a 0-15 range and the right label format.
4. **Scoreboard channel-card:** the new Scoreboard channel-card is
   in the Control Panel with the right number inputs and Show/Hide
   buttons.

Why static-analysis + Playwright, not full behavioral tests:
- The drag behavior already has its own dedicated test file
  (`test_gui_drag_instrumented.py`).
- These tests are about *layout existence and shape*, not user
  interaction. Static analysis catches regressions at the source
  level; Playwright catches them at the rendered DOM level.
- Hardware-gated BLE interactions (volume, scoreboard) cannot be
  tested headlessly; their transport-level correctness is covered
  by the existing `test_e2e_mock_device.py` test file.
"""
import re
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
INDEX_HTML = REPO_ROOT / "gui" / "web_ui" / "index.html"
TEMPLATES_JS = REPO_ROOT / "gui" / "web_ui" / "templates.js"
GALLERY_CSS = REPO_ROOT / "gui" / "web_ui" / "gallery.css"
GALLERY_JS = REPO_ROOT / "gui" / "web_ui" / "gallery.js"
SETTINGS_JS = REPO_ROOT / "gui" / "web_ui" / "settings.js"
APP_JS = REPO_ROOT / "gui" / "web_ui" / "app.js"
CHANNELS_JS = REPO_ROOT / "gui" / "web_ui" / "channels.js"
GUI_API_PY = REPO_ROOT / "gui" / "gui_api.py"


# ──────────────────────────────────────────────────────────────────
# 1. Monthly Best layout (Option B)
# ──────────────────────────────────────────────────────────────────


def test_monthly_best_header_is_devices_not_sync_targets():
    """The right card header in Monthly Best is now 'Devices' — the
    schedule was moved to Settings → Routines, so the header is no
    longer 'Sync Targets & Schedule'."""
    src = TEMPLATES_JS.read_text()
    # Find the right-card header (the one inside the .monthly-best-layout
    # block, not the Gallery card on the left).
    mb_match = re.search(
        r'<div class="monthly-best-layout">(.*?)</div>\s*</div>\s*`,',
        src, re.DOTALL,
    )
    assert mb_match is not None, "monthly-best-layout block not found in templates.js"
    block = mb_match.group(1)
    assert "Sync Targets &amp; Schedule" not in block, (
        "Monthly Best right card still has 'Sync Targets & Schedule' — "
        "the schedule was supposed to move to Settings → Routines "
        "(docs/PLANNING_ROUND5.md §3 Option B). Drop the old header."
    )
    assert re.search(r'<h3>\s*Devices\s*</h3>', block), (
        "Monthly Best right card should have <h3>Devices</h3> as its header."
    )


def test_monthly_best_schedule_block_removed():
    """The schedule block (hc-schedule + 'Enable scheduled sync' + Save
    Schedule button) must be REMOVED from Monthly Best — it moved to
    Settings → Routines."""
    src = TEMPLATES_JS.read_text()
    mb_match = re.search(
        r'<div class="monthly-best-layout">(.*?)</div>\s*</div>\s*`,',
        src, re.DOTALL,
    )
    assert mb_match is not None, "monthly-best-layout block not found in templates.js"
    block = mb_match.group(1)
    assert "hc-schedule" not in block, (
        "Monthly Best still has the .hc-schedule block — it should have "
        "moved to Settings → Routines (Routines sub-tab)."
    )
    assert "Enable scheduled sync" not in block, (
        "Monthly Best still has the 'Enable scheduled sync (runs headless)' "
        "checkbox — it should be gone (move to Routines, drop the "
        "developer-term 'headless')."
    )
    assert "hc-save-schedule-btn" not in block, (
        "Monthly Best still has the Save Schedule button — it should be "
        "in Settings → Routines."
    )


def test_monthly_best_grid_is_true_halve():
    """The Monthly Best grid is now 1.6fr 0.6fr (true halve: gallery 73%
    / devices 27%). Old value 1.4fr 1fr means the right card is still
    too wide and the gallery hasn't been given the dominant real estate."""
    css = GALLERY_CSS.read_text()
    # Locate the .monthly-best-layout grid-template-columns value.
    m = re.search(r"\.monthly-best-layout\s*\{[^}]*grid-template-columns:\s*([^;]+);", css)
    assert m is not None, ".monthly-best-layout grid-template-columns not found"
    cols = m.group(1).strip()
    assert cols == "1.6fr 0.6fr", (
        f"Expected '1.6fr 0.6fr' (true halve per docs/PLANNING_ROUND5.md §3), "
        f"got {cols!r}."
    )


def test_target_row_no_longer_creates_mac_address_element():
    """The renderSyncTargets function in gallery.js must NOT create
    a .target-addr element — the MAC address was dropped from the row
    per docs/PLANNING_ROUND5.md §3.b."""
    src = GALLERY_JS.read_text()
    fn_match = re.search(r"window\.renderSyncTargets\s*=\s*function[^{]*\{(.+?)\n\s*\}", src, re.DOTALL)
    assert fn_match is not None, "renderSyncTargets not found in gallery.js"
    fn_body = fn_match.group(1)
    assert "target-addr" not in fn_body, (
        "renderSyncTargets still creates a .target-addr element — "
        "the MAC address should be removed from the target row "
        "(already visible in Settings → Bluetooth Scanner)."
    )
    assert "addr.textContent" not in fn_body, (
        "renderSyncTargets still sets addr.textContent — the MAC "
        "address should not be rendered."
    )


def test_target_addr_css_class_removed():
    """The .target-addr CSS class should be gone from gallery.css — it
    was only used by the MAC-address element we removed."""
    css = GALLERY_CSS.read_text()
    # The selector should not exist (or be empty if it does).
    m = re.search(r"\.target-addr\s*\{[^}]*\}", css)
    assert m is None, (
        f".target-addr CSS class still defined in gallery.css: {m.group(0)!r}. "
        f"Remove it; the element is no longer created."
    )


# ──────────────────────────────────────────────────────────────────
# 2. Routines sub-tab in Settings
# ──────────────────────────────────────────────────────────────────


def test_settings_has_routines_subtab():
    """The Settings tab nav must include a 'Routines' sub-tab.
    (R15 §1+§7: `.settings-tab-btn` is now `.tab-btn`.)"""
    src = TEMPLATES_JS.read_text()
    assert re.search(
        r'<button class="tab-btn"[^>]*data-settings-tab="settings-routines"[^>]*>'
        r'(?:\s*<svg.*?</svg>)?\s*Routines\s*</button>',
        src, re.DOTALL,
    ), "Settings tab nav is missing the Routines sub-tab button."


def test_routines_subtab_content_exists():
    """The #settings-routines sub-tab content block must exist with
    the new 'Auto-Sync Gallery' card (renamed from Hot-Channel Schedule)."""
    src = TEMPLATES_JS.read_text()
    assert '<div class="settings-tab-content" id="settings-routines">' in src, (
        "settings-routines sub-tab content block not found in templates.js"
    )
    m = re.search(
        r'<div class="settings-tab-content" id="settings-routines">(.+?)</div>\s*</div>\s*</div>\s*</div>',
        src, re.DOTALL,
    )
    assert m is not None, "Could not locate Routines sub-tab block"
    block = m.group(1)
    assert "Auto-Sync Gallery" in block, (
        "Routines sub-tab should be titled 'Auto-Sync Gallery' "
        "(user picked this over 'Hot-Channel Schedule' in planning doc §8)."
    )
    # Old terminology must NOT appear in the Routines sub-tab.
    assert "Hot-Channel" not in block, (
        "Routines sub-tab still mentions 'Hot-Channel' — should be "
        "renamed to 'Auto-Sync Gallery' per user pick."
    )
    # The form elements must exist with the new ids.
    assert 'id="routines-auto-sync-enabled"' in block, "Missing routines-auto-sync-enabled checkbox"
    assert 'id="routines-auto-sync-interval"' in block, "Missing routines-auto-sync-interval select"
    assert 'id="routines-auto-sync-save"' in block, "Missing routines-auto-sync-save button"


def test_settings_js_wires_routines_form():
    """settings.js must wire the routines form save + load handlers."""
    src = SETTINGS_JS.read_text()
    assert "routines-auto-sync-save" in src, (
        "settings.js doesn't reference the routines save button id."
    )
    assert "routines-auto-sync-enabled" in src, (
        "settings.js doesn't read the routines enabled checkbox."
    )
    assert "loadRoutinesAutoSync" in src, (
        "settings.js should define loadRoutinesAutoSync() to load the config."
    )


def test_gallery_js_drops_schedule_handlers():
    """The schedule-related handlers (loadHotChannelSchedule + save button
    click) must be REMOVED from gallery.js — they moved to settings.js.
    We check for actual function definitions / call sites, not comments."""
    src = GALLERY_JS.read_text()
    # No actual call to the (now undefined) loadHotChannelSchedule function.
    assert not re.search(r"\b(loadHotChannelSchedule\s*\()", src), (
        "gallery.js still CALLS loadHotChannelSchedule() — this function "
        "moved to settings.js as loadRoutinesAutoSync. Remove the dead call "
        "or update it to call the new name."
    )
    # No function DEFINITION for loadHotChannelSchedule.
    assert not re.search(r"function\s+loadHotChannelSchedule\b", src), (
        "gallery.js still DEFINES loadHotChannelSchedule — it moved to settings.js."
    )
    # No reference to the old save-button id (active code path).
    assert not re.search(r"(getElementById|querySelector)\s*\(\s*[\"']hc-save-schedule-btn[\"']\s*\)", src), (
        "gallery.js still binds the old hc-save-schedule-btn click handler — "
        "it moved to settings.js."
    )


# ──────────────────────────────────────────────────────────────────
# 3. Volume slider in appbar
# ──────────────────────────────────────────────────────────────────


def test_appbar_volume_slider_exists():
    """The appbar must have a new volume slider with id
    'appbar-volume-slider' and a value display."""
    html = INDEX_HTML.read_text()
    assert 'id="appbar-volume-slider"' in html, (
        "appbar-volume-slider element not found in index.html"
    )
    assert 'id="appbar-volume-value"' in html, (
        "appbar-volume-value display not found in index.html"
    )
    # Range should be 0-15 (the protocol's actual range).
    m = re.search(
        r'<input[^>]*id="appbar-volume-slider"[^>]*>',
        html, re.DOTALL,
    )
    assert m is not None
    slider_html = m.group(0)
    assert 'min="0"' in slider_html, "Volume slider min should be 0"
    assert 'max="15"' in slider_html, (
        "Volume slider max should be 15 — the protocol's actual range "
        "(divoom.music.set_volume, 0x08). Kare: show the raw value."
    )


def test_appbar_volume_handler_in_app_js():
    """app.js must handle the volume slider's change event and call
    set_volume / get_volume on the API."""
    src = APP_JS.read_text()
    assert "appbar-volume-slider" in src, (
        "app.js doesn't reference the volume slider id."
    )
    assert "set_volume" in src, (
        "app.js doesn't call window.pywebview.api.set_volume — the "
        "slider's change handler must push the value to the device."
    )
    assert "get_volume" in src, (
        "app.js doesn't call window.pywebview.api.get_volume — the "
        "slider should initialize to the device's current volume."
    )


def test_gui_api_exposes_set_volume_and_get_volume():
    """gui_api.py must have set_volume(volume: int) -> bool and
    get_volume() -> int | None methods."""
    src = GUI_API_PY.read_text()
    assert re.search(r"def\s+set_volume\s*\(\s*self\s*,\s*volume:\s*int\s*\)", src), (
        "gui_api.py is missing set_volume(self, volume: int) method."
    )
    assert re.search(r"def\s+get_volume\s*\(\s*self\s*\)", src), (
        "gui_api.py is missing get_volume(self) method."
    )


# ──────────────────────────────────────────────────────────────────
# 4. Scoreboard channel-card
# ──────────────────────────────────────────────────────────────────


def test_scoreboard_channel_card_exists():
    """The Control Panel must have a Scoreboard tab-btn with
    data-channel='scoreboard'. (R15 §1+§7: `.channel-card` → `.tab-btn`.)"""
    html = INDEX_HTML.read_text()
    assert re.search(
        r'<button class="tab-btn"[^>]*data-channel="scoreboard"',
        html,
    ), "Scoreboard tab-btn not found in index.html"


def test_scoreboard_panel_has_number_inputs_and_no_buttons():
    """The #panel-scoreboard block must have red/blue number inputs.
    Show/Hide/Enabled buttons were REMOVED in the user feedback pass
    (Round 6.1) — scoreboard should behave like the other channels:
    click the card to switch, edit a number to apply."""
    html = INDEX_HTML.read_text()
    m = re.search(
        r'<div class="channel-panel" id="panel-scoreboard">(.+?)</div>\s*</div>\s*</div>',
        html, re.DOTALL,
    )
    assert m is not None, "panel-scoreboard not found in index.html"
    block = m.group(1)
    assert 'id="scoreboard-red"' in block, "Missing scoreboard-red input"
    assert 'id="scoreboard-blue"' in block, "Missing scoreboard-blue input"
    # Show / Hide / Enabled buttons must NOT exist.
    assert 'id="scoreboard-show-btn"' not in block, (
        "scoreboard-show-btn is back in the panel — it should be removed. "
        "Scoreboard should auto-apply on number-input change, like the other channels."
    )
    assert 'id="scoreboard-hide-btn"' not in block, (
        "scoreboard-hide-btn is back in the panel — it should be removed. "
        "Setting both scores to 0 happens automatically when the user clears them."
    )
    assert 'id="scoreboard-enabled"' not in block, (
        "scoreboard-enabled checkbox is back in the panel — it should be removed. "
        "Editing any number always enables the scoreboard tool."
    )
    # Range should be 0-999 (divoom.scoreboard clamps to 999).
    red_input = re.search(r'<input[^>]*id="scoreboard-red"[^>]*>', block)
    assert red_input is not None
    assert 'min="0"' in red_input.group(0)
    assert 'max="999"' in red_input.group(0)


def test_scoreboard_now_switches_channel():
    """The channel-card click handler must ALLOW scoreboard to call
    switch_channel (Round 6.1: it was previously in the skip list along
    with ambient). The scoreboard is a tool on channel 0x06, so
    switch_channel('scoreboard') switches the device to that channel
    and the user can then edit scores."""
    src = CHANNELS_JS.read_text()
    # The scoreboard-specific skip must be GONE (only ambient is skipped now).
    assert 'activeChannel === "scoreboard"' not in src, (
        "channels.js: scoreboard is still in the skip list — the user "
        "wants clicking the card to switch the device to the scoreboard "
        "channel (0x06), not skip the switch."
    )
    # Ambient must remain skipped — now alongside Text (Round 7), since each
    # has its own Apply/Push button rather than a channel switch.
    assert ('activeChannel === "ambient"' in src
            or '["ambient", "text"].includes' in src), (
        "channels.js: ambient must remain in the skip list (it has its own Apply button)."
    )


def test_scoreboard_handler_in_channels_js():
    """channels.js must wire the number inputs' `change` event to call
    set_scoreboard(1, red, blue)."""
    src = CHANNELS_JS.read_text()
    assert "scoreboard-red" in src, "channels.js doesn't reference scoreboard-red"
    assert "scoreboard-blue" in src, "channels.js doesn't reference scoreboard-blue"
    # The change handler must exist and call set_scoreboard.
    assert re.search(
        r"addEventListener\s*\(\s*[\"']change[\"']\s*,\s*pushScoreboard",
        src,
    ), "channels.js: scoreboard number inputs must listen to 'change' and call pushScoreboard."
    # Show/Hide handlers must be gone.
    assert "scoreboard-show-btn" not in src, (
        "channels.js still references scoreboard-show-btn — the Show button was removed."
    )
    assert "scoreboard-hide-btn" not in src, (
        "channels.js still references scoreboard-hide-btn — the Hide button was removed."
    )
    # set_scoreboard is still called (just from the change handler now).
    assert "set_scoreboard" in src, (
        "channels.js doesn't call window.pywebview.api.set_scoreboard — "
        "the change handler must push the score values to the device."
    )


def test_gui_api_exposes_set_scoreboard():
    """gui_api.py must have set_scoreboard(on_off, red=0, blue=0) -> bool."""
    src = GUI_API_PY.read_text()
    assert re.search(
        r"def\s+set_scoreboard\s*\(\s*self\s*,\s*on_off:\s*int\s*,\s*red:\s*int\s*=\s*0\s*,\s*blue:\s*int\s*=\s*0\s*\)",
        src,
    ), "gui_api.py is missing set_scoreboard(self, on_off: int, red: int = 0, blue: int = 0) method."


# ──────────────────────────────────────────────────────────────────
# 5. Battery badge — DOCUMENTED GAP (intentionally not implemented)
# ──────────────────────────────────────────────────────────────────


def test_no_battery_badge_intentionally_not_implemented():
    """The user requested a battery badge in the appbar (planning
    doc §6.1 Phase 1). We intentionally did NOT implement it because
    divoom_lib has no device-battery protocol command — the only
    related commands are 0xB2/0xB3 (low-power auto-dim, not battery
    level). This test guards against someone adding a fake
    battery badge (e.g. showing the laptop's battery) without
    first finding a real device-battery command.

    If you want a device-battery indicator, you need to:
    1. Find a protocol command (possibly in Divoom Cloud over HTTPS).
    2. Implement it in divoom_lib.
    3. Add a GUI badge in index.html + handler in app.js.
    4. Add a get_battery() method in gui_api.py.
    5. Update this test to assert the new badge exists.
    """
    html = INDEX_HTML.read_text()
    assert "battery" not in html.lower(), (
        "Found 'battery' in index.html. The Round 6 plan called for a "
        "battery badge, but divoom_lib has no device-battery protocol "
        "command. Do not add a battery badge without first finding a "
        "real source for the device's battery level."
    )
    appjs = APP_JS.read_text()
    assert "battery" not in appjs.lower(), (
        "Found 'battery' in app.js. See comment in "
        "test_no_battery_badge_intentionally_not_implemented."
    )
    api = GUI_API_PY.read_text()
    assert "get_battery" not in api, (
        "Found 'get_battery' in gui_api.py. See comment in "
        "test_no_battery_badge_intentionally_not_implemented."
    )


# ──────────────────────────────────────────────────────────────────
# 5b. Round 9 — Display card (orientation / mirror / factory reset)
# ──────────────────────────────────────────────────────────────────


def test_r9_display_card_exists():
    """The Display card (orientation/mirror/factory-reset) exists — it now lives
    in Settings → Devices (moved there in R12 Phase 7). R15 §4: factory reset
    moved to its own Danger zone card."""
    src = TEMPLATES_JS.read_text()
    assert 'id="screen-dir-select"' in src, "Display card missing orientation <select>."
    assert 'id="screen-mirror-toggle"' in src, "Display card missing mirror toggle."
    # R15 §4: factory reset moved out of the Display card into its own
    # Danger zone card — both must still be present, just not nested.
    assert 'id="factory-reset-btn"' in src, "factory-reset-btn is missing from the DOM."
    # The Danger zone card exists with a red border treatment.
    assert re.search(
        r'<div class="card glass-card danger-card">[\s\S]*?id="factory-reset-btn"[\s\S]*?</div>',
        src,
    ), "factory-reset-btn is not inside the new Danger zone card."


def test_r9_settings_js_wires_display_and_guards_reset():
    """settings.js wires orientation/mirror and double-confirms factory reset."""
    src = SETTINGS_JS.read_text()
    assert "set_screen_dir" in src, "settings.js does not call set_screen_dir."
    assert "set_screen_mirror" in src, "settings.js does not call set_screen_mirror."
    # Factory reset must be confirmed (dialog + typed RESET token) before calling.
    assert "factory_reset" in src, "settings.js does not call factory_reset."
    assert 'factory_reset?.("RESET")' in src, (
        "factory_reset must be called with the literal 'RESET' token."
    )
    assert "window.prompt" in src and "RESET" in src, (
        "Factory reset must require a typed RESET confirmation."
    )


def test_r9_gui_api_exposes_display_bridges():
    """gui_api.py has set_screen_dir / set_screen_mirror / token-gated
    factory_reset; brightness stays the existing LAN/multi-target bridge."""
    src = GUI_API_PY.read_text()
    assert re.search(r"def\s+set_screen_dir\s*\(", src), "missing set_screen_dir bridge."
    assert re.search(r"def\s+set_screen_mirror\s*\(", src), "missing set_screen_mirror bridge."
    assert re.search(r"def\s+factory_reset\s*\(", src), "missing factory_reset bridge."
    assert 'str(confirm) != "RESET"' in src, (
        "factory_reset must refuse unless the caller passes the 'RESET' token."
    )


# ──────────────────────────────────────────────────────────────────
# 5c. Round 10 — Notification mirroring (ANCS) card
# ──────────────────────────────────────────────────────────────────


def test_r10_notification_card_in_tools_device():
    """Tools→Device has a Notification card with app select, text, Send."""
    src = TEMPLATES_JS.read_text()
    assert 'id="notif-app-select"' in src, "Notification card missing app <select>."
    assert 'id="notif-text"' in src, "Notification card missing text input."
    assert 'id="notif-send"' in src, "Notification card missing Send button."


def test_r10_settings_js_wires_notification():
    src = SETTINGS_JS.read_text()
    assert "send_notification" in src, "settings.js does not call send_notification."


def test_r10_gui_api_and_lib_expose_notification():
    api = GUI_API_PY.read_text()
    assert re.search(r"def\s+send_notification\s*\(", api), "missing send_notification bridge."
    # range guard present
    assert "1 <= t <= 14" in api, "send_notification must guard app_type 1-14."
    # command id registered
    from pathlib import Path as _P
    cmds = (REPO_ROOT / "divoom_lib" / "models" / "commands.py").read_text()
    assert '"set android ancs": 0x50' in cmds, "0x50 ANCS command not registered."


# ──────────────────────────────────────────────────────────────────
# 5d. Round 11 Phase 2 — quick GUI wins
# ──────────────────────────────────────────────────────────────────

CHANNELS_CSS = REPO_ROOT / "gui" / "web_ui" / "channels.css"


def test_r11_ambient_color_controls_gated_and_no_custom_label():
    """Ambient color controls have an id to gate (3a) and the bare 'Custom'
    label is gone (3b)."""
    html = INDEX_HTML.read_text()
    amb = re.search(r'id="panel-ambient">(.+?)<!-- Round 6 — Scoreboard', html, re.DOTALL)
    assert amb is not None, "ambient panel not found"
    block = amb.group(1)
    assert 'id="ambient-color-controls"' in block, "color controls need an id to gate by mode"
    assert "Custom</span>" not in block, "the 'Custom' label should be removed"
    js = CHANNELS_JS.read_text()
    assert "updateAmbientColorVisibility" in js, "channels.js must gate color controls by mode"


def test_r11_scoreboard_reset_button():
    html = INDEX_HTML.read_text()
    assert 'id="scoreboard-reset-btn"' in html, "scoreboard Reset button missing"
    js = CHANNELS_JS.read_text()
    assert "scoreboard-reset-btn" in js, "Reset button not wired in channels.js"


def test_r11_custom_art_push_is_pinned_footer():
    """The Custom Art panel is a flex column so the Push button stays pinned
    (1a) — mirrors the Monthly Best sticky footer."""
    css = CHANNELS_CSS.read_text()
    assert re.search(r"#panel-design\.active\s*\{[^}]*flex-direction:\s*column", css), (
        "#panel-design.active must be a flex column so the push button pins"
    )
    assert re.search(r"#apply-custom-art-btn\s*\{[^}]*sticky", css), (
        "#apply-custom-art-btn should be a sticky footer"
    )


APPBAR_CSS = REPO_ROOT / "gui" / "web_ui" / "appbar.css"


def test_r11_appbar_phase3():
    """Phase 3: transports in a bottom-right corner (4b), sliders pushed right via
    a leading spacer (4c), unified value font (4a), brightness-mapped thumb (4e),
    and the slider drag-fix (4d)."""
    html = INDEX_HTML.read_text()
    # 4b: transports moved out of the header into a fixed corner element
    assert 'class="appbar-transports corner-transports"' in html
    header = re.search(r'<header class="integrated-appbar.+?</header>', html, re.DOTALL).group(0)
    assert "appbar-transports" not in header, "transports must leave the appbar"
    # 4c: a drag-spacer appears before the brightness blocks (pushes sliders right)
    assert header.index("appbar-drag-spacer") < header.index("appbar-brightness")

    css = APPBAR_CSS.read_text()
    assert "#appbar-volume-value" in css, "4a: volume value must share the value type rule"
    assert ".corner-transports" in css and "position: fixed" in css, "4b corner styles"
    assert "--thumb-color" in css, "4e: brightness thumb tracks value"

    app_js = APP_JS.read_text()
    assert "updateBrightnessThumb" in app_js, "4e: thumb color updated from value"
    assert "stopPropagation" in app_js and "appbar-slider" in app_js, "4d slider drag-fix"


def test_r11_scoreboard_restyle_blue_over_red():
    """Phase 4 (5b): scoreboard is a stacked display with BLUE above RED."""
    html = INDEX_HTML.read_text()
    m = re.search(r'<div class="scoreboard-display">(.+?)</div>\s*<button', html, re.DOTALL)
    assert m is not None, "scoreboard-display wrapper missing"
    block = m.group(1)
    assert block.index("scoreboard-row blue") < block.index("scoreboard-row red"), \
        "BLUE row must come before RED"
    assert 'id="scoreboard-blue"' in block and 'id="scoreboard-red"' in block
    css = CHANNELS_CSS.read_text()
    assert ".scoreboard-score" in css and ".scoreboard-row" in css


def test_r11_wall_toolbar_unified():
    """Phase 5 (item 6): single wall toolbar, icons+labels, editable preset name,
    no 'Canvas'/'Layout & Presets' headings."""
    html = INDEX_HTML.read_text()
    wall = re.search(r'id="display-wall".+?id="arranger-canvas"', html, re.DOTALL).group(0)
    assert "wall-toolbar" in wall
    assert 'id="preset-name-input"' in wall, "editable preset name field missing"
    for ctrl in ('id="add-arranger-screen-btn"', 'id="clear-arranger-btn"',
                 'id="save-preset-btn"', 'id="presets-select"'):
        assert ctrl in wall, f"{ctrl} missing from unified toolbar"
    assert ">Canvas<" not in wall, "'Canvas' heading should be gone"
    assert "Layout &amp; Presets" not in wall, "'Layout & Presets' heading should be gone"
    assert "save-preset-btn" in APP_JS.read_text()


def test_r18_subtabs_have_icons_and_fit_content():
    """R18 a/b: Tools + Settings sub-tab buttons carry a .tab-icon (consistency
    with the channel row), and the pill row sizes to its content rather than the
    full window width."""
    src = TEMPLATES_JS.read_text()
    for did in ("tools-time", "tools-sessions", "settings-devices",
                "settings-divoom", "settings-routines", "settings-connectivity",
                "settings-appearance"):
        m = re.search(rf'data-(?:tools|settings)-tab="{did}"[^>]*>(.*?)</button>', src, re.DOTALL)
        assert m and "tab-icon" in m.group(1), f"{did} tab button is missing a .tab-icon"
    tabs_css = (REPO_ROOT / "gui" / "web_ui" / "tabs.css").read_text()
    assert "fit-content" in tabs_css, ".tabs-row should size to content (item b)"
    settings_css = (REPO_ROOT / "gui" / "web_ui" / "settings.css").read_text()
    assert re.search(r"\.theme-buttons\s*\{[^}]*inline-flex", settings_css), \
        "theme selector should size to content (item b)"


# ──────────────────────────────────────────────────────────────────
# 6. Playwright integration smoke (sanity check, optional)
# ──────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_monthly_best_layout_renders_cleanly():
    """Smoke test: load the real index.html in headless Chromium,
    click the Monthly Best tab, and assert the new layout elements
    exist in the rendered DOM. Behavioral drag test is not possible
    (customize.js is not injected by HTTP serving)."""
    pytest.importorskip("playwright.async_api")
    from playwright.async_api import async_playwright

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        await page.goto(f"file://{INDEX_HTML}")
        await page.wait_for_load_state("domcontentloaded")

        await page.click('[data-tab="monthly-best"]', timeout=2000)
        await page.wait_for_selector("#monthly-best.active", timeout=2000)

        # The right card header should be 'Devices', not 'Sync Targets & Schedule'.
        devices_header = await page.locator("#monthly-best h3:has-text('Devices')").count()
        sync_header = await page.locator(
            "#monthly-best h3:has-text('Sync Targets')"
        ).count()
        assert devices_header == 1, (
            f"Expected exactly 1 'Devices' header in Monthly Best, found {devices_header}"
        )
        assert sync_header == 0, (
            f"Monthly Best still has the old 'Sync Targets & Schedule' header "
            f"({sync_header} found) — should be 'Devices'."
        )

        # The schedule UI must be GONE from Monthly Best.
        assert await page.locator("#hc-save-schedule-btn").count() == 0, (
            "Monthly Best still has the old Save Schedule button — it should "
            "have moved to Settings → Routines."
        )
        assert await page.locator("#hc-enabled").count() == 0, (
            "Monthly Best still has the old 'Enable scheduled sync' checkbox — "
            "it should have moved to Settings → Routines."
        )

        # The appbar volume slider must exist.
        assert await page.locator("#appbar-volume-slider").count() == 1, (
            "appbar-volume-slider not found in the rendered DOM"
        )
        # And the Control Panel must have the Scoreboard tab.
        # (R15 §1+§7: `.channel-card` → `.tab-btn`.)
        await page.click('[data-tab="control-panel"]', timeout=2000)
        await page.wait_for_selector("#control-panel.active", timeout=2000)
        assert await page.locator(
            '.tab-btn[data-channel="scoreboard"]'
        ).count() == 1, "Scoreboard tab-btn not found in Control Panel"

        await browser.close()


# ──────────────────────────────────────────────────────────────────
# 5e. Round 12 §A Phase 7 — tools regroup + unified segmented-pill
# ──────────────────────────────────────────────────────────────────

SETTINGS_CSS = REPO_ROOT / "gui" / "web_ui" / "settings.css"


def test_r12_tools_subtab_uses_sessions_not_tools_inner_collision():
    """R12 §A Phase 7 (tools regroup): the inner Tools sub-tab is renamed
    to 'Sessions' to avoid the parent-tab / sub-tab 'Tools' naming
    collision. Sessions is the device-manual term for the
    multi-timer/noise/sleep bundle."""
    src = TEMPLATES_JS.read_text()
    # The inner sub-tab button is now 'Sessions' with data-tools-tab=tools-sessions.
    # (R15 §1+§7: button class is now `.tab-btn` and has additional `data-tab` /
    # `role` / `aria-selected` attrs — the assertion uses a regex that matches
    # the new shape without locking in attribute order.)
    assert re.search(
        r'<button[^>]*data-tools-tab="tools-sessions"[^>]*>'
        r'(?:\s*<svg.*?</svg>)?\s*Sessions\s*</button>',
        src, re.DOTALL,
    ), "Tools inner sub-tab is not 'Sessions' — it should be renamed to avoid the parent-tab / sub-tab 'Tools' collision."
    # The id of the inner sub-tab content block must match.
    assert 'id="tools-sessions"' in src, (
        "inner sub-tab content id should be 'tools-sessions'."
    )
    # The OLD 'tools-tools' collision id must be GONE.
    assert 'id="tools-tools"' not in src, (
        "id 'tools-tools' is still present — it should be renamed to 'tools-sessions'."
    )
    # The 'Time' sub-tab is still present (alarms + anniversary).
    # (R15 §1+§7: button class is now `.tab-btn` and has additional `data-tab` /
    # `role` / `aria-selected` attrs — the assertion uses a regex that
    # doesn't lock in attribute order.)
    assert re.search(
        r'<button[^>]*data-tools-tab="tools-time"[^>]*>'
        r'(?:\s*<svg.*?</svg>)?\s*Time\s*</button>',
        src, re.DOTALL,
    ), "Tools Time sub-tab is missing — it should contain Alarms + Anniversary."


def test_r15_unified_segmented_pill_css():
    """R15 §1+§7: tab chrome lives in `tabs.css` as the single source of
    truth (`.tabs-row` + `.tab-btn`), shared across Channels / Tools /
    Settings / Theme. `settings.css` keeps the legacy class names as
    aliases so older markup (or external themes) still render."""
    repo_root = Path(__file__).parent.parent
    tabs_css = (repo_root / "gui" / "web_ui" / "tabs.css").read_text()
    settings_css = SETTINGS_CSS.read_text()

    # tabs.css defines the unified `.tabs-row` and `.tab-btn` rules.
    assert re.search(r"\.tabs-row\s*\{", tabs_css), (
        "tabs.css is missing the .tabs-row wrapper rule."
    )
    assert re.search(r"\.tabs-row\s+\.tab-btn\s*\{", tabs_css), (
        "tabs.css is missing the .tabs-row .tab-btn rule."
    )
    assert re.search(r"\.tabs-row\s+\.tab-btn\.active\s*\{", tabs_css), (
        "tabs.css is missing the .tabs-row .tab-btn.active rule."
    )

    # settings.css still aliases the legacy class names so old markup
    # (theme buttons, etc.) keeps rendering — no functional regression.
    assert re.search(
        r"\.settings-tab-btn\s*,\s*\n\s*\.tools-subtab-btn\s*,\s*\n\s*\.theme-mode-btn\s*\{",
        settings_css,
    ), (
        "settings.css should still group the legacy class names "
        "(.settings-tab-btn, .tools-subtab-btn, .theme-mode-btn) so "
        "older markup keeps rendering."
    )
    assert re.search(
        r"\.settings-tab-content\s*,\s*\n\s*\.tools-subtab-content\s*\{",
        settings_css,
    ), (
        "settings.css should group .settings-tab-content and "
        ".tools-subtab-content in a single shared visibility rule."
    )


def test_r12_anniversary_moved_into_time_subtab():
    """The Anniversary/Memorial card lives in the Time sub-tab (not the
    Sessions or Device sub-tab), per the regroup."""
    src = TEMPLATES_JS.read_text()
    # Find the Time sub-tab content block.
    m = re.search(
        r'id="tools-time">(.+?)<!-- R11 item 8: SESSIONS',
        src, re.DOTALL,
    )
    assert m is not None, "Time sub-tab block not found"
    block = m.group(1)
    assert 'id="memorial-save"' in block, (
        "Anniversary/Memorial card (memorial-save button) is missing from the Time sub-tab."
    )
    # Anniversary MUST NOT be in the Sessions sub-tab.
    sm = re.search(
        r'id="tools-sessions">(.+?)</div>\s*</div>\s*</div>',
        src, re.DOTALL,
    )
    if sm:
        assert 'id="memorial-save"' not in sm.group(1), (
            "Anniversary/Memorial is in the Sessions sub-tab — should be in Time."
        )


def test_r12_weather_moved_into_live_widgets():
    """The Weather card now lives in Live Widgets, not in the Tools tab.
    R15 §3: the card uses the 128x128 preview (#weather-device-preview)
    — the old push-weather-btn was removed and replaced with an
    auto-push on card selection."""
    src = TEMPLATES_JS.read_text()
    # Live Widgets template block: between widgets: ` and settings: `.
    lw = re.search(r"widgets:\s*`(.+?)`,\s*\n\s*settings:\s*`", src, re.DOTALL)
    assert lw is not None, "Live Widgets (widgets:) block not found in templates.js"
    lw_block = lw.group(1)
    assert 'id="widget-card-weather"' in lw_block, (
        "Weather card (widget-card-weather) is missing from Live Widgets."
    )
    assert 'id="weather-device-preview"' in lw_block, (
        "Weather preview box (#weather-device-preview) is missing from Live Widgets."
    )
    # The old push-weather-btn is GONE.
    assert 'id="push-weather-btn"' not in lw_block, (
        "Old push-weather-btn is still in Live Widgets — should be removed in R15 §3."
    )
    # Weather MUST NOT still be in the Tools tab.
    tools = re.search(r"tools:\s*`(.+?)`,\s*\n\s*widgets:\s*`", src, re.DOTALL)
    assert tools is not None, "Tools tab block not found in templates.js"
    tools_block = tools.group(1)
    assert 'id="push-weather-btn"' not in tools_block, (
        "Weather card is still in the Tools tab — should have moved to Live Widgets."
    )


def test_r12_device_settings_moved_to_settings_devices():
    """The Device Settings card (24h, °F, low-power, device name, etc.)
    now lives in Settings → Devices, not in the Tools tab."""
    src = TEMPLATES_JS.read_text()
    # Settings → Devices sub-tab block: between id="settings-devices" and the
    # next sub-tab id="settings-divoom" (or end of the Settings block).
    m = re.search(
        r'id="settings-devices">(.+?)<div class="settings-tab-content" id="settings-divoom">',
        src, re.DOTALL,
    )
    assert m is not None, "settings-devices sub-tab block not found"
    block = m.group(1)
    for _id in ["hour24-toggle", "tempf-toggle", "lowpower-toggle", "device-name-input", "sync-time-btn"]:
        assert f'id="{_id}"' in block, (
            f"Device Settings id={_id} not found in Settings → Devices — "
            f"should have moved there in R12."
        )
    # And those ids MUST NOT be in the Tools tab.
    tools = re.search(r"tools:\s*`(.+?)`,\s*\n\s*widgets:\s*`", src, re.DOTALL)
    assert tools is not None
    tools_block = tools.group(1)
    for _id in ["hour24-toggle", "tempf-toggle", "lowpower-toggle", "device-name-input", "sync-time-btn"]:
        assert f'id="{_id}"' not in tools_block, (
            f"Device Settings id={_id} is still in the Tools tab — should be in Settings."
        )
