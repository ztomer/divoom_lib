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
async def test_show_image_emits_0x8b_3phase():
    """A 16px image push (single still OR animation) streams via the 0x8B
    3-phase protocol, matching the futpib reference whose `send_image` routes a
    still PNG through the same animation path as a GIF.

    Round 11 (item 2a): single frames previously used 0x49 and cover art did not
    render on hardware; they now go through 0x8B like multi-frame. The three
    phases are StartSeeding (CW0), SendingData (CW1, ≥1), TerminateSending (CW2).
    """
    from PIL import Image
    p = Path("/tmp/e2e_img_test.png")
    Image.new("RGB", (16, 16), (255, 0, 0)).save(p)
    dev, mock = await _connected_divoom()
    ok = await dev.display.show_image(str(p))
    assert ok is True
    assert mock.written, "no frames written"
    full = b"".join(data for _char, data in mock.written)
    msgs, _ = framing.parse_basic_protocol_frames(bytearray(full))
    gif_cmd = models.COMMANDS["app new send gif cmd"]  # 0x8B
    control_words = [m["payload"][0] for m in msgs if m["command_id"] == gif_cmd]
    assert control_words, "no 0x8B frames emitted"
    assert control_words[0] == 0x00, "first 0x8B phase must be StartSeeding"
    assert control_words[-1] == 0x02, "last 0x8B phase must be TerminateSending"
    assert 0x01 in control_words, "expected at least one SendingData phase"


@pytest.mark.asyncio
async def test_written_frames_are_valid_framing():
    """Every emitted frame round-trips through the parser (valid checksum/END)."""
    dev, mock = await _connected_divoom()
    await dev.display.show_effects(number=0)
    assert mock.written, "no frames written"
    # If any checksum/END were wrong, the parser would yield fewer messages.
    assert len(_decoded_frames(mock)) >= 1


@pytest.mark.asyncio
async def test_weather_set_emits_0x5f_frame():
    """R14 §1: Weather.set() sends 0x5F command with [temp_byte, weather_type].
    Encodes negative temps as two's complement, positive as-is."""
    dev, mock = await _connected_divoom()
    from divoom_lib.system.weather import Weather
    w = Weather(dev)
    ok = await w.set(22, 1)
    assert ok is True
    frames = _decoded_frames(mock)
    cmds = [f["command_id"] for f in frames]
    assert models.COMMANDS["set temp"] in cmds
    weather_cmd = next(f for f in frames if f["command_id"] == models.COMMANDS["set temp"])
    payload = list(weather_cmd["payload"])
    assert payload[0] == 22, f"Expected temp byte 22, got {payload[0]}"
    assert payload[1] == 1, f"Expected weather type 1, got {payload[1]}"


@pytest.mark.asyncio
async def test_weather_set_negative_temp():
    """Negative temps encoded as 256 + celsius (two's complement byte)."""
    dev, mock = await _connected_divoom()
    from divoom_lib.system.weather import Weather
    w = Weather(dev)
    ok = await w.set(-5, 1)
    assert ok is True
    frames = _decoded_frames(mock)
    weather_cmd = next(f for f in frames if f["command_id"] == models.COMMANDS["set temp"])
    payload = list(weather_cmd["payload"])
    assert payload[0] == 251, f"Expected 251 for -5°C, got {payload[0]}"


@pytest.mark.asyncio
async def test_weather_set_rejects_out_of_range():
    """Temps outside -127..128 raise ValueError."""
    dev, _ = await _connected_divoom()
    from divoom_lib.system.weather import Weather
    w = Weather(dev)
    with pytest.raises(ValueError):
        await w.set(200, 1)


@pytest.mark.asyncio
async def test_weather_set_proxy_daemon_roundtrip():
    """Weather push through the daemon proxy: WidgetsApi.push_weather
    path must resolve correctly. Uses the in-process daemon from
    test_daemon_bridge's fixture pattern."""
    import os, threading, time
    import asyncio
    from divoom_daemon.daemon import DivoomDaemon
    from divoom_daemon.daemon_protocol import DaemonClient
    from divoom_gui.daemon_bridge import DaemonDeviceProxy
    from divoom_lib.system.weather import Weather

    sp = f"/tmp/divoom_weather_e2e_{os.getpid()}.sock"
    if os.path.exists(sp):
        os.remove(sp)

    class _FakeWeatherDevice:
        def __init__(self):
            self.is_connected = True
            self.commands = []
        async def send_command(self, cmd, args=None):
            self.commands.append((cmd, args))
            return True
        @property
        def logger(self):
            import logging
            return logging.getLogger(__name__)
        @property
        def control(self):
            class _FakeControl:
                async def set_light_mode(self, channel):
                    self.commands.append(("set_light_mode", channel))
                    return True
            return _FakeControl()

    dev = _FakeWeatherDevice()
    d = DivoomDaemon(mac="11:22:33:44:55:66", socket_path=sp, monitor=object(), device=dev)
    t = threading.Thread(target=d.serve_forever, daemon=True)
    t.start()
    for _ in range(50):
        if os.path.exists(sp):
            break
        time.sleep(0.02)

    try:
        client = DaemonClient(sp)
        proxy = DaemonDeviceProxy(client)
        w = Weather(proxy)
        ok = await w.set(22, 1)
        assert ok is True, "weather set through proxy returned False"
        # Verify the daemon received the send_command call with the
        # correct wire args (0x5F, [22, 1]).
        assert len(dev.commands) >= 1
        cmd, args = dev.commands[-1]
        assert cmd == 0x5F, f"Expected 0x5F, got {cmd:#04x}"
        assert args == [22, 1], f"Expected [22, 1], got {args}"
    finally:
        d.stop()
        t.join(timeout=3.0)
        if os.path.exists(sp):
            os.remove(sp)


@pytest.mark.asyncio
async def test_weather_push_switches_channel_before_data(monkeypatch):
    """Weather push must switch to TEMPRETURE channel (mode 1) before
    sending the 0x5F temperature data — confirmed by the decompiled APK:
    the device only DISPLAYS the cached weather data when in TEMPRETURE
    mode (light mode 1)."""
    import os, threading, time
    import asyncio
    from divoom_daemon.daemon import DivoomDaemon
    from divoom_daemon.daemon_protocol import DaemonClient
    from divoom_gui.daemon_bridge import DaemonDeviceProxy
    from divoom_gui.api.widgets import WidgetsApi
    from divoom_gui.api import AsyncLoopThread
    from divoom_lib.weather_provider import WeatherInfo

    async def _fake_get_weather():
        return WeatherInfo(temperature_c=22, weather_type=1,
                          location="Test", provider="stub", fetched_at=0.0)

    monkeypatch.setattr("divoom_lib.weather_provider.get_weather", _fake_get_weather)

    sp = f"/tmp/divoom_weather_chan_{os.getpid()}.sock"
    if os.path.exists(sp):
        os.remove(sp)

    commands = []

    class _FakeWeatherDevice:
        def __init__(self):
            self.is_connected = True
        async def send_command(self, cmd, args=None):
            commands.append(("send_command", cmd, args))
            return True
        @property
        def logger(self):
            import logging
            return logging.getLogger(__name__)
        @property
        def control(self):
            class _FakeControl:
                async def set_light_mode(self, channel):
                    commands.append(("set_light_mode", channel))
                    return True
            return _FakeControl()

    dev = _FakeWeatherDevice()
    d = DivoomDaemon(mac="11:22:33:44:55:66", socket_path=sp, monitor=object(), device=dev)
    t = threading.Thread(target=d.serve_forever, daemon=True)
    t.start()
    for _ in range(50):
        if os.path.exists(sp):
            break
        time.sleep(0.02)

    try:
        client = DaemonClient(sp)
        proxy = DaemonDeviceProxy(client)
        loop_thread = AsyncLoopThread()
        loop_thread.start()
        loop_thread.ready.wait()
        try:
            api = WidgetsApi(loop_thread, lambda: None, lambda: {"current_divoom": proxy})
            api._run_async = lambda coro: asyncio.run_coroutine_threadsafe(coro, loop_thread.loop).result()
            ok = api.push_weather()
            assert ok is True, f"push_weather returned False, commands={commands}"
        finally:
            loop_thread.stop()
        # Channel switch (TEMPRETURE mode 1, 6-byte payload) must precede
        # the weather data send.  Per APK CmdManager.t2: [1, temp_type,
        # r, g, b, 0].
        idx_light = next((i for i, c in enumerate(commands)
                          if c[0] == "send_command" and c[1] == 0x45), -1)
        idx_weather = next((i for i, c in enumerate(commands)
                            if c[0] == "send_command" and c[1] == 0x5F), -1)
        assert idx_light >= 0, f"No 0x45 command in {commands}"
        assert commands[idx_light][1] == 0x45
        assert commands[idx_light][2] == [1, 0, 255, 255, 255, 0], (
            f"Expected 6-byte thermal payload, got {commands[idx_light]}"
        )
        assert idx_light < idx_weather, (
            f"0x45 at pos {idx_light} should precede 0x5F at {idx_weather}: {commands}"
        )
    finally:
        d.stop()
        t.join(timeout=3.0)
        if os.path.exists(sp):
            os.remove(sp)


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


