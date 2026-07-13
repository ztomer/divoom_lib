# Round 20 — Linux compatibility (daemon + libraries)

> **Input (user):** "We also want the daemon and libraries to be linux
> compatible."

Scope: `divoom_lib` + `divoom_daemon` run on Linux. BLE works via bleak/BlueZ;
the R19 network server + device control are already platform-neutral. The GUI
(pywebview) is out of scope here — this is the headless/library path.

## Findings (the import chain was already mostly clean)
- Only `divoom_daemon/menubar.py` (the macOS menu-bar agent — **not** in the
  daemon import path) has top-level PyObjC imports. `import divoom_daemon.daemon`
  is clean on Linux.
- `bt_spp_transport.py` imports Foundation only inside `sys.platform=="darwin"`
  guards; `connection.py` defaults to bleak BLE.
- `macos_notifications.find_notification_db_path()` already returns None off
  macOS.
- The native ctypes loaders all had Python fallbacks + graceful load — they just
  hard-coded the `.dylib` filename.

## What shipped
1. **Per-platform native lib** — `divoom_lib/native_lib.py`
   (`library_path()`/`platform_libname()`) returns
   `libdivoom_compact.{dylib|so|dll}`; `framing`, `media_decoder`,
   `native.image_encoder`, `native.downscaler` all resolve through it.
2. **Cross-platform build** — `scripts/build_libdivoom.sh`: clang `-dynamiclib`
   → `.dylib` on macOS; `cc -shared -fPIC -lm` → `.so` on Linux. ARM → NEON,
   x86_64 → SSE2.
3. **Portable C** — `compact.c` guarded `<arm_neon.h>` + the NEON tile-row copy
   behind `DIVOOM_HAVE_NEON`; x86_64 uses a byte-identical `memcpy`. Both paths
   verified to compile (native arm64 NEON build + an `-arch x86_64` cross-compile
   of all four sources). (`downsample.c` already guarded its NEON.)
4. **Platform-aware tooling** — `conftest` auto-rebuild uses `library_path()`;
   `pyproject` package-data ships `*.dylib`/`*.so`/`*.dll`.
5. **Daemon on Linux** — notification monitoring is macOS-only; `_cmd_start`
   returns a clean `unsupported`/idle state off macOS (never builds the Mac
   monitor). Everything else (device control, the TCP/Unix server) runs.
6. **Library guard** — `media_source.get_current_playing_track()` returns None
   off macOS instead of shelling out to a missing `osascript`.

Tests: `tests/test_native_lib.py` (resolver + all loaders share it),
`tests/test_daemon_platform.py` (Linux notification degradation), pyproject
`*.so` assertion. Suite **991 / 0 / 75**.

## §outcome
- **SHIPPED.** On Linux: `pip install -e .`, `./scripts/build_libdivoom.sh`
  (produces the `.so`), then `divoom-control daemon [--host 0.0.0.0 --token …]`.
  Device control over BLE uses bleak/BlueZ.
- **Not yet run on real Linux hardware** (verified by cross-compile + platform-
  guard unit tests on macOS). Needs a real Linux box + a Divoom device to
  confirm BlueZ pairing/throughput end-to-end.
- **Known platform gaps (by design, documented):** no notification monitoring on
  Linux (macOS Notification Center only — a D-Bus/MPRIS backend is a future
  feature); no now-playing/cover-art on Linux (AppleScript only); the menu-bar
  agent is macOS-only.
