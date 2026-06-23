# Round 48 — Native Port Tool & Notification Commands

**Agent**: Gemini (Antigravity)  
**Date**: 2026-06-23

## Outcome / what shipped

Implemented device tool and notification commands in the native Rust daemon (`divoomd`) to expand the supported command surface:

1. **Scoreboard**:
   - Ported `"scoreboard.set_scoreboard"`, `"set_scoreboard"`, `"scoreboard.get_scoreboard"`, `"get_scoreboard"`.
   - Mapped to command codes `0x72` (set tool) with type `1`, and `0x71` (get tool) with type `1`.

2. **Timer**:
   - Ported `"timer.set_timer"`, `"set_timer"`, `"timer.get_timer"`, `"get_timer"`.
   - Mapped to command codes `0x72` (set tool) with type `0`, and `0x71` (get tool) with type `0`.

3. **Countdown**:
   - Ported `"countdown.set_countdown"`, `"set_countdown"`, `"countdown.get_countdown"`, `"get_countdown"`.
   - Mapped to command codes `0x72` (set tool) with type `3`, and `0x71` (get tool) with type `3`.

4. **Noise Meter**:
   - Ported `"noise.set_noise"`, `"set_noise"`, `"noise.get_noise"`, `"get_noise"`.
   - Mapped to command codes `0x72` (set tool) with type `2`, and `0x71` (get tool) with type `2`.

5. **Notification Display**:
   - Ported `"device.show_notification"`, `"show_notification"`, `"notification.show_notification"`, `"device.show_notification_text"`, `"show_notification_text"`, `"notification.show_notification_text"`.
   - Mapped to command code `0x50` using proper icon-only or icon-with-text payload structure based on the parameters.

6. **Integration & Parity Tests**:
   - Updated `ported_commands_route_to_device_call` test in `tests/daemon_behavior.rs` to verify that calls to all newly implemented commands and their aliases are correctly matched in the router and dispatch to the device transport (failing honestly with "no device connected").
   - Verified that the new commands compile and pass tests successfully with and without the `ble` feature gate.

## Open / deferred

- Porting macOS notification monitor / SQLite reader.
- Porting live widget loops (sysmon, weather, stock, etc.).
- Porting LAN transport validation.
