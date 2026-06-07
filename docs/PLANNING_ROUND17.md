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

_(filled as phases ship)_
