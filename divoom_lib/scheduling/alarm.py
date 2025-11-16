
import datetime
from ..models import (
    COMMANDS,
    ALARM_COUNT, GAT_ALARM_INFO_LENGTH,
    GAT_STATUS, GAT_HOUR, GAT_MINUTE, GAT_WEEK, GAT_MODE, GAT_TRIGGER_MODE,
    GAT_FM_FREQ_START, GAT_VOLUME,
    MEMORIAL_COUNT, GMT_MEMORIAL_INFO_LENGTH,
    GMT_DIALY_ID, GMT_ON_OFF, GMT_MONTH, GMT_DAY, GMT_HOUR, GMT_MINUTE,
    GMT_HAVE_FLAG, GMT_TITLE_NAME_START, GMT_TITLE_NAME_END
)
from ..utils.converters import bool_to_byte

class Alarm:
    def __init__(self, communicator):
        self.communicator = communicator
        self.logger = communicator.logger
    async def get_alarm_time(self):
        """Get alarm time (0x42)."""
        self.communicator.logger.info("Getting alarm time (0x42)...")
        response = await self.communicator.send_command_and_wait_for_response(models.COMMANDS["get alarm time"])
        if response and len(response) >= models.ALARM_COUNT * models.GAT_ALARM_INFO_LENGTH:  # 10 sets of alarm info
            alarms = []
            for i in range(models.ALARM_COUNT):
                # Assuming data format is similar to set alarm time (excluding animation data)
                # Uint8 alarm_index, status, hour, minute, week, mode, trigger_mode, Fm[2], volume
                # Each alarm is 9 bytes (excluding index)
                alarm_data = response[i*models.GAT_ALARM_INFO_LENGTH:(i+1)*models.GAT_ALARM_INFO_LENGTH]
                if len(alarm_data) == models.GAT_ALARM_INFO_LENGTH:
                    alarms.append({
                        "status": alarm_data[models.GAT_STATUS],
                        "hour": alarm_data[models.GAT_HOUR],
                        "minute": alarm_data[models.GAT_MINUTE],
                        "week": alarm_data[models.GAT_WEEK],
                        "mode": alarm_data[models.GAT_MODE],
                        "trigger_mode": alarm_data[models.GAT_TRIGGER_MODE],
                        "fm_freq": int.from_bytes(alarm_data[models.GAT_FM_FREQ_START:models.GAT_FM_FREQ_START + 2], byteorder='little'),
                        "volume": alarm_data[models.GAT_VOLUME],
                    })
            return alarms
        return None

    async def _set_animation_gif(self, command_key: str, index: int, total_length: int, gif_id: int, data: list) -> bool:
        """Helper method to set animation GIF for alarm or memorial."""
        self.logger.info(
            f"Setting animation GIF for {command_key} with index {index} (0x{models.COMMANDS[command_key]:02x})...")
        args = []
        args += index.to_bytes(1, byteorder='big')
        args += total_length.to_bytes(2, byteorder='little')
        args += gif_id.to_bytes(1, byteorder='big')
        args.extend(data)
        return await self.communicator.send_command(models.COMMANDS[command_key], args)

    async def set_alarm(self, alarm_index: int, status: int, hour: int, minute: int, week: int, mode: int, trigger_mode: int, fm_freq: int = 0, volume: int = 0) -> bool:
        """
        Set the extended alarm time information in the device (0x43).
        
        Args:
            alarm_index (int): Which alarm to set, starting from 0.
            status (int): 1 (alarm on), 0 (alarm off).
            hour (int): Hour to set for the alarm.
            minute (int): Minute to set for the alarm.
            week (int): Bits 0 to 6 represent Sunday to Saturday, respectively. Set to 1 if the alarm should repeat on that day.
            mode (int): Alarm mode (ALARM_MUSIC=0, and others: 1, 2, 3, 4).
            trigger_mode (int): Alarm trigger mode (ALARM_TRIGGER_MUSIC=1, ALARM_TRIGGER_GIF=4).
            fm_freq (int): If trigger_mode is ALARM_TRIGGER_MUSIC, these 2 bytes represent the frequency point.
            volume (int): Volume level for the alarm, ranging from 0 to 100.
        """
        self.logger.info(f"Setting alarm {alarm_index} (0x43)...")
        args = []
        args.append(alarm_index)
        args.append(status)
        args.append(hour)
        args.append(minute)
        args.append(week)
        args.append(mode)
        args.append(trigger_mode)
        args += fm_freq.to_bytes(2, byteorder='little')
        args.append(volume)
        return await self.communicator.send_command(models.COMMANDS["set alarm"], args)

    async def set_alarm_gif(self, alarm_index: int, total_length: int, gif_id: int, data: list) -> bool:
        """Set the alarm animation for a specific alarm (0x51)."""
        return await self._set_animation_gif("set alarm gif", alarm_index, total_length, gif_id, data)

    async def get_memorial_time(self):
        """Get memorial time (0x53)."""
        self.logger.info("Getting memorial time (0x53)...")
        response = await self.communicator.send_command_and_wait_for_response(models.COMMANDS["get memorial time"])
        if response and len(response) >= models.MEMORIAL_COUNT * models.GMT_MEMORIAL_INFO_LENGTH:  # 10 records, each 39 bytes
            memorials = []
            for i in range(models.MEMORIAL_COUNT):
                memorial_data = response[i*models.GMT_MEMORIAL_INFO_LENGTH:(i+1)*models.GMT_MEMORIAL_INFO_LENGTH]
                if len(memorial_data) == models.GMT_MEMORIAL_INFO_LENGTH:
                    memorials.append({
                        "dialy_id": memorial_data[models.GMT_DIALY_ID],
                        "on_off": memorial_data[models.GMT_ON_OFF],
                        "month": memorial_data[models.GMT_MONTH],
                        "day": memorial_data[models.GMT_DAY],
                        "hour": memorial_data[models.GMT_HOUR],
                        "minute": memorial_data[models.GMT_MINUTE],
                        "have_flag": memorial_data[models.GMT_HAVE_FLAG],
                        "title_name": bytes(memorial_data[models.GMT_TITLE_NAME_START:models.GMT_TITLE_NAME_END]).decode('utf-8').strip('\x00')
                    })
            return memorials
        return None

    async def set_memorial_time(self, dialy_id: int, on_off: int, month: int, day: int, hour: int, minute: int, have_flag: int, title_name: str) -> bool:
        """Set memorial time (0x54)."""
        self.logger.info(f"Setting memorial time for id {dialy_id} (0x54)...")
        args = []
        args.append(dialy_id)
        args.append(on_off)
        args.append(month)
        args.append(day)
        args.append(hour)
        args.append(minute)
        args.append(have_flag)
        
        title_bytes = title_name.encode('utf-8')
        if len(title_bytes) > 32:
            self.logger.warning("Title name too long, truncating to 32 bytes.")
            title_bytes = title_bytes[:32]
        
        args.extend(list(title_bytes))
        
        # Pad with null bytes to 32 bytes
        args.extend([0] * (32 - len(title_bytes)))

        return await self.communicator.send_command(models.COMMANDS["set memorial"], args)

    async def set_memorial_gif(self, memorial_index: int, total_length: int, gif_id: int, data: list) -> bool:
        """Set the memorial animation for a specific memorial (0x55)."""
        return await self._set_animation_gif("set memorial gif", memorial_index, total_length, gif_id, data)

    async def set_alarm_listen(self, on_off: int, mode: int, volume: int) -> bool:
        """Enable or disable the alarm audition feature (0xa5)."""
        self.logger.info(
            f"Setting alarm listen: on_off={on_off}, mode={mode}, volume={volume} (0xa5)...")
        args = []
        args.append(bool_to_byte(on_off))
        args += mode.to_bytes(1, byteorder='big')
        args += volume.to_bytes(1, byteorder='big')
        return await self.communicator.send_command(models.COMMANDS["set alarm listen"], args)

    async def set_alarm_volume(self, volume: int) -> bool:
        """Set the volume level for the alarm audition feature (0xa6)."""
        self.logger.info(f"Setting alarm volume to {volume} (0xa6)...")
        args = [volume]
        return await self.communicator.send_command(models.COMMANDS["set alarm vol"], args)

    async def set_alarm_volume_control(self, control: int, index: int):
        """Control the voice alarm feature (0x82)."""
        self.logger.info(
            f"Setting alarm volume control: control={control}, index={index} (0x82)...")
        args = []
        args += control.to_bytes(1, byteorder='big')
        args += index.to_bytes(1, byteorder='big')
        return await self.communicator.send_command(models.COMMANDS["set alarm vol ctrl"], args)
