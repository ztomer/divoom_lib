# Engineering notes & hard-won invariants

Read this on entry (linked from `AGENTS.md`). These are lessons paid for in real
bugs — violate them and you will reintroduce a shipped defect. Keep this file
short and true; add an entry only when a bug teaches something durable.

## Protocol: verify against the source, not the prose

- The **decompiled APK** (`references/apk/`) and the reference implementations in
  `references/divoom-refs/` (futpib, hass-divoom, andreas-mausch) and
  `references/node-divoom-timebox-evo/` are the ground truth — **not** the
  summary tables in `references/apk/APK_INTELLIGENCE_REPORT.md`. That report has
  been wrong on real details (e.g. it listed the ANCS command as `0x60` with an
  RGB payload; the decompiled `CmdManager.java` shows `0x50` and no RGB).
- When implementing a command, read the actual call site in
  `references/apk/decompiled_src/.../CmdManager.java` and confirm against a
  second reference. Cite file+line in the code comment.

## "ACK ≠ success"

- A device notification acknowledging a command is **not** proof the operation
  worked. `get_*` read-backs time out on real hardware (task #20). Design write
  paths as fire-and-forget + (where possible) a real read-back/compare, and never
  report success purely because a frame was acked.

## Image pipeline invariants (every device-image path)

The cover-art bug hunt found three independent root causes; all are now invariants:

1. **Resize to the device pixel grid (16/32) BEFORE encoding.** Encoding a
   source at native resolution overflows the 2-byte per-frame `LLLL`/`TTTT`
   fields ("int too big to convert"). `process_image(..., size=screensize)`.
2. **Clamp frame duration to u16** (`encode_animation_frame` does this).
3. **Push via `display.show_image`** for both single stills and animations —
   don't hand-roll a 0x49/0x8B sender. futpib's `send_image` proves a still PNG
   goes through the *same* animation path as a GIF; there is no separate
   single-frame command.
4. **0x8B 3-phase = 256-byte chunks + chunk-INDEX `offset_id`** (0,1,2,…), never
   a byte offset. The device places chunk N at byte N×256, so the chunk size and
   the index must agree. Use `Animation.stream_animation_8b`.
5. **Bit-pack pixels continuously LSB-first across byte boundaries.** Resetting
   the accumulator per byte (masking to 8 bits) silently drops the carry for
   `nb_bits ∉ {1,2,4,8}` (i.e. 5–8, 17–32, 33–64, 65–128 colours) and renders
   garbage. This is the single most error-prone primitive.

## Dual implementations must be held to *correctness*, not to each other

- We keep a native C encoder **and** a pure-Python fallback (and the framing
  encoders are the same shape). Drift is prevented by running the **same
  correctness suite against each implementation independently**
  (`tests/test_encoder_both_impls.py`).
- **A `C == Python` parity test is not enough:** the byte-packing bug existed in
  *both* copies, so they agreed and the parity test passed. Tests must assert the
  *right answer* (encode → decode round-trips; golden field values), so a bug in
  both still fails. Apply this to any future C/Python twin.
- `conftest.py` auto-rebuilds the dylib when stale so the C side actually runs;
  CI (`.github/workflows/tests.yml`) builds it on macOS. If you change a `.c`
  file, the next `pytest` run rebuilds and re-tests it.

## When to reach for C

- Only for genuinely large/hot data. Our benchmark (`tests/perf_image_encode.py`)
  shows ctypes per-call overhead (~1–5µs) cancels the C speedup for 16×16 frames
  (~30–50µs) — C can even be *slower*. Don't port small/per-event paths (e.g. the
  frame **decoder**, which runs once per tiny notification and is a memory-safety
  risk in C) to C.

## GUI / pywebview

- The frameless window is draggable via `-webkit-app-region: drag` on the appbar;
  interactive children (sliders, buttons, inputs) need
  `-webkit-app-region: no-drag` or dragging them moves the whole window.
- macOS BLE is gated per responsible-process (TCC). Agent `Bash` can SIGABRT on
  BLE; drive real hardware by launching via Terminal. The unit suite skips
  hardware tests by default (`--run-hardware` to include).

## GUI: single source of truth for fonts (R14 §5)

`gui/web_ui/style.css` defines three font families as CSS variables — and
is the **only** file that may declare a raw font name:

| Variable         | Family      | Use                          |
|------------------|-------------|------------------------------|
| `--font-display` | Outfit      | headings, titles, big numbers |
| `--font-sans`    | Inter       | body text, buttons, labels   |
| `--font-mono`    | Inter Mono  | MAC addresses, technical strings |

Every other CSS file, every JS inline style, and the Google Fonts `<link>`
in `index.html` MUST reference one of these variables. The regression net
is `tests/test_fonts.py` — it fails if a new `font-family:` declaration
shows up with a raw family name, or if the Google Fonts request drifts
out of sync with `style.css`.

If you need a new font: add it to `style.css` + the index.html `<link>` +
the allow-list in `tests/test_fonts.py` (in that order). The test will
catch a missed step.

## No emojis in the repo (R14 §6)

Emoji codepoints (any of the 14 standard blocks: U+2300-23FF, U+2600-27BF,
U+2B00-2BFF, U+1F1E6-1F1FF, U+1F300-1FAFF) are forbidden everywhere
except `references/` (third-party code we don't control). The check is
`tests/test_no_emojis.py` — it scans every `.py`/`.js`/`.css`/`.html`/
`.md` file in the repo and fails the build if any emoji character is
present.

For visual indicators use:
- A CSS-styled element (color + shape — e.g. the `transport-dot
  active/inactive` class for the sidebar transport panel).
- An inline SVG (`<svg>...</svg>`) for icons.
- Plain text (the universal fallback).

The transport status JSON in `gui_api.get_transport_status()` previously
carried a `badge` (emoji) + `color` (hex) pair. Both were removed in
R14 §6 — the GUI uses CSS-driven dots via the `transport-dot` class.
