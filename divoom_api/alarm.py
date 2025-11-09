"""
Divoom Alarm and Memorial Commands
"""
import datetime

class Alarm:
    def __init__(self, communicator):
        self.communicator = communicator
        self.logger = communicator.logger
    async def get_alarm_time(self):
        """Get alarm time (0x42)."""
        self.communicator.logger.info("Getting alarm time (0x42)...")
        response = await self.communicator.send_command_and_wait_for_response("get alarm time")
        if response and len(response) >= 10:  # 10 sets of alarm info
            alarms = []
            for i in range(10):
                # Assuming data format is similar to set alarm time (excluding animation data)
                # Uint8 alarm_index, status, hour, minute, week, mode, trigger_mode, Fm[2], volume
                # Each alarm is 9 bytes (excluding index)
                alarm_data = response[i*9:(i+1)*9]
                if len(alarm_data) == 9:
                    alarms.append({
                        "status": alarm_data[0],
                        "hour": alarm_data[1],
                        "minute": alarm_data[2],
                        "week": alarm_data[3],
                        "mode": alarm_data[4],
                        "trigger_mode": alarm_data[5],
                        "fm_freq": int.from_bytes(alarm_data[6:8], byteorder='little'),
                        "volume": alarm_data[8],
                    })
            return alarms
        return None

    async def set_alarm_gif(self, alarm_index: int, total_length: int, gif_id: int, data: list):
        """Set the alarm animation for a specific alarm (0x51)."""
        self.logger.info(
            f"Setting alarm GIF for index {alarm_index} (0x51)...")
        args = []
        args += alarm_index.to_bytes(1, byteorder='big')
        args += total_length.to_bytes(2, byteorder='little')
        args += gif_id.to_bytes(1, byteorder='big')
        args.extend(data)
        return await self.communicator.send_command("set alarm gif", args)

    async def get_memorial_time(self):
        """Get memorial time (0x53)."""
        self.logger.info("Getting memorial time (0x53)...")
        response = await self.communicator.send_command_and_wait_for_response("get memorial time")
        if response and len(response) >= 10 * 39:  # 10 records, each 39 bytes
            memorials = []
            for i in range(10):
                memorial_data = response[i*39:(i+1)*39]
                if len(memorial_data) == 39:
                    memorials.append({
                        "dialy_id": memorial_data[0],
                        "on_off": memorial_data[1],
                        "month": memorial_data[2],
                        "day": memorial_data[3],
                        "hour": memorial_data[4],
                        "minute": memorial_data[5],
                        "have_flag": memorial_data[6],
                        "title_name": bytes(memorial_data[7:39]).decode('utf-8').strip('\x00')
                    })
            return memorials
        return None

    async def set_memorial_gif(self, memorial_index: int, total_length: int, gif_id: int, data: list):
        """Set the memorial animation for a specific memorial (0x55)."""
        self.logger.info(
            f"Setting memorial GIF for index {memorial_index} (0x55)...")
        args = []
        args += memorial_index.to_bytes(1, byteorder='big')
        args += total_length.to_bytes(2, byteorder='little')
        args += gif_id.to_bytes(1, byteorder='big')
        args.extend(data)
        return await self.communicator.send_command("set memorial gif", args)

    async def set_alarm_listen(self, on_off: int, mode: int, volume: int):
        """Enable or disable the alarm audition feature (0xa5)."""
        self.logger.info(
            f"Setting alarm listen: on_off={on_off}, mode={mode}, volume={volume} (0xa5)...")
        args = []
        args += on_off.to_bytes(1, byteorder='big')
        args += mode.to_bytes(1, byteorder='big')
        args += volume.to_bytes(1, byteorder='big')
        return await self.communicator.send_command("set alarm listen", args)

    async def set_alarm_volume(self, volume: int):
        """Set the volume level for the alarm audition feature (0xa6)."""
        self.logger.info(f"Setting alarm volume to {volume} (0xa6)...")
        args = volume.to_bytes(1, byteorder='big')
        return await self.communicator.send_command("set alarm vol", list(args))

    async def set_alarm_volume_control(self, control: int, index: int):
        """Control the voice alarm feature (0x82)."""
        self.logger.info(
            f"Setting alarm volume control: control={control}, index={index} (0x82)...")
        args = []
        args += control.to_bytes(1, byteorder='big')
        args += index.to_bytes(1, byteorder='big')
        return await self.communicator.send_command("set alarm vol ctrl", args)
