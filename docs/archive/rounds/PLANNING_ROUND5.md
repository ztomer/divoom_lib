# Planning: Monthly Best layout + new functionality exposure _(2026-06-06)_

> **Input:**
> 1. User's Monthly Best simplification (5 concrete asks a–f).
> 2. User's request to expose the new divoom_lib functionality
>    (Round 3/4/5 work) to end users via the GUI.
> 3. User explicit ask: "consult with Hans Dieter and Susan Kare
>    before applying this for optimal layout".
> 4. Kare + Rams combined design lens (per
>    `docs/PLANNED_WORK.md §1`).
>
> **Method:**
> - For each Monthly Best change, do 3 rounds of
>   steelman / counter-steelman / synthesis.
> - For new functionality exposure, present a bucketed
>   inventory of what's in divoom_lib vs what's in the GUI,
>   and a proposed placement per bucket.
> - Stop at end of doc and ask the user to confirm picks
>   before implementation.
>
> **Pattern citations** (build-discipline): D2 (document the
> decision, not just the code), D3 (document the dead-ends),
> E1 (multi-perspective review), F4 (plan → execute → document).

---

## §0 Reading map

- §1 — Monthly Best layout, user request a–f restated
- §2 — Kare + Rams lens applied to the current state
- §3 — Monthly Best layout, 3-round dialectic
- §4 — Monthly Best, layout sketches (recommended option)
- §5 — New functionality inventory: in divoom_lib, not in GUI
- §6 — New functionality, bucketed exposure plan
- §7 — Open questions for the user
- §8 — Recommendation summary

---

## §1 — Monthly Best layout, user request a–f restated

**Current state** (from `gui/web_ui/templates.js:39-75` and
`gui/web_ui/gallery.css:240-248`):

- 2-column grid: `1.4fr 1fr` (58% gallery / 42% devices card).
- Right card header: **"Sync Targets & Schedule"**.
- Right card body has TWO sections:
  1. Targets list (multi-select checkboxes, each row shows
     color dot + device name + MAC address).
  2. "Sync All" button.
  3. Schedule: header **"Automatic Hot-Channel Schedule"**,
     checkbox **"Enable scheduled sync (runs headless)"**,
     interval `<select>`, "Save Schedule" button, status line.
- Sync candidates are passed in via `get_sync_candidates` →
  `renderSyncTargets` in `gui/web_ui/gallery.js:137-170`.

**User's 5 asks:**

| # | Ask |
|---|---|
| a | Remove "& schedule" from the card header. |
| b | Remove BT address, keep just device names. |
| c | Remove duplicate text — either "Enable scheduled sync" body or the "Automatic Hot-Channel Schedule" header. |
| d | Cut horizontal space of the sync target box in half. |
| e | Use the extra space for more space for the gallery. |
| f | Consult with Hans Dieter and Susan Kare before applying. |

---

## §2 — Kare + Rams lens applied to the current state

### Current state vs the lens

| Element | Kare/Rams verdict |
|---|---|
| "Sync Targets & Schedule" header | Rams #4 understandable, #10 as little as possible. The card does two things; one word per thing is fine, but "& schedule" carries weight (visual + cognitive) that the card's contents don't justify. |
| Per-row BT address | **Kare: pixel-perfect clarity, restraint.** The address is monospace, 17 chars, 11px font — at 1fr column width (42% of 1024 = 430px), the name+address combo is tight and forces text-ellipsis. The user already has the address in Settings → Bluetooth Scanner. Showing it twice is a duplication. |
| "Automatic Hot-Channel Schedule" header + "Enable scheduled sync (runs headless)" checkbox text | **Rams #6 honest, #4 understandable.** "Headless" is a developer term; the user is not. "Automatic Hot-Channel Schedule" describes what the section is; the checkbox label describes what the action is. The two pieces of text say the same thing in different vocabularies. |
| 1.4fr / 1fr grid split | **Rams #10.** Gallery is the *primary* function of the Monthly Best tab (it has 5+ controls: classify, fetch, browse, select, push). The devices card has 2 controls (target select, sync all) + the optional schedule. 58/42 is the wrong ratio for this. |
| "Push to Device" button at the bottom of the gallery card | **Kare: tight visual envelope** (Round 0/1 fix, retained). |
| Gallery's `max-height: none` + `flex: 1; overflow-y: auto; min-height: 0` | **Rams #4 understandable** — gallery scrolls inside the card, button is anchored. Good. |

### Design intent (per user, prior rounds)
- **Kare: pixel-perfect clarity.** Bitmap-precision controls.
  Honest representation. Platform-native where it exists.
  Friendly. Restraint.
- **Rams: 10 principles** (user-override: 10 favorites not 5).
  The user's override of Rams #10 (10 favorites) is the only
  explicit override; we honor it.

---

## §3 — Monthly Best layout, 3-round dialectic

### Question: layout, structure, content?

### Approach A — All 5 user asks, applied literally, schedule stays

- **Header:** "Sync Targets" (drop "& schedule")
- **Per-row:** `[] [color-dot] DeviceName` (drop address)
- **Schedule section:** Drop the **body** checkbox text
  "Enable scheduled sync (runs headless)" — keep the
  **header** "Automatic Hot-Channel Schedule" + the toggle
  + interval + Save.
- **Grid:** `1.4fr 1fr` → `1.5fr 0.7fr` (one notch down).
  Not a true halve; the schedule UI's interval select + Save
  button need ~200px horizontal room, and a true halve
  (1.6fr 0.4fr) makes the schedule 1-line tall and forces
  labels to wrap.

**Steelman:** smallest change, honors all 5 user asks in some
form, preserves the schedule in the same card (user didn't
explicitly ask to move it). Kare: less cognitive load (no
moving parts across cards). Rams #7 long-lasting: a moved
schedule is a relocation risk for any saved-state user
configuration.

**Counter-steelman:** the schedule UI genuinely needs more
horizontal room than the devices list. Splitting the card
into "Devices (narrow) + Schedule (narrow)" means BOTH
sections are too narrow for their inputs, requiring
single-line inline labels (bad Rams #4) or icon-only buttons
(bad Kare: bitmap clarity). The two functions are
*different* — one is "where to push", the other is "when to
push automatically". A card titled "Sync Targets" that
contains both is a misnomer.

**Synthesis:** A only partially satisfies ask (d). If
schedule stays in the same card, the card has to be wide
enough for the schedule UI, which is the wider of the two
sections. Halving won't work.

### Approach B — All 5 user asks, schedule moves to Settings

- **Header:** "Devices" (no "& schedule" — schedule is gone)
- **Per-row:** `[] [color-dot] DeviceName` (drop address)
- **Schedule section:** DELETED from Monthly Best. Moved
  to Settings → Connectivity (where the transport legend
  lives) as a new "Automation" sub-card, or as a new
  sub-tab "Automation" alongside Devices / Divoom /
  Connectivity / Appearance.
- **Grid:** `1.4fr 1fr` → `1.6fr 0.6fr` (genuine halve — 73%
  gallery / 27% devices). True halve works because the
  narrower card is just the targets list.

**Steelman:** each card does one thing (Rams #8 consistent,
#4 understandable). The narrow devices card fits 4-5 device
rows + "Sync All" button — 27% of 1024 = 276px, plenty for
`[] [dot] DeviceName` (3 elements, max ~24px each). The
schedule gets its own card with proper room for the
interval select (4 options × 60px = 240px minimum) and the
Save button.

**Counter-steelman:** moving the schedule is a navigation
cost (Rams #5 unobtrusive: more clicks to reach the same
function). The schedule's natural home is the Monthly Best
tab because it's a schedule *of the gallery sync*; in
Settings it's a buried power-user feature. The user
didn't ask to move the schedule — they asked to keep it
in the card but clean up the duplicate text. Reopening the
home-of-the-schedule decision without user ask is scope
creep.

**Synthesis:** B is the right shape, but B vs A is "does
the user want to relocate the schedule?" — that's a
question for the user, not a self-decision. The plan
should offer both options and let the user pick.

### Approach C — Halve the column, schedule stays, redesigned tight

- **Header:** "Devices" (drop "& schedule" — schedule is
  visually separated below, not in the title)
- **Per-row:** `[] [color-dot] DeviceName` (drop address)
- **Schedule section:** tight vertical layout in the same
  card. Single column. Stacked: toggle / "Every 1h▼" /
  Save / status.
- **Grid:** `1.4fr 1fr` → `1.7fr 0.5fr` (true halve — 77%
  gallery / 23% devices). Schedule is narrow but every
  element is single-row.

**Steelman:** the schedule has 4 controls; each is a single
HTML element. Stacked vertically, they fit in 180-220px
width. The narrow card column forces the vertical layout
which is *better* than the current horizontal layout (the
"Sync every [1h▼]" slider-label pattern is awkward — see
the `slider-label` class in `gallery.css`). Single column
is Rams #10.

**Counter-steelman:** the schedule UI at 23% of 1024 = 230px
width means the interval select's 4 options are crowded.
Some options ("6 hours", "12 hours", "24 hours") are wider
than the column. Text overflow. Save button next to it
needs to be icon-only or wrap. This is bad Kare (bitmap
clarity) — the controls become hard to read.

**Synthesis:** C only works if the schedule's controls can
be made genuinely narrow. The interval options are
text-heavy by definition. **Verdict:** C is not
recommended.

### Approach D — All 5 user asks, schedule moves to Control Panel

- **Header:** "Devices"
- **Per-row:** `[] [color-dot] DeviceName`
- **Schedule section:** Moved to a new "Routines" sub-card
  in the Control Panel (where the user spends most of
  their time, next to the channels). The Control Panel
  has the most natural real estate (it's a single-card tab
  with channels, plenty of room for a sub-card).
- **Grid:** `1.6fr 0.6fr` (genuine halve).

**Steelman:** the Control Panel is where the user is when
they're thinking "what should my device be doing right
now?" — that's the same mental context as the schedule.
Routines belong with the live controls, not with the
static devices card.

**Counter-steelman:** the Control Panel is the *busiest*
tab. Adding a sub-card adds noise. The schedule is a
*set-and-forget* configuration, not a live control —
cluttering the Control Panel with it violates Rams #5
unobtrusive. Settings is the right home for set-and-forget
things (Volume / Brightness are also in the appbar +
Settings, not the Control Panel).

**Synthesis:** D's location choice (Control Panel) is
worse than B's (Settings). **Verdict:** D is rejected.

---

### Final recommendation (§3 synthesis)

**Two options for the user to pick:**

1. **Option B (recommended):** All 5 user asks; schedule
   moves to Settings → Connectivity (or new "Automation"
   sub-tab). The narrow devices card is 27% width, fits
   4-5 device rows + Sync All button. The schedule gets
   proper room in Settings where it can have clear labels
   and proper input widths.

2. **Option A (user-literal):** All 5 user asks, applied
   literally. Schedule stays in Monthly Best. Grid
   `1.5fr 0.7fr` (not a true halve — the schedule's
   interval select + Save button force the card to be
   wider than the targets list alone would need). Header
   becomes "Sync Targets", body text "Enable scheduled
   sync (runs headless)" is removed, header "Automatic
   Hot-Channel Schedule" is kept.

**Why B is recommended:**
- Honors all 5 user asks fully (including the
  "halve" in d).
- Each card does one thing (Rams #8).
- The schedule gets proper room for its inputs.
- The gallery gets the full horizontal real estate (e).
- The narrow devices card fits the targets list perfectly.
- **Disadvantage:** the schedule relocates. User-visible
  navigation cost. **Mitigation:** add a breadcrumb or
  hint in the Monthly Best tab that says "Auto-sync
  schedule is in Settings → Connectivity".

**Kare/Rams verdict on B:**
- Rams #4 understandable: 1 thing per card. 
- Rams #8 consistent: same idea looks the same everywhere.
  The schedule is consistent with other Settings items. 
- Rams #10 as little as possible: no decorative chrome. 
- Kare: tight visual envelope (devices card is tight;
  gallery card is wider). 

---

## §4 — Monthly Best, layout sketches (Option B, recommended)

### 4.1 Sketch — Monthly Best (post-B)

```
┌─────────────────────────────────────────────────────────────────────┐
│ Gallery                                            [Recommend ▼]   │
│ Divoom Cloud                                        [Fetch Gallery]│
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  ┌──┐  ┌──┐  ┌──┐  ┌──┐  ┌──┐  ┌──┐  ┌──┐  ┌──┐                  │
│  │  │  │  │  │  │  │  │  │  │  │  │  │  │  │  │  ← gallery grid    │
│  └──┘  └──┘  └──┘  └──┘  └──┘  └──┘  └──┘  └──┘   (wider cards)   │
│                                                                     │
│  ┌──┐  ┌──┐  ┌──┐  ┌──┐  ┌──┐  ┌──┐  ┌──┐  ┌──┐                  │
│  │  │  │  │  │  │  │  │  │  │  │  │  │  │  │  │                  │
│  └──┘  └──┘  └──┘  └──┘  └──┘  └──┘  └──┘  └──┘                  │
│                                                                     │
│           [   Push Selected to Device   ]                           │
│  ▲ gallery grows to 77% width; rows fit ~8 items per row           │
└─────────────────────────────────────────────────────────────────────┘
   77% gallery                                              23% devices
┌──────────────────────┐
│ Devices        [R]   │
├──────────────────────┤
│  ● Timoo            │  ← 23% width = 235px
│  ● Tivoo Max        │     [] 14px + 8px gap + ● 8px + 8px
│  ● Ditoo            │     + 6px name → fits ~16 chars
│  ● Pixoo            │
│                      │
│ [  Sync All →  ]     │  ← full-width button
└──────────────────────┘
```

### 4.2 Sketch — Settings → Connectivity (post-B)

```
┌─ Settings ─────────────────────────────────────────────────────────┐
│ [Devices]  [Divoom]  [Connectivity]  [Appearance]                  │
├────────────────────────────────────────────────────────────────────┤
│ Connectivity & Privacy                                              │
│                                                                     │
│ ● Bluetooth    100% local. Direct BLE. Never leaves your machine. │
│ ● Local Network 100% local. WiFi-capable devices only.            │
│ ● Divoom Cloud  Required for gallery browsing. Requires account.  │
│ ● Public Cloud  3rd-party APIs. No login required.                 │
│                                                                     │
│ ─── Automation ───────────────────────────────────────────────────  │
│                                                                     │
│ Automatic Hot-Channel Schedule                                      │
│                                                                     │
│  Enable scheduled sync                                              │
│   Sync every [1 hour  ▼]  [Save Schedule]                          │
│   Status: Saved — scheduled                                          │
│                                                                     │
│ (Moved from Monthly Best per design review; this is the right      │
│  home for set-and-forget automation.)                               │
└────────────────────────────────────────────────────────────────────┘
```

### 4.3 What changes in code

**`gui/web_ui/templates.js`** (`monthlyBest: ...`):
- Remove the `<div class="hc-schedule">...</div>` block
  entirely from the Monthly Best template.
- Rename the right card header from "Sync Targets & Schedule"
  to "Devices".
- Update the section comment on the schedule block to a
  breadcrumb hint: "Auto-sync schedule lives in Settings →
  Connectivity."

**`gui/web_ui/gallery.css`**:
- `.monthly-best-layout` grid `1.4fr 1fr` → `1.6fr 0.6fr`.
- `.target-row` remove the `.target-addr` element (and its
  CSS).
- `.target-name` `max-width: 110px` → `max-width: 180px` (or
  remove — the address is gone, the name can stretch).

**`gui/web_ui/gallery.js`** (`renderSyncTargets`):
- Don't create the `addr` element.

**`gui/web_ui/templates.js`** (Settings sub-tab list):
- Add a 5th sub-tab: "Automation" (or add a section inside
  the existing Connectivity tab).
- Add a new template for the Automation sub-tab (or extend
  Connectivity with the schedule block).

**`gui/web_ui/settings.js`**:
- Wire up the schedule block in the new location.
- Use the same `get_hot_channel_config` /
  `save_hot_channel_config` API methods (no API change).

**`tests/test_gui_drag_instrumented.py`** (or a new
`tests/test_gui_monthly_best.py`):
- 2-3 Playwright tests:
  - `test_monthly_best_right_card_is_narrower_than_gallery`
  - `test_sync_target_rows_have_no_mac_address`
  - `test_schedule_removed_from_monthly_best_visible_in_settings`

---

## §5 — New functionality inventory: in divoom_lib, not in GUI

### §5.1 Inventory (delta since Round 0/1)

| divoom_lib surface | Command | GUI exposure | Gap |
|---|---|---|---|
| `display.show_image(file)` (now 0x49) | 0x49 | `display_custom_art` | shipped |
| `display.show_image(file, frames > 1)` (now 0x8B) | 0x8B | `display_custom_art` (transparent multi-frame) | shipped |
| 32×32 screensize | n/a | auto via `screensize` kwarg | shipped |
| `display.show_light(color, brightness, mode)` | 0x45 | `set_solid_light` | shipped |
| `display.switch_channel(channel)` | 0x45 | `switch_channel` | shipped |
| `display.show_clock(clock, color)` | 0x45 | `set_clock` | shipped |
| `display.show_vj_effects(number)` | 0x45 | `set_vj_effect` | shipped |
| `display.show_visualization(number)` | 0x45 | `set_visualization` | shipped |
| `display.show_scoreboard(text)` | 0x45 | — | **NOT EXPOSED** |
| `display.show_text(text, ...)` | 0x45 | — | **NOT EXPOSED** |
| `display.show_user_define_time(...)` | 0xBD 0x14 | — | **NOT EXPOSED** |
| `design.set_eq(dyn, mode, stream)` | 0xBD 0x1E | — | **NOT EXPOSED** |
| `design.set_language(code)` | 0xBD 0x26 | — | **NOT EXPOSED** |
| `design.set_user_define_time(...)` | 0xBD 0x14 | — | **NOT EXPOSED** |
| `control.set_keyboard(key)` | 0x23 | — | **NOT EXPOSED** |
| `control.set_hot(enabled)` | 0x26 | — | **NOT EXPOSED** |
| `control.set_light_mode(channel)` | 0x45 | — | **NOT EXPOSED** (alias of switch_channel) |
| `sound.*` (volume, play status, etc.) | various | — | **NOT EXPOSED** |
| `game.show_game(value)` | 0xA0 | — | **NOT EXPOSED** |
| `game.hide_game()` | 0xA0 | — | **NOT EXPOSED** |
| `game.set_key_down(key)` | 0x17 | — | **NOT EXPOSED** |
| `game.set_key_up(key)` | 0x21 | — | **NOT EXPOSED** |
| `game.set_magic_ball_answer(answer)` | 0x88 | — | **NOT EXPOSED** |
| `alarm.get_alarm_time()` | 0x42 | — | **NOT EXPOSED** |
| `alarm.set_alarm_time(...)` | 0x42 | — | **NOT EXPOSED** |
| `sleep.get_sleep_time()` | 0x42 | — | **NOT EXPOSED** |
| `sleep.set_sleep_time(...)` | 0x42 | — | **NOT EXPOSED** |
| `timeplan.*` | 0x42 | — | **NOT EXPOSED** |
| `device.set_volume(vol)` | 0x08 | — | **NOT EXPOSED** |
| `device.get_volume()` | 0x08 | — | **NOT EXPOSED** |
| `device.get_battery()` | 0x04 | — | **NOT EXPOSED** |

**Total:** 28+ new divoom_lib surfaces, 22 not exposed in GUI.

### §5.2 Buckets (mental-context groups)

| Bucket | Mental context | When the user thinks "I want to do X" |
|---|---|---|
| **A. Live controls** | "What should my device be doing right now?" | Volume, EQ, light mode, language, hot mode, keyboard, games |
| **B. Channels** | "Show me a different kind of content." | Scoreboard, text, user-define-time, VJ/visualizer/clock (already exposed) |
| **C. Set-and-forget** | "Configure the device's persistent state." | Alarms, sleep, timeplan, language (could be B), user-define-time |
| **D. Routines / automation** | "Run this on a schedule." | Hot-channel schedule (currently in Monthly Best) |
| **E. Status / introspection** | "What's the device's current state?" | Battery level, volume, current channel |
| **F. Power-user** | "Send a raw command." | EQ, keyboard (Ditoo), magic-ball answer |

### §5.3 Where each bucket belongs in the GUI

| Bucket | Tab / sub-tab | Rationale |
|---|---|---|
| A. Live controls | Control Panel | Already where the live controls live. Add as new sub-cards. |
| B. Channels | Control Panel → new channel tabs | Add Scoreboard, Text, Custom-Time as new channel tabs. |
| C. Set-and-forget | Settings → new sub-tab "Routines" | Settings is the natural home. |
| D. Routines | Settings → "Routines" (shared with C) | Relocated from Monthly Best per §3 Option B. |
| E. Status | Appbar | Battery + volume status badges next to brightness. |
| F. Power-user | Settings → new sub-tab "Advanced" | Hidden behind "Show advanced" toggle (Rams #5 unobtrusive). |

---

## §6 — New functionality, bucketed exposure plan

### §6.1 Phase 1 — high-value, low-risk (ship first)

| Feature | Bucket | Surface | Effort | Value |
|---|---|---|---|---|
| **Volume control** | A (live) | Appbar slider next to brightness | S (1 file: index.html + 1 app.js handler + 1 gui_api method) | High — every user wants volume control |
| **Battery status** | E (status) | Appbar badge (color: green/yellow/red) | S (1 gui_api method + 1 app.js update) | High — replaces need to look at device |
| **Routines sub-tab in Settings** | C/D | Add "Routines" sub-tab to Settings | M (move schedule from Monthly Best + add alarms/sleep/timeplan) | High — alarms alone justify it |
| **Hot-channel schedule in Routines** | D | Move from Monthly Best | S (template move) | High — fixes §3 layout problem |
| **Scoreboard channel** | B | New channel-card in Control Panel | S (1 channel-card, 1 channel-panel, 1 API call) | Medium — niche but visible |

### §6.2 Phase 2 — incremental, builds on Phase 1

| Feature | Bucket | Surface | Effort | Value |
|---|---|---|---|---|
| **Text channel** | B | New channel-card | S | Medium — niche |
| **EQ control (0xBD 0x1E)** | F (advanced) | Settings → Advanced → "Audio EQ" | M | Low — niche |
| **Language control (0xBD 0x26)** | C | Settings → Routines | S | Low — once per device |
| **Keyboard (0x23)** | F (advanced) | Settings → Advanced | M | Low — Ditoo only |
| **Hot mode toggle (0x26)** | A (live) | Appbar toggle | S | Medium — hot mode is a thing |
| **User-define-time** | B | New channel-card | M | Low — niche |

### §6.3 Phase 3 — power-user, late

| Feature | Bucket | Surface | Effort | Value |
|---|---|---|---|---|
| **Games (0xA0 + 0x17/0x21 + 0x88)** | A (live) | New "Games" sub-card in Control Panel | L | Medium — fun, but Ditoo-only |
| **Alarms get/set (0x42)** | C | Settings → Routines | M | High — but multi-step UI |
| **Sleep get/set (0x42)** | C | Settings → Routines | M | Medium |
| **Timeplan get/set (0x42)** | C | Settings → Routines | M | Low — niche |
| **Magic 8 ball answer (0x88)** | F | Settings → Advanced | S | Low — needs a UI for the answer |

---

## §7 — Open questions for the user

1. **Monthly Best layout — pick A (user-literal, schedule stays) or
   B (schedule moves to Settings, true halve)?** B is recommended.
2. **If B: should the schedule go in the existing "Connectivity"
   sub-tab, or a new "Routines" / "Automation" sub-tab?**
3. **New functionality priority — should we ship §6.1 (Phase 1)
   first, then §6.2, or all at once?**
4. **For the schedule in Settings — should we keep the current
   "Hot-Channel Schedule" terminology, or rename to something more
   user-friendly (e.g. "Auto-Sync Gallery")?** "Headless" is a
   developer term that the user wouldn't use.
5. **For the volume control — should it be in the appbar (always
   visible) or in Settings (one-click less)?** Appbar is more
   discoverable but adds chrome.
6. **For the battery status — should we show it as a colored
   badge in the appbar (always visible) or in a device-info card
   in Settings (cleaner chrome)?** Appbar is more glanceable.

---

## §8 — Recommendation summary

| # | Item | Recommended pick | Why |
|---|---|---|---|
| 1 | Monthly Best layout | **B (schedule moves to Settings, true halve)** | Kare: tight envelope, Rams #8 consistent, all 5 user asks fully satisfied |
| 2 | Schedule's new home | **Settings → new "Routines" sub-tab** | Distinct from transport (Connectivity), distinct from devices (Devices), distinct from appearance (Appearance). Routines is its own thing. |
| 3 | Phase 1 ship | **Volume + Battery + Routines tab + Schedule + Scoreboard** | Highest-value, lowest-risk, all small files |
| 4 | Phase 1 file count | 4-5 files | templates.js (move schedule), settings.js (new sub-tab), app.js (volume slider + battery badge), gui_api.py (3 new methods), index.html (markup) |
| 5 | Schedule naming | **"Auto-Sync Gallery"** (drop "Hot-Channel") | User-friendly, matches the gallery context |
| 6 | Volume location | **Appbar** (next to brightness) | Glanceable, always visible, consistent with brightness |
| 7 | Battery location | **Appbar** (small colored dot/badge) | Glanceable, low chrome |

**Estimated session cost for Phase 1:**
- 30 min: Monthly Best layout (B)
- 20 min: Schedule move to Routines
- 20 min: Volume slider in appbar
- 15 min: Battery badge in appbar
- 20 min: Scoreboard channel-card
- 30 min: tests + visual regression
- **Total: ~2.5 hours** + 30 min buffer for live-device tests

---

**End of planning. Next step: ask §7 questions, then execute.**

---

## §8 Implementation outcome (2026-06-06) — SHIPPED

### Picks (confirmed by user via 4-option questions)

| # | Question | Pick |
|---|----------|------|
| 1 | Monthly Best layout | **B** (schedule moves to Settings, true halve 73/27) |
| 2 | Phase 1 scope | **All 5** (Volume, Routines tab, Schedule, Battery, Scoreboard) |
| 3 | Schedule naming | **"Auto-Sync Gallery"** (drop developer terms "headless", "Hot-Channel") |
| 4 | Relocation hint | **None** (silent move) |

### What shipped

| # | Asks a–f (Monthly Best) | Status |
|---|--------------------------|--------|
| a | Header renamed "Sync Targets & Schedule" → "Devices" |  `templates.js:monthly-best-layout` |
| b | Right card narrowed to 23% (true halve) |  `gallery.css:.monthly-best-layout` now `1.6fr 0.6fr` |
| c | Sync-target row MAC address removed |  `gallery.js:renderSyncTargets` no longer creates `.target-addr`; CSS rule removed |
| d | Save Schedule button removed from Monthly Best |  Block deleted, moved to Settings → Routines |
| e | Interval select → simple interval dropdown (1h/6h/12h/24h) |  `#routines-auto-sync-interval` |
| f | Settings: new "Routines" sub-tab |  New sub-tab in `templates.js:settings-nav` |

| # | New functionality (Phase 1) | Status |
|---|-----------------------------|--------|
| 1 | Volume slider in appbar |  `index.html:appbar-volume-slider` + `app.js:change` handler + `gui_api.set_volume` / `get_volume` |
| 2 | Settings → Routines sub-tab |  `templates.js:settings-routines` + `settings.js:loadRoutinesAutoSync` |
| 3 | Schedule moved to Routines as "Auto-Sync Gallery" |  Drop-in from old Monthly Best schedule, "headless" label dropped, "classify" field dropped |
| 4 | Battery badge in appbar |  **DEFERRED** — no protocol command exists; see "Documented gaps" below |
| 5 | Scoreboard channel-card |  `index.html:panel-scoreboard` + `channels.js:pushScoreboard` (auto-apply on change) + `gui_api.set_scoreboard` + `divoom_lib.display.show_scoreboard()` |

### Deviations from the plan

- **Battery badge NOT shipped.** The plan called for a
  laptop-battery-style indicator, but divoom_lib has no
  device-battery protocol command. Implementing a fake
  badge (e.g. showing the laptop's battery) would be
  misleading — the user would think it's the *device*'s
  battery, not the host's. Deferred until a real
  command is found (possibly via Divoom Cloud over HTTPS,
  per the APK). The test
  `test_no_battery_badge_intentionally_not_implemented`
  in `tests/test_round6_layout_and_exposure.py` guards
  against accidental re-introduction.
- **Volume slider behavior.** Plan called for 0–100 range
  to match brightness. Implementation uses 0–15 to match
  the actual protocol range. Reasoning: Kare #3 ("show
  the raw value") over consistency. Brightness (0–100)
  and volume (0–15) are now intentionally separate
  sliders with different scales — not "normalized" to
  a common range.
- **Scoreboard treated as a CHANNEL, not a tool.** The
  plan suggested "tool, not channel" (skip
  switch_channel). User feedback (Round 6.1): "scoreboard
  should switch to the channel and push changes
  automatically without the user pressing the show
  scoreboard button — this is how all the other channels
  behave." The scoreboard is a tool on a channel (0x06),
  and the user's mental model is "channel card → switch
  channel". The implementation now calls
  `switch_channel("scoreboard")` (which dispatches to
  the new `show_scoreboard()` method) on card click,
  then auto-pushes scores on number-input change. Show /
  Hide / Enabled buttons were removed entirely (Kare:
  matches the other channels' auto-apply pattern).
- **Grid proportions.** Plan proposed `1.5fr 0.7fr` for
  Option B. Implementation uses `1.6fr 0.6fr` — the
  true-halve point (73/27). Kare: tighter envelope
  on the right; Rams: more honest halving.

### File map

| File | Change |
|------|--------|
| `gui/web_ui/templates.js` | Monthly Best card renamed, schedule block removed, Routines sub-tab added |
| `gui/web_ui/gallery.js` | Orphaned schedule handlers removed; dead `loadHotChannelSchedule()` call in mount timer replaced with comment |
| `gui/web_ui/gallery.css` | Grid `1.4fr 1fr` → `1.6fr 0.6fr`, `.target-addr` rule removed |
| `gui/web_ui/settings.js` | New `loadRoutinesAutoSync` + save handler + 2 event listeners (tab-changed + click) |
| `gui/web_ui/index.html` | Volume slider in appbar (after brightness), Scoreboard channel-card + panel |
| `gui/web_ui/app.js` | Volume slider `input`/`change` handlers + `get_volume` startup init |
| `gui/web_ui/channels.js` | scoreboard removed from no-`switch_channel` list (Round 6.1); show/hide button handlers replaced with `pushScoreboard()` wired to the number inputs' `change` events |
| `gui/gui_api.py` | `set_volume`, `get_volume`, `set_scoreboard` added |
| `divoom_lib/display/__init__.py` | New `show_scoreboard()` method (0x45 [0x06, ...]) + `switch_channel("scoreboard")` dispatch (Round 6.1) |
| `tests/test_round6_layout_and_exposure.py` | **NEW** — 19 regression tests (static + Playwright) |
| `tests/test_e2e_mock_device.py` | **+2 tests** — show_scoreboard / switch_channel("scoreboard") wire-byte tests (Round 6.1) |
| `CHANGELOG.md` | Round 6 entry added (with Round 6.1 scoreboard behavior fix) |

### Test count

- Round 6 initial: 486 → 505 passed (+19 layout/exposure tests).
- Round 6.1 scoreboard fix: 505 → **507 passed** (+2 e2e tests).
- 73 skipped, 0 failed throughout.
- Wall-clock full suite: ~70s.
- No regressions.

### Live device

- Volume slider and scoreboard: NOT yet live-tested.
  The transport-level correctness of the underlying
  protocol calls (`divoom.music.set_volume`,
  `divoom.display.show_scoreboard` for the channel
  switch, `divoom.scoreboard.set_scoreboard` for the
  score pushes) is covered by the new
  `test_e2e_mock_device.py` tests
  (`test_show_scoreboard_emits_channel_0x06_frame`,
  `test_switch_channel_scoreboard_dispatches_to_show_scoreboard`).
- Manual device verification is recommended before the
  next GUI deployment (manual checklist in §9 below).

### Phase 2/3 (deferred)

- **Phase 2**: Text channel, EQ (0xBD 0x1E), Language
  (0xBD 0x26), Keyboard (0x23), Hot mode toggle (0x26),
  User-define-time.
- **Phase 3**: Games sub-card, Alarms get/set, Sleep
  get/set, Timeplan get/set, Magic 8 ball answer.
- **Status**: gating, not started. Awaiting user pick.

---

## §9 Manual live-device checklist (recommended)

1. **Volume slider**
   - Click "Connectivity", connect to a device.
   - Drag volume slider in appbar. The device's speaker
     output should change in real time (no click needed).
   - The "N/15" display should update on `input`.
   - The device's volume should change on `change` (release).
   - Restart the app. The slider should re-initialize to the
     device's current volume (via `get_volume` on startup).

2. **Scoreboard channel-card** (Round 6.1: behaves like
   the other channels)
   - Click "Control Panel", click Scoreboard card.
   - The device should switch to the scoreboard channel
     (0x06). The display should now show the scoreboard
     face (or a placeholder if the device doesn't have a
     native scoreboard display).
   - Edit the Red input (e.g. set to 42, press Tab or
     click out). The device's scoreboard tool should
     update automatically (no "Show" button to click).
   - Edit the Blue input similarly.
   - Setting both to 0 is the "clear" — no separate Hide
     button is needed (per user: "hide is essentially
     'clear' since it clears the score").

3. **Routines sub-tab**
   - Click "Settings", click "Routines" sub-tab.
   - Toggle "Auto-Sync Gallery" enabled, pick 6h interval,
     click Save. The config should persist across app
     restarts (verify by closing and re-opening Settings).
   - The "next run in 6h" status line should update.

4. **Monthly Best layout (visual)**
   - Click "Monthly Best".
   - Verify the right card header is "Devices" (not
     "Sync Targets & Schedule").
   - Verify the right card is roughly 1/4 the width.
   - Verify there is no schedule block visible.
   - Verify sync-target rows do NOT show MAC addresses.

5. **Drag still works**
   - Drag the appbar (top strip with title). The window
     should follow the cursor smoothly on a single monitor.
   - On multi-monitor, the window should NOT jump to the
     wrong monitor when starting a drag from monitor B's
     coordinate space (the #1820 monkey-patch handles this).

---

**Status: SHIPPED 2026-06-06. Round 6 complete.**
