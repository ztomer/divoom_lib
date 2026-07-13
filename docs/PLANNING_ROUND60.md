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
**Status:** **DONE** (commit `2be8a52`). `sync_artwork.rs` / `art_codec.rs` /
`monthly_best.rs` docstrings rewritten to state the decoders exist.
`grep -n "not yet ported" divoomd/src` → 0 hits; `cargo test -p divoomd media` green.
**Plan:** rewrite both docstrings to state the decoders exist and
`resolve_to_gif` is the full path; `resolve_to_image_bytes` stays the
*image-only* subset (GIF/PNG/JPG/magic-43) used by callers that need a single
file, while `resolve_to_gif` also emits animated GIFs for the cloud/hot
containers.
**Kill:** `grep -n "not yet ported\|NOT yet ported\|not ported" divoomd/src` →
0 hits; `cargo test -p divoomd media` green.

## 2. Hardware re-verify cloud decode render (on-brand: device in loop)
**Status:** **DONE (v0.22.8, device-in-loop).** Both decoders green against the
magic-9/18/26/0xAA fixtures: Rust `media` unit tests (2/2: `magic9`/`magic18`
resolve to GIF) and Python `test_resolve_to_gif.py` + `test_media_decoder_cloud.py`
(11/11). Device push verified on the 3 reachable devices (Pixoo-1, Tivoo-Max-light-3,
Ditoo-light-2): `display.show_image` returned True and a post-push `get_brightness`
read-back succeeded → **no device-stick**. `resolve_to_gif` is not exposed via the
C binding, so a direct Rust-vs-Python byte-equal call isn't wired; both decoders
pass their own unit tests against the same fixture formats. Timoo-light-4 was
**not in BLE range** during the run (only 3/4 devices discovered) — re-run when
it is back online.
**Kill:** decoders green (both langs) + device push + no-stick on reachable
devices. (Byte-equal cross-check + Timoo deferred to next device session.)

## 3. `show_clock()` overlay reorder (verify vs APK C2() canonical)
**Status:** **CANONICAL ESTABLISHED from decompiled APK (probe-first, not the
convenience report).** `CmdManager.java:316` `C2(i9,i10,i11,i12,i13,bArr)` builds
`[ENV_MODE, i9, i13, bArr…, i10, i11, i12]`; caller `LightViewModel.java:222`
passes `(f10871c, f10874f, f10875g, f10876h, f10872d, h())`. With `h()` = the
4-byte `[0x01, humidity, weather, date]` blob and `ENV_MODE._value = 0x00`, the
**real** 10-byte frame is:
`[0x00, time_type, style, 0x01, humidity, weather, date, R, G, B]`.
This matches `set_clock_rich` (`display/__init__.py:37`) — so `set_clock_rich`
IS the APK-canonical path. **`show_clock()` (`display/__init__.py:51`) diverges:**
it emits `[0x00, twentyfour, clock, 0x01, weather, temp, calendar, R, G, B]`,
i.e. overlay bytes at positions 4,5,6 are `weather, temp, calendar` where the
firmware/canonical expects `humidity, weather, date`. Confirmed real divergence.
**Status:** **DONE (v0.22.8).** Realigned `show_clock()` to the APK `C2()`
canonical frame `[0x00, time_type, style, 0x01, humidity, weather, date, R, G, B]`
(`display/__init__.py:51`). Its overlay params were `weather, temp, calendar`;
the device's 0x45 env frame reads positions 4/5/6 as `humidity/weather/date`
only, so `temp`/`calendar` were misplaced (a real divergence). Renamed the
overlay params to `(humidity, weather, date)` to match the canonical fields
(web UI `lighting.py` only used `clock`+`color`, so no UI breakage; the one
hardware test using `temp` was updated). Added `tests/test_show_clock_wire.py`
(3 cases) pinning the exact wire bytes. **On-device verification:** pushed
`show_clock(clock=3, humidity/weather/date, color)` to Pixoo-1 → accepted,
post-push read-back responsive (no stick). Physical-screen visual of the
overlays is user-POV (cannot remote-screenshot the device).

## 4. Durable device_call parity test (anti-drift)
**Status:** **DONE** (interim tag v0.22.4). Added `tests/test_device_call_parity.py`
(hardware-free, static): enumerates the Python facade's public callable methods
(class-level, no device) and asserts `divoomd/src/device_call/*.rs` has a
handler for each. During implementation this test **caught 15 real key-alias
gaps**: the Python facade exposes `system.get_brightness` / `system.set_*`
/ `device.get_work_mode` / `sound.*` keys that `divoomd` only handled under a
*different* group prefix (`device.*` / `display.*` / `sleep.*`). Since
`device_call` forwards the verbatim key to `divoomd`, a client using the
`system.*` prefix would break under Rust. Closed by adding alias arms in
`mod.rs` + each submodule `handle` so `divoomd` accepts the exact Python facade
keys. `cargo build --bin divoomd` clean; parity test green; regression-detection
verified (dropping one key turns it red).
**Plan:** structural test enumerates `Divoom` facade public methods and asserts a
matching Rust handler (mirrors framing/encode parity tests).
**Kill:** test fails if any Python method lacks a Rust handler; green today.

## 5. `get_*` read-back timeouts on real hardware (mitigated; bound it)
**Status:** **CODE AUDIT DONE (v0.22.7) — bounded + cached in both paths.**
- Python: `divoom_lib/ble_reads.py::read_with_retry` uses
  `asyncio.wait_for(factory(), timeout=2.5)` per attempt + last-good `ReadCache`
  fallback (`from_cache=True` / `ok=False` with reason).
- Rust: every `get_*` handler passes `ctx.timeout` (`basic.rs`/`system.rs`/
  `sleep.rs`/`design.rs`/`music.rs`/`animation.rs`/`alarm.rs`); AND the daemon
  wraps the whole call in `tokio::time::timeout` default **30s, clamped
  [1s, 120s]** (`daemon.rs:442-448`) — so a `get_*` can never hang the device
  lock past 120s. The plan's `alarm.rs:10-14` per-call timeout is honored.
**Remaining:** the plan's kill-criterion "no UI hang observed on a deliberately
slow device" is a *device observation* — needs the user-driven hardware loop.
Code-level guarantee is satisfied.

## 6. Phase 5 archive — mark Python daemon reference-only (never delete)
**Status:** **DONE** (interim tag v0.22.5). `5.1` already ticked
(`PLANNING_NATIVE_PORT_HARDENING.md:226`). Added REFERENCE/FALLBACK banners to
`divoom_daemon/__init__.py`, `divoom_daemon/daemon.py`, `divoom_daemon/device_owner.py`
stating Rust `divoomd` is the default and the Python daemon is kept (do not
delete; `DIVOOM_USE_RUST_DAEMON=0`). Corrected the hardening-plan Phase-5 goal +
Exit wording to "archive, not delete." No `README`/`ROADMAP`/`AGENTS` claimed
Python was the default (verified). Remaining Phase-5 sub-task `5.4` (sweep
`README`/`ROADMAP`/`AGENTS` to *declare* Rust authoritative) is a no-op here.
**Kill:** no code behavior change; docs reflect reality; Python path still works
when explicitly selected (`DIVOOM_USE_RUST_DAEMON=0`).

## 7. Ditoo re-verify + niche subsystems (hardware-dependent)
**Status:** **DONE (v0.22.8, device-in-loop).** Ditoo-light-2 was in range and
passed the Tier B soak via the Python facade: connect → `set_brightness(50)` →
`get_brightness` (50) → `show_clock(clock=1)` → `show_design(0)` → post-op
`get_brightness` read-back responsive (no stick) → disconnect. Drawing-pad /
SD-music / animation gif-chunk primitives remain wire-tested (covered by
existing encode/animation parity + the #2 image push) but not separately
device-exercised; they share the verified frame pipeline.

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

**Checkpoints so far:** `v0.22.3` (onDaemonEvent fix + round-60 doc accuracy),
`v0.22.4` (#1 docstrings + #4 parity test + alias-gap closure), `v0.22.5` (#6
Phase-5 archive docs), `v0.22.6` (#3 APK C2() canonical established), `v0.22.7`
(#5 get_* timeout audit — bounded+cached both paths), `v0.22.8` (#2 cloud-decode
device push + no-stick, #3 show_clock canonical fix + wire test + device accept,
#7 Ditoo Tier B soak — all device-in-loop, driven from this shell). **Roadmap
complete (remote-verifiable parts).** Caveats: Timoo-light-4 was not in BLE range
(only 3/4 devices found) — re-run #2 on it when back online; physical-screen
visuals of clock overlays / cloud render are user-POV (cannot remote-screenshot
the device). No release yet (user drives the release after satisfaction).
