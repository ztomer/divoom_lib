# Round 36 — Hot-channel update fails on real hardware (Ditoo): HW test plan

**Problem statement (user, 2026-06-09):** after the R35 APK-alignment work
(encoder RR/NN changes, 0x49 counter 1→0-based, TERMINATE removal, 0x8B for
32×32), the hot-channel update **does not work on a real Ditoo**. Iterate
against the hardware until it does.

## What changed since the last known-good hardware state

R35d hardware-verified `show_image` on all 4 devices (incl. Ditoo BLE) both
with and without TERMINATE. AFTER that verification, these landed **without**
hardware re-test:

| Commit | Change | Risk to Ditoo (16×16) |
|---|---|---|
| `ec258c8a` | 0x49 packet counter 1-based → 0-based | only the 0x49 FALLBACK path |
| `47278f10` (R35e) | 32×32 encoder → standard AA (RR=0x00, 1-byte NN), pre-frames removed, 0x8B enabled for 32×32 | 16×16 `encode_animation_frame` shared code touched |
| uncommitted | `sync_artwork`: urllib → aiohttp; PIL resize → `asyncio.to_thread` | download/decode, not BLE |

Also relevant R34 §1b (HW-untested): ACK gating after START (3s wait) +
retransmit serving. R35d's HW pass covered that path for `show_image`.

## The two hot-channel payload classes

`sync_artwork` (daemon) branches on the downloaded bytes:
1. **Magic 43 / GIF** → extract GIF → resize → `show_image` → 0x8B with
   OUR encoder's blob (fallback 0x49).
2. **Magic 9/18/26 raw bin** → `stream_raw_bin_payload` → 0x8B with the
   cloud's PRE-COMPILED bytes (no re-encode).

A Ditoo failure could be in either (or both): encode regression hits only
class 1; 0x8B flow regression (ACK gating, terminate removal) hits both.

## Test environment

- Drive everything **through the daemon** (`DaemonClient` RPCs on
  `/tmp/divoom.sock`) — the exact path the GUI uses. Restart the daemon first
  so it runs current code. BLE authorization: daemon spawn is TCC-disclaimed
  (R24), so this works from any context, no user needed.
- Ditoo = `E9A41E1E-9A96-974F-CE44-54F16D616F28` ("Ditoo-light-2").
- Real payloads: `~/.config/divoom-control/cache_gallery/*.bin` (1855 cached
  downloads; filename `group1_M00_…` ↔ file_id `group1/M00/…`). `.bin` = raw
  cloud bytes → lets us classify magic types and replay without the network.
- All daemon-side evidence in `/tmp/divoom_daemon.log` (chunk progress,
  ACK/retransmit lines, exceptions).

## Phases (iterate; record each run's outcome below)

- **Phase 0 — reproduce.** Restart daemon → `connect_device(Ditoo)` →
  `sync_artwork(<cached file_id>)`. Capture the exact failure mode:
  RPC error? daemon exception? 0x8B chunk stall? success-but-blank-screen?
- **Phase A — baseline regression check.** `show_image` of a generated local
  16×16 GIF on Ditoo (the R35d-verified case) via daemon `device_call`.
  - PASS → common encode/stream path OK; suspect raw-bin path or magic-43
    extraction → Phase B.
  - FAIL → regression in shared code since R35d → Phase C bisect.
- **Phase B — payload-class split.** One magic-43 file and one raw-bin
  (9/18/26) file through `sync_artwork`. Compare.
- **Phase C — targeted bisect** (only what Phase 0/A/B implicates):
  1. TERMINATE removal: re-add CW=2 for the raw-bin path and retry (R35d only
     verified show_image without it).
  2. ACK gating: log whether Ditoo ever sends the `[0]` ready ACK; if it
     never does, the 3s wait + retransmit drain may interleave badly with the
     next command.
  3. 0x49 0-based counter: only if the 0x8B path falls back to 0x49.
  4. R35e shared-encoder diff: encode a frame pre/post R35e
     (`git stash` not needed — encoders are pure; compare against
     `git show 71bc54e4:divoom_lib/...` output) and diff bytes.
- **Phase D — confirm + lock in.** 3 consecutive `sync_artwork` successes on
  Ditoo incl. at least one multi-image batch; re-run
  `tests/test_hardware_smoke.py` on all reachable devices to ensure no
  collateral damage; full unit suite; update APK_COMPARISON.md with verified
  facts; commit.

## Success criterion

"Update Device" (hot-channel sync) renders on the Ditoo reliably (3/3), other
devices unharmed, suite green.

## §runlog — every hardware iteration goes here

- **2026-06-09 18:24 — Phase 0 (reproduce, single magic-9 sync via daemon).**
  Restarted daemon (current code), `connect_device(Ditoo)` OK,
  `sync_artwork(group1/M00/01/10/L1ghbm…)` → **success=True in 14.9s**: Ditoo
  sent the `[0]` start-ACK, all 28 chunks streamed, zero retransmit requests,
  clean quiet. So the TRANSFER works; "doesn't work" = nothing renders.
- **2026-06-09 18:26 — Phase A (R35d baseline show_image).** Generated 16×16
  GIF via daemon `device_call` → success in 1.2s, start-ACK seen. Protocol-level
  pass — note `test_hardware_smoke.py`'s PASS is the same protocol-level check
  (it cannot see the screen), so R35d's "verified with and without terminate"
  did not actually prove DISPLAY.
- **2026-06-09 18:28 — Phase B (batch, 3 magic-9 files back-to-back).** 3/3
  success (18.1s / 4.6s / 6.8s), no errors. GUI batch path is fine too.
- **2026-06-09 18:3x — ROOT CAUSE (forensics, no hardware needed).** Hexdump of
  a magic-9 `.bin`: `09 2a 00 e0 d0 d3 03 …` — high-entropy from byte 4 on.
  `media_decoder.decode_and_save_preview` confirms the format: magic 9 =
  `[magic][total_frames][speed:2 BE]` + **AES-CBC-encrypted** raw RGB frames
  (key `78hrey23y28ogs89`, fixed IV); magic 18/26 add LZO compression. The
  cached `.gif`s ARE its decode output. **`sync_artwork` streams the encrypted
  container raw to the device** (`stream_raw_bin_payload`) — the Ditoo receives
  32KB of ciphertext, ACKs every chunk, and has nothing it can render. The APK
  NEVER raw-streams cloud files: `PixelBean.initWithCloudData` decodes, then
  `pixelEncode` re-encodes for 0x8B. Our raw-stream "success" was a false
  positive all along (transfer-level, not render-level).

## Fix (APK-canonical): decode cloud containers before sending

1. `media_decoder`: extract the AES/LZO frame-decode core from
   `decode_and_save_preview` into `decode_cloud_frames(raw) → (PIL frames,
   duration_ms)` at NATIVE size (no 128×128 preview upscale); new
   `decode_cloud_to_gif(raw, out_path)`. Preview path keeps its behavior.
2. `device_owner.sync_artwork`: magic 43 → extract GIF (existing); **magic
   9/18/26 → decode to native GIF → `show_image`** (resize + our APK-aligned
   encoder + 0x8B); raw-stream only as last-resort fallback for unknown magics.
3. Test on Ditoo via daemon; protocol pass + USER EYE for render confirmation
   (only the user can confirm pixels; everything else verified objectively).
4. Unit tests with a synthesized magic-9 fixture (encrypt a known frame with
   the published key/IV) — no user cache data in the repo.

## §outcome — FIX SHIPPED (`4d7aae3d`), suite greened (`6937a468`)

- **Decoder verified offline**: cached magic-9 bin → 24 native 16×16 frames,
  pixel-identical (0/256 diff) to the established preview pipeline's output.
- **Hardware run (Ditoo, via daemon)**: `sync_artwork` now logs
  `decoded cloud container (magic 9) → 5783B GIF` →
  `show_image: streaming 24 frame(s) via 0x8B (5853 bytes)` → start-ACK →
  success in 4.0s (was 14.9s streaming the 32KB ciphertext). Batch 3/3 at
  2-4s per image, zero retransmits, zero errors.
- **Suite**: 1216 passed / 75 skipped / 0 failed. Also fixed pre-existing
  reds: stale batch-sync-btn regex (R35 span structure), `test_hardware_smoke`
  pytest collection error (`__test__ = False` — it's a manual harness), and
  the no-emoji rule violations in the R35 docs + gallery.js toasts. The
  decoder tests also evict the `divoom_lib.media_decoder` SHIM that
  `test_gallery_cache_rebuild` leaks into `sys.modules`.
- **Lesson recorded**: transfer-level success (every chunk ACKed) is NOT
  render-level success. `test_hardware_smoke`'s PASS and all daemon-RPC
  successes are protocol-level only — the R35d "verified with and without
  terminate" claim was protocol-level too. Final render confirmation needs
  human eyes on the device.
- **REMAINING (user)**: glance at the Ditoo after a hot-channel "Update
  Device" run — the last three synced artworks should now actually display.
