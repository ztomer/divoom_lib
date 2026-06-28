# Round 56 — Native Port: Divoom Cloud Authentication, Gallery Sync, & Monthly Best Scraper Loop

**Agent**: Gemini (Antigravity)  
**Date**: 2026-06-28

## Goal
Implement Divoom Cloud Authentication, token caching, Cloud Gallery sync API, and Monthly Best background scraper loop in the native Rust daemon (`divoomd`), matching the Python implementations in `divoom_auth.py` and `monthly_best_daemon.py`.

## Proposed Changes

### Cargo.toml
- Added `md-5` and `hmac` dependencies to dev-dependencies/dependencies.

### native-port/divoomd/src/cloud.rs [NEW]
- **Email Login**: Send `POST /UserLogin` to `https://appin.divoom-gz.com` with MD5-hashed password.
- **Guest HMAC Auth**: Sign server UTC time from `https://appin.divoom-gz.com/APP/GetServerUTC` using HMAC-MD5 with static key `DivoomBluetoothDevice<>?` and send `POST /User/NewGuest`.
- **Token Cache**: Read/write cached `Token` and `UserId` under `~/.config/divoom-control/auth_token.json` with 23h validity check and atomic 0o600 file creation.
- **Failure Cooldown**: Prevent hammering the Divoom cloud for 120s after auth fails.
- **Gallery Integration**: Implemented `fetch_gallery()` calling `/GetCategoryFileListV2` with token refresh retry logic.

### native-port/divoomd/src/monthly_best.rs [NEW]
- **Config & Normalization**: Implemented loader and validator for `~/.config/divoom-control/hotchannel.json`.
- **Magic 43 Container parsing**: Extracted embedded GIF animation payloads.
- **Monthly Best background loop**: Spawns at daemon startup, polling `hotchannel.json` dynamically and pushing items.

### native-port/divoomd/src/lib.rs
- Registered `pub mod cloud;` and `pub mod monthly_best;`.

### native-port/divoomd/src/daemon.rs
- Exposed `"get_credentials"`, `"get_cached_credentials"`, and `"fetch_gallery"` commands in the socket dispatch match statement.

### native-port/divoomd/src/device_call/basic.rs
- Implemented `"animation.stream_animation_8b"` command handler.

## Verification Plan

### Automated Tests
- Wrote 7 Rust unit tests verifying MD5 hashing, HMAC-MD5 signing, configuration parsing, cache lifecycle, failure cooldowns, Magic 43 parsing, and hotchannel configuration loading. All 7 pass.
- Shipped `test_rust_cloud_auth_endpoints` and `test_rust_fetch_gallery` in `tests/test_rust_daemon_parity.py` verifying socket retrieval of cloud credentials and categories over the Unix socket.

## Outcome
- Successfully implemented cloud auth backend, token caching, gallery API retrieval, and Monthly Best headless sync loop natively in Rust. Exposes all endpoints over the IPC socket. All unit and parity tests are green.

