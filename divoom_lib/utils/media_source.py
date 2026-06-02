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
    """Downloads an artwork cover and downsamples it to Divoom grid resolution."""
    try:
        scratch_dir = Path(__file__).parent.parent.parent / "scratch"
        scratch_dir.mkdir(parents=True, exist_ok=True)
        out_path = scratch_dir / f"album_art_{size}.png"
        
        req = urllib.request.Request(artwork_url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=8) as resp:
            raw_img_data = resp.read()
            
            # Use Pillow to downsample
            from io import BytesIO
            img = Image.open(BytesIO(raw_img_data))
            resized_img = img.resize((size, size), Image.NEAREST)
            resized_img.save(out_path)
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
    """Render CPU/RAM (and battery) as two labelled bar gauges sized to the
    device matrix. Mirrors render_stock_ticker_frame's approach."""
    scratch_dir = Path(__file__).parent.parent.parent / "scratch"
    scratch_dir.mkdir(parents=True, exist_ok=True)
    out_path = scratch_dir / f"sysmon_{size}.png"

    img = Image.new("RGB", (size, size), (5, 6, 12))
    draw = ImageDraw.Draw(img)

    def bar(y, frac, color, h):
        frac = max(0.0, min(1.0, frac / 100.0))
        w = max(1, int(round((size - 2) * frac)))
        draw.rectangle([(1, y), (size - 2, y + h)], outline=(40, 42, 54))
        if w > 0:
            draw.rectangle([(1, y), (1 + w, y + h)], fill=color)

    cpu = stats.get("cpu", 0)
    mem = stats.get("mem", 0)
    cpu_color = (0, 255, 180) if cpu < 70 else (255, 60, 60)
    mem_color = (90, 170, 255) if mem < 80 else (255, 140, 0)

    if size <= 16:
        draw.text((1, 0), "C", fill=(255, 255, 255))
        bar(6, cpu, cpu_color, 2)
        draw.text((1, 8), "M", fill=(255, 255, 255))
        bar(13, mem, mem_color, 2)
    else:
        draw.text((2, 1), f"CPU {cpu}%", fill=cpu_color)
        bar(10, cpu, cpu_color, 4)
        draw.text((2, 17), f"MEM {mem}%", fill=mem_color)
        bar(26, mem, mem_color, 4)

    img.save(out_path)
    return out_path
