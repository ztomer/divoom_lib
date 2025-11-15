# divoom_api/display.py
from .utils.image_processing import process_image, chunks, make_framepart
from . import constants
from .utils.converters import to_int_if_str, bool_to_byte

class Display:
    def __init__(self, communicator) -> None:
        self.communicator = communicator
        self.logger = communicator.logger

    async def show_clock(self, clock: int = 0, twentyfour: bool = True, weather: bool = False, temp: bool = False, calendar: bool = False, color: str | None = None, hot: bool | None = None) -> bool:
        """Show clock on the Divoom device in the color"""
        if hot:
            return await self.communicator.send_command("set hot", [])
        
        args = [constants.BOOLEAN_FALSE]
        args += [bool_to_byte(twentyfour)]
        if clock >= 0 and clock <= 15:
            args += clock.to_bytes(1, byteorder='big')  # clock mode/style
            args += [constants.BOOLEAN_TRUE]  # clock activated
        else:
            args += [constants.BOOLEAN_FALSE, constants.BOOLEAN_FALSE]  # clock mode/style = 0 and clock deactivated
        args += [bool_to_byte(weather)]
        args += [bool_to_byte(temp)]
        args += [bool_to_byte(calendar)]
        return await self.communicator.send_command("set light mode", args)

    async def _set_work_mode(self, mode: int, sub_command_args: list | None = None) -> bool:
        """Helper method to set the work mode."""
        args = [mode]
        result = await self.communicator.send_command("set work mode", args)
        if sub_command_args:
            result = await self.communicator.send_command("set design", sub_command_args)
        return result

    async def show_design(self, number: int | None = None) -> bool:
        """Show design on the Divoom device"""
        sub_command_args = None
        if number is not None:  # additionally change design tab
            number = to_int_if_str(number)
            sub_command_args = [constants.SUB_COMMAND_SET_DESIGN, number]
        return await self._set_work_mode(constants.WORK_MODE_DESIGN, sub_command_args)

    async def show_effects(self, number: int) -> bool:
        """Show VJ effects on the Divoom device"""
        return await self._set_work_mode(constants.WORK_MODE_EFFECTS, [number])

    async def show_image(self, file: str, time: int | None = None) -> bool:
        """Show image or animation on the Divoom device"""
        frames, framesCount = process_image(file, time=time)

        result = None
        if framesCount > 1:
            """Sending as Animation"""
            frameParts = []
            framePartsSize = 0

            for pair in frames:
                frameParts += pair[0]
                framePartsSize += pair[1]

            index = 0
            for framePart in chunks(frameParts, self.communicator.chunksize):
                frame = make_framepart(framePartsSize, index, framePart)
                result = await self.communicator.send_command("set animation frame", frame)
                index += 1

        elif framesCount == 1:
            """Sending as Image"""
            pair = frames[-1]
            frame = make_framepart(pair[1], -1, pair[0])
            result = await self.communicator.send_command("set image", frame)
        return result

    async def show_light(self, color: str, brightness: int | None = None, power: bool | None = None) -> bool:
        """Show light on the Divoom device in the color"""
        if power is None:
            power = True
        if brightness is None:
            brightness = 100
        brightness = to_int_if_str(brightness)

        # Channel number for Lightning is 0x01
        channel_number = constants.LIGHTNING_CHANNEL_NUMBER
        
        # Type of Lightning: 0x00 for Plain color
        type_of_lightning = constants.LIGHTNING_TYPE_PLAIN_COLOR

        # Power state: 0x01 for on, 0x00 for off
        power_state = bool_to_byte(power)

        rgb_color = self.communicator.convert_color(color)
        
        args = [
            constants.LIGHTNING_CHANNEL_NUMBER, # Channel number for Lightning
            rgb_color[0], rgb_color[1], rgb_color[2],
            brightness,
            type_of_lightning,
            power_state,
            constants.FIXED_STRING_BYTE, constants.FIXED_STRING_BYTE, constants.FIXED_STRING_BYTE # Fixed String 000000
        ]
        return await self.communicator.send_command("set channel light", args)

    async def show_visualization(self, number: int | None = None) -> bool:
        """Show visualization on the Divoom device"""
        if number is None:
            return False
        number = to_int_if_str(number)
        return await self._set_work_mode(constants.WORK_MODE_VISUALIZATION, [number])