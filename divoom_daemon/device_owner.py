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
from divoom_daemon.owner_connect import OwnerConnectMixin
from divoom_daemon.owner_live import OwnerLiveMixin
from divoom_daemon.owner_loop import OwnerLoopMixin
from divoom_daemon.owner_notify import OwnerNotifyMixin
from divoom_daemon.owner_util import _json_safe  # re-exported; used by device_call/sync_artwork
from divoom_daemon.owner_wall import OwnerWallMixin

logger = logging.getLogger("divoom_daemon.device_owner")


class DeviceOwner(OwnerArtMixin, OwnerConnectMixin, OwnerLiveMixin, OwnerLoopMixin,
                  OwnerNotifyMixin, OwnerWallMixin):
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
    # connect / disconnect / scan / device_status / _build_device_async /
    # _ensure_device_async / _status_fields / _connection_state / _owned_devices /
    # _current_target_key / probe_lan live in OwnerConnectMixin.
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
        # An exclusive session takes over the active screen (animation / custom-art
        # push). Stop the active device's live jobs FIRST: their tokenless frames
        # would queue behind the exclusive op while it runs, then BURST out FIFO on
        # release and clobber what was just pushed. Stop before acquire so a
        # cancelled poller can't slip one more frame in. Background-device jobs (a
        # different screen) don't clobber and are left running.
        try:
            self.live_jobs_stop_for({})
        except Exception as e:
            logger.debug("stop live jobs on exclusive_start: %s", e)
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

    # connect / disconnect / device_status / scan live in OwnerConnectMixin.

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

    # probe_lan lives in OwnerConnectMixin.

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
        loop = self._loop
        if loop is not None:
            try:
                loop.call_soon_threadsafe(loop.stop)
            except Exception:
                pass
        # Teardown the process-global BLE state tied to THIS loop, so a later
        # restart can't be handed a stale per-loop connect lock (id(loop) reuse) or
        # a registry entry pointing at a transport on the dead loop.
        try:
            from divoom_lib import ble_connection, ble_registry
            ble_connection.forget_loop(loop)
            ble_registry.reset()
        except Exception as e:
            logger.debug("loop-teardown state reset failed: %s", e)
        # Null the refs so _device_loop() rebuilds a fresh loop/queue on next use
        # instead of returning the now-stopped one.
        self._loop = None
        self._cmd_queue = None
        self._loop_thread = None
