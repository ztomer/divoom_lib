# Divoom Control v0.20.0 — Native Rust Port Phase 2 & App Startup Fix (2026-06-22)

This release introduces the Phase 2 of the native Rust port (`divoomd` daemon) along with a critical bug fix for the packaged macOS app bundle.

## Fixes

- **Fixed `ModuleNotFoundError: No module named 'gui_api'` on startup.** 
  Corrected directory layout assumptions within `divoom_gui` imports so that the packaged `Divoom.app` starts up successfully under `py2app` without encountering import issues.
  
- **Single-Source Versioning.**
  The bundle version is now read dynamically from `pyproject.toml` rather than being hardcoded, preventing version drift during releases.

## Native Rust Port (Phase 2)

Significant progress has been made on the `divoomd` native Rust port:
- **Phase-1 BLE Spike:** Completed compilation check for `btleplug` and `tokio` integration.
- **Framing & Models:** Implemented framing and model serialization in Rust, ensuring they are byte-identical to the Python implementation.
- **Command Queue Parity:** Brought command queue implementation to behavioral parity using Tokio.
- **Notify/Response Correlation:** Completed correlation matching for async notifications and command responses in Rust.

## Verification

- Rebuilt the app bundle (`scripts/build_release.sh`) and confirmed successful startup of `dist/Divoom.app` without crashes.
- Ran the full test suite (`python3 -m pytest`) and verified all 1700 tests passed successfully.
