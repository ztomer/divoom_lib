"""Playwright regression tests for two backlog items (docs/BACKLOG.md):

- #57 Appbar connection tooltips: the transport dots live in `.corner-transports`
  (position:fixed; bottom:10px), so the :hover tooltip must open UPWARD. It was
  anchored `top: calc(100% + 8px)` → rendered past the window's bottom edge
  (invisible). This asserts the ::after tooltip anchors above the dot.
- #58 (R32 revision): Settings moved out of the sidebar into an appbar gear pill;
  the device panel is now the bottom element of the sidebar. The sidebar must NOT
  contain a Settings nav button, and the appbar must carry a #appbar-settings-btn
  with data-tab="settings".

Loads the real index.html via file:// in headless Chromium. Skipped if Playwright
/ a browser isn't available (these run when a browser is installed).
"""
import pytest
from pathlib import Path

INDEX_HTML = Path(__file__).parent.parent / "divoom_gui" / "web_ui" / "index.html"


@pytest.mark.asyncio
async def test_settings_moved_to_appbar_gear():
    pytest.importorskip("playwright.async_api")
    from playwright.async_api import async_playwright

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        try:
            page = await browser.new_page()
            await page.goto(f"file://{INDEX_HTML}")
            await page.wait_for_load_state("domcontentloaded")
            result = await page.evaluate(
                """() => {
                    const sidebarSettings = [...document.querySelectorAll('.sidebar .nav-btn[data-tab]')]
                        .some(b => b.getAttribute('data-tab') === 'settings');
                    const gear = document.querySelector('header .appbar-gear[data-tab="settings"]');
                    const sidebar = document.querySelector('.sidebar');
                    const lastChild = sidebar && sidebar.lastElementChild;
                    return {
                        sidebarSettings,
                        hasGear: !!gear,
                        lastIsDevicePanel: !!(lastChild && lastChild.id === 'connected-device-banner'),
                    };
                }"""
            )
            assert not result["sidebarSettings"], "Settings nav button should be removed from the sidebar (R32)"
            assert result["hasGear"], "appbar must have a Settings gear pill with data-tab='settings'"
            assert result["lastIsDevicePanel"], "device panel should be the bottom element of the sidebar"
        finally:
            await browser.close()


@pytest.mark.asyncio
async def test_transport_tooltip_opens_upward():
    pytest.importorskip("playwright.async_api")
    from playwright.async_api import async_playwright

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        try:
            page = await browser.new_page(viewport={"width": 1100, "height": 720})
            await page.goto(f"file://{INDEX_HTML}")
            await page.wait_for_load_state("domcontentloaded")
            await page.hover("#tr-ble-dot")
            # Under :hover the ::after tooltip exists; it must anchor via `bottom`
            # (opens upward), not `top` (which pushed it off the bottom edge).
            style = await page.evaluate(
                """() => {
                    const el = document.querySelector('#tr-ble-dot');
                    const cs = getComputedStyle(el, '::after');
                    return { content: cs.content, top: cs.top, bottom: cs.bottom };
                }"""
            )
            # Tooltip content is present (has a title to show)...
            assert style["content"] not in ("none", "normal", ""), style
            # ...and it renders ABOVE the dot: anchored via `bottom`, the browser
            # resolves the tooltip's `top` to a negative offset (its top edge sits
            # above the dot's box). A positive/zero top would mean it opened
            # downward — off the window's bottom edge, the original bug.
            top_px = float(style["top"].rstrip("px"))
            assert top_px < 0, f"tooltip should open upward (negative top), got {style}"
        finally:
            await browser.close()
