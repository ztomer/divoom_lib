# Planning: Round 11 — GUI overhaul + push-path bug fixes _(2026-06-06)_

> **Input (user, verbatim grouping):** 9 items spanning Channels/custom-art,
> Live Widgets, Ambient, Appbar, Scoreboard, Virtual Wall, a font sweep, a
> tools-regrouping, and a "live push doesn't work" debug. "Write down, plan, ask
> clarifying questions, implement."

This is a large round → **phased**, each phase committed separately with tests
green (core rule). Design calls invoke **Dieter Rams** ("Less, but better";
honest; unobtrusive) + **Susan Kare** (clear, friendly, iconic, pixel-precise).

## Cross-path audit of the image pipeline (after the cover-art bug hunt)

"Do other image paths share these bugs?" — yes; swept them all. The three root
causes (resize-before-encode, 256/chunk-index 0x8B, continuous LSB packing) live
in shared code, so most paths were fixed transitively, but the **native C
encoder reimplemented the packing bug independently**.

| Path | Encoder used | Status |
|---|---|---|
| Cover art / stocks / sysmon (`media_sync`) | `display.show_image` | ✅ fixed (shared) |
| Custom art (`gui_api.display_custom_art`) | `display.show_image` | ✅ fixed (shared) |
| Gallery sync (`gallery_sync`) | resizes → `display.show_image` | ✅ fixed (shared) |
| Virtual Wall (`wall.show_image`) | per-panel → `display.show_image` | ✅ fixed (shared) |
| 32px encoder (`divoom_image_encode_32`) | reuses `encode_pixels`/`build_palette` | ✅ fixed (shared) |
| Monthly-best daemon | own 0x8B streamer | ✅ fixed earlier (256/index) |
| **Native C** (`image_encode.c` ×2, `image_encode_32.c`) | own C packing loop | ✅ **fixed now** + dylib rebuilt |
| Native C 0x8B chunker (`divoom_encode_animation_8b`) | byte-offset+256 | ⚠️ **dormant** — no live caller (live 0x8B is Python `stream_animation_8b`); left as-is, flagged |

**Native C fix:** all three C packing loops had the identical
"reset accumulator per byte + mask to 8 bits → drop carry for nb_bits∉{1,2,4,8}"
bug (its design contract was "byte-for-byte equal to Python", matched to the
*buggy* Python). Rewrote to a continuous LSB accumulator, rebuilt
`gui/libdivoom_compact.dylib`. The native parity tests already parametrize
byte-spanning colour counts (100→7b, 64→6b, 32→5b, 5→3b) and now pass — i.e. C
== fixed Python. (They likely passed before only because the committed dylib
wasn't loading on this arch, so the live path was the Python fallback.)

### Reusable lessons / checklist for any new device-image path
1. **Resize to the device pixel grid (16/32) before encoding** — never encode a
   source at native resolution (overflows the 2-byte LLLL/TTTT fields).
2. **Clamp frame duration to u16** (`encode_animation_frame` now does this).
3. **Push via `display.show_image`** (single + multi frame) — don't hand-roll a
   0x49/0x8B sender. show_image picks 0x8B (16px) via the proven streamer.
4. **0x8B = 256-byte chunks + chunk-INDEX offset id** (futpib), never byte-offset.
5. **Bit-pack pixels continuously LSB-first across byte boundaries** — the single
   most error-prone primitive; covered by a round-trip test for every width 1-8.
6. **Don't fork the encoder.** The C/Python split already drifted once; if perf
   needs C, keep the parity test as the contract and run it in CI.

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

### 2a/2b ✅ SHIPPED — auto cover-art push + button removed

Cover art now pushes **automatically**: refactored the music watcher into one
shared path (`_push_cover_for_track` → `_sync_now_playing`), which (a) listens
for album change via a tighter 1.5s now-playing poll, (b) pushes **immediately**
on change **and** immediately on enable (`force=True`, off the main thread), and
(c) the manual "Push Cover Art to Device" button + handler + were removed
(`push_music_cover_now` bridge left as an unused programmatic helper). +6 unit
tests (`tests/test_music_sync.py`). Suite 562/0.

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

## Design decisions (answered 2026-06-06)

1. **Virtual Wall toolbar:** icons **+ labels** (icon next to a short word).
2. **Unified sub-tab style:** delegated to me → unify on the **segmented pill
   bar** (the existing Settings/Braun pattern, already the dominant style) so the
   change is consistency + dedup, not a new look. One shared component.
3. **Volume slider:** keep **plain** (Rams).
4. **Sequencing:** **bugs first** — user will confirm BLE push fixes on real
   hardware as they land. Then UI phases.

## §outcome

_(filled as phases ship)_

### Phase 1 — push-bug cluster ✅ code-complete (awaiting hardware confirm)

Two distinct root causes found + fixed:

- **1b `int too big to convert`:** `show_image` encoded at the source's *native*
  resolution; a full-res gallery gif overflowed the 2-byte per-frame length
  (`LLLL`)/time (`TTTT`) fields. Fix: `process_image(..., size=screensize)` now
  resizes every frame to the device grid (NEAREST) before encoding, and clamps
  frame duration to `[1, 65535]`. Belt-and-suspenders: `encode_animation_frame`/
  `encode_static_image` clamp `time` to u16 and raise a *clear* error if a body
  still exceeds 65535.
- **1c/2a/9 transfer stall:** the `show_image` 0x8B loop sent phases tightly with
  **byte-offset** ids and 256-byte chunks and no pacing — the device stalled
  waiting. Fix: extracted the **proven** monthly-best streamer into
  `Animation.stream_animation_8b()` (chunk-**index** offset ids, 200-byte
  BLE-safe chunks, write-with-response, 0.5s buffer/settle + 0.01s inter-chunk
  pacing) and routed `show_image` through it. Cover art / stocks / sysmon all
  share this path, so 2a/9 are covered by the same fix.

Tests: +9 (resize/clamp in `test_image_processing.py`, u16 clamp + length-guard
in `test_divoom_image_encode.py`, streamer phases/index ids in
`test_animation_8b_stream.py`). Suite 546 passed / 0 failed.

Note: the **native** C chunker (`divoom_encode_animation_8b`) still uses
byte-offset ids + 256 chunks, but it's not on the live `show_image` path; left
as-is (would need a dylib rebuild) — flagged for a future cleanup.

**⏳ Needs:** user to confirm custom-art + live-cover push on the real device.

#### Reference cross-check (after user flagged the monthly-best path as suspect)

Compared our 0x8B path against the APK + the 3 new refs (futpib, hass-divoom,
andreas-mausch):

| Source | Protocol | Chunk | offset_id |
|---|---|---|---|
| **futpib** `lib.rs`+`animation.rs` | 0x8B 3-phase | **256** | **chunk index** (u16 LE) |
| our 0x8B framing | 0x8B 3-phase | (was 200) | chunk index (u16) |
| hass-divoom / node-divoom | 0x49 | 200 | chunk index (u8) |
| APK `SPP_DRAWING_ENCODE_PLAY` (Q) | own | 200 | chunk index (u8) |
| monthly-best daemon (ours) | 0x8B | **200 ❌** | chunk index |

Findings:
- Our **wire framing matches futpib exactly** (`file_size` u32 + `offset_id` u16
  + control words 0/1/2).
- Our **per-frame blob encoding matches futpib's `frame.rs::serialize`
  byte-for-byte** (`AA`, len u16, time u16, reuse_palette, color_count, palette,
  LSB-packed pixels; 256-colors→`0x00`). Verified field-by-field.
- **The only defect was chunk size: 200 (copied from monthly-best) vs futpib's
  256.** With index-based offset ids the device positions chunk *N* at byte
  *N×256*; 200-byte chunks leave 56-byte gaps so the file never completes — the
  exact stall (1c/2a/9). **Fixed → 256** in both `Animation.stream_animation_8b`
  and the monthly-best daemon. (futpib also omits the Terminate phase; we keep it
  per the protocol doc, but drop it next if hardware still stalls at terminate.)

#### Cover art still failed (single frame) → 2nd root cause

User confirmed **cover art still doesn't render**. Cover art is a *single* 16px
frame, and `show_image` special-cased `frames_count == 1` into the **0x49** path
(0x8B was gated to `> 1`). futpib's `send_image` (lib.rs:572) proves the correct
behavior: a still PNG is wrapped as a 1-frame `DivoomAnimation` and pushed
through the **same** `create_network_packets_from` (0x8B) path as a GIF — there
is *no* separate single-frame command. Fix: route **all** 16px pushes (1 frame
and N frames) through `stream_animation_8b`; 0x49 remains only as a fallback.
(32px still uses its dedicated 0x49 encoder.) e2e test updated to assert the
single-still push emits the 0x8B Start/Data/Terminate phases. Suite 546/0.

**⏳ Still needs hardware confirm** that cover art now renders via 0x8B.

#### Cover art rendered but DISTORTED → 3rd root cause (the real one)

Hardware showed the still now transfers + displays, but **scrambled**. The blob
is structurally correct (matches `save_to_divoom_format`: no file header, frames
back-to-back), so the defect was in **pixel bit-packing**: `encode_pixels` reset
its accumulator at every byte and masked to 8 bits, **dropping the carry whenever
`nb_bits` doesn't divide 8** (3/5/6/7 bits/pixel). A downsampled album cover has
~43 colours → nb_bits=6 → every byte-spanning pixel corrupted. (Solid-colour test
images use 1 colour → nb_bits=1, which divides 8, so tests + earlier "static
works" never caught it.) futpib uses `bitstream_io::LittleEndian` = continuous
LSB-first packing across byte boundaries. Rewrote `encode_pixels` to a continuous
LSB-first accumulator; added a round-trip test for **every** width 1–8 plus
hand-verified 3- and 6-bit cases. Also fixed an unrelated `Path` scoping
`UnboundLocalError` in `scanner_mixin` connection-persist seen in the same log.
Suite 556 passed / 0 failed.

**⏳ Hardware:** confirm the album cover now renders un-distorted.
