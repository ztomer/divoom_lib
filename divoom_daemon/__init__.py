"""REFERENCE/FALLBACK — Rust `divoomd` is the default daemon (see
`divoom_daemon/daemon_client.py`, `DIVOOM_USE_RUST_DAEMON`). This Python daemon
is kept as the reference/fallback implementation per user directive (2026-06-28):
**do not delete it.** It remains in-tree for parity oracle + fallback when
`DIVOOM_USE_RUST_DAEMON=0` is set explicitly.

divoom_daemon — the headless, always-on Divoom agent.

Owns the device connection and all background device-driving (macOS notification
monitoring + routing, and — as R17 progresses — live widgets and gallery sync).
Exposes a Unix-socket event server; the GUI and menubar are thin clients of it.
See docs/PLANNING_ROUND17.md for the 3-way split (divoom_lib / divoom_daemon /
divoom_gui).
"""
