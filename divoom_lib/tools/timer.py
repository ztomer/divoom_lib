
from ..models import (
    COMMANDS,
    TOOL_TYPE_TIMER,
    GTI_TIMER_STATUS,
    STI_CTRL_FLAG_TIMER_PAUSED, STI_CTRL_FLAG_TIMER_STARTED, STI_CTRL_FLAG_TIMER_RESET,
    STI_CTRL_FLAG_TIMER_ENTERING_STOPWATCH
)

class Timer:
    def __init__(self, communicator):
        self.communicator = communicator
        self.logger = communicator.logger

    async def get_timer(self) -> dict | None:
        """Get information about the timer tool."""
        self.logger.info("Getting timer info (0x71)...")
        
        command_id = COMMANDS["get tool info"]
        args = [TOOL_TYPE_TIMER]
        
        # Set the command we are waiting for and send it with the correct protocol
        self.communicator._expected_response_command = command_id
        async with self.communicator._framing_context(use_ios=True, escape=False):
            await self.communicator.send_command(command_id, args)

        # Wait for the response using the default (Basic) protocol
        response = await self.communicator.wait_for_response(command_id)
        
        if response and len(response) >= 1:
            return {"status": response[GTI_TIMER_STATUS]}
        return None

    async def set_timer(self, ctrl_flag: int) -> bool:
        """Set information for the timer tool."""
        self.logger.info(
            f"Setting timer info: ctrl_flag={ctrl_flag} (0x72)...")

        args = [TOOL_TYPE_TIMER, ctrl_flag]
        return await self.communicator.send_command(COMMANDS["set tool"], args)
