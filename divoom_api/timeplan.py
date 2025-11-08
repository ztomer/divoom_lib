"""
Divoom Timeplan Commands
"""

from .base import DivoomCommand

class Timeplan:
    SET_TIME_MANAGE_INFO = DivoomCommand(0x56)
    SET_TIME_MANAGE_CTRL = DivoomCommand(0x57)

    async def set_time_manage_info(self, total_records: int, record_id: int, start_hour: int, start_min: int, end_hour: int, end_min: int, total_time: int, voice_alarm_on_off: int, display_mode: int, cycle_mode: int, pic_len: int, pic_data: list):
        """Set time management information (0x56)."""
        self.logger.info(f"Setting time manage info (0x56)...")
        args = []
        args += total_records.to_bytes(1, byteorder='big')
        args += record_id.to_bytes(1, byteorder='big')
        args += start_hour.to_bytes(1, byteorder='big')
        args += start_min.to_bytes(1, byteorder='big')
        args += end_hour.to_bytes(1, byteorder='big')
        args += end_min.to_bytes(1, byteorder='big')
        args += total_time.to_bytes(1, byteorder='big')
        args += voice_alarm_on_off.to_bytes(1, byteorder='big')
        args += display_mode.to_bytes(1, byteorder='big')
        args += cycle_mode.to_bytes(1, byteorder='big')
        args += pic_len.to_bytes(2, byteorder='little')
        args.extend(pic_data)
        return await self.send_command("set time manage info", args)

    async def set_time_manage_control(self, control: int):
        """Control time management (0x57)."""
        self.logger.info(f"Setting time manage control to {control} (0x57)...")
        args = [control]
        return await self.send_command("set time manage ctrl", args)