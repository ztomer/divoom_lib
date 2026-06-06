import asyncio

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

    async def app_new_send_gif_cmd(self, control_word: int, write_with_response: bool = False, **kwargs) -> bool:
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

        return await self.communicator.send_command(COMMANDS["app new send gif cmd"], args, write_with_response=write_with_response)

    async def stream_animation_8b(self, blob: bytes) -> bool:
        """Stream a pre-encoded animation frame blob via the 0x8B 3-phase
        protocol, using the BLE-safe chunking + pacing proven by the
        monthly-best daemon (``stream_raw_bin_payload``).

        Differences from a naive tight loop (which stalls the device — R11
        items 1c/2a/9): ``file_offset_id`` is a sequential **chunk index**
        (0,1,2,…) not a byte offset; chunks are 200 bytes (BLE-safe); each
        BLE chunk is written **with response**; and the device gets time to
        allocate buffers (0.5s after start) and settle (0.5s before terminate),
        with a brief inter-chunk delay to avoid GATT congestion.

        Args:
            blob: concatenated per-frame bodies (see animation_8b._build_animation_blob).

        Returns:
            True if all three phases were acked, else False.
        """
        file_size = len(blob)
        if file_size <= 0:
            return False

        if not await self.app_new_send_gif_cmd(
            control_word=ANSGC_CONTROL_START_SENDING, file_size=file_size
        ):
            self.logger.error("0x8B start phase failed")
            return False
        await asyncio.sleep(0.5)  # let the device allocate buffers

        is_lan = getattr(self.communicator, "lan", None) is not None
        is_spp = getattr(self.communicator, "use_spp", False)
        is_ble = not is_lan and not is_spp
        write_with_response = is_ble
        delay = 0.01 if is_ble else 0.0

        chunk_size = 200  # BLE-safe payload size
        offset_id = 0
        for i in range(0, file_size, chunk_size):
            chunk = list(blob[i:i + chunk_size])
            if not await self.app_new_send_gif_cmd(
                control_word=ANSGC_CONTROL_SENDING_DATA,
                file_size=file_size,
                file_offset_id=offset_id,
                file_data=chunk,
                write_with_response=write_with_response,
            ):
                self.logger.error(f"0x8B data chunk {offset_id} failed")
                return False
            offset_id += 1
            if delay > 0:
                await asyncio.sleep(delay)

        await asyncio.sleep(0.5)  # let the device settle before terminate
        if not await self.app_new_send_gif_cmd(
            control_word=ANSGC_CONTROL_TERMINATE_SENDING
        ):
            self.logger.error("0x8B terminate phase failed")
            return False
        return True

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
