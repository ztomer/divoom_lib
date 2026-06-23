# PLANNING — Native port of the daemon

Status: evaluation + plan (2026-06-22). Decision: **Rust**. Scope assumption:
**daemon only** (the GUI/menubar stay Python and keep talking to the daemon over
the existing unix-socket NDJSON protocol). Cross-platform is treated as a real
goal (it is one of the stated criteria); the one assumption that would change the
recommendation is called out in "Open questions".

---

## 1. Why port at all

The daemon is the single owner of the device link (BLE + LAN + SPP), a command
queue, live-job pollers, image push, and a socket server. It is the long-running,
hardware-owning, always-on process — the part of the system where memory
footprint, startup, distribution, and safety matter most, and where the Python
runtime carries the most dead weight.

Measured, this session (live daemon, ~3 h uptime):

| Metric | Current Python daemon |
|---|---|
| Resident memory (RSS) | **~83 MB** (`84,592 KB`) |
| Shipped artifact | **78 MB** app bundle (`dist/Divoom.app`) |
| Runtime deps resident | CPython + bleak + pyobjc + pillow + numpy |

The session also surfaced a concrete operational cost of the Python+pyobjc
approach: the TCC Bluetooth grant is tied to process identity, which is why the
daemon can only run from a signed `.app` (the "Bash can't BLE / dev-daemon `.app`
owns Bluetooth" saga). A single signed native binary with a proper `Info.plist`
makes that grant stable and self-contained.

---

## 2. What the port must actually replace

The daemon is ~4,500 LOC (`divoom_daemon/`) over ~7,560 LOC of protocol /
transport / encoder code (`divoom_lib/`). It is **async I/O orchestration, not a
compute engine**. The runtime dependencies define the hard parts:

| Python dep | Role | Port difficulty |
|---|---|---|
| **bleak** | the reason the daemon exists — cross-platform BLE owner: scan / connect / notify / write-with-&-without-response, plus the protocol autoprobe | **dominant** |
| asyncio | command queue with exclusive mode, concurrent live-job pollers, socket server, pervasive timeouts | high |
| aiohttp | LAN HTTP transport + cloud file downloads | low |
| pillow + numpy | GIF/PNG decode + resize — **but the palette encode + downscale hot paths already run in C** (`libdivoom_compact.dylib`) | low–med |
| pyobjc | macOS-only: notification-DB monitor (SQLite), TCC, IOBluetooth RFCOMM (SPP) | macOS-only, isolatable |

Two consequences decide the language choice:

1. **Performance is not the bottleneck.** The workload is I/O-bound (BLE at tens
   of kbps, a unix socket, HTTP) and the CPU-heavy encode/downscale is already in
   C. All native candidates are "fast enough"; the practical speedup over today's
   Python+C-dylib hybrid is modest for a single device. The real wins are memory,
   startup, a single signed static binary, and removing the pyobjc/TCC fragility.
2. **The differentiators are cross-platform BLE and async fit** — not raw compute,
   not memory (all four candidates are tiny).

---

## 3. Language comparison (C / C++ / Rust / Zig)

| Criterion | Rust | C++ | C | Zig |
|---|---|---|---|---|
| Cross-platform BLE | **btleplug** — one async API over CoreBluetooth / BlueZ / WinRT (the direct analog of bleak) | **SimpleBLE** — real, smaller community; ObjC++ (`.mm`) gives clean CoreBluetooth interop | none — hand-write each OS backend | none — hand-write each OS backend |
| Async runtime | **tokio** — best-in-class, maps asyncio 1:1; btleplug is tokio-native | C++20 coroutines / asio — workable, immature ergonomics | manual epoll/kqueue or libuv | async removed in 0.11+; manual loops/threads |
| Memory use | ~2–8 MB | ~3–10 MB | ~1–5 MB | ~1–5 MB |
| Performance | all four far above Python; I/O-bound + hot paths already in C -> effectively tied | tied | tied | tied |
| Memory / thread safety | **compile-time guaranteed** | RAII helps; UAF/races still possible | fully manual (this repo already hit buffer-aliasing + under-alloc bugs in its C) | safety-checked builds; no borrow checker |
| JSON socket protocol | **serde** (best-in-class) | nlohmann/json | cJSON (manual) | std.json |
| Reuse existing C encoders | trivial FFI | direct compile-in | direct | trivial FFI |

Memory and performance — the two quantitative criteria — are met comfortably by
**all four** and do not break the tie (the footprint is dominated by the OS BLE
stack, not the language runtime; compute is already in C). The tie is broken by
**cross-platform BLE** and **async**, and both point to Rust.

### Decision: Rust

- **btleplug** is the only mature one-API-across-macOS/Linux/Windows BLE library
  among the four — it is the Rust bleak. That single fact carries the
  cross-platform criterion. C/Zig would mean hand-building three separate BLE
  backends; C++/SimpleBLE is viable but a smaller bet.
- **tokio** maps this asyncio-heavy daemon (futures, channels, `select!`,
  per-op timeouts, the exclusive command queue) almost line-for-line. C has no
  async; Zig's is currently gone; C++'s is the rough edge of the language.
- **Memory safety** matters here specifically: a 24/7 daemon that owns hardware,
  parses binary device frames, and speaks a socket protocol — exactly the profile
  where Rust removes a whole bug class this codebase has already been bitten by in
  its C.
- **serde** for the NDJSON protocol; trivial **FFI** to keep `libdivoom_compact`
  as-is initially.

Runner-up: **C++** (SimpleBLE + ObjC++ + asio) — only if maximizing C reuse and
staying in the C family outweighs giving up memory safety and best-in-class
async/JSON. **C and Zig are poor fits** for this daemon: both lack cross-platform
BLE, and the async gap is disqualifying for an orchestration-heavy service.

---

## 4. Rust vs the current Python implementation (across the criteria)

| Criterion | Python (today, measured/known) | Rust (projected) | Verdict |
|---|---|---|---|
| **Memory (RSS)** | ~83 MB live | ~2–8 MB (tokio + btleplug) | Rust **~10–40x** lower |
| **Shipped artifact** | 78 MB bundle (CPython + deps) | single static binary, ~3–6 MB | Rust far smaller, no interpreter to ship |
| **Startup** | hundreds of ms (import bleak/pyobjc/numpy/pillow) | sub-millisecond | Rust faster; matters for the restart-on-crash path |
| **Performance (single device)** | I/O-bound; hot paths already in C; GIL-serialized | same radio-bound latency; encode equal (C/native) | ~tied for one device |
| **Performance (multi-device / wall, tail latency)** | GIL caps true parallelism; GC-free but interpreter overhead per frame | true multicore via tokio; no GIL; lower tail latency | Rust ahead under load |
| **Cross-platform BLE** | bleak already covers mac/Linux/Windows (Python's strength) | btleplug covers the same | ~tied on BLE itself |
| **Cross-platform distribution** | heavy: per-OS py2app/pyinstaller, macOS-bound today via pyobjc | one binary, cross-compiled per target; macOS bits behind `cfg(macos)` | Rust much cleaner |
| **Memory/type safety** | dynamic; runtime errors; the C dylib is unchecked | compile-time memory + thread safety; FFI boundary is the only unsafe seam | Rust stronger |
| **macOS TCC / process identity** | grant tied to pyobjc process; needs signed `.app`; fragile (this session) | signed binary + `Info.plist` (`NSBluetoothAlwaysUsageDescription`); self-contained | Rust cleaner |
| **Ecosystem maturity for this job** | bleak/aiohttp/pillow are mature | btleplug/tokio/reqwest/serde/image are mature | ~tied |
| **Iteration speed / churn cost** | fastest to change; no compile; the whole test suite exists | compile step; rebuild the test harness | Python ahead (this is the main cost of porting) |

**Honest summary:** Rust wins decisively on **memory** (~10–40x), **distribution**
(single small binary vs 78 MB bundle), **safety**, and the **TCC/identity** pain
point; it is **roughly tied on single-device performance** (the workload is
radio-bound and the hot paths are already C) and **modestly ahead under
multi-device load**; **cross-platform BLE is a wash** (bleak and btleplug both
solve it) but **cross-platform distribution favors Rust**. The real cost of the
port is the **iteration/rewrite tax** — Python is faster to change and already has
the full test suite — which is exactly why the plan below is incremental and
keeps the Python clients in place.

---

## 5. Architecture: daemon-only port behind the socket seam

**Build strategy (directive): parallel, Python is ground truth.** The Rust daemon
is built ALONGSIDE the Python daemon, not as a replacement-in-progress. The Python
daemon stays the shipping, authoritative implementation (tagged v0.16.0 is the
ground-truth baseline) and keeps receiving fixes. The Rust daemon is switched in
ONLY when it is a 100% working, behavior-identical drop-in — proven by passing the
Python conformance suite over the socket (Phase 3) AND a real-hardware parity run.
Until then it is an independent, non-default target. Concretely:

- Both daemons speak the identical unix-socket NDJSON protocol, so either can sit
  behind the unchanged Python GUI/menubar/CLI. Switching is a launch choice (which
  binary owns `/tmp/divoom.sock`), reversible at any time.
- The Python suite (1700 tests) becomes the **conformance oracle**: the Rust daemon
  is correct when it produces byte-/field-identical socket responses for the same
  request stream, and identical device behavior on the Pixoo. No "trust me" cutover.
- No flag day: the Python daemon is never deleted until the Rust one has shipped and
  soaked. Roll back by relaunching the Python daemon.

The NDJSON-over-unix-socket protocol (`daemon_protocol.py`) is a language-agnostic
boundary. Port the daemon only; leave the Python GUI + menubar talking to it
unchanged. This lets the native daemon ship behind the existing clients and be
validated against real hardware at every step.

```
  divoom_gui (Python, pywebview)  ─┐
  divoom_menubar (Python, PyObjC) ─┼─ unix socket /tmp/divoom.sock (NDJSON) ─→  divoom-daemon (RUST)
  CLI / MCP clients               ─┘                                              owns BLE / LAN / SPP
```

Keep `libdivoom_compact` as-is and FFI to it from Rust for the encode/downscale
hot paths (port to native Rust later only if it earns its keep).

---

## 6. Phased plan (incremental, hardware-validated each step)

1. **Spike — DONE, PASSED (2026-06-23).** The signed native `.app` scanned, found
   a Ditoo, connected, and subscribed to notifications with no SIGKILL: a native
   binary gets the CoreBluetooth TCC grant. The BLE foundation is de-risked.
   **Runnable daemon binary** also landed (`src/main.rs` + `daemon.rs`): owns
   `/tmp/divoomd.sock` (distinct from Python's `/tmp/divoom.sock` so both coexist),
   serves the NDJSON protocol, SIGINT/SIGTERM cleanup, single-instance guard. The
   PYTHON DaemonClient drives it unchanged (ping/device_status/get_status + the
   real exclusive steal-reject); device commands honestly report unimplemented.
   48 tests green. Next: the BLE transport behind the `Handler`.

1. **Spike (de-risk the one real unknown)** — a Rust binary that does
   btleplug scan -> connect -> subscribe-notify -> write against the Pixoo, and
   proves the macOS TCC grant works for a *signed native binary* with
   `NSBluetoothAlwaysUsageDescription`. Scaffolded at `native-port/spike-ble/`.
   Until this passes on real hardware, do not commit to the full port.
2. **Protocol core** — port `framing` + `models` + the BLE notify/response
   correlation (autoprobe, `_expected_response_command`, generic-ACK 0x33) +
   `command_queue` (FIFO + exclusive mode, incl. the R53.x `acquire_now`
   steal-reject and the G3 idle release). FFI to the C encoders.
   - **[DONE] framing + models** (`native-port/divoomd/`): Basic + iOS-LE
     encode/parse, byte-identical to Python across 32 generated vectors
     (`gen_framing_vectors.py` -> `tests/framing_vectors.json`, asserted by
     `tests/framing_parity.rs`).
   - **[DONE] command_queue** (tokio): FIFO + exclusive gate + `acquire_now`
     steal-reject + G3 idle auto-release + item timeout. Behavioral port (not a
     line port — the thread/loop bridge is gone); 5 tests mirror
     `test_command_queue.py`.
   - **[DONE] notify/response correlation** (`response.rs`): the route-notification
     decision (generic-ACK 0x33 scalar-clear; listen-set priority) + `wait_for_response`
     / `wait_for_any_response`. 10 tests pin the two load-bearing rules from this
     session's iOS-LE revert and 0x8B fix.
   - **[DONE] COMMANDS map + NDJSON protocol** (`commands.rs`, `protocol.rs`):
     command name->id (generated, 109 entries) + encode_message/iter_messages,
     typed Request, ok/err replies. Cross-language test parses Python-encoded bytes.
3. **Socket server** (Phase 3) — NDJSON parity with `daemon_protocol.py`.
   - **[DONE] transport skeleton** (`socket_server.rs`): tokio UnixListener accept
     -> read NDJSON -> dispatch via a pluggable `Handler` -> reply, with the frame
     cap. 3 end-to-end tests over a real unix socket (request/reply, pipelined,
     malformed->error). Next (hardware-gated): the BTLE transport + device owner
     behind the Handler; until then the TCC spike remains the manual gate.
   _Original Phase 3 note:_ NDJSON parity with `daemon_protocol.py`.
   - **[DONE] FFI to C encoders** (`native_encode.rs`): animation_frame /
     static_image / frame_32 via libloading, byte-parity vs Python (21 vectors).
   - **[DONE] LAN validation** (`lan.rs`): body build + validate_response honesty.
   - **[DONE] autoprobe decision** (`autoprobe.rs`): iOS-LE -> Basic -> default.

**HARDWARE-INDEPENDENT LAYER COMPLETE (44 tests).** Everything portable without a
device is done: framing, models, response correlation, command_queue, commands,
NDJSON protocol, socket server, C-encoder FFI, LAN validation, autoprobe. The
remaining work is hardware-gated and starts at the TCC spike: the BTLE transport
(btleplug), the device owner (the `Handler` impl wiring queue + transport +
encoders), the LAN HTTP send (reqwest), and the macOS notification monitor.
3. **Socket server** — NDJSON parity with `daemon_protocol.py`. Drive the existing
   Python test suite's socket-level cases against the Rust daemon for behavioral
   parity (run the Python `DaemonClient` against the Rust server).
4. **Orchestration** — live-job pollers, wall delta reconfigure, hot-update
   (with the R53.x per-file `confirmed` honesty), custom-art (with
   `device_confirmed`), 0x8B animation streaming (incl. the retransmit-listen
   fix), LAN transport (reqwest).
5. **macOS extras behind `cfg(target_os = "macos")`** — notification-DB monitor
   (rusqlite over the `group.com.apple.usernoted` DB), TCC preflight. Decide
   whether SPP/RFCOMM is worth an ObjC++ shim or simply dropped (it is already the
   weak, deferred path; btleplug is BLE-only and does not cover classic SPP).

Each phase ends green against the real Pixoo-1 via the same dev-daemon-style
launch + socket-drive workflow used this session.

---

## 7. Risks & open questions

- **TCC for a signed native binary (highest risk)** — must confirm CoreBluetooth
  via btleplug gets (and keeps) the Bluetooth grant when launched as a signed
  binary/`.app`. This is exactly what the Phase-1 spike proves; everything else is
  comparatively mechanical.
- **SPP / classic Bluetooth** — btleplug is BLE-only. SPP (Ditoo-class) would need
  a separate per-platform classic path (macOS IOBluetooth via ObjC++). It is
  already deferred and weak; the cheap option is to drop it from the native daemon
  and keep the Python SPP path available, or document it unsupported.
- **Image decode** — pillow/numpy do GIF/PNG decode + resize. Rust `image` +
  `fast_image_resize` cover this; the palette encode stays in the C dylib via FFI.
  Validate byte-parity against the Python reference (the project already has a
  byte-parity harness for the encoders).
- **Cross-platform scope (the assumption that would flip the decision)** — if the
  target is **macOS-only forever**, cross-platform BLE stops mattering and **C++
  with ObjC++** becomes very competitive (cleanest direct CoreBluetooth interop,
  maximal C reuse). The recommendation here weights cross-platform as a real goal
  per the stated criteria.
- **Rewrite tax** — the Python suite (1700 tests) does not transfer for free.
  Mitigate by reusing it as a *black-box conformance suite* against the Rust
  daemon over the socket (Phase 3), so behavior is pinned without re-authoring
  every unit test up front.

---

## 8. The spike

See `native-port/spike-ble/` — a buildable Rust crate (btleplug + tokio) that
scans for the Pixoo, connects, subscribes to notifications, and sends the 0x46
"get light mode" query, printing the parsed reply. Build with `cargo build`; run
per the crate README (must be a signed binary with the Bluetooth usage string for
the TCC grant). This is Phase 1 — run it against the Pixoo before committing to
the rest.
