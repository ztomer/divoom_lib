# Round 47 — Native Port Remaining Device Call Commands

**Agent**: Gemini (Antigravity)  
**Date**: 2026-06-23

## Outcome / what shipped

Implemented remaining `device_call` commands in the native Rust daemon (`divoomd`) to expand the supported command surface:

1. **Volume Control**:
   - Ported `"music.get_volume"`, `"get_volume"`, `"music.set_volume"`, `"set_volume"`.
   - Mapped to command codes `0x08` (set) and `0x09` (get).

2. **FM Radio**:
   - Ported `"radio.set_radio_frequency"`, `"set_radio_frequency"`, `"radio.set_radio"`, `"set_radio"`.
   - Mapped to command code `0x61` (set radio frequency) taking 2 bytes little-endian frequency.

3. **Low Power Switch**:
   - Ported `"device.get_low_power_switch"`, `"get_low_power_switch"`, `"device.get_low_power"`, `"get_low_power"`, `"device.set_low_power_switch"`, `"set_low_power_switch"`, `"device.set_low_power"`, `"set_low_power"`.
   - Mapped to command codes `0xb2` (set) and `0xb3` (get).

4. **Auto Power Off**:
   - Ported `"device.get_auto_power_off"`, `"get_auto_power_off"`, `"sound.get_auto_power_off"`, `"device.set_auto_power_off"`, `"set_auto_power_off"`, `"sound.set_auto_power_off"`.
   - Mapped to command codes `0xab` (set) and `0xac` (get).

5. **Integration & Parity Tests**:
   - Added `ported_commands_route_to_device_call` test to `tests/daemon_behavior.rs` to verify that calls to all newly implemented commands are correctly matched in the router and dispatch to the device transport (failing honestly with "no device connected").
   - Verified that the new commands compile and pass tests successfully with and without the `ble` feature gate.

## Open / deferred

- Porting macOS notification monitor / SQLite reader.
- Porting live widget loops (sysmon, weather, stock, etc.).
- Porting LAN transport validation.
