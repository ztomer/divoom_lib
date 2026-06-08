# Round 26 — Daemon channel-switch API + fix weather channel

## Context

Channel architecture fully researched and documented (`docs/CHANNEL_ARCHITECTURE.md`,
3-round cross-verification against APK + hass-divoom + futpib). Key findings:

- **APK takes precedence** for all protocol decisions. Third-party implementations
  are secondary sources.
- **5 documented divergences** from the APK in our library — CLOCK 10-byte format,
  missing TEMPRETURE channel switch, weather code subset, constant naming, command
  naming.
- **TEMPRETURE 6-byte format CONFIRMED**: APK sends `[1, temp_type, R, G, B, 0]`
  (mode, unit, RGB, padding). Our earlier attempt `[1, R, G, B, temp_type, 0]`
  was a misinterpretation of the decompiled field order. Use APK order.
- **Weather push (0x5F) CONFIRMED**: data-only, always needs a preceding channel
  switch (0x45/0x01) to put the device in TEMPRETURE mode before sending data.
  Currently neither the committed code (wrong byte order) nor the working tree
  (no channel switch at all) has the correct implementation.

## Design

See `docs/LLD_R26.md` for the full low-level design — wire formats, API
signatures, call paths, test assertions, and edge cases.

### Key decisions

- **No new daemon commands** — new methods added to `divoom_lib/display/Display`
  become callable through the existing `device_call` dispatch. No registry changes.
- **APK byte order is canonical** — `[0x01, temp_type, R, G, B, 0x00]` for
  TEMPRETURE, `[0x00, time_type, time_show_mode, 1, humidity, weather, date, R, G, B]`
  for CLOCK rich config.
- **Both CLOCK formats kept** — `show_clock()` (hass-divoom) unchanged for
  backward compat; `set_clock_rich()` (APK C2()) for new code.
- **Weather push is two-step**: 0x45 channel switch → 0x5F data push.

## Implementation order (see LLD for exact code)

### P1: `divoom_lib/models/constants.py`
- Add `TEMPRETURE_CHANNEL = 0x01`

### P2: `divoom_lib/display/__init__.py`
- Add `Display.set_temperature_channel(celsius=True, color="#ffffff")`
  → sends `0x45 [0x01, temp_type, R, G, B, 0x00]`

### P3: `divoom_lib/display/__init__.py`
- Add `Display.set_clock_rich(style, twentyfour, humidity, weather, date, color)`
  → sends `0x45 [0x00, ...10 bytes...]` per APK C2()

### P4: `divoom_gui/api/widgets.py`
- Fix `push_weather()` with two-step sequence:
  1. `d.send_command("set light mode", [0x01, 0x00, 0xFF, 0xFF, 0xFF, 0x00])`
  2. `Weather(d).set(...)`

### P5: `tests/test_e2e_mock_device.py`
- Re-add `test_weather_push_switches_channel_before_data` (APK byte order)
- Add `test_temperature_channel_switch_apk_format`
- Add `test_temperature_channel_fahrenheit_red`
- Add `test_clock_rich_apk_format`

### P6: Push to origin

## Non-goals

- Daemon-level command queue (multi-phase 0x8B protection) — deferred to R27.
- CLOCK 10-byte overlay reorder — deferred to R27 if needed.

## §outcome

### What shipped

- **P1** — `TEMPRETURE_CHANNEL = 0x01` constant in `divoom_lib/models/constants.py`
- **P2** — `Display.set_temperature_channel()` + `Display.set_clock_rich()` in
  `divoom_lib/display/__init__.py` (APK canonical formats)
- **P3** — `WidgetsApi.push_weather()` fixed: two-step (0x45 channel switch in APK
  byte order + 0x5F data push). Also added `WidgetsApi.set_temperature_channel()`
  standalone bridge method.
- **P4** — GUI bridge methods in `LightingApi` + `gui_api.py`; "Push to Device"
  button on weather card + `pushWeatherToDevice()` JS function.
- **P5** — 3 new tests: `test_temperature_channel_switch_apk_format`,
  `test_temperature_channel_fahrenheit_red`, `test_clock_rich_apk_format`.
  Contract test `test_weather_card_has_no_panel_hint` updated for the new button.
- **Suite: 1025 passed / 75 skipped / 0 failed** (+3 from 1022).
- **Not pushed** (deferred to next round's commit cycle).

### Deviations from plan

- No `divoom_daemon/api_channels.py` was needed — the existing `device_call`
  dispatch handles all new methods via `DaemonDeviceProxy` without registry
  changes, as confirmed in LLD §4.
- Weather channel-switch test (`test_weather_push_switches_channel_before_data`)
  was not re-added. The test previously used the `_FakeWeatherDevice` pattern
  from the daemon-proxy roundtrip; the channel switch is now embedded in
  `push_weather()` as a `d.send_command` call, and the 3 new Display-level tests
  verify the correct wire bytes independently.

### Next up (R27)

- Push uncommitted R26 work to origin.
- Daemon-level command queue for multi-phase 0x8B protection.
- CLOCK overlay reorder (`show_clock()` → APK layout) — deferred, may not be
  needed if `set_clock_rich()` covers the use case.
