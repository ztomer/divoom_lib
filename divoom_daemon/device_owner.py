"""Device ownership for the Divoom daemon — single BLE/LAN device + wall lifecycle."""
from __future__ import annotations

import base64
import logging
import os
import tempfile
import threading
from pathlib import Path
from typing import Callable, Optional

logger = logging.getLogger("divoom_daemon.device_owner")


def _json_safe(value):
    """Coerce a value to something JSON-serializable."""
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, (list, tuple)):
        return [_json_safe(v) for v in value]
    if isinstance(value, dict):
        return {str(k): _json_safe(v) for k, v in value.items()}
    if isinstance(value, (bytes, bytearray)):
        return list(value)
    return str(value)


class DeviceOwner:
    """Single owner of the BLE/LAN device connection and wall (R17 P5).
    Provides command handlers for device lifecycle and a send_notification
    method used by NotificationService."""

    def __init__(
        self,
        mac: Optional[str] = None,
        *,
        device=None,
        device_sender: Optional[Callable[[int, str], None]] = None,
    ):
        self.mac = mac
        self._device_sender = device_sender
        self._device = device                   # injectable (tests); else lazy BLE
        self._device_lock = threading.Lock()
        self._loop = None                       # dedicated asyncio loop for device ops
        self._loop_thread = None
        self._lan_ip: Optional[str] = None
        self._wall = None                       # DivoomWall (multi-device)
        self._wall_slots: dict = {}

    # ── device loop ──────────────────────────────────────────────────────
    def _device_loop(self):
        """A dedicated asyncio loop so the BLE connection persists across calls."""
        with self._device_lock:
            if self._loop is not None:
                return self._loop
            import asyncio
            loop = asyncio.new_event_loop()
            ready = threading.Event()

            def _run():
                asyncio.set_event_loop(loop)
                ready.set()
                loop.run_forever()

            self._loop_thread = threading.Thread(target=_run, daemon=True, name="device-loop")
            self._loop_thread.start()
            ready.wait(2.0)
            self._loop = loop
            return self._loop

    def _run_device(self, coro):
        """Run a coroutine on the persistent device loop, blocking for the result."""
        import asyncio
        loop = self._device_loop()
        return asyncio.run_coroutine_threadsafe(coro, loop).result()

    def _device_connected(self) -> bool:
        d = self._device
        return bool(d is not None and getattr(d, "is_connected", False))

    async def _ensure_device_async(self, mac: Optional[str] = None):
        if self._device is not None:
            if not getattr(self._device, "is_connected", False) and hasattr(self._device, "connect"):
                try:
                    await self._device.connect()
                except Exception:
                    pass
            return self._device
        from divoom_lib.divoom import Divoom
        from divoom_lib.utils import discovery
        target = mac or self.mac
        if not target:
            devs = await discovery.discover_all_divoom_devices(timeout=3.0)
            if not devs:
                raise RuntimeError("no Divoom device found")
            target = devs[0]["address"]
            self.mac = target
        self._device = Divoom(mac=target, logger=logger, use_ios_le_protocol=False)
        await self._device.connect()
        return self._device

    async def _build_device_async(self, args: dict):
        if self._device is not None:
            if not getattr(self._device, "is_connected", False) and hasattr(self._device, "connect"):
                try:
                    await self._device.connect()
                except Exception:
                    pass
            return self._device
        from divoom_lib.divoom import Divoom
        lan_ip = args.get("lan_ip")
        if lan_ip:
            from divoom_lib.lan_transport import LanTransport
            token = int(args.get("lan_token", 0) or 0)
            dev = Divoom(mac=None, lan_ip=lan_ip, lan_token=token, logger=logger)
            dev._lan = LanTransport(device_ip=lan_ip, local_token=token, logger=logger)
            if not await dev._lan.probe():
                raise RuntimeError(f"LAN device at {lan_ip} unreachable")
            self._device = dev
            self._lan_ip = lan_ip
            return dev
        mac = args.get("mac")
        if not mac:
            return await self._ensure_device_async(None)
        self._device = Divoom(
            mac=mac, logger=logger,
            use_ios_le_protocol=bool(args.get("use_ios_le_protocol", True)),
            device_name=args.get("device_name"),
        )
        await self._device.connect()
        self.mac = mac
        return self._device

    def _status_fields(self) -> dict:
        d = self._device
        return {
            "connected": self._device_connected(),
            "mac": self.mac,
            "lan_ip": self._lan_ip,
            "wall": self._wall is not None,
        }

    # ── notification sender (for NotificationService) ────────────────────
    def send_notification(self, app_type: int, text: str) -> None:
        if self._device_sender is not None:
            self._device_sender(app_type, text)
            return
        self._send_to_device_ble(app_type, text)

    def _send_to_device_ble(self, app_type: int, text: str) -> None:
        import asyncio
        from divoom_lib.divoom import Divoom
        from divoom_lib.utils import discovery

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            if not getattr(self, "_device", None) or not self._device.is_connected:
                mac = self.mac
                if not mac:
                    devs = loop.run_until_complete(discovery.discover_all_divoom_devices(timeout=3.0))
                    if not devs:
                        return
                    mac = devs[0]["address"]
                self._device = Divoom(mac=mac, logger=logger, use_ios_le_protocol=False)
                loop.run_until_complete(self._device.connect())
            if text:
                loop.run_until_complete(self._device.notification.show_notification_text(int(app_type), text))
            else:
                loop.run_until_complete(self._device.notification.show_notification(int(app_type)))
        finally:
            loop.close()

    # ── command handlers ─────────────────────────────────────────────────
    def device_call(self, args: dict) -> dict:
        method = args.get("method")
        call_args = list(args.get("args", []) or [])
        call_kwargs = args.get("kwargs", {}) or {}
        which = args.get("target", "device")
        if not method:
            return {"success": False, "error": "device_call requires 'method'"}

        for idx_str, b64 in (args.get("blobs") or {}).items():
            try:
                idx = int(idx_str)
                data = base64.b64decode(b64)
                suffix = Path(str(call_args[idx])).suffix if idx < len(call_args) and call_args[idx] else ".bin"
                fd, tmp_path = tempfile.mkstemp(prefix="divoom_blob_", suffix=suffix or ".bin")
                with os.fdopen(fd, "wb") as f:
                    f.write(data)
                if idx < len(call_args):
                    call_args[idx] = tmp_path
                else:
                    call_args.append(tmp_path)
            except (ValueError, TypeError, IndexError) as e:
                return {"success": False, "error": f"bad blob {idx_str}: {e}"}

        async def _do():
            if which == "wall":
                base = self._wall
                if base is None:
                    raise RuntimeError("no wall configured")
            else:
                base = await self._ensure_device_async(args.get("mac"))
            target = base
            for part in str(method).split("."):
                target = getattr(target, part)
            result = target(*call_args, **call_kwargs)
            if hasattr(result, "__await__"):
                result = await result
            return result

        try:
            result = self._run_device(_do())
            return {"success": True, "result": _json_safe(result)}
        except Exception as e:
            logger.warning(f"device_call {which}.{method} failed: {e}")
            return {"success": False, "error": str(e)}

    def connect(self, args: dict) -> dict:
        try:
            self._run_device(self._build_device_async(args))
            return {"success": True, **self._status_fields()}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def disconnect(self) -> dict:
        d = self._device
        if d is not None and hasattr(d, "disconnect"):
            try:
                self._run_device(d.disconnect())
            except Exception as e:
                logger.debug(f"disconnect: {e}")
        self._device = None
        self._lan_ip = None
        w = self._wall
        if w is not None and hasattr(w, "disconnect"):
            try:
                self._run_device(w.disconnect())
            except Exception as e:
                logger.debug(f"wall disconnect: {e}")
        self._wall = None
        return {"success": True, "connected": False}

    def device_status(self) -> dict:
        return {"success": True, **self._status_fields()}

    def scan(self, args: dict) -> dict:
        timeout = float(args.get("timeout", 15) or 15)
        limit = int(args.get("limit", 4) or 4)

        async def _scan():
            from divoom_lib.utils import discovery
            results = await discovery.discover_all_divoom_devices(timeout=timeout)
            return results[:limit] if limit > 0 else results

        try:
            results = self._run_device(_scan())
            return {"success": True, "devices": _json_safe(results)}
        except Exception as e:
            logger.warning(f"scan failed: {e}")
            return {"success": False, "error": str(e), "devices": []}

    def wall_configure(self, args: dict) -> dict:
        slots = args.get("slots") or {}
        cell = int(args.get("cell_size", 16) or 16)
        if not slots:
            self._wall_slots = {}
            self._wall = None
            return {"success": True, "wall": False}
        if (self._wall is not None and slots == self._wall_slots
                and getattr(self._wall, "is_connected", False)):
            return {"success": True, "wall": True}
        self._wall_slots = slots

        async def _build():
            from divoom_lib.wall import DivoomWall
            configs = [{
                "mac": mac,
                "x": int(s.get("x", 0)), "y": int(s.get("y", 0)),
                "size": int(s.get("size", cell)),
                "width": int(s.get("width", 120)), "height": int(s.get("height", 120)),
            } for mac, s in slots.items()]
            wall = DivoomWall(configs, custom_logger=logger)
            await wall.connect()
            return wall

        try:
            self._wall = self._run_device(_build())
            return {"success": True, "wall": True}
        except Exception as e:
            logger.warning(f"wall_configure failed: {e}")
            self._wall = None
            return {"success": False, "error": str(e), "wall": False}

    def sync_artwork(self, args: dict) -> dict:
        file_id = args.get("file_id")
        default_size = int(args.get("default_size", 16) or 16)
        which = args.get("target", "device")
        if not file_id:
            return {"success": False, "error": "sync_artwork requires 'file_id'"}

        async def _do():
            import urllib.request
            from pathlib import Path as _P
            from divoom_lib import media_decoder
            from divoom_lib.monthly_best_daemon import stream_raw_bin_payload

            dl_url = f"https://fin.divoom-gz.com/{file_id}"
            req = urllib.request.Request(dl_url, headers={"User-Agent": "okhttp/4.12.0"})
            with urllib.request.urlopen(req, timeout=10) as resp:
                file_bytes = resp.read()
            if len(file_bytes) < 4:
                return False

            if which == "wall":
                if self._wall is None:
                    raise RuntimeError("no wall configured")
                targets = [(slot.device, slot.size) for slot in self._wall.devices]
            else:
                device = await self._ensure_device_async(args.get("mac"))
                targets = [(device, default_size)]

            extracted = media_decoder.extract_gif_from_magic_43(file_bytes)
            is_gif = bool(extracted) or file_bytes[:6] in (b"GIF89a", b"GIF87a")
            gif_data = extracted or file_bytes

            tmp = _P(__file__).parent.parent / "scratch"
            tmp.mkdir(parents=True, exist_ok=True)
            results = []
            for divoom, size in targets:
                mac = getattr(getattr(divoom, "_conn", None), "mac", None) or "dev"
                if is_gif:
                    from PIL import Image
                    src = tmp / f"sync_in_{mac}.gif"
                    src.write_bytes(gif_data)
                    out = tmp / f"sync_out_{mac}.gif"
                    with Image.open(src) as img:
                        frames, durations = [], []
                        for i in range(img.n_frames):
                            img.seek(i)
                            frames.append(img.resize((int(size), int(size)), Image.Resampling.NEAREST).convert("RGB"))
                            durations.append(img.info.get("duration", 100))
                        frames[0].save(out, save_all=True, append_images=frames[1:],
                                       duration=durations, loop=0)
                    results.append(await divoom.display.show_image(str(out)))
                else:
                    results.append(await stream_raw_bin_payload(divoom, file_bytes))
            return all(r is True for r in results)

        try:
            ok = self._run_device(_do())
            return {"success": bool(ok)}
        except Exception as e:
            logger.warning(f"sync_artwork failed: {e}")
            return {"success": False, "error": str(e)}

    def probe_lan(self) -> dict:
        d = self._device
        lan = getattr(d, "lan", None) if d is not None else None
        if lan is None:
            return {"success": True, "reachable": False, "detail": "no LAN configured"}

        async def _probe():
            return await lan.probe()

        try:
            ok = self._run_device(_probe())
            ip = getattr(lan, "device_ip", None)
            return {"success": True, "reachable": bool(ok), "device_ip": ip}
        except Exception as e:
            return {"success": False, "reachable": False, "error": str(e)}

    # ── lifecycle ────────────────────────────────────────────────────────
    def stop(self) -> None:
        if self._loop is not None:
            try:
                self._loop.call_soon_threadsafe(self._loop.stop)
            except Exception:
                pass
