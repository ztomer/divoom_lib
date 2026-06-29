# PLANNING — Native Rust Menubar + UI

Status: **planning** (no code yet). Goal: replace the Python presentation layer
(pywebview GUI + pyobjc menubar) with native Rust, completing the native port so
the shipped app has **no Python runtime at all**.

This continues the native-daemon work (`native-port/divoomd/`, now at parity with
the Python daemon). The daemon is already the integration seam; this plan ports
the two remaining Python surfaces that sit on top of it.

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

## 2. The decision: webview-host vs. native-widgets

| Approach | GUI effort | Risk | Loses |
|----------|-----------|------|-------|
| **A. Rust-hosted webview** (keep `web_ui/` verbatim, reimplement bridge in Rust) | reimplement ~70 bridge methods | **low** | nothing — pixel-identical UI |
| B. Native widgets (egui / slint / cacao) | rewrite all 9,172 LOC of UI | **high** | every CSS detail (glass tabs, appbar, animations), months of polish |

**Decision: Approach A.** Rewriting the UI in native widgets throws away the
single largest investment in the repo for no user-visible gain and high risk.
Keeping the proven web frontend and replacing only its Python host is the
parity-preserving move (consistent with the port-parity rule: the original
`web_ui/` *is* the executable spec for the UI).

### Stack (à la carte Tauri ecosystem, no Node build step)
The frontend is static files with no bundler, so we use the webview crates
directly rather than full Tauri (which assumes a JS build pipeline):

- **`wry`** — the webview (WKWebView on macOS; same engine pywebview uses). Loads
  `web_ui/` via a custom protocol handler; `with_ipc_handler` for JS→Rust;
  `evaluate_script` for Rust→JS. This is exactly the pywebview `js_api` shape.
- **`tao`** — windowing (frameless, sizing, multi-monitor — and tao handles the
  multi-monitor drag correctly, so pywebview bug #1820's workaround is dropped).
- **`tray-icon`** — the menubar `NSStatusItem` (cross-platform tray API).
- **`muda`** — native menus for the tray (and a future app menu).
- macOS specifics via **`objc2` + `objc2-app-kit`** where a crate's API is too
  thin (e.g. rendering the device-thumbnail icon into the status item).

All four (`wry`/`tao`/`tray-icon`/`muda`) are maintained by the Tauri team and
designed to compose. Single Rust binary, no Python, no Node.

> Full **Tauri 2.x** is the fallback if we later want auto-update, packaging, and
> a plugin ecosystem — but it's heavier and wants a JS toolchain. Start
> à la carte; promote to Tauri only if those features justify it.

---

## 3. Target architecture

```
┌─────────────────────────────────────────────┐
│ divoom-ui  (new Rust binary, native-port/)   │
│  ├─ tao window  → wry webview → web_ui/ (*)   │   (*) existing assets, unchanged
│  │     └─ ipc_handler → bridge::dispatch()    │
│  ├─ tray-icon + muda  → menubar               │
│  └─ socket client ──────────┐                 │
└─────────────────────────────┼─────────────────┘
                              │ NDJSON unix socket (unchanged protocol)
                       ┌──────▼───────┐
                       │  divoomd     │  single BLE owner (already native)
                       └──────────────┘
```

- **Keep the daemon as a separate process** (matches today; daemon stays the sole
  BLE owner; UI crash never drops the device connection). The UI binary spawns
  `divoomd` if absent — reusing the bundled-resolution logic already in
  `daemon_client.py`, reimplemented in Rust.
- The bridge `dispatch(method, args) -> json` is a Rust match over the ~70 method
  names, each forwarding to a shared `DaemonClient` (Rust) or handling local
  state (presets, file dialogs via `rfd`).
- Reuse `divoomd`'s existing modules in-crate where possible (media decode,
  gallery) by factoring shared code into a `divoom-core` lib crate rather than
  duplicating.

---

## 4. Phased plan

Each phase ends green (tests pass) and shippable (the Python UI remains the
default until Phase 6 flips it), so we never have a broken `main`.

### Phase 0 — Spike & validate (½–1 day)
- New crate `native-port/divoom-ui/` (bin). Add `wry`, `tao`, `tray-icon`, `muda`.
- Get a frameless `tao` window hosting `wry` that loads the **existing**
  `web_ui/index.html` via a custom protocol, with one round-trip IPC method
  (`get_transport_status`) forwarding to a real `divoomd`.
- Get a `tray-icon` status item with a static title + Quit.
- **Exit criteria**: the real dashboard renders pixel-identical in wry, and one
  live device call works end-to-end. Proves Approach A before committing.

### Phase 1 — Rust `DaemonClient` + bridge skeleton
- Port `DaemonClient` (NDJSON framing, RPC, event subscribe, reconnect) to Rust —
  or expose `divoomd`'s existing client internals via the `divoom-core` lib crate.
- Bridge dispatcher with the ~45 **thin forwarder** methods (device_call,
  brightness/volume, clock, weather, alarms, channels, timers, MCP control…).
- **Test**: a headless harness drives `dispatch()` against a `MockTransport`
  daemon (reuse the existing mock) and asserts wire bytes — same parity bar we
  held for the daemon.

### Phase 2 — Menubar parity
- Rebuild the menu structure in `muda`: dynamic device section (with thumbnail
  icons via `objc2-app-kit`), Launch Dashboard, Notifications start/stop/open,
  Quit. Color-coded live status from the event subscription.
- Reconcile with the GUI window: "Launch Dashboard" shows the wry window instead
  of spawning a subprocess (same process now). Single-instance behavior.
- **Test**: status-derivation logic (`derive_state`/`format_status_title`) ported
  with unit tests mirroring the Python ones.

### Phase 3 — The mixin logic (the residual)
- **Presets** (`presets_manager.py`) → straight Rust port (local JSON CRUD, no
  device I/O). Highest-value/lowest-risk.
- **Media sync / custom art** → wire bridge methods to `divoomd`'s existing
  `media::resolve_to_gif` + push path (already at parity; don't re-port).
- **Scanner** → forward to the daemon's scan RPC (daemon already owns it).
- **Gallery / hot-channel** → forward to daemon endpoints already ported.
- File dialogs (`open_file_dialog`) → `rfd` crate.
- **Compare to Python at each method** (port-parity rule): the `gui_api` method
  body is the spec for args/return shape the JS expects — match it exactly so the
  unchanged frontend keeps working.

### Phase 4 — Packaging
- Build `divoom-ui` as a proper `.app` (replaces py2app). Embed the real
  `Info.plist` (BT usage strings, `LSUIElement` per menubar/window mode) — native,
  not the `-sectcreate` helper-binary hack the daemon needed.
- Bundle `divoomd` + `web_ui/` + the encoder dylib as app Resources.
- Codesign; rebuild the `.dmg`; update the Homebrew cask. New
  `scripts/build_release_native.sh` alongside (not replacing) the Python one until
  the cutover.
- **The whole bundle is now Python-free.**

### Phase 5 — Hardware + cross-platform verification
- macOS: BT grant prompt attributed to the native `.app` (the daemon's TCC
  problem disappears — a real bundled app is its own responsible process).
- Verify on the physical devices (Pixoo / Tivoo-Max / Timoo) — same matrix used
  for the daemon parity sign-off.
- Linux: `tray-icon`/`wry` use GTK; validate on the headless box's GUI path or
  document as best-effort (BLE connect is already a known BlueZ limitation).

### Phase 6 — Cutover
- Flip the default launcher to `divoom-ui`. Keep the Python GUI/menubar **archived
  in-tree** as the reference implementation (per standing rule — never delete).
- Update `setup_app.py`/docs to mark the Python UI legacy; remove it from the
  shipped bundle (but keep in the repo).

---

## 5. Risks & open questions

- **wry IPC ergonomics vs. pywebview `js_api`**: pywebview auto-exposes Python
  methods as `pywebview.api.foo(...)` returning promises. wry's `ipc_handler` is a
  single string channel — we need a tiny JS shim that marshals
  `{id, method, args}` and resolves promises by id. **The frontend calls
  `pywebview.api.*` in ~dozens of places** → either (a) inject a shim that
  defines `window.pywebview.api` with the same method names (preferred — zero
  frontend edits), or (b) edit call sites (rejected — breaks "frontend unchanged").
  Phase 0 must prove the shim.
- **Async bridge**: many methods are blocking socket RPCs; run them off the UI
  thread and resolve the JS promise on completion (the shim handles this).
- **Thumbnail rendering** in the status item needs `objc2-app-kit` (tray-icon's
  API may be too coarse for per-row data-URL icons) — confirm in Phase 2.
- **Linux/GTK** parity for wry is lower-fidelity than WKWebView; acceptable since
  macOS is the primary target.
- **`divoom-core` extraction**: factoring shared daemon/UI code is the clean path
  but adds a refactor; if it balloons, the UI can just be a socket client and
  duplicate the small client code.

## 6. Effort estimate (rough)

| Phase | Estimate |
|-------|----------|
| 0 spike | 0.5–1 d |
| 1 client + thin bridge | 1–2 d |
| 2 menubar | 1–2 d |
| 3 mixin residual | 2–3 d |
| 4 packaging | 1 d |
| 5 hardware/x-plat | 1 d + device access |
| 6 cutover | 0.5 d |

The bulk of "UI work" is **avoided** by keeping `web_ui/`. The real cost is the
bridge (Phases 1+3) and packaging.

---

## 7. First action when work starts

Phase 0 spike, gated on the **pywebview-API shim** proving out — if the unchanged
frontend can't talk to a wry IPC handler via a `window.pywebview.api` shim, the
"keep the frontend verbatim" premise fails and we revisit. Everything else is
low-risk forwarding.

> Parked dependency: the v0.21.0 release (daemon BLE bundle) is still waiting on a
> one-time user BT-grant click. This UI work is independent of that and can
> proceed in parallel.
