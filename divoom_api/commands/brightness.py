# divoom_api/commands/brightness.py
from ..base import DivoomBase
from typing import Optional, Dict, Any
import asyncio

class BrightnessCommand:
    """
    This class is used to change the brightness on the Divoom Timebox Evo.
    """
    _PACKAGE_PREFIX = "74"

    def __init__(self, divoom_instance: DivoomBase, opts: Optional[Dict[str, Any]] = None):
        self._divoom_instance = divoom_instance
        self._opts = {
            "brightness": 100,
            "in_min": 0,
            "in_max": 100
        }
        if opts:
            self._opts.update(opts)
        asyncio.create_task(self._update_message())

    def _map(self, x: int, in_min: int, in_max: int, out_min: int, out_max: int) -> int:
        """
        Maps a value from one range to another.
        """
        if x < in_min or x > in_max:
            raise ValueError("map() in_min is < value or in_max > value")
        return int(((x - in_min) * (out_max - out_min)) / (in_max - in_min) + out_min)

    async def _update_message(self):
        """
        Updates the message queue based on the parameters used.
        """
        if (self._opts["brightness"] > 100 or self._opts["brightness"] < 0) and \
           (self._opts["in_min"] is None or self._opts["in_max"] is None):
            raise ValueError(
                "Brightness should be between 0 and 100 or in_min and in_max should be defined"
            )
        
        bri_in_range = self._opts["brightness"]
        if self._opts["in_min"] is not None and self._opts["in_max"] is not None:
            bri_in_range = self._map(
                self._opts["brightness"],
                self._opts["in_min"],
                self._opts["in_max"],
                0,
                100
            )
        
        brightness_hex = self._divoom_instance.number2HexString(bri_in_range)

        # The Node.js version constructs a string like:
        # _PACKAGE_PREFIX + number2HexString(briInRange)
        # This implies the command is the _PACKAGE_PREFIX (74), and the rest are arguments.
        
        command_code = int(self._PACKAGE_PREFIX, 16) # 0x74
        args = [int(brightness_hex, 16)]

        await self._divoom_instance.send_command(command_code, args)

    @property
    def brightness(self) -> int:
        return self._opts["brightness"]

    @brightness.setter
    def brightness(self, value: int):
        self._opts["brightness"] = value
        asyncio.create_task(self._update_message())

    @property
    def in_min(self) -> int:
        return self._opts["in_min"]

    @in_min.setter
    def in_min(self, value: int):
        self._opts["in_min"] = value
        asyncio.create_task(self._update_message())

    @property
    def in_max(self) -> int:
        return self._opts["in_max"]

    @in_max.setter
    def in_max(self, value: int):
        self._opts["in_max"] = value
        asyncio.create_task(self._update_message())

    @property
    def opts(self) -> Dict[str, Any]:
        return self._opts

    @opts.setter
    def opts(self, value: Dict[str, Any]):
        self._opts.update(value)
        asyncio.create_task(self._update_message())
