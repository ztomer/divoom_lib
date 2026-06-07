"""
R15 §1+§7 — tests for the unified tab chrome (tabs.css).

These tests guard the design contract: the segmented-pill shape is
defined in exactly one place (tabs.css) and is shared across
Channels, Tools, Settings, and Theme. Legacy class names in
settings.css are aliases — the new `.tab-btn` / `.tabs-row` is the
source of truth.
"""
from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
TABS_CSS = REPO_ROOT / "divoom_gui" / "web_ui" / "tabs.css"
SETTINGS_CSS = REPO_ROOT / "divoom_gui" / "web_ui" / "settings.css"
CHANNELS_CSS = REPO_ROOT / "divoom_gui" / "web_ui" / "channels.css"
INDEX_HTML = REPO_ROOT / "divoom_gui" / "web_ui" / "index.html"
TEMPLATES_JS = REPO_ROOT / "divoom_gui" / "web_ui" / "templates.js"


# ── tabs.css basics ───────────────────────────────────────────────────


def test_tabs_css_exists() -> None:
    assert TABS_CSS.exists()


def test_tabs_css_uses_design_tokens() -> None:
    """tabs.css must reference the design tokens from style.css."""
    src = TABS_CSS.read_text()
    assert "--font-sans" in src, "tabs.css should use --font-sans"
    assert "--primary" in src, "tabs.css should use --primary for active state"
    assert "--text-muted" in src, "tabs.css should use --text-muted for inactive"


def test_tabs_css_defines_tabs_row() -> None:
    src = TABS_CSS.read_text()
    assert re.search(r"\.tabs-row\s*\{[^}]*display:\s*flex", src, re.DOTALL)


def test_tabs_css_defines_tab_btn() -> None:
    src = TABS_CSS.read_text()
    assert re.search(
        r"\.tabs-row\s+\.tab-btn\s*\{",
        src,
    ), "tabs.css is missing the .tabs-row .tab-btn rule"


def test_tabs_css_defines_active_state() -> None:
    """The active state is the most important contract: --primary bg + white text."""
    src = TABS_CSS.read_text()
    m = re.search(
        r"\.tabs-row\s+\.tab-btn\.active\s*\{([^}]+)\}",
        src,
        re.DOTALL,
    )
    assert m, "tabs.css is missing .tabs-row .tab-btn.active"
    body = m.group(1)
    assert "var(--primary)" in body, "active state must use --primary"
    assert "#ffffff" in body or "white" in body, "active text must be white"


def test_tabs_css_icon_slot() -> None:
    src = TABS_CSS.read_text()
    assert re.search(
        r"\.tabs-row\s+\.tab-icon\s*\{",
        src,
    ), "tabs.css is missing the .tab-icon prefix slot"


# ── legacy aliases in settings.css ────────────────────────────────────


def test_settings_css_keeps_legacy_aliases() -> None:
    """Older markup (theme buttons, etc.) still references the legacy
    class names — settings.css must alias them so they still render."""
    src = SETTINGS_CSS.read_text()
    # The three legacy classes appear in a single shared rule.
    assert re.search(
        r"\.settings-tab-btn\s*,\s*\n\s*\.tools-subtab-btn\s*,\s*\n\s*\.theme-mode-btn\s*\{",
        src,
    ), "settings.css should group legacy class names in a single shared rule"


def test_settings_css_does_not_duplicate_chrome() -> None:
    """The active-state rule must appear once (in tabs.css), not be
    duplicated in settings.css. The alias in settings.css should
    provide a fallback only for markup that hasn't been migrated yet."""
    src = SETTINGS_CSS.read_text()
    # The single .active rule in settings.css uses --primary + #ffffff.
    matches = re.findall(
        r"\.settings-tab-btn\.active\s*,\s*\n\s*\.tools-subtab-btn\.active\s*,\s*\n\s*\.theme-mode-btn\.active\s*\{[^}]+\}",
        src,
        re.DOTALL,
    )
    assert len(matches) == 1, (
        f"settings.css has {len(matches)} legacy-active rules; expected 1"
    )


def test_channels_css_dropped_chrome() -> None:
    """channels.css no longer defines the .channel-card chrome."""
    src = CHANNELS_CSS.read_text()
    # The old vertical-card chrome rule was removed in R15 §1.
    assert "background: rgba(255, 255, 255, 0.02)" not in src, (
        "channels.css still has the old .channel-card chrome background — "
        "should be removed; the chrome now lives in tabs.css."
    )


# ── markup uses the new classes ───────────────────────────────────────


def test_channel_row_uses_tabs_row() -> None:
    html = INDEX_HTML.read_text()
    assert re.search(
        r'<div class="tabs-row"[^>]*role="tablist"',
        html,
    ), "index.html channel row is missing the new .tabs-row wrapper"


def test_settings_subtabs_use_tabs_row() -> None:
    src = TEMPLATES_JS.read_text()
    assert re.search(
        r'<div class="tabs-row"[^>]*aria-label="Settings"',
        src,
    ), "templates.js Settings sub-tab row is missing the new .tabs-row wrapper"


def test_tools_subtabs_use_tabs_row() -> None:
    src = TEMPLATES_JS.read_text()
    assert re.search(
        r'<div class="tabs-row"[^>]*aria-label="Tools"',
        src,
    ), "templates.js Tools sub-tab row is missing the new .tabs-row wrapper"


def test_theme_buttons_use_tabs_row() -> None:
    src = TEMPLATES_JS.read_text()
    assert re.search(
        r'<div class="tabs-row theme-buttons"',
        src,
    ), "templates.js theme-mode row is missing .tabs-row"


def test_no_legacy_channel_card_in_index_html() -> None:
    """After R15 §1, the channel row uses .tab-btn, not .channel-card."""
    html = INDEX_HTML.read_text()
    # The new class is on all 7 channel buttons.
    assert html.count('class="tab-btn') >= 7
    # The old class should be gone from the channel row (it may still
    # appear in a comment, but not as an element class).
    assert 'class="channel-card' not in html, (
        "index.html still has a .channel-card element — should be .tab-btn"
    )


def test_no_legacy_settings_tab_btn_in_templates() -> None:
    """The Settings row uses .tab-btn, not .settings-tab-btn."""
    src = TEMPLATES_JS.read_text()
    # Active state class is the same .tab-btn, so look for the data attr.
    assert re.search(
        r'<button class="tab-btn active"\s+data-settings-tab="settings-devices"',
        src,
    ), "Settings Devices tab is not using .tab-btn"


# ── index.html links tabs.css ─────────────────────────────────────────


def test_index_html_links_tabs_css() -> None:
    html = INDEX_HTML.read_text()
    assert 'href="tabs.css"' in html, (
        "index.html is missing the <link rel='stylesheet' href='tabs.css'>"
    )
    # tabs.css must come after style.css (so it can override the design tokens).
    style_pos = html.find('href="style.css"')
    tabs_pos = html.find('href="tabs.css"')
    assert tabs_pos > style_pos, (
        "tabs.css must be linked AFTER style.css so its rules win over the base"
    )
