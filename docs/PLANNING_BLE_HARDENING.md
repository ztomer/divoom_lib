# BLE Hardening & Foolproofing — workstream plan

Goal: make every Bluetooth interaction **predictable, self-healing, and
honestly reported**. No silent failures, no lying state, no dead-ends the user
can't recover from. This spans several rounds; phases are ordered by
risk-reduction per effort.

## Definition of "foolproof"

1. **Honest state** — the UI/daemon never reports a device "connected/active"
   when it isn't, and never silently drops to a stale frame.
2. **Self-healing** — a transient drop (RF blip, device sleep, OS race)
   recovers automatically with bounded retries + backoff, without user action.
3. **Recoverable dead-ends** — when it genuinely can't connect, the user gets a
   specific, actionable reason (BT off, device asleep, owned by the phone app,
   out of range, needs permission) — never a generic "timed out".
4. **Concurrency-safe** — wall (N devices) + per-device live jobs can hold
   several BLE links at once without connect-storms or cross-talk.
5. **Testable** — failures are reproducible in CI via a fault-injecting fake
   transport; we don't rely on hardware to prove the hardening.

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
  device paths surfaces nothing; the R44 §5 connection-truth check fixed ONE
  site (connect), the pattern remains in reconnect/live/wall/`get_*`.
- **W9 — `get_*` read-backs unreliable** (task #20): name/alarms/brightness
  reads time out; no retry or graceful "unknown".
- **W10 — no adapter/permission preflight.** BT powered-off or unauthorized
  yields an empty scan → "no devices" with no cause.
- **W11 — live-job / wall device loss isn't repaired.** A mid-job drop logs and
  continues; no reconnect, and `get_live_device`'s `is_connected` check (W2)
  can churn.

## Phased workstreams

### Phase 1 — Honest connect + reconnect (kills W1, W2, W8 at the source)
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

### Phase 2 — OS disconnect callback + health (W4, W5, W11)
- Pass `disconnected_callback=` to `BleakClient` so a drop flips
  `ConnectionState` immediately (no inference lag). Keep the write-failure
  inference as a fallback.
- A lightweight per-device `is_alive()` (cached `is_connected` AND no pending
  `_connection_likely_broken`) consulted by live jobs / wall before each push;
  on a confirmed drop, attempt ONE in-loop reconnect via Phase 1 before
  skipping the tick (so a live widget self-heals instead of freezing).

### Phase 3 — Concurrency safety (W6)
- A process-wide `asyncio.Lock` (or small semaphore) around the *connect*
  operation so wall + live jobs don't connect-storm CoreBluetooth (connect is
  the fragile op; writes already serialize per-device via `_write_lock`).
- Wall connect: bounded-concurrency gather (e.g. 2 at a time) + per-slot
  typed result so a partial wall reports WHICH screen failed and why.

### Phase 4 — Adapter / permission preflight (W10)
- Before any scan/connect, check the adapter is powered + authorized
  (CoreBluetooth `CBManagerState`; we already read `CBCentralManager.authorization()`
  for TCC). Map states → actionable messages ("Bluetooth is off",
  "Grant Bluetooth permission to python3"). Surface via the existing daemon→GUI
  error channel + menubar tooltip.

### Phase 5 — `get_*` read-back hardening (W9 / task #20)
- Wrap reads in a bounded retry with a short per-attempt timeout, and on
  exhaustion return a typed "unknown" the UI renders as a dash (not a spinner /
  not a wrong value). Cache the last *good* read so the UI degrades gracefully.
- Investigate the framing mismatch (query 0x42/0x46/0x13) against the APK once
  more — may be a per-model command variant.

### Phase 6 — State-machine consolidation + observability (W7)
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
