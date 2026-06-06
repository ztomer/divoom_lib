# Planning: Round 11 — GUI overhaul + push-path bug fixes _(2026-06-06)_

> **Input (user, verbatim grouping):** 9 items spanning Channels/custom-art,
> Live Widgets, Ambient, Appbar, Scoreboard, Virtual Wall, a font sweep, a
> tools-regrouping, and a "live push doesn't work" debug. "Write down, plan, ask
> clarifying questions, implement."

This is a large round → **phased**, each phase committed separately with tests
green (core rule). Design calls invoke **Dieter Rams** ("Less, but better";
honest; unobtrusive) + **Susan Kare** (clear, friendly, iconic, pixel-precise).

---

## Item 1 — Channels / Custom art

### 1a. Push-to-device button stuck at bottom of gallery → make it a sticky footer
- **Finding:** the Monthly Best panel already solved this (sticky action bar
  pinned to the window bottom). Reuse that exact pattern for the custom-art
  gallery.
- **Plan:** lift the "Push to device" control out of the scrolling gallery into a
  fixed/sticky footer container (same CSS class the Monthly Best panel uses).
  Verify in both themes.

### 1b. Push fails: `int too big to convert` 🐞 (root-cause candidate found)
- **Trace:** `gui_api.display_custom_art` → `display.show_image` →
  `build_8b_phases(frames)` → `_build_animation_blob` → `encode_animation_frame`.
  The crash happens **before** the "routing N frames via 0x8B" log, i.e. during
  blob build, for the gif `group1_M00_1E_FB_…`.
- **Root cause (strong candidate):** a `.to_bytes(2, …)` overflow in
  `divoom_lib/utils/divoom_image_encode.py` — the per-frame `TTTT` (frame time)
  or `LLLL` (body length) field. `_u16_le(n)` does `n.to_bytes(2)`; any value
  > 65535 raises exactly `int too big to convert`. A GIF frame duration or an
  oversized 32-px frame body trips it. (The 256-color `NN` path is already
  handled via `nn=0`.)
- **Plan:** (1) reproduce with a unit test feeding a synthetic frame with
  `time > 65535` and a frame whose body would exceed 65535 bytes; (2) **clamp
  frame time** to `[1, 65535]` ms and guard/validate length with a clear error;
  (3) confirm against the actual offending gif on hardware.

### 1c. Second push: device shows loading then gets stuck 🐞
- **Trace:** gif 2 DID log "routing 5 frames via 0x8B 3-phase", sent start +
  data + terminate, device ACKs (`8b 55 01 01 00 ee`) repeatedly but never
  finishes — a **transfer-stall**, distinct from 1b.
- **Hypotheses:** (a) missing inter-phase pacing / the device wants a delay or a
  per-chunk ACK wait before the next chunk; (b) `offset_id` should be a chunk
  **index** not a byte offset (futpib uses an incrementing packet id); (c) the
  terminate phase races the last data chunk. The repeated identical ACK suggests
  the device is waiting for the next expected chunk id it never gets.
- **Plan:** instrument the 0x8B sender to log each phase's bytes; compare
  `offset_id` semantics vs futpib `animation.rs`; add an await-for-ACK or small
  delay between data phases; verify on hardware (mock-device E2E first).

## Item 2 — Live Widgets

### 2a. Cover-art push doesn't work 🐞  +  9. live widgets push broken (same root)
- **Trace:** `media_sync._push_frame(out_path, size)` → `display.display_image`
  → same `show_image` path as 1b/1c. Same two ACK lines, no render. Almost
  certainly the **same encoder/transfer bug** as Item 1. Fix 1b/1c → re-test all
  live widgets (cover art, stocks, sysmon).
- **Plan:** treat Item 1 + 2a + 9 as one bug cluster; fix the shared
  `show_image`/0x8B path; add a mock-device E2E asserting the full
  start→data→terminate byte sequence for a small animation.

### 2b. "Push cover art to device" button is redundant → remove, do it automatically
- **Finding:** music-sync already auto-pushes on track change (`_push_frame` in
  the sync loop). The manual button is redundant.
- **Plan:** remove the manual button from the Live Widgets template + its handler;
  keep the auto-push in the sync loop. (Net simplification — Rams.)

## Item 3 — Ambient channel

### 3a. Color picker only applies to "Plain color"; hide it for fixed-palette modes
- **Plan:** show the color-related controls **only** when the selected ambient
  mode is "Plain color"; hide for the fixed/preset modes (they ignore color).
  Toggle visibility on the mode `change` event.

### 3b. Remove the word "Custom"
- **Plan:** drop "Custom" from the ambient labels/options.

## Item 4 — Appbar

### 4a. Volume slider font ≠ light slider font → unify
- **Plan:** the two sliders' value labels must share font-family, size, and
  color. Find both label elements; give them one shared class.

### 4b. Move connection-type indicators to **bottom-right**
- **Plan:** relocate the transport indicators from the appbar right edge to a
  bottom-right corner cluster (likely a fixed/absolute element). Keep semantics.

### 4c. Move the sliders to the **right** side of the appbar
- **Plan:** reorder the appbar flex so both sliders sit right-aligned.

### 4d. 🐞 Dragging a slider drags the whole window (regression-safe fix)
- **Cause:** the appbar has `-webkit-app-region: drag` (so the frameless window
  is movable), and interactive children inherit it. Sliders need
  `-webkit-app-region: no-drag`.
- **Plan:** add `no-drag` to the slider controls (and any button/inputs in the
  appbar) without removing `drag` from the bar background — this is the standard,
  non-regressing fix. We did the same kind of fix for the canvas earlier
  (task #8). Verify window still drags from empty appbar areas.

### 4e. Slider visual flair
- **Light slider:** thumb fills **white at full brightness, darkens toward
  black as intensity drops**; keep a contrasting border (white border in dark
  mode, black border in light mode) so it stays visible. This is *honest*
  feedback (the control mirrors the thing it controls) — Rams-approved.
- **Volume slider:** **DESIGN QUESTION** (see clarifying Q). Recommendation:
  keep it plain. Volume has no natural color/lightness mapping, so a matching
  gimmick would be decoration for its own sake — Rams "less but better", Kare
  "don't add chrome that doesn't mean anything." → propose plain, confirm.

## Item 5 — Scoreboard

### 5a. Add a **Reset** button → set both scores to 0/0.
### 5b. Make it look more like the device display — larger, centered, stacked:
```
   [  Blue score  ]
   [  Red score   ]
```
- **Plan:** restyle the scoreboard panel: big centered numerals, blue above red,
  +/- per team, and a Reset button. Wire Reset → `set_scoreboard(1, 0, 0)`.

## Item 6 — Virtual Wall toolbar unification
- **Goal:** merge "Load & presets" into the canvas box; drop the word "canvas".
  One toolbar:
  `[ Add screen | Clear | …flex… | preset-name (editable) | …flex… | Save | Load ]`
  freeing vertical space for the canvas.
- **DESIGN QUESTION:** icons vs text? (see clarifying Q). Rams/Kare lean:
  **icons with tooltips** for the verbs (add ＋, clear 🗑, save 💾, load 📂) —
  compact, language-neutral, and Kare's forte — but only if each icon is
  unambiguous; otherwise icon+label. Preset name stays a visible text field.

## Item 7 — Font sweep (centralize)
- **Finding:** some elements fall back to a default font instead of our chosen
  family. Likely missing `font-family: var(--font-sans)` (or inputs/selects/
  buttons not inheriting).
- **Plan:** audit CSS; add a global rule so `body, input, select, textarea,
  button { font-family: var(--font-sans); }` (and numeric displays use the
  intended family/var). Remove ad-hoc font declarations. One source of truth.

## Item 8 — Regroup the tools (+ unify tab style)

Target information architecture:
| Move | From | To |
|---|---|---|
| Alarms, Anniversary | Tools/Utilities | **Tools → Time** |
| Sleep Aid | (Utilities) | **Tools** (kept) |
| FM Radio | Tools/Radio | **Tools** (kept, regrouped) |
| Weather | Tools/Device | **Live Widgets** |
| Device Settings (+ Display) | Tools/Device | **Settings → Devices** |

- **8f. Consistent tab style across panels** — today Settings sub-tabs,
  Tools sub-tabs, etc. use slightly different hooks. **DESIGN QUESTION:** pick
  ONE unified sub-tab style (see clarifying Q) and apply everywhere.
- **Plan:** restructure templates (Tools→Time/Sleep/Radio; move Weather to Live
  Widgets; move Device Settings to Settings→Devices); collapse the duplicate
  sub-tab CSS/JS into one shared component; keep all bridges working; update the
  R8/R9/R10 UI-presence tests to the new locations.

## Item 9 — Live push debug → folded into Item 2a / Item 1 bug cluster.

---

## Phasing (each phase = its own commit, suite green)

1. **Bug cluster** (1b, 1c, 2a, 9): fix the shared `show_image`/0x8B encoder +
   transfer path; mock-device E2E + unit tests. *(highest value; needs hardware
   to fully confirm.)*
2. **Quick UI wins** (1a sticky footer, 2b remove redundant button, 3a/3b
   ambient, 5a reset).
3. **Appbar** (4a–4e).
4. **Scoreboard restyle** (5b).
5. **Virtual Wall toolbar** (6) — after design answers.
6. **Font sweep** (7).
7. **Tools regroup + unified tab style** (8) — after design answers; touches the
   most files + tests.

## Open clarifying questions (asked via AskUserQuestion)
1. Virtual Wall toolbar: icons / text / icons+labels?
2. Unified sub-tab style: which look?
3. Volume slider flair: keep plain (Rams) or add subtle flair?
4. Sequencing/hardware: confirm phase order + that you can test the BLE push
   fixes on the real device.

## §outcome

_(filled as phases ship)_
