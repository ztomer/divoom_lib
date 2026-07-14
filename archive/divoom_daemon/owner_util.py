"""Small shared helpers for the daemon owner mixins (kept separate so both
device_owner.py and owner_connect.py can use them without a circular import)."""
from __future__ import annotations


def _json_safe(value):
    """Coerce a value to something JSON-serializable."""
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, (list, tuple)):
        return [_json_safe(v) for v in value]
    if isinstance(value, dict):
        return {str(k): _json_safe(v) for k, v in value.items()}
    if isinstance(value, (bytes, bytearray)):
        return list(value)
    return str(value)
