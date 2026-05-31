# Code Review — `divoom-control` library

Dual-persona review (Linus Torvalds / "Uncle Bob" Martin) of the refactored
`divoom_lib` package, with verification against the current source and a
concrete remediation plan.

> Status legend: ✅ confirmed in code · ⚠️ partially true · ❌ not reproduced

---

## 🐧 Linus Torvalds — performance & I/O pragmatism

### L1. Allocation debt: `list`-backed receive buffer ✅
`Divoom.__init__` sets `self.message_buf = []` ([divoom.py:114](divoom_lib/divoom.py:114)).
The basic-protocol parser then does `self.message_buf.extend(new_data)`
([divoom.py:307](divoom_lib/divoom.py:307)), promoting every received byte into
a boxed Python `int`. Worse, the parser re-slices the buffer on every iteration:

- `self.message_buf = self.message_buf[start_index:]` — junk trim ([divoom.py:320](divoom_lib/divoom.py:320))
- `message = self.message_buf[:total_message_len]` then
  `self.message_buf = self.message_buf[total_message_len:]` — consume ([divoom.py:334-335](divoom_lib/divoom.py:334))

Each slice is a fresh list copy. Under a frame-animation stream this is O(n²)
churn plus GC pressure.

**Fix:** make `message_buf` a `bytearray`, consume with `del buf[:n]` (in-place,
no realloc of the tail beyond the memmove), and parse via `int.from_bytes` on
slices of `bytes` only where needed. A `collections.deque`/ring buffer is
overkill here — a `bytearray` with `del buf[:n]` is the idiomatic fast path.

### L2. Hex-string round-tripping on the send path ✅
`_make_message` / `_make_message_ios_le` build the frame as a **hex string**
(`"".join(f"{b:02x}" ...)`, [divoom.py:618](divoom_lib/divoom.py:618),
[divoom.py:639](divoom_lib/divoom.py:639)), and the senders immediately do
`bytes.fromhex(full_message_hex)` ([divoom.py:517](divoom_lib/divoom.py:517),
[divoom.py:561](divoom_lib/divoom.py:561)). Chunking also slices the hex string
by `*2` offsets ([divoom.py:533-539](divoom_lib/divoom.py:533)). We allocate a
string twice the size of the payload only to parse it back to bytes.

**Fix:** builders should return `bytes`/`bytearray`. Chunk on byte boundaries
(`mv = memoryview(buf); mv[i:i+n]`). Keep hex strictly for log lines, guarded by
`logger.isEnabledFor(logging.DEBUG)` so the formatting is skipped when DEBUG is off.

### L3. Logging cost in the hot path ⚠️
`_notification_handler` and `_handle_basic_protocol_notification` call
`data.hex()` / `bytes(message).hex()` unconditionally across ~6 log lines per
notification ([divoom.py:254-261](divoom_lib/divoom.py:254)). Even at INFO level
the `.hex()` allocations run. This compounds L1/L2.

**Fix:** wrap hex formatting in `isEnabledFor` guards or pass lazy `%`-style args
to the logger; drop the duplicate "THIS IS MY NOTIFICATION HANDLER" debug noise.

### L4. Connection robustness / retry ⚠️
`connect()` re-instantiates `BleakClient(self.mac)` when the address changes
([divoom.py:212-213](divoom_lib/divoom.py:212)) and wraps failures into a plain
`ConnectionError` ([divoom.py:221](divoom_lib/divoom.py:221)). `_send_payload`
has a retry loop ([divoom.py:479-512](divoom_lib/divoom.py:477)) but with a
**fixed** `retry_delay=0.1` — no exponential backoff, and `max_reconnect_attempts`
/ `reconnect_delay` fields are stored but never used.

**Fix:** centralize reconnect in a small state machine with exponential backoff
+ jitter; actually consume `max_reconnect_attempts` / `reconnect_delay`. Hard
`await asyncio.sleep(1.0)` after connect ([divoom.py:229](divoom_lib/divoom.py:229))
should be a documented constant, ideally replaced by a readiness check.

### L5. Sync disk I/O on the event loop ✅
`utils/cache.py` uses blocking `open()` + `json.load`/`json.dump`
([cache.py:16-30](divoom_lib/utils/cache.py:16)). These are called from
`async` methods — `_send_diagnostic_payload`, `_handle_cached_payload`,
`set_canonical_light` ([divoom.py:665](divoom_lib/divoom.py:665),
[divoom.py:796](divoom_lib/divoom.py:796), etc.). A slow flush stalls the event
loop and can drop incoming BLE notifications.

**Fix:** wrap cache reads/writes in `await asyncio.to_thread(...)`, or make the
cache module async (`aiofiles`). Keep the `except OSError: pass` swallowing
behavior but log at debug.

### L6. `_wait_for_response` busy-polls ⚠️
It loops `get_nowait()` + `asyncio.sleep(0.1)`
([divoom.py:377-394](divoom_lib/divoom.py:373)) instead of awaiting the queue
with a timeout. Functionally fine, but a `asyncio.wait_for(queue.get(), ...)`
loop is cleaner and lower-latency.

---

## 🛠️ Uncle Bob — SOLID & clean code

### B1. `Divoom` God Object + circular coupling ✅
`__init__` constructs ~20 sub-modules and passes `self` to each
([divoom.py:130-154](divoom_lib/divoom.py:130)); each module stores it back
(`self._divoom = divoom`, e.g. [light.py:42](divoom_lib/display/light.py:42))
and calls `divoom.connect()` / `divoom.send_command(...)`. This is a bidirectional
dependency: nothing can be unit-tested without a full `Divoom`.

**Fix:** extract a narrow `CommandSender` protocol (Python `typing.Protocol`)
exposing only `send_command`, `send_command_and_wait_for_response`,
`is_connected`, `logger`. Modules depend on the protocol; `Divoom` (or a
dedicated transport object) implements it. Inverts the dependency, makes modules
testable with a tiny fake.

### B2. Dual-mode constructor (SRP) ✅
`__init__(config=None, mac=None, logger=None, **kwargs)` branches on type and
even treats a `str` `config` as a MAC ([divoom.py:73-101](divoom_lib/divoom.py:73)).
Two construction contracts in one signature.

**Fix:** keep the canonical `__init__(config: DivoomConfig)` clean and add
classmethods `Divoom.from_config(cfg)` / `Divoom.from_mac(mac, **opts)`. The
legacy kwarg path becomes a thin shim in `from_mac`.

### B3. Stringly-typed exceptions ✅
`raise ValueError("No MAC address...")` / `raise ConnectionError(...)`
([divoom.py:202](divoom_lib/divoom.py:202),
[divoom.py:206](divoom_lib/divoom.py:206),
[divoom.py:221](divoom_lib/divoom.py:221)). Consumers must match on message text.

**Fix:** add a `divoom_lib/exceptions.py` with a `DivoomError` base and
`DeviceAddressMissingError`, `CharacteristicConfigError`,
`DeviceConnectionError`, `CharacteristicDiscoveryError`. Raise those (subclassing
the current built-ins for one release keeps `except ValueError` working).

### B4. Protocol concerns live in the orchestrator ⚠️
Framing, escaping, checksum, chunking, and notification parsing all sit on the
`Divoom` class ([divoom.py:574-639](divoom_lib/divoom.py:574)) alongside
connection management and the module registry. A `protocol.py` already exists in
the tree — the framing/parse logic should move there as pure functions
(`encode_basic(payload) -> bytes`, `decode_basic(buf) -> list[Frame]`), leaving
`Divoom` to orchestrate transport only.

### B5. Untracked duplicate/legacy modules in the tree ⚠️
`git status` shows untracked `divoom_lib/alarm.py`, `base.py`, `game.py`,
`light.py`, `music.py`, `sleep.py`, `tool.py`, `timeplan.py`,
`divoom_protocol.py`, plus `channels/`, `commands/`, `drawing/` — many of which
duplicate the committed `display/`, `scheduling/`, `media/`, `tools/` packages.
This is confusing and risks import-shadowing. Decide which layout is canonical
and delete the rest before doing anything else.

---

## 📊 Tradeoff summary

| Aspect | Current | Pragmatic target | Clean target |
|---|---|---|---|
| Receive buffer | `list[int]`, re-sliced | `bytearray` + `del buf[:n]` | typed `Frame` decoder |
| Send framing | hex string → `bytes.fromhex` | build `bytes` directly | `protocol.encode_*` pure fns |
| Cache I/O | sync `open`/`json` in async | `asyncio.to_thread` | repository abstraction |
| Construction | dual `__init__` shim | one ctor | `from_config` / `from_mac` factories |
| Coupling | circular `Divoom` ↔ modules | flat handle | `CommandSender` Protocol (DIP) |
| Errors | `ValueError`/`ConnectionError` strings | — | domain exception hierarchy |

---

## ⚠️ Constraints discovered during verification

Before executing the plan I traced imports and ran the suite. Two assumptions in
the original review turned out to be wrong — recorded here so the plan stays honest:

1. **The top-level modules were backward-compat shims (resolved).**
   - `base.py`, `constants.py`, `divoom_protocol.py`, `music.py`, `sleep.py`,
     `alarm.py`, `timeplan.py`, `light.py`, and `drawing/*` were all
     **backward-compat shims** re-exporting from the sub-package structure.
   - **All deleted.** Imports now point directly to canonical locations
     (`divoom_lib.divoom`, `divoom_lib.models`, `divoom_lib.display.*`,
     `divoom_lib.media.*`, `divoom_lib.scheduling.*`).

2. **There is no green baseline.** Current state: channels tests ~25 failures,
   `test_divoom_protocol_utils` 8 fails, `test_converters` 2, plus several
   `test_*_functions.py` files that **crash the interpreter** via a macOS
   Bluetooth/TCC privacy violation (they construct a real `BleakClient`/scanner
   at import/setup — an environment + test-design problem, not a perf bug).

3. **Green island that covers the perf targets:** `test_protocol.py` (21✓),
   `test_base.py` (35✓), `test_divoom_protocol.py` (17✓), `test_divoom.py` (7✓),
   plus `test_divoom_protocol_extended.py` (8✓), `test_drawing.py`,
   `test_text.py`, `test_drawing_functions.py`, `test_text_functions.py` (19✓).
   **But** these pin current representations as contracts:
   - `_make_message(...) == "010a00...02"` — asserts a **hex string** return.
   - `message_buf == []` — asserts a **list**.

   ⇒ **L1 (bytearray buffer) and L2 (byte-native builders) cannot be done without
   editing these test assertions.** On a mid-migration codebase with known-broken
   tests, rewriting green-test contracts is a decision to make explicitly, not a
   silent refactor. L3 has no such conflict.

## 🔧 Remediation plan (ordered)

Each phase is independently shippable and keeps the public API working.

### Phase 0 — Hygiene (DONE)
- [x] Migration direction decided (top-level → subpackages).
- [x] All backward-compat shims (`base.py`, `constants.py`, `divoom_protocol.py`,
      `light.py`, `music.py`, `sleep.py`, `alarm.py`, `timeplan.py`, `drawing/*`)
      deleted. Imports updated to canonical paths.
- [x] Legacy `channels/` and `commands/` migrated into `display/` and `system/`.
- [x] Green island is 109 passed / 15 skipped (expanded).

### Phase 1 — Hot-path performance (Linus) — DONE
Applied to **both** `divoom.py` (`Divoom`) and `protocol.py` (`DivoomProtocol`),
which are parallel implementations the test suite exercises separately.
- [x] **L3:** guarded every `.hex()` log call in the notification handlers and
      send path behind `logger.isEnabledFor(...)`, converted to lazy `%`-args,
      removed `"THIS IS MY NOTIFICATION HANDLER"` + duplicate log noise.
- [x] **L1:** `message_buf` is now a `bytearray`; junk-trim and message-consume
      use `del self.message_buf[:n]` (in-place, no tail reallocation). Test
      assertions updated: `message_buf == bytearray()`, `== incomplete_message`.
- [x] **L2:** `_make_message` / `_make_message_ios_le` now return `bytes`
      (built via a `bytearray`); senders chunk on byte boundaries and write bytes
      directly — no more hex-string round-trip. `_int2hexlittle`/`_getCRC` kept
      intact (used by drawing/channels). Test assertions updated to `.hex() ==`.
- [ ] Optional follow-up: parser micro-benchmark feeding a multi-frame stream.

**Verification:** green island (`test_protocol`, `test_base`,
`test_divoom_protocol`, `test_divoom`) = 80 passed / 15 skipped. Full suite
unchanged from baseline at **39 failed / 179 passed / 72 skipped** — zero
regressions; the 39 are pre-existing migration failures in untouched files.

### Phase 0.5 — Test baseline (DONE)
- [x] Added `tests/conftest.py`: hardware integration tests (13 modules that call
      `discover_device()` against a real BLE device) are skipped by default,
      runnable with `--run-hardware`. This stops the macOS TCC abort that was
      killing the whole interpreter, so a real pass/fail baseline now exists.

### Phase 2 — Async I/O correctness (Linus) — DONE
- [x] L5: `cache.load/save` calls in the diagnostic/probe methods now go through
      `asyncio.to_thread`, so disk flushes don't stall the BLE event loop.
- [x] L6: `_wait_for_response` / `wait_for_response` now block on
      `asyncio.wait_for(queue.get(), remaining)` instead of polling with
      `get_nowait()` + `sleep(0.1)`. Same discard/generic-ACK semantics retained.
- [x] L4: `_send_payload` uses exponential backoff (`retry_delay * 2**attempt`)
      between attempts in both implementations.
  - Note: `max_reconnect_attempts` / `reconnect_delay` fields remain unused —
    reconciling them vs `max_retries`/`retry_delay` is a small design decision
    left as follow-up; they're harmless as-is.

### Phase 3 — Exceptions (Uncle Bob) — DONE
- [x] B3: added [exceptions.py](divoom_lib/exceptions.py) with `DivoomError` base
      and `DeviceAddressMissingError` / `CharacteristicConfigError` /
      `DeviceConnectionError`, each subclassing the historical built-in
      (`ValueError`/`ConnectionError`) with identical messages — so existing
      handlers and message-matching tests keep passing. Raised from `connect()`
      in both `divoom.py` and `protocol.py`; exported from the package.

### Phase 4 — Decoupling (Uncle Bob) — DONE
- [x] B4: moved framing/escaping/checksum/parse into shared pure functions
      (`divoom_lib/framing.py`).
- [x] B1: defined `CommandSender` `Protocol` (`divoom_lib/sender_protocol.py`);
      all sub-package modules typed against it.
- [x] **Collapse the duplicate `Divoom` (`divoom.py`) / `DivoomProtocol`
      (`protocol.py`)**: `DivoomProtocol` now inherits from `Divoom`; `protocol.py`
      reduced from 437 lines to 8-line backward-compat subclass.
- [x] B2: added factory classmethods `Divoom.from_config` / `Divoom.from_mac`.

### Phase 5 — Housecleaning (DONE)
- [x] **Remove all backward-compat shims** (11 files): `base.py`, `constants.py`,
      `divoom_protocol.py`, `light.py`, `music.py`, `sleep.py`, `alarm.py`,
      `timeplan.py`, plus `drawing/` directory (3 files). All test/example imports
      updated to canonical `divoom_lib.{divoom|models|display.*|media.*|scheduling.*}`.
- [x] **Fix `self._divoom` → `self.communicator`** in `display/{light,animation,drawing,text}.py`:
      stored attribute renamed to match the Protocol type annotation.
- [x] **Fix `test_drawing.py` / `test_text.py` assertions**: updated `send_command`
      assertion expectations to numeric command IDs (sub-package resolves command
      strings before calling).
- [x] **Migrate `drawing/` directory**: merged `DisplayAnimation` → `display/display_animation.py`,
      `DisplayText` → `display/display_text.py`. Removed backward-compat shims.
- [x] **Simplify `_get_cache_module`**: removed `divoom_protocol` fallback since
      that module no longer exists.
- [x] **Migrate `channels/` → `display/`**: moved CloudChannel, CustomChannel,
      LightningChannel, ScoreBoardChannel, TimeChannel, VJEffectChannel.
      Deleted `channels/` directory.
- [x] **Migrate `commands/` → `system/`**: moved DateTimeCommand → `system/date_time.py`,
      TempWeatherCommand → `system/temp_weather.py`. Deleted `commands/` directory.
- [x] **Green island**: expanded to 109 passed / 15 skipped / 0 failed (includes
      `test_divoom_protocol_extended.py`, `test_drawing.py`, `test_text.py`,
      `test_drawing_functions.py`, `test_text_functions.py`).
- [x] Full suite progressed from 36 failed → see Phase 6 below (now fully green).

### Phase 6 — Remaining failures fixed (DONE)
- [x] The 36 pre-existing failures (channel tests, `test_converters`,
      `test_divoom_protocol_utils`) have since been resolved.
- [x] **Full suite now: 218 passed / 0 failed / 72 skipped** (290 collected; the
      72 skips are the hardware integration tests, run with `--run-hardware`).

### Verification gates
- Test suite green after every phase.
- A real-device smoke test (light on/off, a frame push) after Phase 1 and 2,
  since those touch the wire format and event loop directly.
- Full suite = **218 passed / 0 failed / 72 skipped** (no regressions allowed).

---

## 📒 Execution log (per step)

Chronological record of what was changed and the verification result after each
step. "Green island" early on = `test_protocol.py` + `test_base.py` +
`test_divoom_protocol.py` + `test_divoom.py` (80 passed / 15 skipped);
later expanded to 109 passed / 15 skipped.
"Full suite" baseline after the conftest fix = **39 failed / 179 passed / 72
skipped**; settled at **36 failed / 182 passed / 72 skipped** after Phase 5
(shim deletion uncovered 3 previously-collected-but-not-run channel tests).

### Step 1 — Verify the review against the code
- Traced imports and read `divoom.py`, `cache.py`, module wiring.
- Outcome: confirmed L1/L2/L3/L5/B1/B2/B3; **disproved B5** (untracked modules
  are shims + live code, not deletable). Recorded in *Constraints discovered*.

### Step 2 — Establish a runnable baseline (Phase 0.5)
- **Added** [tests/conftest.py](../tests/conftest.py): `pytest_collection_modifyitems`
  skips the 13 hardware modules that call `discover_device()`; added
  `--run-hardware` opt-in flag.
- Why: those tests instantiate a real `BleakScanner` → macOS TCC privacy
  violation → **whole interpreter aborts**, so no baseline could be measured.
- Verify: full suite now runs to completion → **39 failed / 179 passed / 72
  skipped** (first real baseline).

### Step 3 — L3: guard hot-path logging
- **Edited** `divoom.py` `_notification_handler`, `_handle_ios_le_notification`,
  `_handle_basic_protocol_notification`, both send paths; same in `protocol.py`.
- Change: wrapped every `.hex()` log call in `logger.isEnabledFor(...)`, switched
  to lazy `%`-args, deleted `"THIS IS MY NOTIFICATION HANDLER"` + duplicate lines.
- Verify: green island 80/15. ✅

### Step 4 — L1: bytearray receive buffer
- **Edited** `divoom.py` + `protocol.py`: `self.message_buf = bytearray()`;
  junk-trim and consume use `del self.message_buf[:n]`; `message = bytes(...)`.
- **Edited tests:** `test_protocol.py:33` and `test_base.py:56`
  `== []` → `== bytearray()`; `test_base.py:356` `== list(...)` → `== <bytearray>`.
- Gotcha found: `test_protocol.py` exercises a **separate** `DivoomProtocol`
  class in `protocol.py` — had to apply the change there too.
- Verify: green island 80/15. ✅

### Step 5 — L2: byte-native frame builders + senders
- **Edited** `divoom.py` + `protocol.py`: `_make_message` / `_make_message_ios_le`
  build a `bytearray` and return `bytes`; senders chunk on byte boundaries and
  write bytes directly (removed `bytes.fromhex` round-trip). Kept
  `_int2hexlittle`/`_getCRC` (used by `drawing/`, `channels/`).
- **Edited tests:** `test_protocol.py:42,52,61` and `test_base.py:557,567,575`
  `== "<hex>"` → `.hex() == "<hex>"`.
- Verify: green island 80/15; full suite 39/179 (no regressions). ✅

### Step 6 — Phase 3: domain exceptions (B3)
- **Added** [divoom_lib/exceptions.py](../divoom_lib/exceptions.py):
  `DivoomError` + `DeviceAddressMissingError(ValueError)`,
  `CharacteristicConfigError(ValueError)`, `DeviceConnectionError(ConnectionError)`.
- **Edited** `connect()` in `divoom.py` + `protocol.py` to raise them (messages
  unchanged, so `match=`-based tests pass); exported from `__init__.py`.
- Verify: green island 80/15 (incl. `test_base.py` connect-error tests). ✅

### Step 7 — L6: await the queue instead of polling
- **Edited** `_wait_for_response` (`divoom.py`) / `wait_for_response`
  (`protocol.py`): replaced `get_nowait()` + `sleep(0.1)` loop with
  `asyncio.wait_for(queue.get(), remaining)`; preserved discard + generic-ACK
  semantics. `test_wait_for_response_timeout` (timeout=0.1) still fast. ✅

### Step 8 — L5: async cache I/O
- **Edited** `divoom.py` (7 call sites): `cache_mod.save/load_device_cache(...)`
  → `await asyncio.to_thread(cache_mod.<fn>, ...)`.
- Verify: full suite 39/179 (the red `test_divoom_protocol_utils` failures are a
  pre-existing positional-vs-kwarg mismatch, unaffected). ✅

### Step 9 — L4: exponential backoff
- **Edited** `_send_payload` (`divoom.py`) / `send_payload` (`protocol.py`):
  `backoff = retry_delay * (2 ** attempt)`; all inter-attempt sleeps use it.
- Note: `max_reconnect_attempts` / `reconnect_delay` still unused (follow-up).
- Verify: full suite 39/179. ✅

### Step 10 — B2: construction factories
- **Added** `Divoom.from_config(config)` and `Divoom.from_mac(mac, **opts)`
  classmethods (`__init__` left intact for backward compatibility).
- Verify: smoke-constructed both; green island 63/15 on the subset run. ✅

### Step 11 — B4: extract framing to shared pure functions
- Created `divoom_lib/framing.py` with `int2hexlittle`, `escape_payload`,
  `get_checksum`, `encode_basic_payload`, `encode_ios_le_payload`,
  `parse_ios_le_notification`, `parse_basic_protocol_frames`.
- Both `Divoom` and `DivoomProtocol` delegate to these pure functions.
- Notification handlers in both classes use the shared parse functions.
- Green island: 80 passed, 15 skipped (zero regressions).

### Step 12 — B1: CommandSender Protocol
- Created `divoom_lib/sender_protocol.py` with a `CommandSender`
  `typing.Protocol` exposing `send_command`, `send_command_and_wait_for_response`,
  `wait_for_response`, `convert_color`, `is_connected`, `logger`.
- All sub-package module constructors (`display/`, `system/`, `media/`,
  `scheduling/`, `tools/`, plus `tool.py`, `game.py`) type-hinted
  against `CommandSender`.
- Verified: `isinstance(fake, CommandSender)` passes; modules construct
  cleanly with a fake sender.
- Green island: 80 passed, 15 skipped (no regressions).

### Step 13 — Collapse duplicate Divoom/DivoomProtocol
- `DivoomProtocol` now inherits from `Divoom` instead of being a
  437-line standalone duplicate.
- `protocol.py` reduced to a thin 8-line backward-compat subclass.
- All shared protocol logic lives in `divoom_lib/framing.py`.
- Green island: 80 passed, 15 skipped (no regressions).

### Step 14 — Housecleaning: shim removal & test imports (Phase 5)
- **Verified:** full suite ran at **39 failed / 179 passed / 72 skipped** before changes.
- **Deleted 11 files**: `base.py`, `constants.py`, `divoom_protocol.py`, `light.py`,
  `music.py`, `sleep.py`, `alarm.py`, `timeplan.py`, `drawing/display_animation.py`,
  `drawing/display_text.py`, `drawing/__init__.py`.
- **Updated all test/example imports** from shim paths to canonical
  (`divoom_lib.divoom`, `divoom_lib.models`, `divoom_lib.display.*`,
  `divoom_lib.media.*`, `divoom_lib.scheduling.*`).
- **Fixed `test_divoom_protocol_extended.py`**: corrected `SPP_CHARACTERISTIC_UUID`
  assertion, updated all imports from shims.
- **Fixed `test_drawing.py` / `test_text.py`**: `send_command` assertion expectations
  updated to numeric command IDs.
- **Verify:** green island 109/15 (expanded), full suite **36/182/72**
  (3 more tests collected but pre-existing failures — expected from
  extended test module being importable again). ✅

### Step 15 — Remaining failures fixed; suite fully green (Phase 6)
- The 36 remaining pre-existing failures (channel tests, `test_converters`,
  `test_divoom_protocol_utils`) have since been resolved.
- **Verify:** full suite **218 passed / 0 failed / 72 skipped** (290 collected).
  All review items (L1–L6, B1–B4, dedup, housecleaning) are complete and the
  entire non-hardware suite is green. ✅
