#!/usr/bin/env python3
"""
R14 §6 — remove all emojis from docs and code.

This is a one-shot script. Run from the repo root:

    python3 scripts/remove_emojis.py

It walks the listed files and strips every character whose codepoint
falls in any of the standard emoji blocks (see EMOJI_RANGES). It also
drops the now-unused ``badge`` and ``color`` keys from the transport
status JSON in ``gui/gui_api.py`` (the JS side never reads them).

It writes a backup next to each file as ``<file>.noemoji.bak`` so a
bad pass is reversible. Delete the backups with:

    find . -name '*.noemoji.bak' -delete
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

EMOJI_RANGES = [
    (0x1F300, 0x1F5FF),   # symbols & pictographs
    (0x1F600, 0x1F64F),   # emoticons
    (0x1F680, 0x1F6FF),   # transport & map
    (0x1F700, 0x1F77F),   # alchemical
    (0x1F780, 0x1F7FF),   # geometric extended
    (0x1F800, 0x1F8FF),   # supplemental arrows
    (0x1F900, 0x1F9FF),   # supplemental symbols
    (0x1FA00, 0x1FA6F),   # chess
    (0x1FA70, 0x1FAFF),   # symbols extended-A
    (0x1F1E6, 0x1F1FF),   # regional indicators (flags)
    (0x2600, 0x26FF),     # misc symbols
    (0x2700, 0x27BF),     # dingbats
    (0x2300, 0x23FF),     # misc technical (clock, hourglass)
    (0x2B00, 0x2BFF),     # arrows
]


def is_emoji(ch: str) -> bool:
    cp = ord(ch)
    return any(lo <= cp <= hi for lo, hi in EMOJI_RANGES)


# Files to process. (Discovered by an earlier scan; 36 files.)
TARGET_FILES = [
    "ARCHITECTURE.md",
    "CHANGELOG.md",
    "divoom_lib/bt_spp_transport.py",
    "divoom_lib/divoom.py",
    "divoom_lib/lan_transport.py",
    "divoom_lib/models/capabilities.py",
    "divoom_lib/transport.py",
    "divoom_lib/wall.py",
    "docs/APP_IMPROVEMENT_PLAN.md",
    "docs/CODE_REVIEW.md",
    "docs/DEVICE_VALIDATION_PLAN.md",
    "docs/DIVOOM_PROTOCOL_SUMMARY.md",
    "docs/PLANNED_WORK.md",
    "docs/PLANNING_ROUND11.md",
    "docs/PLANNING_ROUND12.md",
    "docs/PLANNING_ROUND12_D_AUDIT.md",
    "docs/PLANNING_ROUND2_CONTINUATION.md",
    "docs/PLANNING_ROUND3.md",
    "docs/PLANNING_ROUND4.md",
    "docs/PLANNING_ROUND5.md",
    "docs/PLANNING_ROUND9.md",
    "docs/divoom_docs/README.md",
    "docs/next_phase_requirements.md",
    "gui/gui_api.py",
    "gui/menubar.py",
    "gui/web_ui/app.js",
    "gui/web_ui/channels.js",
    "gui/web_ui/gallery.css",
    "gui/web_ui/gallery.js",
    "gui/web_ui/index.html",
    "gui/web_ui/settings.js",
    "gui/web_ui/widgets.js",
    "scripts/install_daemon.sh",
    "scripts/validate_devices.py",
    "tests/test_push_protocol_diagnostic.py",
    "verify_encoder_live.py",
]

# Keys in gui_api.get_transport_status() that the JS side does NOT
# read, and which only exist to carry the (now-removed) emoji badge
# and its color. The 4 transport dicts in the function literal all
# match this pattern.
TRANSPORT_KEYS_TO_DROP = re.compile(
    r'[ \t]*"badge":\s*"[^"]*",\s*\n'
    r'[ \t]*"color":\s*"[^"]*",\s*\n',
    re.MULTILINE,
)


def strip_emojis(text: str) -> tuple[str, int]:
    out: list[str] = []
    removed = 0
    for ch in text:
        if is_emoji(ch):
            removed += 1
            continue
        out.append(ch)
    return "".join(out), removed


def process_file(path: Path) -> tuple[int, int]:
    """Return (emojis_removed, keys_dropped). 0/0 if nothing changed."""
    original = path.read_text(encoding="utf-8")
    stripped, n_removed = strip_emojis(original)
    n_keys = 0
    if path.name == "gui_api.py":
        new_text, n_keys = TRANSPORT_KEYS_TO_DROP.subn("", stripped)
        stripped = new_text
    if stripped == original:
        return 0, 0
    backup = path.with_suffix(path.suffix + ".noemoji.bak")
    backup.write_text(original, encoding="utf-8")
    path.write_text(stripped, encoding="utf-8")
    return n_removed, n_keys


def main() -> int:
    root = Path(".").resolve()
    total_emojis = 0
    total_keys = 0
    files_changed = 0
    for rel in TARGET_FILES:
        p = root / rel
        if not p.exists():
            print(f"  skip (missing): {rel}", file=sys.stderr)
            continue
        n_emoji, n_keys = process_file(p)
        if n_emoji or n_keys:
            files_changed += 1
            total_emojis += n_emoji
            total_keys += n_keys
            print(f"  {rel}: -{n_emoji} emoji, -{n_keys} unused JSON keys")
    print(f"\nDone. {files_changed} files changed, {total_emojis} emojis removed, "
          f"{total_keys} unused transport JSON keys dropped.")
    print("Backups: <file>.noemoji.bak  (delete with `find . -name '*.noemoji.bak' -delete`)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
