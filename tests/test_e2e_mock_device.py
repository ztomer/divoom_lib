"""Hardware-free end-to-end tests.

Inject the `MockBleakClient` (which records every frame the "device" receives)
into a real `Divoom`, drive the high-level Control Center commands, and assert
the exact wire bytes the library produces. This validates the full
bridge → Divoom → framing → GATT-write pipeline that real hardware would
otherwise be needed to confirm — without Bluetooth permission.
"""

import sys
from pathlib import Path

import pytest

sys.path.append(str(Path(__file__).parent.parent))
sys.path.append(str(Path(__file__).parent.parent / "scripts"))

from divoom_lib.divoom import Divoom
from divoom_lib import models, framing
from mock_device import MockBleakClient

MAC = "AA:BB:CC:DD:EE:FF"
WRITE_UUID = "49535343-8841-43f4-a8d4-ecbe34729bb3"


async def _connected_divoom():
    mock = MockBleakClient(MAC)
    dev = Divoom(mac=MAC, client=mock, use_ios_le_protocol=False)
    await dev.connect()
    mock.written.clear()  # drop connection-time chatter
    return dev, mock


def _decoded_frames(mock):
    """Parse every recorded write with the library's own parser."""
    out = []
    for _char, data in mock.written:
        msgs, _ = framing.parse_basic_protocol_frames(bytearray(data))
        out.extend(msgs)
    return out


@pytest.mark.asyncio
async def test_connect_uses_injected_mock():
    dev, mock = await _connected_divoom()
    assert dev.is_connected is True
    assert dev.client is mock  # not replaced by a real BleakClient


@pytest.mark.asyncio
async def test_show_effects_emits_vj_frames():
    """2.d: VJ effect 9 → set light mode [3, 10] due to 1-indexed offset."""
    dev, mock = await _connected_divoom()
    await dev.display.show_effects(number=9)
    frames = _decoded_frames(mock)
    cmds = [f["command_id"] for f in frames]
    assert models.COMMANDS["set light mode"] in cmds
    vj_cmd = next(f for f in frames if f["command_id"] == models.COMMANDS["set light mode"])
    assert list(vj_cmd["payload"])[:2] == [3, 10]


@pytest.mark.asyncio
async def test_show_effects_lan_unsupported():
    """VJ effects should return False and warn on LAN devices."""
    mock = MockBleakClient(MAC)
    # Instantiate with a dummy lan_ip to simulate a Wi-Fi/LAN device
    dev = Divoom(mac=MAC, client=mock, lan_ip="192.168.1.100", use_ios_le_protocol=False)
    assert dev.display.communicator.lan is not None
    
    ok = await dev.display.show_effects(number=5)
    assert ok is False
    
    ok_switch = await dev.display.switch_channel("vj")
    assert ok_switch is False


@pytest.mark.asyncio
async def test_show_visualization_emits_eq_frames():
    """2.c: visualizer 3 → set light mode [4, 3]."""
    dev, mock = await _connected_divoom()
    await dev.display.show_visualization(number=3)
    frames = _decoded_frames(mock)
    cmds = [f["command_id"] for f in frames]
    assert models.COMMANDS["set light mode"] in cmds
    eq_cmd = next(f for f in frames if f["command_id"] == models.COMMANDS["set light mode"])
    assert list(eq_cmd["payload"])[:2] == [4, 3]


@pytest.mark.asyncio
async def test_show_scoreboard_emits_channel_0x06_frame():
    """Round 6.1: show_scoreboard() switches the device to the
    scoreboard tool channel (0x06). Wire bytes: set light mode [0x06,
    0, 0, 0, 0, 0, 0, 0, 0, 0] (10-byte payload per show_clock /
    show_visualization / show_effects / show_design)."""
    dev, mock = await _connected_divoom()
    await dev.display.show_scoreboard()
    frames = _decoded_frames(mock)
    cmds = [f["command_id"] for f in frames]
    assert models.COMMANDS["set light mode"] in cmds
    sb_cmd = next(f for f in frames if f["command_id"] == models.COMMANDS["set light mode"])
    payload = list(sb_cmd["payload"])
    assert payload[0] == 0x06, f"Expected channel id 0x06, got {payload[0]:#04x}"
    # Pad-out: the rest should be zeros (we don't write scores here, just
    # switch channels — scores are pushed by the 0x72 set-tool command).
    assert payload[1:] == [0] * 9, f"Expected padded zeros, got {payload[1:]}"


@pytest.mark.asyncio
async def test_switch_channel_scoreboard_dispatches_to_show_scoreboard():
    """Round 6.1: switch_channel('scoreboard') now routes to
    show_scoreboard() (0x45 [0x06, ...]) instead of returning False."""
    dev, mock = await _connected_divoom()
    ok = await dev.display.switch_channel("scoreboard")
    assert ok is True, "switch_channel('scoreboard') returned False"
    frames = _decoded_frames(mock)
    cmds = [f["command_id"] for f in frames]
    assert models.COMMANDS["set light mode"] in cmds
    sb_cmd = next(f for f in frames if f["command_id"] == models.COMMANDS["set light mode"])
    assert list(sb_cmd["payload"])[0] == 0x06


@pytest.mark.asyncio
async def test_show_clock_emits_clock_frame():
    """2.f: clock dial 2 → 'set light mode' frame carrying the dial index."""
    dev, mock = await _connected_divoom()
    await dev.display.show_clock(clock=2)
    frames = _decoded_frames(mock)
    clock = next(f for f in frames if f["command_id"] == models.COMMANDS["set light mode"])
    # payload: [00, 24h=01, dial=02, activated=01, weather, temp, calendar]
    assert clock["payload"][2] == 2
    assert clock["payload"][3] == 1  # clock activated


@pytest.mark.asyncio
async def test_show_image_emits_0x49_frames():
    """Regression: image push must use command 0x49 (was KeyError 'set image',
    which silently broke album art / gallery / ticker / sysmon on-device).

    Command choice rationale: 0x44 is a single-frame static image; 0x49 is
    the multi-frame animation (and also works for single-frame, as the device
    auto-loops a 1-frame animation as a static image). Live device finding
    on 2026-06-05: 0x44 + 0x49-format body renders only frame 0 and discards
    the rest. 0x49 + 0x49-format body renders all frames correctly."""
    from PIL import Image
    p = Path("/tmp/e2e_img_test.png")
    Image.new("RGB", (16, 16), (255, 0, 0)).save(p)
    dev, mock = await _connected_divoom()
    ok = await dev.display.show_image(str(p))
    assert ok is True
    assert mock.written, "no frames written"
    full = b"".join(data for _char, data in mock.written)
    msgs, _ = framing.parse_basic_protocol_frames(bytearray(full))
    cmds = [m["command_id"] for m in msgs]
    assert 0x49 in cmds


@pytest.mark.asyncio
async def test_written_frames_are_valid_framing():
    """Every emitted frame round-trips through the parser (valid checksum/END)."""
    dev, mock = await _connected_divoom()
    await dev.display.show_effects(number=0)
    assert mock.written, "no frames written"
    # If any checksum/END were wrong, the parser would yield fewer messages.
    assert len(_decoded_frames(mock)) >= 1


@pytest.mark.asyncio
async def test_clock_dial_set_and_read_back_roundtrip():
    """Verify that we can set the clock style and read it back from mock device."""
    dev, mock = await _connected_divoom()
    # Set to clock dial 4
    await dev.display.show_clock(clock=4)
    # Read it back using get_light_mode
    light_mode = await dev.light.get_light_mode()
    assert light_mode is not None
    assert light_mode["time_display_mode"] == 4


@pytest.mark.asyncio
async def test_watchface_roundtrip_script_e2e(monkeypatch):
    """Verify that verify_device in the watchface roundtrip script successfully
    interacts with the Divoom facade using MockBleakClient."""
    from scripts.test_watchface_roundtrip import verify_device
    
    original_divoom_init = Divoom.__init__
    
    def mock_divoom_init(self, *args, **kwargs):
        kwargs["client"] = MockBleakClient(kwargs.get("mac", "AA:BB:CC:DD:EE:FF"))
        original_divoom_init(self, *args, **kwargs)
        
    monkeypatch.setattr(Divoom, "__init__", mock_divoom_init)
    
    success = await verify_device("AA:BB:CC:DD:EE:FF", "MockDevice", dial=3)
    assert success is True


