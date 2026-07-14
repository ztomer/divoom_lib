"""E2E — "Sync Now" (Routines > Auto-Sync): manually push hot-channel content
to every toggled sync target immediately, with per-device progress.

Drives the real web_ui with a mocked ``window.pywebview.api.sync_now`` and
the ``onSyncNowProgress``/``onSyncNowComplete`` events the backend fires
(see divoom_gui/gallery_hot_api.py::sync_now).
"""
import pytest
from pathlib import Path

INDEX_HTML = Path(__file__).parent.parent / "divoom_gui" / "web_ui" / "index.html"

_MOCK_API = """
window.__syncNowCalls = 0;
window.__api = {
    sync_now: () => { window.__syncNowCalls++; return true; },
};
window.pywebview = { api: new Proxy({}, { get: (_t, name) => (...args) => {
    if (window.__api && typeof window.__api[name] === 'function')
        return Promise.resolve(window.__api[name](...args));
    return Promise.resolve(String(name).startsWith('get_') ? '{}' : true);
}})};
"""


async def _open_auto_sync_tab(p):
    browser = await p.chromium.launch(headless=True)
    page = await browser.new_page()
    await page.add_init_script(_MOCK_API)
    await page.goto(f"file://{INDEX_HTML}")
    await page.wait_for_load_state("domcontentloaded")
    await page.wait_for_function("() => !!window.DivoomState && !!window.renderSyncTargets")
    await page.click('.nav-btn[data-tab="routines"]')
    await page.wait_for_selector("#routines-schedule.active")
    await page.evaluate("""() => {
        window.renderSyncTargets([
            {address: "AA:BB", name: "Pixoo", selected: true},
            {address: "CC:DD", name: "Timoo", selected: true},
        ]);
    }""")
    return browser, page


@pytest.mark.asyncio
async def test_sync_now_button_calls_backend_and_disables_while_running():
    pytest.importorskip("playwright.async_api")
    from playwright.async_api import async_playwright

    async with async_playwright() as p:
        browser, page = await _open_auto_sync_tab(p)
        try:
            await page.click("#sync-now-btn")
            calls = await page.evaluate("() => window.__syncNowCalls")
            assert calls == 1
            await page.wait_for_function(
                "() => document.getElementById('sync-now-btn').disabled === true")
        finally:
            await browser.close()


@pytest.mark.asyncio
async def test_sync_now_progress_updates_the_right_device_row():
    pytest.importorskip("playwright.async_api")
    from playwright.async_api import async_playwright

    async with async_playwright() as p:
        browser, page = await _open_auto_sync_tab(p)
        try:
            await page.click("#sync-now-btn")

            await page.evaluate("""() => {
                window.onSyncNowProgress({address: "AA:BB", phase: "connecting"});
                window.onSyncNowProgress({address: "CC:DD", phase: "error", error: "unreachable"});
            }""")

            row_aa = await page.text_content('.sync-now-row-status[data-addr="AA:BB"]')
            row_cc = await page.text_content('.sync-now-row-status[data-addr="CC:DD"]')
            assert "Connecting" in row_aa
            assert "unreachable" in row_cc

            await page.evaluate("""() => {
                window.onSyncNowProgress({address: "AA:BB", phase: "done", served: 3});
                window.onSyncNowComplete({total: 2, ok: 1, failed: 1});
            }""")

            row_aa_done = await page.text_content('.sync-now-row-status[data-addr="AA:BB"]')
            assert "3" in row_aa_done

            await page.wait_for_function(
                "() => document.getElementById('sync-now-btn').disabled === false")
            status = await page.text_content("#sync-now-status")
            assert "1/2" in status
        finally:
            await browser.close()
