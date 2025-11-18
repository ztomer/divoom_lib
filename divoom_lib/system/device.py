
import datetime
import logging
from divoom_lib.models import (
    COMMANDS,
    CHANNEL_ID_MIN, CHANNEL_ID_MAX,
    SD_STATUS_REMOVAL, SD_STATUS_INSERTION,
    BOOT_GIF_OFF, BOOT_GIF_ON,
    TEMP_FORMAT_CELSIUS, TEMP_FORMAT_FAHRENHEIT,
    LOW_POWER_SWITCH_OFF, LOW_POWER_SWITCH_ON,
    SONG_DISPLAY_OFF, SONG_DISPLAY_ON, SONG_DISPLAY_QUERY,
    POVVC_GET, POVVC_SET,
    POCC_GET, POCC_SET, POCC_CHANNEL_MIN, POCC_CHANNEL_MAX,
    SOUND_CONTROL_DISABLE, SOUND_CONTROL_ENABLE,
    GDT_TEMP_FORMAT, GDT_TEMP_VALUE,
    GNTD_DISPLAY_MODES_START, GNTD_TIME_MINUTES_START,
    GDN_NAME_LENGTH, GDN_NAME_BYTES_START
)
from divoom_lib.utils.converters import bool_to_byte

class Device:
    """
    Provides functionality to control the device system settings of a Divoom device.

    Usage::

        import asyncio
        from divoom_lib import Divoom

        async def main():
            device_address = "XX:XX:XX:XX:XX:XX"  # Replace with your device's address
            divoom = Divoom(mac=device_address)
            
            try:
                await divoom.connect()
                await divoom.device.set_brightness(50)
            finally:
                if divoom.is_connected:
                    await divoom.disconnect()

        if __name__ == "__main__":
            asyncio.run(main())
    """
    def __init__(self, divoom) -> None:
        self._divoom = divoom
        self.logger = divoom.logger

    async def set_brightness(self, brightness: int) -> bool:
        """
        Set the screen brightness (0x74).
        
        Args:
            brightness (int): 0-100.
        
        Usage::
            
            await divoom.device.set_brightness(50)
        """
        self.logger.info(f"Setting brightness to {brightness} (0x74)...")
        args = [brightness]
        return await self.communicator.send_command(COMMANDS["set brightness"], args)

    async def get_brightness(self) -> int | None:
        """
        Get the screen brightness by querying the light mode (0x46).
        
        Returns:
            int | None: The brightness level (0-100), or None if the command fails.
            
        Usage::
            
            brightness = await divoom.device.get_brightness()
            if brightness is not None:
                print(f"Current brightness: {brightness}")
        """
        self.logger.info("Getting brightness via get light mode (0x46)...")
        
        command_id = COMMANDS["get light mode"]
        
        # Set the command we are waiting for a response to.
        self.communicator._expected_response_command = command_id
        
        # The device requires sending this command with iOS framing,
        # but the notification response is in the Basic protocol format.
        # We use the framing context to temporarily switch protocols for the send operation.
        async with self.communicator._framing_context(use_ios=True, escape=False):
            await self.communicator.send_command(command_id, [])

        # After sending with the correct protocol, we wait for the response.
        # The notification handler will use the object's default protocol (Basic) to parse the response.
        response_payload = await self.communicator.wait_for_response(command_id)

        if response_payload and len(response_payload) >= 7:
            try:
                brightness = response_payload[6]
                self.logger.info(f"Successfully parsed brightness: {brightness}")
                return brightness
            except IndexError:
                self.logger.warning("Failed to parse brightness from response, payload is too short.")
                return None
        else:
            self.logger.warning(f"Did not receive a valid or sufficiently long payload for get_brightness command.")
            return None


    async def get_work_mode(self) -> int | None:
        """
        Get the current system working mode (0x06).
        
        Returns:
            int | None: The current work mode, or None if the command fails.
            
        Usage::
            
            work_mode = await divoom.device.get_work_mode()
            if work_mode is not None:
                print(f"Current work mode: {work_mode}")
        """
        self.logger.info("Getting work mode (0x06)...")
        response = await self.communicator.send_command_and_wait_for_response(COMMANDS["get work mode"])
        if response and len(response) >= 1:
            # Assuming the response is a single byte representing the mode
            return response[0]
        return None

    async def set_work_mode(self, mode: int) -> bool:
        """
        Switch system working mode (0x05).
        
        Args:
            mode (int): 0-11.
            
        Usage::
            
            # Set work mode to FM Radio
            await divoom.device.set_work_mode(1)
        """
        self.logger.info(f"Setting work mode to: {mode} (0x05)...")
        args = [mode]
        return await self.communicator.send_command(COMMANDS["set work mode"], args)

    async def set_channel(self, channel_id: int) -> bool:
        """
        Switch to a specific channel (0x45).
        
        Args:
            channel_id (int):
                0x00: Time
                0x01: Lightning
                0x02: Cloud Channel
                0x03: VJ Effects
                0x04: Visualization
                0x05: Animation
                0x06: Scoreboard
                
        Usage::
            
            # Switch to the VJ Effects channel
            await divoom.device.set_channel(3)
        """
        if not (CHANNEL_ID_MIN <= channel_id <= CHANNEL_ID_MAX):
            self.logger.error(f"Invalid channel ID: {channel_id}. Must be between {CHANNEL_ID_MIN} and {CHANNEL_ID_MAX}.")
            return False

        self.logger.info(f"Switching to channel: {channel_id} (0x45)...")
        args = [channel_id]
        return await self.communicator.send_command(COMMANDS["set channel light"], args)

    async def send_sd_status(self, status: int) -> bool:
        """
        Notify that there is an insertion or removal action on the TF card (0x15).
        
        Args:
            status (int): 1 for insertion, 0 for removal.
            
        Usage::
            
            # Notify SD card insertion
            await divoom.device.send_sd_status(1)
        """
        self.logger.info(f"Sending SD card status: {status} (0x15)...")
        args = [status]
        return await self.communicator.send_command(COMMANDS["send sd status"], args)

    async def set_boot_gif(self, on_off: int, total_length: int, gif_id: int, data: list) -> bool:
        """
        Set the boot animation (0x52).
        
        Args:
            on_off (int): 1 to set, 0 not to set.
            total_length (int): Total length of the entire data.
            gif_id (int): Sequence number of the sent data.
            data (list): divoom_image_encode_encode_pic encoded data.
            
        Usage::
            
            # This is a low-level command. Consider using a higher-level library for GIF processing.
            # await divoom.device.set_boot_gif(on_off=1, total_length=100, gif_id=1, data=[...])
        """
        self.logger.info(f"Setting boot GIF (0x52)...")
        args = []
        args.append(bool_to_byte(on_off))
        args += total_length.to_bytes(2, byteorder='little')
        args += gif_id.to_bytes(1, byteorder='big')
        args.extend(data)
        return await self.communicator.send_command(COMMANDS["set boot gif"], args)

    async def get_device_temp(self) -> dict | None:
        """
        Get the device's temperature (0x59).
        
        Returns:
            dict | None: A dictionary containing the temperature format and value, or None if the command fails.
            
        Usage::
            
            temp = await divoom.device.get_device_temp()
            if temp:
                print(f"Device temperature: {temp['value']} {'F' if temp['format'] else 'C'}")
        """
        self.logger.info("Getting device temperature (0x59)....")
        response = await self.communicator.send_command_and_wait_for_response(COMMANDS["get device temp"])
        if response and len(response) >= 2:
            temp_format = response[GDT_TEMP_FORMAT]  # 1: Fahrenheit, 0: Celsius
            temp_value = int.from_bytes(
                response[GDT_TEMP_VALUE:GDT_TEMP_VALUE + 1], byteorder='big', signed=True)
            return {"format": temp_format, "value": temp_value}
        return None

    async def send_net_temp(self, year: int, month: int, day: int, hour: int, minute: int, num: int, temp_data: list) -> bool:
        """
        Send network temperature (0x5d).
        
        Args:
            temp_data (list): List of [temperature_value, weather_type] pairs.
            
        Usage::
            
            # This is a low-level command.
            # await divoom.device.send_net_temp(year=2023, month=10, day=27, hour=12, minute=0, num=1, temp_data=[[25, 1]])
        """
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
        return await self.communicator.send_command(COMMANDS["send net temp"], args)

    async def send_net_temp_disp(self, display_modes: list, time_minutes: int) -> bool:
        """
        Send network temperature display settings (0x5e).
        
        Args:
            display_modes (list): List of 5 booleans (0 or 1) for display modes.
            time_minutes (int): Number of minutes since 00:00 of the current day.
            
        Usage::
            
            # This is a low-level command.
            # await divoom.device.send_net_temp_disp(display_modes=[1, 1, 1, 1, 1], time_minutes=720)
        """
        self.logger.info(f"Sending network temperature display (0x5e)...")
        args = []
        for mode in display_modes:
            args.append(bool_to_byte(mode))
        args += time_minutes.to_bytes(2, byteorder='little')
        return await self.communicator.send_command(COMMANDS["send net temp disp"], args)

    async def get_net_temp_disp(self) -> dict | None:
        """
        Obtain the network temperature display mode (0x73).
        
        Returns:
            dict | None: A dictionary containing the display modes and time, or None if the command fails.
            
        Usage::
            
            net_temp_disp = await divoom.device.get_net_temp_disp()
            if net_temp_disp:
                print(f"Network temp display modes: {net_temp_disp['display_modes']}")
        """
        self.logger.info("Getting network temperature display (0x73)...")
        response = await self.communicator.send_command_and_wait_for_response(COMMANDS["get net temp disp"])
        if response and len(response) >= 7:
            display_modes = [response[i] for i in range(GNTD_DISPLAY_MODES_START, GNTD_DISPLAY_MODES_START + 5)]
            time_minutes = int.from_bytes(response[GNTD_TIME_MINUTES_START:GNTD_TIME_MINUTES_START + 2], byteorder='little')
            return {"display_modes": display_modes, "time_minutes": time_minutes}
        return None

    async def set_device_name(self, name: str) -> bool:
        """
        Modify the Bluetooth device name (0x75).
        
        Args:
            name (str): New device name in UTF-8 format (max 16 chars).
            
        Usage::
            
            await divoom.device.set_device_name("My Divoom")
        """
        self.logger.info(f"Setting device name to '{name}' (0x75)...")
        name_bytes = name.encode('utf-8')
        if len(name_bytes) > 16:
            self.logger.warning(
                "Device name too long, truncating to 16 bytes.")
            name_bytes = name_bytes[:16]
        args = []
        args += len(name_bytes).to_bytes(1, byteorder='big')
        args.extend(list(name_bytes))
        return await self.communicator.send_command(COMMANDS["set device name"], args)

    async def get_device_name(self) -> str | None:
        """
        Obtain the Bluetooth device name (0x76).
        
        Returns:
            str | None: The device name, or None if the command fails.
            
        Usage::
            
            device_name = await divoom.device.get_device_name()
            if device_name:
                print(f"Device name: {device_name}")
        """
        self.logger.info("Getting device name (0x76)...")
        response = await self.communicator.send_command_and_wait_for_response(COMMANDS["get device name"])
        if response and len(response) >= 1:
            name_length = response[GDN_NAME_LENGTH]
            if len(response) >= GDN_NAME_BYTES_START + name_length:
                name_bytes = bytes(response[GDN_NAME_BYTES_START:GDN_NAME_BYTES_START + name_length])
                return name_bytes.decode('utf-8')
        return None

    async def set_low_power_switch(self, on_off: int) -> bool:
        """
        Set the low power mode switch (0xb2).
        
        Args:
            on_off (int): 1 to turn on, 0 to turn off.
            
        Usage::
            
            await divoom.device.set_low_power_switch(1)
        """
        self.logger.info(f"Setting low power switch to {on_off} (0xb2)...")
        args = [on_off]
        return await self.communicator.send_command(COMMANDS["set low power switch"], args)

    async def get_low_power_switch(self) -> int | None:
        """
        Obtain the low power mode switch status (0xb3).
        
        Returns:
            int | None: 1 if on, 0 if off, or None if the command fails.
            
        Usage::
            
            low_power_status = await divoom.device.get_low_power_switch()
            if low_power_status is not None:
                print(f"Low power mode is {'on' if low_power_status else 'off'}")
        """
        self.logger.info("Getting low power switch status (0xb3)...")
        response = await self.communicator.send_command_and_wait_for_response(COMMANDS["get low power switch"])
        if response and len(response) >= 1:
            return response[0]  # 1: on, 0: off
        return None

    async def set_song_display_control(self, control: int) -> bool:
        """
        Set the song name display switch (0x83).
        
        Args:
            control (int): 0 to turn off, 1 to turn on, 0xFF to query.
            
        Usage::
            
            await divoom.device.set_song_display_control(1)
        """
        self.logger.info(
            f"Setting song display control to {control} (0x83)...")
        args = [control]
        return await self.communicator.send_command(COMMANDS["set song dis ctrl"], args)

    def _handle_povvc_set(self, kwargs: dict) -> list | None:
        volume = kwargs.get("volume")
        if volume is not None:
            if not (0 <= volume <= 100):
                self.logger.error("Volume must be between 0 and 100.")
                return None
            return [volume]
        self.logger.error("Missing 'volume' for Set Power-on Voice Volume control.")
        return None

    def _handle_povvc_get(self, kwargs: dict) -> list | None:
        return [] # No additional data

    _povvc_handlers = {
        POVVC_SET: _handle_povvc_set,
        POVVC_GET: _handle_povvc_get,
    }

    async def set_power_on_voice_volume(self, control: int, **kwargs) -> bool:
        """
        Set or get the power-on voice volume (0xbb).
        
        Args:
            control (int): 1 to set, 0 to get.
            volume (int): 0-100 (only for control=1).
            
        Usage::
            
            # Set power-on volume to 50
            await divoom.device.set_power_on_voice_volume(1, volume=50)
        """
        self.logger.info(
            f"Setting power-on voice volume (0xbb) with control {control}...")
        args = [control]

        handler = self._povvc_handlers.get(control)
        if handler:
            control_args = handler(self, kwargs)
            if control_args is not None:
                args.extend(control_args)
            else:
                return False
        else:
            self.logger.warning(
                f"Unknown control for set_power_on_voice_volume: {control}")
            return False
        return await self.communicator.send_command(COMMANDS["set poweron voice vol"], args)

    def _handle_pocc_set(self, kwargs: dict) -> list | None:
        channel_id = kwargs.get("channel_id")
        if channel_id is not None:
            if not (POCC_CHANNEL_MIN <= channel_id <= POCC_CHANNEL_MAX):
                self.logger.error(f"Channel ID must be between {POCC_CHANNEL_MIN} and {POCC_CHANNEL_MAX}.")
                return None
            return [channel_id]
        self.logger.error("Missing 'channel_id' for Set Power-on Channel control.")
        return None

    def _handle_pocc_get(self, kwargs: dict) -> list | None:
        return [] # No additional data

    _pocc_handlers = {
        POCC_SET: _handle_pocc_set,
        POCC_GET: _handle_pocc_get,
    }

    async def set_power_on_channel(self, control: int, **kwargs) -> bool:
        """
        Set or get the power-on channel (0x8a).
        
        Args:
            control (int): 1 to set, 0 to get.
            channel_id (int): 0-5 (only for control=1).
            
        Usage::
            
            # Set power-on channel to VJ Effects
            await divoom.device.set_power_on_channel(1, channel_id=3)
        """
        self.logger.info(
            f"Setting power-on channel (0x8a) with control {control}...")
        args = [control]

        handler = self._pocc_handlers.get(control)
        if handler:
            control_args = handler(self, kwargs)
            if control_args is not None:
                args.extend(control_args)
            else:
                return False
        else:
            self.logger.warning(
                f"Unknown control for set_power_on_channel: {control}")
            return False
        return await self.communicator.send_command(COMMANDS["set poweron channel"], args)

    async def set_auto_power_off(self, minutes: int) -> bool:
        """
        Set the auto power-off timer (0xab).
        
        Args:
            minutes (int): Duration in minutes (2 bytes, little-endian).
            
        Usage::
            
            # Set auto power-off to 30 minutes
            await divoom.device.set_auto_power_off(30)
        """
        self.logger.info(
            f"Setting auto power-off to {minutes} minutes (0xab)...")
        args = list(minutes.to_bytes(2, byteorder='little'))
        return await self.communicator.send_command(COMMANDS["set auto power off"], args)

    async def get_auto_power_off(self):
        """
        Get the current auto power-off timer (0xac).
        
        Returns:
            int | None: The auto power-off time in minutes, or None if the command fails.
            
        Usage::
            
            auto_power_off = await divoom.device.get_auto_power_off()
            if auto_power_off is not None:
                print(f"Auto power-off time: {auto_power_off} minutes")
        """
        self.logger.info("Getting auto power-off timer (0xac)...")
        response = await self.communicator.send_command_and_wait_for_response(COMMANDS["get auto power off"])
        if response and len(response) >= 2:
            return int.from_bytes(response[0:2], byteorder='little')
        return None

    async def set_sound_control(self, enable: int):
        """
        Control screen switch with ambient sound (0xa7).
        
        Args:
            enable (int): 1 to enable, 0 to disable.
            
        Usage::
            
            await divoom.device.set_sound_control(1)
        """
        self.logger.info(f"Setting sound control to {enable} (0xa7)...")
        args = [enable]
        return await self.communicator.send_command(COMMANDS["set sound ctrl"], args)

    async def get_sound_control(self):
        """
        Returns the sound control switch value from device (0xa8).
        
        Returns:
            int | None: 1 if enabled, 0 if disabled, or None if the command fails.
            
        Usage::
            
            sound_control_status = await divoom.device.get_sound_control()
            if sound_control_status is not None:
                print(f"Sound control is {'enabled' if sound_control_status else 'disabled'}")
        """
        self.logger.info("Getting sound control status (0xa8)...")
        response = await self.communicator.send_command_and_wait_for_response(COMMANDS["get sound ctrl"])
        if response and len(response) >= 1:
            return response[0]  # 1: enabled, 0: disabled
        return None

    async def send_current_temp(self, temp: int, weather: int) -> bool:
        """
        Send current temperature and weather (0x5f).
        
        Args:
            temp (int): Temperature value.
            weather (int): Weather type.
            
        Usage::
            
            # Send current temperature (25 C) and weather (clear)
            await divoom.device.send_current_temp(25, 1)
        """
        self.logger.info(f"Sending current temp: {temp}, weather: {weather} (0x5f)...")
        args = []
        args += temp.to_bytes(1, byteorder='big', signed=True)
        args += weather.to_bytes(1, byteorder='big')
        return await self.communicator.send_command(COMMANDS["send current temp"], args)

    async def set_temp_type(self, temp_type: int) -> bool:
        """
        Set the temperature format (0x2b).
        
        Args:
            temp_type (int): 0 for Celsius, 1 for Fahrenheit.
            
        Usage::
            
            # Set temperature to Celsius
            await divoom.device.set_temp_type(0)
        """
        self.logger.info(f"Setting temp type to {temp_type} (0x2b)...")
        args = [temp_type]
        return await self.communicator.send_command(COMMANDS["set temp type"], args)
