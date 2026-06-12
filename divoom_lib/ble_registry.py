"""Process-wide BLE connection registry — one live connection per address.

CoreBluetooth (and BlueZ) allow only ONE connection to a peripheral per central.
A ``Divoom`` used standalone and the SAME MAC used as a ``DivoomWall`` slot each
build their own ``BleakClient``; without coordination the second connect to that
address just times out (HW-reproduced: push a wall, then connect a wall member →
16s timeout). This registry makes ``connect()`` evict any prior in-process
connection to the address first, so switching single↔wall — or any caller that
reuses a MAC — never double-connects it. Enforcing the invariant here (the
library) rather than in the daemon means every caller benefits: the wall
self-heal, live jobs, and reconnect paths included.

The registry stores the owning transport (anything with ``mac`` + an async
``disconnect()``). It is loop-agnostic bookkeeping; eviction awaits the old
owner's ``disconnect()`` (in this app every BLE op runs on the daemon's single
device loop, so that await is in-loop).
"""
from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger("divoom_lib.ble_registry")

_active: dict[str, Any] = {}   # normalized address -> owning transport


def _norm(address: Any) -> str | None:
    return str(address).upper() if address else None


async def evict(address: Any, keep: Any) -> None:
    """Disconnect + drop any registered connection to ``address`` other than
    ``keep`` (the transport about to take it over). Best-effort."""
    key = _norm(address)
    if not key:
        return
    existing = _active.get(key)
    if existing is None or existing is keep:
        return
    logger.info("BLE registry: evicting prior connection to %s before reconnect", key)
    try:
        await existing.disconnect()
    except Exception as e:
        logger.debug("registry evict disconnect failed for %s: %s", key, e)
    if _active.get(key) is existing:
        _active.pop(key, None)


def register(address: Any, transport: Any) -> None:
    key = _norm(address)
    if key:
        _active[key] = transport


def unregister(address: Any, transport: Any) -> None:
    key = _norm(address)
    if key and _active.get(key) is transport:
        _active.pop(key, None)


def owner(address: Any) -> Any:
    """The transport currently registered for ``address`` (or None). For tests."""
    return _active.get(_norm(address))


def _reset() -> None:
    """Clear the registry — test hook only."""
    _active.clear()
