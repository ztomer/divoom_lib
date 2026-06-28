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

**Goal:** prove real-device parity for the paths not yet exercised end-to-end.
**Harness note:** per project memory, Claude cannot run BLE from the shell (TCC
crash). The user starts the daemon (or the granted `.app`); the agent drives it
over the Unix/TCP socket with `DaemonClient`.

- [ ] **4.1** MCP-via-Rust: drive `divoom-control mcp-server` against the Rust
  daemon through a real device; confirm tools/list + tools/call round-trip.
- [ ] **4.2** Exclusive-mode-via-Rust: run a multi-step exclusive sequence through
  the proxy exclusive context against real hardware; confirm token gating + honest
  steal-reject (parity with the Python fixes R53 round-25/HW rounds).
- [ ] **4.3** `btleplug` stability on Linux and Windows: scan, connect, get/set
  brightness, disconnect. Record per-OS results and any divergences.
- [ ] **4.4** Re-run the existing Python parity suite against the Rust daemon
  (`tests/test_rust_daemon_parity.py`) and the live `test_rust_hardware_parity`.

**Exit:** documented green results for MCP, exclusive mode, and ≥1 non-macOS BLE
platform.

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
Phase 1 (fix core build) ──► Phase 2 (CI gate) ──► Phase 3 (LOC) ──► Phase 4 (HW/x-platform) ──► Phase 5 (archive)
        no hardware              no hardware          no hardware         needs hardware            gated on all
```

Phases 1–3 are pure code/tooling and can land now. Phase 4 needs the user-driven
BLE harness and other OSes. Phase 5 is gated on 1–4.

**Recommended first unit of work:** Phase 1 + Phase 2 together — fix the regression
*and* add the gate that would have caught it, in one logical change.

---

## Per-round close-out checklist (per AGENTS.md CORE RULE)

After each phase lands:
1. Update `docs/SESSION_HANDOFF.md` ("Current state" + "Open threads").
2. Add a `CHANGELOG.md` entry and update this doc's checkboxes.
3. Commit each logical change; keep tests green and record pass/skip counts for
   **both** `cargo test` and `cargo test --no-default-features`, plus the Python
   suite (`python3 -m pytest`).
</content>
</invoke>
