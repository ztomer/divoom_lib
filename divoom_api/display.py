# divoom_api/display.py
from .utils.image_processing import process_image, chunks, make_framepart
from .utils.converters import color_to_rgb_list

class Display:
    def __init__(self, communicator):
        self.communicator = communicator
        self.logger = communicator.logger

    async def show_clock(self, clock=None, twentyfour=None, weather=None, temp=None, calendar=None, color=None, hot=None):
        """Show clock on the Divoom device in the color"""
        if clock == None:
            clock = 0
        if twentyfour == None:
            twentyfour = True
        if weather == None:
            weather = False
        if temp == None:
            temp = False
        if calendar == None:
            calendar = False

        args = [0x00]
        args += [0x01 if twentyfour == True or twentyfour == 1 else 0x00]
        if clock >= 0 and clock <= 15:
            args += clock.to_bytes(1, byteorder='big')  # clock mode/style
            args += [0x01]  # clock activated
        else:
            args += [0x00, 0x00]  # clock mode/style = 0 and clock deactivated
        args += [0x01 if weather == True or weather == 1 else 0x00]
        args += [0x01 if temp == True or temp == 1 else 0x00]
        args += [0x01 if calendar == True or calendar == 1 else 0x00]
        return await self.communicator.send_command("set light mode", args)

    async def show_design(self, number=None):
        """Show design on the Divoom device"""
        args = [0x05]
        result = await self.communicator.send_command("set work mode", args)

        if number != None:  # additionally change design tab
            if isinstance(number, str):
                number = int(number)

            args = [0x17]
            args += number.to_bytes(1, byteorder='big')
            result = await self.communicator.send_command("set design", args)
        return result

    async def show_effects(self, number):
        args = [0x04]
        args += number.to_bytes(1, byteorder='big')
        return await self.communicator.send_command("set work mode", args)

    async def show_image(self, file, time=None):
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

    async def show_light(self, color, brightness=None, power=None):
        """Show light on the Divoom device in the color"""
        if power is None:
            power = True
        if brightness is None:
            brightness = 100
        if isinstance(brightness, str):
            brightness = int(brightness)

        # Channel number for Lightning is 0x01
        channel_number = 0x01
        
        # Type of Lightning: 0x00 for Plain color
        type_of_lightning = 0x00

        # Power state: 0x01 for on, 0x00 for off
        power_state = 0x01 if power else 0x00

        rgb_color = self.communicator.convert_color(color)
        
        # The PROTOCOL.md indicates that 0x45 is the command for switching channels,
        # and the channel number (0x01 for Lightning) is the first argument.
        # The rest of the arguments are specific to the Lightning channel.
        args = [
            0x01, # Channel number for Lightning
            rgb_color[0], rgb_color[1], rgb_color[2],
            brightness,
            type_of_lightning,
            power_state,
            0x00, 0x00, 0x00 # Fixed String 000000
        ]
        return await self.communicator.send_command("set channel light", args)

    async def show_visualization(self, number, color1, color2):
        """Show visualization on the Divoom device"""
        if number == None:
            return
        if isinstance(number, str):
            number = int(number)

        args = [0x04]
        args += number.to_bytes(1, byteorder='big')
        return await self.communicator.send_command("set view", args)