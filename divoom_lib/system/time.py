
from ..models import (
    COMMANDS,
    HOUR_TYPE_12, HOUR_TYPE_24, HOUR_TYPE_QUERY
)

class Time:
    def __init__(self, communicator) -> None:
        self.communicator = communicator
        self.logger = communicator.logger

    async def set_hour_type(self, hour_type: int) -> bool:
        """Set the hour format (0x2c).
        hour_type: 0 for 12-hour, 1 for 24-hour, 0xFF to query."""
        self.logger.info(f"Setting hour type to {hour_type} (0x2c)...")
        args = [hour_type]
        return await self.communicator.send_command(COMMANDS["set time type"], args)
