"""Hardware-free end-to-end test: weather push through the daemon proxy.

Split out of tests/test_e2e_mock_device.py: this is the only test in that file
that depends on the archived divoom_daemon.daemon.DivoomDaemon server (spun up
in-process to exercise WidgetsApi.push_weather through the daemon proxy). The
rest of that file drives divoom_lib.divoom.Divoom directly against
MockBleakClient and has no daemon dependency, so it stayed in tests/.
"""

import sys
from pathlib import Path

import pytest

sys.path.append(str(Path(__file__).parent.parent.parent))


@pytest.mark.asyncio
async def test_weather_set_proxy_daemon_roundtrip():
    """Weather push through the daemon proxy: WidgetsApi.push_weather
    path must resolve correctly. Uses the in-process daemon from
    test_daemon_bridge's fixture pattern."""
    import os, threading, time
    import asyncio
    from archive.divoom_daemon.daemon import DivoomDaemon
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
