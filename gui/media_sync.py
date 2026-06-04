# gui/media_sync.py

import json
import base64
import logging
import threading
import time
from pathlib import Path

from divoom_lib.utils import media_source
from gallery_sync import GallerySyncMixin

logger = logging.getLogger("divoom_gui")

class MediaSyncMixin(GallerySyncMixin):
    """Mixin for macOS active playback tracker, stock tickers, sysmon widget, and frame pushing."""
    def _get_device_size(self, address: str) -> int:
        for d in self.discovered_list:
            if d.get("address") == address:
                name = d.get("name", "").lower()
                if "64" in name:
                    return 64
                return 16
        return 16

    def get_system_stats_preview(self, size: int = 0) -> str:
        try:
            stats = media_source.get_system_stats()
            sz = int(size) if size and int(size) > 0 else self._active_device_size()
            frame_path = media_source.render_system_stats_frame(stats, size=sz)
            return json.dumps({
                "ok": True, "size": sz, "stats": stats,
                "preview": self._frame_to_data_url(frame_path),
            })
        except Exception as e:
            logger.error(f"get_system_stats_preview failed: {e}")
            return json.dumps({"ok": False, "error": str(e)})

    def apply_system_stats(self) -> str:
        try:
            stats = media_source.get_system_stats()
            if not self._has_push_target():
                return json.dumps({"success": False, "error": "No device connected", "stats": stats})
            size = self._active_device_size()
            frame_path = media_source.render_system_stats_frame(stats, size=size)
            res = self._push_frame(frame_path, size)
            return json.dumps({
                "success": res, "stats": stats,
                "preview": self._frame_to_data_url(frame_path),
            })
        except Exception as e:
            logger.error(f"apply_system_stats failed: {e}")
            return json.dumps({"success": False, "error": str(e)})

    def _music_sync_loop(self):
        last_track = None
        last_artist = None
        while self.music_sync_active:
            try:
                # Handshake/auto-reconnect active single target before doing work
                dev = self.current_divoom
                if dev and not dev.lan and not dev.is_connected:
                    logger.info("Music Sync: Device is offline. Reconnecting BLE...")
                    try:
                        self._run_async(dev.connect())
                    except Exception as cx:
                        logger.warning(f"Music Sync: Auto-reconnect failed: {cx}")
                        time.sleep(3.0)
                        continue

                track_info = media_source.get_current_playing_track()
                if track_info:
                    track = track_info.get("track")
                    artist = track_info.get("artist")
                    source = track_info.get("source")
                    
                    if track != last_track or artist != last_artist:
                        logger.info(f"Music Sync: New track: {track} by {artist} ({source})")
                        last_track = track
                        last_artist = artist
                        
                        art_url = media_source.fetch_album_art_url(track, artist)
                        if art_url:
                            size = self._active_device_size()
                            out_path = media_source.render_and_downsample_artwork(art_url, size=size)
                            preview_url = ""
                            if out_path and out_path.exists():
                                preview_url = self._frame_to_data_url(out_path)
                                logger.info(f"Music Sync: Push cover art frame ({size}px): {out_path}")
                                try:
                                    if not self._push_frame(out_path, size):
                                        logger.warning("Music Sync: no connected target for cover art")
                                except Exception as e:
                                    logger.error(f"Failed to stream artwork: {e}")

                            self.current_track_cache = {
                                "preview": preview_url,
                                "track": track,
                                "artist": artist,
                                "source": source,
                                "artwork_url": art_url
                            }
                        else:
                            self.current_track_cache = {
                                "track": track,
                                "artist": artist,
                                "source": source,
                                "artwork_url": ""
                            }
                else:
                    self.current_track_cache = None
            except Exception as e:
                logger.error(f"Music sync error: {e}")
            time.sleep(3.0)

    def toggle_music_sync(self, enable: bool) -> bool:
        logger.info(f"GUI Action: Toggle music sync to {enable}")
        self.music_sync_active = enable
        if enable:
            if not self.music_thread or not self.music_thread.is_alive():
                self.music_thread = threading.Thread(target=self._music_sync_loop, daemon=True)
                self.music_thread.start()
        return True

    def get_current_track_info(self) -> str:
        if self.current_track_cache:
            return json.dumps(self.current_track_cache)
        return json.dumps({})

    def _active_device_size(self, default: int = 16) -> int:
        try:
            if self.wall_slots:
                sizes = [s.get("size", default) for s in self.wall_slots.values() if isinstance(s, dict)]
                return min(sizes) if sizes else default
            dev = self.current_divoom
            mac = getattr(getattr(dev, "_conn", None), "mac", None) or getattr(dev, "mac", None)
            if mac:
                return self._get_device_size(mac)
        except Exception:
            pass
        return default

    def _has_push_target(self) -> bool:
        dev = self.current_divoom
        return bool(self.wall_slots) or bool(dev)

    def _push_frame(self, frame_path, size: int) -> bool:
        """Push a rendered frame to the wall or the single active (BLE/LAN) device with auto-reconnect support."""
        if self.wall_slots:
            if self._rebuild_wall_instance(size):
                async def connect_and_show():
                    await self.wall_instance.connect()
                    return await self.wall_instance.show_image(str(frame_path))
                return bool(self._run_async(connect_and_show()))
            return False
            
        dev = self.current_divoom
        if not dev:
            return False
            
        if dev.lan:
            return bool(self._run_async(dev.display.show_image(str(frame_path))))
            
        async def connect_and_push_ble():
            if not dev.is_connected:
                logger.info("BLE device went idle/disconnected. Attempting auto-reconnect...")
                try:
                    await dev.connect()
                except Exception as ex:
                    logger.error(f"Auto-reconnect failed: {ex}")
                    return False
            return await dev.display.show_image(str(frame_path))
            
        return bool(self._run_async(connect_and_push_ble()))

    @staticmethod
    def _frame_to_data_url(frame_path) -> str:
        try:
            data = Path(frame_path).read_bytes()
            return "data:image/png;base64," + base64.b64encode(data).decode("ascii")
        except Exception:
            return ""

    def get_ticker_preview(self, symbol: str, size: int = 0) -> str:
        try:
            # Auto-reconnect target check inside widgets preview triggers (ensures handshake is active)
            dev = self.current_divoom
            if dev and not dev.lan and not dev.is_connected:
                logger.info("Stock Ticker: Attempting auto-reconnect before rendering...")
                try:
                    self._run_async(dev.connect())
                except Exception:
                    pass

            data = media_source.fetch_stock_ticker(symbol)
            if not data:
                return json.dumps({"ok": False, "error": "no data"})
            sz = int(size) if size and int(size) > 0 else self._active_device_size()
            frame_path = media_source.render_stock_ticker_frame(symbol, data, size=sz)
            return json.dumps({
                "ok": True, "size": sz, "symbol": symbol,
                "preview": self._frame_to_data_url(frame_path),
                "price": data["price"], "change": data["change"], "pct_change": data["pct_change"],
            })
        except Exception as e:
            logger.error(f"get_ticker_preview failed: {e}")
            return json.dumps({"ok": False, "error": str(e)})

    def apply_stock_ticker(self, symbol: str) -> str:
        logger.info(f"GUI Action: Applying stock ticker for {symbol}...")
        try:
            data = media_source.fetch_stock_ticker(symbol)
            if not data:
                return json.dumps({"success": False, "error": "Could not fetch ticker data"})
            if not self._has_push_target():
                return json.dumps({"success": False, "error": "No device connected"})

            size = self._active_device_size()
            frame_path = media_source.render_stock_ticker_frame(symbol, data, size=size)
            res = self._push_frame(frame_path, size)

            return json.dumps({
                "success": res,
                "preview": self._frame_to_data_url(frame_path),
                "price": data["price"],
                "change": data["change"],
                "pct_change": data["pct_change"],
            })
        except Exception as e:
            logger.error(f"Failed to apply stock ticker: {e}")
            return json.dumps({"success": False, "error": str(e)})

    def _tickers_path(self):
        return Path.home() / ".config" / "divoom-control" / "tickers.json"

    def get_tickers(self) -> str:
        path = self._tickers_path()
        if path.exists():
            try:
                return json.dumps(json.loads(path.read_text(encoding="utf-8")))
            except Exception:
                pass
        seed = self._seed_tickers_from_macos()
        self.set_tickers(json.dumps(seed))
        return json.dumps(seed)

    def set_tickers(self, *symbols_arg, **kwargs) -> bool:
        try:
            symbols = self._coerce_list(symbols_arg, kwargs, "tickers")
            seen, clean = set(), []
            for s in symbols:
                s = str(s).strip().upper()
                if s and s not in seen:
                    seen.add(s)
                    clean.append(s)
            path = self._tickers_path()
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(clean, indent=2), encoding="utf-8")
            return True
        except Exception as e:
            logger.error(f"set_tickers failed: {e}")
            return False

    @staticmethod
    def _seed_tickers_from_macos() -> list:
        default = ["AAPL", "GOOGL", "MSFT", "TSLA", "BTC-USD", "ETH-USD"]
        try:
            import subprocess
            out = subprocess.run(
                ["defaults", "read", "com.apple.stocks"],
                capture_output=True, text=True, timeout=4)
            import re
            syms = re.findall(r'"?symbol"?\s*=\s*"?([A-Z][A-Z0-9.\-]{0,9})"?', out.stdout)
            cleaned = []
            for s in syms:
                s = s.upper()
                if s and s not in cleaned:
                    cleaned.append(s)
            return cleaned or default
        except Exception:
            return default
