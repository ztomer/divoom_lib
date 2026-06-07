"""divoom_daemon — the headless, always-on Divoom agent.

Owns the device connection and all background device-driving (macOS notification
monitoring + routing, and — as R17 progresses — live widgets and gallery sync).
Exposes a Unix-socket event server; the GUI and menubar are thin clients of it.
See docs/PLANNING_ROUND17.md for the 3-way split (divoom_lib / divoom_daemon /
divoom_gui).
"""
