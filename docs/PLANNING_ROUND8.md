# Planning: Round 8 feature excavation — device settings, FM, SD player, scheduler _(2026-06-06)_

> **Input:** "Do another round of feature excavation from the references and the apk."
>
> **Method:** Full inventory of `divoom_lib` public methods (per module) vs. the
> 58 GUI bridge methods (`gui_api.py` + mixins), cross-referenced with
> `apk/APK_INTELLIGENCE_REPORT.md` and the reference repos (`node-divoom-timebox-evo`,
> `fhem-Divoom`, `divoom-ditoo-pro-controller`, `pixoo_spp_reference.py`,
> `divoom-refs`). Kare + Rams lens on the picks. Phase split. **Stop and ask.**

---

## §1 Headline finding

The bottleneck is **not** missing library code — `divoom_lib` already implements
~140 device methods across 30+ modules. The gap is **GUI exposure**: after Rounds
6–7 the GUI surfaces ~58 bridge methods. Whole capability clusters that the
library fully supports (and the references/APK confirm) are still **0% surfaced**.

## §2 Gap list — library has it, GUI does NOT expose it

| Cluster | Library (module → methods) | Refs/APK confirm | Value |
|---|---|---|---|
| **Device Settings** | `system/time.py:set_hour_type` (12/24h); `system/device.py:set_temp_type` (°C/°F), `set_device_name`; `system/date_time.py:update_date_time` (time sync); `system/temp_weather.py:update_temp_weather`; `device_settings.py:set_auto_power_off/set_low_power_switch/set_boot_gif/set_power_on_channel/set_power_on_voice_volume/set_song_display_control/set_sound_control` | APK `SppProc$CMD_TYPE` (0x18,0x2b,0x2c,0x40,0x52,0x75,0x8a,0xab,0xb2…); fhem-Divoom | **HIGH** |
| **FM Radio** | `media/radio.py:set_radio_frequency`; `lan_transport` FM; APK `SPP_GET/SET_FM_CURRENT_FREQ` (96/97), count (100) | APK report §1 | **HIGH** (distinctive; Tivoo/Ditoo have FM) |
| **SD Music player** | `media/music.py`: list/play/pause/next/position/play-mode (12+ methods); volume already exposed | APK `0x06,0x07,0x0a,0x11,0x12,0xb4,0xb8,0xb9` | **MED** (only if SD card used) |
| **Memorial / Anniversary** | `scheduling/alarm.py:get/set_memorial_time,set_memorial_gif` (0x53/0x54/0x55) | APK; hass-divoom | **MED** (bedside feature) |
| **Timeplan / scheduler** | `scheduling/timeplan.py:set_time_manage_info/ctrl` (0x56/0x57) | APK | **MED** (auto channel by time-of-day) |
| **Game / Magic 8-Ball** | `game.py`: show_game, magic_ball_answer, gamecontrol | APK `0x17,0x21,0xa0` | **LOW–MED** (fun, cheap) |
| **Drawing / Sand paint** | `display/drawing.py`: pixel pad, sand paint, movie play (14 methods) | APK `0x35,0x3a,0x3b,0x58,0x5a,0x6b–0x6f` | **LOW** (complex UI) |

(Plus APK-only, no lib yet: screen rotate/mirror & factory reset via 0xBD EXT —
deferred, needs new lib code.)

## §3 Top picks (Kare + Rams)

### Pick 1 — **Device Settings panel** — HIGHEST VALUE
Every device-control app needs basic config. One "Device" card (in the **Tools**
tab or a new "Device" sub-tab): **12/24-hour toggle**, **°C/°F toggle**,
**Sync time now** (push host clock), **device name**, **auto-power-off**,
**screen on/off**. All are simple one-shot set commands — low risk, high
everyday value, fills the most obvious gap. Rams: honest, expected controls.

### Pick 2 — **FM Radio** — HIGH VALUE (distinctive)
A tuner: frequency stepper (87.5–108.0), a few saved presets, on/off. Wraps
`radio.set_radio_frequency`. Fun and unique to a desktop controller. (Gate the
card to devices that have FM — Tivoo/Tivoo-Max/Ditoo.)

### Pick 3 — **Weather push** — MED (cheap, nice)
Push host/online weather to the device's weather widget
(`system/temp_weather.update_temp_weather`). Pairs naturally with the °C/°F
toggle. Small surface.

### Pick 4 — **Memorial / Anniversary** — MED
A date + label that shows a countdown on the device (`set_memorial_time`).
Bedside-clock value; fits alongside Alarms in Tools.

### Pick 5 — **SD Music player** — MED (only if user uses an SD card)
Browse SD tracks + transport (play/pause/next, play-mode) reusing the existing
volume bridge.

## §4 Risk

- Picks 1–4 are mostly one-shot **set** commands → low risk, fire-and-forget
  (no dependence on the broken read-back path, except where a "read current"
  is nice-to-have, which we make optional).
- The **read-back limitation** (queries 0x42/0x46/0x13 time out on hardware,
  see `docs/DEVICE_VALIDATION_PLAN.md`) means "Sync/Read from device" buttons
  can't pre-populate — design these set-oriented, like the Alarms editor.
- FM/SD are device-capability-dependent → gate the cards by device name.

## §6 Phase plan

- **Phase 1 (Round 8):** Device Settings panel (Pick 1) + FM Radio (Pick 2) +
  Weather push (Pick 3). ~bridges + UI in Tools/new Device sub-tab + unit tests.
- **Phase 2 (Round 9):** Memorial/Anniversary + Timeplan scheduler.
- **Phase 3 (later):** SD Music player; Game/Magic-8-Ball; Drawing/Sand;
  APK-only 0xBD EXT (screen rotate/mirror, factory reset — needs new lib code).

## §7 Open questions for the user

Pick the Round 8 scope (defaults: Picks 1–3). See the AskUserQuestion that
accompanies this doc.

## §8 Implementation outcome

_(filled after shipping)_
