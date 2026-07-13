# Planning — Round 59: event-driven UI (kill flaky polling)

**Date:** 2026-07-12 · **Owner:** opencode session `ses_184471307ffeCUHgzv9w51O0oA`

## Problem
The dashboard learns daemon/device state by **polling on timers** (4s heartbeats).
Polling is flaky: it lags (UI shows stale state between ticks), wastes cycles, and
a dropped tick reads as "nothing changed". R58 proved the daemon *can* push honest
state — the `status` connect/disconnect events + the honest subscribe snapshot — but
the rest of the state surface is still polled. Move daemon-owned state to events.

## Audit — polling points (web UI `setInterval`)
| Timer | What it polls | Event-driven? | Plan |
|---|---|---|---|
| `connection_events.js` `refreshConnectionState` 4s | device link state (connected/degraded) | **YES** — daemon already broadcasts `status` on connect/disconnect (R58); add `degraded` | Remove poll; drive from events |
| `connection_events.js` `refreshOwnedDevices` 4s | daemon-owned (non-advertising) devices | **YES** — daemon knows ownership on connect/disconnect | Broadcast `owned_devices` event; remove poll |
| `app_globals.js` `refreshDaemonHealth` 4s | is the daemon reachable/alive | **YES** — subscribe socket closes when daemon dies | Detect socket closure as event; remove poll |
| `settings_notifications.js` `refreshMacNotifStatus` 5s | macOS notif-monitor state | **YES** — daemon knows monitor state changes | Broadcast `notif_status` event; remove poll |
| `gallery_hot.js` `pollProgress` 600ms | hot-channel update progress | **YES** — daemon runs the update | Broadcast `hot_progress` event; remove poll |
| `widgets.js` track/weather/stock/sysmon | **external data** (Yahoo, OpenWeather…) | NO — not daemon state | Keep polling (out of scope) |

## Design
Single broadcast channel (`daemon.tx`) already exists. Add event types:
- `owned_devices` — `{type, devices:[{address,name,kind,state}]}` on connect/disconnect
  (and whenever the owned set changes). Replaces `get_device_activity` polling.
- `notif_status` — `{type, running, counters, error?}` on monitor start/stop/error.
- `hot_progress` — `{type, progress, phase}` during a hot update.
- `status` — extend with `state:"degraded"` when a mid-session write fails (the
  daemon's live-job self-heal already detects this; surface it as an event).

GUI (`_make_daemon_event_handler`) forwards all of these to the web UI via
`window.Divoom.on<Event>(...)`. JS handlers update state immediately; the 4s polls
are removed (the subscribe-socket closure replaces the daemon-health poll).

## Implementation steps
1. Daemon: `owned_devices` broadcast on connect/disconnect (`daemon_connect.rs`);
   `notif_status` on monitor transitions (`macos_notifications.rs`);
   `hot_progress` during update (`sync_artwork.rs`); `status` degraded on write fail.
2. GUI forwarder: forward `owned_devices`/`notif_status`/`hot_progress` (status already).
3. JS: `window.Divoom.onOwnedDevices` / `onNotifStatus` / `onHotProgress` /
   degraded handling in `onDaemonEvent`; remove the 4s `setInterval` polls;
   mark daemon down when the subscribe socket closes (`onDaemonDown`).
4. Keep `widgets.js` external-data polls.

## Verification (HARDWARE in the loop — 4 devices)
- New pytest `test_daemon_event_broadcast.py`: assert `owned_devices` event on
  connect (mock) lists the mac; empty on disconnect. (mock, no HW needed)
- Hardware: extend `tests/test_rust_daemon_parity.py` (or new HW test) to subscribe
  to a REAL daemon, connect a real device, and assert the subscriber receives
  `status`(connected) + `owned_devices`(lists the real mac). Kill the daemon →
  subscriber socket closes (daemon-down path).
- Unit test GUI forwarder for each new event type (fake window).
- User-POV: launch the real app, connect/disconnect a device, confirm the dot +
  sidebar update instantly (no 4s lag), and that killing the daemon flips the
  daemon banner.

## Out of scope this round
- `widgets.js` external-data polls (weather/stock/sysmon/track) — genuinely periodic.
- Full in-app JS visual assertion (documented as user-POV check; logic unit-tested).
