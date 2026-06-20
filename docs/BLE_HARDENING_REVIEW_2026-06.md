# BLE / transport hardening review — 2026-06 (R53)

A four-lens adversarial review of the Bluetooth subsystem (~2,400 LOC across
`ble_*`, `connection.py`, `bt_spp_transport.py`, `command_queue.py`,
`owner_loop.py`, `owner_live.py`, `owner_art.py`). Each finding was verified
against the code. This doc is the source of truth for what shipped vs. what is
deferred — the deferred items are real and tracked here so they aren't lost.

Lenses: (1) connection lifecycle/reconnection, (2) async concurrency/cancellation,
(3) timeouts/leaks/error-honesty, (4) SPP/preflight/LAN parity.

---

## SHIPPED in R53 (verified + tested — `tests/test_ble_timeout_hardening.py`)

- **Unbounded `client.connect()` / `start_notify()`** (`ble_transport.py`).
  `ensure_connected` wrapped the *first* connect with a 12 s timeout, but the
  internal reconnect path (`send_payload → _send_payload_locked → connect`)
  bypasses it and runs **while holding `_write_lock`** — so a dead/asleep/held
  device hung the whole transport forever. Now every raw bleak await is bounded
  (`CONNECT_TIMEOUT=15s`, `NOTIFY_TIMEOUT=6s`, `STOP/ DISCONNECT=3/5s`) and raises
  `DeviceConnectionError` on timeout (reason preserved).
- **Notify-subscription leak on disconnect** (`ble_transport.disconnect`). The
  comment claimed `stop_notify` released the OS subscription, but **no
  `stop_notify` was ever called** — leaking it, which made a later `start_notify`
  on a fresh client raise "already started". Now `disconnect()` calls a bounded
  `stop_notify` before `client.disconnect()`.
- **Daemon RPC thread could block forever on a wedged BLE op**
  (`owner_loop.py`). `_run_device(...).result()` and `_run_on_loop(...).result()`
  had no timeout, and the `CommandQueue` was built with **no `item_timeout`** (so
  ops queued behind a stuck op piled up forever). Now: queue `item_timeout=240s`
  (rejects an op left *waiting* behind a stuck op) + caller-side `.result()`
  backstops (270s device / 90s scan) that surface a clean `TimeoutError` instead
  of hanging a socket handler. `hot_update` is fire-and-forget (`submit()` w/o
  `.result()`) so it is unaffected.
- **Transport-swap registry leak** (`connection.py`). On a BLE↔SPP transport-type
  switch, `_active_transport` was replaced without tearing down the old one — so
  the old BLE transport stayed in the process-wide registry AND kept its
  CoreBluetooth link open while the new transport connected to the *same device*
  (the exact contention the registry exists to prevent). Now
  `_teardown_outgoing_transport()` disconnects+unregisters the outgoing transport
  before the swap (no-op on a same-type reconnect).

---

## DEFERRED — real, but need their own tested surgery (do NOT rush)

Ranked by value. Several touch the 0x8B animation handshake or task lifecycle
where a careless change can break working pushes — they deserve isolated rounds.

### High
- **ACK ≠ success in custom-art push / hot-update.** `custom_art_push.push_page`
  returns `True` on bare GATT-write ACKs with no device-state verification
  (`owner_art.custom_art_push` then reports `success`). `hot_update._stream_file`
  returns `True` on a missing done-ack ("no done-ack … continuing"). A device
  that silently drops the write — or went unreachable mid-stream — is reported as
  success. Fix: verify via `query_page` (0x8E) after K0 / track per-file
  device confirmation and downgrade `success` when unconfirmed. **(Likely related
  to R45 #1 "Custom Art channel empty" — investigate together.)**
- **Live-job push interleaves with a foreground exclusive 0x8B push.** Live-job
  frames are submitted *tokenless*, so while a GUI exclusive push runs they queue
  and then fire in a burst the instant it releases, clobbering it. Fix: have
  `exclusive_start` call `live_jobs_stop_for(mac)` (the channel-switch path
  already does this), or give live pushes a device-stable token treated as a
  barrier.
- **Shared `notification_queue` + scalar `_expected_response_command` cross-talk.**
  A concurrent `send_command_and_wait_for_response` can flush a 0x8B ready-ACK /
  retransmit frame out from under an in-flight animation push (only safe today
  because nothing else runs via `_run_on_loop` — there is no guard preventing a
  future addition). Fix: per-operation response correlation (a `Future` keyed by
  command id) instead of one shared queue + scalar.
- **`ensure_connected` fast-path trusts cached `is_connected`, not `is_alive`.**
  It early-returns success on a handle whose link is dead but whose CoreBluetooth
  bool still reads True (the lag the codebase documents). The OS-disconnect
  callback only flips `_connection_likely_broken`, which the fast-path never
  consults. Fix: check `is_alive` in the fast-path / `_ensure_device_async`.

### Medium
- **Live-job stop is fire-and-forget.** `live_job_stop` schedules `task.cancel()`
  and returns "stopped" without awaiting death → a stopped poller can push one
  more frame; a double-start can momentarily run two pollers; `_live_tasks` is
  mutated cross-thread. Fix: await cancellation to completion; confine
  `_live_tasks` mutation to the loop thread. (Same applies to `stop_all_live_jobs`
  / `_release_live_device_if_idle` in `device_owner.stop`.)
- **SPP transport is weaker than BLE across the board** (`bt_spp_transport.py`):
  the `_open_event.wait()` blocks the *event loop* up to 8 s; a failed connect
  leaks the runloop/read threads + serial port; `_serial_read_loop` swallows all
  errors and dies silently while `is_connected` still reads True; `max_retries`
  is accepted but ignored; no preflight / no `FailureReason` classification; a
  corrupt iOS-LE length field stalls the parser. Fix: bring SPP to BLE parity
  (off-loop open, teardown-on-failure, death-aware `is_connected`, classify
  errors, bound frame length). Dead code: `spp_connection.read_spp_notifications_loop`
  / `disconnect_spp` are unused — delete.
- **Discovery scans are unbounded/unstoppable** (`utils/discovery.py`): fixed 10 s
  `BleakScanner.discover` with no early-exit on match and no `try/finally` stop on
  cancellation. Fix: detection-callback + stop-on-first-match + guaranteed stop.

### Low
- Registry `evict` swallows a disconnect failure but still pops (a failed
  eviction looks successful, old link survives → downstream connect timeout).
- `_connect_locks` / a stale registry survive a daemon device-loop restart
  (key on `id(loop)`; process-global `_active`). Reset on loop teardown.
- Exclusive deadline only re-arms on *dequeue*; a single multi-minute exclusive
  item could be force-released mid-flight. Re-arm on item completion too.
- LAN `post` opens a fresh `aiohttp` session per request.

---

## Cannot verify from this harness (need a real device / app)

Menubar native tile render, hot-channel pixel fidelity, real-app clean-quit,
Tivoo-Max connectivity, Bluetooth TCC grant, Linux end-to-end. Code reviewed;
final confirmation is a hardware/app smoke test.
