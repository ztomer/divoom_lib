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
