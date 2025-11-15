"""
Divoom Light Commands
"""

from .constants import (
    COMMANDS,
    LPWA_CONTROL_SPEED, LPWA_CONTROL_EFFECTS, LPWA_CONTROL_DISPLAY_BOX,
    LPWA_CONTROL_FONT, LPWA_CONTROL_COLOR, LPWA_CONTROL_CONTENT, LPWA_CONTROL_IMAGE_EFFECTS,
    ANSGC_CONTROL_START_SENDING, ANSGC_CONTROL_SENDING_DATA, ANSGC_CONTROL_TERMINATE_SENDING,
    SUG_CONTROL_START_SAVING, SUG_CONTROL_TRANSMIT_DATA, SUG_CONTROL_TRANSMISSION_END,
    SUG_DATA_NORMAL_IMAGE, SUG_DATA_LED_EDITOR, SUG_DATA_SAND_PAINTING, SUG_DATA_SCROLL_ANIMATION,
    MUGI_DATA_GET_COUNT,
    ANUD_CONTROL_START_SENDING, ANUD_CONTROL_SENDING_DATA, ANUD_CONTROL_TERMINATE_SENDING,
    ABUD_CONTROL_START_SENDING, ABUD_CONTROL_SENDING_DATA, ABUD_CONTROL_TERMINATE_SENDING,
    ABUD_CONTROL_DELETE, ABUD_CONTROL_PLAY_ARTWORK, ABUD_CONTROL_DELETE_ALL_BY_INDEX,
    DCMP_CONTROL_EXIT_MOVIE_MODE, DCMP_CONTROL_START_MOVIE_PLAYBACK,
    SPC_CONTROL_INITIALIZE, SPC_CONTROL_RESET,
    PSC_CONTROL_SET_SCROLLING_MODE_SPEED, PSC_CONTROL_SENDING_IMAGE_DATA,
    GLM_CURRENT_LIGHT_EFFECT_MODE, GLM_TEMPERATURE_DISPLAY_MODE, GLM_VJ_SELECTION_OPTION,
    GLM_RGB_COLOR_VALUES_START, GLM_BRIGHTNESS_LEVEL, GLM_LIGHTING_MODE_SELECTION_OPTION,
    GLM_ON_OFF_SWITCH, GLM_MUSIC_MODE_SELECTION_OPTION, GLM_SYSTEM_BRIGHTNESS,
    GLM_TIME_DISPLAY_FORMAT_SELECTION_OPTION, GLM_TIME_DISPLAY_RGB_COLOR_VALUES_START,
    GLM_TIME_DISPLAY_MODE, GLM_TIME_CHECKBOX_MODES_START,
    AGUDI_CONTROL_WORD_SUCCESS, AGUDI_CONTROL_WORD_FAILURE
)

class Light:
    """
    Provides functionality to control the light and display of a Divoom device.

    This class implements a wide range of commands to control the device's
    display, including setting light modes, sending animations, and drawing.
    """
    def __init__(self, communicator):
        """
        Initializes the Light controller.

        Args:
            communicator: The communicator object to send commands to the device.
        """
        self.communicator = communicator
        self.logger = communicator.logger

    async def get_light_mode(self):
        """
        Get the current light mode settings from the device.

        This method sends a command (0x46) to the device to retrieve the current
        light mode settings and returns them as a dictionary.

        Returns:
            dict | None: A dictionary containing the light mode settings,
                         or None if the command fails.
        """
        self.logger.info("Getting light mode (0x46)...")
        
        command_id = COMMANDS["get light mode"]
        
        # Set the command we are waiting for and send it with the correct protocol
        self.communicator._expected_response_command = command_id
        async with self.communicator._framing_context(use_ios=True, escape=False):
            await self.communicator.send_command(command_id, [])

        # Wait for the response using the default (Basic) protocol
        response = await self.communicator.wait_for_response(command_id)
        
        # Based on documentation, response has 20 bytes
        if response and len(response) >= 20:
            return {
                "current_light_effect_mode": response[GLM_CURRENT_LIGHT_EFFECT_MODE],
                "temperature_display_mode": response[GLM_TEMPERATURE_DISPLAY_MODE],
                "vj_selection_option": response[GLM_VJ_SELECTION_OPTION],
                "rgb_color_values": [response[GLM_RGB_COLOR_VALUES_START], response[GLM_RGB_COLOR_VALUES_START + 1], response[GLM_RGB_COLOR_VALUES_START + 2]],
                "brightness_level": response[GLM_BRIGHTNESS_LEVEL],
                "lighting_mode_selection_option": response[GLM_LIGHTING_MODE_SELECTION_OPTION],
                "on_off_switch": response[GLM_ON_OFF_SWITCH],
                "music_mode_selection_option": response[GLM_MUSIC_MODE_SELECTION_OPTION],
                "system_brightness": response[GLM_SYSTEM_BRIGHTNESS],
                "time_display_format_selection_option": response[GLM_TIME_DISPLAY_FORMAT_SELECTION_OPTION],
                "time_display_rgb_color_values": [response[GLM_TIME_DISPLAY_RGB_COLOR_VALUES_START], response[GLM_TIME_DISPLAY_RGB_COLOR_VALUES_START + 1], response[GLM_TIME_DISPLAY_RGB_COLOR_VALUES_START + 2]],
                "time_display_mode": response[GLM_TIME_DISPLAY_MODE],
                "time_checkbox_modes": [response[GLM_TIME_CHECKBOX_MODES_START], response[GLM_TIME_CHECKBOX_MODES_START + 1], response[GLM_TIME_CHECKBOX_MODES_START + 2], response[GLM_TIME_CHECKBOX_MODES_START + 3]],
            }
        return None

    async def set_gif_speed(self, speed: int):
        """
        Set the animation speed for GIFs.

        Args:
            speed (int): The animation speed in milliseconds.

        Returns:
            bool: True if the command was sent successfully, False otherwise.
        """
        self.logger.info(f"Setting GIF speed to {speed}ms (0x16)...")
        args = speed.to_bytes(2, byteorder='little')
        return await self.communicator.send_command(COMMANDS["set gif speed"], list(args))

    def _handle_lpwa_speed(self, kwargs: dict) -> list | None:
        speed = kwargs.get("speed")
        text_box_id = kwargs.get("text_box_id")
        if speed is not None and text_box_id is not None:
            return list(speed.to_bytes(2, byteorder='little')) + list(text_box_id.to_bytes(1, byteorder='big'))
        self.logger.error("Missing 'speed' or 'text_box_id' for Text Speed control.")
        return None

    def _handle_lpwa_effects(self, kwargs: dict) -> list | None:
        effect_style = kwargs.get("effect_style")
        if effect_style is not None:
            return list(effect_style.to_bytes(1, byteorder='big'))
        self.logger.error("Missing 'effect_style' for Text Effects control.")
        return None

    def _handle_lpwa_display_box(self, kwargs: dict) -> list | None:
        x = kwargs.get("x")
        y = kwargs.get("y")
        width = kwargs.get("width")
        height = kwargs.get("height")
        text_box_id = kwargs.get("text_box_id")
        if all(v is not None for v in [x, y, width, height, text_box_id]):
            return list(x.to_bytes(1, byteorder='big')) + \
                   list(y.to_bytes(1, byteorder='big')) + \
                   list(width.to_bytes(1, byteorder='big')) + \
                   list(height.to_bytes(1, byteorder='big')) + \
                   list(text_box_id.to_bytes(1, byteorder='big'))
        self.logger.error("Missing parameters for Text Display Box control.")
        return None

    def _handle_lpwa_font(self, kwargs: dict) -> list | None:
        font_size = kwargs.get("font_size")
        text_box_id = kwargs.get("text_box_id")
        if font_size is not None and text_box_id is not None:
            return list(font_size.to_bytes(1, byteorder='big')) + list(text_box_id.to_bytes(1, byteorder='big'))
        self.logger.error("Missing 'font_size' or 'text_box_id' for Text Font control.")
        return None

    def _handle_lpwa_color(self, kwargs: dict) -> list | None:
        color = kwargs.get("color")
        text_box_id = kwargs.get("text_box_id")
        if color is not None and text_box_id is not None:
            rgb_color = self.communicator.convert_color(color)
            return rgb_color + list(text_box_id.to_bytes(1, byteorder='big'))
        self.logger.error("Missing 'color' (RGB list) or 'text_box_id' for Text Color control.")
        return None

    def _handle_lpwa_content(self, kwargs: dict) -> list | None:
        text_content = kwargs.get("text_content")
        text_box_id = kwargs.get("text_box_id")
        if text_content is not None and text_box_id is not None:
            content_bytes = text_content.encode('utf-8')
            return list(len(content_bytes).to_bytes(2, byteorder='little')) + \
                   list(content_bytes) + \
                   list(text_box_id.to_bytes(1, byteorder='big'))
        self.logger.error("Missing 'text_content' or 'text_box_id' for Text Content control.")
        return None

    def _handle_lpwa_image_effects(self, kwargs: dict) -> list | None:
        effect_style = kwargs.get("effect_style")
        text_box_id = kwargs.get("text_box_id")
        if effect_style is not None and text_box_id is not None:
            return list(effect_style.to_bytes(1, byteorder='big')) + list(text_box_id.to_bytes(1, byteorder='big'))
        self.logger.error("Missing 'effect_style' or 'text_box_id' for Image Effects control.")
        return None

    _lpwa_handlers = {
        LPWA_CONTROL_SPEED: _handle_lpwa_speed,
        LPWA_CONTROL_EFFECTS: _handle_lpwa_effects,
        LPWA_CONTROL_DISPLAY_BOX: _handle_lpwa_display_box,
        LPWA_CONTROL_FONT: _handle_lpwa_font,
        LPWA_CONTROL_COLOR: _handle_lpwa_color,
        LPWA_CONTROL_CONTENT: _handle_lpwa_content,
        LPWA_CONTROL_IMAGE_EFFECTS: _handle_lpwa_image_effects,
    }

    async def set_light_phone_word_attr(self, control: int, **kwargs):
        """
        Set various attributes of the animated text.

        This method sends a command (0x87) to control different aspects of
        animated text, such as speed, effects, color, and content.

        Args:
            control (int): The control word for the attribute to set.
                           (e.g., 1 for speed, 5 for color).
            **kwargs: The arguments for the control word.

        Returns:
            bool: True if the command was sent successfully, False otherwise.
        """
        self.logger.info(
            f"Setting light phone word attribute with control {control} (0x87)...")
        args = [control]

        handler = self._lpwa_handlers.get(control)
        if handler:
            control_args = handler(self, kwargs)
            if control_args is not None:
                args.extend(control_args)
            else:
                return False
        else:
            self.logger.warning(
                f"Unknown control word for set_light_phone_word_attr: {control}")
            return False

        return await self.communicator.send_command(COMMANDS["set light phone word attr"], args)

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
        """
        self.logger.info(
            f"App sending EQ GIF: pos={pos}, total_length={total_length}, gif_id={gif_id} (0x1b)...")
        args = []
        args += pos.to_bytes(1, byteorder='big')
        args += total_length.to_bytes(2, byteorder='little')
        args += gif_id.to_bytes(1, byteorder='big')
        args.extend(data)
        return await self.communicator.send_command(COMMANDS["app send eq gif"], args)

    async def drawing_mul_pad_ctrl(self, screen_id: int, r: int, g: int, b: int, num_points: int, offset_list: list):
        """
        Control the multiple screen drawing pad.

        Args:
            screen_id (int): The ID of the screen.
            r (int): Red color component (0-255).
            g (int): Green color component (0-255).
            b (int): Blue color component (0-255).
            num_points (int): The number of points to draw.
            offset_list (list): A list of offsets for the points.

        Returns:
            bool: True if the command was sent successfully, False otherwise.
        """
        self.logger.info(
            f"Drawing mul pad control: screen_id={screen_id}, color=({r},{g},{b}), num_points={num_points} (0x3a)...")
        args = []
        args += screen_id.to_bytes(1, byteorder='big')
        args += r.to_bytes(1, byteorder='big')
        args += g.to_bytes(1, byteorder='big')
        args += b.to_bytes(1, byteorder='big')
        args += num_points.to_bytes(1, byteorder='big')
        args.extend(offset_list)
        return await self.communicator.send_command(COMMANDS["drawing mul pad ctrl"], args)

    async def drawing_big_pad_ctrl(self, canvas_width: int, screen_id: int, r: int, g: int, b: int, num_points: int, offset_list: list):
        """
        Control the large screen drawing pad.

        Args:
            canvas_width (int): The width of the canvas.
            screen_id (int): The ID of the screen.
            r (int): Red color component (0-255).
            g (int): Green color component (0-255).
            b (int): Blue color component (0-255).
            num_points (int): The number of points to draw.
            offset_list (list): A list of offsets for the points.

        Returns:
            bool: True if the command was sent successfully, False otherwise.
        """
        self.logger.info(
            f"Drawing big pad control: canvas_width={canvas_width}, screen_id={screen_id}, color=({r},{g},{b}), num_points={num_points} (0x3b)...")
        args = []
        args += canvas_width.to_bytes(1, byteorder='big')
        args += screen_id.to_bytes(1, byteorder='big')
        args += r.to_bytes(1, byteorder='big')
        args += g.to_bytes(1, byteorder='big')
        args += b.to_bytes(1, byteorder='big')
        args += num_points.to_bytes(1, byteorder='big')
        args.extend(offset_list)
        return await self.communicator.send_command(COMMANDS["drawing big pad ctrl"], args)

    async def drawing_pad_ctrl(self, r: int, g: int, b: int, num_points: int, offset_list: list):
        """
        Control the drawing pad.

        Args:
            r (int): Red color component (0-255).
            g (int): Green color component (0-255).
            b (int): Blue color component (0-255).
            num_points (int): The number of points to draw.
            offset_list (list): A list of offsets for the points.

        Returns:
            bool: True if the command was sent successfully, False otherwise.
        """
        self.logger.info(
            f"Drawing pad control: color=({r},{g},{b}), num_points={num_points} (0x58)...")
        args = []
        args += r.to_bytes(1, byteorder='big')
        args += g.to_bytes(1, byteorder='big')
        args += b.to_bytes(1, byteorder='big')
        args += num_points.to_bytes(1, byteorder='big')
        args.extend(offset_list)
        return await self.communicator.send_command(COMMANDS["drawing pad ctrl"], args)

    async def drawing_pad_exit(self):
        """
        Exit the drawing pad.

        Returns:
            bool: True if the command was sent successfully, False otherwise.
        """
        self.logger.info("Drawing pad exit (0x5a)...")
        return await self.communicator.send_command(COMMANDS["drawing pad exit"])

    async def drawing_mul_encode_single_pic(self, screen_id: int, data_length: int, data: list):
        """
        Send a single encoded image to multiple screens.

        Args:
            screen_id (int): The ID of the screen.
            data_length (int): The length of the image data.
            data (list): The image data.

        Returns:
            bool: True if the command was sent successfully, False otherwise.
        """
        self.logger.info(
            f"Drawing mul encode single pic: screen_id={screen_id}, data_length={data_length} (0x5b)...")
        args = []
        args += screen_id.to_bytes(1, byteorder='big')
        args += data_length.to_bytes(2, byteorder='little')
        args.extend(data)
        return await self.communicator.send_command(COMMANDS["drawing mul encode single pic"], args)

    async def drawing_mul_encode_pic(self, screen_id: int, total_length: int, pic_id: int, pic_data: list):
        """
        Send encoded animation data to multiple screens for later playback.

        Args:
            screen_id (int): The ID of the screen.
            total_length (int): The total length of the animation data.
            pic_id (int): The ID of the picture.
            pic_data (list): The picture data.

        Returns:
            bool: True if the command was sent successfully, False otherwise.
        """
        self.logger.info(
            f"Drawing mul encode pic: screen_id={screen_id}, total_length={total_length}, pic_id={pic_id} (0x5c)...")
        args = []
        args += screen_id.to_bytes(1, byteorder='big')
        args += total_length.to_bytes(2, byteorder='little')
        args += pic_id.to_bytes(1, byteorder='big')
        args.extend(pic_data)
        return await self.communicator.send_command(COMMANDS["drawing mul encode pic"], args)

    async def drawing_mul_encode_gif_play(self):
        """
        Start playing the animation that was previously sent to multiple screens.

        Returns:
            bool: True if the command was sent successfully, False otherwise.
        """
        self.logger.info("Drawing mul encode GIF play (0x6b)...")
        return await self.communicator.send_command(COMMANDS["drawing mul encode gif play"])

    async def drawing_encode_movie_play(self, frame_id: int, data_length: int, data: list):
        """
        Play a single-screen movie or animation.

        Args:
            frame_id (int): The ID of the frame.
            data_length (int): The length of the frame data.
            data (list): The frame data.

        Returns:
            bool: True if the command was sent successfully, False otherwise.
        """
        self.logger.info(
            f"Drawing encode movie play: frame_id={frame_id}, data_length={data_length} (0x6c)...")
        args = []
        args += frame_id.to_bytes(2, byteorder='little')
        args += data_length.to_bytes(2, byteorder='little')
        args.extend(data)
        return await self.communicator.send_command(COMMANDS["drawing encode movie play"], args)

    async def drawing_mul_encode_movie_play(self, screen_id: int, frame_id: int, data_length: int, data: list):
        """
        Play a movie or animation on multiple screens.

        Args:
            screen_id (int): The ID of the screen.
            frame_id (int): The ID of the frame.
            data_length (int): The length of the frame data.
            data (list): The frame data.

        Returns:
            bool: True if the command was sent successfully, False otherwise.
        """
        self.logger.info(
            f"Drawing mul encode movie play: screen_id={screen_id}, frame_id={frame_id}, data_length={data_length} (0x6d)...")
        args = []
        args += screen_id.to_bytes(1, byteorder='big')
        args += frame_id.to_bytes(2, byteorder='little')
        args += data_length.to_bytes(2, byteorder='little')
        args.extend(data)
        return await self.communicator.send_command(COMMANDS["drawing mul encode movie play"], args)

    async def drawing_ctrl_movie_play(self, control_command: int):
        """
        Control the movie playback.

        Args:
            control_command (int): 0x00 to exit movie mode, 0x01 to start playback.

        Returns:
            bool: True if the command was sent successfully, False otherwise.
        """
        self.logger.info(
            f"Drawing control movie play: command={control_command} (0x6e)...")
        args = [control_command]
        return await self.communicator.send_command(COMMANDS["drawing ctrl movie play"], args)

    async def drawing_mul_pad_enter(self, r: int, g: int, b: int):
        """
        Enter the multiple screen drawing pad or clear the screen.

        Args:
            r (int): Red color component (0-255).
            g (int): Green color component (0-255).
            b (int): Blue color component (0-255).

        Returns:
            bool: True if the command was sent successfully, False otherwise.
        """
        self.logger.info(
            f"Drawing mul pad enter: color=({r},{g},{b}) (0x6f)...")
        args = []
        args += r.to_bytes(1, byteorder='big')
        args += g.to_bytes(1, byteorder='big')
        args += b.to_bytes(1, byteorder='big')
        return await self.communicator.send_command(COMMANDS["drawing mul pad enter"], args)

    def _handle_spc_initialize(self, kwargs: dict) -> list | None:
        device_id = kwargs.get("device_id")
        image_length = kwargs.get("image_length")
        image_data = kwargs.get("image_data")
        if device_id is not None and image_length is not None and image_data is not None:
            return list(device_id.to_bytes(1, byteorder='big')) + \
                   list(image_length.to_bytes(2, byteorder='little')) + \
                   image_data
        self.logger.error("Missing parameters for Initialize sand paint control.")
        return None

    def _handle_spc_reset(self, kwargs: dict) -> list | None:
        return [] # No additional data

    _spc_handlers = {
        SPC_CONTROL_INITIALIZE: _handle_spc_initialize,
        SPC_CONTROL_RESET: _handle_spc_reset,
    }

    async def sand_paint_ctrl(self, control: int, **kwargs):
        """
        Control the sand painting feature.

        Args:
            control (int): The control word (0 for initialize, 1 for reset).
            **kwargs: The arguments for the control word.

        Returns:
            bool: True if the command was sent successfully, False otherwise.
        """
        self.logger.info(f"Sand paint control: control={control} (0x34)...")
        args = [control]

        handler = self._spc_handlers.get(control)
        if handler:
            control_args = handler(self, kwargs)
            if control_args is not None:
                args.extend(control_args)
            else:
                return False
        else:
            self.logger.warning(
                f"Unknown control for sand_paint_ctrl: {control}")
            return False
        return await self.communicator.send_command(COMMANDS["sand paint ctrl"], args)

    def _handle_psc_set_scrolling_mode_speed(self, kwargs: dict) -> list | None:
        mode = kwargs.get("mode")
        speed = kwargs.get("speed")
        if mode is not None and speed is not None:
            return list(mode.to_bytes(1, byteorder='big')) + \
                   list(speed.to_bytes(2, byteorder='little'))
        self.logger.error("Missing 'mode' or 'speed' for Setting Scrolling Mode and Speed.")
        return None

    def _handle_psc_sending_image_data(self, kwargs: dict) -> list | None:
        total_length = kwargs.get("total_length")
        pic_id = kwargs.get("pic_id")
        data = kwargs.get("data")
        if total_length is not None and pic_id is not None and data is not None:
            return list(total_length.to_bytes(2, byteorder='little')) + \
                   list(pic_id.to_bytes(1, byteorder='big')) + \
                   data
        self.logger.error("Missing parameters for Sending Image Data.")
        return None

    _psc_handlers = {
        PSC_CONTROL_SET_SCROLLING_MODE_SPEED: _handle_psc_set_scrolling_mode_speed,
        PSC_CONTROL_SENDING_IMAGE_DATA: _handle_psc_sending_image_data,
    }

    async def pic_scan_ctrl(self, control: int, **kwargs):
        """
        Control the multi-screen scrolling effect.

        Args:
            control (int): The control word (0 for setting mode/speed, 1 for sending data).
            **kwargs: The arguments for the control word.

        Returns:
            bool: True if the command was sent successfully, False otherwise.
        """
        self.logger.info(f"Picture scan control: control={control} (0x35)...")
        args = [control]

        handler = self._psc_handlers.get(control)
        if handler:
            control_args = handler(self, kwargs)
            if control_args is not None:
                args.extend(control_args)
            else:
                return False
        else:
            self.logger.warning(
                f"Unknown control for pic_scan_ctrl: {control}")
            return False
        return await self.communicator.send_command(COMMANDS["pic scan ctrl"], args)


