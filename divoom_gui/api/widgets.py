"""WidgetsApi — weather/stocks/sysmon/cover-art (REVIEW §1.2).

Extracts the live widget surface.
"""
from __future__ import annotations

import json
import asyncio
import logging
from divoom_gui.api import ApiBase

logger = logging.getLogger("divoom_gui.api.widgets")


class WidgetsApi(ApiBase):
    def __init__(self, loop_thread, daemon_client_getter, state_getter):
        super().__init__(loop_thread, daemon_client_getter, state_getter)

    def push_weather(self) -> bool:
        from divoom_lib.system.weather import Weather
        from divoom_lib.weather_provider import get_weather

        async def _push(d):
            info = await get_weather()
            return await Weather(d).set(info.temperature_c, info.weather_type)

        return self._tool_call(_push, "weather")

    def _tool_call(self, fn, label: str) -> bool:
        logger.info(f"GUI Action: Tool {label}...")
        try:
            target = self._current_divoom
            if not target:
                return False
            return bool(self._run_async(fn(target)))
        except Exception as e:
            logger.error(f"tool {label} failed: {e}")
            return False

    def get_weather(self) -> dict:
        from divoom_lib.weather_provider import get_weather
        from divoom_lib.models import WeatherType

        async def _gather():
            info = await get_weather()
            return {
                "temperature_c": info.temperature_c,
                "weather_type": info.weather_type,
                "location": info.location,
                "provider": info.provider,
                "fetched_at": info.fetched_at,
            }

        try:
            return asyncio.run(_gather())
        except Exception as exc:
            logger.warning("get_weather failed: %s", exc)
            return {
                "temperature_c": 0,
                "weather_type": int(WeatherType.Clear),
                "location": "error",
                "provider": "stub",
                "fetched_at": 0.0,
                "error": str(exc),
            }