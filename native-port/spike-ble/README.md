# divoom-spike-ble — Phase-1 native-port spike

Throwaway proof for `docs/PLANNING_NATIVE_PORT.md` Phase 1. It answers the single
question that gates the whole Rust port:

> Can a **native binary** own a Divoom over BLE on macOS via `btleplug` + `tokio`,
> and does it get the **CoreBluetooth TCC grant** (the thing the Python daemon
> currently needs a signed `.app` for)?

It does one round trip against a real device:

```
scan -> connect -> discover -> subscribe(notify) -> write(0x46 query) -> read reply
```

This is **not** the daemon and shares no code with it. It is deliberately tiny.

## Build

```bash
cd native-port/spike-ble
cargo build --release
```

(First build downloads btleplug + tokio + objc bindings from crates.io.)

## Run — two ways

**A. Quick, from the terminal** (TCC is attributed to your terminal app; macOS
prompts once for Bluetooth, or you grant Terminal/iTerm under System Settings >
Privacy & Security > Bluetooth):

```bash
./target/release/divoom-spike-ble
```

**B. The real test — as a signed `.app`** (attributes the grant to a stable
bundle identity `com.divoom.spikeble`, exactly how the port will ship):

```bash
./make_spike_app.sh
open "dist/Divoom Spike BLE.app"          # macOS prompts for Bluetooth on first run
# the app is LSUIElement (no stdout); run the embedded binary to see logs:
"dist/Divoom Spike BLE.app/Contents/MacOS/divoom-spike-ble"
```

## What success looks like

```
[spike] scanning 5s for a Divoom device...
[spike] found: "Pixoo-1" [<uuid>]
[spike] connecting...
[spike] subscribing to notifications...
[spike] writing 0x46 query (01030046490002) as WithResponse
[spike] awaiting a reply (3s)...
[spike] OK  NOTIFY 49535343-1e4d-4bd9-ba61-23c647249616 -> 0119000446...
[spike] done.
```

- Reaching `connecting...` / `subscribing...` without a SIGKILL is the **TCC win**
  (the Python equivalent crashes with SIGABRT from an un-granted shell — see the
  "Bash can't BLE" note in the session handoff).
- A `0x46` reply confirms the Basic-protocol path end to end. **No reply in 3s is
  still a pass** for a device that only speaks iOS-LE framing — the connect +
  subscribe already prove the BLE+TCC path; the framing autoprobe is Phase 2.

## If it fails

- **SIGKILL / "TCC" / immediate exit** -> the binary did not get the Bluetooth
  grant. Use route B (the `.app`) and check System Settings > Privacy > Bluetooth.
  If even the signed `.app` is denied, that is the finding that must be solved
  before the port proceeds.
- **No adapter** -> Bluetooth is off.
- **Device not found** -> it is connected/owned elsewhere (quit the Python daemon /
  the Divoom phone app), or out of range.

## Notes

- The Divoom GATT UUIDs and the `0x46` Basic frame are lifted verbatim from the
  Python implementation (`divoom_lib/divoom.py`, `divoom_lib/framing.py`) so the
  spike talks to the device identically.
- `target/` is git-ignored; only the source, `Info.plist`, and scripts are tracked.
