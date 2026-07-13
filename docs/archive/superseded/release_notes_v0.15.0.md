# Divoom Control v0.15.0

The first packaged release — a macOS control center for Divoom pixel displays
(Pixoo / Tivoo / Ditoo / Timoo) over Bluetooth LE and Wi-Fi/LAN, with a pywebview
GUI, a menu-bar agent, and a headless daemon that owns the device connection.

## Install

```
brew install --cask ztomer/tap/divoom-control
```

Or download `Divoom-v0.15.0.dmg` below and drag `Divoom.app` to `/Applications`.
On first scan, grant the Bluetooth permission prompt.

## Highlights

This release lands a large reliability pass on the daemon ↔ GUI ↔ device path:

- **Daemon-owned devices stay controllable** — a screen the daemon is streaming
  to (live widget) is always selectable in the GUI, with friendly names and a
  per-device menu-bar preview.
- **Virtual wall** — reconfiguring a wall keeps the shared screens connected
  (add/remove a panel in seconds, not a full reconnect); a screen is owned by the
  active link or the wall, never both.
- **Live widgets survive a daemon restart** — sysmon/stocks/weather/music jobs are
  persisted and resume automatically.
- **Robustness** — crash-safe config writes (no more corrupted credentials/presets
  on an unclean exit), credential files locked to `0600`, a BLE scan no longer
  freezes live widgets, and a crashed client can't wedge the device.

See `CHANGELOG.md` for the full list.
