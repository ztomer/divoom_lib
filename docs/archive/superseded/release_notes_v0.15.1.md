# Divoom Control v0.15.1

A GUI/UX reliability update over v0.15.0.

## Install

```
brew upgrade --cask ztomer/tap/divoom-control   # or: brew install --cask ztomer/tap/divoom-control
```

Or download `Divoom-v0.15.1.dmg` below and drag `Divoom.app` to `/Applications`.

## What's fixed

- **Album-art / music live widget now works.** It controls Music/Spotify via
  AppleScript (macOS Automation); that prompt was raised invisibly by the
  background daemon, so it was denied and the widget got no track. The app now
  requests the permission up front, visibly, at launch — and the bundle declares
  the Automation usage.
- **Community gallery fetches the right resolution.** It was always requesting
  16px art; a 64px Pixoo now gets 64px artwork.
- **Connection state is always visible again.** The appbar connection dot was a
  ghost element after a past refactor, so a mid-session degraded or dropped link
  showed no indicator. Restored — it now shows connecting / active / degraded /
  disconnected.
- **Virtual Wall** is now a distinct, labeled button (with a grid glyph + screen
  count) in its own row, instead of an easy-to-miss extra dot.

Under the hood: a Playwright E2E "no knowledge gap" suite that asserts the UI
gives visible feedback at every state transition, plus a static audit that
removed dead element/handler references. See `CHANGELOG.md` for the full list.
