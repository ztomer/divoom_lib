# BLE Hardening — workstream plan

Phases ordered by risk reduced per unit effort. Acceptance criteria:

1. **Honest state** — never report a device connected when it isn't; never
   silently fall back to a stale frame.
2. **Self-healing** — a transient drop (RF blip, device sleep, OS race) recovers
   via bounded retry + backoff, no user action.
3. **Specific failures** — when connect genuinely fails, return the cause (BT
   off, device asleep, held by the phone app, out of range, no permission), not
   a bare "timed out".
4. **Concurrency-safe** — wall (N devices) + per-device live jobs hold several
   BLE links at once without connect-storms or cross-talk.
5. **Testable without hardware** — every failure path reproducible in CI via a
   fault-injecting fake transport.

## Current weaknesses (grounded in `divoom_lib/ble_transport.py`,
`divoom_lib/connection.py`, `divoom_daemon/device_owner.py`,
`divoom_daemon/owner_live.py`, `divoom_lib/wall.py`; bleak 1.1.1)

- **W1 — silent reconnect that returns a dead device.**
  `DeviceOwner._ensure_device_async` does `try: await connect() except: pass`
  then returns `self._device` *even if the reconnect failed*. Downstream
  commands then run against a disconnected link → "timed out"/no-op. (Seen live:
  rapid connect → "Device not found"/"timed out" while the job kept "running".)
- **W2 — `is_connected` lies (macOS CoreBluetooth race).** Partially handled in
  the transport via the `_connection_likely_broken` inference, but the daemon
  layer trusts `is_connected` directly (W1).
- **W3 — connect has no retry/backoff or scan-preflight at the daemon level.**
  A device must be *advertising* to connect; if it's asleep or held by the
  phone app, the single connect attempt just fails with no diagnosis.
- **W4 — no OS-level disconnect signal.** We *infer* drops from write failures
  instead of using bleak's `disconnected_callback`, so a silent drop isn't
  noticed until the next write.
- **W5 — no health/heartbeat.** Nothing proactively detects a dropped link; live
  jobs/wall keep pushing into the void and only log per-iteration errors.
- **W6 — concurrency.** Wall connects N devices with `asyncio.gather` (connect
  storm) and live jobs each build their own link; no serialization of the
  fragile *connect* op, and the shared device event loop can interleave writes.
- **W7 — scattered connection state.** `is_connected`, `_connection_likely_broken`,
  `_notifications_started`, `current_divoom`, daemon `_device`/`_live_devices`
  — no single state machine; hard to reason about or test.
- **W8 — swallowed errors → wrong UI.** `except Exception: pass` in several
  device paths surfaces nothing; the R44 §5 connection-truth check fixed one
  site (connect), the pattern remains in reconnect/live/wall/`get_*`.
- **W9 — `get_*` read-backs unreliable** (task #20): name/alarms/brightness
  reads time out; no retry or graceful "unknown".
- **W10 — no adapter/permission preflight.** BT powered-off or unauthorized
  yields an empty scan → "no devices" with no cause.
- **W11 — live-job / wall device loss isn't repaired.** A mid-job drop logs and
  continues; no reconnect, and `get_live_device`'s `is_connected` check (W2)
  can churn.

## Phased workstreams

### Phase 1 — Honest connect + reconnect — **SHIPPED** (kills W1, W2, W8)
Done: `divoom_lib/ble_connection.py` (ConnectionState/FailureReason/ConnectResult
/BleConnectionError/classify_connect_error/`ensure_connected`); DeviceOwner
connect+reconnect use it (tight 2×8s budget on the interactive path so the typed
reason beats the 20s client timeout); `connect` reply carries {reason, message};
GUI `get_last_connect_error` + actionable toast. `tests/support/fake_ble.py`
fault-injection double; +19 tests. HW-verified (real Ditoo connects; bogus MAC →
typed `timeout` reason in 16.4s). Original spec below.

- New `divoom_lib/ble_connection.py` `ConnectionState` enum
  (DISCONNECTED / CONNECTING / CONNECTED / DEGRADED / FAILED) + a small
  `ensure_connected(deadline)` that: scans-preflight (is the MAC advertising?),
  connects with bounded retries + exponential backoff + jitter, verifies with a
  cheap round-trip (the 0x46 probe already used at connect), and returns a
  typed result (`ConnectResult{ok, state, reason}`) — never a dead handle.
- `DeviceOwner._ensure_device_async` / `_build_device_async` use it and
  propagate the typed reason; `connect_device` reply carries `reason` so the GUI
  shows "device asleep / held by phone / BT off", not "timed out".
- Tests: fake transport that fails N connects then succeeds; asserts backoff
  count, the typed failure reasons, and that a failed reconnect returns
  `ok=False` (not a live-looking handle).

### Phase 2 — OS disconnect callback + health — **SHIPPED (live jobs)** (W4, W5, W11)
Done: `BleakClient(..., disconnected_callback=_on_os_disconnect)` on both
construction sites → a drop flips state immediately (no inference lag); new
`is_alive` (connected and no pending drop) on transport → connection → Divoom.
Live jobs consult `is_alive` and self-heal via Phase 1 `ensure_connected`
(`_ensure_live_device`); the cached background device is rebuilt when its link
dies; an unrecoverable drop skips the tick (loop survives) with a typed reason.
+6 tests (fault-injected OS drop + live-job self-heal). HW-verified. **Wall
self-heal deferred to Phase 3** (handled with the bounded-concurrency rework).
Original spec below.

- Pass `disconnected_callback=` to `BleakClient` so a drop flips
  `ConnectionState` immediately (no inference lag). Keep the write-failure
  inference as a fallback.
- A lightweight per-device `is_alive()` (cached `is_connected` and no pending
  `_connection_likely_broken`) consulted by live jobs / wall before each push;
  on a confirmed drop, attempt one in-loop reconnect via Phase 1 before
  skipping the tick (so a live widget self-heals instead of freezing).

### Phase 3 — Concurrency safety + wall self-heal — **SHIPPED** (W6, W11-wall)
Done: a per-running-loop connect lock (`ble_connection._connect_lock`) funnels
the fragile *connect* handshake one-at-a-time so wall + live jobs never
connect-storm CoreBluetooth (writes already serialize via `_write_lock`; the
lock is lazy-per-loop so the daemon loop and each test loop get their own).
`connect_devices(items, concurrency=2)` brings up many devices with bounded
concurrency, returning a `{key: ConnectResult}` map. `DivoomWall.connect()`
uses it → per-slot typed results on `self.connect_results`, logs which screen
failed and why, stays usable on partial success, raises only on total failure.
`DivoomWall.show_image` self-heals: a dropped slot is revived via Phase 1
`ensure_connected` before its push (captured per-slot, so one dead screen
doesn't freeze the rest). New `DivoomWall.is_alive`. Also hardened the daemon
socket server (`serve_forever` binds+listens on a local socket before
publishing `self._server`, killing a startup race where a concurrent `stop()`
nulled it mid-setup → flaky "Connection refused" in CI). +8 fault-injected
tests (serialized handshake, per-loop lock, bounded concurrency, per-slot
results, partial-ok, total-failure reason, slot self-heal, unrecoverable slot).
Original spec below.

- A process-wide `asyncio.Lock` (or small semaphore) around the *connect*
  operation so wall + live jobs don't connect-storm CoreBluetooth (connect is
  the fragile op; writes already serialize per-device via `_write_lock`).
- Wall connect: bounded-concurrency gather (e.g. 2 at a time) + per-slot
  typed result so a partial wall reports which screen failed and why.

### Phase 4 — Adapter / permission preflight — **SHIPPED** (W10)
Done: `divoom_lib/ble_preflight.py` `preflight_bluetooth()` runs before
scan/connect and maps CoreBluetooth state → the same typed `FailureReason` the
connect path uses, so an empty scan / blocked connect carries a cause. The
default check is the **synchronous, thread-safe** `CBCentralManager.authorization()`
(denied/restricted → `PERMISSION` with an actionable message); auth
not-determined/allowed proceeds. Daemon `scan()` returns
`{success:False, reason, message, devices:[]}` and `connect()` (BLE only, LAN
skips) returns `{success:False, reason, message}` when blocked. +13 tests
(injected readers — no hardware).

IMPORTANT — the live `CBManagerState` power probe (`_read_power_state`, run-loop
pumping) is **opt-in only, not the daemon default**: creating a CBCentralManager
+ pumping NSRunLoop crashes libdispatch off the main thread, and daemon command
handlers run on socket-accept worker threads. The radio-off case is instead
surfaced by the connect path's typed `ADAPTER_OFF` (`classify_connect_error`
maps bleak's "powered off"). A main-thread/GUI caller may pass
`read_power=_read_power_state` to additionally diagnose a powered-off adapter.
Original spec below.

- Before any scan/connect, check the adapter is powered + authorized
  (CoreBluetooth `CBManagerState`; we already read `CBCentralManager.authorization()`
  for TCC). Map states → actionable messages ("Bluetooth is off",
  "Grant Bluetooth permission to python3"). Surface via the existing daemon→GUI
  error channel + menubar tooltip.

### Phase 5 — `get_*` read-back hardening — **SHIPPED (resilience layer)** (W9 / task #20)
Done: `divoom_lib/ble_reads.py` `read_with_retry()` + `ReadCache` + typed
`ReadResult` (ok / value / from_cache / reason; `.known` drives the UI dash).
A flaky read now retries with a short per-attempt timeout and degrades to the
**last-good cached value** (`from_cache=True`) instead of a bare `None` the UI
can't distinguish from a real value; with nothing cached it returns a typed
unknown (`ok=False`). Wired into `Device.get_brightness` + `get_device_name`
(cache attached lazily to the communicator, survives reconnects). Reads no
longer raise out (an exception → typed UNKNOWN). +10 tests (fake comm, no HW).

DEFERRED (needs hardware): the root-cause framing investigation — WHY the
0x42/0x46/0x13 query frame goes unanswered on some models (likely a per-model
command variant). The resilience layer makes the timeout degrade gracefully
regardless; closing the protocol gap is a separate HW-iteration task. Remaining
`get_*` reads (alarms, temp, work mode, …) can adopt `read_with_retry` the same
way. Original spec below.

- Wrap reads in a bounded retry with a short per-attempt timeout, and on
  exhaustion return a typed "unknown" the UI renders as a dash (not a spinner /
  not a wrong value). Cache the last *good* read so the UI degrades gracefully.
- Investigate the framing mismatch (query 0x42/0x46/0x13) against the APK once
  more — may be a per-model command variant.

### Phase 6 — State consolidation + observability — **SHIPPED (observability)** (W7)
Done: a single pure `ble_connection.derive_connection_state(active)` maps the
device/wall's honest liveness (is_connected + is_alive, which already fold in
the P2 OS-drop callback + write-failure inference) to one `ConnectionState` —
DISCONNECTED / CONNECTED / DEGRADED. The daemon exposes it on `device_status`
as `connection_state` (so the GUI dot can show DEGRADED — connected-but-link-
dead — not just on/off) and logs a one-line transition (a connection timeline
in `/tmp/divoom_daemon.log`). Housekeeping: extracted `OwnerNotifyMixin`
(`owner_notify.py`) to keep `device_owner.py` under 500 LOC. +10 tests.

DEFERRED: physically folding the scattered flags (`is_connected`,
`_connection_likely_broken`, `_notifications_started`) into one state object is
a larger refactor of the hot write path; P1–P3 already made those flags honest
and `derive_connection_state` now reads them through one funnel, so the
remaining consolidation is cleanup, not correctness. GUI-side: consuming
`connection_state` to render a DEGRADED (amber) dot is a small follow-up.
Original spec below.

- Fold the scattered flags into the `ConnectionState` owner; expose it on
  `device_status` so the GUI dot reflects CONNECTING/DEGRADED, not just
  on/off. Structured connection logging (one line per state transition) to
  `/tmp/divoom_daemon.log` for field diagnosis.

### Cross-cutting — fault-injection test harness (enables all phases)
- `tests/support/fake_ble.py`: a transport double that can be scripted to
  drop, time out, lie about `is_connected`, fail the Nth connect, or vanish
  from scan — so every hardening path is unit-tested in CI without hardware.
- Hardware smoke (`tests/test_hardware_smoke.py`) extended: connect → drop
  (power-cycle prompt) → auto-reconnect → push, on each real device.

## Rollout order & exit criteria
P1 → P2 → P3 → P4 → P5 → P6, each shippable independently.
**Exit:** rapid connect/disconnect/switch and a mid-session device power-cycle
never leave a lying dot, never wedge a live job, and always yield either a
working device or a specific recoverable reason — proven by the fake-BLE suite
in CI and a hardware smoke on Ditoo + Pixoo (+ wall).

## Notes / non-goals
- Keep the R24 TCC responsibility-disclaim (already solid) — preflight only
  *reports* permission state, doesn't re-implement it.
- LAN/SPP transports get the same `ConnectResult` shape but their failure modes
  differ (HTTP probe / serial) — handled in the same typed-result API.
