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

from divoom_daemon.daemon_protocol import (
    DEFAULT_SOCKET_PATH,
    ENV_HOST,
    DaemonClient,
)

logger = logging.getLogger("divoom_gui")


def _client_alive(client: DaemonClient) -> bool:
    reply = client.send_command("device_status")
    return bool(reply.get("success", False)) or ("connected" in reply)


def daemon_alive(socket_path: str = DEFAULT_SOCKET_PATH, timeout: float = 0.5) -> bool:
    """True if a daemon answers ``device_status`` on ``socket_path``."""
    return _client_alive(DaemonClient(socket_path, timeout=timeout))


def _spawn_disclaimed_macos(cmd: list[str], log_path: str) -> int:
    """Spawn ``cmd`` with macOS TCC responsibility DISCLAIMED, returning the pid.

    This is the crux of making BLE work from the GUI without user intervention.
    A normal child inherits the parent's "responsible process" for TCC — for the
    GUI that's pywebview's `Python.app` (which has no Bluetooth grant), so every
    scan comes back empty/denied. Disclaiming makes the daemon its OWN responsible
    process, attributed to the python binary itself — which the user has already
    granted Bluetooth (it shows as `python3.14` in Privacy > Bluetooth). Verified:
    `CBCentralManager.authorization()` == 3 (allowed) and scans find devices,
    regardless of whether the parent is the GUI, a terminal, or Finder.

    Uses posix_spawn (libc) with `responsibility_spawnattrs_setdisclaim` +
    POSIX_SPAWN_SETSID, redirecting stdout/stderr to ``log_path``.
    """
    import ctypes
    import ctypes.util

    libc = ctypes.CDLL(ctypes.util.find_library("c"), use_errno=True)
    attr_t = ctypes.c_void_p   # posix_spawnattr_t (opaque pointer on macOS)
    fa_t = ctypes.c_void_p     # posix_spawn_file_actions_t
    libc.posix_spawnattr_init.argtypes = [ctypes.POINTER(attr_t)]
    libc.posix_spawnattr_setflags.argtypes = [ctypes.POINTER(attr_t), ctypes.c_short]
    libc.posix_spawnattr_destroy.argtypes = [ctypes.POINTER(attr_t)]
    libc.responsibility_spawnattrs_setdisclaim.argtypes = [ctypes.POINTER(attr_t), ctypes.c_int]
    libc.posix_spawn_file_actions_init.argtypes = [ctypes.POINTER(fa_t)]
    libc.posix_spawn_file_actions_destroy.argtypes = [ctypes.POINTER(fa_t)]
    libc.posix_spawn_file_actions_addopen.argtypes = [
        ctypes.POINTER(fa_t), ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_uint]
    libc.posix_spawn_file_actions_adddup2.argtypes = [ctypes.POINTER(fa_t), ctypes.c_int, ctypes.c_int]
    libc.posix_spawn.argtypes = [
        ctypes.POINTER(ctypes.c_int), ctypes.c_char_p,
        ctypes.POINTER(fa_t), ctypes.POINTER(attr_t),
        ctypes.POINTER(ctypes.c_char_p), ctypes.POINTER(ctypes.c_char_p)]

    POSIX_SPAWN_SETSID = 0x0400
    attr = attr_t()
    if libc.posix_spawnattr_init(ctypes.byref(attr)) != 0:
        raise OSError("posix_spawnattr_init failed")
    try:
        libc.posix_spawnattr_setflags(ctypes.byref(attr), POSIX_SPAWN_SETSID)
        if libc.responsibility_spawnattrs_setdisclaim(ctypes.byref(attr), 1) != 0:
            raise OSError("responsibility_spawnattrs_setdisclaim failed")

        fa = fa_t()
        libc.posix_spawn_file_actions_init(ctypes.byref(fa))
        try:
            libc.posix_spawn_file_actions_addopen(ctypes.byref(fa), 0, b"/dev/null", os.O_RDONLY, 0)
            libc.posix_spawn_file_actions_addopen(
                ctypes.byref(fa), 1, log_path.encode(),
                os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o644)
            libc.posix_spawn_file_actions_adddup2(ctypes.byref(fa), 1, 2)

            argv = (ctypes.c_char_p * (len(cmd) + 1))(*[a.encode() for a in cmd], None)
            env = [f"{k}={v}" for k, v in os.environ.items()]
            envp = (ctypes.c_char_p * (len(env) + 1))(*[e.encode() for e in env], None)
            pid = ctypes.c_int()
            rc = libc.posix_spawn(ctypes.byref(pid), cmd[0].encode(),
                                  ctypes.byref(fa), ctypes.byref(attr), argv, envp)
            if rc != 0:
                raise OSError(f"posix_spawn failed rc={rc}")
            return pid.value
        finally:
            libc.posix_spawn_file_actions_destroy(ctypes.byref(fa))
    finally:
        libc.posix_spawnattr_destroy(ctypes.byref(attr))


def spawn_daemon(
    socket_path: str = DEFAULT_SOCKET_PATH,
    *,
    mac: str | None = None,
    python: str | None = None,
    detach: bool = False,
):
    """Launch the daemon process (``python -m divoom_lib.cli daemon``).

    On macOS, spawn it with TCC responsibility DISCLAIMED so it's attributed to
    the granted python binary (not the GUI's ungranted Python.app) — this is what
    makes BLE work from the GUI with no user intervention (see
    :func:`_spawn_disclaimed_macos`). Falls back to ``subprocess.Popen`` on other
    platforms or if the disclaim spawn is unavailable.

    Caller waits until the socket is live (see :func:`ensure_daemon`).
    """
    cmd = [python or sys.executable, "-m", "divoom_lib.cli", "daemon",
           "--socket", socket_path]
    if mac:
        cmd += ["--mac", mac]
    log_path = os.environ.get("DIVOOM_DAEMON_LOG", "/tmp/divoom_daemon.log")
    try:
        with open(log_path, "a", buffering=1) as fh:
            fh.write(f"\n==== daemon spawn from pid {os.getpid()} ====\n")
    except OSError:
        pass

    if sys.platform == "darwin":
        try:
            pid = _spawn_disclaimed_macos(cmd, log_path)
            logger.info("Spawned daemon (TCC-disclaimed, granted python identity) pid=%s", pid)
            return pid
        except Exception as e:
            logger.warning("Disclaimed spawn failed (%s); falling back to Popen.", e)

    try:
        log_fh = open(log_path, "a", buffering=1)
        _out = _err = log_fh
    except OSError:
        _out = _err = subprocess.DEVNULL
    logger.info("Spawning daemon (Popen, detach=%s): %s", detach, " ".join(cmd))
    return subprocess.Popen(
        cmd, stdout=_out, stderr=_err, stdin=subprocess.DEVNULL,
        start_new_session=detach, env=os.environ.copy(),
    )


def ensure_daemon(
    socket_path: str = DEFAULT_SOCKET_PATH,
    *,
    mac: str | None = None,
    spawn: bool = True,
    wait_timeout: float = 8.0,
    detach: bool = False,
) -> DaemonClient | None:
    """Return a :class:`DaemonClient` for a *live* daemon, auto-spawning one if
    needed. Returns ``None`` if no daemon could be reached/started.

    If ``DIVOOM_DAEMON_HOST`` is set, target that *remote* daemon over TCP and
    never spawn (it's on another host). Otherwise use the local Unix socket and
    auto-spawn. Idempotent: a live daemon returns immediately.
    """
    if os.environ.get(ENV_HOST):
        remote = DaemonClient.from_env(socket_path)
        if _client_alive(remote):
            return remote
        logger.error("Remote daemon at %s:%s not reachable", remote.host, remote.port)
        return None
    if daemon_alive(socket_path):
        return DaemonClient(socket_path)
    if not spawn:
        return None
    spawn_daemon(socket_path, mac=mac, detach=detach)
    deadline = time.monotonic() + wait_timeout
    while time.monotonic() < deadline:
        if daemon_alive(socket_path):
            return DaemonClient(socket_path)
        time.sleep(0.1)
    logger.error("Daemon did not become ready within %.1fs", wait_timeout)
    return None


class _DeviceCallError(RuntimeError):
    """Raised inside the proxy awaitable when the daemon reports failure."""


class _LanView:
    """Minimal stand-in for ``divoom.lan`` so introspection reads still work."""
    def __init__(self, device_ip: str | None):
        self.device_ip = device_ip

    def __bool__(self):
        return bool(self.device_ip)


class _ConnView:
    """Minimal stand-in for ``divoom._conn`` (only ``.mac`` is read by the GUI)."""
    def __init__(self, mac: str | None):
        self.mac = mac


# Root-only synthetic attributes answered from `device_status` rather than a
# dotted method call.
_STATUS_ATTRS = ("is_connected", "lan", "_conn")


class DaemonDeviceProxy:
    """Attribute/method stand-in for a ``Divoom`` (or ``DivoomWall``) that routes
    through a daemon.

    ``proxy.display.show_light(color, b)`` records the dotted path
    ``"display.show_light"`` and returns an awaitable that, when run, issues a
    ``device_call`` RPC and returns the daemon's ``result`` (raising on failure).
    Arbitrary nesting works: ``proxy.lan.set_brightness(v)`` →
    ``"lan.set_brightness"``.

    ``target`` is "device" (the single owned Divoom) or "wall" (the daemon-owned
    DivoomWall). Root-level introspection reads (``is_connected``/``lan``/
    ``_conn``) are answered synchronously from ``device_status``.
    """

    def __init__(self, client: DaemonClient, _path: str = "", *, target: str = "device") -> None:
        object.__setattr__(self, "_client", client)
        object.__setattr__(self, "_path", _path)
        object.__setattr__(self, "_target", target)

    def _status(self) -> dict:
        return self._client.device_status()

    def __getattr__(self, name: str) -> Any:
        # Root-level synthetic introspection reads (device only).
        if name in _STATUS_ATTRS and self._path == "":
            st = self._status()
            if name == "is_connected":
                key = "wall" if self._target == "wall" else "connected"
                return bool(st.get(key, False))
            if name == "lan":
                return _LanView(st.get("lan_ip"))
            if name == "_conn":
                return _ConnView(st.get("mac"))
        if name.startswith("_"):
            raise AttributeError(name)
        path = f"{self._path}.{name}" if self._path else name
        return DaemonDeviceProxy(self._client, path, target=self._target)

    def __call__(self, *args: Any, **kwargs: Any):
        method = self._path
        client = self._client
        target = self._target
        call_args = list(args)

        # Remote daemon (TCP): no shared filesystem, so any positional arg that
        # is a local file path must be shipped as a blob (the daemon writes it to
        # a temp file and substitutes the path back in). Local Unix clients pass
        # the path directly — the daemon reads the same disk.
        blobs: dict[int, bytes] | None = None
        if getattr(client, "is_remote", False):
            for i, a in enumerate(call_args):
                try:
                    if isinstance(a, str) and os.path.isfile(a):
                        with open(a, "rb") as f:
                            blobs = blobs or {}
                            blobs[i] = f.read()
                except OSError:
                    pass

        async def _invoke():
            reply = client.device_call(method, call_args, dict(kwargs),
                                       target=target, blobs=blobs)
            if not reply.get("success", False):
                raise _DeviceCallError(reply.get("error", f"device_call {method} failed"))
            return reply.get("result")

        return _invoke()
