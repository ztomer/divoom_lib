"""Round 11 (items 1c/2a/9): Animation.stream_animation_8b.

Verifies the 0x8B 3-phase streamer matches the futpib reference: a sequential
chunk-INDEX offset_id (0,1,2,…) with 256-byte chunks, sent as start + N data +
terminate. The chunk size MUST be 256 — the device places chunk N at byte N*256,
so the monthly-best daemon's 200-byte chunks left gaps and stalled the device.
"""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from divoom_lib.models import (
    COMMANDS,
    ANSGC_CONTROL_START_SENDING,
    ANSGC_CONTROL_SENDING_DATA,
    ANSGC_CONTROL_TERMINATE_SENDING,
)
from divoom_lib.display.animation import Animation


def _make_anim():
    comm = MagicMock()
    comm.logger = MagicMock()
    comm.lan = None
    comm.use_spp = False
    comm.send_command = AsyncMock(return_value=True)
    return Animation(comm), comm


@pytest.mark.asyncio
async def test_stream_phases_and_chunk_index_offsets():
    anim, comm = _make_anim()
    blob = bytes(range(256)) * 2 + bytes(50)  # 562 bytes → ceil(562/256) = 3 chunks
    with patch("divoom_lib.display.animation.asyncio.sleep", new=AsyncMock()):
        ok = await anim.stream_animation_8b(blob)
    assert ok is True

    calls = [c for c in comm.send_command.await_args_list
             if c.args and c.args[0] == COMMANDS["app new send gif cmd"]]
    # start + 3 data + terminate
    assert len(calls) == 5
    control_words = [c.args[1][0] for c in calls]
    assert control_words[0] == ANSGC_CONTROL_START_SENDING
    assert control_words[-1] == ANSGC_CONTROL_TERMINATE_SENDING
    assert all(cw == ANSGC_CONTROL_SENDING_DATA for cw in control_words[1:-1])

    # data phases: args = [CW, fs(4 LE), offset_id(2 LE), *chunk]
    data_calls = calls[1:-1]
    offset_ids = [int.from_bytes(bytes(c.args[1][5:7]), "little") for c in data_calls]
    assert offset_ids == [0, 1, 2], "offset_id must be a sequential chunk index"
    # First two chunks must be the full 256 bytes (chunk N lands at byte N*256).
    assert len(data_calls[0].args[1]) == 1 + 4 + 2 + 256
    assert len(data_calls[1].args[1]) == 1 + 4 + 2 + 256
    assert len(data_calls[2].args[1]) == 1 + 4 + 2 + 50


@pytest.mark.asyncio
async def test_stream_empty_blob_returns_false():
    anim, comm = _make_anim()
    with patch("divoom_lib.display.animation.asyncio.sleep", new=AsyncMock()):
        assert await anim.stream_animation_8b(b"") is False
    comm.send_command.assert_not_called()


@pytest.mark.asyncio
async def test_stream_aborts_on_chunk_failure():
    anim, comm = _make_anim()
    # start ok, first data chunk fails
    comm.send_command = AsyncMock(side_effect=[True, False])
    with patch("divoom_lib.display.animation.asyncio.sleep", new=AsyncMock()):
        ok = await anim.stream_animation_8b(bytes(300))
    assert ok is False
