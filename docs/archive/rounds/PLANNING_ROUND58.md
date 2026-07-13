# Planning — Round 58: daemon hardening blitz (R57 follow-on)

**Date:** 2026-07-12
**Goal:** close the two hardening gaps left open after R57's connect-wedge fix, with
deterministic (hardware-free) tests, then stop when out of safe-to-harden ideas.

## Gaps addressed

### 1. Socket server: idle timeout + bounded concurrency (DONE)
`divoomd/src/socket_server.rs` previously capped *incoming frame size*
(`MAX_REPLY_BYTES`) but had **no per-connection idle timeout and no concurrency
limit**. A client that connects and holds the socket open silently could pin a
permit + the device lock forever.

- Added `CONNECTION_IDLE_TIMEOUT` (default 300s, `DIVOOMD_IDLE_TIMEOUT_SECS`): a
  connection that sends no newline-terminated request within the window is dropped
  (EOF). Implemented by wrapping the per-read in `tokio::time::timeout`.
- Added `MAX_CONNECTIONS` (default 64, `DIVOOMD_MAX_CONNECTIONS`): a `Semaphore`
  bounds concurrent connections — a 6th+ connection is back-pressured (the accept
  loop waits for a free permit) rather than unbounded.
- `main.rs` reads the env overrides and logs the effective limits.

**Tests (Rust, in-process, hardware-free):**
- `divoomd/tests/socket_server_hardening.rs::idle_timeout_drops_silent_peer`
- `divoomd/tests/socket_server_hardening.rs::max_connections_backpressures_extra`
- Updated pre-existing `divoomd/tests/socket_server_behavior.rs` to the new `serve`
  signature (4 args).

### 2. `device_call` overall timeout enforcement (DONE, with caveat)
`cmd_device_call` (`daemon.rs`) held `self.device` lock across the whole op with a
hardcoded 5s that `handle_device_call` *ignored* at the top level — a hung device op
wedged the lock for every other call.

- Wrapped the call in `tokio::time::timeout`. On overrun the future is dropped
  (releasing the lock) and the client gets `device op timed out after Ns`.
- Honors a caller-requested `timeout` arg, **clamped to 1..120s**, default **30s**
  (matching `connect_timeout`).

**Caveat (RESOLVED on hardware):** some commands are legitimately long (e.g.
hotchannel updates). Measured on real Pixoo-1: connect ~3.9s (reconnect ~1.7s),
brightness/clock/hot-channel 59–61ms, `hot_update.update` 1ms (no pending content).
The 30s default / 120s cap is a safety net against a *hung* op, not a cliff for
slow-but-valid ones — normal ops are 1–2 orders of magnitude under the cap. Very
large 0x8B animation / gallery pushes should pass an explicit `timeout` (≤120s).

**Tests (Rust):**
- `divoomd/tests/socket_server_hardening.rs::idle_timeout_drops_silent_peer`
- `divoomd/tests/socket_server_hardening.rs::max_connections_backpressures_extra`
- `divoomd/tests/socket_server_hardening.rs::subscribe_idle_drops_silent_subscriber`
- `daemon_connect.rs::device_call_timeout_enforced_but_not_false_firing` (lock
  released, no false-fire on a normal mock op)
- `daemon_connect.rs::device_call_short_requested_timeout_still_succeeds` (a 1s
  requested timeout on a fast mock op still succeeds)
- Timeout *firing* on a genuinely hung op is not unit-tested (needs hardware / a
  network-blocked LAN target); covered indirectly by the socket idle-timeout tests.

## Not done this round
- UI auto-reconnect / connection-state-machine hardening (GUI side) — deferred; needs
  the app running to verify (user-POV rule). The R57 connect re-ensure + JS watchdog
  already covers the connect-click path; a background reconnect-on-socket-drop is the
  remaining gap.

## Outcome / what shipped
- Socket idle timeout + bounded concurrency (+ subscribe idle watchdog): shipped, 3
  new Rust tests green.
- `device_call` top-level timeout: shipped, 2 new Rust tests green, default 30s /
  120s-cap; hardware-verified it does not false-kill normal ops.
- Real-hardware loop: `test_rust_hardware_parity` extended to a 3× reconnect loop +
  sequential connect to all 4 discovered devices; **run on 4 real devices — 11
  hardware assertions pass** (2 cloud tests still skipped).
- Full suite green: 44 Rust lib + 3 socket + 2 device_call + Python wedge/edge-e2e/
  parity (23 pass, 3 hw/cloud skips) + 11 hardware (with `--run-hardware`).
- No version bump — behavior change is defensive; will cut v0.22.2 only if a later
  round in this blitz changes user-visible behavior.
