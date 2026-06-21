"""tui/lib.py — Kare TUI output primitives (vendored from ~/projects/scripts/_lib.py).

Import from a repo script (add the repo root or tui/ to sys.path first):
    from tui.lib import info, ok, err, warn, die, hr, section

Self-contained: reads tui/stylerc (repo source of truth), no machine dependency.
Icons: → · ✓ ✗ ⚠   Colors: restrained, NO_COLOR + non-tty aware (degrades to plain text).
"""
import os
import sys

_STYLERC_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "stylerc")

_DEFAULTS = {"ICON_START": "→", "ICON_STEP": "·", "ICON_OK": "✓", "ICON_ERR": "✗", "ICON_WARN": "⚠"}


def _parse_stylerc(path: str) -> dict:
    """Parse key="value" lines from the stylerc, converting \\033 -> ESC."""
    cfg = {}
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, _, val = line.partition("=")
                cfg[key.strip()] = val.strip().strip("\"'").replace(r"\033", "\033")
    except OSError:
        pass
    return cfg


_CFG = _parse_stylerc(_STYLERC_PATH)

ICON_START = _CFG.get("ICON_START", _DEFAULTS["ICON_START"])
ICON_STEP = _CFG.get("ICON_STEP", _DEFAULTS["ICON_STEP"])
ICON_OK = _CFG.get("ICON_OK", _DEFAULTS["ICON_OK"])
ICON_ERR = _CFG.get("ICON_ERR", _DEFAULTS["ICON_ERR"])
ICON_WARN = _CFG.get("ICON_WARN", _DEFAULTS["ICON_WARN"])

if sys.stdout.isatty() and os.environ.get("NO_COLOR") != "1":
    _C_RESET = _CFG.get("C_RESET", "\033[0m")
    _C_DIM = _CFG.get("C_DIM", "\033[2m")
    _C_BOLD = _CFG.get("C_BOLD", "\033[1m")
    _C_GREEN = _CFG.get("C_GREEN", "\033[0;32m")
    _C_RED = _CFG.get("C_RED", "\033[0;31m")
    _C_YELLOW = _CFG.get("C_YELLOW", "\033[0;33m")
    _C_GRAY = _CFG.get("C_GRAY", "\033[0;90m")
else:
    _C_RESET = _C_DIM = _C_BOLD = _C_GREEN = _C_RED = _C_YELLOW = _C_GRAY = ""


def info(message: str) -> None:
    print(f"{_C_GRAY}{ICON_START}{_C_RESET} {_C_DIM}{message}{_C_RESET}")


def ok(message: str) -> None:
    print(f"{_C_GREEN}{ICON_OK}{_C_RESET} {message}")


def err(message: str) -> None:
    print(f"{_C_RED}{ICON_ERR}{_C_RESET} {message}", file=sys.stderr)


def warn(message: str) -> None:
    print(f"{_C_YELLOW}{ICON_WARN}{_C_RESET} {message}")


def die(message: str, code: int = 1) -> None:
    err(message)
    sys.exit(code)


def hr(width: int = 72) -> None:
    print(f"{_C_GRAY}{'─' * width}{_C_RESET}")


def section(title: str) -> None:
    print()
    hr()
    print(f"{_C_BOLD}  {title}{_C_RESET}")
    hr()
