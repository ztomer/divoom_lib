# divoom_api/commands/date_time.py
from ..base import DivoomBase
import datetime
from typing import Optional, Dict, Any
import asyncio

class DateTimeCommand:
    """
    This class is used to set the date and time on the Divoom Timebox Evo.
    """
    _PACKAGE_PREFIX = "18"

    def __init__(self, divoom_instance: DivoomBase, opts: Optional[Dict[str, Any]] = None):
        self._divoom_instance = divoom_instance
        self._opts = {
            "date": datetime.datetime.now()
        }
        if opts:
            self._opts.update(opts)
        asyncio.create_task(self._update_message())

    async def _update_message(self):
        """
        Updates the message queue based on the parameters used.
        """
        current_date = self._opts["date"]

        # Node.js code:
        # number2HexString(Number(this._opts.date.getFullYear().toString().padStart(4, "0").slice(2)))
        # + number2HexString(Number(this._opts.date.getFullYear().toString().padStart(4, "0").slice(0, 2)))
        # + number2HexString(this._opts.date.getMonth() + 1)
        # + number2HexString(this._opts.date.getDate())
        # + number2HexString(this._opts.date.getHours())
        # + number2HexString(this._opts.date.getMinutes())
        # + number2HexString(this._opts.date.getSeconds())
        # + "00";

        year_full = current_date.year
        year_lsb = self._divoom_instance.number2HexString(year_full % 100)
        year_msb = self._divoom_instance.number2HexString(year_full // 100)
        month = self._divoom_instance.number2HexString(current_date.month)
        day = self._divoom_instance.number2HexString(current_date.day)
        hour = self._divoom_instance.number2HexString(current_date.hour)
        minute = self._divoom_instance.number2HexString(current_date.minute)
        second = self._divoom_instance.number2HexString(current_date.second)

        time_string_hex = year_lsb + year_msb + month + day + hour + minute + second + "00"
        
        command_code = int(self._PACKAGE_PREFIX, 16) # 0x18
        args = [int(time_string_hex[i:i+2], 16) for i in range(0, len(time_string_hex), 2)]

        await self._divoom_instance.send_command(command_code, args)

    @property
    def date(self) -> datetime.datetime:
        return self._opts["date"]

    @date.setter
    def date(self, value: datetime.datetime):
        self._opts["date"] = value
        asyncio.create_task(self._update_message())
