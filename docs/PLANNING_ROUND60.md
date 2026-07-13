# Round 60 — Open-thread verification & execution plan

**Method:** every open thread was *verified against the code* before planning
(the previous handoff's "Open threads" list was stale — two "blockers" are
already shipped). Each item below states its **verified status**, then a
concrete plan, kill-criteria, and tests. Hardware items keep the device in the
loop per standing directive.

---

## Verified corrections to the stale handoff

| # | Thread (as recorded) | Verified reality | Verdict |
|---|----------------------|------------------|---------|
| 1 | BLOCKER: cloud image-decode parity missing (magic 9/18/26 LZO + 0xAA) | `divoomd/src/media.rs::resolve_to_gif` (L47-68) decodes magic 9 → `decode_cloud_magic9`, 18/26 → `decode_cloud_magic18_26` (uses `minilzo_rs`, L47 `use minilzo_rs::LZO`), 0xAA → `decode_hot_file`, then `encode_frames_to_gif`. Tests `magic9_resolves_to_decodable_gif` / `magic18_resolves_to_decodable_gif` pass. `sync_artwork.rs:107` calls `resolve_to_gif`, so magic 9/18/26/0xAA now render. | **DONE** — only stale docstrings remain |
| 3 | Phase 5: flip `DIVOOM_USE_RUST_DAEMON` default on | `divoom_daemon/daemon_client.py:200-208` → `use_rust = rust_bin is not None` (defaults Rust when binary present; explicit `=0/1` overrides). | **DONE** |
| 2 | device_call method-level parity audit (54→0 gaps) | ROADMAP + `PLANNING_NATIVE_PORT_HARDENING.md` Phase 4 Tier A/B: mock E2E + real Timoo BLE (connect/brightness/exclusive/MCP/disconnect). Dispatch in `device_call/mod.rs:32`. | **DONE** (audit durable-test wanted, see #4) |

The real remaining work, in priority order:

---

## 1. Strip stale "not ported" docstrings (trivial, hardware-free)
**Status:** `sync_artwork.rs:7-13` PARITY NOTE and `art_codec.rs:138-141`
(`resolve_to_image_bytes`) docstrings still say magic 9/18/26/0xAA are "NOT
yet ported / fail honestly". They ARE ported (`media.rs`). The misleading
comments are a trap for the next session (they read as an open blocker).
**Plan:** rewrite both docstrings to state the decoders exist and
`resolve_to_gif` is the full path; `resolve_to_image_bytes` stays the
*image-only* subset (GIF/PNG/JPG/magic-43) used by callers that need a single
file, while `resolve_to_gif` also emits animated GIFs for the cloud/hot
containers.
**Kill:** `grep -n "not yet ported\|NOT yet ported\|not ported" divoomd/src` →
0 hits; `cargo test -p divoomd media` green.

## 2. Hardware re-verify cloud decode render (on-brand: device in loop)
**Status:** code path complete + unit fixtures pass, but the ROADMAP's
"byte-verified on Pixoo/Tivoo-Max/Timoo" claim should be re-confirmed on the
**currently connected** 4 devices (Pixoo-1, Timoo-light-4, Tivoo-Max-light-3,
Ditoo-light-2) — especially Ditoo (was "re-verify when in range").
**Plan:** via the live Rust daemon (`--run-hardware` test or a manual
`get_animated_preview`/`sync_artwork` call) push a magic-9, magic-18, magic-26,
and 0xAA fixture to each device; assert (a) `resolve_preview_data_url` returns a
`data:image/gif` URL, (b) the device does NOT stick in its loading animation
(the original failure mode), (c) on-screen render matches the Python oracle.
Add a hardware-gated parity test `test_rust_cloud_decode_renders` modelled on
`tests/test_rust_daemon_parity.py::test_rust_hardware_event_broadcast`.
**Kill:** all 4 magics render on all 4 devices with no device-stick; diff vs
Python `media_decoder.resolve_to_gif` output is byte-equal for the resolved GIF.

## 3. `show_clock()` overlay reorder (verify vs APK C2() canonical)
**Status:** `divoom_lib/divoom.py:37` `set_clock_rich` uses the APK `C2()`
10-byte format `0x45 [0x00, time_type, style, 0x01, humidity, weather, date,
R,G,B]` and is annotated "Different overlay positions than show_clock() — APK
canonical" (L41). `show_clock()` (L51) uses a *different* overlay coordinate
layout; ROADMAP flags "mismatched humidity/weather/date coords".
**Plan:** treat `set_clock_rich`/APK `C2()` as ground truth. Diff
`show_clock()`'s wire bytes against `C2()`; realign humidity/weather/date overlay
positions. Cross-check against `references/apk/decompiled_src/` (NOT the
convenience report, which has been wrong before).
**Kill:** `show_clock()` emits the same overlay layout as `C2()`; hardware
screenshot on a 16×16 device shows humidity/weather/date in the APK-canonical
positions.

## 4. Durable device_call parity test (anti-drift)
**Status:** parity claimed 54→0 but nothing *enforces* it — a new Python
`Divoom` method with no Rust handler would silently regress.
**Plan:** add a structural test that enumerates the public methods of the
Python `Divoom` facade (`divoom_lib/divoom.py` + submodules) and asserts each
has a matching handler in the Rust `device_call/*` dispatch (`mod.rs:32` →
per-module `handle`). Mirror the existing framing/encode parity tests'
philosophy. Keep it in the default (non-hardware) suite so CI catches drift.
**Kill:** test fails if any Python method lacks a Rust handler; green today.

## 5. `get_*` read-back timeouts on real hardware (mitigated; bound it)
**Status:** real-hardware read-back (`get_alarms`, weather, etc.) can time out;
currently mitigated by caches (`alarms.json`). `device_call/alarm.rs:10-14`
honors a per-call `timeout` already.
**Plan:** audit every `get_*` read-back for a bounded timeout + cached fallback
so the UI never hangs on a slow/unresponsive device; align Python + Rust paths.
**Kill:** every `get_*` returns within a bounded time or a cached value; no UI
hang observed on a deliberately slow device.

## 6. Phase 5 archive — mark Python daemon reference-only (never delete)
**Status:** Phases 1–4 DONE; Rust is the default (verified #3). `PLANNING_NATIVE_PORT_HARDENING.md:226`
`5.1` checkbox is stale (code already defaults Rust). Phase 5 = "Python backend
deprecation & archival," gated on 1–4.
**Plan:** (a) tick `5.1` in the hardening plan; (b) add a prominent header to
the Python daemon modules: "REFERENCE/FALLBACK — Rust `divoomd` is the default;
kept per user directive, do not delete"; (c) update launch/docs wording.
**Kill:** no code behavior change; docs reflect reality; Python path still
works when explicitly selected (`DIVOOM_USE_RUST_DAEMON=0`).

## 7. Ditoo re-verify + niche subsystems (hardware-dependent)
**Status:** Ditoo was "re-verify when in range"; drawing-pad, SD-music,
animation gif-chunk primitives are wire-tested but not device-verified.
**Plan:** when Ditoo is in range, run the full connect/exclusive/MCP/disconnect
soak; exercise the niche subsystems on whatever device flows are available.
**Kill:** Ditoo passes the same Tier B soak as Timoo; niche subsystems exercised
on at least one device each (or explicitly marked "wire-only" in docs).

---

## Deferred (no action this round)
- **Divoom Cloud HTTP (200+ endpoints):** blocked by `UserNewGuest` `RC=10`
  (auth flow changed) + scope. Own round (clock-face store + 1–2 endpoints).
- **R12 visual pass / R12 hardware verification:** user-driven; no autonomous
  action without user direction.

## Execution order for THIS round
1. **#1** docstring strip (trivial, green-CI) — do first.
2. **#4** durable parity test (hardware-free, prevents regression) — do next.
3. **#6** Phase-5 archive docs (trivial, accurate) — fold in.
4. **#2 / #3 / #5 / #7** require hardware / APK cross-check → verify on the
   real devices (Ditoo when in range) before marking done.

**Next concrete step:** implement #1 + #4 (both hardware-free, keep CI green),
then move to #2 (hardware re-verify) with the 4 devices in the loop.
