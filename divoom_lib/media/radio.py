
from divoom_lib.models import (
    COMMANDS
)

class Radio:
    """
    Provides functionality to control the FM radio of a Divoom device.
    """
    def __init__(self, communicator):
        """
        Initializes the Radio controller.

        Args:
            communicator: The communicator object to send commands to the device.
        """
        self.communicator = communicator
        self.logger = communicator.logger

    async def set_radio_frequency(self, frequency: int) -> bool:
        """
        Set the FM radio frequency.

        Args:
            frequency (int): The frequency to set, e.g., 875 for 87.5 MHz.

        Returns:
            bool: True if the command was sent successfully, False otherwise.
        """
        self.logger.info(f"Setting radio frequency to {frequency} (0x61)...")
        args = list(frequency.to_bytes(2, byteorder='little'))
        return await self.communicator.send_command(COMMANDS["set radio frequency"], args)
