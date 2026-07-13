# Round 45 — cask release, test fix, scan-timeout backstop

**Agent**: opencode  
**Date**: 2026-06-22

## Outcome / what shipped

After the `v0.20.0` cask install, `brew reinstall --cask divoom-control` succeeded
but the app couldn't detect devices — it connected to one device then got stuck.
Root cause: the scan timeout backstop (90s) and the user's configured timeout (360s)
created a guaranteed-failure pattern:

1. **`owner_loop.py:_run_on_loop`** — Future was never saved, so `future.cancel()`
   was unreachable on backstop fire. The scan coroutine kept running for the full
   360s, consuming BLE resources and blocking subsequent operations on the loop.
   **Fix**: save the Future, cancel on `TimeoutError`.

2. **`owner_connect.py:scan()`** — User's `config.ini` had `timeout = 360`. The daemon
   passed it straight to BLE discovery, but `_run_on_loop` only waits 90s. Every scan
   with timeout > 90s was a guaranteed failure (backstop fires, scan fails, coroutine
   runs for remaining 270s). **Fix**: cap scan timeout to `_SCAN_RESULT_TIMEOUT` (90s)
   at the daemon level.

3. **`app_init.js:load_config()`** — `<input max="120">` was bypassed when JS set
   `el.value = conf.timeout` (360). HTML `max` only constrains user interaction, not
   programmatic assignment. **Fix**: clamp to `el.max` before setting.

**Also shipped**:
- Created GitHub release `v0.20.0` on `ztomer/divoom_lib` + uploaded the DMG
  (the cask URL now resolves).
- Fixed `test_connection_cap_rejects_when_full` (`BrokenPipeError` race).
- Session handoff updated, CHANGELOG updated.
- Suite: 1700 passed, 87 skipped.

- **Tivoo-Max SPP routing fix (2 bugs found and fixed)**:
  1. `owner_connect.py:_ensure_device_async` hardcoded `use_ios_le_protocol=False`,
     switching Tivoo-Max to SPP transport (Bluetooth Classic RFCOMM) instead of BLE.
     Fixed to `None` (autoprobe).
  2. `connection.py:connect` SPP condition `not self.use_ios_le_protocol` fired for
     `None` (unprobed) too. Fixed to `self.use_ios_le_protocol is False`.

## Open / deferred

- **Stale `last_connected_device`**: The UUID in config doesn't match any scanned
  device, causing a ~16s auto-connect delay before fallback to a 3s reconnect scan.
  Consider purging or providing a "forget device" UI in a future round.
