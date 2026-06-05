# Visual Regression Fix Plan _(2026-06-04)_

> **Status:** plan — not yet implemented.
> **Author:** build session, follow-up to commit `f2d2507d` "in progress".
> **Goal:** Fix all visual regressions and bugs in the in-progress commit; ship one clean
> commit with a passing test suite, and add an instrumented test for window drag so
> the recurring regression can never silently come back.

---

## 0. Current state snapshot

- **Tests:** 306 passed / 72 skipped / 0 failed (up from 290 at session start).
- **Working tree:** 1 unstaged file (`gui/web_ui/channels.js`, −11 lines that delete
  the now-orphaned `channel-options-title` text-update JS block).
- **Last commit:** `f2d2507d` "in progress" — `+170/−94` across 7 files.
- **Bluetooth:** per user report, works "almost everything correctly" now (was
  SPP-silent at end of Phase 8 — change on user's end is unverified).
- **Pytest:** `tests/test_gui_api.py` passes 17/17 including new `test_drag_window`
  (which only exercises the math, not the real OS).

## 0.1 Design principles (Kare + Rams)

Per user (2026-06-04): **Kare = Susan Kare** (Apple Macintosh bitmap icon
designer, Chicago font, "Solitaire" cursor) and **Deiter = Dieter Rams**
(Braun industrial designer of the 10 principles). The GUI should follow their
**combined** principles — applied at every fix, not just the ambient layout.

### Susan Kare principles (bitmap, honest, iconic)

- **Pixel-perfect clarity** — render at the native grid, no anti-aliasing on
  device previews
- **Honest representation** — an icon/preview looks like what the thing
  actually does, not what we wish it did
- **Restraint** — the fewest pixels possible to convey meaning
- **Friendly** — approachable, not corporate
- **Platform-native** — use the OS's own controls where they exist (e.g.
  the macOS color picker is correct, don't reinvent it)

### Dieter Rams' 10 principles (good design is…)

1. **Innovative** — don't copy, find the right idea
2. **Useful** — every element earns its place
3. **Aesthetic** — minimal, not barren
4. **Understandable** — self-explanatory
5. **Unobtrusive** — chrome stays out of the user's way
6. **Honest** — no fake animations, no fake states
7. **Long-lasting** — survives the next refactor
8. **Consistent** — the same idea looks the same in every place
9. (Environmentally friendly — N/A for UI)
10. **As little design as possible** — "less but better"

### How this lens changes the fixes

| Fix | Kare/Rams verdict |
|---|---|
| §2.1 Custom Art button pinned to bottom | Rams #4 Understandable + #10 As little as possible. The flex layout is the right tool; no decoration needed. |
| §2.2 Color-picker `<div>` → `<label>` | **Kare: use platform-native** — `<label>` is the HTML-native click-to-open-input pattern. Don't reinvent with JS. |
| §3 Ambient previews | **Rams #6 Honest** — previews must show what the device actually does. **Kare: pixel-perfect, restraint, no animation that doesn't exist on the device.** |
| §4 Monthly Best empty space | **Rams #10 As little as possible** — fill empty space with content, not decoration. **Kare: if there's nothing to show, say so with a clear empty-state, don't fake it.** |
| §5 Live widgets broken | **Rams #4 Understandable** — if a widget fails, surface it honestly. **Kare: don't show a broken image, show a clear error glyph.** |
| §6 Device selector move speaker/res out | **Rams #5 Unobtrusive** — speaker/res aren't selector concerns. The image becomes the main visual (Kare: bitmap clarity). |

### Implications for the ambient layout decision (Q2)

The user's "group template colors + show color choosers + maybe 10 favorites"
goes through this lens:

- **Group template colors + show color choosers**: yes — Rams #4 (one place
  for color decisions), Kare: a clean swatch grid is iconic and clear
- **10 last-selected as favorites**: **probably no** — Rams #10 says "as
  little as possible". 10 is decorative bloat. Propose **5 favorites** with
  an explicit user-count rationale (or make it user-configurable, but
  default to 5)
- **Layout**: a single row of 6 fixed swatches + 1 color-picker-circle + a
  5-favorites row, no nested cards, no shadows on swatches. Kare-style
  bitmap clarity. Rams #3 Aesthetic: minimal.

**Q2 is now resolved with a concrete proposal:** single row of fixed swatches
+ color picker + 5-favorites row. No decorative bloat. Kare/Rams
consensus.

### Decision records (from this session)

| # | Hotspot from diff | Verdict |
|---|---|---|
| 1 | Appbar `no-drag` (relies on JS drag) | **Regression — see §1.1** |
| 2 | Removed channel-options-title `<h3>` | Intentional |
| 3 | Sidebar image filter removed (grayscale → full color) | Intentional for now |
| 4 | "Push to Device" button always-visible at bottom | **Bug — see §2.1** |
| 5 | Rename `appbarSelect` → `sidebarDeviceSelect` | Yes, do it |
| 6 | Color-picker wrapper click delegation | **Bug — see §2.2** |
| 7 | Dead CSS: `.appbar-device` class + `select.appbar-device-select` rule | **Remove (now item 8 in user's list)** |
| 8 | (the user's "8." mapped to item 7 above) | Remove dead CSS |

---

## 1. Window drag regression — highest priority

### 1.1 Symptom
**Window cannot be moved** (regression from previous working state). The window
**can** be resized. The drag handler is in `gui/web_ui/widgets.js:13-29`:

```js
let isDragging = false, lastScreenX = 0, lastScreenY = 0;
const appbar = document.querySelector(".integrated-appbar");
if (appbar) {
    appbar.addEventListener("mousedown", (e) => {
        if (e.button === 0 && !e.target.closest("button, select, input")) {
            isDragging = true; lastScreenX = e.screenX; lastScreenY = e.screenY;
        }
    });
    window.addEventListener("mousemove", (e) => {
        if (!isDragging) return;
        const dx = e.screenX - lastScreenX, dy = e.screenY - lastScreenY;
        lastScreenX = e.screenX; lastScreenY = e.screenY;
        if ((dx || dy) && window.pywebview?.api?.drag_window) window.pywebview.api.drag_window(dx, dy);
    });
    window.addEventListener("mouseup", () => isDragging = false);
}
```

**Why it likely fails in practice:**
- The mousedown event fires only if the **event actually reaches** the
  `appbar` element. With the new sidebar layout, the appbar may be covered by a
  higher-z element, or `e.button` may not be 0 (e.g. secondary click on
  touchpads).
- `e.screenX`/`e.screenY` may be 0/0 in pywebview under some conditions; `clientX`
  is the more reliable choice in pywebview.
- The handler is registered **inside `DOMContentLoaded` in widgets.js** which
  runs as a separate script — order-of-execution risk.
- The handler is **never re-attached** if the appbar element is replaced (e.g.
  during template re-injection).

### 1.2 Required fixes

1. **Move the drag handler to `app.js`** (the entry-point script) and register
   it at the end of `DOMContentLoaded` (not inside any setTimeout) so it
   attaches as soon as the DOM is ready.
2. Use `e.clientX`/`e.clientY` for the relative delta (pywebview reliable), and
   keep `e.screenX` only as a fallback.
3. Add `preventDefault()` on the mousedown so it doesn't trigger text-selection
   drag.
4. Add the `appbar` listener via delegation off `document` so it survives any
   future re-injection: `document.addEventListener("mousedown", handler, true)`.
5. The CSS at `gui/web_ui/appbar.css:13` (`-webkit-app-region: no-drag`) is
   **correct** — keep it. Without it, the OS-level drag fights the JS one.

### 1.3 Instrumented test (the user's #1 ask)

**What "instrumented" means here:** a test that loads the GUI in a real (or
headless) WebView2/WKWebView instance, simulates a `mousedown`+`mousemove` on
`.integrated-appbar`, and asserts that `pywebview.api.drag_window` is called
with non-zero deltas. Must run in CI without sudo.

**Approach (recommended):**
- Add `tests/test_gui_drag_instrumented.py` using **Playwright** (already in the
  Chromium ecosystem, can drive pywebview in headless mode if needed).
- More realistic alternative: use **Selenium WebDriver** with **chromedriver**
  pointed at a small `file://` URL serving the appbar HTML in isolation, with
  a stub `pywebview` global injected that records `drag_window` calls.
- Simplest sustainable: **unit-test the delegation logic itself** by extracting
  the drag handler into a pure function `computeDragDelta(prev, curr) →
  (dx, dy)` and testing that, plus a DOM-level test that the handler is
  attached to the right element.

**The test the user asked for is the DOM-level one.** Concretely:

```python
def test_appbar_has_drag_handler_attached():
    """Regression test: window drag must be wired in DOMContentLoaded.
    Recurring regression — last broke in commit f2d2507d."""
    # Use jsdom or a real browser
    from selenium import webdriver
    driver = webdriver.Chrome()
    driver.get("file:///path/to/index.html")
    # Inject stub pywebview
    driver.execute_script("window._dragCalls = []; window.pywebview = {api: {drag_window: (dx, dy) => window._dragCalls.push([dx, dy])}};")
    # Simulate drag
    appbar = driver.find_element(By.CSS_SELECTOR, ".integrated-appbar .appbar-drag-spacer")
    ActionChains(driver).click_and_hold(appbar).move_by_offset(20, 10).release().perform()
    assert driver.execute_script("return window._dragCalls") != []
```

This requires a chromedriver to be available in CI. **Decision needed:** do we
gate this test on `--run-integration` (like `--run-hardware`), or do we install
chromedriver in CI by default?

**See open question Q1.**

---

## 2. Channels panel fixes

### 2.1 Custom Art: button always visible at bottom

**Current state:** `panel-design` content lives in a `custom-art-scroll-container`
with `max-height:280px; overflow-y:auto`. The "Push to Device" button is
**outside** the scroll container, full width, after the scroll area. Total panel
height is `280px + button_height + padding`. On a tall window, the panel does
not fill the available space and the gallery grid stops at 280px.

**Required fix:** make the panel a flex column where the scroll area is `flex:1`
and the button is pinned to the bottom. Concretely, in `index.html` and
`channels.css`:

```html
<div class="channel-panel" id="panel-design" style="display:flex; flex-direction:column; min-height:0;">
    <div class="custom-art-scroll-container" style="flex:1; overflow-y:auto; ...">...</div>
    <button id="apply-custom-art-btn" class="glow-btn" style="width:100%; flex-shrink:0;">Push to Device</button>
</div>
```

The `panel-design` parent is already `display:flex; flex-direction:column` (the
grid-layout card body), so the flex children stack and the button anchors to
the bottom.

**Test:** add a unit test that asserts `#panel-design` has `display:flex;
flex-direction:column` and that `.custom-art-scroll-container` has `flex:1`.

### 2.2 Ambient: color-picker click delegation bug

**Current state:** `channels.js` (unstaged) registers a click delegation on
`.color-picker-wrapper`:

```js
const colorPickerWrapper = document.querySelector(".color-picker-wrapper");
if (colorPickerWrapper && ambientColorInput) {
    colorPickerWrapper.addEventListener("click", (e) => {
        if (e.target !== ambientColorInput) {
            ambientColorInput.click();
        }
    });
}
```

**The bug:** clicking the **4px outer ring** of the wrapper (the part that
extends past the underlying `<input>`) does NOT fire the input's click — but
the user expects it to. The input itself is `44×44` centered with `top:-4px;
left:-4px`, so it overflows the 36×36 wrapper. Clicks within the wrapper
bounds that hit transparent padding do nothing.

**Required fix:** add `pointer-events:none` to the inner input (it already has
`border:none; background:none`), and use a **label** wrapper instead of a
click-handler hack:

```html
<label class="color-picker-wrapper" style="...">
    <input type="color" id="ambient-color-input" value="#00ffcc" style="...">
</label>
```

Native `<label>` wrapping an input triggers the input's click anywhere inside
the label's bounding box. No JS delegation needed. Remove the `channels.js`
delegation block.

### 2.3 Ambient: layout per Kare/Deiter

Per user: "I'm not sure about the layout. Kare and Deiter should decide."

**Defer this design decision** — it's not blocking the bug fixes. The
regression fixes (2.1, 2.2) are independent. The ambient color picker layout
is a design call.

**Open question Q2:** do Kare/Deiter need to weigh in before we ship 2.1 and
2.2, or can we ship those now and have them review the ambient layout later?

---

## 3. Ambient preview fixes

Per user — these are **wrong device previews**. Fix `AMBIENT_PREVIEWS` in
`gui/web_ui/channels.js` and the CSS that renders them.

| Mode | User's description of actual device behavior | Current preview | New preview |
|---|---|---|---|
| 0 (Plain) | solid color | cyan box, 60px | keep, but apply `updateAmbientPreviewsColor` color |
| 1 (Love / pulse) | "color transition mode — colors transition slowly across the color spectrum" | pink heart-beat pulse | **CSS gradient animation** that cycles hue continuously (e.g. `animation: hue-shift 8s infinite linear`) |
| 2 (Plants) | "fixed pattern — red background, four single pixel vertical lines (1px blue, 4 red, 1 blue, 4 red, 1 blue, 4 red, 1 blue)" | green breathing | **Pixel-art 16x16 grid** with red bg + 4 blue vertical stripes at cols 0, 4, 8, 12. Render as inline SVG or CSS grid of 16×16 divs. |
| 3 (Sleeping) | "green static color" | purple fade | **solid green box** with no animation |
| 4 (No mosquito) | "low brightness orange" | yellow strobe | **solid orange box** with `opacity: 0.4` or background `rgba(255, 165, 0, 0.4)` |

**Implementation:** rewrite the `AMBIENT_PREVIEWS` object in `channels.js`
using the description above. The pixel-art for "plants" can be inline SVG with
`<rect>` elements — clean and pixel-perfect at any size.

**Test:** snapshot the SVG/text content of `.ambient-preview` elements to
assert the four "fixed" modes match the spec (plain=color, sleeping=green,
mosquito=orange, plants=4-blue-stripe). The Love preview is harder to test
snapshot-style (CSS animation) — defer that to visual review.

---

## 4. Monthly best — empty space

**Current state:** `#monthly-best` section is rendered from
`templates.js#monthlyBest` (a left "Gallery" card + a right "Preview" card
presumably). User says "empty space".

**Hypotheses (need to confirm with user):**
- The right "Preview" card is always empty until the user clicks a gallery
  item. Maybe it should be hidden until then, OR show a placeholder.
- The left gallery grid is loading slowly (cloud fetch on tab activate), so
  the tab appears empty for the first second.
- The `height: 100%` on `monthly-best-layout` is not actually filling the
  main-content area (the `main.main-content` doesn't have `height: 100%`).

**Open question Q3:** what does the user see on the Monthly Best tab? (Empty
grid? empty preview pane? both? screenshot would be best.)

**Likely fix (without confirmation):**
- Add a `flex:1; min-height:0` chain to the gallery card so the grid fills
  the available space.
- Add a placeholder state in the right preview card when nothing is selected.

---

## 5. Live widgets — multiple regressions

User reports:
- "doesn't show album preview"
- "doesn't allow selection"
- "system monitor doesn't work, etc."

**Hypotheses (need to confirm with user):**
- "Album preview" = `#music-cover-img` should be set to the artwork URL
  returned by `get_current_track_info`. If the python side is failing, no
  artwork is set. But the template has `src="assets/pixoo.png"` as default,
  so the image should at least show the Pixoo logo.
- "Doesn't allow selection" = the `bindCardSelection` click handler may have
  a regression. The check is:
  ```js
  if (e.target.closest("input") || e.target.closest("button") || e.target.closest("select")) {
      if (e.target.closest("#apply-stock-btn") || ...) {
          selectWidget(widgetName);
      }
      return;
  }
  ```
  Wait — this is `return` for the inner block, not the outer. The `return`
  exits the click handler before `selectWidget(widgetName)` is called on the
  body of the card. So clicking the card body **does** call `selectWidget` —
  only clicking an input/button early-returns. This logic is fine.

  BUT: I see at widgets.js:388-402, `bindCardSelection` registers the handler
  on each card. If the cards are re-rendered when switching tabs (because
  `templates.widgets` is innerHTML-ed in), the **listener is lost**. The
  `innerHTML` assignment on `#data-sources` happens in `app.js:209` on
  `DOMContentLoaded`, but if the user switches tabs and the templates are
  re-injected, the listeners vanish.

  Looking at `app.js:206-210`:
  ```js
  if (document.getElementById('monthly-best') && window.DivoomTemplates?.monthlyBest) {
      document.getElementById('monthly-best').innerHTML = window.DivoomTemplates.monthlyBest;
  }
  if (document.getElementById('data-sources') && window.DivoomTemplates?.widgets) {
      document.getElementById('data-sources').innerHTML = window.DivoomTemplates.widgets;
  }
  ```
  This runs **once** on DOMContentLoaded. So the templates are inlined once.
  But the `bindCardSelection` in widgets.js also runs once on DOMContentLoaded,
  which is **after** the templates are inlined (widgets.js loads after
  app.js per index.html:355 vs 353). So order should be:
  1. app.js runs first (line 353) → inlines the templates
  2. widgets.js runs second (line 355) → binds click handlers

  Hmm, but the `app.js:209` line is **inside the `setTimeout(..., 1000)` at
  app.js:441** — let me re-check.

  Wait, looking at the actual code: `app.js:206-210` is **inside the
  `document.addEventListener("DOMContentLoaded")` block at app.js:203**. Not
  in any setTimeout. So it runs at DOM ready, before widgets.js (which is
  loaded after).

  So the templates are inlined first, then the click handlers attach to the
  inlined cards. That should work.

  Unless... the `tab-changed` listener at `widgets.js:435` calls
  `selectWidget(selectedWidget)` which calls `syncActiveWidget` which calls
  Python APIs that may not be ready. That's a separate issue.

  **OR** the cards' content includes nested elements (like a `<form>` or a
  `<button>`) that prevent the click from reaching the card.

  **Best guess:** the user's "doesn't allow selection" is actually "clicking
  the card highlights it, but the album art doesn't show on the device." That
  would be a different bug (python-side `apply_widget` failing).

  Or possibly: clicking the card body calls `selectWidget(widgetName)` but
  `selectWidget` is **defined** in the `DOMContentLoaded` of widgets.js —
  if that script hasn't finished initializing by the time the user clicks,
  there's a JS error.

- "System monitor doesn't work" = `refreshSysmonPreview()` or
  `apply_system_stats()` failing. Look at the python side.

**Open question Q4:** Can the user open Chrome DevTools in the running app
(right-click → Inspect) and paste any errors from the Console? Or take a
screenshot of the Live Widgets tab?

**Likely fix (without confirmation):** add a `console.error` to
`pollTrackInfo`'s `try { }` so failures are visible, then have the user
retry. And add `setTimeout(() => bindCardSelection(...), 500)` to widgets.js
as a safety net for any future template re-injection.

---

## 6. Device selector sidebar

Per user:
- Move **speaker icon** and **resolution** to Settings tab
- In the bluetooth table and wi-fi table they were relevant (i.e. settings
  has device tables — find them in `settings.js`)
- Increase the **preview image** to fill the freed space
- The selector will move one line down (since image grows)

**Current state in `index.html:97-116`:**
```html
<div class="sidebar-device-panel" id="connected-device-banner">
    <div class="sidebar-device-preview">
        <img id="banner-device-image" src="assets/pixoo.png" alt="Device Preview">
    </div>
    <select id="sidebar-device-select" class="sidebar-device-select">...</select>
    <span id="banner-device-name" style="display: none;">No Connected Screen</span>
    <div class="sidebar-device-status">
        <span id="sidebar-device-speaker-container" title="Speaker Status">
            <svg ... id="sidebar-speaker-icon">...</svg>
        </span>
        <span id="banner-device-res" class="sidebar-device-res">16x16</span>
    </div>
    <span id="banner-device-mac" style="display: none;">-</span>
    <span id="banner-device-speaker" style="display: none;">No</span>
</div>
```

**Plan:**
1. Remove `#sidebar-device-speaker-container` and `#banner-device-res` from
   the sidebar.
2. Move them to a new column in the bluetooth table and Wi-Fi table in
   `settings.js` (find the table rows in templates or settings DOM).
3. Enlarge `.sidebar-device-preview` from 80×80 to something bigger (proposed:
   120×120, or 100% of the available width). The image becomes the main
   visual.
4. The selector moves one line down (the previous "speaker+res" row is gone).

**Open question Q5:** what are the bluetooth and wi-fi table IDs/selectors in
`settings.js`? Need to read the file to plan the column addition.

---

## 7. Cleanup

- **Dead CSS:** `gui/web_ui/appbar.css:24-43` (`.appbar-device` class +
  `select.appbar-device-select` rule) — DOM no longer uses either. Delete.
- **Variable rename:** `appbarSelect` → `sidebarDeviceSelect` at
  `gui/web_ui/app.js:423` for clarity.
- **Unstaged channels.js:** confirm the user's intent — does the
  `channel-options-title` text-update code need to stay (if the element will
  be re-added) or be deleted (matches the unstaged −11 lines)? **Decide before
  committing.**
- **No more `appbar-device` class anywhere:** grep for it across all files
  and ensure zero references remain.

---

## 8. Phasing (per F4 plan → execute → document)

### Phase A — Fixes that don't need answers _(2 hr)_

1. §2.1 Custom Art button pinned to bottom
2. §2.2 Color-picker wrapper → `<label>` (Kare: platform-native)
3. §3 Ambient preview rewrites (Kare: pixel-perfect, Rams #6: honest)
4. §7 Dead CSS removal + variable rename
5. Channel-options-title decision (commit the unstaged −11 lines OR revert
   the HTML change — pick one)

### Phase A-bonus — Ambient layout per Kare/Rams _(1 hr)_

6. Implement the resolved Q2 layout: fixed-swatch row + color picker + 5
   favorites row. No decorative bloat. Rams #10.

### Phase B — Window drag fix + instrumented test _(3 hr)_

6. §1.1 Move drag handler to app.js, fix clientX/screenX, preventDefault
7. §1.3 Add `tests/test_gui_drag_instrumented.py` with Selenium or pure-DOM
8. Run with `--run-integration` flag (gate on it for CI by default)

### Phase C — Device selector sidebar move _(1 hr)_

9. §6 Move speaker/res to settings tables, enlarge preview image
10. Test that all references are updated

### Phase D — Monthly best + live widgets _(deferred)_

11. §4 Monthly best empty space — needs confirmation
12. §5 Live widgets — needs DevTools console output

### Phase E — Documentation _(30 min)_

13. Update `docs/CODE_REVIEW.md` Phase 9 "Visual regression cleanup" with
    what shipped per CHANGELOG stanza (D1 + D2)

---

## 9. Resolved questions (2026-06-04, 22:54 EDT)

**Q1.** **Run in CI by default.** Install chromedriver in the CI env. The
instrumented test catches the recurring regression on every commit.

**Q2.** **10 favorites** (user override of Rams #10). Layout: 6 fixed
template swatches + color picker circle + 10-favorites row. Kare/Rams
honored where it doesn't conflict with explicit user choice. Note for
the changelog: this is a deliberate non-application of Rams #10 per
user preference — Kare/Rams are guides, not laws (D4 explicit no-action
as output).

**Q3.** **Layout collapsed.** Both cards present but height/width chain
broken. Fix: ensure `.monthly-best-layout` and the two card bodies have
`flex:1; min-height:0` chain so they fill the available main-content
height. (The gallery grid inside uses `flex:1; overflow-y:auto;
min-height:0` already — likely the parents don't propagate height.)

**Q4.** **"you can install and run whatever you need"** — green light to
install chromedriver / Playwright. Plan: use Playwright Python
(`playwright install chromium`) for the drag test, which is more
maintained than raw Selenium. As a bonus, also run a headless Playwright
session against the running app to capture any live-widget console
errors — that resolves the "live widgets broken" regression
empirically (D2: document the decision not just the code).

**Q5.** **Settings restructure.** The bluetooth + wi-fi tables are in
the Settings form (sidebar → Settings tab → "devices" sub-section).
**Move the connectivity/privacy segment to its own sub-tab** (e.g.
"Privacy" or "Connectivity") within Settings. The "devices" sub-section
stays for bluetooth + wi-fi. This is a more substantial restructure
than originally scoped.

**Q6.** **Dead, delete the JS.** Commit the unstaged −11 lines from
`channels.js`. The `<h3 id="channel-options-title">` element was
removed in the in-progress commit and won't return.

---

## 10. What deliberately won't ship in this session

- A wholesale redesign of the ambient color layout (deferred to Kare/Deiter
  per B2 — design decisions need design owners).
- Any changes to the BT SPP transport layer (Phase 8 already documented as
  blocked at the OS level).
- Refactoring the GUI files to a framework (React/Vue/Svelte) — out of scope.
- Making the arranger popup work on mobile (not a target platform).

---

## 11. File-level diff plan (preview)

```
M  gui/web_ui/app.js
    - Remove the 8-line force-styling block (already done in commit)
    - Rename appbarSelect → sidebarDeviceSelect (line 423)
    - Move appbar mousedown drag handler from widgets.js to here
    - Use clientX/Y, add preventDefault, use document delegation

M  gui/web_ui/index.html
    - panel-design: change custom-art-scroll-container to flex:1
    - Push-to-Device button: keep outside scroll, full width, flex-shrink:0
    - .color-picker-wrapper: change <div> to <label>
    - .sidebar-device-status: remove speaker+res spans (move to settings)
    - .sidebar-device-preview: enlarge container (proposed: 120x120)

M  gui/web_ui/widgets.js
    - Remove the appbar drag mousedown/mousemove/mouseup block (moved to app.js)
    - Keep all the rest (audio levels, stocks, sysmon)

M  gui/web_ui/channels.js
    - Delete the click delegation on .color-picker-wrapper (label handles it)
    - Rewrite AMBIENT_PREVIEWS object per §3

M  gui/web_ui/channels.css
    - Add #panel-design { display:flex; flex-direction:column; min-height:0; }
    - Add .custom-art-scroll-container { flex:1; min-height:0; }
    - Add hue-shift keyframes for the Love/pulse preview
    - Reduce .clock-preview-box or .mini-clock-svg if they push the design
      panel off the screen (size sanity check)

M  gui/web_ui/sidebar.css
    - .sidebar-device-preview: width/height 80px → 120px
    - .sidebar-device-status: display:none (or remove)

M  gui/web_ui/appbar.css
    - DELETE .appbar-device { ... } block (lines 23-31)
    - DELETE select.appbar-device-select { ... } block (lines 33-43)
    - KEEP -webkit-app-region: no-drag on .integrated-appbar

A  tests/test_gui_drag_instrumented.py
    - Selenium-based test asserting the appbar drag handler is wired
    - Gated behind --run-integration flag

A  tests/test_ambient_previews.py
    - Snapshot test asserting AMBIENT_PREVIEWS HTML for the 4 static modes
      matches the spec (plain=color, sleeping=green, mosquito=orange,
      plants=4-blue-stripe pattern)

M  docs/CODE_REVIEW.md
    - Add Phase 9 "Visual regression cleanup" stanza
```

---

**End of plan. Awaiting answers to Q1–Q6 before implementation begins.**
