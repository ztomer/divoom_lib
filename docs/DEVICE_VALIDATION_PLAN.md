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

## Acceptance

- [ ] All four devices connect.
- [ ] Brightness + solid colors visibly change.
- [ ] 6 clock dials render distinctly.
- [ ] VJ effects animate (≥ most of 0–15).
- [ ] Real visualizer/EQ count recorded; UI list updated to match.
- [ ] A pushed image (ticker/sysmon) actually displays on the matrix.
- [ ] Report shows 0 command-level errors (or each error is understood + fixed).

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
  Bluetooth gate, as expected. **Handed off to the user to run from their
  terminal.** Awaiting `test_reports/device_validation.json`.
