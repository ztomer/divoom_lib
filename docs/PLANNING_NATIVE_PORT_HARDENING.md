# Planning — Native Rust Port Hardening & Path to Python Archival

**Created:** 2026-06-28
**Owner:** any agent (Claude Code / opencode)
**Status:** open
**Context:** Post-R56 evaluation of the `native-port/divoomd` Rust daemon. The port
is functionally near-complete (status + shipped surface in `docs/ROADMAP.md` →
"Native Rust Port"). This plan closes the correctness/tooling/verification gaps
that block declaring parity and archiving the Python backend.

---

## Findings (evaluated against the tree, not just the handoff)

| # | Finding | Severity | Evidence |
|---|---------|----------|----------|
| 1 | `cargo build --no-default-features` (hardware-free core) **fails with 8 errors** — a regression against the documented `ble`-gate invariant. | **HIGH** | `mock_transport.rs:4` `use crate::ble::BleResult;` (unconditional); `wall.rs` refs `DeviceTransport::Ble`, `daemon.encoder()`, `send_command`; `live_jobs.rs:739-740` `send_command`. Landed in `e4bd424`. |
| 2 | **No CI runs cargo at all** — neither `cargo test` nor `--no-default-features`. The regression in #1 passed unnoticed. | **HIGH** | No `.github/workflows/*` references `cargo`/`divoomd`; `scripts/rust_coverage.sh` does not pass `--no-default-features`. |
| 3 | **500-LOC house rule violated** in the Rust tree, though docs claim it is fully enforced. | MEDIUM | `live_jobs.rs` = 965 LOC; `daemon.rs` = 502 LOC. |
| 4 | Cross-platform `btleplug` BLE stability (Windows/Linux) **unverified**. | MEDIUM | Roadmap §3.1; dev fleet is all-macOS. |
| 5 | MCP-via-Rust and exclusive-mode-via-Rust **not hardware-verified** end-to-end. | MEDIUM | Roadmap "Open workstreams"; only macOS/Tivoo-Max brightness path validated. |
| 6 | Python backend **archival/deprecation** not started (the end goal). | LOW (blocked) | Roadmap §3.2; gated on 1–5. |

Baseline that IS green: `cargo test` (default `ble`) → 62 pass; working tree clean;
no stubs/TODOs in `src/`.

---

## Phase 1 — Restore the hardware-free core build (no hardware needed)

**Goal:** `cargo build --no-default-features` and `cargo test --no-default-features`
both pass, restoring the documented "core builds/tests without BLE" invariant.

- [ ] **1.1** Relocate the shared result/error type out of the `ble`-gated module.
  Move `BleResult` (and its error type) from `ble.rs` to a non-gated module
  (`transport.rs` or a new `error.rs`); re-export from `ble` for compatibility so
  the `ble` build is unchanged.
- [ ] **1.2** Fix `mock_transport.rs` to import the relocated `BleResult` (no
  `crate::ble` dependency). MockTransport must compile in the no-ble core — that is
  its entire purpose.
- [ ] **1.3** Gate or abstract the ble-only references in `wall.rs`
  (`DeviceTransport::Ble`, `daemon.encoder()`, `send_command`) and `live_jobs.rs`
  (`send_command`). Prefer routing through a transport-trait method available in all
  builds over `#[cfg(feature = "ble")]` sprinkles; fall back to cfg-gating the
  ble-specific arms if a clean trait boundary is too large for this phase.
- [ ] **1.4** Verify both matrices locally:
  - `cargo test` → expect 62 pass.
  - `cargo test --no-default-features` → expect green (count TBD; record it).
- [ ] **1.5** Resolve the 9 existing `unused variable` warnings touched along the way
  (e.g. `wall.rs:41`, `wall.rs:443`, `art_hot.rs:101`) only if trivially in scope.

**Exit:** both feature matrices build and test green.

**STATUS: DONE (2026-06-28, commit `f7e0e7c`).** `cargo test` = 62 green;
`cargo test --no-default-features` = 62 green (was 8 compile errors). The fix went
further than 1.3 anticipated: rather than cfg-sprinkling `wall.rs`/`live_jobs.rs`,
the `DeviceTransport` method layer + `NativeEncoder` + `device_call` were all
un-gated (they only needed ble via the relocated `BleResult` + the `Ble` match
arms, which are now individually gated). Net effect: the full command surface +
MockTransport now build/test hardware-free — which is what unlocks Phase 4 Tier A.

---

## Phase 2 — CI gate so this cannot regress silently (no hardware needed)

**Goal:** the Phase 1 invariant is machine-enforced; #1-class regressions fail CI.

- [ ] **2.1** Add a `rust` CI job (`.github/workflows/`) that runs, against
  `native-port/divoomd`:
  - `cargo build --no-default-features`
  - `cargo test --no-default-features`
  - `cargo test` (default `ble`) — note: BLE deps must compile on the runner; if
    the BLE *stack* needs platform libs, keep the default-feature step build-only or
    on a macOS runner, and make the **no-default-features** step the always-on gate.
  - `cargo fmt --check` and `cargo clippy -- -D warnings` (optional but recommended).
- [ ] **2.2** Decide runner OS. Minimum: `--no-default-features` on `ubuntu-latest`
  (fast, hardware-free). Optional matrix: add `macos-latest` for the `ble` build.
- [ ] **2.3** Confirm the existing emoji gate still runs and add the Rust job
  alongside it (don't replace).

**Exit:** a push that breaks the no-ble core turns CI red.

**STATUS: DONE (2026-06-28, commit `762c6ad`).** Added two jobs to
`.github/workflows/tests.yml`: `rust-core` (ubuntu, `cargo test
--no-default-features --locked` — the regression gate, proves Linux-portable core
without btleplug/libdbus) and `rust-ble` (macos, builds libdivoom dylib + `cargo
test --locked` — full ble build on CoreBluetooth, FFI parity test active). Did not
add `-D warnings` to the no-ble job: it has ~17 structural dead-code warnings (ble-
only helpers in `art*`/encoder modules, legitimately unused without ble); gating on
them would force noise-suppression churn. fmt/clippy on the default build is a
future nicety, not required for the gate.

---

## Phase 3 — 500-LOC compliance in the Rust tree (no hardware needed)

**Goal:** every Rust source file < 500 LOC, matching the house rule; gate it.

- [ ] **3.1** Split `live_jobs.rs` (965) into cohesive submodules (e.g.
  `live_jobs/{mod,system,stocks,weather,music}.rs`), mirroring the Python
  live-job split. Keep public paths stable via `mod.rs` re-exports.
- [ ] **3.2** Trim `daemon.rs` (502) back under 500 — extract the smallest cohesive
  unit (likely a dispatch/status helper) into an existing or new module.
- [ ] **3.3** Extend the LOC check to the Rust tree (either add `native-port/**/*.rs`
  to whatever enforces the rule, or add a small check to the new CI job).
- [ ] **3.4** Re-run both test matrices; expect no behavior change.

**Exit:** `wc -l` over all `*.rs` shows max < 500; LOC rule is gated.

---

## Phase 4 — Hardware & cross-platform verification (needs hardware / other OSes)

**Goal:** prove parity for the paths not yet exercised end-to-end — maximizing
what runs WITHOUT user involvement, and isolating the irreducible
needs-a-human/needs-a-device residue so it's the only thing left.

**Key enabler (landed in Phase 1):** `device_call` + `MockTransport` now build and
test without the `ble` feature, and the daemon exposes a `{"mock": true}` connect
path. So the entire command surface — routing, wire-byte serialization, exclusive
gating, MCP round-trips — can be driven over the socket with **no hardware, no TCC,
no user**. Only *real-radio behavior on a real device on a real OS* genuinely needs
hardware. That splits Phase 4 into three tiers by how autonomous each can be.

### Tier A — fully autonomous, no hardware (the bulk; runs in CI)

Drives the real daemon binary over its socket with the device backed by
`MockTransport`. Asserts wire bytes + response shapes + gating logic. No TCC, no
device, no user. This is where most of "verification" actually lives.

- [ ] **4A.1 MCP-via-Rust (mock):** start the Rust daemon (`{"mock": true}`
  connect), run the MCP server against it, assert `tools/list` returns the full
  catalog and representative `tools/call` invocations route through `device_call`
  to the mock and produce the expected `(cmd_id, payload)` wire tuples.
- [ ] **4A.2 Exclusive-mode (mock):** over the socket, exercise
  acquire → second-acquire-rejected (honest steal-reject, no hang) → release →
  re-acquire, plus a wrong-token `device_call` rejection. Pure `command_queue`
  logic — hardware-independent (mirrors the Python R53 steal-reject teeth tests).
- [ ] **4A.3** Fold A.1/A.2 into `cargo test` (extend `mock_device_tests.rs`) and/or
  the Python `tests/test_rust_daemon_parity.py` so the Phase-2 CI gate covers them.

### Tier B — autonomous on macOS via the pre-granted `.app` (real device)

The TCC limit is that Claude's Bash-spawned BLE crashes (SIGABRT). The workaround
is already proven: `open "dist/Divoom Dev Daemon.app"` launches the daemon under
**its own** persisted Bluetooth grant (launchd, not a Bash child), then the agent
drives it over `/tmp/divoom.sock` with `DaemonClient` — **no per-run user action**,
provided the grant from the original one-time approval still holds for that binary.

- [ ] **4B.1** `open` the granted dev-daemon `.app`; over the socket run the real
  MCP-via-Rust and exclusive-mode sequences from Tier A against a real Pixoo —
  confirms the mock results hold on real radio.
- [ ] **4B.2** Run the live `test_rust_hardware_parity` (scan/connect/get+set
  brightness/disconnect) against the `.app`-launched Rust daemon.
- [ ] **4B.3** Autonomy caveat to record: if the `.app` is rebuilt/re-signed, its
  TCC identity may reset → one-time user re-grant. Keep a stable signed dev-daemon
  `.app` so Tier B stays user-free across runs. (This is the only place a human may
  re-enter, and only on identity change — not per run.)

### Tier C — not autonomable from this machine (cross-platform real radio)

Linux/Windows `btleplug` *runtime* stability needs real devices on those OSes,
which this macOS host can't provide. Automate everything short of the radio:

- [ ] **4C.1** CI: `cargo build --target x86_64-unknown-linux-gnu` /
  `x86_64-pc-windows-msvc` with `--features ble` (install `libdbus-1-dev` on the
  Linux runner) — proves the btleplug backends *compile* per-OS. Build-only, no
  device.
- [ ] **4C.2** Real-radio smoke on Linux/Windows is the irreducible residue: either
  offload to a self-hosted/cloud runner with a paired device, or accept as a
  documented manual step before Phase 5. **`log()`/note this gap explicitly** — do
  not let a green Tier-A/C build read as "cross-platform verified."

**Exit:** Tier A green in CI; Tier B green on a real Pixoo via the `.app` (no
per-run user action); Tier C compiles for Linux/Windows with the real-radio smoke
explicitly tracked as the only remaining human/device-bound item.

---

## Phase 5 — Python backend deprecation & archival (gated on 1–4)

**Goal:** make the Rust daemon the default and retire the Python daemon backend.

- [ ] **5.1** Flip `DIVOOM_USE_RUST_DAEMON` default to on (or remove the flag and
  spawn Rust by default) in `daemon_client.py` / GUI launcher.
- [ ] **5.2** Soak period: run the GUI + menubar + MCP against the Rust daemon for a
  defined window; confirm no parity regressions.
- [ ] **5.3** Archive `divoom_daemon/` Python backend (move under `archive/` or tag
  + delete), keeping `divoom_lib` only where still depended on (encoders, SPP
  bridge `spp_bridge.py`).
- [ ] **5.4** Update `README`, `ROADMAP.md`, `AGENTS.md` to declare Rust the
  authoritative daemon and Python the historical reference.

**Exit:** Rust is the default daemon; Python backend archived; docs updated.

---

## Sequencing & dependencies

```
Phase 1 (core build) ──► Phase 2 (CI gate) ──► Phase 3 (LOC) ──► Phase 4 ──► Phase 5 (archive)
   [DONE]                   [DONE]               no hardware       tiered      gated on all
```

Phases 1 + 2 are **DONE** (committed). Phase 3 is pure code/tooling. Phase 4 is now
mostly autonomous — Tier A runs hardware-free in CI, Tier B is user-free on macOS
via the granted `.app`, and only Tier C's cross-platform real-radio smoke is
genuinely human/device-bound. Phase 5 is gated on 1–4.

**Recommended next unit of work:** Phase 3 (LOC splits) then Phase 4 Tier A
(mock-driven MCP + exclusive-mode E2E in CI) — both land with no hardware.

---

## Per-round close-out checklist (per AGENTS.md CORE RULE)

After each phase lands:
1. Update `docs/SESSION_HANDOFF.md` ("Current state" + "Open threads").
2. Add a `CHANGELOG.md` entry and update this doc's checkboxes.
3. Commit each logical change; keep tests green and record pass/skip counts for
   **both** `cargo test` and `cargo test --no-default-features`, plus the Python
   suite (`python3 -m pytest`).
