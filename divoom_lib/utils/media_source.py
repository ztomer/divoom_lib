#!/usr/bin/env python3
"""
media_source.py — Advanced data sources for Divoom displays.
Fetches live macOS album artwork (Spotify/Apple Music), current date/time widgets,
and stock/crypto tickers, rendering them dynamically onto pixel grids.
"""

import os
import subprocess
import urllib.request
import json
import logging
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

logger = logging.getLogger(__name__)

def get_current_playing_track() -> dict | None:
    """
    Queries Spotify and Apple Music on macOS using AppleScript.
    Returns: {"track": str, "artist": str, "source": str} or None.
    """
    # 1. Check Spotify
    spotify_script = """
    if application "Spotify" is running then
        tell application "Spotify"
            if player state is playing then
                return name of current track & " -|- " & artist of current track
            end if
        end tell
    end if
    return ""
    """
    try:
        proc = subprocess.run(["osascript", "-e", spotify_script], capture_output=True, text=True, timeout=2)
        res = proc.stdout.strip()
        if res and "-|-" in res:
            parts = res.split(" -|- ")
            return {"track": parts[0], "artist": parts[1], "source": "Spotify"}
    except Exception as e:
        logger.debug(f"Spotify AppleScript check failed: {e}")

    # 2. Check Apple Music (Music.app)
    music_script = """
    if application "Music" is running then
        tell application "Music"
            if player state is playing then
                return name of current track & " -|- " & artist of current track
            end if
        end tell
    end if
    return ""
    """
    try:
        proc = subprocess.run(["osascript", "-e", music_script], capture_output=True, text=True, timeout=2)
        res = proc.stdout.strip()
        if res and "-|-" in res:
            parts = res.split(" -|- ")
            return {"track": parts[0], "artist": parts[1], "source": "Apple Music"}
    except Exception as e:
        logger.debug(f"Apple Music AppleScript check failed: {e}")

    return None


def fetch_album_art_url(track: str, artist: str) -> str | None:
    """Queries iTunes search API to find the album cover artwork URL."""
    try:
        term = f"{artist} {track}"
        url_encoded = urllib.parse.quote(term)
        api_url = f"https://itunes.apple.com/search?term={url_encoded}&limit=1&entity=song"
        
        req = urllib.request.Request(api_url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            results = data.get("results", [])
            if results:
                # Get high-resolution 100x100 artwork and replace size with 500x500
                artwork_url = results[0].get("artworkUrl100")
                if artwork_url:
                    return artwork_url.replace("100x100bb.jpg", "500x500bb.jpg")
    except Exception as e:
        logger.warning(f"iTunes album artwork search failed: {e}")
    return None


def render_and_downsample_artwork(artwork_url: str, size: int = 16) -> Path | None:
    """Downloads an artwork cover and downsamples it to Divoom grid resolution using a SOTA pipeline."""
    try:
        scratch_dir = Path(__file__).parent.parent.parent / "scratch"
        scratch_dir.mkdir(parents=True, exist_ok=True)
        out_path = scratch_dir / f"album_art_{size}.png"
        
        req = urllib.request.Request(artwork_url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=8) as resp:
            raw_img_data = resp.read()
            
            from io import BytesIO
            from PIL import ImageEnhance, ImageFilter
            img = Image.open(BytesIO(raw_img_data))
            
            # 1. Pre-process original high-res image (convert to RGB, enhance contrast & sharpness)
            img_rgb = img.convert("RGB")
            contrast_enhancer = ImageEnhance.Contrast(img_rgb)
            img_enhanced = contrast_enhancer.enhance(1.2)
            sharpness_enhancer = ImageEnhance.Sharpness(img_enhanced)
            img_enhanced = sharpness_enhancer.enhance(1.3)
            
            # 2. Smooth downscale using LANCZOS
            try:
                resample_filter = Image.Resampling.LANCZOS
            except AttributeError:
                try:
                    resample_filter = Image.LANCZOS
                except AttributeError:
                    resample_filter = Image.ANTIALIAS
            
            resized_img = img_enhanced.resize((size, size), resample_filter)
            
            # 3. Post-downscale sharpening
            sharpened_img = resized_img.filter(ImageFilter.SHARPEN)
            
            # 4. Quantize to adaptive 64-color palette with dithering for retro pixel-art look
            dither_val = Image.Dither.FLOYDSTEINBERG if hasattr(Image, 'Dither') else 1
            quantized_img = sharpened_img.quantize(colors=64, dither=dither_val)
            
            # 5. Convert back to RGB for device/display compatibility
            final_img = quantized_img.convert("RGB")
            final_img.save(out_path)
            return out_path
    except Exception as e:
        logger.error(f"Downsampling artwork failed: {e}")
    return None


def fetch_stock_ticker(symbol: str) -> dict | None:
    """
    Fetches live stock or crypto price using Yahoo Finance public API.
    symbol: e.g. "AAPL", "GOOG", "BTC-USD".
    """
    try:
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?interval=2m"
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            chart = data.get("chart", {})
            result = chart.get("result", [])
            if result:
                meta = result[0].get("meta", {})
                price = meta.get("regularMarketPrice")
                prev_close = meta.get("chartPreviousClose")
                change = price - prev_close if price and prev_close else 0
                pct_change = (change / prev_close) * 100 if prev_close else 0
                return {
                    "price": round(price, 2) if price else 0,
                    "change": round(change, 2),
                    "pct_change": round(pct_change, 2)
                }
    except Exception as e:
        logger.warning(f"Yahoo stock price query for {symbol} failed: {e}")
    return None


def render_stock_ticker_frame(symbol: str, data: dict, size: int = 16) -> Path:
    """
    Renders a neat visual stock ticker to fit Divoom grid dimensions (16x16 or 32x32).
    Shows the symbol name, current price, and green up-arrow / red down-arrow indicating change.
    """
    scratch_dir = Path(__file__).parent.parent.parent / "scratch"
    scratch_dir.mkdir(parents=True, exist_ok=True)
    out_path = scratch_dir / f"ticker_{symbol}_{size}.png"
    
    img = Image.new("RGB", (size, size), (5, 6, 12)) # Dark slate bg
    draw = ImageDraw.Draw(img)
    
    # Text colors
    is_up = data["change"] >= 0
    text_color = (0, 255, 180) if is_up else (255, 60, 60) # Green vs Red
    
    if size == 16:
        # Mini 16x16 layout
        # Render a simple colored arrow and mini price
        if is_up:
            # Draw green up arrow
            draw.polygon([(8, 2), (4, 7), (12, 7)], fill=text_color)
            draw.rectangle([(6, 7), (10, 10)], fill=text_color)
        else:
            # Draw red down arrow
            draw.polygon([(8, 10), (4, 5), (12, 5)], fill=text_color)
            draw.rectangle([(6, 2), (10, 5)], fill=text_color)
            
        # Draw symbol/text in 1px outline
        draw.text((1, 11), symbol[:3].upper(), fill=(255,255,255))
    else:
        # 32x32 layout allows typography
        # Draw symbol name
        draw.text((2, 2), symbol.upper()[:4], fill=(255, 255, 255))
        # Draw arrow
        if is_up:
            draw.polygon([(24, 6), (20, 12), (28, 12)], fill=text_color)
        else:
            draw.polygon([(24, 12), (20, 6), (28, 6)], fill=text_color)
        # Draw price
        draw.text((2, 14), f"${data['price']}", fill=text_color)
        
    img.save(out_path)
    return out_path


def get_system_stats() -> dict:
    """Return live host metrics for an on-device system monitor (ported from the
    Wi-Fi-only Pixoo64-Advanced-Tools concept, rendered to a frame for BLE)."""
    try:
        import psutil
        cpu = psutil.cpu_percent(interval=0.0)
        mem = psutil.virtual_memory().percent
        battery = None
        try:
            b = psutil.sensors_battery()
            battery = int(b.percent) if b else None
        except Exception:
            battery = None
        return {"cpu": round(cpu), "mem": round(mem), "battery": battery}
    except Exception as e:
        logger.warning(f"get_system_stats failed: {e}")
        return {"cpu": 0, "mem": 0, "battery": None}


def render_system_stats_frame(stats: dict, size: int = 16) -> Path:
    """Render CPU, RAM, and Battery as three labeled bar gauges sized to the
    device matrix. Mirrors render_stock_ticker_frame's approach."""
    scratch_dir = Path(__file__).parent.parent.parent / "scratch"
    scratch_dir.mkdir(parents=True, exist_ok=True)
    out_path = scratch_dir / f"sysmon_{size}.png"

    img = Image.new("RGB", (size, size), (5, 6, 12))
    draw = ImageDraw.Draw(img)

    def draw_gauge(x, y, w_max, h, value, color):
        draw.rectangle([(x, y), (x + w_max - 1, y + h - 1)], outline=(40, 42, 54))
        frac = max(0.0, min(1.0, value / 100.0))
        w_fill = max(1, int(round((w_max - 2) * frac)))
        if w_fill > 0:
            draw.rectangle([(x + 1, y + 1), (x + w_fill, y + h - 2)], fill=color)

    cpu = stats.get("cpu", 0)
    mem = stats.get("mem", 0)
    bat = stats.get("battery")
    if bat is None:
        bat = 100

    cpu_color = (0, 255, 180) if cpu < 70 else (255, 60, 60)
    mem_color = (90, 170, 255) if mem < 80 else (255, 140, 0)
    bat_color = (0, 255, 100) if bat > 25 else (255, 60, 60)

    if size <= 16:
        # CPU Label + Bar at y=1
        draw.text((1, -1), "C", fill=(255, 255, 255))
        draw_gauge(6, 1, 9, 3, cpu, cpu_color)
        # MEM Label + Bar at y=6
        draw.text((1, 4), "M", fill=(255, 255, 255))
        draw_gauge(6, 6, 9, 3, mem, mem_color)
        # BAT Label + Bar at y=11
        draw.text((1, 9), "B", fill=(255, 255, 255))
        draw_gauge(6, 11, 9, 3, bat, bat_color)
    else:
        # Larger layouts (e.g. 32x32, 64x64)
        scale = size / 32.0
        
        y_cpu_text = int(round(0 * scale))
        y_cpu_bar = int(round(6 * scale))
        y_mem_text = int(round(10 * scale))
        y_mem_bar = int(round(16 * scale))
        y_bat_text = int(round(20 * scale))
        y_bat_bar = int(round(26 * scale))
        
        bar_w = int(round(28 * scale))
        bar_h = int(round(3 * scale))
        
        if bar_h < 3:
            bar_h = 3
            
        draw.text((2, y_cpu_text), f"CPU {cpu}%", fill=cpu_color)
        draw_gauge(2, y_cpu_bar, bar_w, bar_h, cpu, cpu_color)
        
        draw.text((2, y_mem_text), f"MEM {mem}%", fill=mem_color)
        draw_gauge(2, y_mem_bar, bar_w, bar_h, mem, mem_color)
        
        draw.text((2, y_bat_text), f"BAT {bat}%", fill=bat_color)
        draw_gauge(2, y_bat_bar, bar_w, bar_h, bat, bat_color)

    img.save(out_path)
    return out_path


def render_notification_frame(app_name: str, size: int = 16) -> Path:
    """
    Renders a pixel-art notification frame for Mail, WhatsApp, or Telegram.
    Saves it as a PNG and returns the path.
    """
    scratch_dir = Path(__file__).parent.parent.parent / "scratch"
    scratch_dir.mkdir(parents=True, exist_ok=True)
    out_path = scratch_dir / f"notification_{app_name}_{size}.png"
    
    img = Image.new("RGB", (size, size), (5, 6, 12)) # Dark slate bg
    draw = ImageDraw.Draw(img)
    
    app_lower = app_name.lower()
    scale = size / 16.0
    
    if app_lower == "mail":
        # Draw a beautiful retro envelope
        left = int(2 * scale)
        top = int(4 * scale)
        right = int(13 * scale)
        bottom = int(11 * scale)
        
        draw.rectangle([(left, top), (right, bottom)], fill=(40, 42, 54), outline=(255, 255, 255))
        mid_x = int(7 * scale)
        mid_y = int(8 * scale)
        draw.line([(left, top), (mid_x, mid_y)], fill=(255, 60, 60))
        draw.line([(right, top), (mid_x, mid_y)], fill=(255, 60, 60))
        
    elif app_lower == "whatsapp":
        # Draw a WhatsApp green chat bubble
        bubble_left = int(2 * scale)
        bubble_top = int(2 * scale)
        bubble_right = int(13 * scale)
        bubble_bottom = int(11 * scale)
        draw.ellipse([(bubble_left, bubble_top), (bubble_right, bubble_bottom)], fill=(34, 197, 94))
        
        tail_points = [
            (int(4 * scale), int(10 * scale)),
            (int(2 * scale), int(13 * scale)),
            (int(7 * scale), int(11 * scale))
        ]
        draw.polygon(tail_points, fill=(34, 197, 94))
        
        mid = size / 2.0
        draw.arc([(mid - 2*scale, mid - 2*scale), (mid + 2*scale, mid + 2*scale)], 180, 360, fill=(255, 255, 255), width=max(1, int(1.5*scale)))
        
    elif app_lower == "telegram":
        # Draw a paper airplane in a blue circle
        draw.ellipse([(int(1*scale), int(1*scale)), (int(14*scale), int(14*scale))], fill=(14, 165, 233))
        
        points = [
            (int(11 * scale), int(4 * scale)),
            (int(4 * scale), int(8 * scale)),
            (int(7 * scale), int(9 * scale))
        ]
        draw.polygon(points, fill=(255, 255, 255))
        points2 = [
            (int(11 * scale), int(4 * scale)),
            (int(7 * scale), int(9 * scale)),
            (int(9 * scale), int(11 * scale))
        ]
        draw.polygon(points2, fill=(224, 242, 254))
        
    else:
        # Generic yellow alert bell
        draw.ellipse([(int(5*scale), int(3*scale)), (int(10*scale), int(9*scale))], fill=(245, 158, 11))
        draw.rectangle([(int(3*scale), int(9*scale)), (int(12*scale), int(11*scale))], fill=(245, 158, 11))
        draw.ellipse([(int(7*scale), int(11*scale)), (int(8*scale), int(12*scale))], fill=(255, 255, 255))

    img.save(out_path)
    return out_path
