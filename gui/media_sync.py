import json
import asyncio
import logging
import urllib.request
import struct
import threading
import time
from pathlib import Path
from divoom_lib import divoom_auth
from divoom_lib.utils import media_source

logger = logging.getLogger("divoom_gui")

class MediaSyncMixin:
    def _get_device_size(self, address: str) -> int:
        for d in self.discovered_list:
            if d.get("address") == address:
                name = d.get("name", "").lower()
                if "64" in name:
                    return 64
                return 16
        return 16

    def _extract_gif_from_magic_43(self, file_data: bytes) -> bytes | None:
        if len(file_data) < 10 or file_data[0] != 43:
            return None
        try:
            text_len = struct.unpack("<I", file_data[6:10])[0]
            text_start = 10
            text_end = text_start + text_len
            
            gif_len_offset = text_end
            if len(file_data) < gif_len_offset + 4:
                return None
                
            gif_len = struct.unpack("<I", file_data[gif_len_offset:gif_len_offset+4])[0]
            gif_start = gif_len_offset + 4
            gif_end = gif_start + gif_len
            
            if gif_end > len(file_data):
                gif_end = len(file_data)
                
            gif_data = file_data[gif_start:gif_end]
            if gif_data.startswith(b"GIF89a") or gif_data.startswith(b"GIF87a"):
                return gif_data
        except Exception as e:
            logger.warning(f"Failed to extract GIF: {e}")
        return None

    def fetch_gallery(self, classify: int, target_size: int = 16) -> str:
        """
        Fetches popular community gallery artworks and caches previews locally.
        Filters by active connected device grid size to prevent hardware scaling mismatch.
        """
        logger.info(f"GUI Action: Fetching gallery classify={classify} target_size={target_size}...")
        try:
            if not self.cached_creds:
                # Check config.ini first to ensure credentials are stored
                import configparser
                config_file = Path.home() / ".config" / "divoom-control" / "config.ini"
                email, password = "", ""
                if config_file.exists():
                    cfg = configparser.ConfigParser()
                    cfg.read(config_file)
                    email = cfg.get("divoom", "email", fallback="")
                    password = cfg.get("divoom", "password", fallback="")
                
                if not email or not password:
                    return json.dumps({"error": "Divoom account credentials are not configured. Please enter your email and password in the Divoom tab inside Settings."})

                self.cached_creds = divoom_auth.get_credentials()
                
            # FileSize bitmask: 1=16px, 2=32px, 4=64px
            file_size_bitmask = 127
            if target_size == 16:
                file_size_bitmask = 1
            elif target_size == 32:
                file_size_bitmask = 2
            elif target_size == 64:
                file_size_bitmask = 4
                
            body = {
                "Command": "GetCategoryFileListV2",
                "Token": self.cached_creds.token,
                "UserId": self.cached_creds.user_id,
                "DeviceId": self.device_id,
                "Classify": classify,
                "FileSort": 1,
                "FileType": 5,
                "FileSize": file_size_bitmask,
                "Version": 19,
                "StartNum": 1,
                "EndNum": 30,
                "RefreshIndex": 0
            }
            if self.device_pw:
                body["DevicePassword"] = self.device_pw

            url = "https://appin.divoom-gz.com/GetCategoryFileListV2"
            payload = json.dumps(body).encode("utf-8")
            req = urllib.request.Request(
                url,
                data=payload,
                headers={
                    "Content-Type": "application/json; charset=utf-8",
                    "User-Agent": "okhttp/4.12.0",
                },
                method="POST"
            )
            
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                file_list = data.get("FileList", [])
                
                cache_dir = Path(__file__).parent / "web_ui" / "assets" / "cache_gallery"
                cache_dir.mkdir(parents=True, exist_ok=True)
                
                results = []
                for item in file_list:
                    file_id = item.get("FileId")
                    pixel_amb_id = item.get("PixelAmbId")
                    preview_url = ""
                    
                    if file_id:
                        safe_filename = file_id.replace("/", "_")
                        cache_file = cache_dir / safe_filename
                        
                        if not cache_file.exists():
                            try:
                                dl_url = f"https://fin.divoom-gz.com/{file_id}"
                                req_dl = urllib.request.Request(dl_url, headers={"User-Agent": "okhttp/4.12.0"})
                                with urllib.request.urlopen(req_dl, timeout=5) as dl_resp:
                                    raw_bytes = dl_resp.read()
                                    
                                    extracted_gif = self._extract_gif_from_magic_43(raw_bytes)
                                    if extracted_gif:
                                        cache_file = cache_file.with_suffix(".gif")
                                        cache_file.write_bytes(extracted_gif)
                                        logger.info(f"Gallery Cache: Extracted Magic 43 GIF to {cache_file.name}")
                                    elif raw_bytes.startswith(b"GIF89a") or raw_bytes.startswith(b"GIF87a"):
                                        cache_file = cache_file.with_suffix(".gif")
                                        cache_file.write_bytes(raw_bytes)
                                        logger.info(f"Gallery Cache: Saved standard GIF to {cache_file.name}")
                                    else:
                                        if pixel_amb_id:
                                            ext_fb = Path(pixel_amb_id).suffix or ".png"
                                            cache_file_fb = cache_file.with_suffix(ext_fb)
                                            if not cache_file_fb.exists():
                                                dl_url_fb = f"https://fin.divoom-gz.com/{pixel_amb_id}"
                                                req_dl_fb = urllib.request.Request(dl_url_fb, headers={"User-Agent": "okhttp/4.12.0"})
                                                with urllib.request.urlopen(req_dl_fb, timeout=5) as dl_resp_fb:
                                                    cache_file_fb.write_bytes(dl_resp_fb.read())
                                            # Also save the raw binary file for streaming if needed
                                            cache_file_bin = cache_file.with_suffix(".bin")
                                            if not cache_file_bin.exists():
                                                cache_file_bin.write_bytes(raw_bytes)
                                        else:
                                            cache_file_bin = cache_file.with_suffix(".bin")
                                            cache_file_bin.write_bytes(raw_bytes)
                            except Exception as dl_err:
                                logger.warning(f"Failed to cache preview for {file_id}: {dl_err}")
                        
                        for ext in [".gif", ".png", ".jpg", ".bin"]:
                            possible_file = cache_file.with_suffix(ext)
                            if possible_file.exists():
                                preview_url = f"assets/cache_gallery/{possible_file.name}"
                                break
                    
                    results.append({
                        "name": item.get("FileName", "unnamed"),
                        "file_id": file_id,
                        "likes": item.get("LikeCnt", 0),
                        "magic": item.get("FileType", 3),
                        "preview_url": preview_url
                    })
                
                try:
                    gallery_cache = Path.home() / ".config" / "divoom-control" / "gallery_cache.json"
                    gallery_cache.parent.mkdir(parents=True, exist_ok=True)
                    gallery_cache.write_text(json.dumps(results, indent=2), encoding="utf-8")
                    logger.info(f"Gallery Cache: Successfully saved {len(results)} gallery items offline.")
                except Exception as cache_err:
                    logger.warning(f"Failed to save gallery cache: {cache_err}")
                    
                return json.dumps(results)
        except Exception as e:
            logger.error(f"Gallery fetch failed: {e}")
            try:
                gallery_cache = Path.home() / ".config" / "divoom-control" / "gallery_cache.json"
                if gallery_cache.exists():
                    logger.warning("Gallery: Offline fallback loaded from gallery_cache.json")
                    return gallery_cache.read_text(encoding="utf-8")
            except Exception as cache_err:
                logger.error(f"Failed to load gallery cache fallback: {cache_err}")
            return json.dumps({"error": str(e)})

    def batch_sync_artwork(self, artwork_json: str) -> bool:
        """Syncs the selected artwork to all active devices in parallel with automatic PIL resizing."""
        logger.info(f"GUI Action: Batch syncing artwork details: {artwork_json}")
        try:
            art = json.loads(artwork_json)
            file_id = art["file_id"]
            
            logger.info(f"Downloading gallery asset from CDN: {file_id}...")
            dl_url = f"https://fin.divoom-gz.com/{file_id}"
            d_req = urllib.request.Request(dl_url, headers={"User-Agent": "okhttp/4.12.0"})
            
            with urllib.request.urlopen(d_req, timeout=10) as d_resp:
                file_bytes = d_resp.read()
                if len(file_bytes) < 4:
                    return False
                
                targets = []
                if self.wall_slots:
                    if not self._rebuild_wall_instance():
                        return False
                    targets = [d for d, _, _, _, _, _ in self.wall_instance.devices]
                elif self.current_divoom and self.current_divoom.is_connected:
                    targets = [self.current_divoom]
                else:
                    return False
                    
                extracted_gif = self._extract_gif_from_magic_43(file_bytes)
                is_gif = False
                gif_data = None
                
                if extracted_gif:
                    is_gif = True
                    gif_data = extracted_gif
                elif file_bytes.startswith(b"GIF89a") or file_bytes.startswith(b"GIF87a"):
                    is_gif = True
                    gif_data = file_bytes
                
                async def run_sync():
                    sync_tasks = []
                    for divoom in targets:
                        if is_gif:
                            target_size = self._get_device_size(divoom._conn.mac)
                            temp_dir = Path(__file__).parent.parent / "scratch"
                            temp_dir.mkdir(parents=True, exist_ok=True)
                            
                            temp_input = temp_dir / f"sync_in_{divoom._conn.mac}.gif"
                            temp_input.write_bytes(gif_data)
                            
                            temp_output = temp_dir / f"sync_out_{divoom._conn.mac}.gif"
                            
                            try:
                                from PIL import Image
                                with Image.open(temp_input) as img:
                                    frames = []
                                    durations = []
                                    for frame_idx in range(img.n_frames):
                                        img.seek(frame_idx)
                                        resized_frame = img.resize((target_size, target_size), Image.Resampling.NEAREST)
                                        frames.append(resized_frame.convert("RGB"))
                                        durations.append(img.info.get("duration", 100))
                                    
                                    frames[0].save(
                                        temp_output,
                                        save_all=True,
                                        append_images=frames[1:],
                                        duration=durations,
                                        loop=0
                                    )
                                logger.info(f"Sync: Resized GIF to {target_size}x{target_size} for {divoom._conn.mac}")
                                sync_tasks.append(divoom.display.show_image(str(temp_output)))
                            except Exception as resize_err:
                                logger.error(f"Failed to resize GIF: {resize_err}")
                                sync_tasks.append(divoom.display.show_image(str(temp_input)))
                        else:
                            from divoom_lib.monthly_best_daemon import stream_raw_bin_payload
                            sync_tasks.append(stream_raw_bin_payload(divoom, file_bytes))
                            
                    results = await asyncio.gather(*sync_tasks, return_exceptions=True)
                    return all(res is True for res in results)
                    
                return self._run_async(run_sync())
        except Exception as e:
            logger.error(f"Batch sync failed: {e}")
            return False

    def _music_sync_loop(self):
        """Background thread polling macOS active playback and streaming artwork."""
        last_track = None
        last_artist = None
        while self.music_sync_active:
            try:
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
                            size = 16
                            out_path = media_source.render_and_downsample_artwork(art_url, size=size)
                            if out_path and out_path.exists():
                                logger.info(f"Music Sync: Push cover art frame: {out_path}")
                                try:
                                    if self.wall_slots:
                                        if self._rebuild_wall_instance(size):
                                            self._run_async(self.wall_instance.show_image(str(out_path)))
                                    elif self.current_divoom and self.current_divoom.is_connected:
                                        self._run_async(self.current_divoom.display.show_image(str(out_path)))
                                except Exception as e:
                                    logger.error(f"Failed to stream artwork: {e}")
                                    
                            self.current_track_cache = {
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

    def apply_stock_ticker(self, symbol: str) -> str:
        logger.info(f"GUI Action: Applying stock ticker for {symbol}...")
        try:
            data = media_source.fetch_stock_ticker(symbol)
            if not data:
                return json.dumps({"success": False})
                
            size = 16
            frame_path = media_source.render_stock_ticker_frame(symbol, data, size=size)
            
            res = False
            if self.wall_slots:
                if self._rebuild_wall_instance(size):
                    res = self._run_async(self.wall_instance.show_image(str(frame_path)))
            elif self.current_divoom and self.current_divoom.is_connected:
                res = self._run_async(self.current_divoom.display.show_image(str(frame_path)))
                
            return json.dumps({
                "success": res,
                "price": data["price"],
                "change": data["change"],
                "pct_change": data["pct_change"]
            })
        except Exception as e:
            logger.error(f"Failed to apply stock ticker: {e}")
            return json.dumps({"success": False, "error": str(e)})
