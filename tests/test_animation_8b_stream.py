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
    # R34 §1b: by default the fake device never replies on 0x8b — the streamer
    # must fall back to the legacy fixed-sleep flow (APK ACK-gating is optional).
    comm.wait_for_response = AsyncMock(return_value=None)
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
    # start + 3 data (APK does NOT send terminate — R35d)
    assert len(calls) == 4
    control_words = [c.args[1][0] for c in calls]
    assert control_words[0] == ANSGC_CONTROL_START_SENDING
    assert all(cw == ANSGC_CONTROL_SENDING_DATA for cw in control_words[1:])

    # data phases: args = [CW, fs(4 LE), offset_id(2 LE), *chunk]
    data_calls = calls[1:]
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


# ── R34 §1b: APK-aligned device-driven flow ──────────────────────────────


@pytest.mark.asyncio
async def test_stream_waits_for_start_ack_before_chunks():
    """APK: after START, the device replies [0] ('send the animation') and only
    then does the app stream chunks (bluetooth/s.java → startSendAllAni)."""
    anim, comm = _make_anim()
    order = []
    comm.send_command = AsyncMock(side_effect=lambda *a, **k: order.append(("send", a[1][0])) or True)
    comm.wait_for_response = AsyncMock(side_effect=lambda *a, **k: order.append(("wait",)) or bytes([0]))
    with patch("divoom_lib.display.animation.asyncio.sleep", new=AsyncMock()):
        # quiet retransmit phase: after the ready ACK, subsequent waits go quiet
        comm.wait_for_response.side_effect = [bytes([0]), None]
        ok = await anim.stream_animation_8b(bytes(300))
    assert ok is True
    assert comm.wait_for_response.await_count >= 1
    # The ready wait targets the 0x8b command id.
    assert comm.wait_for_response.await_args_list[0].args[0] == COMMANDS["app new send gif cmd"]


@pytest.mark.asyncio
async def test_stream_serves_retransmit_requests():
    """APK: the device may reply [1][idx:2 LE] requesting chunk idx again
    (bluetooth/s.java → resendBlueData). The streamer must re-send that chunk."""
    anim, comm = _make_anim()
    blob = bytes(range(256)) * 2 + bytes(50)  # 3 chunks
    # ready ACK, then one retransmit request for chunk 1, then quiet
    comm.wait_for_response = AsyncMock(side_effect=[bytes([0]), bytes([1, 1, 0]), None])
    with patch("divoom_lib.display.animation.asyncio.sleep", new=AsyncMock()):
        ok = await anim.stream_animation_8b(blob)
    assert ok is True
    data_calls = [c for c in comm.send_command.await_args_list
                  if c.args and c.args[0] == COMMANDS["app new send gif cmd"]
                  and c.args[1][0] == ANSGC_CONTROL_SENDING_DATA]
    offset_ids = [int.from_bytes(bytes(c.args[1][5:7]), "little") for c in data_calls]
    assert offset_ids == [0, 1, 2, 1], "chunk 1 must be re-sent on request"
    # The retransmitted chunk carries the same bytes as the original.
    assert data_calls[3].args[1][7:] == data_calls[1].args[1][7:]


@pytest.mark.asyncio
async def test_stream_falls_back_when_device_never_acks():
    """No 0x8b reply at all (older firmware / LAN): the streamer must still
    complete via the legacy fixed-sleep flow."""
    anim, comm = _make_anim()  # wait_for_response → None
    with patch("divoom_lib.display.animation.asyncio.sleep", new=AsyncMock()):
        ok = await anim.stream_animation_8b(bytes(300))
    assert ok is True
    calls = [c for c in comm.send_command.await_args_list
             if c.args and c.args[0] == COMMANDS["app new send gif cmd"]]
    assert len(calls) == 3  # start + 2 data, no terminate (R35d), no retransmits


@pytest.mark.asyncio
async def test_stream_clears_expected_response_command_on_failure():
    """R53.23: the 0x8B streamer sets communicator._expected_response_command before
    START. On the device-ready-timeout + chunk-failure path it used to leave it
    pinned to 0x8B, mis-routing the NEXT op's notifications (cross-talk). A
    try/finally must always clear it."""
    anim, comm = _make_anim()
    comm._expected_response_command = None              # real BLE-path attribute
    comm.wait_for_response = AsyncMock(return_value=None)   # device never ACKs ready
    comm.send_command = AsyncMock(side_effect=[True, False])  # start ok, chunk fails
    with patch("divoom_lib.display.animation.asyncio.sleep", new=AsyncMock()):
        ok = await anim.stream_animation_8b(bytes(300))
    assert ok is False
    assert comm._expected_response_command is None, "scalar leaked after failed stream"


@pytest.mark.asyncio
async def test_stream_clears_expected_response_command_on_success():
    anim, comm = _make_anim()
    comm._expected_response_command = None
    comm.wait_for_response = AsyncMock(return_value=None)   # falls back to sleep
    with patch("divoom_lib.display.animation.asyncio.sleep", new=AsyncMock()):
        ok = await anim.stream_animation_8b(bytes(300))
    assert ok is True
    assert comm._expected_response_command is None, "scalar leaked after successful stream"


# ── R53.x HW: 0x8B retransmit dead-path fix ──────────────────────────────────


@pytest.mark.asyncio
async def test_stream_listens_for_0x8b_during_stream_and_cleans_up():
    """The retransmit window runs with _expected_response_command == None (the
    start-ACK wait cleared it). Without 0x8B in _listen_commands the real handler
    DROPS every unsolicited retransmit request, so the streamer must LISTEN for
    0x8B for the stream's duration and remove it afterward.

    Teeth: drop the `_listen.add(...)` and seen_during is all-False; drop the
    `_listen.discard(...)` and 0x8B leaks into _listen_commands after the stream."""
    cmd8b = COMMANDS["app new send gif cmd"]
    comm = MagicMock()
    comm.logger = MagicMock()
    comm.lan = None
    comm.use_spp = False
    comm.send_command = AsyncMock(return_value=True)
    comm._expected_response_command = None
    comm._listen_commands = set()  # a REAL set so the fix engages (isinstance check)

    seen_during = []

    async def _wait(cmd, timeout):
        seen_during.append(cmd8b in comm._listen_commands)
        return None  # device quiet → ready-wait falls back, retransmit phase ends

    comm.wait_for_response = _wait
    anim = Animation(comm)
    with patch("divoom_lib.display.animation.asyncio.sleep", new=AsyncMock()):
        ok = await anim.stream_animation_8b(bytes(300))
    assert ok is True
    assert any(seen_during), "0x8B must be in _listen_commands DURING the stream"
    assert cmd8b not in comm._listen_commands, "0x8B must be removed after the stream"


def test_listened_0x8b_retransmit_queues_without_consuming_scalar():
    """The mechanism the fix relies on: with the scalar cleared mid-stream, a 0x8B
    frame survives ONLY because it's in _listen_commands (the handler is_listened
    branch queues it without touching the scalar). Not-listening = dropped = the bug."""
    import asyncio
    import logging
    from divoom_lib.ble_notify import BleNotifyMixin
    from divoom_lib import framing

    cmd8b = COMMANDS["app new send gif cmd"]
    frame = bytes(framing.encode_ios_le_payload([cmd8b, 0x01, 0x05, 0x00]))  # "resend chunk 5"

    def _mk(listen):
        o = object.__new__(BleNotifyMixin)
        o._expected_response_command = None  # cleared by the start-ACK wait
        o.notification_queue = asyncio.Queue()
        o._listen_commands = listen
        o.use_ios_le_protocol = True
        o.logger = logging.getLogger("t8b")
        return o

    listening = _mk({cmd8b})
    listening._handle_ios_le_notification(frame)
    assert listening.notification_queue.qsize() == 1, "listened 0x8B must be queued"
    assert listening._expected_response_command is None, "listening must not touch the scalar"

    # teeth: not listening → the retransmit request is silently dropped (the bug)
    not_listening = _mk(set())
    not_listening._handle_ios_le_notification(frame)
    assert not_listening.notification_queue.qsize() == 0
