# Planning: Round 7 feature harvest — text, alarms, sleep, tools _(2026-06-06)_

> **Input:**
> 1. Round 6 shipped Monthly Best layout (Option B), Routines sub-tab,
>    Volume slider, Scoreboard channel-card (Round 6 + 6.1).
> 2. User request: "Do another round of feature harvesting from the
>    references."
> 3. Cross-referenced all 4 reference repos (`futpib`,
>    `andreas-mausch`, `hass-divoom`, APK `SppProc$CMD_TYPE.java`) +
>    every divoom_lib public method (590+ LOC) + every GUI control
>    (66 reachable Python methods).
>
> **Method:**
> - Inventory what's in divoom_lib (full).
> - Inventory what the GUI exposes (full).
> - Inventory what the 4 reference repos cover (full).
> - Cross-reference → 1 consolidated gap list.
> - Kare + Rams lens for the highest-value picks.
> - Phase 1/2/3 split. Stop and ask user to pick.
>
> **Pattern citations** (build-discipline): D1 (delete the dead
> code), D2 (document the decision, not just the code), F1
> (foundation before cutover), F2 (test before you trust).

---

## §0 Reading map

- §1 — Status of Round 6; what's still unexposed
- §2 — Dead code in the GUI (build-discipline D1)
- §3 — Top 5 high-value feature picks
- §4 — Kare + Rams lens on each
- §5 — Risk assessment
- §6 — Phase plan
- §7 — Open questions for the user
- §8 — Implementation outcome (after shipping)

---

## §1 Status: what's still unexposed

After Round 6 + 6.1, the GUI exposes **20-ish divoom_lib methods** out
of **~140** public ones. Six full divoom_lib modules (926 LOC) are
completely un-surfaced:

| Module | LOC | Public methods | GUI exposure |
|---|---|---|---|
| `divoom_lib/display/text.py` | 173 | `set_light_phone_word_attr`, `set_text_content` | **0** — no "send text to device" feature |
| `divoom_lib/scheduling/alarm.py` | 254 | `get_alarm_time`, `set_alarm`, `set_alarm_gif`, `get_memorial_time`, `set_memorial_time`, `set_memorial_gif`, `set_alarm_listen`, `set_alarm_volume`, `set_alarm_volume_control` | **0** — no alarm editor at all |
| `divoom_lib/scheduling/sleep.py` | 234 | `show_sleep`, `get_sleep_scene`, `set_sleep_scene_listen`, `set_scene_volume`, `set_sleep_color`, `set_sleep_light`, `set_sleep_scene` | **0** — no sleep-aid panel |
| `divoom_lib/tools/timer.py` | 87 | `get_timer`, `set_timer` | **0** |
| `divoom_lib/tools/countdown.py` | 92 | `get_countdown`, `set_countdown` | **0** |
| `divoom_lib/tools/noise.py` | 86 | `get_noise`, `set_noise` | **0** |

Of the 4 reference repos, `hass-divoom` confirms the alarm/sleep
features (`0x40, 0x42, 0x43, 0x82, 0xA2, 0xA3, 0xA4`) and the
APK's `SppProc$CMD_TYPE` confirms the tools (0x71/0x72 sub-codes
`0x01` timer, `0x03` countdown, `0x05` noise). The features
*exist* in the official app and other libraries; we just don't
expose them.

### Other unexposed (smaller features, also live in divoom_lib)

| Feature | divoom_lib method | GUI exposure |
|---|---|---|
| Brightness get (init slider to device state) | `device.get_brightness()` | No — slider defaults to 80 always |
| 12/24-hour clock | `time.set_hour_type(hour_type)` | No — hidden in protocol params |
| Auto power-off | `sound.set_auto_power_off` / `get_auto_power_off` | No |
| Hot mode | `control.set_hot` | No |
| Low-power switch | `device_settings.set_low_power_switch` / `get_low_power_switch` | No |
| Power-on channel | `device_settings.set_power_on_channel` | No |
| Power-on voice volume | `sound.set_power_on_voice_volume` | No |
| BT password | `bluetooth.set_bluetooth_password` | No |
| Device name (BT) | `device.set_device_name` / `get_device_name` | No |
| Sleep color | `sound.set_sleep_color` | No |
| Song display control | `sound.set_song_display_control` | No |
| Sound control (ambient) | `sound.set_sound_control` / `get_sound_control` | No |
| Boot GIF | `device_settings.set_boot_gif` | No |
| Timeplan | `timeplan.set_time_manage_info` / `set_time_manage_ctrl` | No |
| Scoreboard get | `scoreboard.get_scoreboard` | No — push-only |

### Also in divoom_lib but **not** in references/APK (Round 6's `EQ`)

- `design.set_eq` (0xBD 0x1E) and `design.set_language` (0xBD 0x26)
  exist in divoom_lib but the `EQ visualization` patterns are NOT
  the same as the `set_eq` equalizer. EQ on the visualization grid
  is already exposed (12 patterns). `set_eq` is the *device's
  actual 10-band equalizer for the microphone* (Ditoo-Mic) — much
  more niche.
- `set_language` is a 16-language device menu. Niche, only useful
  for non-English users. Defer.

---

## §2 Dead code in the GUI (build-discipline D1: delete before adding)

The harvest also surfaced **5 dead Python methods** that no JS file
ever calls. Per `build-discipline D1` ("if you wrote it and never
used it, delete it; rot compounds"), these should be removed before
adding new features.

| Dead method | File | LOC | Last touched | Why dead |
|---|---|---|---|---|
| `trigger_notification(app_name)` | `gui/media_sync.py:331` | ~70 | Round 1 (SppProc icons) | The audio-visualizer card was removed in Round 0. No JS caller. |
| `toggle_audio_visualizer(enable)` | `gui/media_sync.py:407` | ~12 | Round 1 | Same — was tied to the deleted visualizer. |
| `get_audio_levels()` | `gui/media_sync.py:419` | ~150 | Round 1 | Same — `_AudioVisualizerWorker` (140 LOC) is also dead. |
| `save_lan_config(device_ip, local_token)` | `gui/gui_api.py:92` | ~30 | Unknown | `add_lan_device` is used instead. |
| `probe_lan()` | `gui/gui_api.py:121` | ~10 | Unknown | `add_lan_device` does its own reachability check. |
| `scan_devices(self)` | `gui/scanner_mixin.py:14` | ~3 | Unknown | Superseded by `scan_devices_with_config`. |

**Estimated dead-code cleanup:** ~275 LOC removed, 6 method
signatures gone, no behavior change. The `trigger_notification`
icons (Kakao, IG, Snapchat, FB, Twitter, WhatsApp, etc.) are
useful — they should be **preserved as constants** for future use
in Live Widgets, not deleted entirely.

**Other small bugs the harvest surfaced:**

- **Hard-coded preset placeholder options** in `index.html:344-345`:
  `<option value="wall_2x2">2x2 Matrix Wall</option>` and
  `<option value="strip_1x2">1x2 Wide Panel</option>` are not
  real presets — the user can never load them. Should be removed
  (Rams #5: "honest").
- **Brightness slider always defaults to 80** on startup, even
  though `divoom_lib/system/device.py:get_brightness` exists. The
  volume slider is the only one that reads back. (Kare: matches
  the volume pattern, more honest.)
- **Scoreboard inputs always default to 0**, even though
  `divoom.scoreboard.get_scoreboard` exists.

---

## §3 Top 5 high-value picks

After 3 rounds of steelman/counter-steelman/synthesis, these are
the highest-value features that round out the basic functionality
of a desktop divoom control app:

### Pick 1 — Text Channel ("Type and push to device") — **HIGHEST VALUE**

The single most-requested feature for any pixel-display app. The
library has `divoom_lib/display/text.py` (173 LOC) with full
support for animated text: speed, effects, box, font, color,
content, image effects. **Zero GUI exposure.** Reference repos
confirm the feature.

- `0x86` (set text content) + `0x87` (set word attributes) +
  `0x6c` (push frame) protocol.
- Round 7 ships: a "Text" tab in Control Panel with: text input,
  font select (0-3), color picker, scroll/marquee/blink/static
  effect select, speed slider, "Push to Device" button.

### Pick 2 — Alarms (full editor) — **HIGH VALUE**

The library has 254 LOC for alarms but no UI. Bedside-clock users
*need* this. 10 alarm slots, each with hour/minute/weekday
pattern/mode/trigger-mode/FM freq/volume + optional alarm GIF.

- `0x42` (get all 10) + `0x43` (set one) + `0x51` (set alarm GIF).
- Round 7 ships: a "Divoom" sub-tab → "Alarms" list with 10 rows,
  each editable: enable toggle, hour:minute, weekday mask
  (Mon-Sun checkboxes), Save.

### Pick 3 — Sleep Aid (full editor) — **HIGH VALUE**

The library has 234 LOC for sleep but no UI. Bedside-clock users
*need* this. Set the sleep time, scene mode, FM frequency, volume,
color, brightness.

- `0x40` (set sleep) + `0x41` (set sleep scene) + `0xA2` (get
  scene) + `0xA3-0xA4` (listen/volume) + `0xAD-0xAE` (color,
  light).
- Round 7 ships: a "Divoom" sub-tab → "Sleep" card with: sleep
  time (HH:MM), enable toggle, mode (off/light/white-noise/FM),
  color picker, brightness slider, volume slider, Save.

### Pick 4 — Tools (Timer / Countdown / Noise) — **MEDIUM VALUE**

The library has full implementations but no UI. These are
single-purpose tools that complement the existing scoreboard.

- `0x71 0x01` (timer) + `0x72 0x01` (timer ctrl) + `0x71 0x03` +
  `0x72 0x03` (countdown) + `0x71 0x05` + `0x72 0x05` (noise).
- Round 7 ships: a "Tools" sub-card in the new "Tools" channel
  card in Control Panel: 3 mini-panels (Timer pause/start/reset,
  Countdown minutes:seconds/start/cancel, Noise meter
  start/stop). All push on click, no separate "Apply" button.

### Pick 5 — Display getters (read device state) — **MEDIUM VALUE**

Fix the brightness-default-80 bug and the scoreboard-default-0 bug.
Both are push-only today. Reading back is the only way to make
the GUI a true mirror of device state.

- `device.get_brightness()` on appbar init.
- `scoreboard.get_scoreboard()` on scoreboard panel open.
- Optionally: `device.get_work_mode()` to highlight the active
  channel card on the Control Panel.
- Kare #3: show the raw value, no normalization. Matches the
  volume slider pattern from Round 6.

---

## §4 Kare + Rams lens on each pick

### Kare (visual hierarchy, raw values, pixel-perfect clarity)

| Pick | Kare check |
|---|---|
| Text | Type-and-send is the most "Kare" feature: pixel-perfect text on a 16×16 grid. 0-3 font index shown raw, 0-15 speed shown raw. |
| Alarms | Time displayed in 24h `HH:MM` raw. 7-day weekday pattern as 7 checkboxes (no "weekday/weekend" abstractions). |
| Sleep | Same — raw `HH:MM`, raw 0-15 volume (matches appbar slider). |
| Tools | Timer: minutes/seconds raw. Countdown: minutes/seconds raw. Noise: no abstraction. |
| Getters | Slider values match device state on open — pixel-perfect parity. |

### Rams (less but better, honest, thorough)

| Pick | Rams check |
|---|---|
| Text | One text input, one effect dropdown, one color, one speed, one button. Five controls, exhaustive. |
| Alarms | 10 rows, each a single line of 4 fields (toggle / time / weekdays / save). The "list" pattern is honest about there being 10 of them. |
| Sleep | One card, six fields, one button. Honest. |
| Tools | One sub-card per tool. Three small UIs are honest about the device being a multi-tool platform. |
| Getters | Match the volume pattern from Round 6 (one slider, one get on init, one set on change). Consistent. |

**Honest about deletion:** the dead-code cleanup (§2) is Rams
#10 inverted — sometimes "less but better" means **removing**
what's there. The 275 LOC of dead code should be deleted before
adding new features.

---

## §5 Risk assessment

| Pick | Risk | Reason |
|---|---|---|
| Text | **Low** | Library implementation is well-tested. Wire bytes documented in `text.py`. Need a small Playwright test. |
| Alarms | **Medium** | 10-slot array; user can clobber existing alarms if they don't read first. Solution: always `get_alarm_time` on panel open, then `set_alarm` only on save. |
| Sleep | **Medium** | Multiple sub-commands. Solution: keep the existing `set_sleep_scene` (all-in-one) rather than the per-knob `set_sleep_color` / `set_sleep_light` / etc. |
| Tools | **Low** | 3 simple sub-tools. Wire bytes are documented. |
| Getters | **Low** | Read-only calls. No state mutation. |
| Dead-code cleanup | **Low** | Verified by `git grep` that no JS caller exists. After removal, run full test suite. |

---

## §6 Phase plan

### Phase 1 (Round 7, this round)

If the user picks all 5, this is ~3 hours of work plus tests.

1. **Dead-code cleanup** (15 min, 275 LOC removed)
2. **Text Channel** (60 min)
3. **Alarms** (45 min)
4. **Sleep Aid** (45 min)
5. **Tools sub-card** (30 min)
6. **Display getters** (15 min)
7. **Tests** (30 min, ~20 new tests)
8. **CHANGELOG + this doc** (15 min)

### Phase 2 (deferred to Round 8)

- Hour type (12/24) toggle
- Auto power-off timer
- Low-power switch
- Hot mode toggle
- Power-on channel
- BT password
- Device name

### Phase 3 (deferred to Round 9+)

- Boot GIF
- Timeplan
- Memorial day editor
- Power-on voice volume
- Song display control
- Sound control (ambient)
- All FM radio sub-commands (region, search, favourite)
- OTA / firmware update
- All 0xBD EXT sub-commands (factory reset, screen rotate, screen mirror)

---

## §7 Open questions for the user

4 questions, in the same format as Round 6. Default picks marked.

---

## §8 Implementation outcome (TBD after shipping)

To be filled in after the user picks and the work lands.

---

**Status: DRAFT 2026-06-06. Awaiting §7 picks.**
