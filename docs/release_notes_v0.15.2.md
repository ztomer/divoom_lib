# Divoom Control v0.15.2

A UI/UX polish release over v0.15.1 — the sidebar device area, the channel
previews, and a clean app quit.

## Install

```
brew upgrade --cask ztomer/tap/divoom-control   # or: brew install --cask ztomer/tap/divoom-control
```

Or download `Divoom-v0.15.2.dmg` below and drag `Divoom.app` to `/Applications`.

## What's new

- **Device selector → named chips.** The unlabeled colored dots are now
  self-labeling rows (color dot + device name + live state), so every screen is
  identifiable at a glance and the list scales past four devices.
- **Flat, face-on device preview.** The 3/4 product photos made composited live
  frames land crooked; the preview now shows the screen content straight in a
  neutral bezel — aligned for any model — and the device PNGs got real
  transparency (the baked-in checkerboard background is gone).
- **Specific channel previews.** The preview now shows the exact clock face you
  picked (all six styles, in your color) and the actual ambient mode
  (Plain / Love / Plants / Sleeping / No-Mosquito), instead of a generic glyph.
- **Real device-face thumbnails in the menu bar.** Per-device menu-bar tiles show
  the actual face each screen is displaying, falling back to a glyph when there's
  no preview.
- **Virtual Wall button** gets a distinct "joined panels" glyph (no longer the
  Pixel Art icon) and folds the screen count into its label.
- **Tidier sidebar.** The scan indicator is pinned to the bottom (so a scan no
  longer nudges the preview), the connection dot moved to an unobtrusive
  lower-right corner, and the Auto-Sync device list fits more screens without
  scrolling.
- **Clean app quit.** Quitting no longer leaves the host process lingering or
  produces a shutdown cascade in the logs — one shutdown, immediate exit.

See `CHANGELOG.md` for the full list.
