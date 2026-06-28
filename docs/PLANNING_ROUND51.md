# Round 51 — Native Port: Live Jobs, Wall, Art Sync, & Notifications

**Agent**: Gemini (Antigravity)  
**Date**: 2026-06-23

## Goal
Implement the remaining native Rust daemon functionality to achieve 100% parity with the headless Python daemon, including:
1. **Live Jobs integration & wiring**: Register the `LiveJobCoordinator` in the daemon and wire the `live_job_*` and `*device_activity` commands.
2. **Multi-Panel Wall Coordinator (`src/wall.rs`)**: Coordinate mapping, delta configurations, image cropping/resizing, and parallel streaming. Keep under 500 LOC.
3. **Artwork Sync, Custom Art & Hot Updates (`src/art.rs`)**: Cloud downloads, slot programming, and hot update sync loops with confirmations. Keep under 500 LOC.
4. **macOS Notification Monitor (`src/macos_notifications.rs`)**: Polling usernoted SQLite DB, parsing plists, mapping app IDs, and socket event broadcasts. Keep under 500 LOC, gated by `#[cfg(target_os = "macos")]`.
5. **Full Dispatch Wiring**: Wire all remaining socket commands, ensuring all tests (Rust and Python) pass.

## Proposed Changes

### Cargo.toml
- Verify existing dependencies (`reqwest`, `rusqlite`, `plist`, `sysinfo`) are active (done).

### native-port/divoomd/src/daemon.rs
- Add `live_jobs: Arc<LiveJobCoordinator>` to `Daemon`.
- Wire `"live_job_start"`, `"live_job_stop"`, `"live_job_list"`, `"live_jobs_stop_for"`, `"set_device_activity"`, and `"get_device_activity"` in `Daemon::dispatch`.
- Wire remaining commands once their submodules are implemented.

### native-port/divoomd/src/wall.rs
- Implement `DivoomWall` coordinate mapping and parallel streaming/cropping.
- Ensure strict adherence to the 500 LOC limit.

### native-port/divoomd/src/art.rs
- Implement artwork downloading, custom art page programming, and hot updates syncing.
- Ensure strict adherence to the 500 LOC limit.

### native-port/divoomd/src/macos_notifications.rs
- Implement the macOS usernoted monitor, database queries, and plist processing.
- Ensure strict adherence to the 500 LOC limit.

## Verification Plan

### Automated Tests
- Run `cargo test` and `cargo test --no-default-features`.
- Run `python3 -m pytest` to verify integration parity.
