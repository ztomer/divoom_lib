
from divoom_lib.models import (
    COMMANDS,
    ANSGC_CONTROL_START_SENDING, ANSGC_CONTROL_SENDING_DATA, ANSGC_CONTROL_TERMINATE_SENDING,
    SUG_CONTROL_START_SAVING, SUG_CONTROL_TRANSMIT_DATA, SUG_CONTROL_TRANSMISSION_END,
    SUG_DATA_NORMAL_IMAGE, SUG_DATA_LED_EDITOR, SUG_DATA_SAND_PAINTING, SUG_DATA_SCROLL_ANIMATION,
    MUGI_DATA_GET_COUNT,
    ANUD_CONTROL_START_SENDING, ANUD_CONTROL_SENDING_DATA, ANUD_CONTROL_TERMINATE_SENDING,
    ABUD_CONTROL_START_SENDING, ABUD_CONTROL_SENDING_DATA, ABUD_CONTROL_TERMINATE_SENDING,
    ABUD_CONTROL_DELETE, ABUD_CONTROL_PLAY_ARTWORK, ABUD_CONTROL_DELETE_ALL_BY_INDEX,
    AGUDI_CONTROL_WORD_SUCCESS, AGUDI_CONTROL_WORD_FAILURE
)

class Animation:
    """
    Provides functionality to control the animation features of a Divoom device.

    Usage::

        import asyncio
        from divoom_lib.divoom import Divoom

        async def main():
            device_address = "XX:XX:XX:XX:XX:XX"  # Replace with your device's address
            divoom = Divoom(mac=device_address)
            
            try:
                await divoom.protocol.connect()
                await divoom.animation.set_gif_speed(100)
            finally:
                if divoom.protocol.is_connected:
                    await divoom.protocol.disconnect()

        if __name__ == "__main__":
            asyncio.run(main())
    """
    def __init__(self, communicator):
        """
        Initializes the Animation controller.

        Args:
            communicator: The communicator object to send commands to the device.
        """
        self.communicator = communicator
        self.logger = communicator.logger

    async def set_gif_speed(self, speed: int):
        """
        Set the animation speed for GIFs.

        Args:
            speed (int): The animation speed in milliseconds.

        Returns:
            bool: True if the command was sent successfully, False otherwise.
        
        Usage::

            # Set the GIF speed to 100ms
            await divoom.animation.set_gif_speed(100)
        """
        self.logger.info(f"Setting GIF speed to {speed}ms (0x16)...")
        args = speed.to_bytes(2, byteorder='little')
        return await self.communicator.send_command(COMMANDS["set gif speed"], list(args))

    async def set_light_phone_gif(self, total_len: int, gif_id: int, gif_data: list) -> bool:
        """
        Display user-drawn animations on the device (0x49).

        Args:
            total_len (int): Total length of the data.
            gif_id (int): Sequential number of the sent data.
            gif_data (list): The encoded animation data.

        Returns:
            bool: True if the command was sent successfully, False otherwise.
        
        Usage::
            
            # This is a low-level command. Consider using a higher-level library for GIF processing.
            # await divoom.animation.set_light_phone_gif(total_len=100, gif_id=1, gif_data=[...])
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

    async def app_new_send_gif_cmd(self, control_word: int, **kwargs):
        """
        Send a new GIF animation to the device using the upgraded protocol.

        This method sends a command (0x8b) to transfer animated data to the
        device, using a chunked transfer mechanism.

        Args:
            control_word (int): The control word for the transfer
                                (e.g., start, send data, terminate).
            **kwargs: The arguments for the control word.

        Returns:
            bool: True if the command was sent successfully, False otherwise.
        
        Usage::
            
            # This is a low-level command. Consider using a higher-level library for GIF processing.
            # await divoom.animation.app_new_send_gif_cmd(control_word=0, file_size=100)
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

    def _handle_sug_start_saving_or_terminate_sending(self, kwargs: dict) -> list | None:
        data = kwargs.get("data")
        speed = kwargs.get("speed")
        text_length = kwargs.get("text_length")
        mode = kwargs.get("mode")
        len_val = kwargs.get("len_val")

        if data is not None and len(data) >= 1:
            # Data[0]: 0 for normal image, 1 for LED editor, 2 for sand painting, 3 for scroll animation
            args = [data[0]]
            if data[0] == SUG_DATA_LED_EDITOR:  # LED editor
                if speed is not None and text_length is not None and len(data) >= 3:
                    args.append(speed)
                    args.append(text_length)
                    args.extend(data[3:])  # File data
                else:
                    self.logger.error(
                        "Missing parameters for LED editor in set_user_gif.")
                    return None
            elif data[0] == SUG_DATA_SCROLL_ANIMATION:  # Scroll animation
                if mode is not None and speed is not None and len_val is not None:
                    args.append(mode)
                    args.extend(speed.to_bytes(2, byteorder='little'))
                    args.extend(len_val.to_bytes(2, byteorder='little'))
                else:
                    self.logger.error(
                        "Missing parameters for Scroll animation in set_user_gif.")
                    return None
            return args
        self.logger.error(
            "Missing 'data' for Start saving/Transmission end control word.")
        return None

    def _handle_sug_transmit_data(self, kwargs: dict) -> list | None:
        data = kwargs.get("data")
        if data is not None and len(data) >= 2:
            # Current data length
            args = list(len(data).to_bytes(2, byteorder='little'))
            args.extend(data)  # Image data
            return args
        self.logger.error(
            "Missing 'data' for Transmit data control word.")
        return None

    _sug_handlers = {
        SUG_CONTROL_START_SAVING: _handle_sug_start_saving_or_terminate_sending,
        SUG_CONTROL_TRANSMISSION_END: _handle_sug_start_saving_or_terminate_sending,
        SUG_CONTROL_TRANSMIT_DATA: _handle_sug_transmit_data,
    }

    async def set_user_gif(self, control_word: int, **kwargs):
        """
        Set a user-defined picture or animation.

        This method sends a command (0xb1) to upload a user-defined GIF
        to the device.

        Args:
            control_word (int): The control word for the transfer.
            **kwargs: The arguments for the control word.

        Returns:
            bool: True if the command was sent successfully, False otherwise.
        
        Usage::
            
            # This is a low-level command. Consider using a higher-level library for GIF processing.
            # await divoom.animation.set_user_gif(control_word=0, data=[...])
        """
        self.logger.info(
            f"Setting user GIF with control word {control_word} (0xb1)...")
        args = [control_word]

        handler = self._sug_handlers.get(control_word)
        if handler:
            control_args = handler(self, kwargs)
            if control_args is not None:
                args.extend(control_args)
            else:
                return False
        else:
            self.logger.warning(
                f"Unknown control word for set_user_gif: {control_word}")
            return False

        return await self.communicator.send_command(COMMANDS["set user gif"], args)

    async def modify_user_gif_items(self, data: int):
        """
        Get the number of user-defined items or delete a specific item.

        Args:
            data (int): 0xff to get the count of items, or the index of the
                        item to delete (1-indexed).

        Returns:
            int | None: The number of items if `data` is 0xff, or None.
        
        Usage::
            
            # Get the number of user GIFs
            num_gifs = await divoom.animation.modify_user_gif_items(0xff)
            if num_gifs is not None:
                print(f"Number of user GIFs: {num_gifs}")
        """
        self.logger.info(
            f"Modifying user GIF items with data {data} (0xb6)...")
        args = [data]
        response = await self.communicator.send_command_and_wait_for_response(COMMANDS["modify user gif items"], args)
        if response and len(response) >= 1:
            return response[0]  # Item number
        return None

    def _handle_anud_start_sending(self, kwargs: dict) -> list | None:
        file_size = kwargs.get("file_size")
        index = kwargs.get("index")
        if file_size is not None and index is not None:
            return list(file_size.to_bytes(4, byteorder='little')) + list(index.to_bytes(1, byteorder='big'))
        self.logger.error("Missing 'file_size' or 'index' for Start Sending control word.")
        return None

    def _handle_anud_sending_data(self, kwargs: dict) -> list | None:
        file_size = kwargs.get("file_size")
        file_offset_id = kwargs.get("file_offset_id")
        file_data = kwargs.get("file_data")
        if file_size is not None and file_offset_id is not None and file_data is not None:
            return list(file_size.to_bytes(4, byteorder='little')) + \
                   list(file_offset_id.to_bytes(2, byteorder='little')) + \
                   file_data
        self.logger.error("Missing 'file_size', 'file_offset_id', or 'file_data' for Sending Data control word.")
        return None

    def _handle_anud_terminate_sending(self, kwargs: dict) -> list | None:
        return [] # No additional data

    _anud_handlers = {
        ANUD_CONTROL_START_SENDING: _handle_anud_start_sending,
        ANUD_CONTROL_SENDING_DATA: _handle_anud_sending_data,
        ANUD_CONTROL_TERMINATE_SENDING: _handle_anud_terminate_sending,
    }

    async def app_new_user_define(self, control_word: int, **kwargs):
        """
        Send a new user-defined image frame.

        This method sends a command (0x8c) to transfer a user-defined image
        frame to the device.

        Args:
            control_word (int): The control word for the transfer.
            **kwargs: The arguments for the control word.

        Returns:
            bool: True if the command was sent successfully, False otherwise.
        
        Usage::
            
            # This is a low-level command. Consider using a higher-level library for image processing.
            # await divoom.animation.app_new_user_define(control_word=0, file_size=100, index=1)
        """
        self.logger.info(
            f"App new user define with control word {control_word} (0x8c)...")
        args = [control_word]

        handler = self._anud_handlers.get(control_word)
        if handler:
            control_args = handler(self, kwargs)
            if control_args is not None:
                args.extend(control_args)
            else:
                return False
        else:
            self.logger.warning(
                f"Unknown control word for app_new_user_define: {control_word}")
            return False

        return await self.communicator.send_command(COMMANDS["app new user define"], args)

    def _handle_abud_start_sending(self, kwargs: dict) -> list | None:
        file_size = kwargs.get("file_size")
        index = kwargs.get("index")
        file_id = kwargs.get("file_id")
        if file_size is not None and index is not None and file_id is not None:
            return list(file_size.to_bytes(4, byteorder='little')) + \
                   list(index.to_bytes(1, byteorder='big')) + \
                   list(file_id.to_bytes(4, byteorder='big'))
        self.logger.error("Missing 'file_size' or 'index' or 'file_id' for Start Sending control word.")
        return None

    def _handle_abud_sending_data(self, kwargs: dict) -> list | None:
        file_size = kwargs.get("file_size")
        file_offset_id = kwargs.get("file_offset_id")
        file_data = kwargs.get("file_data")
        if file_size is not None and file_offset_id is not None and file_data is not None:
            return list(file_size.to_bytes(4, byteorder='little')) + \
                   list(file_offset_id.to_bytes(2, byteorder='little')) + \
                   file_data
        self.logger.error("Missing 'file_size', 'file_offset_id', or 'file_data' for Sending Data control word.")
        return None

    def _handle_abud_terminate_sending(self, kwargs: dict) -> list | None:
        return [] # No additional data

    def _handle_abud_delete_or_play_artwork(self, kwargs: dict) -> list | None:
        file_id = kwargs.get("file_id")
        index = kwargs.get("index")
        if file_id is not None and index is not None:
            return list(file_id.to_bytes(4, byteorder='big')) + \
                   list(index.to_bytes(1, byteorder='big'))
        self.logger.error("Missing 'file_id' or 'index' for Delete/Play control word.")
        return None

    def _handle_abud_delete_all_by_index(self, kwargs: dict) -> list | None:
        index = kwargs.get("index")
        if index is not None:
            return list(index.to_bytes(1, byteorder='big'))
        self.logger.error("Missing 'index' for Delete all files control word.")
        return None

    _abud_handlers = {
        ABUD_CONTROL_START_SENDING: _handle_abud_start_sending,
        ABUD_CONTROL_SENDING_DATA: _handle_abud_sending_data,
        ABUD_CONTROL_TERMINATE_SENDING: _handle_abud_terminate_sending,
        ABUD_CONTROL_DELETE: _handle_abud_delete_or_play_artwork,
        ABUD_CONTROL_PLAY_ARTWORK: _handle_abud_delete_or_play_artwork,
        ABUD_CONTROL_DELETE_ALL_BY_INDEX: _handle_abud_delete_all_by_index,
    }

    async def app_big64_user_define(self, control_word: int, **kwargs):
        """
        Send a 64x64 user-defined image frame.

        This method sends a command (0x8d) to transfer a large (64x64)
        user-defined image frame to the device.

        Args:
            control_word (int): The control word for the transfer.
            **kwargs: The arguments for the control word.

        Returns:
            bool: True if the command was sent successfully, False otherwise.
        
        Usage::
            
            # This is a low-level command. Consider using a higher-level library for image processing.
            # await divoom.animation.app_big64_user_define(control_word=0, file_size=100, index=1, file_id=123)
        """
        self.logger.info(
            f"App big64 user define with control word {control_word} (0x8d)...")
        args = [control_word]

        handler = self._abud_handlers.get(control_word)
        if handler:
            control_args = handler(self, kwargs)
            if control_args is not None:
                args.extend(control_args)
            else:
                return False
        else:
            self.logger.warning(
                f"Unknown control word for app_big64_user_define: {control_word}")
            return False

        return await self.communicator.send_command(COMMANDS["app big64 user define"], args)

    async def app_get_user_define_info(self, user_index: int):
        """
        Get information about a 64x64 user-defined image frame.

        Args:
            user_index (int): The index of the user-defined image.

        Returns:
            dict | None: A dictionary containing information about the image,
                         or None if the command fails.
        
        Usage::
            
            user_define_info = await divoom.animation.app_get_user_define_info(0)
            if user_define_info:
                print(f"User define info: {user_define_info}")
        """
        self.logger.info(
            f"App get user define info for index {user_index} (0x8e)...")
        args = user_index.to_bytes(1, byteorder='big')
        response = await self.communicator.send_command_and_wait_for_response(COMMANDS["app get user define info"], list(args))
        if response and len(response) >= 1:
            control_word = response[0]
            if control_word == AGUDI_CONTROL_WORD_SUCCESS:
                if len(response) >= 8:
                    user_index_resp = response[1]
                    total = int.from_bytes(response[2:4], byteorder='little')
                    offset = int.from_bytes(response[4:6], byteorder='little')
                    num = int.from_bytes(response[6:8], byteorder='little')
                    file_ids = []
                    for i in range(num):
                        if len(response) >= 8 + (i+1)*4:
                            file_ids.append(int.from_bytes(
                                response[8+i*4:8+(i+1)*4], byteorder='big'))
                    return {
                        "control_word": control_word,
                        "user_index": user_index_resp,
                        "total": total,
                        "offset": offset,
                        "num": num,
                        "file_ids": file_ids,
                    }
            elif control_word == AGUDI_CONTROL_WORD_FAILURE:
                if len(response) >= 2:
                    user_index_resp = response[1]
                    return {
                        "control_word": control_word,
                        "user_index": user_index_resp,
                    }
        return None

    async def set_rhythm_gif(self, pos: int, total_length: int, gif_id: int, data: list):
        """
        Set the related information for the rhythm animation.

        Args:
            pos (int): The position of the data chunk.
            total_length (int): The total length of the animation data.
            gif_id (int): The ID of the GIF.
            data (list): The animation data chunk.

        Returns:
            bool: True if the command was sent successfully, False otherwise.
        
        Usage::
            
            # This is a low-level command. Consider using a higher-level library for GIF processing.
            # await divoom.animation.set_rhythm_gif(pos=0, total_length=100, gif_id=1, data=[...])
        """
        self.logger.info(
            f"Setting rhythm GIF: pos={pos}, total_length={total_length}, gif_id={gif_id} (0xb7)...")
        args = []
        args += pos.to_bytes(1, byteorder='big')
        args += total_length.to_bytes(2, byteorder='little')
        args += gif_id.to_bytes(1, byteorder='big')
        args.extend(data)
        return await self.communicator.send_command(COMMANDS["set rhythm gif"], args)

    async def app_send_eq_gif(self, pos: int, total_length: int, gif_id: int, data: list):
        """
        Send an EQ rhythm animation to the device.

        Args:
            pos (int): The position of the data chunk.
            total_length (int): The total length of the animation data.
            gif_id (int): The ID of the GIF.
            data (list): The animation data chunk.

        Returns:
            bool: True if the command was sent successfully, False otherwise.
        
        Usage::
            
            # This is a low-level command. Consider using a higher-level library for GIF processing.
            # await divoom.animation.app_send_eq_gif(pos=0, total_length=100, gif_id=1, data=[...])
        """
        self.logger.info(
            f"App sending EQ GIF: pos={pos}, total_length={total_length}, gif_id={gif_id} (0x1b)...")
        args = []
        args += pos.to_bytes(1, byteorder='big')
        args += total_length.to_bytes(2, byteorder='little')
        args += gif_id.to_bytes(1, byteorder='big')
        args.extend(data)
        return await self.communicator.send_command(COMMANDS["app send eq gif"], args)
