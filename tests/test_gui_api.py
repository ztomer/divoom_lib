import sys
import json
import asyncio
import unittest
from unittest.mock import AsyncMock, MagicMock, patch
from pathlib import Path
import pytest

# Add paths to imports
sys.path.append(str(Path(__file__).parent.parent))
sys.path.append(str(Path(__file__).parent.parent / "divoom_gui"))

from gui_main import DivoomGuiAPI

class TestDivoomGuiAPI(unittest.TestCase):
    def setUp(self):
        # Prevent actually touching credentials files or presetting configs on disk during unit testing
        self.presets_patcher = patch("pathlib.Path.exists", return_value=False)
        self.presets_patcher.start()

        self.api = DivoomGuiAPI()
        self.api.window = MagicMock()

    def tearDown(self):
        self.presets_patcher.stop()

    def test_window_controls(self):
        """Test native window minimize, maximize, and thread-delayed close controls."""
        self.api.minimize_window()
        self.api.window.minimize.assert_called_once()

        self.api.maximize_window()
        self.api.window.toggle_fullscreen.assert_called_once()

        with patch("threading.Thread") as mock_thread:
            self.api.close_window()
            mock_thread.assert_called_once()

    def test_push_text(self):
        """R32 §D Text Channel: push_text renders the text to a device-sized
        image and pushes it via display.show_image (the LPWA 0x87 path didn't
        render on the LED matrices — nothing appeared)."""
        import os
        dev = MagicMock()
        dev.is_connected = True
        captured = {}

        async def _show_image(path):
            # Capture while the temp file still exists (push_text unlinks it).
            captured["path"] = path
            captured["exists"] = os.path.isfile(path)
            captured["ends_png"] = str(path).endswith(".png")
            return True

        dev.display.show_image = AsyncMock(side_effect=_show_image)
        self.api.current_divoom = dev
        self.api.current_target_mode = "single"
        ok = self.api.push_text("HI", color="#FF0000", speed=40, effect_style=1)
        self.assertTrue(ok)
        dev.display.show_image.assert_awaited_once()
        self.assertTrue(captured.get("exists"), "text image should exist during the push")
        self.assertTrue(captured.get("ends_png"))

    def test_push_text_empty_noop(self):
        """Empty text is a no-op (returns False, pushes nothing)."""
        dev = MagicMock()
        dev.display.show_image = AsyncMock(return_value=True)
        self.api.current_divoom = dev
        self.api.current_target_mode = "single"
        self.assertFalse(self.api.push_text("   "))
        dev.display.show_image.assert_not_called()

    def test_render_text_png_produces_sized_image(self):
        """The text renderer produces a square device-sized RGB PNG with the
        requested color present (no anti-aliasing)."""
        from PIL import Image
        from divoom_gui.api.lighting import LightingApi
        path = LightingApi._render_text_png("HI", "#FF0000", 16, 1)
        try:
            img = Image.open(path).convert("RGB")
            self.assertEqual(img.size, (16, 16))
            colors = {c for _, c in img.getcolors(maxcolors=4096)}
            self.assertIn((255, 0, 0), colors, "the fill color should appear in the render")
        finally:
            import os
            os.unlink(path)

    def test_set_alarm(self):
        """R7 Alarms: set_alarm maps enabled→status and weekday mask through."""
        dev = MagicMock()
        dev.alarm.set_alarm = AsyncMock(return_value=True)
        self.api.current_divoom = dev
        ok = self.api.set_alarm(2, True, 7, 30, 0b0011111)  # weekdays Mon-Fri
        self.assertTrue(ok)
        dev.alarm.set_alarm.assert_called_once_with(2, 1, 7, 30, 31, 0, 0)

    def test_set_alarm_no_device(self):
        self.api.current_divoom = None
        self.assertFalse(self.api.set_alarm(0, True, 6, 0, 0))

    def test_sleep_start_stop(self):
        """R7 Sleep Aid: start_sleep passes minutes/volume/color; stop sets on=0."""
        dev = MagicMock()
        dev.sleep.show_sleep = AsyncMock(return_value=True)
        self.api.current_divoom = dev
        self.assertTrue(self.api.start_sleep(20, "#ff0000", 8))
        kw = dev.sleep.show_sleep.call_args.kwargs
        self.assertEqual(kw.get("sleeptime"), 20)
        self.assertEqual(kw.get("volume"), 8)
        self.assertEqual(kw.get("on"), 1)
        self.assertEqual(list(kw.get("color")), [255, 0, 0])
        self.assertTrue(self.api.stop_sleep())
        self.assertEqual(dev.sleep.show_sleep.call_args.kwargs.get("on"), 0)

    def test_tools_timer_countdown_noise(self):
        """R7 Tools: action strings map to the right ctrl flags."""
        dev = MagicMock()
        dev.timer.set_timer = AsyncMock(return_value=True)
        dev.countdown.set_countdown = AsyncMock(return_value=True)
        dev.noise.set_noise = AsyncMock(return_value=True)
        self.api.current_divoom = dev
        self.api.set_timer("start"); dev.timer.set_timer.assert_called_with(1)
        self.api.set_timer("reset"); dev.timer.set_timer.assert_called_with(2)
        self.api.set_countdown("start", 5, 30); dev.countdown.set_countdown.assert_called_with(0, 5, 30)
        self.api.set_countdown("stop", 5, 30); dev.countdown.set_countdown.assert_called_with(1, 5, 30)
        self.api.set_noise("start"); dev.noise.set_noise.assert_called_with(1)
        self.api.set_noise("stop"); dev.noise.set_noise.assert_called_with(2)

    def test_r8_device_settings(self):
        """R8: hour/temp/name/fm map to the right facade calls + bool coercion."""
        dev = MagicMock()
        dev.system.set_hour_type = AsyncMock(return_value=True)
        dev.device.set_temp_type = AsyncMock(return_value=True)
        dev.device.set_device_name = AsyncMock(return_value=True)
        dev.radio.set_radio_frequency = AsyncMock(return_value=True)
        self.api.current_divoom = dev
        self.api.set_hour_type(True); dev.system.set_hour_type.assert_called_with(1)
        self.api.set_hour_type("false"); dev.system.set_hour_type.assert_called_with(0)
        self.api.set_temp_unit(True); dev.device.set_temp_type.assert_called_with(1)
        self.api.set_device_name("Bedroom"); dev.device.set_device_name.assert_called_with("Bedroom")
        self.api.set_fm_frequency(1015); dev.radio.set_radio_frequency.assert_called_with(1015)

    def test_r8_memorial_and_timeplan(self):
        """R8: memorial + timeplan pass through with status/have-flag derivation."""
        dev = MagicMock()
        dev.alarm.set_memorial_time = AsyncMock(return_value=True)
        dev.timeplan.set_time_manage_info = AsyncMock(return_value=True)
        self.api.current_divoom = dev
        self.api.set_memorial(0, True, 12, 25, 9, 0, "Xmas")
        dev.alarm.set_memorial_time.assert_called_with(0, 1, 12, 25, 9, 0, 1, "Xmas")
        self.api.set_timeplan(1, True, 7, 30, 0b0011111, 0)
        dev.timeplan.set_time_manage_info.assert_called_with(1, 7, 30, 31, 0, 0, 0, 10, 0)

    def test_r8_sync_time_and_auto_off_instantiated(self):
        """R8: time-sync + auto-power-off use the un-faceted helper classes."""
        dev = MagicMock()
        self.api.current_divoom = dev
        with patch("divoom_lib.system.date_time.DateTimeCommand") as DT:
            DT.return_value.update_date_time = AsyncMock(return_value=True)
            self.assertTrue(self.api.sync_time())
            DT.assert_called_once_with(dev)
        with patch("divoom_lib.system.device_settings.DeviceSettings") as DS:
            DS.return_value.set_auto_power_off = AsyncMock(return_value=True)
            self.assertTrue(self.api.set_auto_power_off(60))
            DS.return_value.set_auto_power_off.assert_called_with(60)

    def test_r8_no_device(self):
        self.api.current_divoom = None
        self.assertFalse(self.api.set_hour_type(True))
        self.assertFalse(self.api.set_fm_frequency(900))

    def test_r9_screen_dir_mirror(self):
        """R9: screen dir/mirror reach d.design with bool/int coercion."""
        dev = MagicMock()
        dev.design.set_screen_dir = AsyncMock(return_value=True)
        dev.design.set_screen_mirror = AsyncMock(return_value=True)
        self.api.current_divoom = dev
        self.api.set_screen_dir(2); dev.design.set_screen_dir.assert_called_with(2)
        self.api.set_screen_mirror("on"); dev.design.set_screen_mirror.assert_called_with(True)
        self.api.set_screen_mirror(0); dev.design.set_screen_mirror.assert_called_with(False)

    def test_r9_factory_reset_requires_token(self):
        """R9: factory_reset only fires with the literal 'RESET' token."""
        dev = MagicMock()
        dev.design.factory_reset = AsyncMock(return_value=True)
        self.api.current_divoom = dev
        self.assertFalse(self.api.factory_reset())          # no token
        self.assertFalse(self.api.factory_reset("yes"))     # wrong token
        dev.design.factory_reset.assert_not_called()
        self.assertTrue(self.api.factory_reset("RESET"))    # correct token
        dev.design.factory_reset.assert_called_once()

    def test_r9_no_device(self):
        self.api.current_divoom = None
        self.assertFalse(self.api.set_screen_dir(1))
        self.assertFalse(self.api.set_screen_mirror(True))
        self.assertFalse(self.api.factory_reset("RESET"))

    def test_r10_send_notification(self):
        """R10: text vs icon-only path + app_type range guard."""
        dev = MagicMock()
        dev.notification.show_notification = AsyncMock(return_value=True)
        dev.notification.show_notification_text = AsyncMock(return_value=True)
        self.api.current_divoom = dev
        # icon-only when no text
        self.api.send_notification(6)
        dev.notification.show_notification.assert_called_with(6)
        dev.notification.show_notification_text.assert_not_called()
        # text path when text given
        self.api.send_notification(7, "Hi")
        dev.notification.show_notification_text.assert_called_with(7, "Hi")
        # blank/whitespace text falls back to icon-only
        self.api.send_notification(2, "   ")
        dev.notification.show_notification.assert_called_with(2)
        # out-of-range refused without sending
        dev.notification.show_notification.reset_mock()
        self.assertFalse(self.api.send_notification(0))
        self.assertFalse(self.api.send_notification(15))
        dev.notification.show_notification.assert_not_called()

    def test_r10_no_device(self):
        self.api.current_divoom = None
        self.assertFalse(self.api.send_notification(6))

    # ── macOS notification mirroring (daemon-owned) ─────────────────────
    # The daemon is the single owner of the monitor; the GUI delegates over
    # RPC and must NOT poll the DB itself (docs/PLANNING_daemon_ownership.md).

    def _fake_client(self, *, state="idle", counters=None, error=None):
        """A DaemonClient stub whose notification RPCs return canned replies."""
        c = MagicMock()
        reply = {"success": error is None, "state": state,
                 "counters": counters or {"seen": 0, "routed": 0, "dropped": 0}}
        if error:
            reply["error"] = error
        c.start_notifications.return_value = reply
        c.stop_notifications.return_value = {"success": True, "state": "idle"}
        c.notification_status.return_value = reply
        c.set_routing.return_value = {"success": True}
        return c

    def test_notification_listener_initial_state(self):
        """No daemon → not running; stop is a safe no-op."""
        with patch.object(self.api, "_client", return_value=None):
            self.assertFalse(self.api.is_notification_listener_running())
            self.assertFalse(self.api.stop_notification_listener()["running"])

    @patch("sys.platform", new="darwin")
    @patch("divoom_daemon.macos_notifications.find_notification_db_path",
           return_value=Path("/fake/db.sqlite"))
    def test_start_notification_listener_delegates_to_daemon(self, _db):
        client = self._fake_client(state="active")
        with patch.object(self.api, "_client", return_value=client):
            result = self.api.start_notification_listener()
        self.assertTrue(result["running"])
        self.assertEqual(result["db_path"], "/fake/db.sqlite")
        client.start_notifications.assert_called_once()

    @patch("sys.platform", new="darwin")
    def test_start_notification_listener_no_daemon(self):
        with patch.object(self.api, "_client", return_value=None):
            result = self.api.start_notification_listener()
        self.assertFalse(result["running"])
        self.assertIn("daemon", result["error"])

    @patch("sys.platform", new="linux")
    def test_start_notification_listener_macos_only(self):
        result = self.api.start_notification_listener()
        self.assertFalse(result["running"])
        self.assertIn("macOS", result["error"])

    @patch("sys.platform", new="darwin")
    @patch("divoom_daemon.macos_notifications.find_notification_db_path",
           return_value=Path("/fake/db.sqlite"))
    def test_start_notification_listener_reports_daemon_error(self, _db):
        client = self._fake_client(state="error", error="db not found")
        with patch.object(self.api, "_client", return_value=client):
            result = self.api.start_notification_listener()
        self.assertFalse(result["running"])
        self.assertIn("db not found", result["error"])

    def test_stop_notification_listener_delegates(self):
        client = self._fake_client(state="active")
        with patch.object(self.api, "_client", return_value=client):
            result = self.api.stop_notification_listener()
        self.assertFalse(result["running"])
        client.stop_notifications.assert_called_once()

    def test_gui_does_not_instantiate_local_monitor(self):
        """Regression for the §1.2 double-route fix: the GUI must never build
        its own MacNotificationMonitor — that is the daemon's job."""
        with patch("divoom_daemon.macos_notifications.MacNotificationMonitor") as mock_cls, \
             patch.object(self.api, "_client", return_value=self._fake_client(state="active")), \
             patch("sys.platform", new="darwin"), \
             patch("divoom_daemon.macos_notifications.find_notification_db_path", return_value=None), \
             patch("divoom_daemon.macos_notifications.load_routing_table", return_value=[]):
            self.api.start_notification_listener()
            self.api.stop_notification_listener()
            self.api.is_notification_listener_running()
            self.api.get_notification_listener_status()
        mock_cls.assert_not_called()

    # ── status snapshot + routing save (Settings card) ────────────────

    @patch("sys.platform", new="darwin")
    @patch("divoom_daemon.macos_notifications.find_notification_db_path",
           return_value=Path("/fake/db.sqlite"))
    def test_get_notification_listener_status_shape(self, _db):
        """The status dict has every key the JS side renders; counters + state
        come from the daemon, rules from disk."""
        client = self._fake_client(state="active",
                                   counters={"seen": 12, "routed": 8, "dropped": 4})
        with patch("divoom_daemon.macos_notifications.load_routing_table",
                   return_value=[("whatsapp", 6), ("com.apple.mail", 7)]), \
             patch.object(self.api, "_client", return_value=client):
            s = self.api.get_notification_listener_status()

        self.assertTrue(s["platform_supported"])
        self.assertTrue(s["running"])
        self.assertEqual(s["db_path"], "/fake/db.sqlite")
        self.assertEqual(s["counters"], {"seen": 12, "routed": 8, "dropped": 4})
        self.assertEqual(s["rules"], [["whatsapp", 6], ["com.apple.mail", 7]])
        self.assertIn("routing_path", s)
        self.assertIsNone(s["error"])

    @patch("sys.platform", new="linux")
    def test_status_unsupported_off_macos(self):
        """On non-darwin, status reports unsupported and the toggle is disabled upstream."""
        s = self.api.get_notification_listener_status()
        self.assertFalse(s["platform_supported"])
        self.assertFalse(s["running"])
        self.assertIsNotNone(s["error"])
        # Rules still load from the file (or defaults) even off-macOS.
        self.assertIsInstance(s["rules"], list)

    def test_save_notification_routing_delegates_to_daemon(self):
        """save_notification_routing validates then forwards to set_routing."""
        client = self._fake_client()
        with patch("divoom_daemon.macos_notifications.load_routing_table",
                   return_value=[("whatsapp", 6)]), \
             patch.object(self.api, "_client", return_value=client):
            result = self.api.save_notification_routing('[["whatsapp", 6]]')
        self.assertIsNone(result["error"])
        self.assertEqual(result["rules"], [["whatsapp", 6]])
        client.set_routing.assert_called_once_with([("whatsapp", 6)])

    def test_save_notification_routing_rejects_invalid_json(self):
        """Invalid JSON returns the previous rules and a non-null error,
        without ever touching the daemon."""
        client = self._fake_client()
        with patch("divoom_daemon.macos_notifications.load_routing_table",
                   return_value=[("whatsapp", 6)]), \
             patch.object(self.api, "_client", return_value=client):
            result = self.api.save_notification_routing("this is not json")
        self.assertIsNotNone(result["error"])
        self.assertIn("Invalid", result["error"])
        self.assertEqual(result["rules"], [["whatsapp", 6]])
        client.set_routing.assert_not_called()

    def test_save_notification_routing_daemon_unavailable(self):
        """No daemon → previous rules + error, nothing written."""
        with patch("divoom_daemon.macos_notifications.load_routing_table",
                   return_value=[("whatsapp", 6)]), \
             patch.object(self.api, "_client", return_value=None):
            result = self.api.save_notification_routing('[["whatsapp", 6]]')
        self.assertIn("daemon", result["error"])
        self.assertEqual(result["rules"], [["whatsapp", 6]])

    def test_scan_devices(self):
        """R17 P5: scanning is owned by the daemon; the GUI proxies via scan()."""
        fake = MagicMock()
        fake.scan.return_value = {"success": True, "devices": [
            {"name": "Pixoo-Test", "address": "11:22:33:44:55:66"}]}
        self.api._daemon_client = fake
        with patch.object(type(self.api), "_cache_discovered", return_value=None):
            res = json.loads(self.api.scan_devices(timeout=2, limit=1))
        self.assertEqual(len(res), 1)
        self.assertEqual(res[0]["name"], "Pixoo-Test")
        fake.scan.assert_called_once_with(timeout=2.0, limit=1)

    def test_connect_single_device(self):
        """R17 P5: connect is delegated to the daemon; current_divoom becomes a
        DaemonDeviceProxy (the daemon owns the real BLE connection)."""
        from divoom_gui.daemon_bridge import DaemonDeviceProxy
        fake = MagicMock()
        fake.disconnect_device.return_value = {"success": True}
        fake.connect_device.return_value = {"success": True, "connected": True}
        self.api._daemon_client = fake
        with patch.object(type(self.api), "_device_name_for", return_value=None), \
             patch.object(type(self.api), "_persist_last_connected", return_value=None):
            success = self.api.connect_single_device("00:11:22:33:44:55")
        self.assertTrue(success)
        self.assertIsInstance(self.api.current_divoom, DaemonDeviceProxy)
        fake.connect_device.assert_called_once()
        self.assertEqual(fake.connect_device.call_args.kwargs.get("mac"), "00:11:22:33:44:55")

    def test_preset_persistence(self):
        """Test preset name loading when no files exist."""
        preset_names = self.api.load_preset_names()
        self.assertEqual(json.loads(preset_names), [])

        preset_data = self.api.load_preset_by_name("NonExistent")
        self.assertEqual(json.loads(preset_data), {})

    def _fake_wall_client(self):
        """A fake daemon client for wall ops: wall_configure succeeds and
        device_call (target='wall') records the dotted method + returns True."""
        fake = MagicMock()
        fake.wall_configure.return_value = {"success": True, "wall": True}
        fake.device_status.return_value = {"success": True, "connected": False,
                                           "mac": None, "lan_ip": None, "wall": True}
        fake.device_call.return_value = {"success": True, "result": True}
        return fake

    def test_wall_operations(self):
        """R17 P5: wall ops route through the daemon-owned wall via device_call
        (target='wall')."""
        fake = self._fake_wall_client()
        self.api._daemon_client = fake
        slots = {"AA:BB:CC:DD:EE:FF": {"x": 0, "y": 0, "size": 16, "width": 120, "height": 120}}
        self.api.update_wall_slots(json.dumps(slots))
        self.assertEqual(self.api.wall_slots, slots)
        self.api.current_target_mode = "wall"

        self.assertTrue(self.api.set_solid_light("00FFCC", 100))
        fake.device_call.assert_called_with("set_light", ["00FFCC", 100], {},
                                            target="wall", blobs=None, token=None)

        self.assertTrue(self.api.set_clock(3))
        # show_clock is called with clock=3 (kwargs)
        last = fake.device_call.call_args
        self.assertEqual(last.args[0], "show_clock")
        self.assertEqual(last.kwargs.get("target"), "wall")

    def test_vj_and_visualization_selectors(self):
        """2.c/2.d: VJ + EQ selectors dispatch to the daemon-owned wall."""
        fake = self._fake_wall_client()
        self.api._daemon_client = fake
        self.api.update_wall_slots(json.dumps(
            {"AA:BB:CC:DD:EE:FF": {"x": 0, "y": 0, "size": 16, "width": 120, "height": 120}}
        ))
        self.api.current_target_mode = "wall"

        self.assertTrue(self.api.set_vj_effect(5))
        self.assertEqual(fake.device_call.call_args.args[0], "show_effects")

        self.assertTrue(self.api.set_visualization(3))
        self.assertEqual(fake.device_call.call_args.args[0], "show_visualization")

    def test_vj_visualization_no_target(self):
        """With no connected device and no wall, selectors fail gracefully (no raise)."""
        self.api.current_divoom = None
        self.api.wall_slots = {}
        self.assertFalse(self.api.set_vj_effect(0))
        self.assertFalse(self.api.set_visualization(0))

    def test_hot_channel_bridges_delegate(self):
        """4.c/4.d: target + schedule bridges delegate to hotchannel_config."""
        cfg = {"enabled": False, "interval": 3600, "classify": 18, "targets": ["AA"]}
        with patch("divoom_lib.hotchannel_config.set_targets", return_value=True) as mset, \
             patch("divoom_lib.hotchannel_config.load_config", return_value=cfg), \
             patch("divoom_lib.hotchannel_config.get_targets", return_value=["AA"]), \
             patch("divoom_lib.hotchannel_config.save_config", return_value=True) as msave:

            self.assertTrue(self.api.set_sync_targets(json.dumps(["AA", "BB"])))
            mset.assert_called_once_with(["AA", "BB"])

            self.assertEqual(json.loads(self.api.get_hot_channel_config())["targets"], ["AA"])

            self.assertTrue(self.api.save_hot_channel_config(json.dumps({"enabled": True})))
            msave.assert_called_once()

            cands = json.loads(self.api.get_sync_candidates())
            sel = {c["address"]: c["selected"] for c in cands}
            self.assertTrue(sel.get("AA"))  # persisted target shows as selected

    def test_ticker_preview_returns_data_url(self):
        """5.d: get_ticker_preview renders a frame and returns a PNG data URL."""
        from pathlib import Path as _P
        with patch("divoom_lib.utils.media_source.fetch_stock_ticker",
                   return_value={"price": 100.0, "change": 1.0, "pct_change": 1.0}), \
             patch("divoom_lib.utils.media_source.render_stock_ticker_frame",
                   return_value=_P("/tmp/ticker_preview_test.png")), \
             patch.object(type(self.api), "_frame_to_data_url",
                          staticmethod(lambda p: "data:image/png;base64,AAA")):
            res = json.loads(self.api.get_ticker_preview("AAPL", 32))
            self.assertTrue(res["ok"])
            self.assertEqual(res["size"], 32)
            self.assertTrue(res["preview"].startswith("data:image/png;base64,"))

    def test_apply_stock_ticker_no_target(self):
        """5.a: clear failure when there is no connected device."""
        self.api.current_divoom = None
        self.api.wall_slots = {}
        with patch("divoom_lib.utils.media_source.fetch_stock_ticker",
                   return_value={"price": 1.0, "change": 0.0, "pct_change": 0.0}):
            res = json.loads(self.api.apply_stock_ticker("AAPL"))
            self.assertFalse(res["success"])
            self.assertEqual(res["error"], "No device connected")

    def test_ticker_persistence(self):
        """5.e: tickers save/load, de-duped and upper-cased."""
        import tempfile, os
        from pathlib import Path as _P
        tmp = _P(tempfile.mkdtemp()) / "tickers.json"
        # Override the setUp-wide Path.exists=False so the read path works.
        with patch.object(type(self.api), "_tickers_path", lambda self: tmp), \
             patch("pathlib.Path.exists", return_value=True):
            self.assertTrue(self.api.set_tickers(json.dumps(["aapl", "AAPL", "btc-usd", ""])))
            self.assertEqual(json.loads(self.api.get_tickers()), ["AAPL", "BTC-USD"])

    def test_system_stats_preview_and_apply(self):
        """Area 7: system-monitor widget renders a frame and reports stats."""
        from pathlib import Path as _P
        with patch("divoom_lib.utils.media_source.get_system_stats",
                   return_value={"cpu": 12, "mem": 43, "battery": 80}), \
             patch("divoom_lib.utils.media_source.render_system_stats_frame",
                   return_value=_P("/tmp/sysmon_test.png")), \
             patch.object(type(self.api), "_frame_to_data_url",
                          staticmethod(lambda p: "data:image/png;base64,BBB")):
            prev = json.loads(self.api.get_system_stats_preview(32))
            self.assertTrue(prev["ok"])
            self.assertEqual(prev["stats"]["cpu"], 12)
            self.assertTrue(prev["preview"].startswith("data:image/png;base64,"))

            # apply with no device → clear failure
            self.api.current_divoom = None
            self.api.wall_slots = {}
            res = json.loads(self.api.apply_system_stats())
            self.assertFalse(res["success"])
            self.assertEqual(res["error"], "No device connected")

    def test_sync_hot_channel_multi(self):
        """4.b: sync_hot_channel pushes every artwork and reports a summary."""
        with patch.object(self.api, "batch_sync_artwork", return_value=True) as m:
            res = json.loads(self.api.sync_hot_channel(json.dumps(["id1", "id2", "id3"])))
            self.assertTrue(res["ok"])
            self.assertEqual(res["synced"], ["id1", "id2", "id3"])
            self.assertEqual(m.call_count, 3)

        with patch.object(self.api, "batch_sync_artwork", side_effect=[True, False]):
            res2 = json.loads(self.api.sync_hot_channel(json.dumps(["a", "b"])))
            self.assertFalse(res2["ok"])
            self.assertEqual(res2["failed"], ["b"])

    @patch("urllib.request.urlopen")
    def test_fetch_gallery_and_batch_sync(self, mock_urlopen):
        """Test cloud gallery catalog scraping and concurrent monthly best async streams."""
        # Mock fetch_gallery HTTP JSON response
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps({
            "FileList": [
                {"FileName": "NeonSkull", "FileId": "9999", "LikeCnt": 1500, "FileType": 5, "PixelAmbId": "amb123"}
            ]
        }).encode("utf-8")
        mock_urlopen.return_value.__enter__.return_value = mock_resp

        # Mock authentication credentials
        self.api.cached_creds = MagicMock()
        self.api.cached_creds.token = "token123"
        self.api.cached_creds.user_id = 99
        self.api.cached_creds.is_valid.return_value = True

        # Pre-seed cached data for the offline cache loader check.
        # Use a real-looking file_id (not "9999") so the rebuild-on-stale path
        # doesn't trigger (see gui/gallery_sync.py load_cached_gallery).
        cached_items = [
            {"name": "NeonSkull", "file_id": "group1/M00/01/AAA_neon", "likes": 1500, "magic": 5, "preview_url": "data:image/png;base64,..."}
        ]

        import threading
        import time

        with patch("pathlib.Path.exists", return_value=True), \
             patch("pathlib.Path.read_text", return_value=json.dumps(cached_items)):
            gallery_json = self.api.fetch_gallery(classify=1)
            gallery = json.loads(gallery_json)
            self.assertEqual(len(gallery), 1)
            self.assertEqual(gallery[0]["name"], "NeonSkull")
            self.assertEqual(gallery[0]["file_id"], "group1/M00/01/AAA_neon")

            # Wait for background fetch worker to finish executing under mocked Path
            for t in threading.enumerate():
                if t.name == "DivoomGalleryFetch":
                    t.join(timeout=5.0)

        # R17 P5: the daemon downloads + streams the asset; the GUI delegates
        # via sync_artwork. Wall target because wall_slots is set + no single
        # device is connected.
        fake = MagicMock()
        fake.wall_configure.return_value = {"success": True, "wall": True}
        fake.sync_artwork.return_value = {"success": True}
        self.api._daemon_client = fake
        self.api.wall_slots = {"AA:BB:CC:DD:EE:FF": {"x": 0, "y": 0, "size": 16}}

        artwork_json = json.dumps({"file_id": "9999"})
        sync_success = self.api.batch_sync_artwork(artwork_json)
        self.assertTrue(sync_success)
        fake.sync_artwork.assert_called_once_with("9999", target="wall")

    def test_stock_ticker_apply(self):
        """Test Yahoo Stock ticker downsampling and display coordination pipeline."""
        mock_data = {"price": 105.5, "change": 1.2, "pct_change": 1.15}
        with patch("divoom_lib.utils.media_source.fetch_stock_ticker", return_value=mock_data) as mock_fetch, \
             patch("divoom_lib.utils.media_source.render_stock_ticker_frame", return_value=Path("/tmp/ticker.png")) as mock_render:
            
            # Single connected device path
            self.api.current_divoom = MagicMock()
            self.api.current_divoom.is_connected = True
            self.api.current_divoom.display.show_image = AsyncMock(return_value=True)

            res = self.api.apply_stock_ticker("AAPL")
            res_dict = json.loads(res)
            self.assertTrue(res_dict["success"])
            self.assertEqual(res_dict["price"], 105.5)
            mock_fetch.assert_called_with("AAPL")
            mock_render.assert_called_with("AAPL", mock_data, size=16)

    def test_lan_device_operations(self):
        """Test adding, loading, and deleting LAN devices with mock preset file storage."""
        mock_presets_data = {}
        def mock_read_text(*args, **kwargs):
            return json.dumps(mock_presets_data)
        def mock_write_text(content, *args, **kwargs):
            nonlocal mock_presets_data
            mock_presets_data = json.loads(content)
            return len(content)
            
        with patch("pathlib.Path.exists", return_value=True), \
             patch("pathlib.Path.read_text", side_effect=mock_read_text), \
             patch("pathlib.Path.write_text", side_effect=mock_write_text):
                 
            # Add device
            success = self.api.add_lan_device("192.168.1.100", 123)
            self.assertTrue(success)
            
            # Load devices
            devices_json = self.api.load_lan_devices()
            devices = json.loads(devices_json)
            self.assertEqual(len(devices), 1)
            self.assertEqual(devices[0]["ip"], "192.168.1.100")
            self.assertEqual(devices[0]["token"], 123)
            
            # Delete device
            del_success = self.api.delete_lan_device("192.168.1.100")
            self.assertTrue(del_success)
            
            # Load again to check empty
            devices_json2 = self.api.load_lan_devices()
            self.assertEqual(json.loads(devices_json2), [])

if __name__ == "__main__":
    unittest.main()
