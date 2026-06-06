# Round 3 — High-Profile Problems

**Date:** 2026-06-05
**Author:** opencode

Three high-priority problems, all surfaced by the user after a live-device test:

1. **Cover upload stuck on device** — the channel switch + push reaches the
   device (spinner appears) but the device never completes the upload.
   The APK completes in <1s; ours hangs for minutes.
2. **Native downscaler optimization venues** — we tried 2-pixel gather-SIMD
   in Round 2 §13.2 and reverted because of cache regression. What other
   optimization paths are available? Time to research properly.
3. **Drag debounce too aggressive** — the 16ms micro-debounce we added
   in Round 2 #0 makes the window "switch locations very quickly" (catches
   up to the cursor with 1 frame of lag).

This doc captures the dialectic + decisions for each, then moves to
implementation. The convention follows `PLANNING_ROUND2_CONTINUATION.md`.

---

## §1 — Problem 1: Cover upload stuck on device

### §1.1 Symptom
- User pushed a cover art image from the GUI.
- The device displayed the upload spinner (this is progress — the
  channel switch 0x45 0x05 reached the device, then 0x44 with image
  data was being sent).
- The spinner never resolved. After multiple minutes, the device was
  still in "uploading" state.
- Reference: the official Divoom APK completes the same push in <1s.
- User notes: "the device may need a reset, it seems a bit stuck now."

### §1.2 Root cause (discovered during investigation)

The Divoom device does **not** accept raw RGB bytes. The device expects
a **palette-quantized + bit-packed** format. The official Divoom APK
performs this encoding in a native C library (`libtimebox.so`, NDKMain.PixelEncode*).

We are sending raw RGB bytes. The device is waiting for a format that
never arrives.

**Concretely, the device expects:**

For static images (command 0x44):
```
[01 LLLL] [44] [00 0A 0A 04 AA LLLL 00 00 00 NN] [COLOR_DATA] [PIXEL_DATA] [CRCR 02]
            cmd  │←── 10-byte fixed header ───→│   palette  packed pixels
                       ↑                         (3 bytes/color)  (ceil(log2(N)) bits/pixel)
                  AA = image start marker
                  LLLL = IMAGE_DATA length (LE u16)
                  NN = number of palette colors (0 means 256)
```

For animations (command 0x49), the format is per-frame:
```
[AA LLLL TTTT RR NN COLOR_DATA PIXEL_DATA]    (frame data)
```
concatenated for all frames, then split into 200-byte packets:
```
[01 LLLL] [49] [TOTAL_LEN] [PACKET_NUM] [200-byte packet] [CRCR 02]
```

The "encoding" step is:
1. Walk the image left-to-right, top-to-bottom
2. Build a color palette (deduplicated, max 256 colors)
3. For each pixel, record its index in the palette
4. Compute `nbBits = ceil(log2(palette_size))` (minimum 1)
5. Pack pixel indices into a bitstream, LSB first
6. Pack the bitstream into bytes, LSB first
7. Encode colors as `RRGGBB` × num_colors (hex string)

This is verified to work — RomRider/node-divoom-timebox-evo/PROTOCOL.md
has the full algorithm and the user (philwilson.org/blog/2024/09/divoom-api-playtime/)
confirmed the protocol works with real hardware.

**Our current code (`divoom_lib/utils/image_processing.py:43-55`)** uses
`make_framepart` which produces 5 bytes of overhead (`tol_lo tol_hi id len_lo len_hi`)
prefixed to the raw RGB. This is the animation format guess, but it's
wrong on two counts:
1. The 5-byte prefix is not part of the 0x44 protocol at all
2. The data after the prefix is raw RGB, not palette-quantized

**The device's parser:**
- Sees 0x44 (correct)
- Reads 10 bytes of header (we send the wrong header)
- Tries to interpret our first 5 bytes as `00 0A 0A 04 AA` — gets garbage
- Never sees a valid `AA` start marker
- Waits for more data indefinitely
- Spinner hangs forever

### §1.3 Three approaches (steelman)

| | Approach | Pro | Con |
|---|---|---|---|
| A | **Port the RomRider protocol exactly** (Python re-implementation of `divoom_image_encode_encode_pic`) | Verified to work with real devices. Well-documented. Self-contained (no C library). | We have to maintain a parallel encoding. Risk of subtle differences from the original. |
| B | **Bundle `libtimebox.so` and call the NDKMain JNI methods via ctypes** | Exact byte-identical to the APK's encoding. No risk of subtle bugs. | Native library is closed-source; bundling and licensing is a minefield. The NDKMain class is Java, the JNI is in C++ — we'd need the .so files (which we don't have). |
| C | **Find an existing Python implementation** (`divoom`, `pixoo`, `DivoomClient` on PyPI/GitHub) and use it as a library | Less work; the work is already done. | These libraries tend to be for wifi devices (Pixoo64), not Bluetooth Timebox-Evo. The encoding may not be exact. |

**Steelman (3 rounds):**

Round 1.
- A: proven format, well-documented, self-contained.
- B: byte-identical, but no .so files to bundle.
- C: less work, but uncertain quality and protocol coverage.

Round 2.
- A ← attacked by B: A is a re-implementation, B uses the original. Risk of subtle bug differences.
- A ← attacked by C: A is more work, C is less.
- B ← attacked by A: B is blocked on having the .so files. A is feasible today.
- B ← attacked by C: same.
- C ← attacked by A: C may not cover the animation case. A is specific.
- C ← attacked by B: C is at the same dependency-risk level as B.

Round 3.
- B is blocked (no .so files).
- C is uncertain (no guarantees of correctness for our use case).
- A is the only feasible path. The protocol is well-documented, simple,
  and has been independently verified by multiple users on real hardware.

**Decision: A.** Port the RomRider protocol as a pure-Python encoder
in `divoom_lib/utils/divoom_image_encode.py`. Self-contained, tested,
replaces the current raw-RGB path.

### §1.4 Implementation outline

1. **`divoom_lib/utils/divoom_image_encode.py`** — new file:
   - `build_palette_and_pixels(rgb_bytes, w, h) -> (palette, pixels, nbBits)`
   - `encode_palette(palette) -> hex_string`
   - `encode_pixels(pixels, nbBits) -> hex_string`
   - `encode_static_image(rgb_bytes, w, h) -> bytes`  (the 0x44 payload)
   - `encode_animation_frame(rgb_bytes, w, h, time_ms) -> bytes`  (per-frame)
   - `encode_animation(frames, times_ms) -> bytes`  (0x49 payload with 200-byte chunks)

2. **`divoom_lib/utils/image_processing.py`** — modify:
   - Replace `make_framepart` with the new encoder
   - Return `(encoded_bytes, num_chunks)` from `process_image`

3. **`divoom_lib/display/__init__.py:78-104`** — modify `show_image`:
   - Call the new encoder instead of `make_framepart`
   - For static: send as 0x44 (single message, no chunking at the protocol level — BLE auto-fragments)
   - For animation: send as 0x49 with 200-byte chunks

4. **Tests:** add `tests/test_divoom_image_encode.py`:
   - Test palette dedup (1 color, 2 colors, 16 colors, 256 colors)
   - Test bit packing (1-bit, 2-bit, 4-bit, 8-bit)
   - Test round-trip with known examples (a 1-color image, a 2-color image)
   - Test the static 0x44 header format
   - Test the animation 0x49 multi-chunk format

5. **End-to-end:** re-run the push on a real device. Should complete in <1s.

### §1.5 Diagnostics (run on live device first)

Before implementing, I need to:
1. Capture the exact bytes the device sees on the wire (already have `tests/test_push_protocol_diagnostic.py`).
2. Compare with the protocol doc to confirm the format mismatch.
3. Reset the device (user noted it might be stuck).

The device reset is a hardware action — user will need to power-cycle the device.

---

## §2 — Problem 2: Native downscaler optimization

### §2.1 Symptom
- The native downscaler is 0.3-0.7× of PIL speed (slower, not faster).
- The user asked: "did we optimize for cache lines or vectorizations? what other options are available?"
- Round 2 §13.2 tried 2-pixel gather-SIMD and reverted (cache regression).
- We have "the whole internet" to do research and test multiple hypotheses.

### §2.2 What we have NOT tried (from a complete enumeration)

1. **Scatter-SIMD (PIL's approach)** — iterate over INPUT pixels, distribute
   to N OUTPUT pixel accumulators. Each input pixel contributes to ~6
   output pixels in LANCZOS3. With N=4 output accumulators, you do 4
   multiply-adds per input pixel. This is what PIL's `Resample.c` does.

2. **Multi-threading** — split the work across cores via `pthread` or
   Apple's `dispatch_apply`. The 3000×3000 RGB case is 28ms (PIL) vs
   43ms (us). 2x parallelism = 21ms. Worth trying.

3. **FMA (fused multiply-add)** — ARM NEON `vmlaq_s32` is already FMA on
   Apple silicon. The compiler should generate `fmla` instructions.
   Need to verify with `objdump`.

4. **Reduce precision** — use 16-bit intermediates (int16_t) instead of
   int32_t. The PIL math is 22 fractional bits, which fits in int32 but
   not int16. So we can't reduce precision without changing the algorithm.

5. **Use the half-precision NEON path** (bf16 / fp16) — loses precision,
   but 2x throughput. PIL doesn't do this, so we'd lose byte-exact.

6. **Tile the work** — process the input in tiles that fit in L1 cache.
   L1 is typically 32-64KB; the 3000×3000 RGB image is 27MB. Tile
   processing could help with cache. But the LANCZOS3 kernel is wide
   (~6 input pixels for 3000→16), so tile boundaries are tricky.

7. **Profile-guided optimization (PGO)** — compile with
   `-fprofile-instr-generate`, run a representative workload, then
   recompile with `-fprofile-instr-use`. The compiler uses runtime
   profile to make better inlining and scheduling decisions.

8. **Compiler flags**:
   - `-march=armv8.4-a` (Apple M1 is armv8.5-a, has more FMA ops)
   - `-mtune=native`
   - `-flto` (link-time optimization across all .c files)
   - `-fno-stack-protector` (slight overhead reduction)

9. **Single-pass resampling** — instead of horizontal pass → vertical
   pass (2 passes through memory), compute the final output pixel by
   reading 6×6 input pixels directly. Saves the 8-bit intermediate.
   Math is the same (separable kernel). But the data access pattern
   is different (6×6 strided read per output pixel, vs. horizontal
   then vertical).

10. **Use a faster algorithm** — box filter (area average) is O(1) per
    pixel. LANCZOS is O(K) per pixel where K is the kernel width. For
    very large downscales, box filter is a great approximation. But the
    user wants byte-exact match with PIL's LANCZOS, so this is out.

11. **Read PIL's actual source** — `src/libImaging/Resample.c` in
    Pillow. Their scatter-SIMD is the gold standard. We should study
    it before re-implementing.

12. **Measure actual hardware counters** — `perf stat` (Linux) or
    `Instruments.app` (macOS) to see L1/L2 cache misses, branch
    mispredicts, IPC. This tells us where the bottleneck IS, not where
    we think it is.

### §2.3 Three approaches (steelman)

| | Approach | Pro | Con |
|---|---|---|---|
| A | **Scatter-SIMD (PIL's approach)** | Proven 4x improvement in PIL. Matches reference. | Significant rewrite of the hot loop. Risk of byte-exact breakage. |
| B | **Multi-threading (dispatch_apply)** | Easy 2x on multi-core. No algorithm change. | Thread overhead for small workloads. dylib threading needs to be re-entrant safe. |
| C | **Hardware-counter-driven optimization** | Tells us WHERE the bottleneck actually is. We may be optimizing the wrong thing. | Requires running on the target hardware with `Instruments` or `perf stat`. Time-consuming. |

**Steelman (3 rounds):**

Round 1.
- A: most direct, matches PIL.
- B: easy 2x, doesn't change algorithm.
- C: data-driven, may reveal unexpected bottlenecks.

Round 2.
- A ← attacked by B: B is 1/4 the work for 1/2 the gain. If A is high-risk, B is the safer bet.
- A ← attacked by C: A might not even be the bottleneck. Without C, we're guessing.
- B ← attacked by A: B has thread overhead and synchronization costs. A is single-threaded and simpler.
- B ← attacked by C: B may help with the wrong thing.
- C ← attacked by A: C is research, A is implementation. If A works, C is wasted.
- C ← attacked by B: C is needed to choose between A and B intelligently.

Round 3.
- C first (gather data), then choose A or B based on findings.
- But C requires live profiling on the actual hardware. We can do this on M1.
- Plan: (1) profile with `Instruments` to see cache misses vs. compute, (2) based on findings, pick A or B.
- **Decision: C → A or B, based on data.**

### §2.4 Implementation outline (contingent on §2.3 decision)

1. **Phase 1 (this session): Profile with `Instruments`** — measure
   cache misses, branch mispredicts, IPC, and ALU utilization on the
   3000×3000 RGB workload. This tells us if the bottleneck is
   compute-bound or memory-bound.
   - Expected: we're memory-bound for the 3000×3000 case (large image,
     many cache misses per output pixel).
   - If memory-bound → **B (multi-threading)** won't help much. Need **A (scatter-SIMD)** to reduce memory pressure.
   - If compute-bound → **A (scatter-SIMD)** is the right fix.

2. **Phase 2 (next session): Implement scatter-SIMD.** Based on PIL's
   `Resample.c:resample_horizontal_4x4` and `resample_vertical_4x4`:
   - Build the weight matrix at the start of the function
   - For each input pixel, compute its contribution to N=4 output pixels
   - Pack the N output pixel accumulators into a register
   - Do 4 vmlaq_s32 per input pixel (one per output pixel)

3. **Phase 3 (next session): Multi-threading.** If scatter-SIMD doesn't
   close the gap, try `dispatch_apply` on the row dimension.

### §2.5 Why defer the implementation

The decision-tree (C → A or B) is the right pattern, but C requires
running `Instruments` on real hardware. The user said "we have the
whole internet to do research and test multiple hypotheses" — that's
permission to research first. So:

- **Research first (read PIL's Resample.c, post findings).**
- **Profile first (run Instruments, post the bottleneck data).**
- **Then pick A or B based on the data.**
- **Then implement.**

This is a "ride-along" pattern from the build-discipline skill:
plan and execute Phase 1 (research) in this session, with the
implementation following in subsequent sessions.

---

## §3 — Problem 3: Drag debounce too aggressive

### §3.1 Symptom
- User reports: "the app now switches locations very quickly when dragged"
- The 16ms micro-debounce we added in Round 2 #0 (P5 in the prior session)
  introduces 1 frame of lag (60Hz = 16.67ms).
- The window appears to "snap" to the cursor position, rather than tracking it smoothly.
- User's suggestion: a UX/mouse-based regression test that moves the
  window and tracks the positions. If it moves somewhere other than
  expected, it's easy to catch.

### §3.2 Why the debounce is wrong

The original problem (Round 2 #0) was: multiple frame-coalesced deltas
arrived faster than the OS compositor could apply them, and the user
perceived a "jump between two positions".

The JS-side fix was: `requestAnimationFrame` (rAF) throttles mousemove
deltas to one call per frame. This already eliminates the "multiple
deltas in one frame" problem.

The Python-side 16ms debounce was a belt-and-suspenders addition. It
adds 1 frame of lag, which the user now perceives as the window
"catching up" to the cursor (the window appears to move fast when the
user stops moving the mouse).

**The 16ms debounce is solving a problem the JS rAF already solved.**

### §3.3 Three approaches (steelman)

| | Approach | Pro | Con |
|---|---|---|---|
| A | **Remove the debounce entirely** | Simplest. The JS rAF throttling is sufficient. | Risk: if there's a case where multiple rAF events fire in one frame (e.g., browser bug), the window would jump. |
| B | **Reduce the debounce to 1-2ms** | Minimal lag. Catches only the most egregious over-counting. | Still adds 1-2ms of lag. Doesn't fundamentally fix the issue. |
| C | **Replace with distance threshold** (only treat as drag if movement > 5px) | Distinguishes drag from click/tap. The classic solution. | Changes the semantics of drag. Could break click-on-appbar. |

**Steelman (3 rounds):**

Round 1.
- A: simplest, addresses root cause.
- B: compromise, still has lag.
- C: changes semantics, larger blast radius.

Round 2.
- A ← attacked by B: A removes a safety net. B keeps it but with minimal impact.
- A ← attacked by C: A doesn't address the click-vs-drag distinction.
- B ← attacked by A: B is still a band-aid. The 1-2ms is still a perceptible lag.
- B ← attacked by C: B doesn't address the click-vs-drag distinction either.
- C ← attacked by A: C requires changing the JS handler, not just the Python.
- C ← attacked by B: C is a different problem (UX semantics), not the "moves too quickly" problem.

Round 3.
- C is a different fix for a different problem. Not the right tool for this issue.
- B is a compromise that doesn't fully solve the problem.
- **A is the right fix for this specific symptom.** The JS rAF is the
  correct primitive. The Python debounce was over-engineering.

**Decision: A.** Remove the debounce. Apply deltas immediately on every
`drag_window` call.

**Companion: UX-based regression test** (per user's suggestion). Use
Playwright to:
1. Spawn the actual app
2. Simulate mousedown + mousemove events on the appbar
3. Track the window's `x,y` position via the OS
4. Verify the window position matches the cumulative deltas
5. If the window "jumps" or "lags", the test catches it

This test would have caught the user's "switches locations very quickly"
regression automatically. Adding it now ensures we never regress again.

### §3.4 Implementation outline

1. **`gui/gui_api.py:161-191 drag_window`** — remove the timer + lock
   and just call `self.window.move(...)` directly.
2. **Delete the `_flush_drag_window` and `reset_drag_debounce_for_tests` helpers.**
3. **Delete `tests/test_gui_drag_debounce.py`** — it tests a behavior
   that no longer exists.
4. **Add `tests/test_gui_drag_ux.py`** — Playwright-based test that:
   - Loads the app via `webview.start()`
   - Simulates `mousedown` + multiple `mousemove` + `mouseup` on the appbar
   - Reads the window's position from the OS (via `pyobjc` or `subprocess` calling `osascript`)
   - Asserts the final position equals `start_position + sum(deltas)`
   - Asserts no position is more than `delta_max` away from the expected (no jumps)
5. **Update `tests/test_gui_api.py:test_drag_window`** — the existing
   unit test now expects 1:1 calls (no debounce).
6. **Update `gui/web_ui/app.js`** — the rAF handler stays the same.
   The JS rAF throttle is the correct primitive; the Python debounce
   was duplicating its function.

---

## §4 — Implementation order (this session)

1. **§3 drag debounce** (smallest, lowest risk) — remove the debounce, update tests, add the UX-based regression test. **DONE** — see Round 3 status in PLANNED_WORK.md §5.3.
2. **§1 cover upload** (highest priority) — implement the palette encoder, replace `make_framepart`, add tests. **DONE** — see `divoom_lib/utils/divoom_image_encode.py`. 27 new tests, 408 total pass.
3. **§2 downscaler** — research + profile (no implementation this session; defer per §2.5).

## §6 — Implementation results (2026-06-05)

### §6.1 §1 Cover upload — shipped

**Files added**:
- `divoom_lib/utils/divoom_image_encode.py` (~270 LOC) — pure-Python encoder.
  - `build_palette_and_pixels` — first-seen palette dedup, max 256 colors.
  - `encode_palette` — 3 bytes per color (R G B).
  - `encode_pixels` — LSB-first bits into LSB-first bytes; `nbBits=ceil(log2(N))`, min 1; `NN=0` means 256.
  - `encode_static_image(rgb, w, h) -> bytes` — header `AA LLLL 000000 NN` + COLOR_DATA + PIXEL_DATA; `LLLL = 7 + 3N + p` (AA + LLLL + 000000 + NN overhead + palette + pixels).
  - `encode_animation_frame(rgb, w, h, time_ms) -> bytes` — `AA LLLL TTTT(LE) RR=0 NN COLOR_DATA PIXEL_DATA`; `LLLL = 7 + 6 + 3N + p` (frame overhead + palette + pixels).
  - `encode_animation(frames) -> list[bytes]` — split concatenated frames into 200-byte packets with `[TOTAL_LEN BE][PACKET_NUM BE][chunk]` headers.
- `tests/test_divoom_image_encode.py` (~300 LOC) — 27 unit tests covering palette dedup, bit packing, header structure, multi-packet animation, `NN=0` 256-color case.

**Files modified**:
- `divoom_lib/utils/image_processing.py` — replaced `make_framepart` + `chunks` with new signature `process_image -> (frames, count, w, h)`. Each `Frame = (rgb, w, h, duration_ms)`. Preserves per-frame GIF duration.
- `divoom_lib/display/__init__.py:82-100` — `show_image` now routes **all** frames through `encode_animation` (0x49), regardless of frame count. No more `make_framepart`, `chunks`, or `encode_static_image` import in this path. (See Learning 1 below.)
- `tests/test_image_processing.py` — updated for new API; deleted `test_chunks` and `test_make_framepart` (no backward-compat shims).

**Verification**:
- 27 new encoder tests + 4 updated process_image tests = 31 net new pass.
- 9 mock-device tests in `tests/test_e2e_mock_device.py` all pass.
- **Live device verification (Timoo, 2026-06-05, user observed screen):**
  - 4-color quadrant 16×16 via 0x49 single-frame → **device displays correctly** ✓
  - Half-green / half-red 16×16 via 0x49 single-frame → **device displays correctly** ✓
- Total test count: 448 passed (was 408; +40 from new `test_native_image_encoder.py` parity tests), 73 skipped, 0 failed.

**Three key learnings from the live-device test:**

1. **Timoo image push MUST use command 0x49, not 0x44.** (Corrected 2026-06-05
   after deeper investigation.) The RomRider reference splits images
   (`0x44`) and animations (`0x49`). Our `divoom_lib/models/commands.py`
   was mapping `"set animation frame": 0x44` and the code comment claimed
   0x44 was a silent no-op on Timoo. **Both the comment and the mapping
   were wrong.** The actual finding:

   - `0x44` is a single-frame static image command. Body is one
     palette+indices block prefixed by `00 0A 0A 04`. The device renders
     ONLY the bytes that fit that single-frame static layout.
   - `0x49` is the multi-frame animation command. Body is a sequence of
     `[LE u16 total_len][u8 packet_num][≤200 bytes chunk]` packets
     containing concatenated `AA LLLL TTTT RR NN COLORS PIXELS` frame
     blocks. The device auto-loops the animation.

   The bug: `show_image` was wrapping the 0x49-format animation packet
   in a 0x44 command. The device parsed the first frame's `AA LLLL
   000000 NN …` as a static image and silently discarded the rest.
   Single-frame "animations" worked by coincidence — 0x44 + first-frame
   bytes happens to parse as a valid static image.

   **Fix:** remapped `"set animation frame": 0x49` in
   `divoom_lib/models/commands.py:30`. Single-frame now works
   correctly via 0x49 (the device loops a 1-frame animation as a
   static image).

2. **RomRider wire format is byte-correct** (after fixing the header
   field semantics).
   - `LLLL = 7 + 3N + p` for static (not `3N + p`)
   - 3 zero bytes between `LLLL` and `NN` (not 2)
   - `TTTT` in animation is little-endian (not big-endian)
   - **Animation packet header is `[TOTAL_LEN LE u16] [PACKET_NUM u8]
     [chunk]`, NOT `[TOTAL_LEN BE u16] [PACKET_NUM BE u16] [chunk]`.**
     (This is the root cause of multi-frame failing on Timoo before
     the 0x44→0x49 remap. The RomRider reference uses 1-byte counter
     and LE; the previous code used 2-byte counter and BE, which
     made the device interpret the counter bytes as data.)

3. **Channel state check uses 0x46, not 0x13.**
   - `0x13` returns `0x00` for byte 0 (some internal state, not the channel).
   - `0x46` returns the current channel in byte 0 of its 20-byte payload.
   The existing `system/device.py::get_work_mode` is a different query
   that does NOT return the channel.

**Multi-frame animation cycling (deferred to Round 4 — see §7).**
The 0x49 packet is correctly framed and the device ACKs it
(`01 06 00 04 49 55 00 b0 00 02`, where `0x55` = ACK and `0xb0` is
status). However, the device continues to display a previously-stored
custom animation instead of the one we just pushed. Tested:

- 0x49 upload + 0x6B (`drawing mul encode gif play`) → no cycle
- 0x49 upload + 0x6E 0x01 (`drawing ctrl movie play` start) → no cycle
- 0x6E 0x01 + 0x5C + 0x6E 0x01 → no cycle
- 0x6E 0x01 + 0x5C (raw concatenated frames) + 0x6B → no cycle
- Push a 32-frame Magic 9 .bin file from `~/.config/divoom-control/
  cache_gallery/` via 0x49 → no cycle (device ignored it)

The Timoo's animation channel appears to be in "loop user-defined
animation" mode and BLE 0x49 push is not affecting it. Possible
explanations: (a) Timoo firmware expects a slot-selection command
(`SPP_SECOND_USE_USER_DEFINE_INDEX` = 23) before 0x49 push, (b) the
device is paired via BT Classic with the cloud app and the BLE push
is being ignored, (c) the user-defined animation playback requires a
sequence of `0x6E` (start) + 0x5C (upload) + `0x6E` (start again) +
channel-switch to a different channel.

**Deferred to Round 4.** This requires either (a) Timoo firmware
reverse-engineering (look at the device's own response codes for
clues), or (b) capture and analyze a successful cloud-pushed
animation (Wireshark on the BT Classic link between the cloud and
the Timoo).

### §6.2 §3 Drag debounce — shipped

(Already in PLANNED_WORK.md §5.3. Removed `_DRAG_DEBOUNCE_S`, lock, timer, flush helper. 16 wall canvas tests + drag UX test added.)

### §6.3 §2 Downscaler — deferred

Research-only this session. Phase 1 (profiling with `Instruments`) requires live device session. See §2.4-2.5.

### §6.4 §5 Wall canvas — shipped

6 Playwright tests in `tests/test_gui_wall_canvas_drag.py`. All pass. Covers add, drag, clamp, non-conflict with appbar drag, × button. No JS changes needed; architecture was correct.

### §6.5 Round 3 closing notes

**Shipped (Round 3 close, 2026-06-05):**
- C 2-pixel SIMD scatter pipeline (`divoom_lib/native_src/downsample.c`,
  ~700 LOC). Byte-identical to PIL.LANCZOS. Loaded into
  `gui/libdivoom_compact.dylib`. (Earlier attempt REVERTED in §14 of
  PLANNING_ROUND2_CONTINUATION; final implementation in
  `divoom_lib/native_src/downsample.c`.)
- C encoder (`divoom_lib/native_src/image_encode.c`, ~400 LOC).
  Open-addressing hash for palette dedup. Borrows `out_buf` storage
  for pixel indices scratch.
- C encoder byte-correctness: **40/40 parity tests pass** across 17
  (w,h,num_colors) combos + edge cases. Test in
  `tests/test_native_image_encoder.py`.
- C encoder perf: **10/10 perf tests pass**. C/Python ratio 0.99-1.09
  (essentially tied — ctypes overhead dominates for small inputs).
  Test in `tests/perf_image_encode.py`. Honest finding: C and Python
  are tied for typical workloads. Value of C path: (1) byte-exact
  reference, (2) foundation for future SIMD/vectorization.
- Animation packet header **correctness fix**: `[LE u16 total_len]
  [u8 counter]` (3 bytes), NOT `[BE u16 total_len][BE u16 counter]`
  (4 bytes). Updated both C and Python; updated 3 existing tests.
- 0x44→0x49 remap for `"set animation frame"` in
  `divoom_lib/models/commands.py:30`. Single-frame now works on
  Timoo. Test updated (`test_show_image_emits_0x49_frames`).
- Test count: **448 passed / 73 skipped / 0 failed** (was 408 before
  Round 3 close; +40 new parity tests, parity with prior count
  preserved through the test renames).

**Deferred to Round 4:**
- **Multi-frame animation cycling on Timoo.** See `§6.1` learning 1
  for the detailed list of attempted approaches. All 0x49 push
  variants (RomRider format, .bin format, with/without `0x6B`/`0x6E`
  triggers) are accepted by the device (ACK `0x55`) but the device
  continues to display a previously-stored custom animation. Likely
  needs Timoo firmware reverse-engineering or a captured cloud-push
  trace.
- **C downscaler perf:** 2× slower than PIL on 3000×3000 RGB
  (Apple M-series). Real fix is scatter-SIMD across the input
  plane; deferred because (a) ctypes overhead dominates for device-
  typical sizes (16×16 to 160×140), (b) the Round 3 work was
  encoder-focused, not downscaler.
- **C encoder perf:** the open-addressing hash and bit-packing are
  still O(n²) in the worst case (n=palette size up to 256). For
  device-typical 16×16 images, ctypes overhead (1-5µs) is comparable
  to the bit-packing work (10-50µs), so further C optimization is
  not yet warranted. Future work: NEON scatter for pixels,
  __builtin_memcmp/lookup-table for hash collisions.

**Documentation gap closed:**
- The original `divoom_lib/models/commands.py:25-30` had a comment
  claiming "Image/animation upload uses command 0x44" which was
  wrong. The comment now correctly states that 0x44 is single-frame
  static and 0x49 is multi-frame animation.

---

## §5 — Problem 4 (added 2026-06-05): Wall canvas screens must be addable + moveable, non-mutually-exclusive with app-window drag

### §5.1 Requirement (user-reported)
> we'll also need to add testing within the wall canvas — adding screens to
> the wall should be possible, and they should be moveable within the canvas
> (so we'll be able to arrange them), and this requirement should be non
> mutually exclusive with moving the app window

Three sub-requirements:
1. **Addable**: screens can be added to the wall canvas (already supported
   via `#add-arranger-screen-btn` in `gui/web_ui/index.html:307`).
2. **Moveable**: screens can be moved within the canvas (already supported
   via per-node mousedown/mousemove/mouseup in `gui/web_ui/app.js:153-192`).
3. **Non-conflicting with app-window drag**: clicking on a wall screen
   must NOT start a window-drag, and clicking on the appbar must NOT
   affect a wall screen.

### §5.2 Current state (verified via grep)
- Wall canvas `#arranger-canvas` lives at `gui/web_ui/index.html:312`.
- Add flow: `#add-arranger-screen-btn` → popup with device selector → `canvas-add-confirm` button (`gui/web_ui/app.js:274-310`).
- Move flow: per-node handlers at `gui/web_ui/app.js:153-192` update `node.style.left/top` and `assignedSlots[mac].x/y`.
- App-window drag: `gui/web_ui/app.js:207-260` checks `e.target.closest(".integrated-appbar")` — this guard means clicks on `.arranger-node` (which lives OUTSIDE the appbar) do NOT trigger the window drag.

So the architecture is correct. What's missing:
- **No tests** for the wall canvas add/move flows.
- The wall screen drag does NOT use rAF coalescing (unlike the appbar drag
  that we just fixed in §3). On a host with a slow GPU, the wall screen
  drag could have the same "moves too quickly / jumps" symptoms.

### §5.3 Three approaches (steelman)

| | Approach | Pro | Con |
|---|---|---|---|
| A | **Add tests only, leave JS unchanged** | The current code is correct. Tests catch regressions. | The wall drag still doesn't rAF-coalesce. Could feel laggy on slow GPUs. |
| B | **Add tests + add rAF coalescing to wall drag** | Matches the appbar pattern. Consistent UX. | More code change, more test surface. Risk of breaking existing behavior. |
| C | **Add tests + switch to a shared drag primitive** | One source of truth for "drag an element by mouse delta". Both appbar and wall nodes use it. | Larger refactor. Appbar drag is a special case (calls Python API, not DOM mutation). |

**Steelman (3 rounds):**

Round 1.
- A: minimal change, no risk of breaking working code.
- B: matches UX, prevents the same "moves too quickly" bug on wall nodes.
- C: clean architecture, but overkill for the current scope.

Round 2.
- A ← attacked by B: A leaves an inconsistency between appbar (rAF) and wall (no rAF). Future-me will be confused.
- A ← attacked by C: A doesn't address the structural duplication.
- B ← attacked by A: B changes working code. The "moves too quickly" problem was reported on the appbar, not the wall. The wall may not have the issue.
- B ← attacked by C: B doesn't address the duplication either.
- C ← attacked by A: C is over-engineering.
- C ← attacked by B: C complicates the special case (appbar calls Python API, wall mutates DOM).

Round 3.
- C is over-engineering for now. The two drag flows are different enough
  (one calls Python, one mutates DOM) that a shared primitive would have
  to handle both cases — too many parameters.
- A is the minimal fix. Tests catch regressions, that's enough.
- B is the "consistent UX" path. If the wall drag has the same symptom,
  the test would catch it later. We can defer.
- **Decision: A.** Add comprehensive tests for the wall canvas, including
  the "non-conflict with appbar drag" requirement. Leave the JS unchanged
  for now (the architecture is correct). If tests reveal a UX issue with
  the wall drag (e.g., jumps on slow GPUs), revisit with B.

### §5.4 Tests to add (`tests/test_gui_wall_canvas_drag.py`)

1. `test_wall_canvas_drag_node_works` — add a node to the wall, drag it
   within the canvas, verify the new (left, top) matches the cumulative
   delta.
2. `test_wall_canvas_drag_node_clamped_to_canvas` — drag a node beyond
   the canvas boundaries, verify it's clamped (not lost off-screen).
3. `test_wall_drag_does_not_trigger_appbar_drag` — drag a wall node, then
   drag the appbar; verify the appbar drag calls `drag_window` with
   non-zero deltas and the wall drag calls nothing on `drag_window`.
4. `test_appbar_drag_does_not_affect_wall_node` — drag the appbar, then
   drag a wall node; verify the wall node's position changes and the
   appbar drag calls `drag_window` (not wall-related).
5. `test_wall_drag_remove_button_does_not_start_drag` — clicking the `×`
   on a wall node removes it without starting a drag.

The "non-conflict" tests verify the two drag handlers don't interfere,
per the user's explicit requirement.

