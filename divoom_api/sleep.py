"""
Divoom Sleep Commands
"""

from .base import DivoomCommand

class Sleep:
    GET_SLEEP_SCENE = DivoomCommand(0xA2)
    SET_SLEEP_SCENE_LISTEN = DivoomCommand(0xA3)
    SET_SCENE_VOL = DivoomCommand(0xA4)
    SET_SLEEP_COLOR = DivoomCommand(0xAD)
    SET_SLEEP_LIGHT = DivoomCommand(0xAE)
    SET_SLEEP_AUTO_OFF = DivoomCommand(0x40)
    SET_SLEEP_SCENE = DivoomCommand(0x41)

    async def show_sleep(self, value=None, sleeptime=None, sleepmode=None, volume=None, color=None, brightness=None, frequency=None, on: int = None):
        """Show sleep mode on the Divoom device and optionally sets mode, volume, time, color, frequency and brightness (0x40)."""
        if sleeptime == None:
            sleeptime = 120
        if sleepmode == None:
            sleepmode = 0
        if volume == None:
            volume = 100
        if brightness == None:
            brightness = 100
        if on == None:
            on = 1  # Default to on if not specified
        if isinstance(sleeptime, str):
            sleeptime = int(sleeptime)
        if isinstance(sleepmode, str):
            sleepmode = int(sleepmode)
        if isinstance(volume, str):
            volume = int(volume)
        if isinstance(brightness, str):
            brightness = int(brightness)

        args = []
        args += sleeptime.to_bytes(1, byteorder='big')
        args += sleepmode.to_bytes(1, byteorder='big')
        args += on.to_bytes(1, byteorder='big')  # Added 'on' parameter
        args += self._parse_frequency(frequency)
        args += volume.to_bytes(1, byteorder='big')

        if color is None or len(color) < 3:
            args += [0x00, 0x00, 0x00]
        else:
            args += self.convert_color(color)
        args += brightness.to_bytes(1, byteorder='big')

        return await self.send_command("set sleeptime", args)

    async def get_sleep_scene(self):
        """Get the current scene mode settings from the device (0xa2)."""
        self.logger.info("Getting sleep scene (0xa2)...")
        response = await self._send_command_and_wait_for_response("get sleep scene")
        if response and len(response) >= 10:
            return {
                "time": response[0],
                "mode": response[1],
                "on": response[2],
                "fm_freq": int.from_bytes(response[3:5], byteorder='little'),
                "volume": response[5],
                "color_r": response[6],
                "color_g": response[7],
                "color_b": response[8],
                "light": response[9],
            }
        return None

    async def set_sleep_scene_listen(self, on_off: int, mode: int, volume: int):
        """Set the sleep mode listen settings (0xa3)."""
        self.logger.info(
            f"Setting sleep scene listen: on_off={on_off}, mode={mode}, volume={volume} (0xa3)...")
        args = []
        args += on_off.to_bytes(1, byteorder='big')
        args += mode.to_bytes(1, byteorder='big')
        args += volume.to_bytes(1, byteorder='big')
        return await self.send_command("set sleep scene listen", args)

    async def set_scene_volume(self, volume: int):
        """Set the volume level for the sleep mode listen feature (0xa4)."""
        self.logger.info(f"Setting scene volume to {volume} (0xa4)...")
        args = volume.to_bytes(1, byteorder='big')
        return await self.send_command("set scene vol", list(args))

    async def set_sleep_color(self, color: list):
        """Set the sleep mode color (0xad)."""
        self.logger.info(f"Setting sleep color to {color} (0xad)...")
        if color is None or len(color) < 3:
            self.logger.error("Color must be a list of 3 RGB values.")
            return False
        args = self.convert_color(color)
        return await self.send_command("set sleep color", args)

    async def set_sleep_light(self, light: int):
        """Set the sleep mode brightness (0xae)."""
        self.logger.info(f"Setting sleep light to {light} (0xae)...")
        args = light.to_bytes(1, byteorder='big')
        return await self.send_command("set sleep light", list(args))

    async def set_sleep_scene(self, mode: int, on: int, fm_freq: list, volume: int, color: list, light: int):
        """Set the scene mode, including the sleep mode, without a time parameter (0x41)."""
        self.logger.info(
            f"Setting sleep scene: mode={mode}, on={on}, fm_freq={fm_freq}, volume={volume}, color={color}, light={light} (0x41)...")
        args = []
        args += mode.to_bytes(1, byteorder='big')
        args += on.to_bytes(1, byteorder='big')
        args.extend(fm_freq)  # Expecting a list of 2 bytes
        args += volume.to_bytes(1, byteorder='big')
        args.extend(self.convert_color(color))
        args += light.to_bytes(1, byteorder='big')
        return await self.send_command("set sleep scene", args)
