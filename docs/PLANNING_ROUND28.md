# Round 28 — MCP-via-daemon, scan filter, tab layout, device bitmap font

Date: 2026-06-08. Driven by user feedback over several sub-rounds (r1–r3). All
work shipped on `main`; suite **1079 passed / 75 skipped / 0 failed** at close.

## Context

User-reported issues against the running app, in order:

1. `./run_gui.sh` failed with `ModuleNotFoundError: No module named 'webview'`.
2. The MCP card showed a "MAC" the user didn't understand, and a Python traceback
   appeared *in the GUI panel but not the terminal*. "Shouldn't the MCP run from
   the daemon with ip and port?"
3. Device scan listed "very much not divoom devices."
4. Tab chrome: inconsistent spacing/padding across Channels/Tools/Settings.
5. Device-bound text used an anti-aliased TrueType font — unreadable at 16/32px.
   "We must use bitmapped fonts. I believe we have some bundled in the apk?"
6. Follow-ups: giant glass pane in Channels; large gap + horizontal shift in
   Tools/Settings; Settings glass pane wrapping the whole panel.
7. "The font we're sending to the device needs to be half the size it is now."

## Outcome

### r1 — MCP routes through the daemon + Divoom-only scan

- **`webview`**: false alarm — `pywebview 6.2.1` + `pyobjc` are installed for the
  Homebrew `python3.14`; the import chain is clean. Stale state before an install.
- **The "MAC"** is a macOS CoreBluetooth peripheral UUID (Apple hides real MACs).
- **Root cause of the panel traceback**: `cmd_mcp_server` called `_resolve_device()`
  → opened a *second* BLE connection to the device the daemon already owns (R17
  single-owner) → `DeviceConnectionError: ... was not found`. The MCP subprocess
  logs to `~/.config/divoom-control/mcp-server.log`, which the GUI card tails — so
  it showed in the panel, not the terminal.
- **Fix**: `cmd_mcp_server` now builds the tool catalog against a
  `DaemonDeviceProxy` via `ensure_daemon()` — a thin daemon client, no own BLE.
  `--mac` optional; new `--socket/--host/--port/--token` (local or remote daemon).
- **Plumbing move**: `divoom_gui/daemon_bridge.py` → `divoom_daemon/daemon_client.py`
  so `divoom_lib`/MCP can use it without a backwards `lib`→`gui` dependency.
  `daemon_bridge.py` is now a re-export shim (GUI call-sites/tests unchanged).
- `mcp_control.start(mac=None)` + `gui_api.start_mcp_server` no longer require a
  MAC. `get_capabilities` awaits the proxy's `to_dict()`.
- **Scan**: removed the `discover_all_divoom_devices` fallback that returned ALL
  named BLE devices when no Divoom matched. New `is_divoom_name()` +
  `DIVOOM_NAME_KEYWORDS` single source of truth.

### r1 — Tab chrome spacing centralised

- One glass pane per tab area; `[2px] tab-row [2px]` padding, `1px` gap to cards.
- Tokens in `style.css :root`: `--tab-pane-pad-y/-pad-x/-gap` (later `--panel-gap`).

### r2 — Tab layout bug fixes

- **Channels giant pane**: the grid's default `align-content` stretched both auto
  rows → the tab pane ballooned to ~217px. Fixed with `grid-template-rows: auto 1fr`.
- **Tools/Settings 21px gap**: `.tab-content` is `display:flex; gap:20px`, so the
  pane inherited a 20px flex gap. Tokenised as `--panel-gap` and added
  `.tab-content > .tabs-section { margin-bottom: calc(var(--tab-pane-gap) - var(--panel-gap)) }`
  so flex (Tools/Settings) and grid (Channels) both net `--tab-pane-gap` (1px).
- **Horizontal shift**: `.tabs-row` was centered (`margin: 0 auto`) — moved with
  the scrollbar and didn't align with the left-aligned cards. Now left-anchored.
- **Settings pane wrapped everything**: `templates_settings.js` never closed
  `.tabs-section` after the tab row (browser auto-closed at fragment end), nesting
  all 5 content panels inside the glass pane. Added the missing `</div>`.

### Device bitmap font (no anti-aliasing)

- Device text (stock ticker) was drawn with `ImageFont.load_default(size=…)` — an
  anti-aliased TrueType font that turns to grey mush at 16/32/64px.
- **Reverse-engineered the APK font format** from `F2/d.smali`: 32 bytes/glyph
  (16×16 @ 1bpp); glyph for codepoint `cp` at offset `(cp-0x21)*32` for printable
  ASCII; stored rotated 270° CW. (`'A'`=idx32, `'0'`=idx15 — verified by decoding.)
- `scripts/extract_apk_font.py` bakes out the rotation and writes the
  printable-ASCII subset (95 glyphs, 3040 B) to
  `divoom_lib/fonts/divoom_fond16_default_ascii.bin`.
- **New `divoom_lib/fonts/`** (`BitmapFont`, `get_default_font`): proportional,
  pixel-exact rendering (`draw_text`/`render`/metrics), `max_width` drops whole
  glyphs on narrow matrices, unsupported codepoints → `?`. `media_source.py`
  rewired; `ImageFont`/`_tiny_font` removed; `pyproject.toml` ships `fonts/*.bin`.

### r3 — Halve the device font

- Full glyphs (~9–10px) dominate a 16px matrix. Added a half-size variant
  (`divoom_fond16_default_half.bin`, ~5px): each glyph cropped, 2×-downsampled
  with an **OR rule** (a 2×2 block lights if ANY source pixel is lit, preserving
  1px strokes), re-placed in the same 16-cell format so `BitmapFont` reads it
  unchanged. `extract_apk_font.py` emits both. New `get_small_font()`;
  `media_source.py` uses it for all device text.
- **Known tradeoff**: at ~5px a few glyphs collapse to the same shape (e.g.
  `B`/`8`). Fine for numeric tickers/percentages; if letter legibility ever
  matters more, swap in a purpose-built tiny font.

## Files touched (key)

- `divoom_lib/cli.py`, `cli_commands.py` — MCP daemon routing + flags.
- `divoom_daemon/daemon_client.py` (new), `divoom_gui/daemon_bridge.py` (shim).
- `divoom_lib/utils/discovery.py` — `is_divoom_name` + no fallback.
- `divoom_lib/mcp_tools.py` — `get_capabilities` awaits proxy.
- `divoom_gui/mcp_control.py`, `gui_api.py` — MAC optional.
- `divoom_gui/web_ui/{style,style_extra,tabs,sidebar}.css`,
  `templates_settings.js` — tab layout + tokens.
- `divoom_lib/fonts/` (new package + 2 `.bin` assets), `scripts/extract_apk_font.py`.
- `divoom_lib/utils/media_source.py` — bitmap (small) font.
- Tests: `test_daemon_bridge`, `test_mcp_server`, `test_discovery`,
  `test_tabs_chrome`, `test_bitmap_font` (new).

## Commits

`517d9ca0` MCP-via-daemon + scan filter · `6aa8c747` tab spacing tokens ·
`eb9169ea` device bitmap font · `27892d5a` tab layout fixes ·
`fe36661a` halve device font.

## Verification

- Full suite green throughout (1055 → 1079 passed).
- Tab layout verified live in the browser preview (Channels/Tools/Settings:
  pane→card = 1px, zero sub-tab horizontal shift, no giant/ wrapping pane).
- Bitmap font verified crisp (rendered pixels are only bg or fg, never AA grey);
  half font verified ~half the full glyph height.
