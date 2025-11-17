
from divoom_lib.models import (
    COMMANDS,
    TOOL_TYPE_NOISE,
    GTI_NOISE_STATUS,
    STI_CTRL_FLAG_NOISE_START, STI_CTRL_FLAG_NOISE_STOP
)

class Noise:
    def __init__(self, communicator):
        self.communicator = communicator
        self.logger = communicator.logger

    async def get_noise(self) -> dict | None:
        """Get information about the noise tool."""
        self.logger.info("Getting noise info (0x71)...")
        
        command_id = COMMANDS["get tool info"]
        args = [TOOL_TYPE_NOISE]
        
        # Set the command we are waiting for and send it with the correct protocol
        self.communicator._expected_response_command = command_id
        async with self.communicator._framing_context(use_ios=True, escape=False):
            await self.communicator.send_command(command_id, args)

        # Wait for the response using the default (Basic) protocol
        response = await self.communicator.wait_for_response(command_id)
        
        if response and len(response) >= 1:
            return {"status": response[GTI_NOISE_STATUS]}
        return None

    async def set_noise(self, ctrl_flag: int) -> bool:
        """Set information for the noise tool."""
        self.logger.info(
            f"Setting noise info: ctrl_flag={ctrl_flag} (0x72)...")

        args = [TOOL_TYPE_NOISE, ctrl_flag]
        return await self.communicator.send_command(COMMANDS["set tool"], args)
