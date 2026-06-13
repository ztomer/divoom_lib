# Architecture gap scan — 2026-06-13

Scan of the daemon-ownership seams (`DeviceOwner`, `CommandQueue`, `ble_registry`,
the GUI/menubar clients, the quit path), done after R47. Most of the surface is
solid; six gaps stand out. Several are the same "owns the device but the
bookkeeping disagrees" class as R47 (daemon-owned-device visibility).

Status: **all gaps resolved.** G1–G5 + G7 shipped (G4/G5/G7 HW-verified; G2 + G3
HW pass still pending); G6 closed won't-fix (no real trigger). G7 was found during
G4 HW testing (wall rebuilt fully on every reconfigure). See CHANGELOG entries
"Architecture gap fixes G1–G3", "G4–G5", and "G7 + G6 resolution" (2026-06-13).

---

## High priority

### G1 — Stale activity registry: ghost devices (the inverse of R47)

R47 surfaces daemon-owned devices in the selector + menubar from
`_device_activity`, but nothing ever *removes* an entry.

- `device_owner.disconnect()` (`divoom_daemon/device_owner.py:283`) and
  `wall_configure()` teardown (`:333`) don't touch `_device_activity`.
- `stop_all_live_jobs()` (`:482`) cancels tasks without setting `idle` — only the
  per-job `live_job_stop` reverts to idle.

Result: after a device is disconnected or a wall is torn down, its tile/dot
lingers as "streaming" forever, and `refreshOwnedDevices` keeps re-injecting it
into the selector. R47 is half-complete without teardown.

**Fix:** clear/idle the activity entry on `disconnect`, `wall_configure(empty)`,
and `stop_all_live_jobs`; add a TTL prune in `get_device_activity` (drop entries
older than N min with no live job and not the active device). ~1 file, small.

### G2 — A scan freezes live widgets and hangs every user action for up to 60 s

`scan()` runs through `_run_device` → the command queue
(`divoom_daemon/device_owner.py:304`), and the queue worker awaits each item to
completion before dequeuing the next (`command_queue.py:213`). Live-widget pushes
go through the **same** queue (`live_jobs.push_image_to_device` →
`_cmd_queue.submit_async`, `live_jobs.py:28`). So a default 60 s scan blocks every
widget tick, channel switch, and art push behind it.

A BLE scan is a central-manager op — it doesn't need the connected-peripheral
lock at all. Likely contributes to the "no indication / feels stuck" symptom.

**Fix:** run the discovery coroutine directly on the device loop
(`run_coroutine_threadsafe`) instead of through the serialized queue, so scans run
concurrently with device I/O. Medium; needs a HW pass (scan while a widget
streams).

### G3 — A leaked exclusive token wedges the device permanently

The daemon's queue is created as `CommandQueue(loop)` with **no `item_timeout`
and no `maxsize`** (`device_owner.py:79`). `exclusive_start` sets
`_exclusive_owner = token`; if a client dies or errors between `exclusive_start`
and `exclusive_end` (push crash, GUI killed, socket drop), the token never
releases and `_dequeue` will only ever dispatch that orphaned token — every other
caller blocks **forever** (no expiry to bail them out). One crashed push = total
device lockup until daemon restart.

**Fix:** give the device queue a sane `item_timeout`; auto-release the exclusive
owner on client disconnect or after an idle deadline; consider a bounded
`maxsize` for backpressure. Medium, robustness-critical.

---

## Medium priority

### G4 — Registry eviction silently kills the active device when a wall reuses its MAC

`ble_registry.evict` (`divoom_lib/ble_registry.py:32`) disconnects the prior
transport for an address, but the daemon's `_device`/`_wall` references aren't
told. If screen X is the active `_device` and you then build a wall that includes
X, the wall's connect evicts X → `_device` now holds a dead handle → next
`device_call` reconnects X, evicting the wall's slot → they ping-pong. Narrow
(same screen as both active device *and* a wall member) but a real correctness
hole, and exactly the single↔wall contention R45 #6 was about.

**Fix:** when a wall slot claims a MAC the active device holds, have the daemon
drop/relinquish `_device` for that MAC explicitly (or share the one transport).
Needs HW repro.

### G5 — Background live-device health is invisible

`_connection_state` (`device_owner.py:96`) only derives from `_device or _wall`,
never `_live_devices`. A background streaming device that drops gets self-healed
(P2) but emits no DEGRADED signal anywhere — the GUI/menubar heartbeat only
watches the active device. So a stuttering live widget on a non-active screen is
silent. Now that R47 shows these devices, surfacing their health is the natural
next step.

**Fix:** fold `_live_devices` health into `device_status` (per-mac), let the
heartbeat reflect it on the streaming dot.

---

## Low priority / noted

### G6 — Scan indicator covers only the Settings button

The reconnect/auto-discovery scans inside `_ensure_device_async` (no-mac path)
give no GUI signal. Minor; the R47 indicator is button-triggered only. Could be
wired to a daemon "scanning" event for full coverage.

---

## Suggested sequencing

1. **G1** — finishes R47 (small, same area, ship together).
2. **G3 then G2** — queue robustness + scan concurrency; both touch the
   command-queue / device-loop boundary, so one "device-loop hardening" round.
3. **G4 / G5** — a "wall + multi-device contention" round; both need HW repro.

Near-term: **G1** (leaves R47 showing ghosts) and **G3** (failure mode is a
total, silent device lockup).
