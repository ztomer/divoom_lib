"""
Divoom Game Commands
"""
import time

class Game:
    def __init__(self, communicator):
        self.communicator = communicator
        self.logger = communicator.logger

    async def show_game(self, value=None):
        """Show game on the Divoom device"""
        if isinstance(value, str):
            value = int(value)

        args = [0x00 if value == None else 0x01]
        args += (0 if value == None else value).to_bytes(1, byteorder='big')
        return await self.communicator.send_command("set game", args)

    async def send_gamecontrol(self, value=None):
        """Send game control to the Divoom device"""
        if value == None:
            value = 0
        if isinstance(value, str):
            if value == "go":
                value = 0
            elif value == "ok":
                value = 5
            elif value == "left":
                value = 1
            elif value == "right":
                value = 2
            elif value == "up":
                value = 3
            elif value == "down":
                value = 4

        result = None
        args = []
        if value == 0:
            # Updated command name
            result = await self.communicator.send_command("send game shark", args)
        elif value > 0:
            args += value.to_bytes(1, byteorder='big')
            # Updated command name
            result = await self.communicator.send_command("set game ctrl info", args)
            await asyncio.sleep(0.1)
            # Updated command name
            result = await self.communicator.send_command("set game ctrl key up info", args)
        return result