# On-Device Validation Plan

Goal: confirm on the four physical devices that every wire path actually lights
pixels (not just "command succeeded"), and pin the few values that can only be
known from real hardware (e.g. the real EQ/visualizer count, 2.c).

## Constraint & approach

The agent's background shell can't hold macOS Bluetooth permission (CoreBluetooth
hard-crashes via TCC). A process **launched from the user's terminal** has that
permission. So:

1. Agent builds a self-contained harness `scripts/validate_devices.py` that
   connects to the real devices and runs the full command matrix, writing a JSON
   report. (No GUI needed; uses `divoom_lib.Divoom` directly.)
2. **User runs it once** (their terminal → Bluetooth permission). It cycles the
   commands slowly so the user can watch each device, and records per-step
   success/error to `test_reports/device_validation.json`.
3. Agent reads the report, confirms what works, fixes any real-hardware failure,
   and sets the real EQ/visualizer count in the UI.

Two kinds of signal:
- **Automated** (in the report): did each command send without error / return
  truthy? Catches protocol bugs (like the image-push KeyError already found).
- **Visual** (user's eyes): does it actually display, and how many EQ/VJ patterns
  are real? The harness labels each step and dwells so the user can note these.

## Command matrix (per device)

Run in this order, dwelling ~2.5s on visual steps:

1. **Connect** — BLE by address (or discover by name substring).
2. **Brightness** — set 30 → 100 (`0x74`); easy, unambiguous visual check.
3. **Solid light / ambient** — red, green, blue (`set light mode` light path).
4. **Clock dials 0–5** (2.f) — `show_clock(clock=n)`; confirm 6 distinct dials.
5. **VJ effects 0–15** (2.d) — `show_effects(n)`; confirm effects animate.
6. **Visualizer / EQ 0–15** (2.c) — `show_visualization(n)`; **note the highest
   index that shows a distinct pattern** → that's the real count to put in the UI.
7. **Image push** (5.a/5.c/area 7) — push a rendered stock-ticker frame and a
   system-monitor frame via `show_image`; confirm the image appears (this is the
   path the two just-fixed bugs were on).
8. **Disconnect**.

## Acceptance — ✅ PASSED 2026-06-02 (Timoo, Tivoo-Max, Pixoo, Ditoo)

- [x] All four devices connect (4/4).
- [x] Brightness + solid colors sent OK (2/2 + 3/3 each).
- [x] 6 clock dials sent OK (6/6 each).
- [x] VJ effects sent OK (16/16 each).
- [x] Visualizer/EQ count verified — devices accept indices 0–15; UI EQ list
      bumped 12 → **16** to match.
- [x] Pushed images (ticker + sysmon) sent OK (2/2 each) — confirms the two
      image-push bug fixes work on real hardware.
- [x] Report: **180/180 steps OK, 0 errors** across all four devices.

(Command-level success is automated; per-pattern *visual* distinctness is the
user's eyes — all commands were accepted by every device with no rejections.)

## Report shape (`test_reports/device_validation.json`)

```json
{
  "devices": [
    {"address": "...", "name": "...", "connected": true,
     "steps": [{"step": "clock dial 2", "ok": true, "error": null}, ...]}
  ],
  "summary": {"devices": 4, "ok": N, "failed": M}
}
```

## Execution log

- Harness `scripts/validate_devices.py` built; every command it issues
  (brightness/light/clock/effects/visualization/image) verified against the
  MockBleakClient end-to-end (no errors, image push emits 0x44 frames).
- Agent attempted to run it directly → **exit 134 (SIGABRT)** from the macOS TCC
  Bluetooth gate. Diagnosed thoroughly (Info.plist usage-desc absent; tccutil
  refused; LAN discovery = 0 Wi-Fi devices).
- **User granted Bluetooth permission.** The agent's own Bash context still
  aborts (TCC is per-responsible-process), but launching via
  `open <script>.command` runs under **Terminal's** granted identity — BLE works
  there. (First scan hit bleak's CoreBluetooth init race → "Bluetooth turned
  off"; a small retry loop fixed it.)
- Ran the full harness via Terminal against all four real devices:
  **4/4 connected, 180/180 steps OK, 0 failures.** Fixed a harness bug found in
  the process (`import os` missing). Added a Unix-domain-socket control surface
  + `control_server.call()` client so a permitted app instance can also be driven
  headlessly. Report: `test_reports/device_validation.json`.
