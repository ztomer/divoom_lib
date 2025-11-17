
from divoom_lib.models import (
    COMMANDS,
    TOOL_TYPE_COUNTDOWN,
    GTI_COUNTDOWN_STATUS, GTI_COUNTDOWN_MINUTES, GTI_COUNTDOWN_SECONDS,
    STI_CTRL_FLAG_COUNTDOWN_START, STI_CTRL_FLAG_COUNTDOWN_CANCEL
)

class Countdown:
    def __init__(self, communicator):
        self.communicator = communicator
        self.logger = communicator.logger

    async def get_countdown(self) -> dict | None:
        """Get information about the countdown tool."""
        self.logger.info("Getting countdown info (0x71)...")
        
        command_id = COMMANDS["get tool info"]
        args = [TOOL_TYPE_COUNTDOWN]
        
        # Set the command we are waiting for and send it with the correct protocol
        self.communicator._expected_response_command = command_id
        async with self.communicator._framing_context(use_ios=True, escape=False):
            await self.communicator.send_command(command_id, args)

        # Wait for the response using the default (Basic) protocol
        response = await self.communicator.wait_for_response(command_id)
        
        if response and len(response) >= 3:
            return {
                "status": response[GTI_COUNTDOWN_STATUS],
                "minutes": response[GTI_COUNTDOWN_MINUTES],
                "seconds": response[GTI_COUNTDOWN_SECONDS],
            }
        return None

    async def set_countdown(self, ctrl_flag: int, minutes: int, seconds: int) -> bool:
        """Set information for the countdown tool."""
        self.logger.info(
            f"Setting countdown info: ctrl_flag={ctrl_flag}, minutes={minutes}, seconds={seconds} (0x72)...")

        args = [TOOL_TYPE_COUNTDOWN, ctrl_flag, minutes, seconds]
        return await self.communicator.send_command(COMMANDS["set tool"], args)
