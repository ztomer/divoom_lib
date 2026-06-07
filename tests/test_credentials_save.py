"""Regression: saving settings with a blank password must NOT erase the stored
Divoom password (the "credentials get erased from time to time" bug).

The settings form never re-populates the password field, so a plain re-save
submits password="". save_credentials used to overwrite the stored password with
that blank, and the next 23h token-cache expiry then degraded the account to a
guest token. The fix preserves the stored password when a blank one is given.
"""
import configparser
import sys
from pathlib import Path

import pytest

sys.path.append(str(Path(__file__).parent.parent))
sys.path.append(str(Path(__file__).parent.parent / "gui"))

import presets_manager
from presets_manager import PresetsManagerMixin


class _FakeCreds:
    def is_valid(self):
        return True


class _Host(PresetsManagerMixin):
    def __init__(self):
        self.cached_creds = None


@pytest.fixture
def home(tmp_path, monkeypatch):
    monkeypatch.setattr(presets_manager.Path, "home", staticmethod(lambda: tmp_path))
    monkeypatch.setattr(presets_manager.divoom_auth, "get_credentials",
                        lambda *a, **k: _FakeCreds())
    cfg_dir = tmp_path / ".config" / "divoom-control"
    cfg_dir.mkdir(parents=True)
    return tmp_path, cfg_dir / "config.ini"


def _read(cfg_path):
    c = configparser.ConfigParser()
    c.read(cfg_path)
    return c


def test_blank_password_preserves_stored_password(home):
    tmp, cfg_path = home
    host = _Host()
    # First, a real save with email + password.
    host.save_credentials("me@example.com", "s3cret")
    assert _read(cfg_path)["divoom"]["password"] == "s3cret"

    # Re-save with a blank password (form never re-populates it) — must NOT wipe.
    host.save_credentials("me@example.com", "")
    cfg = _read(cfg_path)
    assert cfg["divoom"]["password"] == "s3cret", "blank re-save erased the password"
    assert cfg["divoom"]["email"] == "me@example.com"


def test_blank_password_keeps_token_cache(home):
    tmp, cfg_path = home
    host = _Host()
    host.save_credentials("me@example.com", "s3cret")
    token = tmp / ".config" / "divoom-control" / "auth_token.json"
    token.write_text("{}", encoding="utf-8")
    # blank re-save must not delete the working token cache
    host.save_credentials("me@example.com", "")
    assert token.exists(), "blank re-save nuked the token cache"


def test_new_password_updates_and_refreshes(home):
    tmp, cfg_path = home
    host = _Host()
    host.save_credentials("me@example.com", "old")
    token = tmp / ".config" / "divoom-control" / "auth_token.json"
    token.write_text("{}", encoding="utf-8")
    host.save_credentials("me@example.com", "new")
    assert _read(cfg_path)["divoom"]["password"] == "new"
    assert not token.exists(), "a real password change should invalidate the cache"
