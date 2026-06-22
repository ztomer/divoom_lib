import asyncio
import logging
from pathlib import Path
from divoom_lib.utils import media_source

logger = logging.getLogger("divoom_daemon.live_jobs")

_MAX_BACKOFF = 60.0


async def _backoff_sleep(interval: float, fails: int) -> None:
    """Sleep the normal interval on success (fails==0); on CONSECUTIVE failures
    grow toward _MAX_BACKOFF. Without this a permanently-dead device is hammered
    with a fresh ensure_connected (~16s/attempt) every tick — a reconnect storm.
    Never sleeps LESS than the normal interval (a long-interval poller like weather,
    900s > _MAX_BACKOFF, must not be sped UP by the cap on failure)."""
    if fails <= 0:
        await asyncio.sleep(interval)
    else:
        await asyncio.sleep(max(interval, min(_MAX_BACKOFF, interval * (2 ** min(fails, 6)))))

async def _ensure_live_device(device_owner, mac, params):
    """BLE Hardening P2: hand back a device that's genuinely ALIVE, self-healing
    a dropped link with Phase 1's bounded retry. Raises a typed reason when it
    can't recover so the loop logs + skips that tick instead of blasting a dead
    link (the OS disconnect_callback already flipped is_alive to False)."""
    from divoom_lib.ble_connection import ensure_connected, BleConnectionError
    dev = await device_owner.get_live_device(mac, params)
    if not getattr(dev, "is_alive", getattr(dev, "is_connected", False)):
        res = await ensure_connected(dev, attempts=2, attempt_timeout=8.0)
        if not res.ok:
            raise BleConnectionError(res)
    return dev


async def _push_image_coro(device_owner, mac, params, frame_path):
    dev = await _ensure_live_device(device_owner, mac, params)
    await dev.display.show_image(str(frame_path))

async def push_image_to_device(device_owner, mac, params, frame_path):
    coro = _push_image_coro(device_owner, mac, params, frame_path)
    return await device_owner._cmd_queue.submit_async(coro)

async def _push_weather_coro(device_owner, mac, params, temp_c, weather_type):
    from divoom_lib.system.weather import Weather
    from divoom_lib.models import COMMANDS
    dev = await _ensure_live_device(device_owner, mac, params)
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
    fails = 0
    while True:
        try:
            # psutil read off the BLE event loop (render is a fast small-canvas
            # PIL op writing a shared scratch path — left on-loop so concurrent
            # device pollers can't race that file).
            stats = await asyncio.to_thread(media_source.get_system_stats)
            frame_path = media_source.render_system_stats_frame(stats, size=size)
            await push_image_to_device(device_owner, mac, params, frame_path)
            fails = 0
        except asyncio.CancelledError:
            raise
        except Exception as e:
            fails += 1
            logger.error(f"Sysmon sync loop error for {mac}: {e}")
        await _backoff_sleep(5.0, fails)

async def run_stocks(device_owner, mac: str, params: dict):
    symbol = params.get("symbol", "").upper()
    if not symbol:
        logger.warning(f"Stocks loop for {mac} started without symbol")
        return
    size = int(params.get("size", 16))
    logger.info(f"Starting stocks loop for {mac} (symbol={symbol}, size={size})")
    fails = 0
    while True:
        try:
            data = await asyncio.to_thread(media_source.fetch_stock_ticker, symbol)  # urllib off the loop
            if data:
                frame_path = media_source.render_stock_ticker_frame(symbol, data, size=size)
                await push_image_to_device(device_owner, mac, params, frame_path)
            fails = 0
        except asyncio.CancelledError:
            raise
        except Exception as e:
            fails += 1
            logger.error(f"Stocks sync loop error for {mac} ({symbol}): {e}")
        await _backoff_sleep(15.0, fails)

async def run_weather(device_owner, mac: str, params: dict):
    logger.info(f"Starting weather loop for {mac}")
    from divoom_lib.weather_provider import get_weather
    fails = 0
    while True:
        try:
            info = await get_weather()
            await push_weather_to_device(device_owner, mac, params, info.temperature_c, info.weather_type)
            fails = 0
        except asyncio.CancelledError:
            raise
        except Exception as e:
            fails += 1
            logger.error(f"Weather sync loop error for {mac}: {e}")
        await _backoff_sleep(15.0 * 60, fails)

async def run_music(device_owner, mac: str, params: dict):
    size = int(params.get("size", 16))
    logger.info(f"Starting music loop for {mac} (size={size})")
    last_track = None
    last_artist = None
    fails = 0
    while True:
        try:
            # get_current_playing_track runs up to TWO blocking osascript
            # subprocesses (Spotify, then Music.app) — at the 1.5s music cadence
            # that would stall the shared BLE event loop ~80×/min. Off-load it.
            track_info = await asyncio.to_thread(media_source.get_current_playing_track)
            if track_info:
                track = track_info.get("track")
                artist = track_info.get("artist")
                if track != last_track or artist != last_artist:
                    art_url = await asyncio.to_thread(media_source.fetch_album_art_url, track, artist)
                    if art_url:
                        out_path = media_source.render_and_downsample_artwork(art_url, size=size)
                        if out_path and out_path.exists():
                            await push_image_to_device(device_owner, mac, params, out_path)
                    # only mark this track "shown" once the push SUCCEEDS, so a failed
                    # push to a dead device retries on the next tick (not only when the
                    # track changes again).
                    last_track = track
                    last_artist = artist
            fails = 0
        except asyncio.CancelledError:
            raise
        except Exception as e:
            fails += 1
            logger.error(f"Music sync loop error for {mac}: {e}")
        await _backoff_sleep(1.5, fails)
