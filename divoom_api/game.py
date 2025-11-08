"""
Divoom Game Commands
"""

from .base import DivoomCommand

class Game:
    SEND_GAME_SHARK = DivoomCommand(0x88)
    SET_GAME = DivoomCommand(0xA0)
    SET_GAME_CTRL_INFO = DivoomCommand(0x17)
    SET_GAME_CTRL_KEY_UP_INFO = DivoomCommand(0x21)
