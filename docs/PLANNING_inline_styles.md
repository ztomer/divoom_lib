# Planning — inline-style → CSS-token migration (REVIEW_2026-06 §2.1 / §4.3)

**Status: scoped, not started.** Read-only investigation 2026-06-09.

## Real numbers

`grep -ho 'style="[^"]*"' templates_*.js` reports 142, but **4 are false
matches** (`data-style="18|3|9|6"` in `templates_monthly_best.js` — the regex
caught the `style="…"` substring). Actual inline-style count: **138**, across:

| File | count |
|---|---|
| `templates_settings.js` | 58 |
| `templates_widgets.js` | 51 |
| `templates_routines.js` | 21 |
| `templates_monthly_best.js` | 11 (−4 false = 7) |
| `templates_tools.js` | 1 |

Precedent already exists: `.flex-row` lives in `style_extra.css:78`, `.flex-header`
in `style.css:201`. New utilities should go in **`style_extra.css`** (the
existing utility home). Tokens available: `--text-main`, `--text-muted`,
`--font-mono`, `--font-sans`, etc.

## The review's own exception (do NOT migrate these)

§2.1 explicitly exempts "trivial widths and `colspan` that genuinely vary per
instance." So the goal is **not zero inline styles** — it's removing the
*repeated, themable* ones. Leave inline:
- one-off sizing: `width:60px`, `flex:1`, `flex:2`, `min-width:0`,
  `min-width:120px/140px`, `max-width:540px/600px`, `height:38px`
- `display:none` (JS toggles visibility — semantic state, not styling)
- genuinely unique compositions used exactly once

That accounts for roughly **40–50** of the 138. The remaining **~90** are
repeated patterns worth tokenizing.

## Proposed utility classes (mapped to the frequency data)

**Layout (biggest win — ~50 occurrences):**
| Class | Replaces | Seen |
|---|---|---|
| `.row` | `display:flex; align-items:center;` (+ gap variants) | many |
| `.row-between` | `display:flex; justify-content:space-between; align-items:center;` | 4+ |
| `.col` | `display:flex; flex-direction:column;` | 10+ |
| `.wrap` | adds `flex-wrap:wrap;` | 3+ |
| `.gap-6/.gap-8/.gap-10/.gap-12/.gap-14` | the `gap:Npx` values in use | many |

`display:flex; gap:10px; align-items:center; flex-wrap:wrap;` (5×) →
`class="row wrap gap-10"`. `.flex-row` already exists — reconcile/extend it
rather than adding a near-duplicate `.row`.

**Typography (~15):**
| Class | Replaces |
|---|---|
| `.label-sm` | `font-size:11px; font-weight:600; color:var(--text-muted); display:block; margin-bottom:6px;` (appears 2× with the two declaration orderings — both collapse to one class) |
| `.label-xs` | `font-size:10px; margin-bottom:4px; display:block;` (4×) |
| `.text-sm` | `font-size:13px; color:var(--text-main);` (5×) |
| `.text-mono-sm` | `font-family:var(--font-mono); font-size:11px;` |

**Semantic colour (~6) — replace hex with tokens + classes:**
- `#ffcc00` → `.text-warn` (add `--warn` token)
- `#ff4444` → `.text-error` (add `--error` token)
- keep the swatch-specific brand hexes as-is (they ARE the data)

**Structural reset (~13):** `margin:0;` (11×) and `min-width:0; overflow:hidden;`
(6×) — fold into the relevant component base rules (e.g. card title `h*`,
truncating flex children) rather than a `.m0` utility, so the reset is tied to
the component, not sprinkled.

## Batches (one PR-sized commit each, verify between)

1. **Add the utility/token layer** to `style_extra.css` (+ `--warn`/`--error`
   tokens). No template edits yet — pure addition, zero risk. Land it.
2. **`templates_tools.js` (1) + `templates_monthly_best.js` (7)** — smallest
   surface, good shakedown of the new classes.
3. **`templates_routines.js` (21).**
4. **`templates_widgets.js` (51).**
5. **`templates_settings.js` (58).**

Do 4 and 5 in sub-batches per view/section, not all at once.

## Verification (proven this session)

There are no unit tests for rendered CSS, so verify visually. The technique used
for the §2.3 `!important` fix works headlessly without the PyWebView bridge:
1. `python3 -m http.server` over `divoom_gui/web_ui/` via `.claude/launch.json`
   (already configured: `web_ui-static`, port 8799).
2. For each migrated block, render before/after and compare computed styles
   (`getComputedStyle`) — or screenshot the section — through the preview tools.
3. Because the JS builds markup as strings, also confirm the class names land:
   load the real `index.html`, drive the view, snapshot.

Per-batch acceptance: the migrated elements compute the same box model
(display/flex/gap/margin) and colour as before. Any divergence = fix before
landing the batch.

## Risk
- Medium. No test net; purely visual. Mitigated by (a) the review's
  leave-inline exception keeping genuinely-unique styles untouched, (b) small
  batches with per-batch visual verification, (c) batch 1 being a no-op addition.
- The `.flex-row` reconciliation (existing vs new `.row`) is the one place to be
  careful — audit its current users before changing it.
