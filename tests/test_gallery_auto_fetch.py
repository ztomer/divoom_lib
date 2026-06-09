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
def _cat(paths: list[Path]) -> str:
    parts = []
    for p in paths:
        if p.exists():
            parts.append(p.read_text())
    return "\n".join(parts)

TEMPLATES_JS = _cat([
    REPO_ROOT / "divoom_gui" / "web_ui" / "templates_tools.js",
    REPO_ROOT / "divoom_gui" / "web_ui" / "templates_monthly_best.js",
    REPO_ROOT / "divoom_gui" / "web_ui" / "templates_widgets.js",
    REPO_ROOT / "divoom_gui" / "web_ui" / "templates_settings.js",
])
GALLERY_JS = REPO_ROOT / "divoom_gui" / "web_ui" / "gallery.js"
GALLERY_CSS = REPO_ROOT / "divoom_gui" / "web_ui" / "gallery.css"


# ── 1. No visible "Fetch Gallery" button ──────────────────────────────


def test_fetch_gallery_button_fully_removed() -> None:
    """R32 §A2: the ghost 'Fetch Gallery' button is gone entirely. Fetch
    auto-fires on style change and tab activation, so there's no button —
    not even a hidden one — and the JS no longer references its id."""
    src = TEMPLATES_JS
    assert "load-gallery-btn" not in src, (
        "load-gallery-btn should be removed entirely (R32 §A2)."
    )
    js = GALLERY_JS.read_text()
    assert "load-gallery-btn" not in js, (
        "gallery.js still references the removed load-gallery-btn id."
    )


def test_fetch_gallery_label_not_in_html() -> None:
    """R32 §A2: the 'Fetch Gallery' label should not appear in the markup."""
    src = TEMPLATES_JS
    assert "Fetch Gallery" not in src, (
        "'Fetch Gallery' label still present — the button was removed (R32 §A2)."
    )


# ── 2. Button labels renamed ──────────────────────────────────────────


def test_batch_sync_btn_renamed_to_update_device() -> None:
    src = TEMPLATES_JS
    assert "Push Selected to Device" not in src, (
        "Old 'Push Selected to Device' label still present — should be 'Update Device'."
    )
    assert re.search(
        r'<button\s+id="batch-sync-btn"[^>]*>\s*Update Device\s*</button>',
        src,
    ), "batch-sync-btn button must be renamed to 'Update Device'."


def test_sync_all_btn_moved_to_routines() -> None:
    """R32 §A1+§B: the multi-device sync button moved from Monthly Best to
    Settings → Routines and is labelled 'Sync devices now'."""
    src = TEMPLATES_JS
    assert "Sync All" not in src, "Old 'Sync All' label still present."
    # Must live in the Routines sub-tab now.
    routines = re.search(
        r'<div class="settings-tab-content" id="settings-routines">(.+?)`;',
        src, re.DOTALL,
    )
    assert routines is not None, "settings-routines block not found"
    assert re.search(
        r'<button\s+id="sync-all-btn"[^>]*>\s*Sync devices now\s*</button>',
        routines.group(1),
    ), "Routines must host the 'Sync devices now' (sync-all-btn) button."


def test_refresh_targets_btn_removed() -> None:
    """R15 §2: the Refresh button on the Devices card is gone —
    the same operation lives in Settings → Devices as a manual scan,
    and the list auto-refreshes on a 30s timer."""
    src = TEMPLATES_JS
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
    # R32 §A2: the change handler calls loadGallery() and persists the style
    # per device, so it's now an arrow wrapper rather than a bare reference.
    assert re.search(
        r"document\.getElementById\(\"gallery-classify\"\)"
        r"[\s\S]*?addEventListener\(\"change\",[\s\S]*?loadGallery\(\)",
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
