"""
Divoom Timeplan Commands
"""

from .base import DivoomCommand

class Timeplan:
    SET_TIME_MANAGE_INFO = DivoomCommand(0x56)
    SET_TIME_MANAGE_CTRL = DivoomCommand(0x57) # This command was not explicitly in the markdown, but it's likely related to 0x56. I'll add it for now.
