# Round 49 — Native Port Scheduling Commands

**Agent**: Gemini (Antigravity)  
**Date**: 2026-06-23

## Outcome / what shipped

Implemented all alarm, sleep, and timeplan scheduling commands in the native Rust daemon (`divoomd`) to expand the supported command surface:

1. **Alarm**:
   - Ported `"alarm.get_alarm_time"`, `"get_alarm_time"`, `"alarm.set_alarm"`, `"set_alarm"`, `"alarm.set_alarm_gif"`, `"set_alarm_gif"`, `"alarm.get_memorial_time"`, `"get_memorial_time"`, `"alarm.set_memorial_time"`, `"set_memorial_time"`, `"alarm.set_memorial_gif"`, `"set_memorial_gif"`, `"alarm.set_alarm_listen"`, `"set_alarm_listen"`, `"alarm.set_alarm_volume"`, `"set_alarm_volume"`, `"alarm.set_alarm_volume_control"`, `"set_alarm_volume_control"`.
   - Correctly deserialized and parsed 10-byte alarm info blocks and 39-byte memorial info blocks from the device's query responses (command codes `0x42` and `0x53` respectively).

2. **Sleep**:
   - Ported `"sleep.show_sleep"`, `"show_sleep"`, `"sleep.get_sleep_scene"`, `"get_sleep_scene"`, `"sleep.set_sleep_scene_listen"`, `"set_sleep_scene_listen"`, `"sleep.set_scene_volume"`, `"set_scene_volume"`, `"sleep.set_sleep_color"`, `"set_sleep_color"`, `"sleep.set_sleep_light"`, `"set_sleep_light"`, `"sleep.set_sleep_scene"`, `"set_sleep_scene"`.
   - Correctly deserialized and parsed 10-byte sleep scene status blocks from `0xa2` responses.

3. **Timeplan**:
   - Ported `"timeplan.set_time_manage_info"`, `"set_time_manage_info"`, `"timeplan.set_time_manage_ctrl"`, `"set_time_manage_ctrl"`.
   - Mapped to command codes `0x56` (info) and `0x57` (control) respectively.

4. **Integration & Parity Tests**:
   - Updated the `ported_commands_route_to_device_call` integration test in `tests/daemon_behavior.rs` to verify that all newly implemented commands and their aliases correctly match in the router and dispatch to the device transport.
   - Verified that the new commands compile and pass tests successfully with and without the `ble` feature gate.
   - Verified that the full Python pytest suite passed completely without regressions (1706 passed, 87 skipped).

## Open / deferred

- Porting macOS notification monitor / SQLite reader.
- Porting live widget loops (sysmon, weather, stock, etc.).
- Porting LAN transport validation.
