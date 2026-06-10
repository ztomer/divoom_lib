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
                        file_bytes = await resp.read()
                if len(file_bytes) < 4:
                    return None

                # R40 §2: one resolver for every CDN container (plain GIF,
                # magic 43, AES 9/18/26, AND 0xAA hot files — the previous
                # branching missed 0xAA, so assigning a hot tile to a slot
                # crashed Image.open with "cannot identify image file").
                scratch = tmp / f"ca_{fid.replace('/', '_')}.gif"
                gif_data = await asyncio.to_thread(
                    media_decoder.resolve_to_gif, file_bytes, scratch)
                if gif_data is None:
                    logger.warning(f"custom_art_push: undecodable payload for {fid} "
                                   f"(magic {file_bytes[0]})")
                    return None

                # Resize to 16x16 and encode as AA frame
                src = tmp / f"ca_in_{fid.replace('/', '_')}.gif"
                src.write_bytes(gif_data)
                with Image.open(src) as img:
                    img = img.convert("RGB").resize((16, 16), Image.Resampling.NEAREST)
                    rgb = img.tobytes()
                return encode_animation_frame(rgb, 16, 16, 500)

            frames: list[bytes] = [b""] * SLOTS_PER_PAGE
            for idx, fid in slot_map.items():
                encoded = await _encode_file(fid)
                if encoded is None:
                    return {"success": False, "error": f"could not fetch/decode {fid}"}
                frames[idx] = encoded

            if not await push_page(device, page, frames, use_new_mode=False):
                return {"success": False, "error": "page push failed"}
            return {"success": True, "files_pushed": len(slot_map)}

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

    def hot_update(self, args: dict) -> dict:
        """Start a HOT channel update in the background and return immediately.
        Call ``hot_update_progress({})`` to poll progress."""
        device_size = int(args.get("device_size", 16) or 16)
        show = bool(args.get("show", True))

        if self._get_hot_progress().get("phase") in (
                "fetching_manifest", "downloading", "uploading"):
            return {"success": False, "error": "hot update already in progress"}

        self._set_hot_progress({"phase": "starting"})

        async def _do():
            try:
                device = await self._ensure_device_async(args.get("mac"))
                result = await device.hot_update.update(
                    device_size=device_size,
                    progress_cb=lambda p: self._set_hot_progress(p))
                if result.get("success") and show:
                    await device.hot_update.show_hot_channel()
                self._set_hot_progress({"phase": "done", "result": result})
            except Exception as e:
                logger.warning(f"hot_update failed: {e}")
                self._set_hot_progress({"phase": "error", "error": str(e)})

        if self._cmd_queue is None:
            self._device_loop()
        self._cmd_queue.submit(_do())
        return {"success": True, "started": True}

    def hot_update_progress(self, args: dict) -> dict:
        """Query the current hot update progress. Returns the latest phase dict."""
        return self._get_hot_progress()
