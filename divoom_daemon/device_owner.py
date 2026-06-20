"""Device ownership for the Divoom daemon — single BLE/LAN device + wall lifecycle."""
from __future__ import annotations

import base64
import logging
import os
import tempfile
import threading
from pathlib import Path
from typing import Callable, Optional

from divoom_daemon.owner_art import OwnerArtMixin
from divoom_daemon.owner_live import OwnerLiveMixin
from divoom_daemon.owner_loop import OwnerLoopMixin
from divoom_daemon.owner_notify import OwnerNotifyMixin
from divoom_daemon.owner_wall import OwnerWallMixin

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


class DeviceOwner(OwnerArtMixin, OwnerLiveMixin, OwnerLoopMixin, OwnerNotifyMixin,
                  OwnerWallMixin):
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
        self._cmd_queue = None                  # CommandQueue, created with loop
        self._hot_progress: dict = {"phase": "idle"}
        self._hot_progress_lock = threading.Lock()
        self._last_conn_state = None             # P6: last observed ConnectionState
        self._scan_name_cache: dict = {}         # MAC(upper) -> friendly name, from scans
        OwnerLiveMixin.__init__(self)

    # ── device loop ──────────────────────────────────────────────────────
    # _device_loop / _run_device / _run_on_loop live in OwnerLoopMixin.

    def _device_connected(self) -> bool:
        # P6 design: the legacy `connected` field reflects the raw is_connected;
        # honest liveness (DEGRADED on a dead-but-cached link) is surfaced via
        # `connection_state` (derive_connection_state → is_alive), not here.
        d = self._device
        return bool(d is not None and getattr(d, "is_connected", False))

    def _owned_devices(self) -> list[dict]:
        """Devices the daemon holds (active + live jobs). A connected BLE peripheral
        stops advertising → scan can't see it → it vanishes from the selector; union
        it back. Name: device_name | scan-cache | raw MAC. BLE only (LAN isn't scan)."""
        def _name(dev, mac):
            return (getattr(dev, "device_name", None)
                    or self._scan_name_cache.get(mac.upper()) or mac)

        owned: dict[str, dict] = {}
        d = self._device
        if d is not None and self.mac and not self._lan_ip:
            owned[self.mac.upper()] = {
                "name": _name(d, self.mac), "address": self.mac, "owned": True}
        for mac, dev in (getattr(self, "_live_devices", None) or {}).items():
            if mac and mac.upper() not in owned:
                owned[mac.upper()] = {
                    "name": _name(dev, mac), "address": mac, "owned": True}
        return list(owned.values())

    def _current_target_key(self) -> Optional[str]:
        """Normalized identity of the device the owner currently holds (BLE mac or
        LAN key), so a connect to a DIFFERENT target can be detected."""
        if self._lan_ip:
            return f"LAN:{self._lan_ip}"
        return (self.mac or "").upper() or None

    def _connection_state(self) -> str:
        """P6: the honest dot state + a one-line transition log (a connection
        timeline in the daemon log). See ble_connection.derive_connection_state."""
        from divoom_lib.ble_connection import derive_connection_state
        active = self._device if self._device is not None else self._wall
        state = derive_connection_state(active)
        if state != self._last_conn_state:
            logger.info("connection state: %s -> %s (mac=%s)",
                        getattr(self._last_conn_state, "value", "none"),
                        state.value, self.mac)
            self._last_conn_state = state
        return state.value

    async def _ensure_device_async(self, mac: Optional[str] = None):
        # BLE Hardening P1: a failed reconnect raises a typed reason, never a
        # dead handle the next command silently times out on.
        from divoom_lib.ble_connection import ensure_connected, BleConnectionError
        if self._device is not None:
            # R53/HW: re-ensure on a dead-but-cached-connected link (is_alive is
            # honest; is_connected lags True after an OS drop).
            if not getattr(self._device, "is_alive",
                           getattr(self._device, "is_connected", False)) \
                    and hasattr(self._device, "connect"):
                res = await ensure_connected(self._device)
                if not res.ok:
                    raise BleConnectionError(res)
            return self._device
        from divoom_lib.divoom import Divoom
        from divoom_lib.utils import discovery
        target = mac or self.mac
        if not target:
            from divoom_daemon.daemon_config import load_daemon_config
            devs = await discovery.discover_all_divoom_devices(
                timeout=load_daemon_config().reconnect_scan_timeout)
            if not devs:
                raise RuntimeError("no Divoom device found")
            target = devs[0]["address"]
            self.mac = target
        dev = Divoom(mac=target, logger=logger, use_ios_le_protocol=False)
        res = await ensure_connected(dev)
        if not res.ok:
            raise BleConnectionError(res)
        self._device = dev
        return self._device

    async def _build_device_async(self, args: dict):
        # BLE Hardening P1: honest connect (retry+backoff, verify, typed reason).
        from divoom_lib.ble_connection import ensure_connected, BleConnectionError
        # R53/HW: if a DIFFERENT *known* target is requested than the one we hold,
        # release the current one first — else connecting to B while A is active
        # silently returned A (cached is_connected made it look connected in 0.0s),
        # driving the wrong screen. current_key=None (untracked/injected) → reuse.
        requested = args.get("mac") or (args.get("lan_ip") and f"LAN:{args.get('lan_ip')}")
        requested_key = (requested or "").upper() or None
        current_key = self._current_target_key()
        if self._device is not None and requested_key and current_key and requested_key != current_key:
            logger.info("connect target changed (%s -> %s); releasing current device",
                        current_key, requested_key)
            try:
                await self._device.disconnect()
            except Exception as e:
                logger.debug("release-on-switch disconnect failed (continuing): %s", e)
            self._device = None
            self._lan_ip = None
            self.mac = None
        if self._device is not None:
            # Same target (or a generic "use active" request): re-ensure if the
            # link is not alive, else reuse.
            if not getattr(self._device, "is_alive",
                           getattr(self._device, "is_connected", False)) \
                    and hasattr(self._device, "connect"):
                res = await ensure_connected(self._device, attempts=2, attempt_timeout=8.0)
                if not res.ok:
                    raise BleConnectionError(res)
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
        dev = Divoom(mac=mac, logger=logger, device_name=args.get("device_name"),
                     use_ios_le_protocol=bool(args.get("use_ios_le_protocol", True)))
        res = await ensure_connected(dev, attempts=2, attempt_timeout=8.0)
        if not res.ok:
            raise BleConnectionError(res)   # don't keep a dead handle
        self._device = dev
        self.mac = mac
        return self._device

    def _status_fields(self) -> dict:
        d = self._device
        return {
            "connected": self._device_connected(),
            "connection_state": self._connection_state(),   # P6: honest dot state
            "mac": self.mac,
            "lan_ip": self._lan_ip,
            "wall": self._wall is not None,
        }

    # send_notification / _send_to_device_ble live in OwnerNotifyMixin.

    # ── command handlers ─────────────────────────────────────────────────
    def device_call(self, args: dict) -> dict:
        method = args.get("method")
        call_args = list(args.get("args", []) or [])
        call_kwargs = args.get("kwargs", {}) or {}
        which = args.get("target", "device")
        token = args.get("token")
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
            result = self._run_device(_do(), token=token)
            return {"success": True, "result": _json_safe(result)}
        except Exception as e:
            logger.warning(f"device_call {which}.{method} failed: {e}")
            return {"success": False, "error": str(e)}

    def exclusive_start(self, args: dict) -> dict:
        token = args.get("token")
        if not token:
            return {"success": False, "error": "exclusive_start requires 'token'"}
        if self._cmd_queue is None:
            self._device_loop()
        try:
            # Submit acquire WITH the token so it passes the exclusive-mode
            # gate on the queue's worker side.
            self._run_device(self._cmd_queue.acquire(token), token=token)
            return {"success": True, "token": token}
        except Exception as e:
            logger.warning(f"exclusive_start failed: {e}")
            return {"success": False, "error": str(e)}

    def exclusive_end(self, _args: dict) -> dict:
        token = _args.get("token")
        if not token:
            return {"success": False, "error": "exclusive_end requires 'token'"}
        if self._cmd_queue is None:
            return {"success": False, "error": "no queue"}
        try:
            # release token too: the queue is in exclusive mode, so only items
            # with MATCHING tokens are dequeued.
            self._run_device(self._cmd_queue.release(token), token=token)
            return {"success": True}
        except Exception as e:
            logger.warning(f"exclusive_end failed: {e}")
            return {"success": False, "error": str(e)}

    def connect(self, args: dict) -> dict:
        from divoom_lib.ble_connection import BleConnectionError
        # Reject an explicitly-empty target (mac="") — a UI bug must not silently
        # grab an arbitrary/last device. mac=None (absent) still means "use active".
        if any(v is not None and not str(v).strip()
               for v in (args.get("mac"), args.get("lan_ip"))):
            return {"success": False, "reason": "invalid_target",
                    "error": "empty target", "message": "No device selected."}
        # BLE Hardening P4: a BLE connect (mac, not LAN) preflights adapter/
        # permission so a powered-off radio / missing grant fails fast with cause.
        if args.get("mac") and not args.get("lan_ip"):
            from divoom_lib.ble_preflight import preflight_bluetooth
            pf = preflight_bluetooth()
            if not pf.ok:
                logger.warning("connect blocked by preflight: %s", pf.reason.value)
                return {"success": False, "error": pf.message,
                        "reason": pf.reason.value, "message": pf.message}
        # G4: taking a wall member as active — relinquish the wall first.
        tgt = args.get("mac") or (args.get("lan_ip") and f"LAN:{args.get('lan_ip')}")
        if tgt and tgt in (getattr(self, "_wall_slots", None) or {}):
            self._drop_current_wall()
            self._wall_slots = {}
        try:
            self._run_device(self._build_device_async(args))
            return {"success": True, **self._status_fields()}
        except BleConnectionError as e:
            logger.warning(f"connect failed: {e.result.reason.value} ({e.result.detail})")
            return {"success": False, "error": str(e),
                    "reason": e.result.reason.value, "message": e.result.message}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def disconnect(self) -> dict:
        self.forget_device_activity(self.mac or (self._lan_ip and f"LAN:{self._lan_ip}"))  # G1: no ghost
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
        from divoom_daemon.daemon_config import load_daemon_config
        cfg = load_daemon_config()
        # 0 is a valid limit ("no cap"); only default when absent/None (not `or`).
        timeout = float(args.get("timeout") or cfg.scan_timeout)
        raw_limit = args.get("limit")
        limit = int(raw_limit if raw_limit is not None else cfg.scan_limit)

        # BLE Hardening P4: preflight so an empty scan carries a cause (denied
        # permission / powered-off adapter) instead of a silent "no devices".
        from divoom_lib.ble_preflight import preflight_bluetooth
        pf = preflight_bluetooth()
        if not pf.ok:
            logger.warning("scan blocked by preflight: %s (%s)", pf.reason.value, pf.detail)
            return {"success": False, "error": pf.message,
                    "reason": pf.reason.value, "message": pf.message, "devices": []}

        async def _scan():
            from divoom_lib.utils import discovery
            # early-exit once `limit` devices are seen (limit<=0 → full window)
            results = await discovery.discover_all_divoom_devices(
                timeout=timeout, expected=limit)
            return results[:limit] if limit > 0 else results

        try:
            # G2: scan off the command queue — it uses the central manager, not the
            # connected peripheral, so it must not serialize behind (and freeze)
            # device I/O / live-widget pushes for the scan's whole duration.
            results = self._run_on_loop(_scan())
            # Cache mac->name (so a non-advertising owned device keeps its name),
            # then union-in owned devices absent from this scan. See _owned_devices.
            for d in results:
                addr, nm = (d.get("address") or "").upper(), d.get("name")
                if addr and nm:
                    self._scan_name_cache[addr] = nm
            seen = {(d.get("address") or "").upper() for d in results}
            for od in self._owned_devices():
                if (od.get("address") or "").upper() not in seen:
                    results.append(od)
            return {"success": True, "devices": _json_safe(results)}
        except Exception as e:
            logger.warning(f"scan failed: {e}")
            return {"success": False, "error": str(e), "devices": []}

    # ── wall ──────────────────────────────────────────────────────────────
    # _drop_current_wall / _active_key / _relinquish_active_if_in /
    # wall_configure / _wall_delta live in OwnerWallMixin.

    def sync_artwork(self, args: dict) -> dict:
        file_id = args.get("file_id")
        default_size = int(args.get("default_size", 16) or 16)
        which = args.get("target", "device")
        if not file_id:
            return {"success": False, "error": "sync_artwork requires 'file_id'"}

        async def _do():
            import asyncio
            import aiohttp
            from pathlib import Path as _P
            from divoom_lib import media_decoder
            from divoom_lib.monthly_best_daemon import stream_raw_bin_payload

            dl_url = f"https://fin.divoom-gz.com/{file_id}"
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    dl_url,
                    headers={"User-Agent": "okhttp/4.12.0"},
                    timeout=aiohttp.ClientTimeout(total=10),
                ) as resp:
                    file_bytes = await resp.read()
            if len(file_bytes) < 4:
                return False

            if which == "wall":
                if self._wall is None:
                    raise RuntimeError("no wall configured")
                targets = [(slot.device, slot.size) for slot in self._wall.devices]
            else:
                device = await self._ensure_device_async(args.get("mac"))
                targets = [(device, default_size)]

            tmp = _P(__file__).parent.parent / "scratch"
            tmp.mkdir(parents=True, exist_ok=True)
            # Resolve to a plain GIF (R36): cloud containers (magic 9/18/26) are
            # app-side AES ciphertext the device can't decode — raw-streaming them
            # ACKs every chunk yet renders NOTHING. Decode → GIF → show_image like
            # the APK. R40 §2 unified resolver (GIF / magic 43 / AES / 0xAA hot).
            resolved = await asyncio.to_thread(
                media_decoder.resolve_to_gif, file_bytes, tmp / "sync_decoded.gif")
            is_gif = resolved is not None
            gif_data = resolved if resolved is not None else file_bytes
            if is_gif and gif_data is not file_bytes:
                logger.info(f"sync_artwork: decoded container "
                            f"(magic {file_bytes[0]}) → {len(gif_data)}B image")

            results = []
            for divoom, size in targets:
                mac = getattr(getattr(divoom, "_conn", None), "mac", None) or "dev"
                if is_gif:
                    from PIL import Image
                    src = tmp / f"sync_in_{mac}.gif"
                    src.write_bytes(gif_data)
                    out = tmp / f"sync_out_{mac}.gif"
                    def _resize():
                        with Image.open(src) as img:
                            frames, durations = [], []
                            for i in range(img.n_frames):
                                img.seek(i)
                                frames.append(img.resize((int(size), int(size)), Image.Resampling.NEAREST).convert("RGB"))
                                durations.append(img.info.get("duration", 100))
                            frames[0].save(out, save_all=True, append_images=frames[1:],
                                           duration=durations, loop=0)
                    await asyncio.to_thread(_resize)
                    results.append(await divoom.display.show_image(str(out)))
                else:
                    # Last resort for unknown magics: legacy raw 0x8B stream.
                    logger.warning(f"sync_artwork: unknown payload magic "
                                   f"{file_bytes[0]}; raw-streaming as-is")
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
        try:
            self.stop_all_live_jobs()
        except Exception:
            pass
        if self._cmd_queue is not None:
            try:
                self._cmd_queue.stop()
            except Exception:
                pass
        if self._loop is not None:
            try:
                self._loop.call_soon_threadsafe(self._loop.stop)
            except Exception:
                pass
