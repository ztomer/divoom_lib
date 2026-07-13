# Round 17 — 3-way split: divoom_lib / divoom_daemon / divoom_gui

> **Input (user):** "We probably want the project split 3-way — library, daemon,
> gui. Today we have library and gui." Decisions: **(1) the daemon absorbs ALL
> background device work** (notifications + live widgets/media-sync + gallery/
> monthly-best); **(2) physical split first**, then migrate behavior; **(3) three
> top-level packages.**

Supersedes R16 P3/P4 (menubar + GUI become daemon clients) — that behavior
migration happens after the physical split here.

## Target structure

```
divoom_lib/      pure protocol + encoders + CLI + MCP + weather + capabilities
                 (no host/OS/GUI deps)   ← includes the native dylib (its true home)
divoom_daemon/   headless, always-on: device connection, macOS notification
                 monitor + routing, live widgets (media-sync), gallery +
                 monthly-best sync, the Unix-socket event server, the menubar agent
divoom_gui/      pywebview frontend + a THIN bridge that is a daemon client + web_ui
```

### Module allocation (from today's `gui/`)
- **→ divoom_daemon/**: `daemon.py`, `daemon_protocol.py`, `macos_notifications.py`,
  `media_sync.py`, `gallery_sync.py`, `media_decoder.py`, `scanner_mixin.py`,
  `control_server.py`, `mcp_control.py`, `menubar.py`, `menubar_status.py`
- **→ divoom_gui/**: `gui_main.py`, `gui_api.py` (slimmed to a daemon client),
  `presets_manager.py`, `web_ui/`
- **→ divoom_lib/**: `libdivoom_compact.dylib` + `compact.c` (library artifact;
  fixes the cross-component path coupling)

## Hazards (measured)
- **10 test files** hard-code `…/ "gui"` on `sys.path` + `from gui.* import`.
- **9 references** to `gui/libdivoom_compact.dylib` (`framing.py`,
  `native/image_encoder.py`, `scripts/build_libdivoom.sh`, `conftest.py`,
  `pyproject.toml`). Renaming `gui/` breaks these — so the **dylib must move to
  `divoom_lib/`** and all 9 refs updated, as a discrete sub-step.
- `pyproject.toml` ships the `gui` package + `web_ui/` + dylib → must be rewritten
  for three packages (`divoom_lib`, `divoom_daemon`, `divoom_gui`; darwin extras).
- The god-object `gui_api.py` (935 lines) mixes presentation with background work
  via `MediaSyncMixin`/`ScannerMixin` — those mixins can't simply move to the
  daemon while `gui_api` inherits them. The **physical move of the mixins is
  coupled to the behavior migration** (gui_api becomes a client). So: move the
  cleanly-separable modules physically first; move the mixins WITH their behavior
  migration.

## Dependency-safe, incremental phases (each: tests green + commit)

1. **Establish `divoom_daemon/`** + move the self-contained daemon core
   (`daemon.py`, `daemon_protocol.py`). Fix `cli.py` + 2 daemon tests. (Smallest;
   proves the top-level-package pattern.)
2. **Move `macos_notifications.py` + `menubar*.py`** into `divoom_daemon/`. Fix
   `gui_api.py` import + the macos/menubar tests. (`menubar_status` is standalone;
   `menubar` is macOS-only.)
3. **Move the dylib + `compact.c` to `divoom_lib/`**; update the 9 refs + build
   script + conftest auto-rebuild + pyproject package-data.
4. **Rename `gui/` → `divoom_gui/`**; move `gui_main.py`/`gui_api.py`/
   `presets_manager.py`/`web_ui/`. Fix the 10 test path-hacks (prefer real package
   imports over `sys.path` insertion). Update pyproject + the menubar/gui launch
   paths.
5. **Behavior migration (was R16 P3/P4 + the widgets):** move `media_sync` /
   `gallery_sync` / `scanner_mixin` into the daemon; `gui_api` + `menubar` become
   `DaemonClient`s (subscribe for events, send intents). **Removes R15 §6's
   `gui_api._push_menubar_status`.** This is the largest phase.
6. **pyproject 3-package finalize + entry points** (`divoom-control`,
   `divoom-control daemon`, the GUI launcher). Verify `pip install -e .`.
7. **Close:** handoff + CHANGELOG + push.

### Shim strategy
During phases 1-4, where a moved module still has stragglers, leave a 1-line
re-export shim at the old path (`from divoom_daemon.X import *`) so unported
importers keep working; delete the shim once all importers are updated. Avoids a
big-bang break across 959 tests.

## Note on R16
R16 P1+P2 shipped the daemon (protocol + server). Its files relocate in Phase 1
here. R16 P3/P4/P5 are folded into Phase 5/7 of this round.

## §outcome

- **P1 SHIPPED** (`refactor(R17-P1)`): created `divoom_daemon/` package; moved
  `daemon.py` + `daemon_protocol.py` out of `gui/`; fixed `cli.py` + 2 tests.
- **P2 SHIPPED** (`refactor(R17-P2)`): moved `macos_notifications.py` +
  `menubar.py` + `menubar_status.py` into `divoom_daemon/`; repathed every
  importer consistently (no shim — `@patch` needs one module path); fixed the
  menubar's `gui_main` launch path.
- **P3 SHIPPED** (`refactor(R17-P3)`): moved the native dylib + `compact.c` into
  `divoom_lib/` (its true home); fixed all 9+ refs (framing, image_encoder,
  downscaler, build script, conftest, pyproject + its test); rebuilt + verified.
  (Also swept in 9 pre-existing `verify_*.py` root→`scripts/` pure renames.)
- Suite after each: **959 passed / 0 failed / 75 skipped.**
- **P4 SHIPPED** (`refactor(R17-P4)`): renamed `gui/` → `divoom_gui/` (+ __init__).
  Repathed every reference (19 test path-hacks, `from gui.` imports, menubar's
  launch path, scripts, pyproject). Browser-verified via the Playwright DOM tests
  (which load `divoom_gui/web_ui/index.html`). Suite 963 / 0.
- **P6 SHIPPED** (folded in): pyproject now finds all three packages
  (`divoom_lib`/`divoom_daemon`/`divoom_gui`), ships the dylib with divoom_lib +
  web_ui with divoom_gui; `divoom-control` + `divoom-control daemon` entry points
  verified; all three packages import.
- **P5 — SHIPPED (full cutover; user chose "do the full flip now").** The GUI
  no longer holds a BLE connection anywhere; the daemon is the sole owner.
  - `feat(R17-P5): daemon owns connect/scan/wall/LAN — full-cutover protocol`:
    enriched `connect` (BLE+LAN+auto), `device_status` {connected,mac,lan_ip,wall},
    `scan`, `wall_configure` + `device_call target="wall"`, `probe_lan`,
    idempotent wall; matching `DaemonClient` methods.
  - `feat(R17-P5): full GUI cutover — daemon is the sole BLE owner`:
    * scanner_mixin → thin client (scan/connect(BLE+LAN)/wall-build via daemon;
      `current_divoom`/`wall_instance` are `DaemonDeviceProxy` handles).
    * gui_api → `_client()`/`ensure_daemon` (auto-spawn) + `_device_status()`;
      transport-status / save_lan_config / probe_lan read daemon state, not
      device internals; wall branches call single wall methods via the
      target="wall" proxy (no `wall_instance.devices` iteration in the GUI).
    * gallery `batch_sync_artwork` → daemon `sync_artwork` (download+decode+
      resize+stream run daemon-side; binary never crosses the socket).
    * `DaemonDeviceProxy` carries a target + answers `is_connected`/`lan`/`_conn`
      from `device_status` so introspection call-sites work unchanged.
    * `DivoomWall` gained `switch_channel`/`push_text`/`set_brightness`/
      `set_volume`; `media_decoder` moved divoom_gui→divoom_lib (shared util).
  - Tests: rewrote the 5 gui_api tests that mocked direct BLE → daemon-client
    model; +4 daemon, +8 bridge, +2 wall tests. **Suite 980 / 0 / 75.**
  - **media_sync (live widgets/cover-art) needs NO rewrite** — it drives the
    device only through `current_divoom`/`wall_instance` (now proxies) with
    path-based `show_image`, so it routes through the daemon automatically.
  - **Remaining (post-cutover, needs the live app + hardware):**
    1. **Runtime verification** — drive the real pywebview GUI against a live
       daemon + a real device for every channel/tool/wall/gallery path. None of
       the cutover is hardware-verified; it is unit-green only.
    2. **Menubar still uses `gui_api._push_menubar_status`** (R15 §6) to push
       notification status to the menubar's own socket. The daemon already owns
       the notification monitor + broadcasts status events; the menubar should
       *subscribe* to the daemon instead, and `_push_menubar_status` be removed.
       Left working rather than ripped out blind.
    3. **save_lan_config** no longer hot-attaches LAN to a live device; the saved
       config applies on the next `connect_device(lan_ip=...)`. Verify acceptable.

- (superseded) **P5 — mechanism only (pre-flip notes):**
  - **Daemon side SHIPPED** (`feat(R17-P5): daemon device_call RPC`): generic
    `device_call` ({method,args,kwargs} → dotted-method dispatch on the daemon's
    owned `Divoom`, awaited, JSON-coerced), `connect`/`disconnect`/`device_status`,
    a dedicated device asyncio loop that survives across calls. +4 tests.
  - **GUI client side SHIPPED** (`feat(R17-P5): GUI daemon bridge`): `ensure_daemon()`
    auto-spawns a detached daemon if none is live; `DaemonDeviceProxy` makes
    `proxy.display.show_light(...)` issue a `device_call` so the existing
    `_run_async(target.X.Y(...))` call-sites work unchanged once `target` is a
    proxy. +8 tests. Suite 975/0/75.
  - **BLOCKER discovered — the cutover cannot be partial.** Because BLE is
    single-owner, if the GUI flips its *single-device* path to the daemon but
    keeps owning the device anywhere else, the two processes contend for the
    connection — worse than today. Two gui_api subsystems still own BLE directly
    and have no daemon equivalent yet:
      1. **Wall / multi-device** (`wall_instance` = a `DivoomWall` holding several
         live `Divoom` connections; `_rebuild_wall_instance()` + iteration over
         `wall_instance.devices`). Needs the daemon to own a wall composition +
         a multi-device call protocol — a real protocol extension, not a flip.
      2. **Scanning + connect** (`scanner_mixin` constructs `Divoom(...).connect()`
         and sets `current_divoom`) — must become `client.connect(mac)` + a
         daemon-owned scan RPC.
      3. **LAN/status internals** (`current_divoom._conn.mac`, `.lan.device_ip`,
         `._lan =` in transport-status / lan-config) — must be served by
         `device_status` fields, not device attribute reads.
  - **Therefore the full flip = daemon also owns wall+scan+LAN, plus runtime
    verification against the live pywebview app + real hardware** (which can't be
    unit-tested). Scoping decision surfaced to the user.

- (superseded) **P5 — the behavior migration — NOT started.** This was the actual behavioural
  daemonisation and the one remaining large piece. **Key constraint:** the BLE
  device connection can only be held by ONE process, so the daemon and the GUI
  cannot both own the device. The correct model is **daemon = single device
  owner; GUI = thin RPC client.** Concretely: a generic `device_call` RPC on the
  daemon (`{method, args}` executed on its owned `Divoom`), and `gui_api` device
  methods become thin proxies through `DaemonClient` (no direct BLE in the GUI);
  scanning/connection/wall/LAN ownership moves to the daemon; menubar + GUI
  subscribe for status; remove R15 §6's `gui_api._push_menubar_status`. Large,
  high-risk rewrite of the 935-line `gui_api` — do it as its own careful, tested
  program, not rushed.
