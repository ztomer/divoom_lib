"""Up-front macOS permission priming."""
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent))
sys.path.append(str(Path(__file__).parent.parent / "divoom_gui"))

from divoom_gui import permissions


def test_prime_automation_pokes_each_player(monkeypatch):
    calls = []
    monkeypatch.setattr(permissions.subprocess, "run",
                        lambda *a, **k: calls.append(a[0]))
    permissions._prime_automation()
    joined = " ".join(" ".join(c) for c in calls)
    assert "Music" in joined and "Spotify" in joined
    # uses osascript, and never LAUNCHES a player (guarded by `is running`).
    assert all(c[0] == "osascript" for c in calls)
    assert "is running" in joined


def test_prime_automation_swallows_errors(monkeypatch):
    def _boom(*a, **k):
        raise RuntimeError("osascript missing")
    monkeypatch.setattr(permissions.subprocess, "run", _boom)
    permissions._prime_automation()   # must not raise


def test_prime_permissions_noop_off_darwin(monkeypatch):
    monkeypatch.setattr(permissions.sys, "platform", "linux")
    started = []
    monkeypatch.setattr(permissions.threading, "Thread",
                        lambda *a, **k: started.append(1) or type("T", (), {"start": lambda self: None})())
    permissions.prime_permissions()
    assert started == []   # no priming thread off macOS
