"""R53.39: the menubar subscriber loop must NOT permanently die when the daemon
drops under keep-alive. The old code called _on_shutdown() (a no-op under
keep-alive) and then unconditionally `return`ed, killing the reader thread — so
after any daemon restart the menubar stayed frozen forever, never re-subscribing.
Under the shared lifecycle (keep-alive off) it should still follow the daemon
down (terminate + stop the reader).

Teeth: restore the unconditional `return` and the keep-alive test sees only one
subscribe attempt (reader died) instead of reconnecting.
"""
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent))

import divoom_lib.lifecycle_config as lifecycle_config
from divoom_menubar.menubar_client import MenubarClient


def _make_client(daemon_success):
    client = object.__new__(MenubarClient)
    client._running = True
    client._on_shutdown = None
    client._on_status_change = None
    client._status = {}

    class _Inner:
        def __init__(self):
            self.subscribe_calls = 0

        def subscribe(self, on_event, should_stop=None):
            self.subscribe_calls += 1
            # connection "lost" immediately; stop the test after a few reconnects
            if self.subscribe_calls >= 3:
                client._running = False
            return

        def send_command(self, _cmd):
            return {"success": daemon_success}

    client._client = _Inner()
    return client


def test_keep_alive_reader_keeps_reconnecting(monkeypatch):
    monkeypatch.setattr("time.sleep", lambda *_a, **_k: None)
    # keep-alive ON → do NOT follow the daemon down
    monkeypatch.setattr(lifecycle_config, "get_keep_daemon_alive", lambda *a, **k: True)
    monkeypatch.setattr(lifecycle_config, "should_follow_daemon_shutdown", lambda _ka: False)

    client = _make_client(daemon_success=False)  # daemon is down
    shutdown_calls = []
    client._on_shutdown = lambda: shutdown_calls.append(1)

    client._subscribe_loop()  # self-terminates after 3 subscribe attempts

    assert client._client.subscribe_calls >= 3, "reader must keep reconnecting under keep-alive"
    assert shutdown_calls == [], "must not invoke shutdown under keep-alive"


def test_follow_down_terminates_reader(monkeypatch):
    monkeypatch.setattr("time.sleep", lambda *_a, **_k: None)
    # keep-alive OFF → follow the daemon down
    monkeypatch.setattr(lifecycle_config, "get_keep_daemon_alive", lambda *a, **k: False)
    monkeypatch.setattr(lifecycle_config, "should_follow_daemon_shutdown", lambda _ka: True)

    client = _make_client(daemon_success=False)
    shutdown_calls = []

    def _shutdown():
        shutdown_calls.append(1)
        client._running = False  # mimic terminate → stop()

    client._on_shutdown = _shutdown

    client._subscribe_loop()

    assert shutdown_calls == [1], "must follow the daemon down exactly once"
    assert client._client.subscribe_calls == 1, "reader must stop after following down"
