# ROUND 57 — Bulletproof daemon connect / retry / UI updates

## Context

v0.22 connect from the UI failed for **all** devices. Root-caused (R56+): the Rust
daemon's BLE path can **wedge forever** on a dead CoreBluetooth session. `BleTransport::connect`
and `ble::scan` call `central.start_scan()` / `central.peripherals()` with **no `tokio::time::timeout`
guard**. On a wedged central those awaits never return, so `run_connect`/`run_scan` never produce
an `Err`, so the `reset_central` self-heal in `cmd_connect`/`cmd_scan` **never fires** — the command
hangs, the client's 20s read times out, the UI shows "Failed to connect", and the daemon stays stuck
for every later connect.

A wedged daemon is a critical bug, not a corner case. This round makes connect/scan/retry/UI
**structurally unable to wedge**, and adds ultra-pedantic tests that exercise the wedge
**deterministically** (no flaky real-BLE dependency).

Scope decision (user): **Rust daemon + menubar only.** The Python daemon
(`divoom_daemon/daemon.py`, `owner_connect.py`, …) is dead code — no parity fixes there. The
Python **client** (`daemon_protocol.py` / `daemon_client.py`) and the JS UI are still in scope
(the GUI talks to `divoomd` over the socket).

## Wedging-case matrix (what "bulletproof" must cover)

| # | Case | Today | Fix |
|---|------|-------|-----|
| 1 | Dead central: `start_scan`/`peripherals` hang | **wedge** | bound every central await w/ `tokio::time::timeout`; on timeout return Err matching `is_dead_central` → `reset_central` + retry |
| 2 | Dead central during `scan` | **wedge** (same) | same guard in `ble::scan` (done in R56; keep) |
| 3 | Daemon process dies (CoreBluetooth SIGABRT) | client returns error dict (ok) | UI already has daemon-down banner + auto-reconnect; verify + add test |
| 4 | Connect longer than client `connect_timeout` (20s) | false "Failed" | reconcile: daemon bounded worst-case < client timeout; async "connecting" ack + status events (later) |
| 5 | Concurrent `connect` (double-click / 2 clients) | overwrites shared `device`, corrupts central | **connect-in-progress guard** (like `scanning`) → reject 2nd with clear error |
| 6 | Connect while already connected to a device | stale overwrite | `cmd_connect` drops prior device first (mirror Python) |
| 7 | Stale `DaemonDeviceProxy` after daemon restart | commands fail silently | `connect_single_device` re-ensures daemon on failure; `reconnect_daemon` already exists |
| 8 | UI "connecting…" spinner wedged (no client timeout path) | stuck | UI watchdog: cap spinner at client timeout + surface failure; never trust a hung promise |
| 9 | `subscribe` stream dies (daemon restart) | heartbeat stops updating | existing daemon-health heartbeat re-probes; verify + test |
| 10 | Reply never newline-terminated | buffer cap (ok) | keep `MAX_REPLY_BYTES` on both ends |

## Fix groups

**A. Bound every central await (Rust, `ble.rs` + new `central.rs`).**
- Introduce `BleCentral` enum: `Real(Adapter)` + `#[cfg(test)] Faulty`. Wrap btleplug so
  `start_scan`/`peripherals`/`stop_scan` go through `BleCentral` methods.
- In `ble::scan` + `ble::connect`, every central await is inside `tokio::time::timeout`; on
  timeout return an error string containing `timed out`/`stale`/`central` so `is_dead_central`
  matches → `reset_central` + retry. Confirmed: healthy connect still 0.9s; dead-central recovery
  ~3–10s (within client 20s).
- Extend `is_dead_central` (done R56) to match `timed out`/`stale`/`central` (keep
  `device not found in scan` + `no BLE adapter` excluded).

**B. Connect-in-progress guard (`daemon.rs` + `daemon_connect.rs`).**
- Add `connecting: AtomicBool` + `ConnectGuard` (Drop resets, like `ScanGuard`).
- `cmd_connect` rejects a 2nd concurrent connect with `err_reply("connect already in progress")`.

**C. Client resilience (`daemon_protocol.py` / `daemon_client.py`).**
- `connect_single_device` (scanner_mixin) re-ensures daemon (`reconnect_daemon`) once before
  giving up on a daemon-unreachable reply.
- Keep `connect_timeout` ≥ daemon bounded worst-case (set to 30s for margin).

**D. UI watchdog (`app_globals.js`).**
- `connectDevice`: arm a `setTimeout` (client `connect_timeout` + slack) that, if the promise
  hasn't resolved, flips the dot to `inactive` + shows "Background service not responding" so the
  spinner can never wedge.

## Test strategy (deterministic — no real BLE needed)

The crown jewel: a **fake/wedged central** (`BleCentral::Faulty`) whose `start_scan`/`peripherals`
never resolve. This lets us exercise the wedge + self-heal in CI without hardware.

- `native-port/divoomd/src/central.rs` (new, `#[cfg(feature="ble")]`):
  - `scan(&Faulty, …)` returns **within** `dur+10s`, is `Err` (no hang).
  - `connect(&Faulty, id)` returns **within** bounds, is `Err` matching `is_dead_central` (no hang).
  - `is_dead_central` matches `timed out`/`stale`/`central`/`Channel closed`; NOT
    `device not found in scan` / `no BLE adapter`.
  - `cmd_connect` on a `Daemon` whose `central()` yields `Faulty` returns bounded `Err` (uses a
    `#[cfg(test)]` central override on `Daemon`).
- Python (`tests/`): `DaemonClient.send_command` against a **hanging socket server** returns an
  error dict and never raises/hangs (deterministic, no daemon binary needed). Plus connect
  timeout/retry assertions.
- Hardware (`tests/test_rust_daemon_parity.py`, `--run-hardware`): scan→connect→device_call→
  disconnect→reconnect loop ×N, asserting no wedge across iterations (skipped by default).
- UI e2e (Playwright, `tests/test_e2e_device_status_*.py`): simulate daemon-down → banner shows,
  never a wedged spinner; slow/failing connect → failure surfaced, spinner cleared.

## Files

- `native-port/divoomd/src/central.rs` (NEW) — `BleCentral` enum + methods + wedge tests.
- `native-port/divoomd/src/lib.rs` — `pub mod central;`.
- `native-port/divoomd/src/ble.rs` — `make_central`→`BleCentral`; `scan`/`connect` take `&BleCentral`;
  bound `start_scan`/`stop_scan`; `BleTransport._central: BleCentral`.
- `native-port/divoomd/src/daemon.rs` — `central` field/return type `BleCentral`; `stop_scan_cleanup`;
  `#[cfg(test)]` central override; `connecting` guard field.
- `native-port/divoomd/src/daemon_connect.rs` — `ConnectGuard`; guard in `cmd_connect`.
- `divoom_gui/scanner_mixin.py` — `connect_single_device` re-ensure daemon.
- `divoom_gui/web_ui/app_globals.js` — connect watchdog.
- `tests/test_daemon_client_wedge.py` (NEW) — hanging-socket client test.
- `divoom_daemon/daemon_config.py` — `connect_timeout` 20→30 (margin).

## Plan of work (incremental, each with a red→green test)

1. `BleCentral` abstraction + bound `start_scan`/`stop_scan` in `connect` + `connect` guard.
2. Fake-central wedge unit tests (central.rs) — the deterministic harness.
3. Python hanging-socket client test.
4. `connect_single_device` re-ensure + UI connect watchdog.
5. Reconcile timeouts; run full suite; update CHANGELOG + SESSION_HANDOFF; cut v0.22.1 if shipped code changed.

## Outcome / what shipped

- **Root cause confirmed + fixed.** Rust `BleTransport::connect`/`ble::scan` had no
  timeout around `central.start_scan()`/`central.peripherals()`; a dead
  CoreBluetooth session hung forever → self-heal never fired → daemon unusable
  for all devices. New `BleCentral` abstraction bounds every BLE call in
  `tokio::time::timeout`; `connect` guard added; `is_dead_central` widened.
- **Files shipped:** `central.rs` (NEW) + `daemon_ble.rs` (NEW, split for 500-LOC
  rule); edits to `ble.rs`, `daemon.rs`, `daemon_connect.rs`, `lib.rs`,
  `scanner_mixin.py`, `app_globals.js`, `daemon_config.py`.
- **Tests shipped (deterministic, no hardware):** 4 Rust wedge tests (`central.rs`
  `BleCentral::Faulty`), 4 Rust connect-lifecycle unit tests (`daemon_connect.rs`),
  5 Python hanging-socket client tests (`test_daemon_client_wedge.py`), 8 Python
  daemon connect/disconnect edge-case e2e (`test_daemon_connect_edge_e2e.py`, real
  divoomd over a socket via its `mock` transport). All green: 42 Rust lib + 39 python.
- **Released v0.22.1** (tag, GitHub release w/ DMG, Homebrew cask bumped, sha
  `3f9fb34e69f63483fc409a445b9ce4b757f71a473fc941e9415383615de0a18e`). Real BLE
  connect verified unchanged on Pixoo-1 (0.7s).
- **Remaining gap:** real-device `--run-hardware` scan→connect→device_call→
  disconnect→reconnect loop needs a free Pixoo; the mock/LAN e2e covers the
  orchestration logic without radio.
