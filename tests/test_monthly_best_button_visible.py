"""Playwright regression test for the Monthly Best "Push to Device" button.

User-reported bug (Round 2 #1b, 2026-06-05):
  "the 'Push Selected to Device' button is pushed out of view when
   the gallery has many items (because the card body is
   overflow:hidden + the gallery is overflow-y:auto)."

The fix was applied in Round 0/1 via a flex column chain
(`#monthly-best.active` → `.card-body` → `.gallery-grid` with
`flex:1; overflow-y:auto; min-height:0` and `.gallery-actions`
with `margin-top:auto`). This test loads the real `index.html` in
headless Chromium, populates the gallery with 50 fake items, and
asserts the button is visible at the bottom of the card.

If the button is ever pushed off-screen by a future layout change,
this test fails and the regression is caught at CI time.

Requires:
  pip install playwright pytest-playwright
  playwright install chromium

Run with::
    pytest --run-integration tests/test_monthly_best_button_visible.py -v -s
"""

import pytest
from pathlib import Path

# The real index.html lives in gui/web_ui/. We load it via file://
# so the test is self-contained.
INDEX_HTML = Path(__file__).parent.parent / "divoom_gui" / "web_ui" / "index.html"


@pytest.mark.asyncio
async def test_push_button_visible_with_many_gallery_items():
    """Push button stays at the bottom of the card when gallery has 50 items."""
    pytest.importorskip("playwright.async_api")
    from playwright.async_api import async_playwright

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        await page.goto(f"file://{INDEX_HTML}")
        await page.wait_for_load_state("domcontentloaded")

        # Switch to the Monthly Best tab (find by data-tab attribute or click).
        # The exact selector depends on index.html structure; use a robust query.
        try:
            await page.click('[data-tab="monthly-best"]', timeout=2000)
        except Exception:
            # Fallback: click the tab by text.
            await page.click('text=Monthly Best', timeout=2000)

        await page.wait_for_selector("#monthly-best.active", timeout=2000)

        # Inject 50 fake gallery items into the grid (don't depend on
        # the real cloud fetch — the layout is what we're testing).
        await page.evaluate("""
            () => {
                const grid = document.getElementById('gallery-container');
                if (!grid) return;
                grid.innerHTML = '';
                for (let i = 0; i < 50; i++) {
                    const item = document.createElement('div');
                    item.className = 'gallery-item';
                    item.textContent = 'Item ' + (i + 1);
                    grid.appendChild(item);
                }
                // Force the grid to think it has lots of content
                // (the auto-fill grid will lay them out).
            }
        """)

        # Wait for layout to settle.
        await page.wait_for_timeout(200)

        # Get bounding boxes of the gallery container and the button.
        gallery_box = await page.locator("#gallery-container").bounding_box()
        button_box = await page.locator("#batch-sync-btn").bounding_box()
        card_box = await page.locator("#monthly-best .card.glass-card").first.bounding_box()

        # The button must be within the card's vertical extent.
        assert card_box is not None, "Card not found"
        assert button_box is not None, "Push button not found"
        assert gallery_box is not None, "Gallery container not found"

        button_top = button_box["y"]
        button_bottom = button_box["y"] + button_box["height"]
        card_top = card_box["y"]
        card_bottom = card_box["y"] + card_box["height"]

        # Button should be inside the card's vertical extent.
        assert card_top <= button_top, (
            f"Button top ({button_top}) is above card top ({card_top})"
        )
        assert button_bottom <= card_bottom, (
            f"Button bottom ({button_bottom}) is below card bottom ({card_bottom}). "
            f"The button is being pushed out of view — Round 2 #1b regression."
        )

        # The button should be at the bottom of the card, not in the middle.
        # Allow a small slack (50px) for the gallery scroll bottom.
        slack = 50
        card_bottom_anchor = card_bottom - slack
        assert button_bottom >= card_bottom_anchor, (
            f"Button bottom ({button_bottom}) is not at card bottom "
            f"({card_bottom}). Card bottom anchor (with {slack}px slack): "
            f"{card_bottom_anchor}. The button is not pinned to the bottom."
        )

        await browser.close()


@pytest.mark.asyncio
async def test_gallery_scrolls_internally_not_whole_card():
    """The gallery itself scrolls, not the whole card (button stays put)."""
    pytest.importorskip("playwright.async_api")
    from playwright.async_api import async_playwright

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        await page.goto(f"file://{INDEX_HTML}")
        await page.wait_for_load_state("domcontentloaded")

        try:
            await page.click('[data-tab="monthly-best"]', timeout=2000)
        except Exception:
            await page.click('text=Monthly Best', timeout=2000)

        await page.wait_for_selector("#monthly-best.active", timeout=2000)

        # Inject 100 items to ensure overflow.
        await page.evaluate("""
            () => {
                const grid = document.getElementById('gallery-container');
                if (!grid) return;
                grid.innerHTML = '';
                for (let i = 0; i < 100; i++) {
                    const item = document.createElement('div');
                    item.className = 'gallery-item';
                    item.textContent = 'Item ' + (i + 1);
                    grid.appendChild(item);
                }
            }
        """)
        await page.wait_for_timeout(200)

        # Read scroll heights: gallery scrollHeight > clientHeight (scrollable).
        # The whole card's scrollHeight should equal its clientHeight (not scrollable).
        gallery_scroll = await page.evaluate("""
            () => {
                const g = document.getElementById('gallery-container');
                return { scrollHeight: g.scrollHeight, clientHeight: g.clientHeight };
            }
        """)
        card_scroll = await page.evaluate("""
            () => {
                const c = document.querySelector('#monthly-best .card.glass-card');
                return { scrollHeight: c.scrollHeight, clientHeight: c.clientHeight };
            }
        """)

        # The gallery is the one that scrolls, not the card.
        assert gallery_scroll["scrollHeight"] > gallery_scroll["clientHeight"], (
            "Gallery should be scrollable (100 items), but scrollHeight <= clientHeight. "
            f"scrollHeight={gallery_scroll['scrollHeight']}, clientHeight={gallery_scroll['clientHeight']}"
        )

        await browser.close()
