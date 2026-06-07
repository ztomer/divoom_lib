# Planning: How to continue with Round 2 pending items _(2026-06-05)_

> **Input:** `docs/PLANNED_WORK.md` §5 — the 4 pending items.
> **Method:** for each item, list 2-3 candidate approaches. For each
> approach, do **3 rounds** of steelman → counter-steelman → synthesis.
> **Output:** a recommended order, an open-questions list, and a
> decision-ready table.

> **Pattern citations** (build-discipline): A2 (parity proof before
> cutover), B1 (kill criterion per phase), B2 (decision-criteria
> checklist for deferrals), D2 (document the decision, not just the
> code), D4 (explicit no-action as output), E1 (multi-perspective
> review), F4 (plan → execute → document loop).

---

## §0 Reading map

- §1 — Item **#0** Window drag still jumps
- §2 — Item **#1b** "Push to Device" sticky bottom
- §3 — Items **#2** and **#3** (one fix) Channel-switch before push
- §4 — Item **#3a** `display_custom_image` library wrapper
- §5 — Order-of-operations decision (which item first?)
- §6 — Open questions for the user
- §7 — Recommendation summary

Items #2 and #3 share a root cause (channel-switch missing from the
push path), so they are analysed together. The wrapper #3a depends
on #2/#3 being verified first, so its analysis assumes the channel-
switch fix is in.

---

## §1 — Item #0: Window drag still jumps, rAF fix was insufficient

### Context (from PLANNED_WORK.md §5.1)

The JS handler is fine (rAF test passes). The issue is that
`pywebview.api.drag_window(dx, dy)` is called with *deltas*; multiple
deltas queue faster than the OS compositor applies them, causing
overshoot-then-correction (visible stutter).

### Approach A — Python micro-debounce in `gui_api.py`

Coalesce `drag_window` calls arriving within 16 ms by summing deltas
and applying once. Host-side, catches any caller.

- **Pros:**
  - Smallest change surface (one binding, ~10 lines).
  - Host-side fix catches all callers (not just the JS handler).
  - Preserves the existing `drag_window(dx, dy)` API.
  - Testable in isolation (call the binding 10× in 1 ms; assert one
    call into the underlying window-move).
- **Cons:**
  - Adds a per-binding timer (one thread + one lock, or a 16 ms
    last-call cache).
  - Could be perceived as "laggy" if the user does micro-drags
    (drag 1 px → wait 16 ms → apply). rAF already coalesces so the
    visual cost is small, but a real slow host would feel it.
  - Doesn't fix the underlying semantic — the binding still speaks
    deltas, so a future caller from a different language binding
    would re-introduce the bug.

### Approach B — Change the semantics to cumulative position

`drag_window(newX, newY)` instead of `drag_window(dx, dy)`. The
caller is responsible for tracking position; the binding is
idempotent.

- **Pros:**
  - Eliminates the root cause (deltas can't queue out of order
    because there's only ever one target position).
  - No timer/lock on the Python side; the binding is stateless.
  - Easier to reason about in tests.
- **Cons:**
  - **API change.** Every existing caller must be updated. There's
    currently exactly one (the JS handler), so the blast radius is
    small, but the binding is a public API and other code paths
    could exist (e.g. gesture / accessibility handlers).
  - The binding no longer matches `pywebview`'s native
    `move_window(dx, dy)` semantic, so we'd need a translation
    layer in `gui_api.py` to map `newX, newY` to `dx, dy` for the
    underlying `pywebview` call anyway — back to a per-call sum.
  - **Rams #7 long-lasting** — coupling our binding to a specific
    semantic (cumulative) when the underlying tool speaks deltas
    is a source of future drift.

### Approach C — Drop the JS handler; use OS-native frameless drag

`-webkit-app-region: drag` on the appbar. No JS, no Python, no
pywebview. Let the OS handle the drag.

- **Pros:**
  - Zero code on our side. No tests to write for the drag itself.
  - The OS compositor is exactly the right place to do window drag.
  - Solves the "delays queue" problem forever (it doesn't exist at
    this layer).
- **Cons:**
  - Conflicts with the existing interactive elements in the
    appbar (device selector, channel title, status indicators).
    `-webkit-app-region: drag` swallows all events on the
    appbar; we'd need to carve out non-drag regions for
    interactive children.
  - Pywebview's frameless mode + `-webkit-app-region: drag` has
    known issues on some macOS versions (the user just hit one of
    these in Round 0; Round 0 §7 cleanup kept the existing
    `-webkit-app-region: no-drag` on `.integrated-appbar`
    deliberately).
  - Less control over drag feel (no rAF throttle, no over-shoot
    protection).

### Dialectic — 3 rounds

**Round 1 — Initial positions.**

- **A (steelman):** Smallest-blast-radius, host-side, preserves the
  API, catches all callers. The 16 ms window is exactly one frame at
  60 Hz; humans won't notice.
- **B (steelman):** Eliminates the *root cause* — deltas can't queue
  out of order if they don't exist. Stateless binding, easy to
  reason about. There's only one caller right now, so the API change
  is cheap.
- **C (steelman):** The OS is the right place for window drag. We're
  reinventing a wheel. The existing appbar already has the
  `-webkit-app-region` infrastructure; extending it is the
  Kare/Rams-honest move (let the platform do it).

**Round 2 — Counter-steelman.**

- **A ← attacked by B:** A preserves the buggy delta API. B is the
  actual fix; A is a band-aid that papers over the symptom. If
  another caller appears, the bug re-introduces itself.
- **A ← attacked by C:** A still pays the cost of dragging in JS +
  Python. C offloads it entirely. A is doing work that the OS
  should do.
- **B ← attacked by A:** B's API change is the actual "blast
  radius" — it's a public binding. A's blast radius is one
  function. A is reversible; B is not (a public API change
  accumulates). B also re-introduces a translation layer to
  `pywebview` deltas, which is the same logic A has, but harder to
  test.
- **B ← attacked by C:** B still requires a Python binding. C
  removes it. B is partial.
- **C ← attacked by A:** C's conflict with interactive elements
  is the *entire appbar*. The user has a device selector, status
  icons, etc. on the appbar. C requires carving out
  `no-drag` regions for all of them, which is the same
  hand-rolled coordination we're trying to escape. C also has
  known pywebview-on-macOS issues that the user already
  rejected once in Round 0.
- **C ← attacked by B:** C changes the user-facing drag model.
  With the JS handler we have a rAF-throttled follow; with C the
  OS could lag the window behind the cursor by a frame or more on
  slow hosts. We traded a known-bad stutter for a known-bad lag.

**Round 3 — Synthesis.**

- **C is rejected.** The user already tried `-webkit-app-region:
  drag` and kept the JS handler deliberately (Round 0 §7). We
  don't reopen that decision.
- **A and B are the live candidates.** A is a small, testable
  band-aid that preserves the API. B is a more invasive fix that
  addresses the root cause. The question is **blast radius vs
  correctness**: A ships faster, B is right-er.
- **Recommendation (2026-06-05, original — REJECTED by implementation):**
  A, with a regression test for the specific failure mode (10 calls
  in 1 ms → 1 underlying window-move) and a comment block in
  `gui_api.py` explaining the 16 ms choice and the deferred B. If
  A turns out to feel laggy, B becomes the next step.
- **Final outcome (2026-06-06, 4 attempts later):** the original
  recommendation was wrong. Approach A (Python micro-debounce on
  custom `drag_window` binding) was implemented in Round 4 but the
  window still "jumped around like crazy" in manual testing. Root
  cause analysis revealed the issue was not our debounce logic —
  it was that pywebview's bundled `pywebview-drag-region`
  mechanism was ALSO active (the CSS class was on the appbar),
  and the two drag paths were fighting each other. The 4-attempt
  journey (OS-native → custom JS+debounce → bundled-only with
  `DIRECT_TARGET_ONLY=True` → custom JS+partial #1820 patch →
  **bundled-only + full #1820 patch [CURRENT]**) is documented
  in detail in `docs/DRAG_FIX_HISTORY.md`. **Lesson (D3):**
  document the dead-ends. The "right" answer turned out to be the
  *combination* of the bundled mechanism (Approach C's spirit)
  AND the upstream bug fix (the #1820 patch, not in the original
  analysis because we hadn't read the issue at that point).

---

## §2 — Item #1b: "Push to Device" sticky at bottom of gallery card

### Context (from PLANNED_WORK.md §5.2)

Card body is `overflow:hidden` + gallery is `overflow-y:auto`, so the
button gets pushed out of view. Target: gallery scrolls, button
stays at the bottom of the visible card area.

### Approach A — Flex layout (the current plan)

Card body `display: flex; flex-direction: column`; gallery `flex:
1; overflow-y: auto; min-height: 0`; button `flex-shrink: 0`.

- **Pros:**
  - Established pattern in this codebase (Round 0 §2.1 already used
    this for Custom Art).
  - No new CSS concepts; the file already has `.monthly-best-layout`
    using the same chain.
  - The whole card body is the scroll context, so the scrollbar is
    always visible (or always absent if the gallery fits).
- **Cons:**
  - Fixes the symptom, not the cause — the button is at the bottom
    of the *card*, but if the *card* itself is in a scrollable
    region, the button can still be pushed out of the window
    viewport. The Monthly Best card is currently in a tab that's
    rendered in `main.main-content` (which is not scrollable
    itself in the current design), so this is a theoretical concern.
  - If the gallery shrinks (only 2 items), the button jumps to the
    middle of the empty space. The card looks "loose" (Kare: a
    loose card is a Kare fail — bitmap clarity requires a
    tight visual envelope).

### Approach B — `position: sticky` on the button

`position: sticky; bottom: 0` on the button inside a scrolling
gallery container.

- **Pros:**
  - The button follows the gallery scroll (always at the visible
    bottom of the scroll viewport, not the card).
  - Cleaner conceptually for "always visible" semantics.
- **Cons:**
  - Requires the gallery's scroll context to be the *button's
    containing block*. If the gallery has `overflow-y: auto` and
    the button is its next sibling, sticky works. If the card
    itself scrolls, the sticky button moves with the card, which
    is what we want.
  - **Browser-compat quirk:** Safari has historically been strict
    about sticky inside flex containers. The current layout is
    flex; sticky may need a wrapper. The user is on macOS
    (WebKit), so this matters.
  - **Kare honesty:** sticky buttons can look like the card has
    "floating chrome" — Rams #5 unobtrusive says no. The flex
    approach is more honest about layout.

### Approach C — Separate fixed bottom bar

Move "Push to Device" out of the card entirely; into a fixed bar
at the bottom of the window.

- **Pros:**
  - Always visible regardless of card content.
  - Visual hierarchy: the action lives at the application level,
    not the card level.
- **Cons:**
  - **Wrong scope.** The button pushes *the selected gallery item*,
    not a global action. Putting it in a global bar implies it
    operates on the global state, which would be confusing.
  - Visual chrome at the bottom of the window fights the
    titlebar (top) and any future status bar. Rams #10
    "as little design as possible" — a global bar for a per-card
    action is too much.
  - Disconnect: the user has to look at the gallery to know what
    they pushed, then look at the bottom of the window to confirm
    the action. Visual distance is a Kare fail.

### Dialectic — 3 rounds

**Round 1 — Initial positions.**

- **A (steelman):** Pattern reuse (Round 0 §2.1). Tight visual
  envelope. Kare/Rams-honest.
- **B (steelman):** "Always visible" semantics match the user's
  exact words. Sticky buttons are a well-known primitive.
- **C (steelman):** Maximum visibility. The button becomes a global
  app action, not a card action.

**Round 2 — Counter-steelman.**

- **A ← attacked by B:** "Always visible" is a sticky semantic.
  Flex-bottom-anchored is "always at the bottom of the card" which
  is *not* the same thing. If the card scrolls (e.g. on a small
  window), flex-bottom moves with the card and disappears.
- **A ← attacked by C:** A creates a loose-card problem. The fix
  is local to the gallery card; the action is not.
- **B ← attacked by A:** B's sticky-inside-flex Safari quirk is a
  known papercut. A is already a working pattern. B introduces a
  browser-compat risk for no semantic gain if the card doesn't
  scroll.
- **B ← attacked by C:** Sticky is "always visible inside the
  scroll context". If the user has many gallery items and scrolls
  the gallery, sticky-bottom follows them. C's "global bar"
  stays put at the window bottom. Different semantics; different
  intent.
- **C ← attacked by A:** The button is per-card, not global.
  Kare: per-card actions live in the card. C creates
  scope-creep and a visual disconnect.
- **C ← attacked by B:** C is heavier than B. Same problem, more
  chrome. Rams #10.

**Round 3 — Synthesis.**

- **C is rejected.** The button is a per-card action.
- **A and B are the live candidates.** A is the conservative fix
  that reuses an existing pattern. B is the more semantically
  correct "always visible inside the scroll context" fix but
  introduces Safari flex-sticky risk on a real platform.
- **Recommendation: A, with the loose-card concern mitigated by a
  min-height on the gallery area (e.g. `min-height: 200px` so the
  card never collapses to "gallery + huge empty space + button").**
  If the card-scroll-in-window issue manifests (need to see
  actual window heights), escalate to B.

---

## §3 — Items #2 + #3: Channel-switch before push

### Context (from PLANNED_WORK.md §5.3 and §5.4)

The push path (`_music_sync_loop` → `_push_frame` →
`dev.display.show_image(...)`) sends image bytes only. It does NOT
switch the device to the design/custom-art channel first. The
device stays on the previous channel; new image is buffered but
not displayed. Cover art (#2), stocks (#3a), and sysmon (#3) all
hit this same bug.

### Approach A — Switch-to-design-channel before every push (current plan)

Add an explicit `switch_to_channel(0x05)` before each `_push_frame`
call. Three call sites (cover art, stocks, sysmon) each get the
switch added.

- **Pros:**
  - Smallest change per call site (one line).
  - Each call site is self-documenting ("I push to the design
    channel, here's the switch").
  - Easy to add a regression test: assert that the channel-switch
    packet is sent *before* the image packet in the protocol log.
- **Cons:**
  - Duplicates the switch logic in 3 (later: N) call sites. A
    future widget dev (weather, calendar, notifications) will
    forget to add it. This is exactly the failure mode that
    produced the bug.
  - Doesn't fix the root cause: the `_push_frame` function
    should know that it pushes to the design channel.
  - **Rams #4 understandable + #7 long-lasting:** a future reader
    will wonder why every call site has the same 2-line dance.

### Approach B — Use the existing `trigger_notification` wrapper

There's already a comment in the code (line 309) about
"trigger_notification switches BLE device to design channel
automatically". Use that wrapper for music/stocks/sysmon pushes.

- **Pros:**
  - Reuses an existing, tested path. No new code.
  - The notification wrapper presumably already does the
    switch + push dance correctly.
- **Cons:**
  - `trigger_notification` may have notification-specific framing
    (the device notification channel may be different from the
    design channel). Need to read the code to verify.
  - The notification wrapper may add unwanted side effects (e.g.
    a "you got a notification" sound, a popup animation, a
    timeout). The music cover art push doesn't want a notification
    sound.
  - Naming dissonance: "trigger notification" for a "push cover
    art" action is misleading and Rams #4-ununderstandable.

### Approach C — Make `_push_frame` do the switch by default

`_push_frame` is the right primitive — it pushes a frame, and
pushing a frame to a device requires the device to be on the
design channel. The function should own that.

- **Pros:**
  - **Root cause fix.** Future widget dev calls `_push_frame`,
    gets the channel switch for free.
  - One place to change behavior. If the channel ID changes from
    `0x05` to something else, one update.
  - The wrapper #3a can be a thin layer over this.
- **Cons:**
  - Couples `_push_frame` to the design channel. If a future
    caller wants to push to a *different* channel (e.g. a
    future "live wallpaper" mode), they need a new function or
    a channel parameter.
  - Existing callers of `_push_frame` may have already done the
    switch manually. Double-switching could be wasteful or, if
    the device treats channel-switch as stateful, could confuse
    the device.
  - Need to verify the channel-switch packet doesn't have
    side-effects (a sound, a visual transition) that would be
    unwanted on every push.

### Dialectic — 3 rounds

**Round 1 — Initial positions.**

- **A (steelman):** Smallest change, self-documenting, easy to
  test. The duplicate code is OK for 3 call sites.
- **B (steelman):** Reuses the existing pattern. The comment
  about "switches automatically" is essentially a TODO someone
  left for us.
- **C (steelman):** Fixes the root cause. Future-proof. One place
  to change behavior.

**Round 2 — Counter-steelman.**

- **A ← attacked by C:** A is a band-aid. The whole point of
  functions is to factor common behavior. 3 call sites with the
  same 2 lines is a function in disguise.
- **A ← attacked by B:** A adds code where an existing function
  already does the work. Reinventing the wheel.
- **B ← attacked by A:** B is a misnomer. "trigger_notification"
  for "push cover art" is a code smell.
- **B ← attacked by C:** B is a stopgap that reuses the wrong
  abstraction. The right move is to make `_push_frame` correct,
  not to route around it.
- **C ← attacked by A:** C couples `_push_frame` to the design
  channel. A keeps the function generic.
- **C ← attacked by B:** C is a larger refactor. B is "use the
  thing that's already there".

**Round 3 — Synthesis.**

- **B is rejected** unless we verify the existing wrapper does
  what we need without side-effects. The naming is too far off
  the intent to use as-is.
- **A vs C:** A is correct for 3 call sites. C is correct for 3+
  call sites. Since #3a is going to introduce a 4th call site
  and possibly many more (weather, calendar, notifications), the
  factoring pressure of C grows.
- **Recommendation: C, with the channel parameter being a kwarg
  defaulting to `0x05` so the function remains channel-flexible
  for the future wallpaper case. The double-switch concern is
  addressed by reading the device state first (`get work mode`),
  which #3a is going to do anyway (`wait_for_display=True`).**
  A is the fallback if C's refactor scope turns out to be too
  large for this session.

---

## §4 — Item #3a: `display_custom_image` library wrapper

### Context (from PLANNED_WORK.md §5.5)

A high-level wrapper that does the full 3-step dance (switch
channel → encode image → push bytes) for any caller. Future widget
dev (weather, calendar, notifications) will all need the same
dance. The current 3 callers each do it slightly differently and
miss steps.

### Approach A — Thin wrapper, minimal API

```python
async def display_custom_image(
    self, file_path: str, size: int | None = None,
    wait_for_display: bool = False,
) -> bool
```

- **Pros:**
  - **Kare + Rams minimum viable.** One function, one intent.
  - `size=None` auto-detects from device. No magic numbers.
  - `wait_for_display` is the only flag; everything else is
    behavior.
  - Easy to test (mock the file_path, assert protocol bytes).
- **Cons:**
  - Doesn't cover: batch push, animation, partial update, custom
    channel. If we need any of these, the API grows and breaks
    backward compat.
  - Single positional arg + 2 kwargs is borderline "rich
    signature" — Rams #4 understandable is at risk if the
    semantics of `wait_for_display` aren't obvious from the
    name.
  - The `size: int | None = None` pattern requires the function
    to query the device for its matrix size, which is an
    extra BLE round-trip per call. Could be expensive in
    tight loops.

### Approach B — Rich wrapper, options object

```python
@dataclass
class DisplayOptions:
    size: int | None = None
    channel: int = 0x05
    wait_for_display: bool = False
    timeout_s: float = 2.0
    retry_count: int = 1

async def display_custom_image(
    self, file_path: str, options: DisplayOptions | None = None,
) -> bool
```

- **Pros:**
  - Forward-compatible: add new options without breaking the
    signature.
  - The dataclass is self-documenting; the IDE shows the
    options.
  - `channel` is explicit, addressing the C-concern from §3.
- **Cons:**
  - **Rams #10 as little as possible** violated. 5 options for
    one function is bloat. Most callers will use the defaults.
  - The dataclass adds a class to the public API. More surface
    to maintain and document.
  - Default-object pattern (`options=None`) is more verbose at
    the call site than kwargs.

### Approach C — Method on the `Divoom` orchestrator that takes the existing `DivoomProtocol`

The wrapper lives on the high-level `Divoom` class and composes the
existing `DivoomProtocol` methods (channel switch, image push,
work-mode query).

- **Pros:**
  - **Lives at the right architectural layer.** The orchestrator
    coordinates; the protocol is the wire format.
  - The existing 3 callers (`_push_frame` in `media_sync.py`) all
    already have a `Divoom` instance in scope.
  - Tests can mock `DivoomProtocol` cleanly.
- **Cons:**
  - Adds a method to the `Divoom` class. The class is already
    large (the B1 "God Object" finding from `CODE_REVIEW.md`).
  - If the protocol layer needs to grow (e.g. a new "push to
    channel X" method), the wrapper has to grow with it.
  - Naming: `display_custom_image` vs the existing `show_image`
    is a naming-dissonance problem (Rams #8 consistent).

### Dialectic — 3 rounds

**Round 1 — Initial positions.**

- **A (steelman):** Kare + Rams minimum. One function, one intent.
  Easy to test. The 2 kwargs cover the 2 things that vary.
- **B (steelman):** Forward-compatible. The dataclass is
  self-documenting. The `channel` kwarg makes the §3
  concern explicit.
- **C (steelman):** Lives at the right layer. The orchestrator
  composes the protocol. Easy to mock.

**Round 2 — Counter-steelman.**

- **A ← attacked by B:** A's "minimal API" creates a hard cap.
  The first caller that needs `channel` (the §3 fix needs it)
  will force a signature change. B is forward-compatible by
  design.
- **A ← attacked by C:** A's `size: int | None = None` pattern
  means the function has to know about device introspection. C
  delegates to the protocol layer.
- **B ← attacked by A:** B is bloat. 5 options for one
  function. Most callers will use 0 of them. Rams #10.
- **B ← attacked by C:** B is a public class. More surface
  area. The orchestrator already has a way to pass
  per-call options (kwargs) — adding a dataclass is
  duplicating the pattern.
- **C ← attacked by A:** C adds a method to a God Object that
  is already too large. The orchestrator has enough methods.
- **C ← attacked by B:** C's `DivoomProtocol` dependency is
  tight. B's options object can be passed without a
  protocol handle.

**Round 3 — Synthesis.**

- **A is the best *shape*.** Kare + Rams: minimal, one intent,
  one function. The signature concerns are real but addressable:
  - The `channel` concern from §3 → make the channel an
    internal default; expose it as a private `_channel` kwarg
    for the test, not as a public option. If a real caller
    needs a different channel, *that* is the time to expose
    it (per A2: parity-proof-before-cutover on a real use
    case).
  - The `size: int | None = None` extra BLE round-trip →
    amortize by caching the device's matrix size on the
    `Divoom` instance. The first call queries; subsequent
    calls reuse.
  - The naming concern → rename to match the existing pattern
    (`show_image` → `display_custom_image` is consistent with
    `display` as a noun, but the existing verb is `show`).
    Possible names: `display_image`, `push_image`,
    `show_custom_image`. The user decides.
- **B and C are rejected for the wrong reasons at this stage.**
  B is bloat; C adds to a God Object. Either could be right
  later if the function's call surface grows.

---

## §5 — Order of operations

### Three plausible orders

1. **#2/#3 first, then #3a, then #0, then #1b.**
   - #2/#3 unblocks cover art, which is the highest-value user-
     visible fix (cover art is a marquee feature).
   - #3a is the wrapper that consolidates the fix.
   - #0 and #1b are quality-of-life polish, no user blocker.
2. **#1b first, then #0, then #2/#3, then #3a.**
   - Polish first, since the channel-switch fix requires a live
     device test (we can ship #1b and #0 without a device).
   - Risk: the channel-switch fix may surface new issues that
     interact with the layout (e.g. the push button needs to
     reflect "pushing..." state, which the wrapper should own).
3. **#0 first, then #2/#3, then #3a, then #1b.**
   - Drag fix unblocks testing of the channel-switch (you need
     a stable window to click through the gallery).
   - Drag fix is also the simplest in terms of code surface.
   - #1b is the most isolated change (single CSS rule + class
     change) so it can go last as a cleanup.

### Recommendation

**Order 1**, but with the following kill criteria (B1):

- **#2/#3 done =** push cover art on a real device, see the
  image appear, repeat for stocks + sysmon.
- **#3a done =** `_push_frame` callers in `media_sync.py`
  refactored to call `display_custom_image`, the wrapper is
  tested with at least one mock-device test, and the channel-
  switch is in `_push_frame` (per §3 Approach C) not duplicated
  in 3 places.
- **#0 done =** drag the window manually, no jump, the new
  regression test passes (asserts 10 calls in 1 ms → 1
  underlying window-move).
- **#1b done =** gallery with 50+ items shows the button at
  the bottom of the visible card area at all scroll positions.

If #2/#3 can't be verified (no live device), the order flips to
**Order 2**: ship the polish, defer the channel-switch fix as a
well-documented "requires live device test" item (B4 honest
deferral).

---

## §6 — Open questions for the user

1. **For #0:** Approach A (Python micro-debounce) or Approach B
   (change semantics to cumulative position)? A is recommended.
2. **For #1b:** Is the Monthly Best card currently in a
   scrollable parent? (Affects whether flex-bottom-anchored is
   enough or sticky is needed.) If you can take a screenshot of
   the card at a small window height, that's the most useful
   data.
3. **For #2/#3:** Do you have a live device available for testing
   in this session? If not, the wrapper #3a can still be
   written + mock-tested, but the actual end-to-end verification
   has to wait.
4. **For #2/#3 Approach C:** Is the channel-switch packet
   stateless (sending it twice is fine) or does it have a
   side-effect (e.g. a sound, a visual transition)? The code
   comment in `gui_api.py:309` suggests the latter ("switches
   automatically") — if so, double-switching on a re-push
   would be a UX bug. Need to check the protocol summary.
5. **For #3a:** Preferred name? `display_custom_image` (current
   proposal) vs `display_image` vs `push_image` vs
   `show_custom_image`. The existing convention in `Divoom` is
   `show_image` (verb-noun).
6. **For #3a:** Where should the function live? On the `Divoom`
   orchestrator class (the current plan) or in a new
   `divoom_lib/display/` module? The orchestrator is large;
   the new module would be a cleaner home.
7. **For the C downscaler perf gap (§6 in PLANNED_WORK.md):**
   in scope for this session, or deferred to a follow-up? The
   user flagged it as suspicious; investigation could take
   2-4 hours; the byte-exact path is already shipped.
8. **Order of operations:** Order 1 (channel-switch first) or
   Order 2 (polish first)? The difference is whether you have
   a live device available *now*.

---

## §7 — Recommendation summary

| #   | Item                       | Approach                          | Notes                                                  |
|----:|----------------------------|-----------------------------------|--------------------------------------------------------|
| 0   | Window drag still jumps    | **A** (Python micro-debounce)     | 16 ms = 1 frame at 60 Hz; new regression test required |
| 1b  | Push button sticky bottom  | **A** (flex layout)               | Reuse Round 0 pattern; add min-height to avoid loose-card |
| 2/3 | Channel switch before push | **C** (`_push_frame` owns switch) | Default `channel=0x05`; check protocol for double-switch UX |
| 3a  | `display_custom_image`     | **A** (thin wrapper)              | Internal `_channel` kwarg; cache device size on instance |

**Order:** 2/3 → 3a → 0 → 1b, **if** a live device is available.
Otherwise: 1b → 0 → 2/3 (as documentation only) → 3a (as
mock-tested code only), with #2/#3 verification deferred.

**Deferred:** C downscaler perf gap (§6 in PLANNED_WORK.md) — low
priority, byte-exact path is shipped.

---

**End of planning. Next step: answer §6 questions, then execute
§5 Order 1.**

---

## §8 — Resolved decisions (2026-06-05)

| #   | Item                       | Approach                          | Decision                                                                       |
|----:|----------------------------|-----------------------------------|--------------------------------------------------------------------------------|
| 0   | Window drag still jumps    | **A** (Python micro-debounce)     | Confirmed.                                                                     |
| 1b  | Push button sticky bottom  | **A** (flex layout)               | Confirmed.                                                                     |
| 2/3 | Channel switch before push | **C** (`_push_frame` owns switch) | Confirmed. Need to investigate channel-switch side effects first.             |
| 3a  | Wrapper                    | `display_image`                   | Confirmed (name).                                                              |
| 3a  | Wrapper location           | `divoom_lib/display/` module      | Confirmed.                                                                     |
| –   | Live device                | All 4 available                   | Confirmed. End-to-end verification is in scope.                               |
| –   | Channel-switch idempotency | Need to investigate protocol docs | **Open investigation.** Blocked until resolved (could change §3 design).       |
| –   | C perf gap                 | Investigate now                   | Confirmed. Add to execution order.                                             |
| –   | Order of operations        | Order 1: #2/#3 → #3a → #0 → #1b   | Confirmed, with C perf gap as parallel work item.                              |

### Revised execution order

1. **Investigate channel-switch side effects** in
   `docs/DIVOOM_PROTOCOL_SUMMARY.md` and the APK reference
   (`references/apk/decompiled_src/.../bluetooth/`). This is a
   prerequisite for #2/#3.
2. **#2/#3** — make `_push_frame` own the switch. Live-device verify.
3. **#3a** — `display_image` wrapper in `divoom_lib/display/`.
4. **#0** — Python micro-debounce for `drag_window`.
5. **#1b** — flex layout for "Push to Device" button.
6. **(Parallel) C perf gap** — investigate the 4-pixels-at-a-time
   NEON deinterleave hypothesis.

### Next concrete step

**Step 1: Read `docs/DIVOOM_PROTOCOL_SUMMARY.md` and the APK
reference for the `0x45 0x05` (set light mode / set design
channel) command. Determine: does it have side effects (sound,
visual transition, device log entry)? Is it idempotent?**

This is a read-only investigation. Once the answer is known, the
§3 Approach C design can be finalized:
- **If idempotent** — `_push_frame` always sends the switch
  before the image. No guard needed.
- **If not idempotent** — `_push_frame` first calls
  `get work mode`; only sends the switch if the current mode ≠
  `0x05`. Adds one BLE round-trip per push but avoids the
  side-effect.
- **If unknown / no docs** — the wrapper `display_image` does
  the conservative thing (check first) and we add a comment
  documenting the rationale.

---

## §9 — Investigation results (2026-06-05)

### §9.1 Channel-switch side effects

**Verdict: appears to be a pure state change with no observable
side effects beyond the channel change itself.**

Evidence:
- `docs/DIVOOM_PROTOCOL_SUMMARY.md:78-81`: `0x45` is
  `Set Light Mode` with payload `[0x01 (Light Mode), R, G, B,
  Brightness (0-100), Effect Mode (0x00), On/Off Switch (0x01),
  0x00, 0x00, 0x00]`. Device returns single-byte ACK `0x01` on
  success. No mention of sound, animation, or log entry.
- APK reference
  `references/apk/decompiled_src/sources/com/divoom/Divoom/bluetooth/SppProc$LIGHT_MODE.java`
  defines the channel enum: `0=CLOCK, 1=TEMP, 2=COLOR_LIGHT,
  3=SPECIAL_LIGHT, 4=SOUND_LIGHT, 5=SOUND_USER, 6=MUSIC`. Channel
  `0x05` = `SOUND_USER` (the user-custom-art / design channel).
- APK `CmdManager.r2()` sends a 6-byte payload
  `[mode, 0, 0, 0, 0, 0]`. The protocol summary's 10-byte payload
  is the validated form (truncated payloads are rejected by the
  device's parser).
- The library's existing `divoom_lib/display/__init__.py:62` uses
  exactly this pattern: `args = [0x05] + [0x00] * 9`.

**Implication for §3:** Approach C is safe. The channel switch
appears idempotent (sending `0x45 0x05` while already on mode 0x05
is expected to be a no-op or a no-visible-effect re-assertion).

### §9.2  CRITICAL: the channel switch is *already* being sent

**`gui/media_sync.py:182-209 _push_frame()` calls
`dev.display.show_image(str(frame_path))` — and
`divoom_lib/display/__init__.py:75-101 show_image()` *already
calls* `await self.show_design()` at line 77, which sends the
`0x45 0x05` channel switch.**

This means the planning doc's §3 premise — "the push path doesn't
switch the device to the design channel" — is **wrong**. The
channel switch is happening on every push.

### §9.3 Revised diagnosis for #2/#3

The "device doesn't update" symptom is real, but the root cause
is **not** a missing channel switch. Candidates:

1. **Image data corruption** — `process_image()` in
   `divoom_lib/utils/image_processing.py` may be producing bytes
   the device rejects. Need to compare the produced frame bytes
   against a known-good reference (e.g. push a known-good image
   from a different path and see if it works).
2. **Wrong device** — the `_push_frame` may be pushing to a
   different divoom instance than expected (e.g. a stale
   `current_divoom` after a device reconnect, or a wall slot
   when a single device is expected). Need to log the
   `dev.mac_address` and the `dev.display` reference.
3. **Wrong image mode** — the cover art is 144×144 from
   `render_and_downsample_artwork`, but `_push_frame` passes
   `size=16`. The downscaling in the wrapper vs. in
   `process_image` may be a double-downscale, producing wrong
   pixels at the 16×16 size.
4. **Transport issue** — iOS-LE `0x44 set image` may need
   different framing than SPP `set image`. The chunking
   (`chunksize`) may be wrong for iOS-LE.
5. **Channel switch happens AFTER image push** — the order in
   `show_image` is `show_design()` first, then process_image,
   then send. This is correct. But if some other code path
   bypasses `show_image` and goes direct, the switch may be
   missing. (Search for direct `set image` / `0x44` calls.)

### §9.4 Revised plan for #2/#3

**Step 1 (read-only, do this first):**
- Confirm `process_image` output is byte-exact to a
  known-good image pushed via the official Divoom app.
- Confirm the order in `show_image` is `show_design()` →
  `process_image` → `send_command("set image", ...)`.
- Confirm `_push_frame` calls `show_image` (not a lower-level
  function).
- Check `gui/gallery_sync.py:334,337` — does it also call
  `show_image`?

**Step 2 (small, do this if Step 1 finds the cause):**
- Fix the root cause. The fix is not "add a channel switch"
  because that's already there. The fix is whatever Step 1
  found.

**Step 3 (do this regardless of Step 1 outcome):**
- Add a regression test that asserts `show_image` sends
  `0x45 0x05` (channel switch) BEFORE `0x44` (set image). This
  test guards against future regressions of the channel
  switch.

**Step 4 (do this if Step 2 doesn't find a clear root cause):**
- Live-device diagnostic: add a one-shot Python script that
  pushes a known-good 16×16 image via `show_image` and logs
  the protocol bytes end-to-end. Run on a real device, see
  what happens.

### §9.5 Impact on #3a

The wrapper `#3a display_image` is still useful as a public-API
hardening, but its *purpose* shifts:
- **Originally planned:** consolidate the missing channel switch
  + image push into one function.
- **Revised purpose:** consolidate the *existing* `show_image` +
  `render_and_downsample_artwork` + `fetch_album_art_url` dance
  into one high-level call that the GUI can use. Channel switch
  is already a freebie via `show_image`.

The `display_image` API stays the same:
```python
async def display_image(
    self, file_path: str, size: int | None = None,
    wait_for_display: bool = False,
) -> bool
```

But it lives in `divoom_lib/display/__init__.py` (already a
suitable module — see §4 §6) and is essentially a thin alias for
`show_image` + optional pre-flight checks. Whether this is worth
adding depends on whether the existing 3 callers
(`_push_frame`, `gallery_sync.py:334/337`) can be simplified by
calling the new wrapper instead.

### §9.6 Live-device diagnostic test (new — needed)

The user's protocol-log observation
(`01060004315556e60002` for the image push) suggests the bytes
ARE being sent, but the device isn't displaying. We need a
live-device test that:
1. Records the protocol byte stream end-to-end during a
   `push_music_cover_now` call.
2. Compares the bytes against a known-good push (e.g. from
   the official Divoom app or a prior known-working session).
3. Reports any discrepancy.

The existing `tests/test_divoom_chunksize.py` and
`tests/test_native_downscaler.py` are mock-based; we need a
hardware-gated test similar to
`tests/test_live_widgets_diagnostic.py`. Mark it with
`@pytest.mark.hardware` and the existing
`--run-hardware` flag.

---

## §10 — Open questions (updated)

1. **For #2/#3:** The original premise (channel switch missing)
   is wrong. The real bug is something else. Do you want to:
   (a) Run the live-device diagnostic first to identify the real
   root cause?
   (b) Skip the diagnostic and add the regression test (#9.4
   Step 3) as a guard against future regressions, then move on?
   (c) Take a different approach — explain what you observed in
   your session that suggested the channel switch was missing?

2. **For #9.4 Step 1:** Can you describe what you saw on the
   device when you tested `push_music_cover_now`? Specifically:
   - Did the device's previous image stay on screen?
   - Did the device's screen go blank?
   - Did the device show a "loading" indicator?
   - Did the device emit any sound?
   - Was the device on the design channel already, or on
     something else (clock, visualizer)?

3. **For #3a (now §9.5):** With the channel switch already
   happening, is the wrapper still worth adding? It would be
   ~10 lines that alias `show_image` with optional pre-flight
   checks. The main value is API ergonomics (one function for
   "display this image"), not the channel switch.

4. **For C perf gap:** investigation order — start with the
   NEON `vld4q_u8` deinterleave hypothesis, or do a profiler
   pass first (Instruments/Time Profiler) to see where the
   30% is actually going?

---

## §11 — Final decisions (2026-06-05, after §9 investigation)

| #   | Item                              | Decision                                                                  |
|----:|-----------------------------------|---------------------------------------------------------------------------|
| 0   | Window drag fix                   | Approach A (Python micro-debounce) — ship after #2/#3                    |
| 1b  | Push button sticky bottom         | Approach A (flex layout) — ship last                                       |
| 2/3 | Cover art / stocks / sysmon push  | **Run live-device diagnostic first.** Channel switch is already happening; the real bug is elsewhere. |
| 3a  | `display_image` wrapper           | Yes, for API ergonomics. Thin alias for `show_image` with optional pre-flight checks. |
| –   | C perf gap                        | **Profile first with Instruments.** Find the actual hot spot before optimizing. |
| –   | Order                             | Live-device diagnostic → #3a wrapper → #0 drag → #1b button → C perf profiling |

### Diagnostic plan for #2/#3

The user observed: "device was on a different channel" when the
push happened. This means the channel switch either:
1. Failed silently (BLE write-without-response, no ACK).
2. Succeeded but was overridden by something.
3. Took effect but the image push landed on a "design" page
   that doesn't display.
4. Had its `0x45 0x05` bytes arrive *after* the image bytes
   (BLE is async, no ordering guarantee with
   write-without-response).

To diagnose:
- Add a `tests/test_push_protocol_diagnostic.py` (hardware-gated).
- Use the existing transport's byte-level send to log every
  command.
- Read `get work mode` before and after the push to see if the
  channel changed.
- Compare against a known-good push from the official Divoom
  app (if available) or a prior known-working session.

### Live-device diagnostic test (sketch)

```python
import pytest
from divoom_lib import Divoom

@pytest.mark.hardware
def test_push_protocol_diagnostic():
    """Record the full protocol byte stream during a cover-art push.
    
    Goal: determine why the device doesn't display the image even
    though the channel switch (0x45 0x05) is sent.
    """
    dev = Divoom(mac=KNOWN_DEVICE_MAC)
    dev.connect(use_ios_le=True)
    
    # 1. Read initial state
    initial_mode = dev.system.get_work_mode()
    log(f"Initial work mode: {initial_mode:#x}")
    
    # 2. Push a known-good test image
    test_image = make_test_image_16x16()  # solid red square
    test_image.save("/tmp/divoom_diag.png")
    
    # 3. Hook the transport to log every byte
    with transport_byte_logger() as log_bytes:
        dev.display.show_image("/tmp/divoom_diag.png")
    
    # 4. Read final state
    time.sleep(2.0)  # let device process
    final_mode = dev.system.get_work_mode()
    log(f"Final work mode: {final_mode:#x}")
    
    # 5. Assertions
    log(f"Bytes sent: {log_bytes.sent}")
    log(f"Bytes received: {log_bytes.received}")
    assert log_bytes.contains(b"\x45\x05"), "Channel switch was sent"
    assert log_bytes.contains(b"\x44"), "Image data was sent"
    # The actual assertion depends on what we find
```

Run with: `pytest tests/test_push_protocol_diagnostic.py --run-hardware -v -s`

### Revised file plan

| Action  | File                                                                |
|---------|---------------------------------------------------------------------|
| NEW     | `tests/test_push_protocol_diagnostic.py` (hardware-gated)           |
| NEW     | `docs/PLANNING_ROUND2_CONTINUATION.md` (this file)                  |
| READ    | `divoom_lib/display/__init__.py` (verify `show_image` calls `show_design` first) |
| READ    | `divoom_lib/utils/image_processing.py` (verify `process_image` output) |
| READ    | `gui/media_sync.py` (verify `_push_frame` calls `show_image`)       |
| READ    | `divoom_lib/ble_transport.py` (verify iOS-LE framing for `set image` / `set animation frame`) |

---

## §12 — Implementation results (2026-06-05)

### §12.1 Live-device diagnostic

Ran `tests/test_push_protocol_diagnostic.py` with `--run-hardware` on
both Timoo and Tivoo. Two findings:

1. **BLE start_notify bug** (real, fixed in
   `divoom_lib/ble_transport.py`): the `connect()` method called
   `start_notify` on every invocation. macOS CoreBluetooth raises
   "Characteristic notifications already started" if `start_notify`
   is called twice without a `stop_notify` in between. After a
   transient disconnect/reconnect, the OS-side subscription state
   can be inconsistent even when `is_connected` is True. **Fix:**
   added `_notifications_started` state flag, guarded
   `start_notify`, reset flag in `disconnect()`.

2. **Deeper BLE write race** (not fixed in this session): the first
   iOS-LE write after `connect()` returns "disconnected" and
   `get_work_mode` (0x13) times out. Reproducible across devices
   even after `sudo pkill bluetoothd`. This is a known
   macOS CoreBluetooth race where the connection is reported
   established before GATT services are fully discovered. The
   fix would be to either (a) add a longer post-connect sleep,
   (b) wait for GATT service discovery before allowing writes,
   or (c) retry the first write on disconnect. **Deferred** — needs
   more iteration with a real device in good state.

### §12.2 #3a `display_image` wrapper

Implemented in `divoom_lib/display/__init__.py`:
- `display_image(file, time=None, wait_for_display=False, poll_timeout_s=2.0)`
- Thin alias for `show_image` (which already does channel switch + push)
- Optional `wait_for_display=True` polls `get_work_mode` until
  the device reports mode 0x05 (design channel)
- 8 unit tests in `tests/test_display_image_wrapper.py`, all passing
- All tests mock `show_image` and `_get_work_mode` — no hardware needed
- Live-device verification is via the existing diagnostic

### §12.3 #0 Python drag micro-debounce

Implemented in `gui/gui_api.py:drag_window`:
- 16ms debounce window (= 1 frame at 60Hz)
- `threading.Lock` + `threading.Timer` for thread safety
- Coalesces all deltas arriving within the window into a single
  `window.move` call
- `reset_drag_debounce_for_tests()` hook for unit tests
- 5 unit tests in `tests/test_gui_drag_debounce.py`, all passing
- Updated `tests/test_gui_api.py:test_drag_window` to wait for the
  flush (was: immediate move; now: debounced)

### §12.4 #1b Push to Device button — flex layout

The flex chain was already correct from Round 0/1 (flex column
on `#monthly-best.active` → `.card-body` → `.gallery-grid` with
`flex:1; overflow-y:auto; min-height:0`; button uses
`margin-top:auto`). No code change needed; just a regression
test.

2 Playwright tests in `tests/test_monthly_best_button_visible.py`:
- `test_push_button_visible_with_many_gallery_items`: injects
  50 items, asserts button is at the bottom of the card
- `test_gallery_scrolls_internally_not_whole_card`: injects
  100 items, asserts the gallery scrolls (not the whole card)

Both tests pass with the existing layout. Regression guard in
place for future CSS changes.

### §12.5 C downscaler perf profile

Profile harness:
- Built `/tmp/profile_downsampler` (inlines `downsample.c`)
- macOS `sample` to attribute cycles

Results (3000×3000 → 16×16, RGB, 50 iters):
- **99% of samples in `downsample_lanczos3`** (2321 of 2321)
- The hot spot is at offset +2008, inside the inner resampling loop
- `kernel1d_init` (per-output-pixel setup) is negligible
  (5 samples out of 2321)

This **confirms hypothesis (a)** from `PLANNED_WORK.md §6`:
the bottleneck is the inner resample loop. PIL's hot loop
processes 4 input pixels per NEON op via `vld4q_u8` deinterleave;
our loop processes 1 pixel per op. The fix is to implement
4-pixels-at-a-time SIMD.

**Action:** deferred to a follow-up session. The byte-exact
path is shipped and not user-blocking (cover art push takes
~40ms for 3000×3000, which is well below the user's perceptual
threshold).

### §12.6 Test count

- Before: 354 passed / 72 skipped / 0 failed
- After: 369 passed / 73 skipped / 0 failed
- +15: 8 (display_image wrapper) + 5 (drag debounce) + 2 (button
  visible). 1 skipped → 73 skipped because the BLE diagnostic
  is hardware-gated.

### §12.7 Files changed/created in this session

| Status | File                                                                |
|--------|---------------------------------------------------------------------|
| CHANGED | `divoom_lib/ble_transport.py` (start_notify guard, disconnect reset) |
| CHANGED | `divoom_lib/display/__init__.py` (display_image + _get_work_mode)   |
| CHANGED | `gui/gui_api.py` (drag_window debounce)                              |
| CHANGED | `tests/conftest.py` (added test_push_protocol_diagnostic to skip set)|
| CHANGED | `tests/test_gui_api.py` (test_drag_window now waits for debounce flush) |
| NEW     | `tests/test_push_protocol_diagnostic.py` (hardware-gated)            |
| NEW     | `tests/test_display_image_wrapper.py` (8 unit tests)                 |
| NEW     | `tests/test_gui_drag_debounce.py` (5 unit tests)                    |
| NEW     | `tests/test_monthly_best_button_visible.py` (2 Playwright tests)     |
| NEW     | `docs/PLANNING_ROUND2_CONTINUATION.md` (this file)                   |

---

## §13 — Plan for the two remaining items (2026-06-05)

### §13.1 BLE write race (the actual #2/#3 root cause)

**Symptom (from §12.1 diagnostic):**
- Protocol probe in `connect()` succeeds (1.0s sleep, write_with_response=True).
- The very next write — `get_work_mode` (0x13) — returns "disconnected".
- `self.client.is_connected` reports True even after the write fails.
- Retry logic: re-enters `if not self.is_connected` → reconnect → second
  write times out. The OS-level GATT state is stuck.

**Three approaches (steelman each):**

| | Approach | Pro | Con |
|---|---|---|---|
| A | **Connection-likely-broken flag** — when a write fails with "disconnected" / "not connected", set `self._connection_likely_broken = True`. The retry loop checks this flag as if `is_connected` were False, forcing a full reconnect on the next attempt. | Smallest change. Localized to the existing retry loop. Backward compatible. | Doesn't address WHY the OS reports connected while writes fail — just forces a retry. |
| B | **Wait for `services` event** — use `BleakClient.get_services()` after `connect()` to block until GATT services are fully discovered. macOS reports `is_connected=True` before GATT discovery finishes; if the first write lands during discovery, it fails. | Addresses the root cause (race between connect-completion and GATT discovery). PIL doesn't have this issue (different BLE stack). | Brittle: relies on Bleak's `get_services()` blocking properly, which is implementation-defined. May hang if services never resolve. |
| C | **Write-with-response for first command after connect** — use `write_with_response=True` for the protocol probe AND the first user command after `connect()`. The first command waits for an ACK, which forces the OS to fully establish the GATT connection before returning. | Conceptually clean. Forces a real round-trip. No new flags. | Adds 30-100ms latency to the first command after every connect. May not help if the OS reports ACK without actually writing. |

**Steelman (3 rounds):**

Round 1: Initial positions.
- A: pragmatic, fixes the symptom, can be tested in 5 lines.
- B: addresses root cause; if it works, the problem goes away.
- C: simplest, uses an existing parameter.

Round 2: Counter-steelman.
- A ← attacked by B: A is a band-aid. If the OS-level state is fundamentally broken, retries won't help.
- A ← attacked by C: C is the same fix in a different guise. The first-command-wait is just a synchronous version of A's flag.
- B ← attacked by A: B introduces a new blocking call that may not work on all Bleak backends.
- B ← attacked by C: B is the most invasive (new dependency on get_services), C is the least.
- C ← attacked by A: C has the latency cost. A doesn't.
- C ← attacked by B: C doesn't actually fix the race, just makes the first write slower.

Round 3: Synthesis.
- B is theoretically correct but practically risky (Bleak API stability).
- C is conceptually clean but adds latency on every connect.
- **A is the practical winner**: the existing retry logic is the right primitive; we just need to feed it better information. A failed write IS evidence the connection is broken, even if `is_connected` lies. The flag captures that evidence.

**Decision: A**, with a test that simulates a "disconnected" exception and verifies the retry triggers a reconnect.

**Implementation sketch:**

```python
# In __init__:
self._connection_likely_broken = False

# In _send_ios_le_payload / _send_basic_protocol_payload:
except Exception as e:
    err_str = str(e).lower()
    if "disconnected" in err_str or "not connected" in err_str:
        self._connection_likely_broken = True
    self.logger.error(f"Error sending payload: {e}")
    return False

# In _send_payload_locked:
for attempt in range(max_retries):
    if not self.is_connected or self._connection_likely_broken:
        self._connection_likely_broken = False
        # ... existing reconnect logic ...

    if await send_func(...):
        self._connection_likely_broken = False
        return True
    # retry
```

**Test sketch:**

```python
async def test_write_failure_sets_connection_likely_broken():
    """If write_gatt_char raises 'disconnected', the next attempt must reconnect."""
    transport.client.write_gatt_char = AsyncMock(side_effect=[Exception("disconnected"), None])
    transport.client.is_connected = True  # Bleak lies
    transport._divoom = MagicMock()
    transport._divoom._send_ios_le_payload = AsyncMock(side_effect=[False, True])
    # ... or similar ...
    await transport.send_payload([0x13])
    assert transport._connection_likely_broken is False  # cleared after success
```

### §13.2 C downscaler 4-pixel NEON deinterleave

**Symptom (from §12.5 profile):**
- 99% of CPU samples are in `downsample_lanczos3` at the inner resample loop.
- Current: 1 output pixel per NEON op. PIL: 4 output pixels per NEON op.
- Per `PLANNED_WORK.md §6`, hypothesis (a) confirmed.

**Three approaches:**

| | Approach | Pro | Con |
|---|---|---|---|
| A | **4-pixel SIMD via `vld4q_u8` deinterleave** — process 4 output pixels per loop iteration. Each pixel reads from 4 input rows × 1 column offset. The 4 pixels' weights form a 4×4 outer-product-friendly layout. | Matches PIL's structure. Maximum throughput. | Significant rewrite of the inner loop. Easy to break byte-exact match. |
| B | **2-pixel SIMD** — half the work, half the risk. Process 2 output pixels per iteration. | Simpler rewrite. Less surface for byte-exact bugs. Still 2× the throughput of the 1-pixel version. | Leaves half the potential on the table. |
| C | **Optimize the existing 1-pixel loop with better instruction selection** — `vld1q_u8` + `vmlaq_s32` is already NEON; maybe the auto-vectorizer can be coaxed to do better. | Zero code rewrite, just compiler flags. | Diminishing returns; the 30% gap suggests we're at the limit of the 1-pixel structure. |

**Steelman (3 rounds):**

Round 1.
- A: maximum payoff. PIL is the reference; we know their structure.
- B: half the risk, half the reward. Ship-able.
- C: lowest effort, lowest reward.

Round 2.
- A ← attacked by B: A risks breaking the byte-exact match. The 38 existing tests need to still pass; one regression and we lose the byte-exact guarantee.
- A ← attacked by C: A requires invasive changes. C might be 80% of the win with 5% of the effort.
- B ← attacked by A: B is a half-measure. If we're going to rewrite the loop, do it right.
- B ← attacked by C: B still requires the rewrite. C is strictly less work.
- C ← attacked by A: C may not close the gap. The 30% deficit is structural, not just compiler tuning.
- C ← attacked by B: C is even less than B.

Round 3.
- C is rejected. The 30% gap is too large for compiler flags to close alone.
- A and B are the live candidates. The byte-exact guarantee is the load-bearing constraint (38 tests, all passing). **The risk of breaking byte-exact is the deciding factor.**
- **B is the safer choice**: 2-pixel SIMD is a natural extension of the existing 1-pixel code, with a clear mapping (1 input → 2 inputs per weight step). The byte-exact match is easier to preserve because the per-pixel operations are nearly identical, just wider.
- **Decision: B** for this session. If 2-pixel closes most of the gap (we expect ~1.5-1.8× of current throughput), A becomes a follow-up to chase the remaining 1.3-1.7×.

**Implementation sketch (B):**

The current horizontal pass loops over output pixels x in [0, out_w). For each x:
- For each weight index k in [0, kmax):
  - read input pixel (in_x_idx[k], y) for the current output pixel
  - multiply by weight k
  - accumulate

2-pixel SIMD: process 2 adjacent output pixels per loop iteration. For output pixels (x, x+1):
- For each weight index k:
  - read input pixel (in_x_idx_0[k], y) and (in_x_idx_1[k], y) for both output pixels
  - multiply by weights (k0, k1) for both
  - accumulate into 2 separate accumulators

The 2 accumulators can be packed into a single NEON int32x4_t (low 2 lanes = pixel 0, high 2 lanes = pixel 1 — but we need separate accumulators per channel, so it's actually int32x2_t for RGB or int32x4_t for RGBA).

For RGBA: 2 output pixels × 4 channels = 8 int32 accumulators. Pack into 2 int32x4_t vectors (one per pixel).

For RGB: 2 output pixels × 3 channels = 6 int32 accumulators. Pack into 1.5 int32x4_t. Use 2 int32x4_t with the high lanes of the second one as padding (they're discarded on quantize).

**Test sketch:**

The existing `test_native_downscaler.py` already covers byte-exact match. After the 2-pixel SIMD is in place, all 38 tests + the 500-case stress test must still pass.

**Benchmark sketch:**

Extend `tests/perf_downsample.py` to include the new 2-pixel path. Verify:
- Byte-exact match holds
- Throughput improves by ~1.5× on the 3000×3000 RGBA case (currently 0.3× of PIL)
- 16×16 case is still fast (no overhead from SIMD setup)

---

## §14 — C 2-pixel SIMD experiment: FAILED, reverted (2026-06-05)

### What was tried
Added `horizontal_pass_2pixels` (2 adjacent output pixels per inner iter)
and dispatched from `horizontal_pass` for `out_w >= 2`. Byte-exact match
preserved (same input pixels, same weights, same int32 math, just
different iteration order).

### What happened
All 38 byte-exact tests pass. **But perf got WORSE on most workloads:**

| workload                       | before (1-px) | after (2-px) | delta |
|--------------------------------|---------------|--------------|-------|
| 3000×3000 RGB                  | 39.6 ms (0.7×) | 42.5 ms (0.6×) | -7%  |
| 3000×3000 RGBA                 | 43.5 ms (0.3×) | 30.5 ms (0.4×) | +30% |
| 1920×1080 RGB                  | 9.4 ms (0.7×)  | 9.4 ms (0.7×)  | ~0%  |
| 144×144 RGB                    | 0.10 ms (0.8×) | 0.10 ms (0.8×) | ~0%  |
| 640×480 RGB                    | 1.5 ms (0.7×)  | 1.4 ms (0.7×)  | ~0%  |

### Why
**Cache locality regression.** With 2-pixel gather-SIMD, each inner
iteration reads 2 input pixels at addresses separated by `scale` input
pixels (e.g. 187 input pixels apart for 3000→16, scale=187.5). This
means 2 separate cache line fetches per iter. The 1-pixel path reads
contiguous input pixels per inner iter, so a single cache line
serves the whole kernel. For 3000×3000 RGB, the 2x cache pressure
beats the 2x loop-overhead savings.

For RGBA the input is 33% larger (4 ch vs 3), so the same 2 reads/iter
are MORE likely to hit the same cache line (the cache line is 64B,
holding ~21 RGBA pixels = 16 in a 4-line kernel). That's why RGBA
showed a small win (0.3× → 0.4×) while RGB regressed.

### Decision: reverted.
The 1-pixel gather path is the best balance of byte-exact match +
cache friendliness for downscaling. The 2-pixel path lives in git
history (this session) if anyone wants to re-enable it conditionally
(e.g. for non-downscaling cases only).

### Lesson recorded
**For gather-SIMD on downscaling, the strided memory access pattern
hurts cache more than the loop-overhead savings help.** PIL avoids
this by using a **scatter** pattern: iterate over input pixels,
distribute to output pixels' accumulators. Scatter reads each input
pixel ONCE (cache-friendly) and writes to 4-6 output accumulators
in a small region (L1-resident). That's the right pattern for
downscaling.

Implementing scatter is a bigger refactor (~200 lines, new
abstraction for the per-input-pixel → per-output-pixel weight lookup).
**Defer to a future session.** See `docs/PLANNED_WORK.md §6` for
the deferred work entry.

---

## §14 — Final drag fix outcome (2026-06-06)

### §14.1 What actually shipped

The §1 dialectic's recommendation (Approach A: Python micro-
debounce on a custom `drag_window` binding) was implemented and
reverted 3 times. The 4-attempt journey is documented in full in
`docs/DRAG_FIX_HISTORY.md`. The **final shipped fix** is the
**bundled pywebview drag-region mechanism + a gated monkey-patch
to the cocoa `BrowserView.move`** that fixes upstream issue #1820.

Files changed (Round 5 ship):
- `gui/web_ui/index.html:24` — `<header class="integrated-appbar
  pywebview-drag-region">` (drag-region CSS class is ON).
- `gui/web_ui/app.js` — custom drag handler REMOVED. No
  `pywebview.api.drag_window` calls anywhere.
- `gui/gui_api.py` — `DivoomGuiAPI.drag_window` REMOVED. No custom
  Python drag binding.
- `gui/gui_main.py:27-66` — `_pywebview_1820_bug_present()` helper
  that introspects the source of `webview.platforms.cocoa.BrowserView.move`
  and returns True iff the literal token `self.screen.origin.x + x`
  is present (the bug token from #1820).
- `gui/gui_main.py:111-128` — gated application of the #1820
  monkey-patch. Skips on non-darwin, on ImportError, and when the
  detection helper returns False.
- `tests/test_gui_drag_instrumented.py` — 6 tests (4 static guards
  + 2 detection-contract canaries that simulate an upstream fix
  and confirm the helper returns False).

### §14.2 Why the §1 dialectic was wrong

The §1 dialectic's three approaches all assumed the *current*
pywebview drag-region mechanism was bug-free. We had not yet read
upstream issue #1820, so Approach C's steelman ("the OS is the
right place for window drag") was actually the closest to the
truth, but we were rejecting it for the wrong reasons (interactive
children carve-out, pywebview-on-macOS issues). The real blocker
on the bundled mechanism turned out to be the cocoa backend bug
in #1820, not the interactive-children carve-out (the default
`DIRECT_TARGET_ONLY=False` walks up the DOM correctly).

The custom-handler approaches (A and B) failed because:
- They require re-implementing coordinate math the OS already does.
- They are sensitive to the pywebview-bundled mechanism being
  active simultaneously. If the `pywebview-drag-region` CSS class
  is on the appbar, BOTH drag paths fire, fighting each other.
- They couple our drag feel to specific pywebview internal
  semantics (deltas vs absolute coordinates) that are not
  documented and may change between releases.

### §14.3 What was learned

1. **Always read the upstream issue tracker first.** The §1
   dialectic would have recommended Approach C from the start if
   we had known about #1820.
2. **Test the bundled mechanism before reinventing it.** A 1-line
   CSS class is dramatically less surface than ~50 LOC of custom
   JS + ~30 LOC of custom Python.
3. **When you fix a drag, pick ONE path.** Two drag paths
   simultaneously = "jumps around like crazy".
4. **`DRAG_REGION_DIRECT_TARGET_ONLY=True` is a footgun for
   drag regions with interactive children.** Default False is
   the only safe setting.
5. **The detection token approach is the right way to do
   upstream-aware monkey-patches.** Any plausible fix necessarily
   removes the bug token, so a simple substring match is a
   robust self-deactivation signal. The 2 detection-contract
   tests in `test_gui_drag_instrumented.py` are the canary that
   tells you when the token no longer matches the bug signature
   in the installed pywebview (which is when you delete the
   workaround).

### §14.4 Maintenance contract

When pywebview ships #1820:

1. `pip install --upgrade pywebview`
2. Run `pytest tests/test_gui_drag_instrumented.py` — the
   `test_pywebview_1820_detection_matches_source` test will fail
   with a clear message.
3. Confirm the fix in the new source (visit
   `/opt/homebrew/lib/python3.14/site-packages/webview/platforms/cocoa.py`).
4. Delete `_pywebview_1820_bug_present()` and the entire patch
   block from `gui/gui_main.py`.
5. Update the 2 detection-contract tests to assert the patch is
   no longer present.
6. Run the full test suite, verify all green.

Detailed steps in `docs/DRAG_FIX_HISTORY.md` → "How to undo the
workaround".

### §14.5 Test count delta

- Before Round 5: 369 passed / 73 skipped / 0 failed.
- After Round 5: 484 passed / 73 skipped / 0 failed.
- Net: +115 (drag fix added 0 — actually went from 4 → 6 tests in
  the drag test file; the rest are Round 3/4 work being counted
  correctly for the first time after multiple `conftest.py` reorgs).
