"""
Divoom Game Commands
"""
import time
import asyncio
from . import constants
from .utils.converters import to_int_if_str

class Game:
    """
    Provides functionality to control the game features of a Divoom device.
    """
    def __init__(self, communicator):
        """
        Initializes the Game controller.

        Args:
            communicator: The communicator object to send commands to the device.
        """
        self.communicator = communicator
        self.logger = communicator.logger

    async def show_game(self, value: int | None = None) -> bool:
        """
        Show or hide a game on the Divoom device.

        Args:
            value (int | None): The game to show. If None or 0, it hides the game.

        Returns:
            bool: True if the command was sent successfully, False otherwise.
        """
        value = to_int_if_str(value) if value is not None else 0
        
        game_state = constants.SHOW_GAME_ON if value > 0 else constants.SHOW_GAME_OFF
        args = [game_state, value]
        return await self.communicator.send_command(constants.COMMANDS["set game"], args)

    async def send_gamecontrol(self, value: str | int | None = None) -> bool:
        """
        Send a game control command to the Divoom device.

        Args:
            value (str | int | None): The control command to send.
                Can be a string ('up', 'down', 'left', 'right', 'go') or an integer.
                If None, it sends the 'go' command.

        Returns:
            bool: True if the command was sent successfully, False otherwise.
        """
        if value is None:
            control_value = constants.GAME_CONTROL_GO
        elif isinstance(value, str):
            control_value = constants.GAME_CONTROL_MAP.get(value.lower(), constants.GAME_CONTROL_GO)
        else:
            control_value = to_int_if_str(value)

        if control_value == constants.GAME_CONTROL_GO:
            return await self.communicator.send_command(constants.COMMANDS["send game shark"])
        else:
            args = [control_value]
            result = await self.communicator.send_command(constants.COMMANDS["set game ctrl info"], args)
            await asyncio.sleep(0.1)
            result = await self.communicator.send_command(constants.COMMANDS["set game ctrl key up info"], args)
            return result