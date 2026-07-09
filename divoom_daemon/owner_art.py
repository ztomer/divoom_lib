"""Custom-art and HOT-channel handlers for the daemon's DeviceOwner.

Split from device_owner.py (500-LOC rule). The mixin relies on the host
class for ``_run_device``, ``_ensure_device_async``, ``_hot_progress_lock``,
``_hot_progress``, ``_cmd_queue`` and ``_device_loop``.
"""
from __future__ import annotations

import asyncio
import logging

logger = logging.getLogger("divoom_daemon.device_owner")


class OwnerArtMixin:
    """custom_art_push / custom_art_query_page / hot_update RPC handlers."""

    def custom_art_push(self, args: dict) -> dict:
        """Push cloud files to a custom art page on the device.

        Preferred form — full page mapping (the page is sent exactly once,
        so unmapped slots are cleared rather than each push wiping the rest):
            slots: dict {slot 0-11 (str or int): file_id}
        Legacy form:
            file_ids: list of cloud file IDs, assigned sequentially
            slot: optional starting slot 0-11

        Common:
            page: target page 0, 1, or 2
            mac: optional device MAC override
        """
        from divoom_lib.tools.custom_art_push import SLOTS_PER_PAGE

        page = int(args.get("page", 0))
        slot_map: dict[int, str] = {}
        if args.get("slots"):
            for k, fid in args["slots"].items():
                idx = int(k)
                if 0 <= idx < SLOTS_PER_PAGE and fid:
                    slot_map[idx] = fid
        else:
            base = int(args.get("slot") or 0)
            for i, fid in enumerate(args.get("file_ids", [])):
                if base + i < SLOTS_PER_PAGE:
                    slot_map[base + i] = fid
        if not slot_map:
            return {"success": False,
                    "error": "custom_art_push requires 'slots' or 'file_ids'"}

        async def _do():
            import aiohttp
            from pathlib import Path as _P
            from PIL import Image
            from divoom_lib import media_decoder
            from divoom_lib.tools.custom_art_push import push_page
            from divoom_lib.utils.divoom_image_encode import encode_animation_frame

            device = await self._ensure_device_async(args.get("mac"))
            tmp = _P(__file__).parent.parent / "scratch"
            tmp.mkdir(parents=True, exist_ok=True)

            async def _encode_file(fid: str) -> bytes | None:
                dl_url = f"https://fin.divoom-gz.com/{fid}"
                async with aiohttp.ClientSession() as session:
                    async with session.get(
                        dl_url,
                        headers={"User-Agent": "okhttp/4.12.0"},
                        timeout=aiohttp.ClientTimeout(total=10),
                    ) as resp:
                        status = resp.status
                        file_bytes = await resp.read()
                # A non-200 returns an HTML/JSON error page that can be >4 bytes —
                # don't let it slip past the length guard and get treated as art.
                if status != 200:
                    logger.warning("custom_art_push: CDN HTTP %s for %s", status, fid)
                    return None
                if len(file_bytes) < 4:
                    return None

                # R40 §2: one resolver for every CDN container (plain GIF,
                # magic 43, AES 9/18/26, AND 0xAA hot files — the previous
                # branching missed 0xAA, so assigning a hot tile to a slot
                # crashed Image.open with "cannot identify image file").
                scratch = tmp / f"ca_{fid.replace('/', '_')}.gif"
                src = tmp / f"ca_in_{fid.replace('/', '_')}.gif"
                try:
                    gif_data = await asyncio.to_thread(
                        media_decoder.resolve_to_gif, file_bytes, scratch)
                    if gif_data is None:
                        logger.warning(f"custom_art_push: undecodable payload for {fid} "
                                       f"(magic {file_bytes[0]})")
                        return None

                    # Resize to 16x16 and encode as AA frame
                    src.write_bytes(gif_data)
                    with Image.open(src) as img:
                        img = img.convert("RGB").resize((16, 16), Image.Resampling.NEAREST)
                        rgb = img.tobytes()
                    return encode_animation_frame(rgb, 16, 16, 500)
                finally:
                    # The two per-file scratch GIFs were never deleted → scratch/
                    # grew without bound on a long-running daemon doing repeated
                    # custom-art/hot pushes. Clean both on every path.
                    for _p in (scratch, src):
                        try:
                            _p.unlink()
                        except OSError:
                            pass

            frames: list[bytes] = [b""] * SLOTS_PER_PAGE
            for idx, fid in slot_map.items():
                encoded = await _encode_file(fid)
                if encoded is None:
                    return {"success": False, "error": f"could not fetch/decode {fid}"}
                frames[idx] = encoded

            if not await push_page(device, page, frames, use_new_mode=False):
                return {"success": False, "error": "page push failed"}
            # ACK ≠ device-confirmed. push_page returns True once every chunk got a
            # GATT write-with-response ACK — that catches a mid-stream unreachable
            # device (write_with_response fails), but NOT an app-layer drop (the
            # device ACKs the link write then silently ignores the data). The only
            # confirmation channel, 0x8E query_page, is unreliable on real HW (Pixoo
            # never answers — HW-verified 2026-06: all pages time out at 4s), so we
            # do NOT verify (it would add a 4s dead wait to every push). Report the
            # honest truth instead: writes accepted, storage not device-confirmed.
            return {"success": True, "files_pushed": len(slot_map),
                    "device_confirmed": False}

        coro = _do()
        try:
            result = self._run_device(coro)
            return result
        except Exception as e:
            try:
                coro.close()
            except Exception:
                pass
            logger.warning(f"custom_art_push failed: {e}")
            return {"success": False, "error": str(e)}

    def custom_art_query_page(self, args: dict) -> dict:
        """Query device for filled slot IDs on a custom art page.

        Args:
            page: page to query (0, 1, or 2)
            mac: optional device MAC override
        """
        page = int(args.get("page", 0))

        async def _do():
            from divoom_lib.tools.custom_art_push import query_page
            device = await self._ensure_device_async(args.get("mac"))
            ids = await query_page(device, page)
            return {"ids": ids or []}

        coro = _do()
        try:
            result = self._run_device(coro)
            return {"success": True, **result}
        except Exception as e:
            try:
                coro.close()
            except Exception:
                pass
            logger.warning(f"custom_art_query_page failed: {e}")
            return {"success": False, "error": str(e)}

    def _set_hot_progress(self, p: dict) -> None:
        with self._hot_progress_lock:
            self._hot_progress = p

    def _get_hot_progress(self) -> dict:
        with self._hot_progress_lock:
            return dict(self._hot_progress)

    # Phases during which a new hot update must be refused. "starting" is included
    # so a second call can't slip through the window between the claim and the
    # first download (the old guard omitted it AND did a non-atomic check-then-set,
    # so two socket-handler threads could both launch and clobber each other's
    # progress). _try_begin_hot_update claims the slot atomically under the lock.
    _HOT_ACTIVE_PHASES = ("starting", "fetching_manifest", "downloading", "uploading")

    def _try_begin_hot_update(self) -> bool:
        with self._hot_progress_lock:
            if self._hot_progress.get("phase") in self._HOT_ACTIVE_PHASES:
                return False
            self._hot_progress = {"phase": "starting"}
            return True

    def _clear_stuck_starting(self) -> None:
        """If the fire-and-forget _do() never ran (its queue item expired/cancelled
        under a held exclusive session), 'starting' would wedge ALL future hot
        updates now that it's in the active set. Reset it to a terminal error."""
        with self._hot_progress_lock:
            if self._hot_progress.get("phase") == "starting":
                self._hot_progress = {"phase": "error",
                                      "error": "hot update did not start (queue timeout)"}

    def hot_update(self, args: dict) -> dict:
        """Start a HOT channel update in the background and return immediately.
        Call ``hot_update_progress({})`` to poll progress."""
        device_size = int(args.get("device_size", 16) or 16)
        show = bool(args.get("show", True))

        # Atomic claim: refuses concurrent starts (incl. the "starting" window).
        if not self._try_begin_hot_update():
            return {"success": False, "error": "hot update already in progress"}

        async def _do():
            try:
                device = await self._ensure_device_async(args.get("mac"))
                result = await device.hot_update.update(
                    device_size=device_size,
                    progress_cb=lambda p: self._set_hot_progress(p))
                # R53: the daemon owns the last-checked stamp — it did the work
                # and knows the outcome. Key by the address the GUI passed (so its
                # read hits the same key). Mirrors the native Rust daemon.
                addr = args.get("address") or ""
                if addr and result.get("success"):
                    try:
                        from divoom_lib import hot_update_state
                        hot_update_state.record_check(addr, result)
                    except Exception as e:
                        logger.debug(f"hot_update: record_check failed: {e}")
                if result.get("success") and show:
                    await device.hot_update.show_hot_channel()
                self._set_hot_progress({"phase": "done", "result": result})
            except Exception as e:
                logger.warning(f"hot_update failed: {e}")
                self._set_hot_progress({"phase": "error", "error": str(e)})

        if self._cmd_queue is None:
            self._device_loop()
        try:
            fut = self._cmd_queue.submit(_do())
        except Exception as e:
            # submit() can raise (QueueStopped mid-restart, QueueFull) BEFORE
            # returning a future → add_done_callback never attaches and _do() never
            # runs, so the just-claimed "starting" phase (now in the active set)
            # would reject EVERY future hot_update for the daemon's lifetime. Clear
            # the claim and surface the error instead of wedging the feature.
            self._clear_stuck_starting()
            logger.warning(f"hot_update submit failed: {e}")
            return {"success": False, "error": str(e)}

        def _on_done(f):
            # _do() catches its own errors (→ "done"/"error"); a future exception
            # here means the QUEUE expired/cancelled the item before _do() ran, so
            # the phase is stuck "starting" — clear it so it can't wedge.
            try:
                failed = f.cancelled() or f.exception() is not None
            except Exception:
                failed = True
            if failed:
                self._clear_stuck_starting()

        try:
            fut.add_done_callback(_on_done)
        except Exception:
            pass
        return {"success": True, "started": True}

    def hot_update_progress(self, args: dict) -> dict:
        """Query the current hot update progress. Returns the latest phase dict."""
        return self._get_hot_progress()
