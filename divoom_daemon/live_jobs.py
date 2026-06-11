import asyncio
import logging
from pathlib import Path
from divoom_lib.utils import media_source

logger = logging.getLogger("divoom_daemon.live_jobs")

async def _push_image_coro(device_owner, mac, params, frame_path):
    dev = await device_owner.get_live_device(mac, params)
    if not getattr(dev, "is_connected", False):
        await dev.connect()
    await dev.display.show_image(str(frame_path))

async def push_image_to_device(device_owner, mac, params, frame_path):
    coro = _push_image_coro(device_owner, mac, params, frame_path)
    return await device_owner._cmd_queue.submit_async(coro)

async def _push_weather_coro(device_owner, mac, params, temp_c, weather_type):
    from divoom_lib.system.weather import Weather
    from divoom_lib.models import COMMANDS
    dev = await device_owner.get_live_device(mac, params)
    if not getattr(dev, "is_connected", False):
        await dev.connect()
    await dev.send_command(
        COMMANDS["set light mode"],
        [0x01, 0x00, 0xFF, 0xFF, 0xFF, 0x00],
    )
    await Weather(dev).set(temp_c, weather_type)

async def push_weather_to_device(device_owner, mac, params, temp_c, weather_type):
    coro = _push_weather_coro(device_owner, mac, params, temp_c, weather_type)
    return await device_owner._cmd_queue.submit_async(coro)

async def run_sysmon(device_owner, mac: str, params: dict):
    size = int(params.get("size", 16))
    logger.info(f"Starting sysmon loop for {mac} (size={size})")
    while True:
        try:
            stats = media_source.get_system_stats()
            frame_path = media_source.render_system_stats_frame(stats, size=size)
            await push_image_to_device(device_owner, mac, params, frame_path)
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.error(f"Sysmon sync loop error for {mac}: {e}")
        await asyncio.sleep(5.0)

async def run_stocks(device_owner, mac: str, params: dict):
    symbol = params.get("symbol", "").upper()
    if not symbol:
        logger.warning(f"Stocks loop for {mac} started without symbol")
        return
    size = int(params.get("size", 16))
    logger.info(f"Starting stocks loop for {mac} (symbol={symbol}, size={size})")
    while True:
        try:
            data = media_source.fetch_stock_ticker(symbol)
            if data:
                frame_path = media_source.render_stock_ticker_frame(symbol, data, size=size)
                await push_image_to_device(device_owner, mac, params, frame_path)
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.error(f"Stocks sync loop error for {mac} ({symbol}): {e}")
        await asyncio.sleep(15.0)

async def run_weather(device_owner, mac: str, params: dict):
    logger.info(f"Starting weather loop for {mac}")
    from divoom_lib.weather_provider import get_weather
    while True:
        try:
            info = await get_weather()
            await push_weather_to_device(device_owner, mac, params, info.temperature_c, info.weather_type)
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.error(f"Weather sync loop error for {mac}: {e}")
        await asyncio.sleep(15.0 * 60)

async def run_music(device_owner, mac: str, params: dict):
    size = int(params.get("size", 16))
    logger.info(f"Starting music loop for {mac} (size={size})")
    last_track = None
    last_artist = None
    while True:
        try:
            track_info = media_source.get_current_playing_track()
            if track_info:
                track = track_info.get("track")
                artist = track_info.get("artist")
                if track != last_track or artist != last_artist:
                    last_track = track
                    last_artist = artist
                    art_url = media_source.fetch_album_art_url(track, artist)
                    if art_url:
                        out_path = media_source.render_and_downsample_artwork(art_url, size=size)
                        if out_path and out_path.exists():
                            await push_image_to_device(device_owner, mac, params, out_path)
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.error(f"Music sync loop error for {mac}: {e}")
        await asyncio.sleep(1.5)
