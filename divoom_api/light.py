"""
Divoom Light Commands
"""

from .base import DivoomCommand, DivoomBase

class Light(DivoomBase):
    SET_LIGHT_MODE = DivoomCommand(0x45)
    GET_LIGHT_MODE = DivoomCommand(0x46)
    SET_LIGHT_PIC = DivoomCommand(0x44)
    SET_LIGHT_PHONE_GIF = DivoomCommand(0x49)
    SET_GIF_SPEED = DivoomCommand(0x16)
    SET_LIGHT_PHONE_WORD_ATTR = DivoomCommand(0x87)
    APP_NEW_SEND_GIF_CMD = DivoomCommand(0x8B)
    SET_USER_GIF = DivoomCommand(0xB1)
    MODIFY_USER_GIF_ITEMS = DivoomCommand(0xB6)
    APP_NEW_USER_DEFINE = DivoomCommand(0x8C)
    APP_BIG64_USER_DEFINE = DivoomCommand(0x8D)
    APP_GET_USER_DEFINE_INFO = DivoomCommand(0x8E)
    SET_RHYTHM_GIF = DivoomCommand(0xB7)
    APP_SEND_EQ_GIF = DivoomCommand(0x1B)
    DRAWING_MUL_PAD_CTRL = DivoomCommand(0x3A)
    DRAWING_BIG_PAD_CTRL = DivoomCommand(0x3B)
    DRAWING_PAD_CTRL = DivoomCommand(0x58)
    DRAWING_PAD_EXIT = DivoomCommand(0x5A)
    DRAWING_MUL_ENCODE_SINGLE_PIC = DivoomCommand(0x5B)
    DRAWING_MUL_ENCODE_PIC = DivoomCommand(0x5C)
    DRAWING_MUL_ENCODE_GIF_PLAY = DivoomCommand(0x6B)
    DRAWING_ENCODE_MOVIE_PLAY = DivoomCommand(0x6C)
    DRAWING_MUL_ENCODE_MOVIE_PLAY = DivoomCommand(0x6D)
    DRAWING_CTRL_MOVIE_PLAY = DivoomCommand(0x6E)
    DRAWING_MUL_PAD_ENTER = DivoomCommand(0x6F)
    SAND_PAINT_CTRL = DivoomCommand(0x34)
    PIC_SCAN_CTRL = DivoomCommand(0x35)

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
        return await self.send_command(Light.SET_LIGHT_MODE, args)

    async def show_design(self, number=None):
        """Show design on the Divoom device"""
        args = [0x05]
        result = await self.send_command("set view", args)

        if number != None:  # additionally change design tab
            if isinstance(number, str):
                number = int(number)

            args = [0x17]
            args += number.to_bytes(1, byteorder='big')
            result = await self.send_command("set design", args)
        return result
