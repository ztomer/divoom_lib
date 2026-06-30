# PLANNING — Native Rust Menubar + UI

> **OUTCOME / SUPERSEDED (2026-06-30).** The full-native-egui-UI goal below was
> reversed by the maintainer. Final architecture: **Python pywebview GUI** (the
> desktop UI) + **Rust daemon** (`divoomd`) + **standalone Rust menubar**
> (`native-port/divoom-menubar/`, replacing the pyobjc menubar). The egui crate
> (`native-port/divoom-ui/`) was deleted. The plan below is kept for historical
> context only; current state lives in `docs/SESSION_HANDOFF.md` + `CHANGELOG.md`.

Status: **Phases 0-3 done + Phase 4a (tray) done (2026-06-29)** —
`native-port/divoom-ui/` is feature-complete across all 7 tabs + a native tray
menubar. Remaining: Phase 4b packaging + cutover (user-gated). Goal: replace the Python presentation layer (pywebview GUI + pyobjc
menubar) with native Rust, completing the native port so the shipped app has **no
Python runtime at all**.

This continues the native-daemon work (`native-port/divoomd/`, now at parity with
the Python daemon). The daemon is already the integration seam; this plan ports
the two remaining Python surfaces that sit on top of it.

### Decision log (constraints set by the user, in order)
1. **Full native widgets**, not a hosted webview. (Overrides the original
   webview-host recommendation below — that section is kept for the record but is
   superseded by §2.)
2. **Cross-platform** (macOS / Linux / Windows).
3. **Permissive licensing**: ship MIT now, possibly closed-source commercial
   later, **never pay a license fee**. → rules out Slint (GPL-or-pay).
4. **Toolkit = egui/eframe** (MIT/Apache). The current `web_ui/` is the visual
   reference for layout + look, reproduced in native widgets (not embedded).

---

## 1. What exists today (the surface to replace)

Three processes, all talking to **one daemon** over the NDJSON unix socket
(`/tmp/divoom.sock`). The daemon is the single BLE owner; everything else is a
socket client. **This separation is the key enabler — a Rust UI is just another
socket client; we do not have to touch BLE, cloud, or codec logic.**

### 1a. `divoom_menubar/` — pyobjc menubar (NSStatusItem)  (~648 LOC)
- `menubar.py` (368) — `NSStatusBar`/`NSStatusItem`/`NSMenu`. A `menuNeedsUpdate_`
  delegate rebuilds a **device section** (per-device rows with a thumbnail icon
  rendered from a data-URL), plus fixed items: **Launch Dashboard** (⌘D),
  **Open / Start / Stop Notifications**, **Quit**. Title shows live status
  (color-coded). Launches the GUI via `subprocess.Popen([python, gui_main.py])`.
- `menubar_client.py` (258) — wraps `DaemonClient`; **subscribes** to daemon
  events over the socket on a background thread to drive live status; reconnect
  loop; never blocks the main thread in `menuNeedsUpdate_`.

### 1b. `divoom_gui/` — pywebview dashboard
- **Host**: `gui_main.py` (309) — `webview.create_window(... js_api=api ...)`,
  frameless 1080×768, loads `web_ui/index.html` as a `file://` URL with query
  params. Carries a workaround for pywebview upstream bug #1820 (multi-monitor
  drag). Eagerly spawns the daemon + menubar before `webview.start()`.
- **Bridge**: `gui_api.py` (492) — `DivoomGuiAPI` exposed via `js_api`. ~70
  public methods. **Most are thin forwarders** to `self._client().device_call(...)`
  / daemon RPCs (e.g. `set_brightness`, `set_clock`, `push_weather`, `set_alarm`,
  `device_call`, `start_mcp_server`). Heavier logic lives in **mixins**:
  - `MediaSyncMixin` (`media_sync.py`, 418) — wall-image / custom-art decode +
    push. Much already has a Rust twin in `divoomd` (`media::resolve_to_gif`).
  - `PresetsManagerMixin` (`presets_manager.py`, 446) — local preset CRUD
    (`presets.json`). Pure local state, no device I/O.
  - `ScannerMixin` (`scanner_mixin.py`, 296) — device scan orchestration (daemon
    already owns the actual BLE scan).
  - Plus `gallery_sync.py` (487), `gallery_hot_api.py` (222), `mcp_control.py`
    (227), `control_server.py`, `audio_visualizer.py`, `permissions.py`.
- **Frontend**: `web_ui/` — **9,172 LOC of plain static HTML/CSS/JS**, no
  bundler (just `<script src>` tags + one Google-Fonts CDN link). 36 files:
  tabs (channels, gallery, custom-art, widgets, settings, routines, alarms),
  device selector, channel preview, the glass-tab/appbar styling.

### Architectural takeaway
- The **frontend is portable as-is**: a Rust webview loads the existing `web_ui/`
  directory unchanged. We do **not** rewrite 9,172 LOC of UI.
- The **bridge** is the real work: reimplement ~70 `js_api` methods in Rust.
  ~70% are thin daemon-forwarders (trivial); the residual is the mixin logic,
  most of which already exists in `divoomd` (media/gallery/scan) or is pure local
  state (presets — straight port).
- The **menubar** is a clean, small, self-contained rewrite against AppKit.

---

## 2. The decision: native widgets via egui (SUPERSEDES the webview plan below)

The user requires **full native widgets** (no embedded browser) that are
**cross-platform** and carry **no GPL/royalty obligation** (MIT now, maybe
commercial later, never pay). Toolkit shortlist:

| Toolkit | License | MIT app? | Commercial later? | Fidelity | Verdict |
|---------|---------|----------|-------------------|----------|---------|
| **Slint** | GPLv3 **or** paid **or** non-OSS royalty-free | ✗ | GPL or $ | high | **rejected** (licensing) |
| **iced** | MIT | ✓ | ✓ | high | viable |
| **egui/eframe** | MIT/Apache | ✓ | ✓ | good (theming, not pixel-perfect CSS) | **chosen** |

**Decision: egui/eframe.** Permissive, biggest ecosystem, fastest to a working
cross-platform app, trivial image grids + built-in widgets — and the user picked
it over iced for pragmatism. The Braun dark look is reproduced via a custom egui
theme (the palette is copied byte-for-byte from `web_ui/style.css`). The current
`web_ui/` is the **visual reference**, not a shipped artifact — it is read for
layout/look only and stays archived in-tree.

> The webview approach in §§ below (wry/tao + keep `web_ui/` verbatim) was the
> earlier recommendation. It is **retained for the record but not pursued** — the
> user explicitly chose native widgets. Skip to §4-native for the live plan.

---

## 3. Target architecture (native)

```
┌──────────────────────────────────────────────────┐
│ divoom-ui  (Rust/egui bin, native-port/divoom-ui) │
│  ├─ eframe window (frameless, custom appbar)       │
│  │    ├─ shell.rs  appbar + sidebar + content      │
│  │    └─ theme.rs  Braun dark tokens (from CSS)    │
│  └─ daemon.rs  socket client on a worker thread ─┐ │
└──────────────────────────────────────────────────┼┘
                       NDJSON socket (DIVOOM_SOCKET) │
                       /tmp/divoom.sock              │
                ┌──────▼───────┐                      
                │  divoomd     │  single BLE owner (already native)
                └──────────────┘
```

- **Daemon stays a separate process** (sole BLE owner; a UI crash never drops the
  device). UI is a pure client; all socket I/O is on a background worker thread
  (`daemon.rs`) that talks to the UI over `mpsc` channels — the egui frame loop
  never blocks on a socket.
- **Protocol reuse, not code reuse (for now):** the wire format is trivial
  (`{"command","args"}` + `\n`), so `daemon.rs` speaks it directly rather than
  depending on the heavy `divoomd` lib (which pulls reqwest/rusqlite/btleplug).
  A `divoom-core` extraction can come later if duplication grows.
- **Cross-platform connection:** unix socket on macOS/Linux today; the daemon's
  TCP+token transport (R54) covers Windows — only `ConnConnect::open()` changes.

---

## 4-native. Phased plan (egui)

Each phase ends compiling + verifiable; the Python UI stays default until cutover.

### Phase 0 — Scaffold + shell + theme  ✓ DONE (2026-06-29)
- Crate `native-port/divoom-ui/` (eframe/egui 0.29). `theme.rs` mirrors the
  `web_ui` `:root` palette (Braun dark, `#ff5a1f` accent, 168px sidebar).
- `shell.rs` renders the app shell: frameless integrated **appbar** (window
  controls + brightness/volume sliders + Settings pill, window-drag), **sidebar**
  (6 nav tabs with active orange accent bar + device panel pinned bottom),
  **content** host with the Channels sub-tab row.
- `daemon.rs` worker thread + the live-status/scan/device_call wiring.
- **Verified**: compiles clean; renders faithfully to the reference (self-grabbed
  framebuffer screenshot — egui `ViewportCommand::Screenshot`, no OS screen-record
  permission needed, gated by `DIVOOM_UI_SCREENSHOT`); "daemon ready" shows live
  against a no-BLE `divoomd` on `DIVOOM_SOCKET`.

### Phase 1 — Daemon client hardening + live wiring  ✓ DONE (2026-06-29)
- NDJSON request/reply, reconnect-once, status poll, get_status / scan / connect /
  device_call(set_brightness, music.set_volume).
- **`subscribe` event thread** (status push + auto-reconnect); **`divoomd`
  auto-spawn** when the socket is absent (`DIVOOMD_BIN`/sibling-of-exe/PATH +
  poll-connect).
- Deferred: Windows TCP transport (folded into Phase 4 packaging).

### Phase 2 — Channels tab (control-panel)  ✓ DONE (2026-06-29)
- `channels.rs`: per-channel panels reproduced from `web_ui`/`channels_grids.js`,
  wired to the device_call leaf the Python facades use (positional args, verified
  vs the Rust dispatch): clock face → `display.show_clock`; visualizer (12 EQ) →
  `display.show_visualization`; VJ (16) → `display.show_effects`; ambient (5 modes
  + color/swatches) → `display.show_light`; scoreboard → `set_scoreboard`.
- Deferred to Phase 3: **Text push** (needs the bitmap-font→image render from
  `LightingApi._render_text_png`), **Sessions** (Sleep Aid), and clock color
  (`set_clock_rich` richness — `show_clock` is white-only on device).

### Phase 3 — Remaining tabs (in progress)
- **Device Settings ✓ DONE (3a)** — `device_settings.rs`, all controls wired to
  device_call leaves; `sync_time` flagged as a daemon gap (port `DateTimeCommand`).
- Remaining: Settings (app-level RPCs via `Cmd::Raw`), Schedule (alarms week-table),
  Live Widgets (gallery image grids — egui texture loading), Pixel Art editor,
  Virtual Wall, + Channels Text push / Sessions.
- Local state (presets) ported straight; media/gallery/scan forward to `divoomd`.

### Phase 4 — Native tray/menubar + packaging + cutover
- **4a ✓ DONE** — `tray.rs`: cross-platform tray via **`tray-icon`** mirroring
  `divoom_menubar` (Show Dashboard / Start-Stop Notifications / Quit; label tracks
  live state). Built lazily on first frame; events polled from the eframe loop;
  same-process (Show Dashboard focuses the window). Device-section thumbnails +
  color-coded status are a later polish (objc2-app-kit if needed).
- **4b — REMAINING, USER-GATED:** package per-OS (macOS `.app` with a real
  `Info.plist` — BT strings + tray-mode `LSUIElement`; the daemon's `-sectcreate`
  hack is unneeded for a real app). Bundle `divoomd` + encoder dylib. Update build
  scripts + Homebrew cask. **Then cutover:** flip the default launcher to
  `divoom-ui`; archive the Python UI in-tree (**never deleted**). Cutover changes
  what ships and needs the macOS BT grant (physical click) + user review → not done
  autonomously.

---

## 5. Cross-platform / hardware verification (per phase)
- macOS: BT grant prompt attributed to the native `.app` (the daemon's TCC
  problem disappears — a real bundled app is its own responsible process).
- Verify on the physical devices (Pixoo / Tivoo-Max / Timoo) — same matrix used
  for the daemon parity sign-off.
- Verify on the physical devices (Pixoo / Tivoo-Max / Timoo) — same matrix used
  for the daemon parity sign-off; the UI drives `device_call` over the socket.
- Linux: `tray-icon` uses GTK/AppIndicator; eframe uses winit+glow (x11/wayland).
  Validate on the headless box's GUI path or document best-effort (BLE *connect* is
  already a known BlueZ limitation; scan works).
- Windows: switch the socket client to the daemon's TCP+token transport.

---

## 6. Risks & open questions

- **Fidelity ceiling**: egui is immediate-mode — the result reads as a faithful
  reproduction of the Braun look (palette is exact), not pixel-identical CSS
  (glass blur, font rendering, sub-pixel spacing differ). Accepted by the user in
  choosing egui over iced/Slint.
- **Custom fonts**: the web UI uses Outfit/Inter (CDN). egui ships its own default
  proportional font; bundling Inter/Outfit TTFs is a small later polish, not a
  blocker.
- **Tray thumbnails**: per-device status icons in the tray may need
  `objc2-app-kit` on macOS if `tray-icon`'s image API is too coarse — confirm in
  Phase 4.
- **Frameless window chrome**: custom appbar drag/resize via
  `ViewportCommand::StartDrag` works on macOS; re-verify resize affordances on
  Linux/Windows in Phase 4.
- **`divoom-core` extraction**: if the client/codec duplication between `divoomd`
  and `divoom-ui` grows, factor a shared lib crate; for now the UI duplicates the
  tiny NDJSON client to avoid pulling `divoomd`'s heavy deps.

## 7. Status / next action

- **Phase 0 done**: shell + theme + live daemon wiring, verified by self-grabbed
  screenshot. Next: **Phase 1 remainder** — event subscription (push updates),
  `divoomd` auto-spawn, then **Phase 2** (Channels panels).

> Parked dependency: the v0.21.0 release (daemon BLE bundle) is still waiting on a
> one-time user BT-grant click. This UI work is independent of that and can
> proceed in parallel.
