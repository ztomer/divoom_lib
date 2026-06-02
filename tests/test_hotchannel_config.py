"""Unit tests for the shared hot-channel persistence layer."""

import json
import sys
from pathlib import Path

import pytest

sys.path.append(str(Path(__file__).parent.parent))

from divoom_lib import hotchannel_config as hc


@pytest.fixture
def cfg_path(tmp_path, monkeypatch):
    p = tmp_path / "hotchannel.json"
    monkeypatch.setenv("DIVOOM_HOTCHANNEL_CONFIG", str(p))
    return p


def test_defaults_when_missing(cfg_path):
    cfg = hc.load_config()
    assert cfg == {"enabled": False, "interval": 3600, "classify": 18, "targets": []}


def test_save_and_reload(cfg_path):
    assert hc.save_config({"enabled": True, "interval": 900, "classify": 5,
                           "targets": ["AA:BB:CC:DD:EE:FF"]})
    cfg = hc.load_config()
    assert cfg["enabled"] is True
    assert cfg["interval"] == 900
    assert cfg["classify"] == 5
    assert cfg["targets"] == ["AA:BB:CC:DD:EE:FF"]


def test_partial_save_merges(cfg_path):
    hc.save_config({"targets": ["X"], "interval": 1200})
    hc.save_config({"enabled": True})  # partial
    cfg = hc.load_config()
    assert cfg["enabled"] is True
    assert cfg["targets"] == ["X"]      # preserved
    assert cfg["interval"] == 1200      # preserved


def test_interval_floor(cfg_path):
    hc.save_config({"interval": 5})
    assert hc.load_config()["interval"] == hc.MIN_INTERVAL


def test_targets_dedupe_and_clean(cfg_path):
    hc.set_targets(["AA", "AA", "  ", "BB", ""])
    assert hc.get_targets() == ["AA", "BB"]


def test_corrupt_file_falls_back(cfg_path):
    cfg_path.write_text("{not json", encoding="utf-8")
    assert hc.load_config()["interval"] == 3600


def test_written_file_is_valid_json(cfg_path):
    hc.save_config({"targets": ["LAN:192.168.1.5"]})
    data = json.loads(cfg_path.read_text())
    assert data["targets"] == ["LAN:192.168.1.5"]
