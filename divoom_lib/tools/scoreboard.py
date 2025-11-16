
from ..models import (
    COMMANDS,
    TOOL_TYPE_SCORE,
    GTI_SCORE_ON_OFF, GTI_SCORE_RED_SCORE_START, GTI_SCORE_RED_SCORE_LENGTH,
    GTI_SCORE_BLUE_SCORE_START, GTI_SCORE_BLUE_SCORE_LENGTH,
    STI_SCORE_OFF, STI_SCORE_ON
)

class Scoreboard:
    def __init__(self, communicator):
        self.communicator = communicator
        self.logger = communicator.logger

    async def get_scoreboard(self) -> dict | None:
        """Get information about the scoreboard tool."""
        self.logger.info("Getting scoreboard info (0x71)...")
        
        command_id = COMMANDS["get tool info"]
        args = [TOOL_TYPE_SCORE]
        
        # Set the command we are waiting for and send it with the correct protocol
        self.communicator._expected_response_command = command_id
        async with self.communicator._framing_context(use_ios=True, escape=False):
            await self.communicator.send_command(command_id, args)

        # Wait for the response using the default (Basic) protocol
        response = await self.communicator.wait_for_response(command_id)
        
        if response and len(response) >= 5:
            return {
                "on_off": response[GTI_SCORE_ON_OFF],
                "red_score": int.from_bytes(response[GTI_SCORE_RED_SCORE_START:GTI_SCORE_RED_SCORE_START + GTI_SCORE_RED_SCORE_LENGTH], byteorder='little'),
                "blue_score": int.from_bytes(response[GTI_SCORE_BLUE_SCORE_START:GTI_SCORE_BLUE_SCORE_START + GTI_SCORE_BLUE_SCORE_LENGTH], byteorder='little'),
            }
        return None

    async def set_scoreboard(self, on_off: int, red_score: int = 0, blue_score: int = 0) -> bool:
        """Set information for the scoreboard tool."""
        self.logger.info(
            f"Setting scoreboard info: on_off={on_off}, red_score={red_score}, blue_score={blue_score} (0x72)...")

        args = [TOOL_TYPE_SCORE]
        args.append(on_off)
        args.extend(red_score.to_bytes(2, byteorder='little'))
        args.extend(blue_score.to_bytes(2, byteorder='little'))

        return await self.communicator.send_command(COMMANDS["set tool"], args)
