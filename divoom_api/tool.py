"""
Divoom Tool Commands
"""

from .base import DivoomCommand, DivoomBase

class Tool(DivoomBase):
    GET_TOOL_INFO = DivoomCommand(0x71)
    SET_TOOL_INFO = DivoomCommand(0x72)

    async def show_countdown(self, value=None, countdown=None):
        """Show countdown tool on the Divoom device"""
        if value == None:
            value = 1
        if isinstance(value, str):
            value = int(value)

        args = [0x03]
        args += (0x01 if value == True or value ==
                 1 else 0x00).to_bytes(1, byteorder='big')
        if countdown != None:
            args += int(countdown[0:2]).to_bytes(1, byteorder='big')
            args += int(countdown[3:]).to_bytes(1, byteorder='big')
        else:
            args += [0x00, 0x00]
        return await self.send_command(Tool.SET_TOOL_INFO, args)
