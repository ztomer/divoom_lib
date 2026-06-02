"""Shared persistence for the Monthly Best "hot channel" feature.

Both the desktop GUI and the headless daemon read/write this single config so
that the user's selected target devices and schedule survive across sessions and
drive automatic, headless syncs (request items 4.c / 4.d).

Stored at ``~/.config/divoom-control/hotchannel.json``:

    {
      "enabled": false,        # whether the scheduled daemon should run
      "interval": 3600,        # seconds between automatic sync cycles
      "classify": 18,          # Divoom gallery classification id (18 = Recommend)
      "targets": ["AA:BB:CC:DD:EE:FF", "LAN:192.168.1.50"]  # device addresses
    }
"""

from __future__ import annotations

import json
import os
from pathlib import Path

CONFIG_DIR = Path.home() / ".config" / "divoom-control"
CONFIG_PATH = CONFIG_DIR / "hotchannel.json"

DEFAULTS = {
    "enabled": False,
    "interval": 3600,
    "classify": 18,
    "targets": [],
}

# Guardrails.
MIN_INTERVAL = 60  # never hammer the cloud/device faster than once a minute


def _config_path() -> Path:
    # Honor an override (used by tests) without importing test code.
    override = os.environ.get("DIVOOM_HOTCHANNEL_CONFIG")
    return Path(override) if override else CONFIG_PATH


def load_config() -> dict:
    """Return the stored config merged over defaults (never raises)."""
    cfg = dict(DEFAULTS)
    path = _config_path()
    if path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                cfg.update({k: data[k] for k in DEFAULTS if k in data})
        except (OSError, ValueError):
            pass
    return _normalize(cfg)


def save_config(cfg: dict) -> bool:
    """Persist a (partial) config, merged over the current stored values."""
    merged = load_config()
    for k in DEFAULTS:
        if k in cfg:
            merged[k] = cfg[k]
    merged = _normalize(merged)
    try:
        path = _config_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(merged, indent=2), encoding="utf-8")
        return True
    except OSError:
        return False


def set_targets(targets: list[str]) -> bool:
    return save_config({"targets": targets})


def get_targets() -> list[str]:
    return load_config()["targets"]


def _normalize(cfg: dict) -> dict:
    """Coerce/validate fields so callers and the daemon get safe values."""
    out = dict(DEFAULTS)
    out.update(cfg)
    out["enabled"] = bool(out.get("enabled", False))
    try:
        out["interval"] = max(MIN_INTERVAL, int(out.get("interval", 3600)))
    except (TypeError, ValueError):
        out["interval"] = DEFAULTS["interval"]
    try:
        out["classify"] = int(out.get("classify", 18))
    except (TypeError, ValueError):
        out["classify"] = DEFAULTS["classify"]
    targets = out.get("targets") or []
    if not isinstance(targets, list):
        targets = []
    # De-dupe, drop blanks, preserve order.
    seen, clean = set(), []
    for t in targets:
        t = str(t).strip()
        if t and t not in seen:
            seen.add(t)
            clean.append(t)
    out["targets"] = clean
    return out
