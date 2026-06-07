# gui/gui_api.py

import json
import logging
import asyncio
import sys
import webview
import threading
import time
from pathlib import Path

from divoom_lib.divoom import Divoom
from divoom_lib.wall import DivoomWall
from divoom_lib import divoom_auth

# Import mixins
from presets_manager import PresetsManagerMixin
from media_sync import MediaSyncMixin
from scanner_mixin import ScannerMixin

logger = logging.getLogger("divoom_gui")

class AsyncLoopThread(threading.Thread):
    def __init__(self):
        super().__init__(daemon=True)
        self.loop = asyncio.new_event_loop()
        self.ready = threading.Event()

    def run(self):
        asyncio.set_event_loop(self.loop)
        self.ready.set()
        self.loop.run_forever()

    def stop(self):
        self.loop.call_soon_threadsafe(self.loop.stop)

class DivoomGuiAPI(MediaSyncMixin, PresetsManagerMixin, ScannerMixin):
    """The PyWebView JS api bridge orchestrator."""
    def __init__(self) -> None:
        self.loop_thread = AsyncLoopThread()
        self.loop_thread.start()
        self.loop_thread.ready.wait()

        self.current_divoom = None
        self.discovered_list = []
        self.wall_slots = {}  # "mac" -> {"x": x, "y": y, "width": w, "height": h, "size": size}
        self.wall_instance = None
        self.cached_creds = None
        self.device_pw = 0
        self.device_id = 0
        self.window = None  # Reference to pywebview Window instance

        self.music_sync_active = False
        self.music_thread = None
        self.current_track_cache = None
        self.current_target_mode = "single"

        # Load credentials on startup
        try:
            self.cached_creds = divoom_auth.get_credentials()
        except Exception as e:
            logger.warning(f"Failed to load credentials on startup: {e}")

        # Load virtual device details for gallery API
        device_cache_path = Path.home() / ".config" / "divoom-control" / "virtual_device.json"
        if not device_cache_path.exists():
            device_cache_path = Path(__file__).parent.parent / "api_scraper" / "divoom_docs" / "virtual_device.json"
        if device_cache_path.exists():
            try:
                device_info = json.loads(device_cache_path.read_text(encoding="utf-8"))
                self.device_id = device_info.get("BluetoothDeviceId", 0)
                self.device_pw = device_info.get("DevicePassword", 0)
                logger.info(f"Loaded virtual device: DeviceId={self.device_id}")
            except Exception as e:
                logger.warning(f"Failed to load virtual device: {e}")

    def _run_async(self, coro):
        future = asyncio.run_coroutine_threadsafe(coro, self.loop_thread.loop)
        return future.result()

    def _schedule_async(self, coro) -> None:
        """Fire-and-forget: schedule ``coro`` on the main asyncio loop
        without blocking the caller. Used by the macOS notification
        monitor's polling thread (which must not block on BLE)."""
        asyncio.run_coroutine_threadsafe(coro, self.loop_thread.loop)

    def get_transport_status(self) -> str:
        """Return live status of all four transport layers as JSON."""
        ble_connected = bool(self.current_divoom and self.current_divoom.is_connected)
        lan_ip = self.current_divoom.lan.device_ip if (self.current_divoom and self.current_divoom.lan) else None
        cloud_ok = bool(self.cached_creds and self.cached_creds.is_valid())
        # Note: the GUI's updateTransportPanel (settings.js) reads only
        # ``available`` and ``detail`` from this dict. ``badge`` (emoji)
        # and ``color`` (its hex) were removed in R14 §6; the GUI uses
        # CSS-driven dots via the `transport-dot active/inactive` class.
        return json.dumps({
            "ble": {"available": ble_connected, "label": "Bluetooth", "description": "Bluetooth — 100% local, never leaves your machine.", "detail": self.current_divoom._conn.mac if ble_connected and self.current_divoom else None},
            "lan": {"available": bool(lan_ip), "label": "Local Network", "description": "Local Network — 100% local, WiFi-capable devices only.", "detail": f"{lan_ip}:9000" if lan_ip else "No device IP configured"},
            "cloud": {"available": cloud_ok, "label": "Divoom Cloud", "description": "Divoom Cloud — appin.divoom-gz.com, Divoom's servers, requires account.", "detail": "Authenticated" if cloud_ok else "Not authenticated"},
            "external": {"available": True, "label": "Public Cloud", "description": "Public Cloud — 3rd-party APIs (weather, stocks), no login required.", "detail": "Available"}
        })

    def save_lan_config(self, device_ip: str, local_token: int) -> bool:
        logger.info(f"GUI Action: Saving LAN config ip={device_ip} token={local_token}...")
        try:
            import configparser
            config_file = Path.home() / ".config" / "divoom-control" / "config.ini"
            config_file.parent.mkdir(parents=True, exist_ok=True)
            cfg = configparser.ConfigParser()
            if config_file.exists():
                cfg.read(config_file)
            if "lan" not in cfg:
                cfg["lan"] = {}
            cfg["lan"]["device_ip"] = device_ip
            cfg["lan"]["local_token"] = str(local_token)
            with open(config_file, "w") as f:
                cfg.write(f)

            # Hot-attach to current device if connected
            if self.current_divoom and device_ip:
                from divoom_lib.lan_transport import LanTransport
                self.current_divoom._lan = LanTransport(
                    device_ip=device_ip,
                    local_token=local_token,
                    logger=logger,
                )
            return True
        except Exception as e:
            logger.error(f"Failed to save LAN config: {e}")
            return False

    def probe_lan(self) -> str:
        logger.info("GUI Action: Probing LAN transport reachability...")
        try:
            if not self.current_divoom or not self.current_divoom.lan:
                return json.dumps({"reachable": False, "detail": "No LAN IP configured. Save a device IP first."})
            ok = self._run_async(self.current_divoom.lan.probe())
            ip = self.current_divoom.lan.device_ip
            return json.dumps({
                "reachable": ok,
                "detail": f"{' Connected' if ok else ' Unreachable'} — {ip}:9000",
            })
        except Exception as e:
            return json.dumps({"reachable": False, "detail": str(e)})

    def minimize_window(self) -> None:
        if self.window:
            self.window.minimize()

    def maximize_window(self) -> None:
        if self.window:
            self.window.toggle_fullscreen()

    def close_window(self) -> None:
        if hasattr(self, "loop_thread"):
            self.loop_thread.stop()
        if self.window:
            def _destroy():
                time.sleep(0.1)
                self.window.destroy()
            threading.Thread(target=_destroy, daemon=True).start()

    def set_solid_light(self, color: str, brightness: int, mode_type: int = 0) -> bool:
        logger.info(f"GUI Action: Applying solid light {color} (brightness={brightness}, mode_type={mode_type})...")
        try:
            if getattr(self, "current_target_mode", "single") == "wall":
                if not self._rebuild_wall_instance():
                    return False
                return self._run_async(self.wall_instance.set_light(color, brightness))
            elif self.current_divoom:
                return self._run_async(self.current_divoom.display.show_light(color, brightness, True, mode_type))
            return False
        except Exception as e:
            logger.error(f"Light setting failed: {e}")
            return False

    def set_clock(self, style: int, color: str = None) -> bool:
        logger.info(f"GUI Action: Applying clock style {style} with color {color}...")
        try:
            if getattr(self, "current_target_mode", "single") == "wall":
                if not self._rebuild_wall_instance():
                    return False
                return self._run_async(self.wall_instance.show_clock(clock=style))
            elif self.current_divoom:
                return self._run_async(self.current_divoom.display.show_clock(clock=style, color=color))
            return False
        except Exception as e:
            logger.error(f"Clock setting failed: {e}")
            return False

    def switch_channel(self, channel: str) -> bool:
        logger.info(f"GUI Action: Switching channel to {channel}...")
        try:
            if getattr(self, "current_target_mode", "single") == "wall":
                if not self._rebuild_wall_instance():
                    return False
                tasks = []
                for divoom, _, _, _, _, _ in self.wall_instance.devices:
                    tasks.append(divoom.display.switch_channel(channel))
                
                async def run_switch():
                    results = await asyncio.gather(*tasks, return_exceptions=True)
                    return all(res is True or isinstance(res, dict) for res in results)
                
                return self._run_async(run_switch())

            target = self.current_divoom
            if not target:
                return False
            return self._run_async(target.display.switch_channel(channel))
        except Exception as e:
            logger.error(f"Channel switch failed: {e}")
            return False

    def set_vj_effect(self, number: int) -> bool:
        logger.info(f"GUI Action: Applying VJ effect {number}...")
        try:
            if getattr(self, "current_target_mode", "single") == "wall":
                if not self._rebuild_wall_instance():
                    return False
                return self._run_async(self.wall_instance.show_effects(number=int(number)))
            target = self.current_divoom
            if not target:
                return False
            return self._run_async(target.display.show_effects(number=int(number)))
        except Exception as e:
            logger.error(f"VJ effect failed: {e}")
            return False

    def set_visualization(self, number: int) -> bool:
        logger.info(f"GUI Action: Applying visualizer {number}...")
        try:
            if getattr(self, "current_target_mode", "single") == "wall":
                if not self._rebuild_wall_instance():
                    return False
                return self._run_async(self.wall_instance.show_visualization(number=int(number)))
            target = self.current_divoom
            if not target:
                return False
            return self._run_async(target.display.show_visualization(number=int(number)))
        except Exception as e:
            logger.error(f"Visualizer failed: {e}")
            return False

    def push_text(self, text: str, color: str = "#FFFFFF", font_size: int = 1,
                  speed: int = 50, effect_style: int = 1) -> bool:
        """Round 7 — Text Channel: type & push scrolling text to the device.

        Runs the full LPWA (0x87) sequence: display-box → font → color → speed →
        effect → content. effect_style: 0 static, 1 scroll-left, 2 scroll-up,
        3 hold, 4 marquee (device-dependent)."""
        logger.info(f"GUI Action: Push text {text!r} (color={color}, speed={speed}, effect={effect_style})...")
        from divoom_lib.models import (
            LPWA_CONTROL_DISPLAY_BOX, LPWA_CONTROL_FONT, LPWA_CONTROL_COLOR,
            LPWA_CONTROL_SPEED, LPWA_CONTROL_EFFECTS, LPWA_CONTROL_CONTENT,
        )

        async def _push(divoom, size: int) -> bool:
            t = divoom.text
            box = 0
            await t.set_light_phone_word_attr(LPWA_CONTROL_DISPLAY_BOX, x=0, y=0,
                                              width=size, height=size, text_box_id=box)
            await t.set_light_phone_word_attr(LPWA_CONTROL_FONT, font_size=int(font_size), text_box_id=box)
            await t.set_light_phone_word_attr(LPWA_CONTROL_COLOR, color=color, text_box_id=box)
            await t.set_light_phone_word_attr(LPWA_CONTROL_SPEED, speed=int(speed), text_box_id=box)
            await t.set_light_phone_word_attr(LPWA_CONTROL_EFFECTS, effect_style=int(effect_style))
            res = await t.set_light_phone_word_attr(LPWA_CONTROL_CONTENT, text_content=str(text), text_box_id=box)
            return res is not False

        try:
            if not text or not str(text).strip():
                return False
            if getattr(self, "current_target_mode", "single") == "wall":
                if not self._rebuild_wall_instance():
                    return False

                async def run_all():
                    results = []
                    for entry in self.wall_instance.devices:
                        divoom = entry[0]
                        sz = entry[3] if len(entry) > 3 else 16
                        results.append(await _push(divoom, int(sz)))
                    return all(results)
                return self._run_async(run_all())

            target = self.current_divoom
            if not target:
                return False
            size = self._active_device_size() if hasattr(self, "_active_device_size") else 16
            return self._run_async(_push(target, int(size)))
        except Exception as e:
            logger.error(f"push_text failed: {e}")
            return False

    # ── Round 7: Alarms (scheduling/alarm.py, 0x42/0x43) ──────────────────

    def get_alarms(self) -> str:
        """Read the device's 10 alarm slots as JSON. May be empty if the device
        doesn't answer the 0x42 query (see read-back limitation)."""
        try:
            target = self.current_divoom
            if not target:
                return json.dumps([])
            alarms = self._run_async(target.alarm.get_alarm_time())
            return json.dumps(alarms or [])
        except Exception as e:
            logger.error(f"get_alarms failed: {e}")
            return json.dumps([])

    def set_alarm(self, index: int, enabled, hour: int, minute: int,
                  week: int = 0, mode: int = 0, trigger_mode: int = 0) -> bool:
        """Set one alarm slot (0x43). `week` is a 7-bit weekday mask (bit0=Mon)."""
        logger.info(f"GUI Action: Set alarm {index} {int(hour):02d}:{int(minute):02d} "
                    f"enabled={enabled} week={week}...")
        try:
            status = 1 if (enabled in (True, 1, "1", "true", "True")) else 0
            target = self.current_divoom
            if not target:
                return False
            return bool(self._run_async(target.alarm.set_alarm(
                int(index), status, int(hour), int(minute), int(week),
                int(mode), int(trigger_mode))))
        except Exception as e:
            logger.error(f"set_alarm failed: {e}")
            return False

    # ── Round 7: Sleep Aid (scheduling/sleep.py) ──────────────────────────

    def start_sleep(self, minutes: int = 30, color: str = "#2040ff", volume: int = 10) -> bool:
        """Begin the sleep fade: dim to `color` over `minutes`, at `volume`."""
        logger.info(f"GUI Action: Start sleep {minutes}min color={color} vol={volume}...")
        try:
            target = self.current_divoom
            if not target:
                return False
            from divoom_lib.utils.converters import color_to_rgb_list
            rgb = color_to_rgb_list(color)
            return bool(self._run_async(target.sleep.show_sleep(
                sleeptime=int(minutes), volume=int(volume), color=rgb, on=1)))
        except Exception as e:
            logger.error(f"start_sleep failed: {e}")
            return False

    def stop_sleep(self) -> bool:
        logger.info("GUI Action: Stop sleep...")
        try:
            target = self.current_divoom
            if not target:
                return False
            return bool(self._run_async(target.sleep.show_sleep(on=0)))
        except Exception as e:
            logger.error(f"stop_sleep failed: {e}")
            return False

    # ── Round 7: Tools — timer / countdown / noise (tools/*) ──────────────

    def set_timer(self, action: str = "start") -> bool:
        """Stopwatch control: action in {start, stop, reset}."""
        from divoom_lib.models import (
            STI_CTRL_FLAG_TIMER_STARTED, STI_CTRL_FLAG_TIMER_PAUSED, STI_CTRL_FLAG_TIMER_RESET)
        flag = {"start": STI_CTRL_FLAG_TIMER_STARTED, "stop": STI_CTRL_FLAG_TIMER_PAUSED,
                "reset": STI_CTRL_FLAG_TIMER_RESET}.get(action, STI_CTRL_FLAG_TIMER_STARTED)
        return self._tool_call(lambda d: d.timer.set_timer(flag), f"timer {action}")

    def set_countdown(self, action: str = "start", minutes: int = 5, seconds: int = 0) -> bool:
        """Countdown control: action in {start, stop}."""
        from divoom_lib.models import STI_CTRL_FLAG_COUNTDOWN_START, STI_CTRL_FLAG_COUNTDOWN_CANCEL
        flag = STI_CTRL_FLAG_COUNTDOWN_CANCEL if action == "stop" else STI_CTRL_FLAG_COUNTDOWN_START
        return self._tool_call(lambda d: d.countdown.set_countdown(flag, int(minutes), int(seconds)),
                               f"countdown {action} {minutes}:{seconds}")

    def set_noise(self, action: str = "start") -> bool:
        """Noise meter control: action in {start, stop}."""
        from divoom_lib.models import STI_CTRL_FLAG_NOISE_START, STI_CTRL_FLAG_NOISE_STOP
        flag = STI_CTRL_FLAG_NOISE_STOP if action == "stop" else STI_CTRL_FLAG_NOISE_START
        return self._tool_call(lambda d: d.noise.set_noise(flag), f"noise {action}")

    def _tool_call(self, fn, label: str) -> bool:
        logger.info(f"GUI Action: Tool {label}...")
        try:
            target = self.current_divoom
            if not target:
                return False
            return bool(self._run_async(fn(target)))
        except Exception as e:
            logger.error(f"tool {label} failed: {e}")
            return False

    # ── Round 8: Device settings / FM / weather / memorial / timeplan ─────
    # All are one-shot SET commands routed through the single active device.

    @staticmethod
    def _as_bool(v) -> bool:
        return v in (True, 1, "1", "true", "True", "on", "yes")

    def set_hour_type(self, is_24h) -> bool:
        """12/24-hour clock format (0x2c)."""
        return self._tool_call(lambda d: d.system.set_hour_type(1 if self._as_bool(is_24h) else 0), "hour type")

    def set_temp_unit(self, fahrenheit) -> bool:
        """Temperature unit °C/°F (0x2b)."""
        return self._tool_call(lambda d: d.device.set_temp_type(1 if self._as_bool(fahrenheit) else 0), "temp unit")

    def sync_time(self) -> bool:
        """Push the host clock to the device (0x18)."""
        from divoom_lib.system.date_time import DateTimeCommand
        return self._tool_call(lambda d: DateTimeCommand(d).update_date_time(), "time sync")

    def set_device_name(self, name: str) -> bool:
        return self._tool_call(lambda d: d.device.set_device_name(str(name)), "device name")

    def set_auto_power_off(self, minutes: int) -> bool:
        from divoom_lib.system.device_settings import DeviceSettings
        return self._tool_call(lambda d: DeviceSettings(d).set_auto_power_off(int(minutes)), "auto power off")

    def set_low_power(self, on) -> bool:
        from divoom_lib.system.device_settings import DeviceSettings
        return self._tool_call(lambda d: DeviceSettings(d).set_low_power_switch(1 if self._as_bool(on) else 0), "low power")

    def push_weather(self) -> bool:
        """Push current weather to the device's weather widget.

        R15 §3: pulls live weather from the configured provider, then
        writes the resulting temperature + icon to the device via
        ``divoom.weather.set``. The legacy TempWeatherCommand shim is
        no longer used in this path — the new Weather class is the
        canonical source of truth (R14 §1)."""
        from divoom_lib.system.weather import Weather
        from divoom_lib.weather_provider import get_weather

        async def _push(d):
            info = await get_weather()
            return await Weather(d).set(info.temperature_c, info.weather_type)

        return self._tool_call(_push, "weather")

    def get_weather(self) -> dict:
        """Return the current weather as a dict for the Live Widgets
        card to render. Shape::

            {
                "temperature_c": int,
                "weather_type": int,    # divoom WeatherType enum value
                "location": str,
                "provider": str,        # "wttr_in" | "stub"
                "fetched_at": float,    # unix epoch seconds
            }

        Never raises — falls back to StubProvider on any error.
        Uses a private event loop because the GUI's loop thread is
        for device-bound work; weather fetches don't need a device."""
        from divoom_lib.weather_provider import get_weather
        from divoom_lib.models import WeatherType
        import asyncio

        async def _gather():
            info = await get_weather()
            return {
                "temperature_c": info.temperature_c,
                "weather_type": info.weather_type,
                "location": info.location,
                "provider": info.provider,
                "fetched_at": info.fetched_at,
            }

        try:
            return asyncio.run(_gather())
        except Exception as exc:  # last-ditch: never break the UI
            logger.warning("get_weather failed: %s", exc)
            return {
                "temperature_c": 0,
                "weather_type": int(WeatherType.Clear),
                "location": "error",
                "provider": "stub",
                "fetched_at": 0.0,
                "error": str(exc),
            }

    def set_fm_frequency(self, freq_x10: int) -> bool:
        """Tune the FM radio. freq_x10 = MHz×10 (e.g. 875 = 87.5 MHz)."""
        return self._tool_call(lambda d: d.radio.set_radio_frequency(int(freq_x10)), "fm")

    def set_memorial(self, index, enabled, month, day, hour, minute, title="") -> bool:
        """Anniversary/memorial countdown slot (0x54)."""
        on = 1 if self._as_bool(enabled) else 0
        have = 1 if title else 0
        return self._tool_call(
            lambda d: d.alarm.set_memorial_time(int(index), on, int(month), int(day),
                                                int(hour), int(minute), have, str(title)),
            "memorial")

    def set_timeplan(self, index, enabled, hour, minute, week=0, channel=0) -> bool:
        """Scheduled time-plan slot: at hour:minute on weekdays `week`, switch to
        `channel` (0x56). Basic mapping; mode=channel, defaults for the rest."""
        status = 1 if self._as_bool(enabled) else 0
        return self._tool_call(
            lambda d: d.timeplan.set_time_manage_info(status, int(hour), int(minute),
                                                      int(week), int(channel), 0, 0, 10, 0),
            "timeplan")

    # ── Round 9: display orientation + factory reset (0xBD EXT) ──────────
    # (Brightness already has a full LAN/multi-target bridge — see set_brightness
    #  below + the appbar slider; not re-added here.)
    def set_screen_dir(self, direction) -> bool:
        """Rotate the display (0xBD 0x23). direction = 0..3 (0/90/180/270°)."""
        return self._tool_call(lambda d: d.design.set_screen_dir(int(direction)),
                               "screen direction")

    def set_screen_mirror(self, on) -> bool:
        """Mirror/flip the display (0xBD 0x24)."""
        return self._tool_call(lambda d: d.design.set_screen_mirror(self._as_bool(on)),
                               "screen mirror")

    def factory_reset(self, confirm="") -> bool:
        """Factory-reset the device (0xBD 0x25). DESTRUCTIVE — refuses unless the
        caller passes the literal token "RESET" (belt-and-suspenders behind the
        UI double-confirm). Never invoked implicitly."""
        if str(confirm) != "RESET":
            logger.warning("factory_reset refused: missing/invalid confirm token")
            return False
        return self._tool_call(lambda d: d.design.factory_reset(), "factory reset")

    # ── Round 10: notification mirroring (SPP_SET_ANDROID_ANCS, 0x50) ─────
    def send_notification(self, app_type, text="") -> bool:
        """Manually trigger the device's notification display for an app type
        (1-14, see NOTIFICATION_APPS). With text → icon+text form; else icon."""
        t = int(app_type)
        if not (1 <= t <= 14):
            logger.warning(f"send_notification: app_type {t} out of range 1-14")
            return False
        msg = str(text or "").strip()
        if msg:
            return self._tool_call(
                lambda d: d.notification.show_notification_text(t, msg),
                "notification")
        return self._tool_call(
            lambda d: d.notification.show_notification(t), "notification")

    # ── Round 13 §3: macOS notification mirroring ────────────────────────
    # The monitor runs in a daemon thread that polls the macOS Notification
    # Center SQLite DB. The sink callback (called on the polling thread)
    # schedules the BLE send on the main asyncio loop via _schedule_async
    # so the polling thread never blocks on BLE roundtrips.

    def _notification_monitor(self):
        """Lazy accessor for the macOS monitor singleton. Imports
        ``gui.macos_notifications`` lazily so non-macOS hosts don't
        fail to import this module."""
        if not hasattr(self, "_mac_monitor") or self._mac_monitor is None:
            from gui.macos_notifications import MacAppRouter, MacNotificationMonitor
            router = MacAppRouter()
            self._mac_monitor = MacNotificationMonitor(router=router, poll_interval=1.0)
        return self._mac_monitor

    def _notification_sink(self, app_type: int, title: str, body: str) -> None:
        """Sink for the monitor. Truncates to a single line of text and
        schedules a fire-and-forget BLE send."""
        text = (title or body or "").strip().splitlines()[0] if (title or body) else ""
        self._schedule_async(self._send_notification_async(app_type, text))

    async def _send_notification_async(self, app_type: int, text: str) -> None:
        """Coroutines run on the main loop. Logs + sends; ignores failures
        (we'd rather drop a notification than back up the polling thread)."""
        d = self.current_divoom
        if d is None or not d.is_connected:
            return
        try:
            if text:
                await d.notification.show_notification_text(int(app_type), text)
            else:
                await d.notification.show_notification(int(app_type))
        except Exception as e:
            logger.debug(f"_send_notification_async: {e}")

    def _push_menubar_status(self, status: dict) -> dict:
        """Best-effort, event-driven push of the listener status to the menubar
        agent over its Unix socket (R15 §6 — the menubar does NOT poll). Returns
        `status` unchanged so callers can ``return self._push_menubar_status(...)``.
        Silent no-op if the menubar agent isn't running."""
        try:
            from gui.menubar_status import derive_state, push_notification_status
            push_notification_status(derive_state(status), status.get("counters"))
        except Exception as e:
            logger.debug(f"menubar status push skipped: {e}")
        return status

    def start_notification_listener(self) -> dict:
        """Start polling the macOS Notification Center DB. Returns a
        status dict for the JS side (``{running, db_path, error?}``).
        Safe to call multiple times; no-op if already running."""
        if sys.platform != "darwin":
            return self._push_menubar_status({"running": False, "error": "macOS only"})
        try:
            monitor = self._notification_monitor()
            if monitor.is_running:
                return self._push_menubar_status({"running": True, "db_path": str(monitor.db_path)})
            monitor.start(sink=self._notification_sink)
            return self._push_menubar_status({"running": True, "db_path": str(monitor.db_path)})
        except FileNotFoundError as e:
            logger.warning(f"start_notification_listener: {e}")
            return self._push_menubar_status({"running": False, "error": str(e)})
        except Exception as e:
            logger.exception(f"start_notification_listener: {e}")
            return self._push_menubar_status({"running": False, "error": str(e)})

    def stop_notification_listener(self) -> dict:
        """Stop the polling thread. No-op if not running."""
        if not hasattr(self, "_mac_monitor") or self._mac_monitor is None:
            return self._push_menubar_status({"running": False})
        self._mac_monitor.stop()
        return self._push_menubar_status({"running": False})

    def is_notification_listener_running(self) -> bool:
        if not hasattr(self, "_mac_monitor") or self._mac_monitor is None:
            return False
        return self._mac_monitor.is_running

    def get_notification_listener_status(self) -> dict:
        """Rich status snapshot for the Settings → Devices card.

        Returns a dict the JS side can render directly::

            {
              "platform_supported": bool,    # False on non-darwin
              "running": bool,
              "db_path": str | None,         # macOS Notification Center DB
              "routing_path": str,           # ~/.config/divoom-control/...
              "rules": [[substr, app_type], ...],
              "counters": {"seen": int, "routed": int, "dropped": int},
              "error": str | None,
            }
        """
        from gui.macos_notifications import ROUTING_PATH, load_routing_table
        if sys.platform != "darwin":
            return {
                "platform_supported": False,
                "running": False,
                "db_path": None,
                "routing_path": str(ROUTING_PATH),
                "rules": [list(r) for r in load_routing_table()],
                "counters": {"seen": 0, "routed": 0, "dropped": 0},
                "error": "macOS notifications are only supported on macOS",
            }
        monitor = self._notification_monitor()
        rules = [list(r) for r in monitor._router.rules]
        return {
            "platform_supported": True,
            "running": monitor.is_running,
            "db_path": str(monitor.db_path) if monitor.db_path else None,
            "routing_path": str(ROUTING_PATH),
            "rules": rules,
            "counters": {
                "seen":    monitor.records_seen,
                "routed":  monitor.records_routed,
                "dropped": monitor.records_dropped,
            },
            "error": None,
        }

    def save_notification_routing(self, json_text: str) -> dict:
        """Save a user-edited routing table. Persists to disk and
        hot-reloads the running monitor's router (no listener restart
        required).

        Returns ``{"rules": [[substr, app_type], ...], "error": str|None}``.

        On parse / validation error, returns the *previous* rule list
        unchanged and a non-null ``error`` string — the GUI shows the
        error and keeps the user's draft.
        """
        from gui.macos_notifications import (
            ROUTING_PATH, load_routing_table, save_routing_table,
        )
        import json as _json
        try:
            parsed = _json.loads(json_text) if json_text.strip() else []
        except _json.JSONDecodeError as e:
            return {"rules": [list(r) for r in load_routing_table()], "error": f"Invalid JSON: {e}"}
        try:
            path = save_routing_table(
                [(s, int(t)) for s, t in parsed], path=ROUTING_PATH
            )
        except (ValueError, TypeError) as e:
            return {
                "rules": [list(r) for r in load_routing_table()],
                "error": f"Invalid routing entries: {e}",
            }
        # Hot-reload the running monitor's router.
        monitor = self._notification_monitor()
        from gui.macos_notifications import MacAppRouter
        monitor._router = MacAppRouter.from_file(path)
        logger.info(f"save_notification_routing: saved {len(parsed)} rules to {path}")
        return {
            "rules": [list(r) for r in load_routing_table(path)],
            "error": None,
        }

    def display_wall_image(self, file_path: str, cell_size: int) -> bool:
        logger.info(f"GUI Action: Push display wall asset {file_path!r} (cell size={cell_size})...")
        try:
            if not self._rebuild_wall_instance(cell_size):
                return False
            return self._run_async(self.wall_instance.show_image(file_path))
        except Exception as e:
            logger.error(f"Wall display failed: {e}")
            return False

    def open_file_dialog(self) -> str | None:
        logger.info("Opening native file dialog...")
        try:
            if not self.window:
                logger.error("No webview window reference available.")
                return None
            
            file_types = ('Image files (*.png;*.jpg;*.jpeg;*.gif)', 'All files (*.*)')
            result = self.window.create_file_dialog(
                webview.OPEN_DIALOG,
                allow_multiple=False,
                file_types=file_types
            )
            
            if result and len(result) > 0:
                logger.info(f"Selected file: {result[0]}")
                return result[0]
            return None
        except Exception as e:
            logger.error(f"Error opening file dialog: {e}")
            return None

    def set_brightness(self, brightness: int) -> bool:
        logger.info(f"GUI Action: Setting brightness to {brightness}...")
        try:
            val = int(brightness)
            if getattr(self, "current_target_mode", "single") == "wall":
                if not self._rebuild_wall_instance():
                    return False
                tasks = []
                for divoom, _, _, _, _, _ in self.wall_instance.devices:
                    if divoom.lan:
                        tasks.append(divoom.lan.set_brightness(val))
                    else:
                        tasks.append(divoom.device.set_brightness(val))

                async def run_brightness():
                    results = await asyncio.gather(*tasks, return_exceptions=True)
                    return all(res is True or isinstance(res, dict) for res in results)

                return self._run_async(run_brightness())

            target = self.current_divoom
            if not target:
                return False
            if target.lan:
                return self._run_async(target.lan.set_brightness(val))
            else:
                return self._run_async(target.device.set_brightness(val))
        except Exception as e:
            logger.error(f"Brightness setting failed: {e}")
            return False

    def get_brightness(self) -> int | None:
        """Read the device's current brightness (0-100). Returns None on failure.

        New in Round 7 (docs/PLANNING_ROUND7.md §3). Used by the appbar
        brightness slider to initialize to the actual device value on
        startup, matching the volume-slider pattern from Round 6.

        Wire: 0x46 get light mode (parsed by divoom_lib.device.get_brightness).
        LAN devices return a dict from the LAN transport; we extract the
        'brightness' field if present, else fall back to None.
        """
        logger.info("GUI Action: Getting current brightness...")
        try:
            target = self.current_divoom
            if not target:
                return None
            return self._run_async(target.device.get_brightness())
        except Exception as e:
            logger.error(f"Brightness get failed: {e}")
            return None

    def get_work_mode(self) -> int | None:
        """Read the device's current work mode (0-15). Returns None on failure.

        New in Round 7. Used by the Control Panel to highlight the
        channel card that matches the device's currently-active channel.
        Wire: 0x13 get work mode. Returns the work mode integer
        (0=clock, 1=lightning, 2=cloud, 3=vj, 4=visualizer, 5=design,
        6=scoreboard, 7=animation, etc.).
        """
        logger.info("GUI Action: Getting current work mode...")
        try:
            target = self.current_divoom
            if not target:
                return None
            return self._run_async(target.device.get_work_mode())
        except Exception as e:
            logger.error(f"Work mode get failed: {e}")
            return None

    def get_scoreboard_state(self) -> dict | None:
        """Read the current scoreboard state from the device.

        New in Round 7. Returns a dict with `on_off`, `red_score`,
        `blue_score` keys, or None on failure. Used by the scoreboard
        panel to initialize the red/blue inputs to the actual device
        state (matching the volume/brightness slider patterns).

        Wire: 0x71 0x04 (get tool info, TOOL_TYPE_SCORE).
        """
        logger.info("GUI Action: Getting current scoreboard state...")
        try:
            target = self.current_divoom
            if not target:
                return None
            return self._run_async(target.scoreboard.get_scoreboard())
        except Exception as e:
            logger.error(f"Scoreboard get failed: {e}")
            return None

    def set_volume(self, volume: int) -> bool:
        """Set the device volume (0-15).

        New in Round 6 (docs/PLANNING_ROUND5.md §6.1). The wire command
        is 0x08 set volume. Validated to 0-15; out-of-range is clamped.
        """
        logger.info(f"GUI Action: Setting volume to {volume}...")
        try:
            val = max(0, min(15, int(volume)))
            if getattr(self, "current_target_mode", "single") == "wall":
                if not self._rebuild_wall_instance():
                    return False
                tasks = []
                for divoom, _, _, _, _, _ in self.wall_instance.devices:
                    tasks.append(divoom.music.set_volume(val))

                async def run_volume():
                    results = await asyncio.gather(*tasks, return_exceptions=True)
                    return all(res is True for res in results)

                return self._run_async(run_volume())

            target = self.current_divoom
            if not target:
                return False
            return self._run_async(target.music.set_volume(val))
        except Exception as e:
            logger.error(f"Volume setting failed: {e}")
            return False

    def get_volume(self) -> int | None:
        """Read the device volume (0-15). Returns None on failure.

        New in Round 6. Used by the appbar volume slider to initialize
        to the actual device value on startup. Wire command is 0x09
        get volume.
        """
        logger.info("GUI Action: Getting current volume...")
        try:
            target = self.current_divoom
            if not target:
                return None
            return self._run_async(target.music.get_volume())
        except Exception as e:
            logger.error(f"Volume get failed: {e}")
            return None

    def set_scoreboard(self, on_off: int, red: int = 0, blue: int = 0) -> bool:
        """Set the scoreboard tool (0x72 set tool, TOOL_TYPE_SCORE).

        New in Round 6 (docs/PLANNING_ROUND5.md §6.1). The scoreboard
        is a tool, not a channel — it has its own panel in the Control
        Center and its own show/hide buttons. Wire details in
        divoom_lib/tools/scoreboard.py.
        """
        logger.info(f"GUI Action: Setting scoreboard on_off={on_off} red={red} blue={blue}...")
        try:
            target = self.current_divoom
            if not target:
                return False
            return self._run_async(target.scoreboard.set_scoreboard(int(on_off), int(red), int(blue)))
        except Exception as e:
            logger.error(f"Scoreboard set failed: {e}")
            return False

    def display_custom_art(self, file_path: str) -> bool:
        logger.info(f"GUI Action: Pushing custom art {file_path!r}...")
        try:
            if getattr(self, "current_target_mode", "single") == "wall":
                if not self._rebuild_wall_instance():
                    return False
                return self._run_async(self.wall_instance.show_image(file_path))

            target = self.current_divoom
            if not target:
                return False
            return self._run_async(target.display.show_image(file_path))
        except Exception as e:
            logger.error(f"Failed to display custom art: {e}")
            return False

    # ── Round 15 §5: MCP server subprocess control ────────────────────
    #
    # The GUI spawns ``python -m divoom_lib.cli mcp-server --mac <MAC>``
    # as a subprocess and tracks it via MCPController. pywebview's
    # event loop and the MCP server's stdio loop would otherwise fight
    # over file descriptors — subprocess isolation is the clean fix.

    def start_mcp_server(self, mac: str = "") -> dict:
        """Start the MCP stdio server subprocess (R15 §5).

        ``mac`` is optional; falls back to the active device's MAC if
        empty. Returns a status dict (see ``mcp_server_status()``)."""
        from gui.mcp_control import MCPController, status_to_dict
        ctl = MCPController.instance()
        target_mac = mac or (self.current_divoom.mac if self.current_divoom else "")
        if not target_mac:
            return status_to_dict(ctl.status()) | {"error": "no MAC available"}
        return status_to_dict(ctl.start(mac=target_mac))

    def stop_mcp_server(self) -> dict:
        """Stop the MCP server subprocess (no-op if not running)."""
        from gui.mcp_control import MCPController, status_to_dict
        ctl = MCPController.instance()
        return status_to_dict(ctl.stop())

    def is_mcp_server_running(self) -> bool:
        """True if the subprocess is alive."""
        from gui.mcp_control import MCPController
        return MCPController.instance().is_running()

    def mcp_server_status(self) -> dict:
        """Snapshot of the subprocess state (JSON-friendly)."""
        from gui.mcp_control import MCPController, status_to_dict
        return status_to_dict(MCPController.instance().status())
