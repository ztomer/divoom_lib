"""ARCHIVED (2026-07-13, explicit user sign-off) — the Python reference
implementation of the Divoom daemon SERVER. The Rust daemon (`divoomd/`) is
now the sole shipping daemon; this package is kept for historical reference
only and is no longer imported by any active code path (GUI, menubar, CLI,
MCP all talk to whichever daemon is running via the still-active
`divoom_daemon.daemon_client`/`divoom_daemon.daemon_protocol` socket client
— those two modules were NOT archived, since they're shared client
infrastructure, not server implementation).

This package is internally self-consistent (its own cross-imports were
rewritten to `archive.divoom_daemon.*`) and can still be run/imported
standalone for reference, but it is not exercised by the test suite or CI.

The original divoom_daemon — the headless, always-on Divoom agent (Python
implementation). Owned the device connection and all background
device-driving (macOS notification monitoring + routing, live widgets,
gallery sync) behind a Unix-socket event server. See
`docs/archive/rounds/PLANNING_ROUND17.md` for the original 3-way split
(divoom_lib / divoom_daemon / divoom_gui) this package was part of, and
`docs/ROADMAP.md`'s "Native Rust daemon" section for the parity/archival
history.
"""
