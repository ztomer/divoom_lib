# divoom_api/commands/temp_weather.py
from ..base import DivoomBase
from ..constants import WeatherType
from typing import Optional, Dict, Any
import asyncio

class TempWeatherCommand:
    """
    This class is used to set the temperature and weather on the Divoom Timebox Evo.
    """
    _PACKAGE_PREFIX = "5F"

    def __init__(self, divoom_instance: DivoomBase, opts: Optional[Dict[str, Any]] = None):
        self._divoom_instance = divoom_instance
        self._opts = {
            "temperature": 0,
            "weather": WeatherType.Clear
        }
        if opts:
            self._opts.update(opts)

    async def update_temp_weather(self):
        """
        Manually triggers an update to set the temperature and weather on the Divoom device.
        """
        await self._update_message()

    async def _update_message(self):
        """
        Updates the message queue based on the parameters used.
        """
        if not (-127 <= self._opts["temperature"] <= 128):
            raise ValueError("Temperature should be between -127 and 128")

        encoded_temp = self._divoom_instance.number2HexString(
            self._opts["temperature"] if self._opts["temperature"] >= 0 else (256 + self._opts["temperature"])
        )
        weather_hex = self._divoom_instance.number2HexString(self._opts["weather"])

        # The Node.js version constructs a string like:
        # _PACKAGE_PREFIX + encodedTemp + number2HexString(this._opts.weather)
        # This implies the command is the _PACKAGE_PREFIX (5F), and the rest are arguments.
        
        command_code = int(self._PACKAGE_PREFIX, 16) # 0x5F
        args = [int(encoded_temp, 16), int(weather_hex, 16)]

        await self._divoom_instance.send_command(command_code, args)

    @property
    def temperature(self) -> int:
        return self._opts["temperature"]

    @temperature.setter
    def temperature(self, value: int):
        self._opts["temperature"] = value

    @property
    def weather(self) -> int:
        return self._opts["weather"]

    @weather.setter
    def weather(self, value: int):
        self._opts["weather"] = value
