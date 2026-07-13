# Round 54 — Native Port: Add Rust Daemon Auto-Spawn Option

**Agent**: Gemini (Antigravity)  
**Date**: 2026-06-28

## Goal
Add support for the environment variable `DIVOOM_USE_RUST_DAEMON` inside the Python daemon client / GUI launcher, enabling users to seamlessly run the entire project (GUI/menubar/TUI) backed by the native Rust daemon `divoomd` instead of the Python daemon.

## Proposed Changes

### divoom_daemon/daemon_client.py
- Modify `spawn_daemon()` to check for `DIVOOM_USE_RUST_DAEMON` env variable.
- Locate the compiled Rust `divoomd` binary at `native-port/divoomd/target/release/divoomd` (or `debug` folder, or `DIVOOM_RUST_BINARY` env override).
- Fallback to looking in the system PATH if no compiled binary is found in the workspace.
- Construct the command `cmd` using the Rust binary path and arguments `--socket <path>` and optionally `--mac <address>`.

## Verification Plan

### Automated Tests
- Run `python3 -m pytest tests/test_daemon_server.py` to ensure normal spawning (Python daemon) is unaffected.
- Set `DIVOOM_USE_RUST_DAEMON=1` and run the integration tests to verify the GUI/client correctly auto-spawns the Rust daemon.

## Outcome
- Spawning both the Python daemon (default) and the Rust daemon (`DIVOOM_USE_RUST_DAEMON=1`) works flawlessly. All 12 socket-level integration tests pass cleanly in both modes.
