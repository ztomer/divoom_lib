from divoom_lib.sender_protocol import CommandSender
from divoom_lib.models import (
    COMMANDS,
    ANSGC_CONTROL_START_SENDING, ANSGC_CONTROL_SENDING_DATA, ANSGC_CONTROL_TERMINATE_SENDING,
    SUG_CONTROL_START_SAVING, SUG_CONTROL_TRANSMIT_DATA, SUG_CONTROL_TRANSMISSION_END,
    SUG_DATA_LED_EDITOR, SUG_DATA_SCROLL_ANIMATION,
    ANUD_CONTROL_START_SENDING, ANUD_CONTROL_SENDING_DATA, ANUD_CONTROL_TERMINATE_SENDING,
    ABUD_CONTROL_START_SENDING, ABUD_CONTROL_SENDING_DATA, ABUD_CONTROL_TERMINATE_SENDING,
    ABUD_CONTROL_DELETE, ABUD_CONTROL_PLAY_ARTWORK, ABUD_CONTROL_DELETE_ALL_BY_INDEX,
    AGUDI_CONTROL_WORD_SUCCESS, AGUDI_CONTROL_WORD_FAILURE
)
from .animation_user import AnimationUserDefine

class Animation(AnimationUserDefine):
    """
    Provides functionality to control the animation features of a Divoom device.

    Usage::

        import asyncio
        from divoom_lib import Divoom

        async def main():
            device_address = "XX:XX:XX:XX:XX:XX"  # Replace with your device's address
            divoom = Divoom(mac=device_address)
            
            try:
                await divoom.connect()
                await divoom.animation.set_gif_speed(100)
            finally:
                if divoom.is_connected:
                    await divoom.disconnect()

        if __name__ == "__main__":
            asyncio.run(main())
    """
    def __init__(self, divoom: CommandSender):
        """
        Initializes the Animation controller.

        Args:
            divoom: The Divoom object to send commands to the device.
        """
        super().__init__(divoom)

    async def set_gif_speed(self, speed: int) -> bool:
        """
        Set the animation speed for GIFs.
        """
        self.logger.info(f"Setting GIF speed to {speed}ms (0x16)...")
        args = speed.to_bytes(2, byteorder='little')
        return await self.communicator.send_command(COMMANDS["set gif speed"], list(args))

    async def set_light_phone_gif(self, total_len: int, gif_id: int, gif_data: list) -> bool:
        """
        Display user-drawn animations on the device (0x49).
        """
        self.logger.info(f"Setting light phone gif (0x49)...")
        args = []
        args += total_len.to_bytes(2, byteorder='little')
        args += gif_id.to_bytes(1, byteorder='big')
        args.extend(gif_data)
        return await self.communicator.send_command(COMMANDS["set light phone gif"], args)

    def _handle_ansgc_start_sending(self, kwargs: dict) -> list | None:
        file_size = kwargs.get("file_size")
        if file_size is not None:
            return list(file_size.to_bytes(4, byteorder='little'))
        self.logger.error("Missing 'file_size' for Start Sending control word.")
        return None

    def _handle_ansgc_sending_data(self, kwargs: dict) -> list | None:
        file_size = kwargs.get("file_size")
        file_offset_id = kwargs.get("file_offset_id")
        file_data = kwargs.get("file_data")
        if file_size is not None and file_offset_id is not None and file_data is not None:
            return list(file_size.to_bytes(4, byteorder='little')) + \
                   list(file_offset_id.to_bytes(2, byteorder='little')) + \
                   file_data
        self.logger.error("Missing 'file_size', 'file_offset_id', or 'file_data' for Sending Data control word.")
        return None

    def _handle_ansgc_terminate_sending(self, kwargs: dict) -> list | None:
        return [] # No additional data

    _ansgc_handlers = {
        ANSGC_CONTROL_START_SENDING: _handle_ansgc_start_sending,
        ANSGC_CONTROL_SENDING_DATA: _handle_ansgc_sending_data,
        ANSGC_CONTROL_TERMINATE_SENDING: _handle_ansgc_terminate_sending,
    }

    async def app_new_send_gif_cmd(self, control_word: int, **kwargs) -> bool:
        """
        Send a new GIF animation to the device using the upgraded protocol.
        """
        self.logger.info(
            f"App new send GIF command with control word {control_word} (0x8b)...")
        args = [control_word]

        handler = self._ansgc_handlers.get(control_word)
        if handler:
            control_args = handler(self, kwargs)
            if control_args is not None:
                args.extend(control_args)
            else:
                return False
        else:
            self.logger.warning(
                f"Unknown control word for app_new_send_gif_cmd: {control_word}")
            return False

        return await self.communicator.send_command(COMMANDS["app new send gif cmd"], args)

    async def set_rhythm_gif(self, pos: int, total_length: int, gif_id: int, data: list) -> bool:
        """
        Set the related information for the rhythm animation.
        """
        self.logger.info(
            f"Setting rhythm GIF: pos={pos}, total_length={total_length}, gif_id={gif_id} (0xb7)...")
        args = []
        args += pos.to_bytes(1, byteorder='big')
        args += total_length.to_bytes(2, byteorder='little')
        args += gif_id.to_bytes(1, byteorder='big')
        args.extend(data)
        return await self.communicator.send_command(COMMANDS["set rhythm gif"], args)

    async def app_send_eq_gif(self, pos: int, total_length: int, gif_id: int, data: list) -> bool:
        """
        Send an EQ rhythm animation to the device.
        """
        self.logger.info(
            f"App sending EQ GIF: pos={pos}, total_length={total_length}, gif_id={gif_id} (0x1b)...")
        args = []
        args += pos.to_bytes(1, byteorder='big')
        args += total_length.to_bytes(2, byteorder='little')
        args += gif_id.to_bytes(1, byteorder='big')
        args.extend(data)
        return await self.communicator.send_command(COMMANDS["app send eq gif"], args)
