#!/usr/bin/env python3
"""Feishin / Navidrome album art integration for Divoom displays.

Feishin (Electron-based Navidrome client) stores its Subsonic API credentials
in Chromium Local Storage (LevelDB format). We scan the LevelDB files for the
credential string and call the Navidrome Subsonic API directly.
"""
import json
import logging
import os
import subprocess
import sys
import urllib.request
from pathlib import Path

logger = logging.getLogger(__name__)

_FEISHIN_CREDS_CACHE = None
_FEISHIN_CREDS_AT = 0.0


def _feishin_creds() -> tuple | None:
    global _FEISHIN_CREDS_CACHE, _FEISHIN_CREDS_AT
    import time
    now = time.monotonic()
    if _FEISHIN_CREDS_CACHE is not None and now - _FEISHIN_CREDS_AT < 60.0:
        return _FEISHIN_CREDS_CACHE

    leveldb_dir = Path.home() / "Library/Application Support/Feishin/Local Storage/leveldb"
    if not leveldb_dir.is_dir():
        _FEISHIN_CREDS_CACHE = None
        return None

    import re
    cred_pat = re.compile(rb'"credential":"(u=[^"]+)"')
    url_pat = re.compile(rb'"url":"(https?://[^"]+)"')

    server_url = None
    auth_qs = None
    for f in sorted(leveldb_dir.iterdir()):
        if f.suffix not in ('.ldb', '.log'):
            continue
        try:
            raw = f.read_bytes()
            if not auth_qs:
                m = cred_pat.search(raw)
                if m:
                    auth_qs = m.group(1).decode()
            if not server_url:
                m = url_pat.search(raw)
                if m:
                    server_url = m.group(1).decode()
            if auth_qs and server_url:
                break
        except Exception:
            continue

    if not (auth_qs and server_url):
        _FEISHIN_CREDS_CACHE = None
        return None

    _FEISHIN_CREDS_CACHE = (server_url.rstrip("/"), auth_qs)
    _FEISHIN_CREDS_AT = now
    return _FEISHIN_CREDS_CACHE


def _feishin_is_running() -> bool:
    try:
        return subprocess.run(
            ["pgrep", "-q", "Feishin"], capture_output=True, timeout=1
        ).returncode == 0
    except Exception:
        return False


def get_feishin_playing_track() -> dict | None:
    if sys.platform != "darwin":
        return None
    if not _feishin_is_running():
        return None

    creds = _feishin_creds()
    if not creds:
        return None

    server_url, auth_qs = creds
    api_url = f"{server_url}/rest/getNowPlaying.view?f=json&c=divoom&v=1.16.0&{auth_qs}"
    try:
        req = urllib.request.Request(api_url, headers={"User-Agent": "Divoom/1.0"})
        with urllib.request.urlopen(req, timeout=5) as resp:
            body = json.loads(resp.read().decode("utf-8"))
        sr = body.get("subsonic-response", {})
        if sr.get("status") != "ok":
            return None
        np = sr.get("nowPlaying") or {}
        entries = np.get("entry") if isinstance(np, dict) else None
        if not entries:
            return None
        entry = entries[0] if isinstance(entries, list) else entries
        if not entry or not entry.get("title"):
            return None
        track = entry.get("title", "")
        artist = entry.get("artist", "")
        cover_id = entry.get("coverArt", "")
        art_url = None
        if cover_id:
            art_url = f"{server_url}/rest/getCoverArt.view?f=json&c=divoom&v=1.16.0&{auth_qs}&id={cover_id}&size=500"
        return {"track": track, "artist": artist, "source": "Feishin", "artwork_url": art_url}
    except Exception as e:
        logger.debug(f"Feishin Navidrome API query failed: {e}")
        return None
