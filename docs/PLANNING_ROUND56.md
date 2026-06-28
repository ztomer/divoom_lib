# Round 56 — Native Port: Divoom Cloud Authentication & Caching

**Agent**: Gemini (Antigravity)  
**Date**: 2026-06-28

## Goal
Implement Divoom Cloud Authentication and token caching in the native Rust daemon (`divoomd`), matching the Python implementation in `divoom_auth.py`.

## Proposed Changes

### Cargo.toml
- Added `md-5` and `hmac` dependencies to dev-dependencies/dependencies.

### native-port/divoomd/src/cloud.rs [NEW]
- **Email Login**: Send `POST /UserLogin` to `https://appin.divoom-gz.com` with MD5-hashed password.
- **Guest HMAC Auth**: Sign server UTC time from `https://appin.divoom-gz.com/APP/GetServerUTC` using HMAC-MD5 with static key `DivoomBluetoothDevice<>?` and send `POST /User/NewGuest`.
- **Token Cache**: Read/write cached `Token` and `UserId` under `~/.config/divoom-control/auth_token.json` with 23h validity check and atomic 0o600 file creation.
- **Failure Cooldown**: Prevent hammering the Divoom cloud for 120s after auth fails.

### native-port/divoomd/src/lib.rs
- Registered `pub mod cloud;`.

### native-port/divoomd/src/daemon.rs
- Exposed `"get_credentials"` and `"get_cached_credentials"` commands in the socket dispatch match statement.

## Verification Plan

### Automated Tests
- Wrote 5 unit tests verifying MD5 hashing, HMAC-MD5 signing, config parsing, cache lifecycle, and failure cooldown. All 5 pass.
- Shipped `test_rust_cloud_auth_endpoints` in `tests/test_rust_daemon_parity.py` verifying socket retrieval of cached/fresh cloud credentials.

## Outcome
- Successfully implemented cloud auth backend and token caching natively in Rust. Exposed socket dispatch commands to let client proxy/GUI query credentials over the socket, eliminating local Python auth requirements. All unit and parity tests are green.
