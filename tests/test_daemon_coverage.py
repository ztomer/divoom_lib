"""R61 coverage push: divoom_daemon.daemon branches not exercised by
test_daemon_server.py (a real DivoomDaemon over a temp socket, driving command
dispatch/status/notifications) or test_adversarial_round35.py (the
single-instance flock happy/reject pair).

Gaps closed:
  * ``_cmd_shutdown``'s two swallowed-exception branches — a broadcast() that
    raises, and the background thread's delayed ``self.stop()`` that raises —
    neither may propagate or crash the daemon.
  * ``_acquire_instance_lock``'s falsy-socket_path short-circuit and its
    "flock unsupported on this filesystem" branch (a non-OSError from
    ``fcntl.flock``, distinct from the already-tested OSError-loses-the-race
    case).
  * ``run()`` — the module-level entry point — essentially untested before:
    the lost-instance-lock early return, the happy path (notifier start,
    rehydrate, SIGTERM registration, serve_forever -> KeyboardInterrupt ->
    stop(), return 0), a rehydrate failure that's logged but not fatal, and a
    SIGTERM-registration failure (``signal.signal`` raising ValueError, e.g.
    not on the main thread) that must not prevent the daemon from serving.

``DivoomDaemon`` itself is constructed for real (no monitor/serve_forever
needed for the shutdown/lock tests — SocketServer doesn't bind until
serve_forever runs); ``run()`` is driven against a fully fake ``DivoomDaemon``
class (monkeypatched in) so no socket/BLE/notification machinery starts.
"""
import threading
import time
from unittest.mock import MagicMock

import pytest

import divoom_daemon.daemon as daemon_mod
from divoom_daemon.daemon import DivoomDaemon


def _make_daemon(**kwargs):
    kwargs.setdefault("socket_path", "/tmp/divoom_cov_daemon_unused.sock")
    return DivoomDaemon(**kwargs)


# ── _cmd_shutdown: both swallowed-exception branches ──────────────────────


def test_cmd_shutdown_swallows_broadcast_exception(monkeypatch):
    d = _make_daemon()
    monkeypatch.setattr(d, "broadcast", MagicMock(side_effect=RuntimeError("broadcast boom")))
    monkeypatch.setattr(d, "stop", MagicMock())  # avoid touching real socket/notifier teardown

    reply = d._cmd_shutdown({})
    assert reply == {"success": True, "shutting_down": True}

    time.sleep(0.4)  # let the background thread run past the 0.25s delay
    d.stop.assert_called_once()


def test_cmd_shutdown_swallows_stop_exception(monkeypatch):
    d = _make_daemon()
    monkeypatch.setattr(d, "broadcast", MagicMock())
    called = {"stop": False}

    def bad_stop():
        called["stop"] = True
        raise RuntimeError("stop boom")

    monkeypatch.setattr(d, "stop", bad_stop)

    excepthook_calls = []
    orig_hook = threading.excepthook

    def hook(args):
        excepthook_calls.append(args)

    threading.excepthook = hook
    try:
        reply = d._cmd_shutdown({})
        assert reply == {"success": True, "shutting_down": True}
        time.sleep(0.4)  # let the background thread's stop() raise
    finally:
        threading.excepthook = orig_hook

    assert called["stop"] is True
    assert excepthook_calls == [], (
        "the except Exception: pass around self.stop() must swallow the failure, "
        "not leak it as an uncaught exception in the background thread"
    )


# ── broadcast(): the plain delegation to SocketServer.broadcast ──────────


def test_broadcast_delegates_to_socket_server():
    d = _make_daemon()
    d._socket_server.broadcast = MagicMock()
    event = {"type": "status", "state": "idle"}

    d.broadcast(event)

    d._socket_server.broadcast.assert_called_once_with(event)


# ── _acquire_instance_lock: falsy socket_path + non-OSError flock failure ─


def test_acquire_instance_lock_true_when_socket_path_falsy():
    d = _make_daemon(socket_path="")
    assert d._acquire_instance_lock() is True


def test_acquire_instance_lock_flock_unsupported_does_not_block_startup(monkeypatch, tmp_path):
    import fcntl

    d = _make_daemon(socket_path=str(tmp_path / "divoom.sock"))

    def bad_flock(*_a, **_k):
        raise NotImplementedError("flock not supported on this fs")

    monkeypatch.setattr(fcntl, "flock", bad_flock)
    assert d._acquire_instance_lock() is True


# ── run(): the module-level entry point ────────────────────────────────────


def _fake_daemon_factory(*, acquire_ok=True, rehydrate_raises=None,
                          serve_raises=KeyboardInterrupt):
    """Builds a fake DivoomDaemon class (for monkeypatching in as
    ``daemon_mod.DivoomDaemon``) plus the list of instances it creates, so
    tests can assert on what run() actually did without any real socket,
    BLE, or notification monitor ever starting."""
    instances = []

    class _FakeNotifier:
        def __init__(self):
            self.started = False

        def start(self):
            self.started = True

    class _FakeDeviceOwner:
        def __init__(self):
            self.rehydrated = False

        def rehydrate_live_jobs(self):
            if rehydrate_raises is not None:
                raise rehydrate_raises
            self.rehydrated = True

    class _FakeDaemon:
        def __init__(self, **kwargs):
            self.kwargs = kwargs
            self._notifier = _FakeNotifier()
            self._device_owner = _FakeDeviceOwner()
            self.served = False
            self.stopped = False
            instances.append(self)

        def _acquire_instance_lock(self):
            return acquire_ok

        def serve_forever(self):
            self.served = True
            if serve_raises is not None:
                raise serve_raises

        def stop(self):
            self.stopped = True

    return _FakeDaemon, instances


def test_run_returns_early_when_instance_lock_lost(monkeypatch):
    Fake, instances = _fake_daemon_factory(acquire_ok=False)
    monkeypatch.setattr(daemon_mod, "DivoomDaemon", Fake)

    rc = daemon_mod.run(socket_path="/tmp/divoom_cov_run_lost_lock.sock")

    assert rc == 0
    d = instances[0]
    assert d._notifier.started is False, "must not start the notifier if the lock was lost"
    assert d.served is False, "must not call serve_forever if the lock was lost"


def test_run_happy_path_serves_until_keyboard_interrupt(monkeypatch):
    calls = {}

    def fake_signal(sig, handler):
        calls["sig"] = sig
        calls["handler"] = handler

    import signal as real_signal
    monkeypatch.setattr(real_signal, "signal", fake_signal)

    Fake, instances = _fake_daemon_factory(serve_raises=KeyboardInterrupt)
    monkeypatch.setattr(daemon_mod, "DivoomDaemon", Fake)

    rc = daemon_mod.run(socket_path="/tmp/divoom_cov_run_happy.sock")

    assert rc == 0
    d = instances[0]
    assert d._notifier.started is True
    assert d._device_owner.rehydrated is True
    assert d.served is True
    assert d.stopped is True, "KeyboardInterrupt from serve_forever must trigger daemon.stop()"
    assert calls["sig"] == real_signal.SIGTERM

    # The registered handler itself (never actually invoked by a real SIGTERM
    # in this test) must translate the signal into a KeyboardInterrupt so it
    # rides the same clean-shutdown path as Ctrl-C.
    with pytest.raises(KeyboardInterrupt):
        calls["handler"](real_signal.SIGTERM, None)


def test_run_rehydrate_failure_is_logged_not_fatal(monkeypatch):
    import signal as real_signal
    monkeypatch.setattr(real_signal, "signal", lambda *a, **k: None)

    Fake, instances = _fake_daemon_factory(
        rehydrate_raises=RuntimeError("rehydrate boom"), serve_raises=KeyboardInterrupt)
    monkeypatch.setattr(daemon_mod, "DivoomDaemon", Fake)

    rc = daemon_mod.run(socket_path="/tmp/divoom_cov_run_rehydrate_fail.sock")

    assert rc == 0
    d = instances[0]
    assert d._device_owner.rehydrated is False
    assert d.served is True, "a rehydrate failure must not stop the daemon from serving"


def test_run_signal_registration_failure_is_swallowed(monkeypatch):
    """signal.signal raises ValueError when not called on the main thread
    (e.g. under some test harnesses) — run() must swallow it and still serve."""
    import signal as real_signal

    def bad_signal(*_a, **_k):
        raise ValueError("signal only works in main thread")

    monkeypatch.setattr(real_signal, "signal", bad_signal)

    Fake, instances = _fake_daemon_factory(serve_raises=KeyboardInterrupt)
    monkeypatch.setattr(daemon_mod, "DivoomDaemon", Fake)

    rc = daemon_mod.run(socket_path="/tmp/divoom_cov_run_sigfail.sock")

    assert rc == 0
    assert instances[0].served is True
