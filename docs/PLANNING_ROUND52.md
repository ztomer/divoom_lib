# Round 52 — Native Port: Align Notification Service, Command Schemas, and TCP/Token Auth

**Agent**: Gemini (Antigravity)  
**Date**: 2026-06-28

## Goal
Align the native Rust daemon's macOS notification service, routing table, and command response JSON schemas with the ground-truth Python daemon. Port the headless TCP network server listener and token authentication features to achieve complete parity.

## Proposed Changes

### native-port/divoomd/src/macos_notifications.rs
- Refactor the macOS notifications monitor to query the database using the read-only `rusqlite` connection directly.
- Walk candidate paths to find Sonoma/Sequoia `DARWIN_USER_DIR` databases and the group container fallback `~/Library/Group Containers/group.com.apple.usernoted/db2/db`.
- Parse binary plists using `plist::from_bytes` to read `app` (bundle ID), `req.titl`, and `req.body`.
- Implement routing rules, seen/routed/dropped counters, duplicate suppression, and error streak health checks.
- Add `load_routing_rules()`, `save_routing_rules()`, and `set_routing()` helpers.

### native-port/divoomd/src/daemon.rs
- Wire the updated macOS notifications `status_event()`, `notification_status()`, `set_routing()`, and start/stop monitor functions in the command dispatcher.
- Ensure the output JSON schemas match the Python daemon exactly.
- Relocate `DeviceTransport` to `src/transport.rs` and simplify argument parsing to satisfy the 500 LOC limit constraint (daemon.rs is now 443 lines).

### native-port/divoomd/src/main.rs
- Add argument parsing for `--host`, `--port`, and `--token` (with environment variable fallback).
- Require a non-empty token for binding to a TCP port, and wire TcpListener concurrently with UnixListener.

### native-port/divoomd/src/socket_server.rs
- Make `serve_connection` generic over the stream type (`AsyncRead + AsyncWrite + Unpin`) to serve both UnixStream and TcpStream.
- Add `serve_tcp` and implement constant-time comparison helper `constant_time_eq` for token verification.

### tests/test_rust_daemon_parity.py [NEW]
- Write Python integration tests that spin up the compiled Rust `divoomd` daemon and drive it using `DaemonClient` over both Unix and TCP (with correct, incorrect, and missing tokens) to verify response parity and security.

## Verification Plan

### Automated Tests
- Run `cargo test` in `native-port/divoomd` to ensure all Rust tests pass.
- Run `python3 -m pytest tests/test_daemon_server.py tests/test_rust_daemon_parity.py` to verify command parity and token auth security.

### Outcome
- All 51 Rust tests and 11 Python integration tests passed successfully. Parity confirmed.
