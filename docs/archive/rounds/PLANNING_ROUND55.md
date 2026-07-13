# Round 55 — Native Port: Bluetooth Classic SPP Integration

**Agent**: Gemini (Antigravity)  
**Date**: 2026-06-28

## Goal
Implement Bluetooth Classic SPP (Serial Port Profile) support in the native Rust daemon (`divoomd`) via a lightweight Python subprocess bridge (`spp_bridge.py`), avoiding complex Objective-C private framework bindings in Rust and keeping codebases converged.

## Proposed Changes

### divoom_daemon/spp_bridge.py [NEW]
- Helper script to open `BTSppTransport` (Python) and bridge it to standard input/output with JSON-line protocol.
- Inputs `{"command": "write", "payload": [...]}` and outputs `{"type": "connected"}` or `{"type": "notification", "command_id": ..., "payload": [...]}`.

### native-port/divoomd/src/spp.rs [NEW]
- Struct `SppTransport` in Rust to spawn and communicate with `spp_bridge.py`.
- Implements `send_command`, `wait_for_response`, `wait_for_any_response`, `stream_animation_8b`, and `disconnect` methods.

### native-port/divoomd/src/transport.rs
- Add `DeviceTransport::Spp(SppTransport)` variant and delegate methods.

### native-port/divoomd/src/daemon_connect.rs
- Route to `SppTransport::connect()` in `cmd_connect` when `use_ios_le_protocol` is `false`.

### native-port/divoomd/src/art.rs & src/art_hot.rs & src/live_jobs.rs & src/daemon.rs & src/macos_notifications.rs
- Add `DeviceTransport::Spp` support to match blocks.

## Verification Plan

### Automated Tests
- Run `python3 -m pytest tests/test_rust_daemon_parity.py` and verify `test_rust_spp_connect_failure_integration` passes.
- Run `python3 -m pytest tests/test_rust_daemon_parity.py -s -v --run-hardware` and verify `test_rust_hardware_parity` successfully scans, connects, queries, set/gets brightness, and disconnects on live Divoom hardware (Tivoo-Max).

## Outcome
- Successfully integrated SPP support using a subprocess helper bridge. Verified that invalid connection attempts correctly trigger the SPP bridge, execute Python's proven `BTSppTransport`, and propagate errors gracefully.
- Successfully verified the native Rust daemon's end-to-end functionality against live physical hardware (Tivoo-Max) via the new `test_rust_hardware_parity` test. All tests are green.
