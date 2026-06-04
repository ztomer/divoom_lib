# divoom_lib/display/__init__.py
from .light import Light
from .drawing import Drawing
from .animation import Animation
from .text import Text
from .display_animation import DisplayAnimation
from .display_text import DisplayText

from ..utils.image_processing import process_image, chunks, make_framepart
from .. import models as constants
from ..utils.converters import to_int_if_str, bool_to_byte
from ..sender_protocol import CommandSender

class Display:
    def __init__(self, communicator: CommandSender) -> None:
        self.communicator = communicator
        self.logger = communicator.logger

    async def show_clock(self, clock: int = 0, twentyfour: bool = True, weather: bool = False, temp: bool = False, calendar: bool = False, color: str | None = None, hot: bool | None = None) -> bool:
        """Show clock on the Divoom device in the color"""
        clock = to_int_if_str(clock)
        if self.communicator.lan:
            await self.communicator.lan.set_clock(clock)
            return True
            
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
        
        # Always append color payload to guarantee full 10-byte environmental packet format.
        # This prevents the clock face channel from getting stuck or failing to switch styles.
        color_val = color or "#ffffff"
        rgb = self.communicator.convert_color(color_val)
        args += [rgb[0], rgb[1], rgb[2]]
        return await self.communicator.send_command("set light mode", args)

    async def _set_work_mode(self, mode: int, sub_command_args: list | None = None) -> bool:
        """Helper method to set the work mode."""
        args = [mode]
        result = await self.communicator.send_command("set work mode", args)
        if sub_command_args:
            result = await self.communicator.send_command("set design", sub_command_args)
        return result

    async def show_design(self, number: int | None = None) -> bool:
        """Show custom art / design channel on the Divoom device"""
        if self.communicator.lan:
            await self.communicator.lan.set_channel(3)
            return True
        # Under protocol.md: Animation channel is command 0x45, payload [0x05]
        return await self.communicator.send_command("set light mode", [0x05])

    async def show_effects(self, number: int) -> bool:
        """Show VJ effects on the Divoom device"""
        if self.communicator.lan:
            self.logger.warning("VJ effects are not supported on Wi-Fi (LAN) devices.")
            return False
        # VJ effects are 1-indexed (1-16) on BLE hardware
        return await self.communicator.send_command("set light mode", [0x03, int(number) + 1])

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

        rgb_color = self.communicator.convert_color(color)

        if self.communicator.lan:
            await self.communicator.lan.set_ambient_light(
                brightness, rgb_color[0], rgb_color[1], rgb_color[2], 1 if power else 0
            )
            return True

        # Channel number for Lightning is 0x01
        channel_number = constants.LIGHTNING_CHANNEL_NUMBER
        
        # Type of Lightning: 0x00 for Plain color
        type_of_lightning = constants.LIGHTNING_TYPE_PLAIN_COLOR

        # Power state: 0x01 for on, 0x00 for off
        power_state = bool_to_byte(power)
        
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
        if self.communicator.lan:
            await self.communicator.lan.set_channel(2)
            return True
        if number is None:
            return False
        number = to_int_if_str(number)
        # Under protocol.md: Visualization is command 0x45, payload [0x04, number]
        return await self.communicator.send_command("set light mode", [0x04, number])

    async def switch_channel(self, channel: str) -> bool:
        """Switches display active channel mode (Clock, Visualizer, VJ, Design)."""
        channel_lower = channel.lower()
        if self.communicator.lan:
            if channel_lower == "vj":
                self.logger.warning("VJ effects are not supported on Wi-Fi (LAN) devices.")
                return False
            mapping = {"clock": 0, "visualizer": 2, "design": 3}
            if channel_lower not in mapping:
                return False
            val = mapping[channel_lower]
            await self.communicator.lan.set_channel(val)
            return True

        if channel_lower == "clock":
            return await self.show_clock()
        elif channel_lower == "visualizer":
            return await self.show_visualization(number=0)
        elif channel_lower == "vj":
            return await self.show_effects(number=0)
        elif channel_lower == "design":
            return await self.show_design()
        return False

__all__ = ["Display", "Light", "Drawing", "Animation", "Text"]
