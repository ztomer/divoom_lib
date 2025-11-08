"""
Divoom Game Commands
"""
import time
from .base import DivoomBase

class Game:
    SEND_GAME_SHARK = 0x88
    SET_GAME = 0xA0
    SET_GAME_CTRL_INFO = 0x17
    SET_GAME_CTRL_KEY_UP_INFO = 0x21

    async def show_game(self, value=None):
        """Show game on the Divoom device"""
        if isinstance(value, str):
            value = int(value)

        args = [0x00 if value == None else 0x01]
        args += (0 if value == None else value).to_bytes(1, byteorder='big')
        return await self.send_command("set game", args)

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
            result = await self.send_command("send game shark", args)
        elif value > 0:
            args += value.to_bytes(1, byteorder='big')
            # Updated command name
            result = await self.send_command("set game ctrl info", args)
            time.sleep(0.1)
            # Updated command name
            result = await self.send_command("set game ctrl key up info", args)
        return result