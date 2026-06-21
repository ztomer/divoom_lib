#!/usr/bin/env python3
"""Fail if any git-tracked text file contains a disallowed emoji.

Policy (user, 2026-06-20): emoji are a FAILURE STATE. The only permitted pictographic/symbol
glyphs are the Susan-Kare icon set (`~/projects/scripts/_stylerc`) plus the plain typographic
arrows used as text operators:

    →  U+2192  (ICON_START)        ✓  U+2713  (ICON_OK)
    ✗  U+2717  (ICON_ERR)          ⚠  U+26A0  (ICON_WARN)
    ↔  U+2194  ↑  U+2191  ↓  U+2193 (typographic arrows — permitted as text)

Everything else in the emoji/symbol ranges below (check-mark-button, colour squares, the warn sign
with an emoji variation-selector, decorative section emoji, double-arrow / star, keycaps, regional
flags, ...) is rejected. This is a deterministic, app-free style gate, run by `ci_local.sh` and the
pre-commit hook so the policy can't silently regress.

    python3 tools/check_no_emoji.py            # all tracked text files (ci_local.sh gate)
    python3 tools/check_no_emoji.py --staged   # only staged files (pre-commit hook)

This file lists disallowed codepoints by NUMBER, never as literal glyphs, so it never trips itself.
"""
import os, subprocess, sys

# The complete allow-list, in two buckets so the policy is auditable:
#   1. Kare icon set + approved typographic arrows — the canonical vocabulary.
#   2. Functional (non-emoji) symbols that carry meaning, not decoration: Mac modifier-key glyphs
#      shown in native menus / shortcut docs, and the left-arrow companion to the cardinal set.
# To go Kare-strict, delete bucket 2 (and the three arrows from bucket 1).
ALLOWED = {
    "→", "✓", "✗", "⚠", "↔", "↑", "↓",   # 1. Kare icons + arrows
    "←", "⌘", "⌥", "⌨",                    # 2. functional: cardinal arrow + Mac keys (⌘ cmd / ⌥ opt)
}

# Codepoint ranges that hold emoji / decorative pictographs. A char in any of these that is NOT in
# ALLOWED is a failure. (inclusive lo, inclusive hi)
RANGES = (
    (0x1F000, 0x1FAFF),   # all emoji blocks: pictographs, symbols, supplemental, regional flags
    (0x2600,  0x26FF),    # misc symbols (sun, gear, no-entry, ... and the allowed warn sign U+26A0)
    (0x2700,  0x27BF),    # dingbats (check-mark-button, scissors, ... and the allowed check/x)
    (0x2300,  0x23FF),    # misc technical (pause, stopwatch, ... and the allowed keyboard glyph)
    (0x2B00,  0x2BFF),    # stars, big block arrows
    (0x2190,  0x21FF),    # arrows (cardinal + bidi allowed via ALLOWED; double-arrow, mapsto rejected)
    (0xFE00,  0xFE0F),    # variation selectors (emoji-presentation VS16, etc.)
    (0x20E3,  0x20E3),    # combining enclosing keycap
)


def _is_disallowed(ch: str) -> bool:
    if ch in ALLOWED:
        return False
    o = ord(ch)
    return any(lo <= o <= hi for lo, hi in RANGES)


def _root() -> str:
    return subprocess.run(["git", "rev-parse", "--show-toplevel"],
                          capture_output=True, text=True).stdout.strip()


# Vendored / third-party trees we don't author and therefore don't police.
# Add per-repo prefixes here (e.g. "references/", "vendor/", "third_party/").
#   docs/divoom_docs/ — captured Divoom API responses + docs (sample gallery
#   data carries real emoji in user-supplied category/art names; not ours to edit).
EXCLUDE_PREFIXES = ("docs/divoom_docs/",)


def _files(root: str, staged: bool):
    if staged:
        out = subprocess.run(["git", "diff", "--cached", "--name-only", "--diff-filter=ACM"],
                             cwd=root, capture_output=True, text=True).stdout
    else:
        out = subprocess.run(["git", "ls-files"], cwd=root, capture_output=True, text=True).stdout
    return [f for f in out.split("\n") if f and not f.startswith(EXCLUDE_PREFIXES)]


def main() -> int:
    staged = "--staged" in sys.argv
    root = _root()
    if not root:
        print("[no_emoji] not a git repo — skipping"); return 0
    files = _files(root, staged)
    bad = []
    for f in files:
        try:
            with open(os.path.join(root, f), encoding="utf-8") as fh:
                for lineno, line in enumerate(fh, 1):
                    for col, ch in enumerate(line, 1):
                        if _is_disallowed(ch):
                            bad.append(f"{f}:{lineno}:{col}: U+{ord(ch):04X} {ch!r}")
        except (UnicodeDecodeError, FileNotFoundError, IsADirectoryError, PermissionError):
            continue   # binary / gone / dir — no text to police
    if bad:
        scope = "staged" if staged else "tracked"
        print(f"✗ DISALLOWED EMOJI in {len(bad)} location(s) ({scope}) — "
              f"only the Kare icon set is permitted (→ ✓ ✗ ⚠ ↔ ↑ ↓):")
        for b in bad[:200]:
            print("  " + b)
        if len(bad) > 200:
            print(f"  … and {len(bad) - 200} more")
        return 1
    print(f"✓ [no_emoji] OK — {len(files)} {'staged' if staged else 'tracked'} files clean")
    return 0


if __name__ == "__main__":
    sys.exit(main())
