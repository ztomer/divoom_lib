"""
Divoom Alarm and Memorial Commands
"""

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
