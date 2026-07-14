"""R53 round 26 — multi-persona (Uncle Bob / Linus / Carmack / Hashimoto)
adversarial review fixes.

- Auth bearer token must be REDACTED in logs (it was printed in clear → leaked
  into headless daemon logfiles).
- CommandQueue.acquire must REJECT a steal by a different token (it used to
  silently overwrite the owner, stranding the holder's queued items).
- audio_visualizer must import `time` (the read-loop error path called
  time.sleep → NameError → killed the capture thread).
"""
import asyncio
import sys
from pathlib import Path

import pytest

sys.path.append(str(Path(__file__).parent.parent))
sys.path.append(str(Path(__file__).parent.parent / "divoom_gui"))


# ── auth token redaction ────────────────────────────────────────────────────

def test_redact_masks_token():
    from divoom_lib.divoom_auth import _redact
    secret = "abcdef0123456789deadbeef"
    out = _redact(secret)
    assert secret not in out, "full token must never appear"
    assert out.startswith("abcd"), "keeps a short prefix for correlation"
    assert "24 chars" in out
    assert _redact("") == "****"
    assert _redact(None) == "****"


# ── exclusive-steal rejection ───────────────────────────────────────────────

def test_acquire_rejects_steal_by_different_token():
    from archive.divoom_daemon.command_queue import CommandQueue

    async def run():
        loop = asyncio.get_event_loop()
        q = CommandQueue(loop, item_timeout=240.0, exclusive_timeout=30.0)
        await q.acquire("token-A")
        await q.acquire("token-A")  # same token re-acquire is idempotent
        stole = True
        try:
            await q.acquire("token-B")
            stole = True
        except RuntimeError:
            stole = False
        return stole, q._exclusive_owner

    stole, owner = asyncio.run(run())
    assert stole is False, "a different token must NOT steal the exclusive slot"
    assert owner == "token-A", "the original owner must be retained"


def test_acquire_succeeds_after_release():
    from archive.divoom_daemon.command_queue import CommandQueue

    async def run():
        loop = asyncio.get_event_loop()
        q = CommandQueue(loop, item_timeout=240.0, exclusive_timeout=30.0)
        await q.acquire("A")
        await q.release("A")
        await q.acquire("B")  # free now → must succeed
        return q._exclusive_owner

    assert asyncio.run(run()) == "B"


# ── audio visualizer time import ────────────────────────────────────────────

def test_audio_visualizer_imports_time():
    import divoom_gui.audio_visualizer as av
    assert hasattr(av, "time"), "audio_visualizer must import time (error-path backoff)"
