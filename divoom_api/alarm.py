"""
Divoom Alarm and Memorial Commands
"""
import datetime
from .base import DivoomCommand, DivoomBase

class Alarm(DivoomBase):
    # Alarm Commands
    GET_ALARM_TIME = DivoomCommand(0x42)
    SET_ALARM_TIME = DivoomCommand(0x43)
    SET_ALARM_GIF = DivoomCommand(0x51)
    SET_ALARM_LISTEN = DivoomCommand(0xA5)
    SET_ALARM_VOL = DivoomCommand(0xA6)
    SET_ALARM_VOL_CTRL = DivoomCommand(0x82)

    # Memorial Commands
    SET_MEMORIAL_TIME = DivoomCommand(0x54)
    GET_MEMORIAL_TIME = DivoomCommand(0x53)
    SET_MEMORIAL_GIF = DivoomCommand(0x55)

    async def show_alarm(self, number=None, time=None, weekdays=None, alarmMode=None, triggerMode=None, frequency=None, volume=None):
        """Show alarm tool on the Divoom device"""
        if number == None:
            number = 0
        if volume == None:
            volume = 100
        if alarmMode == None:
            alarmMode = 0
        if triggerMode == None:
            triggerMode = 0
        if isinstance(number, str):
            number = int(number)
        if isinstance(volume, str):
            volume = int(volume)
        if isinstance(alarmMode, str):
            alarmMode = int(alarmMode)
        if isinstance(triggerMode, str):
            triggerMode = int(triggerMode)

        args = []
        args += number.to_bytes(1, byteorder='big')
        args += (0x01 if time != None else 0x00).to_bytes(1, byteorder='big')

        if time != None:
            args += int(time[0:2]).to_bytes(1, byteorder='big')
            args += int(time[3:]).to_bytes(1, byteorder='big')
        else:
            args += [0x00, 0x00]
        if weekdays != None:
            weekbits = 0
            if 'sun' in weekdays:
                weekbits += 1
            if 'mon' in weekdays:
                weekbits += 2
            if 'tue' in weekdays:
                weekbits += 4
            if 'wed' in weekdays:
                weekbits += 8
            if 'thu' in weekdays:
                weekbits += 16
            if 'fri' in weekdays:
                weekbits += 32
            if 'sat' in weekdays:
                weekbits += 64
            args += weekbits.to_bytes(1, byteorder='big')
        else:
            args += [0x00]

        args += alarmMode.to_bytes(1, byteorder='big')
        args += triggerMode.to_bytes(1, byteorder='big')
        args += self._parse_frequency(frequency)
        args += volume.to_bytes(1, byteorder='big')
        return await self.send_command(Alarm.SET_ALARM_TIME, args)

    async def show_memorial(self, number=None, value=None, text=None, animate=True):
        """Show memorial tool on the Divoom device"""
        if number == None:
            number = 0
        if text == None:
            text = "Home Assistant"
        if isinstance(number, str):
            number = int(number)
        if not isinstance(text, str):
            text = str(text)

        args = []
        args += number.to_bytes(1, byteorder='big')
        args += (0x01 if value != None else 0x00).to_bytes(1, byteorder='big')

        if value != None:
            clock = datetime.datetime.fromisoformat(value)
            args += clock.month.to_bytes(1, byteorder='big')
            args += clock.day.to_bytes(1, byteorder='big')
            args += clock.hour.to_bytes(1, byteorder='big')
            args += clock.minute.to_bytes(1, byteorder='big')
        else:
            args += [0x00, 0x00, 0x00, 0x00]

        args += (0x01 if animate == True else 0x00).to_bytes(1, byteorder='big')
        for char in text[0:15].ljust(16, '\n').encode('utf-8'):
            args += (0x00 if char == 0x0a else char).to_bytes(2, byteorder='big')

        return await self.send_command("set memorial", args)

    async def get_alarm_time(self):
        """Get alarm time (0x42)."""
        self.logger.info("Getting alarm time (0x42)...")
        response = await self._send_command_and_wait_for_response("get alarm time")
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
        return await self.send_command("set alarm gif", args)

    async def get_memorial_time(self):
        """Get memorial time (0x53)."""
        self.logger.info("Getting memorial time (0x53)...")
        response = await self._send_command_and_wait_for_response("get memorial time")
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
        return await self.send_command("set memorial gif", args)

    async def set_alarm_listen(self, on_off: int, mode: int, volume: int):
        """Enable or disable the alarm audition feature (0xa5)."""
        self.logger.info(
            f"Setting alarm listen: on_off={on_off}, mode={mode}, volume={volume} (0xa5)...")
        args = []
        args += on_off.to_bytes(1, byteorder='big')
        args += mode.to_bytes(1, byteorder='big')
        args += volume.to_bytes(1, byteorder='big')
        return await self.send_command("set alarm listen", args)

    async def set_alarm_volume(self, volume: int):
        """Set the volume level for the alarm audition feature (0xa6)."""
        self.logger.info(f"Setting alarm volume to {volume} (0xa6)...")
        args = volume.to_bytes(1, byteorder='big')
        return await self.send_command("set alarm vol", list(args))

    async def set_alarm_volume_control(self, control: int, index: int):
        """Control the voice alarm feature (0x82)."""
        self.logger.info(
            f"Setting alarm volume control: control={control}, index={index} (0x82)...")
        args = []
        args += control.to_bytes(1, byteorder='big')
        args += index.to_bytes(1, byteorder='big')
        return await self.send_command("set alarm vol ctrl", args)
