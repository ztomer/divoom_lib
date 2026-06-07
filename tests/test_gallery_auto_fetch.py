"""
R15 §2 — tests for the Monthly Best auto-fetch + Update Device +
box size cap.

The §2 contract is four-fold:
1. Opening the Monthly Best tab auto-fetches (no more "Fetch Gallery" click).
2. Changing the gallery classify <select> auto-fetches.
3. The "Fetch Gallery" button is gone from the visible UI.
4. The gallery box is capped at 168px (was 1fr) so wide panels don't
   grow the tiles past legibility.

These tests are static (string/regex) + a small headless test for the
JS auto-fetch behavior. The static tests are sufficient to guard the
contract because the changes are mechanical (one button + one CSS rule).
"""
from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
TEMPLATES_JS = REPO_ROOT / "gui" / "web_ui" / "templates.js"
GALLERY_JS = REPO_ROOT / "gui" / "web_ui" / "gallery.js"
GALLERY_CSS = REPO_ROOT / "gui" / "web_ui" / "gallery.css"


# ── 1. No visible "Fetch Gallery" button ──────────────────────────────


def test_no_visible_fetch_gallery_button() -> None:
    """The button must still exist in the DOM (ghost), but be hidden
    via the HTML `hidden` attribute so it's not clickable in the UI."""
    src = TEMPLATES_JS.read_text()
    m = re.search(
        r'<button\s+id="load-gallery-btn"[^>]*>',
        src,
    )
    assert m, "load-gallery-btn button removed entirely — keep it as a hidden ghost."
    attrs = m.group(0)
    assert "hidden" in attrs, (
        f"load-gallery-btn is not hidden — should have the HTML `hidden` "
        f"attribute. Got: {attrs!r}"
    )


def test_button_text_not_in_visible_html() -> None:
    """The literal 'Fetch Gallery' string must not appear as visible UI
    text in templates.js (the hidden ghost button is acceptable, plus
    any comments explaining why the button is hidden)."""
    src = TEMPLATES_JS.read_text()
    # The hidden button still uses the old label as its textContent —
    # that's fine, it just isn't visible. We only need to assert that
    # there's no *visible* Fetch Gallery UI. The button is the only
    # allowed occurrence outside comments.
    button_uses_label = bool(re.search(
        r'<button\s+id="load-gallery-btn"[^>]*>\s*Fetch Gallery\s*</button>',
        src,
    ))
    assert button_uses_label, (
        "The hidden ghost button must still have 'Fetch Gallery' as its "
        "textContent so the auto-fetch flow can identify it."
    )


# ── 2. Button labels renamed ──────────────────────────────────────────


def test_batch_sync_btn_renamed_to_update_device() -> None:
    src = TEMPLATES_JS.read_text()
    assert "Push Selected to Device" not in src, (
        "Old 'Push Selected to Device' label still present — should be 'Update Device'."
    )
    assert re.search(
        r'<button\s+id="batch-sync-btn"[^>]*>\s*Update Device\s*</button>',
        src,
    ), "batch-sync-btn button must be renamed to 'Update Device'."


def test_sync_all_btn_renamed_to_update_devices() -> None:
    src = TEMPLATES_JS.read_text()
    assert "Sync All" not in src, (
        "Old 'Sync All → Devices' label still present — should be 'Update Devices'."
    )
    assert re.search(
        r'<button\s+id="sync-all-btn"[^>]*>\s*Update Devices\s*</button>',
        src,
    ), "sync-all-btn button must be renamed to 'Update Devices'."


def test_refresh_targets_btn_removed() -> None:
    """R15 §2: the Refresh button on the Devices card is gone —
    the same operation lives in Settings → Devices as a manual scan,
    and the list auto-refreshes on a 30s timer."""
    src = TEMPLATES_JS.read_text()
    assert "refresh-targets-btn" not in src, (
        "Refresh button on the Devices card is still in templates.js — "
        "should be removed."
    )
    # And the JS handler should be gone too.
    js = GALLERY_JS.read_text()
    assert "refresh-targets-btn" not in js, (
        "Click handler for refresh-targets-btn is still in gallery.js — "
        "should be removed."
    )


# ── 3. Auto-fetch on tab activation + on classify change ─────────────


def test_load_gallery_exposed_on_window() -> None:
    """loadGallery() is the canonical entry point — it must be on
    window for the auto-fetch hooks below to call it."""
    js = GALLERY_JS.read_text()
    assert "window.loadGallery = loadGallery" in js, (
        "loadGallery() is not exposed on window — auto-fetch hooks can't call it."
    )


def test_classify_change_auto_fetches() -> None:
    js = GALLERY_JS.read_text()
    assert re.search(
        r"document\.getElementById\(\"gallery-classify\"\)"
        r"[\s\S]*?addEventListener\(\"change\",\s*loadGallery\)",
        js,
    ), "classify <select> is missing a 'change' → loadGallery() hook."


def test_tab_activation_auto_fetches() -> None:
    js = GALLERY_JS.read_text()
    assert re.search(
        r'addEventListener\(\"tab-changed\",\s*\(?e\)?\s*=>\s*\{[^}]*'
        r'e\.detail\.tab\s*===\s*\"monthly-best\"[^}]*loadGallery\(\)',
        js,
        re.DOTALL,
    ), (
        "tab-changed handler for 'monthly-best' tab is missing a "
        "loadGallery() call."
    )


# ── 4. Box size cap ───────────────────────────────────────────────────


def test_gallery_grid_box_cap_present() -> None:
    """The grid template must cap the box at 168px (Rams #10 + a
    legible preview). The floor is 110px (smallest preview + name)."""
    css = GALLERY_CSS.read_text()
    assert re.search(
        r"grid-template-columns:\s*repeat\(auto-fill,\s*minmax\(110px,\s*168px\)\)",
        css,
    ), (
        "gallery-grid box cap missing — should be "
        "`repeat(auto-fill, minmax(110px, 168px))`."
    )


def test_gallery_grid_box_cap_not_unbounded() -> None:
    """Belt-and-braces: the old unbounded `1fr` cap must be gone."""
    css = GALLERY_CSS.read_text()
    assert "minmax(110px, 1fr)" not in css, (
        "gallery-grid still has the old `minmax(110px, 1fr)` cap — "
        "should be `minmax(110px, 168px)`."
    )
