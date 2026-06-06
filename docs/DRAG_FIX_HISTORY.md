# Window drag fix — history of attempts _(2026-06-06)_

> **Purpose:** document every drag fix attempt in this project, why
> each failed (or stuck), and what the final correct fix is. This is
> the source of truth for "why does the drag work the way it does
> today?" — including the upstream-detection contract that
> auto-deactivates the workaround when pywebview ships its own fix.
>
> **Audience:** future maintainers who will (a) be tempted to revert
> to a "simpler" custom JS/Python drag handler, or (b) wonder why
> `gui_main.py` has a 25-line block that monkey-patches a third-party
> library.
>
> **Pattern citations** (build-discipline): D2 (document the
> decision, not just the code), D3 (document the dead-ends), F4
> (plan → execute → document loop).

---

## TL;DR — current state

The frameless window drag works via **pywebview's bundled
drag-region mechanism** (CSS class `.pywebview-drag-region` on the
appbar) **plus a monkey-patch to the cocoa `BrowserView.move`** that
fixes an upstream coordinate-double-count bug
([pywebview#1820](https://github.com/r0x0r/pywebview/issues/1820),
May 2026). The monkey-patch is **idempotent**: it self-deactivates
the moment pywebview ships the upstream fix.

- `gui/gui_main.py:27-66` — `_pywebview_1820_bug_present()` source-
  based detection.
- `gui/gui_main.py:111-128` — gated application of the monkey-patch
  (only when the bug is still present).
- `gui/web_ui/index.html:24` — `<header class="integrated-appbar
  pywebview-drag-region">` (the JS-side hook).
- `gui/web_ui/app.js` — no custom drag handler (cleaned up).
- `gui/gui_api.py` — no `drag_window` method (cleaned up).
- `tests/test_gui_drag_instrumented.py` — 6 regression tests (4
  static guards + 2 detection-contract canaries).

---

## Why a drag fix was even needed

The Divoom Control Center uses pywebview's **frameless** mode with
a custom integrated appbar (`<header class="integrated-appbar">`).
pywebview's frameless mode gives you a window without the OS
titlebar; you're responsible for the chrome. The custom appbar
needs to act as a **drag region** so the user can move the window.

Three plausible drag mechanisms exist:

| Mechanism                                  | Code surface                  | Tradeoffs |
|--------------------------------------------|-------------------------------|-----------|
| **OS-native frameless drag** (`-webkit-app-region: drag`) | CSS only | Conflicts with interactive children (buttons, sliders). pywebview 6.2.1 has known issues with this on some macOS versions. |
| **pywebview's bundled drag-region** (`.pywebview-drag-region` CSS class + `customize.js` hook) | CSS class + bug-free upstream | One-line CSS class; relies on the upstream implementation being correct. **Not bug-free in 6.2.1** (see #1820). |
| **Custom JS + Python binding** (mousedown/move/up on appbar, `pywebview.api.drag_window(dx, dy)` calls) | ~50 LOC JS + ~30 LOC Python | Full control over drag feel (rAF throttling, debouncing, etc.), but you have to get the coordinate math right AND keep it right across pywebview upgrades. **Multiple failure modes.** |

The project's history with these is documented below.

---

## Attempt 0 (pre-2026) — OS-native `-webkit-app-region: drag`

**Approach:** apply `-webkit-app-region: drag` to the appbar CSS.
No JS, no Python. Let the OS handle the drag.

**Why it was rejected (Round 0 §7 cleanup, 2026-06-04):**
- Conflicts with the appbar's interactive children (close/min/max
  buttons, global brightness slider, transport status dots). Every
  child needs an explicit `-webkit-app-region: no-drag` carve-out,
  which is the same hand-rolled coordination we were trying to
  escape.
- pywebview frameless mode + `-webkit-app-region: drag` has known
  issues on some macOS versions. The user hit one of these in an
  early round and explicitly rejected the OS-native path.
- We do not reopen this decision.

**Lesson:** the OS is the right place to do window drag in general,
but pywebview's frameless-on-macOS stack doesn't support it cleanly
when the drag region has interactive children. **Kare/Rams:** the
OS-native approach failed the "platform-native controls where they
exist" principle here, because the platform-native control doesn't
support the pattern we need.

---

## Attempt 1 (Round 4) — custom JS drag handler + Python rAF debounce

**Approach:**
- JS in `app.js`: mousedown on `.integrated-appbar` → mousemove
  sends cumulative deltas → mouseup ends. rAF-throttled.
- Python in `gui_api.py:drag_window(dx, dy)`: 16ms Timer-based
  micro-debounce, coalesces deltas arriving within the same frame,
  applies once via `self.window.move(self.window.x + dx,
  self.window.y + dy)`.

**Steelman at the time:** smallest blast radius (one binding,
~10 LOC), host-side fix catches all callers, rAF + debounce give
exactly the right drag feel. 16ms = one frame at 60Hz; humans
won't notice.

**Why it failed (per user, 2026-06-05 manual test):**
> "the window jumps around like crazy"

**Root cause we missed at the time:** the real bug was NOT in our
JS or Python code. It was in **pywebview's own drag handler**, in
the cocoa backend. Our custom handler was actually working OK; the
**other** drag path (pywebview's bundled `pywebview-drag-region`)
was ALSO active (because the CSS class was still on the header),
and the two paths were fighting each other. The jumps we saw were
the result of both paths sending move commands simultaneously with
different coordinate semantics (cumulative deltas vs absolute
screen coords).

**Lesson:** when fixing a drag, **either** use the bundled
mechanism **or** disable it completely. Half-on / half-off gives
double-drag, which manifests as "jumps around like crazy".

---

## Attempt 2 (Round 5, first try) — `pywebview-drag-region` only, with `DIRECT_TARGET_ONLY=True`

**Approach:**
- Removed the custom JS handler from `app.js` entirely.
- Removed the `drag_window` Python binding.
- Re-enabled the bundled `pywebview-drag-region` CSS class on the
  appbar.
- Set `webview.settings['DRAG_REGION_DIRECT_TARGET_ONLY'] = True`
  so the drag only starts when the EXACT target matches the drag
  region (no child traversal).

**Steelman:** the cleanest possible drag setup. Zero code on our
side. The OS compositor is the right place to do window drag.

**Why it failed (per user, 2026-06-05 manual test):**
> "the window is now not draggable at all"

**Root cause:** the appbar has interactive children (close / min /
max buttons, brightness slider, transport dots). With
`DRAG_REGION_DIRECT_TARGET_ONLY=True`, the JS in
`webview/js/customize.js:55-61` only starts a drag when the exact
mousedown target matches the drag-region selector. Every
interactive child fails the `.matches()` check → no drag starts
on any click within the appbar that doesn't hit dead space.

**Two compounding bugs in pywebview 6.2.1:**
1. **Contract mismatch in `customize.js:44-48`:** JS sends deltas
   (`x = ev.screenX - initialX`) to a Python method that expects
   absolute coordinates (`window.move` calls
   `setFrameTopLeftPoint_`). Even on single-monitor, this
   teleports the window to near `(delta, flipped_y)` on every
   mousemove.
2. **Coordinate double-count in `cocoa.py:811-815`
   (upstream issue #1820, May 2026):** `BrowserView.move` adds
   `self.screen.origin.x` to the X coordinate the JS sends. On
   multi-monitor setups this jumps the window off-screen
   mid-drag. On single-monitor it's a no-op because
   `screen.origin = (0, 0)`.

The `DIRECT_TARGET_ONLY=True` setting then made the first bug
catastrophic on the child elements (no drag starts at all) and
turned the second bug into "window doesn't drag from anywhere in
the appbar".

**Lesson:** don't enable `DRAG_REGION_DIRECT_TARGET_ONLY` on a
drag region with interactive children. The default (`False`)
walks up the DOM to find a drag-region ancestor, which is what
you want.

---

## Attempt 3 (Round 5, second try) — custom JS handler + partial #1820 patch

**Approach:**
- Restored the custom JS drag handler (no debounce, no anchor
  chain). Skips clicks on `button, select, input, .no-drag` so
  window controls still work.
- Restored `gui_api.py:drag_window(dx, dy)` (simplest possible:
  `self.window.move(self.window.x + dx, self.window.y + dy)`).
- Applied the upstream-recommended monkey-patch from issue #1820:
  drops the `self.screen.origin.x` term from `BrowserView.move` on
  macOS.

**Steelman:** combined the best of both — full control of drag
feel (custom JS) AND the upstream bug fix (the #1820 patch fixes
multi-monitor, which is the real bug we were chasing).

**Why it failed (per user, 2026-06-06 manual test):**
> "the window is back to jumping around"

**Root cause:** we left the `pywebview-drag-region` CSS class on
the appbar from Attempt 2, but the custom JS handler was supposed
to take over. Result: both paths were active again, fighting each
other, producing the same "jumps around like crazy" symptom as
Attempt 1.

**Lesson:** again: when fixing a drag, **either** use the bundled
mechanism **or** disable it completely. Don't leave the CSS class
in place "just in case".

---

## Attempt 4 (Round 5, third try — current) — bundled drag-region + #1820 patch

**Approach:**
- `<header class="integrated-appbar pywebview-drag-region">` in
  `gui/web_ui/index.html:24`. The `pywebview-drag-region` class is
  the JS-side hook into pywebview's `customize.js` drag handler.
- **No `DRAG_REGION_DIRECT_TARGET_ONLY` setting** (use the default
  `False`, so child element clicks walk up the DOM and find the
  drag region).
- **No custom JS drag handler** in `app.js`. No `pywebview.api.drag_window`
  calls anywhere.
- **No custom Python `drag_window`** in `gui_api.py`.
- Monkey-patch in `gui/gui_main.py:111-128` that replaces
  `BrowserView.move` with the upstream-recommended workaround from
  issue #1820:
  ```python
  def _patched_move(self, x, y):
      flipped_y = self.screen.size.height - y
      self.window.setFrameTopLeftPoint_(
          AppKit.NSPoint(x, self.screen.origin.y + flipped_y)
      )
  ```
  This drops the `self.screen.origin.x` term that causes the
  multi-monitor coordinate double-count.

**Why this works:**
- The bundled drag-region mechanism does the right thing on a
  single monitor (because `screen.origin = (0, 0)`, the buggy
  `+ self.screen.origin.x` is a no-op).
- The #1820 patch fixes the multi-monitor case by dropping the
  `+ self.screen.origin.x` term entirely.
- No custom code to maintain, no coordinate math to get wrong, no
  fighting between two drag paths.
- The monkey-patch is a one-time, in-place function replacement
  on `BrowserView.move`, so it persists for the lifetime of the
  process.

**Why the patch is gated on detection (and how it
self-deactivates):** the patched `BrowserView.move` is the same
shape as the upstream-recommended fix. If pywebview ships its own
fix to #1820, the source of `BrowserView.move` will no longer
contain the literal token `self.screen.origin.x + x` (the bug
token). The detection helper in `gui_main.py:_pywebview_1820_bug_present()`
uses that token's presence as the bug-present signal, and the
application block in `main()` only applies the patch when the
helper returns `True`. When upstream ships the fix:

1. The detection helper returns `False`.
2. The patch is skipped, the log line is "pywebview #1820 already
   fixed upstream; skipping patch".
3. The code becomes a no-op (just an import + a function call
   that returns `False`).

**Maintenance contract:** the moment pywebview ships #1820, the
entire block in `gui_main.py:96-128` (and the detection helper
itself) can be deleted. The regression test
`test_pywebview_1820_detection_matches_source` will tell you when
this happens — it fails the moment the detection token no longer
matches the actual bug signature in the installed pywebview.

---

## Decision record (the keepers)

- **Bundled drag-region is the right path.** Custom JS/Python drag
  handlers are too failure-prone (3 of 4 attempts failed). The
  pywebview `pywebview-drag-region` class does the right thing on
  single monitor, and the #1820 patch handles multi-monitor.
- **Never enable `DRAG_REGION_DIRECT_TARGET_ONLY` on a drag region
  with interactive children.** Default `False` is the only safe
  setting for our appbar layout.
- **Never leave both custom + bundled drag paths active at once.**
  Pick one.
- **The #1820 patch must be idempotent.** Source-based detection
  on the literal bug token `self.screen.origin.x + x` is the
  robust signal.
- **Behavioral test is impossible in CI.** pywebview's
  `customize.js` is injected by `webview.start()`, not by serving
  HTML over HTTP. Playwright cannot exercise the actual drag
  handler. Static guards + a manual-test protocol are the only
  options.
- **Rams #10 (as little as possible):** the final fix is 3 lines
  of CSS (one class), 1 line of monkey-patch assignment, and a
  detection helper. That's the minimum surface that works.
- **Kare (platform-native where it exists):** the bundled
  drag-region is the platform-native mechanism. We use it.

---

## File map (current)

| File | Role |
|---|---|
| `gui/web_ui/index.html:24` | `<header class="integrated-appbar pywebview-drag-region">` — the CSS-class hook into pywebview's `customize.js:69-89` drag handler. |
| `gui/web_ui/app.js` | No custom drag handler. No `pywebview.api.drag_window` calls. |
| `gui/gui_api.py` | No `drag_window` method. Drag is handled by pywebview, not Python. |
| `gui/gui_main.py:27-66` | `_pywebview_1820_bug_present()` — source-based detection of the upstream bug. |
| `gui/gui_main.py:111-128` | Gated application of the #1820 monkey-patch. Skips on non-darwin, on ImportError, and when the bug is not detectable. |
| `tests/test_gui_drag_instrumented.py` | 6 tests: 4 static guards + 2 detection-contract canaries. |
| `docs/PLANNED_WORK.md` §5 #0 | Status table entry pointing to this file. |
| `docs/PLANNING_ROUND2_CONTINUATION.md` §1 | Original dialectic on the drag fix (the **recommendation was wrong**; this file is the corrected history). |

---

## Manual test protocol

The drag cannot be behaviorally tested in CI. The protocol for
verifying it on a real macOS window is:

1. **Single-monitor baseline:** open the app, drag the appbar.
   Window should follow the cursor 1:1, no stutter, no jump.
2. **Multi-monitor off-screen jump (the #1820 bug):** drag the
   window to a secondary monitor, then drag it back. The window
   should track the cursor across the monitor boundary smoothly.
   Without the patch, it jumps off-screen on the first mousemove
   after crossing the boundary.
3. **Child-element clicks:** click the close / min / max buttons
   and the brightness slider. The window should NOT start a drag
   on these clicks (the child traversal should NOT find the
   drag-region as a direct target, OR the click handlers should
   fire first and stop propagation). If a child click starts a
   drag, the `DIRECT_TARGET_ONLY` setting is wrong OR the click
   handlers are missing `e.stopPropagation()`.
4. **Log line on startup:** with the buggy pywebview, you should
   see "Applied pywebview #1820 multi-monitor drag patch" in the
   log. With a fixed pywebview, you should see "pywebview #1820
   already fixed upstream; skipping patch".

If any of these fail, the drag mechanism has regressed and
`tests/test_gui_drag_instrumented.py` should be updated to catch
the specific regression.

---

## How to undo the workaround (when pywebview ships #1820)

1. Check upstream: https://github.com/r0x0r/pywebview/issues/1820
2. Confirm the fix is in the latest pywebview release on PyPI:
   `pip index versions pywebview` or
   `python3 -c "from importlib.metadata import version; print(version('pywebview'))"`.
3. Update pywebview: `pip install --upgrade pywebview`.
4. Run the test suite. The
   `test_pywebview_1820_detection_matches_source` test will fail
   with a clear message telling you the detection token no longer
   matches the bug signature in the new source.
5. Confirm the fix is in the new source (visit the file at
   `/opt/homebrew/lib/python3.14/site-packages/webview/platforms/cocoa.py`,
   look at `BrowserView.move`).
6. Delete `_pywebview_1820_bug_present()` and the entire patch
   block from `gui/gui_main.py`.
7. Delete the two detection-contract tests from
   `tests/test_gui_drag_instrumented.py` and update
   `test_gui_main_patches_cocoa_drag` to assert that the patch
   is no longer present.
8. Run the full test suite, verify all green.

---

**End of history. The current drag mechanism is the bundled
pywebview drag-region + the gated #1820 monkey-patch. Don't reopen
the custom-handler path without very strong reason — 3 of 4
attempts at it failed in production.**
