"""
Divoom Sleep Commands
"""
from .constants import (
    COMMANDS,
    SHOW_SLEEP_DEFAULT_SLEEPTIME, SHOW_SLEEP_DEFAULT_SLEEPMODE,
    SHOW_SLEEP_DEFAULT_VOLUME, SHOW_SLEEP_DEFAULT_BRIGHTNESS,
    SHOW_SLEEP_DEFAULT_ON, SHOW_SLEEP_DEFAULT_COLOR_RGB,
    GSS_RESPONSE_LENGTH, GSS_TIME, GSS_MODE, GSS_ON, GSS_FM_FREQ_START,
    GSS_VOLUME, GSS_COLOR_R, GSS_COLOR_G, GSS_COLOR_B, GSS_LIGHT,
    SET_SLEEP_COLOR_RGB_LENGTH
)
from .utils.converters import parse_frequency, to_int_if_str, bool_to_byte

class Sleep:
    """
    Provides functionality to control the sleep mode of a Divoom device.
    """

    def __init__(self, communicator):
        """
        Initializes the Sleep controller.

        Args:
            communicator: The communicator object to send commands to the device.
        """
        self.communicator = communicator
        self.logger = communicator.logger

    async def show_sleep(self, value=None, sleeptime: int = SHOW_SLEEP_DEFAULT_SLEEPTIME, sleepmode: int = SHOW_SLEEP_DEFAULT_SLEEPMODE, volume: int = SHOW_SLEEP_DEFAULT_VOLUME, color: list | None = None, brightness: int = SHOW_SLEEP_DEFAULT_BRIGHTNESS, frequency: int | None = None, on: int = SHOW_SLEEP_DEFAULT_ON) -> bool:
        """
        Show sleep mode on the Divoom device.

        This method can also set the mode, volume, time, color, frequency, and brightness.

        Args:
            value: This argument is not used.
            sleeptime (int): The sleep time in minutes.
            sleepmode (int): The sleep mode.
            volume (int): The volume level.
            color (list | None): The RGB color as a list of 3 integers.
            brightness (int): The brightness level.
            frequency (int | None): The FM radio frequency.
            on (int): 1 to turn on sleep mode, 0 to turn off.

        Returns:
            bool: True if the command was sent successfully, False otherwise.
        """
        sleeptime = to_int_if_str(sleeptime)
        sleepmode = to_int_if_str(sleepmode)
        volume = to_int_if_str(volume)
        brightness = to_int_if_str(brightness)

        args = []
        args += sleeptime.to_bytes(1, byteorder='big')
        args += sleepmode.to_bytes(1, byteorder='big')
        args.append(bool_to_byte(on))  # Use bool_to_byte directly
        args += parse_frequency(frequency)
        args += volume.to_bytes(1, byteorder='big')

        if color is None or len(color) < SET_SLEEP_COLOR_RGB_LENGTH:
            args += SHOW_SLEEP_DEFAULT_COLOR_RGB
        else:
            args += self.communicator.convert_color(color)
        args += brightness.to_bytes(1, byteorder='big')

        return await self.communicator.send_command(COMMANDS["set sleeptime"], args)

    async def get_sleep_scene(self):
        """
        Get the current sleep scene settings from the device.

        Returns:
            dict | None: A dictionary containing the sleep scene settings,
                         or None if the command fails.
        """
        self.logger.info("Getting sleep scene (0xa2)...")
        response = await self.communicator.send_command_and_wait_for_response(COMMANDS["get sleep scene"])
        if response and len(response) >= GSS_RESPONSE_LENGTH:
            return {
                "time": response[GSS_TIME],
                "mode": response[GSS_MODE],
                "on": response[GSS_ON],
                "fm_freq": int.from_bytes(response[GSS_FM_FREQ_START:GSS_FM_FREQ_START + 2], byteorder='little'),
                "volume": response[GSS_VOLUME],
                "color_r": response[GSS_COLOR_R],
                "color_g": response[GSS_COLOR_G],
                "color_b": response[GSS_COLOR_B],
                "light": response[GSS_LIGHT],
            }
        return None

    async def set_sleep_scene_listen(self, on_off: int, mode: int, volume: int) -> bool:
        """
        Set the sleep mode listen settings.

        Args:
            on_off (int): 1 to turn on, 0 to turn off.
            mode (int): The listen mode.
            volume (int): The volume level.

        Returns:
            bool: True if the command was sent successfully, False otherwise.
        """
        self.logger.info(
            f"Setting sleep scene listen: on_off={on_off}, mode={mode}, volume={volume} (0xa3)...")
        args = []
        args.append(bool_to_byte(on_off))
        args += mode.to_bytes(1, byteorder='big')
        args += volume.to_bytes(1, byteorder='big')
        return await self.communicator.send_command(COMMANDS["set sleep scene listen"], args)

    async def set_scene_volume(self, volume: int) -> bool:
        """
        Set the volume level for the sleep mode listen feature.

        Args:
            volume (int): The volume level.

        Returns:
            bool: True if the command was sent successfully, False otherwise.
        """
        self.logger.info(f"Setting scene volume to {volume} (0xa4)...")
        args = [volume]
        return await self.communicator.send_command(COMMANDS["set scene vol"], args)

    async def set_sleep_color(self, color: list):
        """
        Set the sleep mode color.

        Args:
            color (list): The RGB color as a list of 3 integers.

        Returns:
            bool: True if the command was sent successfully, False otherwise.
        """
        self.logger.info(f"Setting sleep color to {color} (0xad)...")
        if color is None or len(color) < SET_SLEEP_COLOR_RGB_LENGTH:
            self.logger.error("Color must be a list of 3 RGB values.")
            return False
        args = self.communicator.convert_color(color)
        return await self.communicator.send_command(COMMANDS["set sleep color"], args)

    async def set_sleep_light(self, light: int) -> bool:
        """
        Set the sleep mode brightness.

        Args:
            light (int): The brightness level.

        Returns:
            bool: True if the command was sent successfully, False otherwise.
        """
        self.logger.info(f"Setting sleep light to {light} (0xae)...")
        args = [light]
        return await self.communicator.send_command(COMMANDS["set sleep light"], args)

    async def set_sleep_scene(self, mode: int, on: int, fm_freq: list, volume: int, color: list, light: int) -> bool:
        """
        Set the sleep scene mode.

        Args:
            mode (int): The scene mode.
            on (int): 1 to turn on, 0 to turn off.
            fm_freq (list): The FM radio frequency as a list of 2 bytes.
            volume (int): The volume level.
            color (list): The RGB color as a list of 3 integers.
            light (int): The brightness level.

        Returns:
            bool: True if the command was sent successfully, False otherwise.
        """
        self.logger.info(
            f"Setting sleep scene: mode={mode}, on={on}, fm_freq={fm_freq}, volume={volume}, color={color}, light={light} (0x41)...")
        args = []
        args += mode.to_bytes(1, byteorder='big')
        args.append(bool_to_byte(on))
        args.extend(fm_freq)  # Expecting a list of 2 bytes
        args += volume.to_bytes(1, byteorder='big')
        args.extend(self.communicator.convert_color(color))
        args += light.to_bytes(1, byteorder='big')
        return await self.communicator.send_command(COMMANDS["set sleep scene"], args)
