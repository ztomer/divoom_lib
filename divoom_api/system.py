"""
Divoom System Commands
"""
import datetime
import logging

class System:
    async def get_work_mode(self):
        """Get the current system working mode (0x13)."""
        self.logger.info("Getting work mode (0x13)...")
        response = await self._send_command_and_wait_for_response("get work mode")
        if response:
            # Assuming the response is a single byte representing the mode
            return int.from_bytes(response, byteorder='big')
        return None

    async def send_sd_status(self, status: int):
        """Notify that there is an insertion or removal action on the TF card (0x15).
        Status: 1 for insertion, 0 for removal."""
        self.logger.info(f"Sending SD card status: {status} (0x15)...")
        args = [status]
        return await self.send_command("send sd status", args)

    async def set_boot_gif(self, on_off: int, total_length: int, gif_id: int, data: list):
        """Set the boot animation (0x52).
        on_off: 1 to set, 0 not to set.
        total_length: Total length of the entire data.
        gif_id: Sequence number of the sent data.
        data: divoom_image_encode_encode_pic encoded data."""
        self.logger.info(f"Setting boot GIF (0x52)...")
        args = []
        args += on_off.to_bytes(1, byteorder='big')
        args += total_length.to_bytes(2, byteorder='little')
        args += gif_id.to_bytes(1, byteorder='big')
        args.extend(data)
        return await self.send_command("set boot gif", args)

    async def get_device_temp(self):
        """Get the device's temperature (0x59)."""
        self.logger.info("Getting device temperature (0x59)...")
        response = await self._send_command_and_wait_for_response("get device temp")
        if response and len(response) >= 2:
            temp_format = response[0]  # 1: Fahrenheit, 0: Celsius
            temp_value = int.from_bytes(
                response[1:2], byteorder='big', signed=True)
            return {"format": temp_format, "value": temp_value}
        return None

    async def send_net_temp(self, year: int, month: int, day: int, hour: int, minute: int, num: int, temp_data: list):
        """Send network temperature (0x5d).
        temp_data: List of [temperature_value, weather_type] pairs."""
        self.logger.info(f"Sending network temperature (0x5d)...")
        args = []
        args += year.to_bytes(2, byteorder='little')
        args += month.to_bytes(1, byteorder='big')
        args += day.to_bytes(1, byteorder='big')
        args += hour.to_bytes(1, byteorder='big')
        args += minute.to_bytes(1, byteorder='big')
        args += num.to_bytes(1, byteorder='big')
        for temp_val, weather_type in temp_data:
            args += temp_val.to_bytes(1, byteorder='big', signed=True)
            args += weather_type.to_bytes(1, byteorder='big')
        return await self.send_command("send net temp", args)

    async def send_net_temp_disp(self, display_modes: list, time_minutes: int):
        """Send network temperature display settings (0x5e).
        display_modes: List of 5 booleans (0 or 1) for display modes.
        time_minutes: Number of minutes since 00:00 of the current day."""
        self.logger.info(f"Sending network temperature display (0x5e)...")
        args = []
        for mode in display_modes:
            args += mode.to_bytes(1, byteorder='big')
        args += time_minutes.to_bytes(2, byteorder='little')
        return await self.send_command("send net temp disp", args)

    async def get_net_temp_disp(self):
        """Obtain the network temperature display mode (0x73)."""
        self.logger.info("Getting network temperature display (0x73)...")
        response = await self._send_command_and_wait_for_response("get net temp disp")
        if response and len(response) >= 7:
            display_modes = [response[i] for i in range(5)]
            time_minutes = int.from_bytes(response[5:7], byteorder='little')
            return {"display_modes": display_modes, "time_minutes": time_minutes}
        return None

    async def set_device_name(self, name: str):
        """Modify the Bluetooth device name (0x75).
        name: New device name in UTF-8 format (max 16 chars)."""
        self.logger.info(f"Setting device name to '{name}' (0x75)...")
        name_bytes = name.encode('utf-8')
        if len(name_bytes) > 16:
            self.logger.warning(
                "Device name too long, truncating to 16 bytes.")
            name_bytes = name_bytes[:16]
        args = []
        args += len(name_bytes).to_bytes(1, byteorder='big')
        args.extend(list(name_bytes))
        return await self.send_command("set device name", args)

    async def get_device_name(self):
        """Obtain the Bluetooth device name (0x76)."""
        self.logger.info("Getting device name (0x76)...")
        response = await self._send_command_and_wait_for_response("get device name")
        if response and len(response) >= 1:
            name_length = response[0]
            if len(response) >= 1 + name_length:
                name_bytes = bytes(response[1:1+name_length])
                return name_bytes.decode('utf-8')
        return None

    async def set_low_power_switch(self, on_off: int):
        """Set the low power mode switch (0xb2).
        on_off: 1 to turn on, 0 to turn off."""
        self.logger.info(f"Setting low power switch to {on_off} (0xb2)...")
        args = [on_off]
        return await self.send_command("set low power switch", args)

    async def get_low_power_switch(self):
        """Obtain the low power mode switch status (0xb3)."""
        self.logger.info("Getting low power switch status (0xb3)...")
        response = await self._send_command_and_wait_for_response("get low power switch")
        if response and len(response) >= 1:
            return response[0]  # 1: on, 0: off
        return None

    async def set_hour_type(self, hour_type: int):
        """Set the hour format (0x2c).
        hour_type: 0 for 12-hour, 1 for 24-hour, 0xFF to query."""
        self.logger.info(f"Setting hour type to {hour_type} (0x2c)...")
        args = [hour_type]
        return await self.send_command("set time type", args)

    async def set_song_display_control(self, control: int):
        """Set the song name display switch (0x83).
        control: 0 to turn off, 1 to turn on, 0xFF to query."""
        self.logger.info(
            f"Setting song display control to {control} (0x83)...")
        args = [control]
        return await self.send_command("set song dis ctrl", args)

    async def set_bluetooth_password(self, control: int, password: str = None):
        """Set the password for user's Bluetooth connection (0x27).
        control: 1 to set, 0 to cancel, 2 to get status.
        password: 4-digit password (only for control=1)."""
        self.logger.info(
            f"Setting Bluetooth password (0x27) with control {control}...")
        args = [control]
        if control == 1 and password:
            if len(password) != 4 or not password.isdigit():
                self.logger.error("Password must be a 4-digit string.")
                return False
            args.extend([int(digit) for digit in password])
        return await self.send_command("set blue password", args)

    async def set_power_on_voice_volume(self, control: int, volume: int = None):
        """Set or get the power-on voice volume (0xbb).
        control: 1 to set, 0 to get.
        volume: 0-100 (only for control=1)."""
        self.logger.info(
            f"Setting power-on voice volume (0xbb) with control {control}...")
        args = [control]
        if control == 1 and volume is not None:
            if not (0 <= volume <= 100):
                self.logger.error("Volume must be between 0 and 100.")
                return False
            args.append(volume)
        return await self.send_command("set poweron voice vol", args)

    async def set_power_on_channel(self, control: int, channel_id: int = None):
        """Set or get the power-on channel (0x8a).
        control: 1 to set, 0 to get.
        channel_id: 0-5 (only for control=1)."""
        self.logger.info(
            f"Setting power-on channel (0x8a) with control {control}...")
        args = [control]
        if control == 1 and channel_id is not None:
            if not (0 <= channel_id <= 5):
                self.logger.error("Channel ID must be between 0 and 5.")
                return False
            args.append(channel_id)
        return await self.send_command("set poweron channel", args)

    async def set_auto_power_off(self, minutes: int):
        """Set the auto power-off timer (0xab).
        minutes: Duration in minutes (2 bytes, little-endian)."""
        self.logger.info(
            f"Setting auto power-off to {minutes} minutes (0xab)...")
        args = minutes.to_bytes(2, byteorder='little')
        return await self.send_command("set auto power off", list(args))

    async def get_auto_power_off(self):
        """Get the current auto power-off timer (0xac)."""
        self.logger.info("Getting auto power-off timer (0xac)...")
        response = await self._send_command_and_wait_for_response("get auto power off")
        if response and len(response) >= 2:
            return int.from_bytes(response[0:2], byteorder='little')
        return None

    async def set_sound_control(self, enable: int):
        """Control screen switch with ambient sound (0xa7).
        enable: 1 to enable, 0 to disable."""
        self.logger.info(f"Setting sound control to {enable} (0xa7)...")
        args = [enable]
        return await self.send_command("set sound ctrl", args)

    async def get_sound_control(self):
        """Returns the sound control switch value from device (0xa8)."""
        self.logger.info("Getting sound control status (0xa8)...")
        response = await self._send_command_and_wait_for_response("get sound ctrl")
        if response and len(response) >= 1:
            return response[0]  # 1: enabled, 0: disabled
        return None

    async def show_temperature(self, value=None, color=None):
        """Show temperature on the Divoom device in the color"""
        result = await self.show_clock(clock=None, twentyfour=None, weather=None, temp=True, calendar=None, color=color, hot=None)
        await self.send_command("set temp type", [0x01 if value == True or value == 1 else 0x00])
        return result

    async def send_volume(self, value=None):
        """Send volume to the Divoom device"""
        if value == None:
            value = 0
        if isinstance(value, str):
            value = int(value)

        args = []
        args += int(value * 15 / 100).to_bytes(1, byteorder='big')
        return await self.send_command("set volume", args)

    async def send_weather(self, value=None, weather=None):
        """Send weather to the Divoom device"""
        if value == None:
            return
        if weather == None:
            weather = 0
        if isinstance(weather, str):
            weather = int(weather)

        args = []
        args += int(round(float(value[0:-2]))
                    ).to_bytes(1, byteorder='big', signed=True)
        args += weather.to_bytes(1, byteorder='big')
        result = await self.send_command("set temp", args)

        if value[-2] == "°C":
            await self.send_command("set temp type", [0x00])
        if value[-2] == "°F":
            await self.send_command("set temp type", [0x01])
        return result