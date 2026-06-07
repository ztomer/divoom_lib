"""GUI → daemon bridge (R17 P5).

The BLE device can be held by only one process, so the **daemon is the sole
device owner** and the GUI is a thin RPC client. This module gives the GUI:

  * ``ensure_daemon()`` — make sure a daemon is running (auto-spawn one if not),
    returning a connected :class:`DaemonClient`. Idempotent + safe to call on
    every GUI device action.
  * ``DaemonDeviceProxy`` — a stand-in for a ``Divoom`` whose attribute access
    builds a dotted method path and whose calls issue a ``device_call`` RPC, so
    existing call-sites like ``target.display.show_light(color, b)`` work
    unchanged once ``target`` is a proxy. Calls return awaitables, so the GUI's
    ``_run_async(...)`` scheduling still applies.

Nothing here imports BLE or pywebview — it's pure client plumbing and unit-tested
against a fake daemon in ``tests/test_daemon_bridge.py``.
"""
from __future__ import annotations

import logging
import os
import subprocess
import sys
import time
from typing import Any

from divoom_daemon.daemon_protocol import DEFAULT_SOCKET_PATH, DaemonClient

logger = logging.getLogger("divoom_gui")


def daemon_alive(socket_path: str = DEFAULT_SOCKET_PATH, timeout: float = 0.5) -> bool:
    """True if a daemon answers ``device_status`` on ``socket_path``."""
    reply = DaemonClient(socket_path, timeout=timeout).send_command("device_status")
    return bool(reply.get("success", False)) or ("connected" in reply)


def spawn_daemon(
    socket_path: str = DEFAULT_SOCKET_PATH,
    *,
    mac: str | None = None,
    python: str | None = None,
) -> subprocess.Popen:
    """Launch a detached daemon process (``python -m divoom_lib.cli daemon``).

    Detached so it outlives the GUI process; stdout/stderr inherited so its logs
    surface where the GUI was launched. Caller is responsible for waiting until
    the socket is live (see :func:`ensure_daemon`).
    """
    cmd = [python or sys.executable, "-m", "divoom_lib.cli", "daemon",
           "--socket", socket_path]
    if mac:
        cmd += ["--mac", mac]
    logger.info("Spawning daemon: %s", " ".join(cmd))
    return subprocess.Popen(
        cmd,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        stdin=subprocess.DEVNULL,
        start_new_session=True,  # detach from the GUI's process group
        env=os.environ.copy(),
    )


def ensure_daemon(
    socket_path: str = DEFAULT_SOCKET_PATH,
    *,
    mac: str | None = None,
    spawn: bool = True,
    wait_timeout: float = 8.0,
) -> DaemonClient | None:
    """Return a :class:`DaemonClient` for a *live* daemon, auto-spawning one if
    needed. Returns ``None`` if no daemon could be reached/started.

    Idempotent: if a daemon is already up, returns immediately without spawning.
    """
    if daemon_alive(socket_path):
        return DaemonClient(socket_path)
    if not spawn:
        return None
    spawn_daemon(socket_path, mac=mac)
    deadline = time.monotonic() + wait_timeout
    while time.monotonic() < deadline:
        if daemon_alive(socket_path):
            return DaemonClient(socket_path)
        time.sleep(0.1)
    logger.error("Daemon did not become ready within %.1fs", wait_timeout)
    return None


class _DeviceCallError(RuntimeError):
    """Raised inside the proxy awaitable when the daemon reports failure."""


class DaemonDeviceProxy:
    """Attribute/method stand-in for a ``Divoom`` that routes through a daemon.

    ``proxy.display.show_light(color, b)`` records the dotted path
    ``"display.show_light"`` and returns an awaitable that, when run, issues a
    ``device_call`` RPC and returns the daemon's ``result`` (raising on failure).
    Arbitrary nesting works: ``proxy.lan.set_brightness(v)`` →
    ``"lan.set_brightness"``.
    """

    def __init__(self, client: DaemonClient, _path: str = "") -> None:
        object.__setattr__(self, "_client", client)
        object.__setattr__(self, "_path", _path)

    def __getattr__(self, name: str) -> "DaemonDeviceProxy":
        if name.startswith("_"):
            raise AttributeError(name)
        path = f"{self._path}.{name}" if self._path else name
        return DaemonDeviceProxy(self._client, path)

    def __call__(self, *args: Any, **kwargs: Any):
        method = self._path
        client = self._client

        async def _invoke():
            reply = client.device_call(method, list(args), dict(kwargs))
            if not reply.get("success", False):
                raise _DeviceCallError(reply.get("error", f"device_call {method} failed"))
            return reply.get("result")

        return _invoke()
