# Round 53 — Native Port: Add --mac CLI Option Support

**Agent**: Gemini (Antigravity)  
**Date**: 2026-06-28

## Goal
Add the `--mac` command-line argument to the native Rust daemon (`divoomd`) to match the Python daemon's CLI options, allowing the daemon to store a default target device MAC address on startup.

## Proposed Changes

### native-port/divoomd/src/main.rs
- Add `mac: Option<String>` to the `ConfigArgs` struct.
- Update `parse_args()` to support `--mac` and `--mac=` command-line options.
- Pass `args.mac` to `Daemon::new_with_mac()` during initialization.

### native-port/divoomd/src/daemon.rs
- Add `new_with_mac(default_mac: Option<String>)` constructor to the `Daemon` struct.
- Make `new()` delegate to `new_with_mac(None)` to avoid breaking existing unit tests.
- Update `device_status()` to return the configured default/current MAC address even when the device is disconnected, aligning with Python's schema behaviors.

### tests/test_rust_daemon_parity.py
- Add `test_rust_default_mac` integration test to assert the daemon correctly parses and returns the default MAC.

## Verification Plan

### Automated Tests
- Run `cargo test` in `native-port/divoomd` to ensure the compilation and existing test suite pass.
- Run `python3 -m pytest tests/test_rust_daemon_parity.py` to verify command parity.

## Outcome
- All 51 Rust tests and 12 Python integration tests passed successfully. Parity confirmed.
