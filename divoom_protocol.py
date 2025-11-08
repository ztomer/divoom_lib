from .divoom_api.base import DivoomBase
from .divoom_api.system import System
from .divoom_api.alarm import Alarm
from .divoom_api.game import Game
from .divoom_api.light import Light
from .divoom_api.music import Music
from .divoom_api.sleep import Sleep
from .divoom_api.timeplan import Timeplan
from .divoom_api.tool import Tool


class DivoomBluetoothProtocol(DivoomBase, System, Alarm, Game, Light, Music, Sleep, Timeplan, Tool):
        """Class Divoom encapsulates the Divoom Bluetooth communication."""

    async def get_light_mode(self):

    async def get_light_mode(self):
        """Get the current light mode settings from the device (0x46)."""
        self.logger.info("Getting light mode (0x46)...")
        response = await self._send_command_and_wait_for_response("get light mode")
        # Based on documentation, response has 20 bytes
        if response and len(response) >= 20:
            return {
                "current_light_effect_mode": response[0],
                "temperature_display_mode": response[1],
                "vj_selection_option": response[2],
                "rgb_color_values": [response[3], response[4], response[5]],
                "brightness_level": response[6],
                "lighting_mode_selection_option": response[7],
                "on_off_switch": response[8],
                "music_mode_selection_option": response[9],
                "system_brightness": response[10],
                "time_display_format_selection_option": response[11],
                "time_display_rgb_color_values": [response[12], response[13], response[14]],
                "time_display_mode": response[15],
                "time_checkbox_modes": [response[16], response[17], response[18], response[19]],
            }
        return None

    async def set_gif_speed(self, speed: int):
        """Modify the animation speed (0x16).
        speed: Animation speed in milliseconds (2 bytes, little-endian)."""
        self.logger.info(f"Setting GIF speed to {speed}ms (0x16)...")
        args = speed.to_bytes(2, byteorder='little')
        return await self.send_command("set gif speed", list(args))

    async def set_light_phone_word_attr(self, control: int, **kwargs):
        """Set various attributes of the animated text (0x87).
        control: 1 (Speed), 2 (Effects), 3 (Display Box), 4 (Font), 5 (Color), 6 (Content), 7 (Image Effects)."""
        self.logger.info(
            f"Setting light phone word attribute with control {control} (0x87)...")
        args = [control]

        if control == 1:  # Changing Text Speed
            speed = kwargs.get("speed")
            text_box_id = kwargs.get("text_box_id")
            if speed is not None and text_box_id is not None:
                args += speed.to_bytes(2, byteorder='little')
                args += text_box_id.to_bytes(1, byteorder='big')
            else:
                self.logger.error(
                    "Missing 'speed' or 'text_box_id' for Text Speed control.")
                return False
        elif control == 2:  # Changing Text Effects
            effect_style = kwargs.get("effect_style")
            if effect_style is not None:
                args += effect_style.to_bytes(1, byteorder='big')
            else:
                self.logger.error(
                    "Missing 'effect_style' for Text Effects control.")
                return False
        elif control == 3:  # Changing Text Display Box
            x = kwargs.get("x")
            y = kwargs.get("y")
            width = kwargs.get("width")
            height = kwargs.get("height")
            text_box_id = kwargs.get("text_box_id")
            if all(v is not None for v in [x, y, width, height, text_box_id]):
                args += x.to_bytes(1, byteorder='big')
                args += y.to_bytes(1, byteorder='big')
                args += width.to_bytes(1, byteorder='big')
                args += height.to_bytes(1, byteorder='big')
                args += text_box_id.to_bytes(1, byteorder='big')
            else:
                self.logger.error(
                    "Missing parameters for Text Display Box control.")
                return False
        elif control == 4:  # Changing Text Font
            font_size = kwargs.get("font_size")
            text_box_id = kwargs.get("text_box_id")
            if font_size is not None and text_box_id is not None:
                args += font_size.to_bytes(1, byteorder='big')
                args += text_box_id.to_bytes(1, byteorder='big')
            else:
                self.logger.error(
                    "Missing 'font_size' or 'text_box_id' for Text Font control.")
                return False
        elif control == 5:  # Changing Text Color
            color = kwargs.get("color")
            text_box_id = kwargs.get("text_box_id")
            if color is not None and len(color) == 3 and text_box_id is not None:
                args.extend(self.convert_color(color))
                args += text_box_id.to_bytes(1, byteorder='big')
            else:
                self.logger.error(
                    "Missing 'color' (RGB list) or 'text_box_id' for Text Color control.")
                return False
        elif control == 6:  # Changing Text Content
            text_content = kwargs.get("text_content")
            text_box_id = kwargs.get("text_box_id")
            if text_content is not None and text_box_id is not None:
                content_bytes = text_content.encode('utf-8')
                args += len(content_bytes).to_bytes(2, byteorder='little')
                args.extend(list(content_bytes))
                args += text_box_id.to_bytes(1, byteorder='big')
            else:
                self.logger.error(
                    "Missing 'text_content' or 'text_box_id' for Text Content control.")
                return False
        elif control == 7:  # Changing Image Effects
            effect_style = kwargs.get("effect_style")
            text_box_id = kwargs.get("text_box_id")
            if effect_style is not None and text_box_id is not None:
                args += effect_style.to_bytes(1, byteorder='big')
                args += text_box_id.to_bytes(1, byteorder='big')
            else:
                self.logger.error(
                    "Missing 'effect_style' or 'text_box_id' for Image Effects control.")
                return False
        else:
            self.logger.warning(
                f"Unknown control word for set_light_phone_word_attr: {control}")
            return False

        return await self.send_command("set light phone word attr", args)

    async def app_new_send_gif_cmd(self, control_word: int, file_size: int = None, file_offset_id: int = None, file_data: list = None):
        """Used for the upgrade process to transfer animated data (0x8b)."""
        self.logger.info(
            f"App new send GIF command with control word {control_word} (0x8b)...")
        args = [control_word]

        if control_word == 0:  # Start Sending
            if file_size is not None:
                args += file_size.to_bytes(4, byteorder='little')
            else:
                self.logger.error(
                    "Missing 'file_size' for Start Sending control word.")
                return False
        elif control_word == 1:  # Sending Data
            if file_size is not None and file_offset_id is not None and file_data is not None:
                # Total Length
                args += file_size.to_bytes(4, byteorder='little')
                args += file_offset_id.to_bytes(2, byteorder='little')
                args.extend(file_data)
            else:
                self.logger.error(
                    "Missing 'file_size', 'file_offset_id', or 'file_data' for Sending Data control word.")
                return False
        elif control_word == 2:  # Terminate Sending
            pass  # No additional data
        else:
            self.logger.warning(
                f"Unknown control word for app_new_send_gif_cmd: {control_word}")
            return False

        return await self.send_command("app new send gif cmd", args)

    async def set_user_gif(self, control_word: int, data: list = None, speed: int = None, text_length: int = None, mode: int = None, len_val: int = None):
        """Set a user-defined picture (0xb1)."""
        self.logger.info(
            f"Setting user GIF with control word {control_word} (0xb1)...")
        args = [control_word]

        if control_word == 0 or control_word == 2:  # Start saving or Transmission end
            if data is not None and len(data) >= 1:
                # Data[0]: 0 for normal image, 1 for LED editor, 2 for sand painting, 3 for scroll animation
                args.append(data[0])
                if data[0] == 1:  # LED editor
                    if speed is not None and text_length is not None and len(data) >= 3:
                        args.append(speed)
                        args.append(text_length)
                        args.extend(data[3:])  # File data
                    else:
                        self.logger.error(
                            "Missing parameters for LED editor in set_user_gif.")
                        return False
                elif data[0] == 3:  # Scroll animation
                    if mode is not None and speed is not None and len_val is not None:
                        args.append(mode)
                        args += speed.to_bytes(2, byteorder='little')
                        args += len_val.to_bytes(2, byteorder='little')
                    else:
                        self.logger.error(
                            "Missing parameters for Scroll animation in set_user_gif.")
                        return False
            else:
                self.logger.error(
                    "Missing 'data' for Start saving/Transmission end control word.")
                return False
        elif control_word == 1:  # Transmit data
            if data is not None and len(data) >= 2:
                # Current data length
                args += len(data).to_bytes(2, byteorder='little')
                args.extend(data)  # Image data
            else:
                self.logger.error(
                    "Missing 'data' for Transmit data control word.")
                return False
        else:
            self.logger.warning(
                f"Unknown control word for set_user_gif: {control_word}")
            return False

        return await self.send_command("set user gif", args)

    async def modify_user_gif_items(self, data: int):
        """Get the number of user-defined items or delete a specific item (0xb6).
        data: 0xff to get count, other value to delete item (1-indexed)."""
        self.logger.info(
            f"Modifying user GIF items with data {data} (0xb6)...")
        args = [data]
        response = await self._send_command_and_wait_for_response("modify user gif items", args)
        if response and len(response) >= 1:
            return response[0]  # Item number
        return None

    async def app_new_user_define(self, control_word: int, file_size: int = None, index: int = None, file_offset_id: int = None, file_data: list = None):
        """New user-defined image frame transmission (0x8c)."""
        self.logger.info(
            f"App new user define with control word {control_word} (0x8c)...")
        args = [control_word]

        if control_word == 0:  # Start Sending
            if file_size is not None and index is not None:
                args += file_size.to_bytes(4, byteorder='little')
                args += index.to_bytes(1, byteorder='big')
            else:
                self.logger.error(
                    "Missing 'file_size' or 'index' for Start Sending control word.")
                return False
        elif control_word == 1:  # Sending Data
            if file_size is not None and file_offset_id is not None and file_data is not None:
                # Total Length
                args += file_size.to_bytes(4, byteorder='little')
                args += file_offset_id.to_bytes(2, byteorder='little')
                args.extend(file_data)
            else:
                self.logger.error(
                    "Missing 'file_size', 'file_offset_id', or 'file_data' for Sending Data control word.")
                return False
        elif control_word == 2:  # Terminate Sending
            pass  # No additional data
        else:
            self.logger.warning(
                f"Unknown control word for app_new_user_define: {control_word}")
            return False

        return await self.send_command("app new user define", args)

    async def app_big64_user_define(self, control_word: int, file_size: int = None, index: int = None, file_id: int = None, file_offset_id: int = None, file_data: list = None):
        """64 large canvas user-defined image frame transmission (0x8d)."""
        self.logger.info(
            f"App big64 user define with control word {control_word} (0x8d)...")
        args = [control_word]

        if control_word == 0:  # Start Sending
            if file_size is not None and index is not None and file_id is not None:
                args += file_size.to_bytes(4, byteorder='little')
                args += index.to_bytes(1, byteorder='big')
                # Assuming 4 bytes for File Id
                args += file_id.to_bytes(4, byteorder='big')
            else:
                self.logger.error(
                    "Missing 'file_size', 'index', or 'file_id' for Start Sending control word.")
                return False
        elif control_word == 1:  # Sending Data
            if file_size is not None and file_offset_id is not None and file_data is not None:
                # Total Length
                args += file_size.to_bytes(4, byteorder='little')
                args += file_offset_id.to_bytes(2, byteorder='little')
                args.extend(file_data)
            else:
                self.logger.error(
                    "Missing 'file_size', 'file_offset_id', or 'file_data' for Sending Data control word.")
                return False
        elif control_word == 2:  # Terminate Sending
            pass  # No additional data
        elif control_word == 3 or control_word == 4:  # Delete or Play specific artwork
            if file_id is not None and index is not None:
                args += file_id.to_bytes(4, byteorder='big')
                args += index.to_bytes(1, byteorder='big')
            else:
                self.logger.error(
                    "Missing 'file_id' or 'index' for Delete/Play control word.")
                return False
        elif control_word == 5:  # Delete all files of a specific index
            if index is not None:
                args += index.to_bytes(1, byteorder='big')
            else:
                self.logger.error(
                    "Missing 'index' for Delete all files control word.")
                return False
        else:
            self.logger.warning(
                f"Unknown control word for app_big64_user_define: {control_word}")
            return False

        return await self.send_command("app big64 user define", args)

    async def app_get_user_define_info(self, user_index: int):
        """64 custom image frame ID upload function (0x8e)."""
        self.logger.info(
            f"App get user define info for index {user_index} (0x8e)...")
        args = user_index.to_bytes(1, byteorder='big')
        response = await self._send_command_and_wait_for_response("app get user define info", list(args))
        if response and len(response) >= 1:
            control_word = response[0]
            if control_word == 1:
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
            elif control_word == 2:
                if len(response) >= 2:
                    user_index_resp = response[1]
                    return {
                        "control_word": control_word,
                        "user_index": user_index_resp,
                    }
        return None

    async def set_rhythm_gif(self, pos: int, total_length: int, gif_id: int, data: list):
        """Set the related information for the rhythm animation (0xb7)."""
        self.logger.info(
            f"Setting rhythm GIF: pos={pos}, total_length={total_length}, gif_id={gif_id} (0xb7)...")
        args = []
        args += pos.to_bytes(1, byteorder='big')
        args += total_length.to_bytes(2, byteorder='little')
        args += gif_id.to_bytes(1, byteorder='big')
        args.extend(data)
        return await self.send_command("set rhythm gif", args)

    async def app_send_eq_gif(self, pos: int, total_length: int, gif_id: int, data: list):
        """App sends EQ rhythm animation to the device (0x1b)."""
        self.logger.info(
            f"App sending EQ GIF: pos={pos}, total_length={total_length}, gif_id={gif_id} (0x1b)...")
        args = []
        args += pos.to_bytes(1, byteorder='big')
        args += total_length.to_bytes(2, byteorder='little')
        args += gif_id.to_bytes(1, byteorder='big')
        args.extend(data)
        return await self.send_command("app send eq gif", args)

    async def drawing_mul_pad_ctrl(self, screen_id: int, r: int, g: int, b: int, num_points: int, offset_list: list):
        """Multiple screen drawing pad control (0x3a)."""
        self.logger.info(
            f"Drawing mul pad control: screen_id={screen_id}, color=({r},{g},{b}), num_points={num_points} (0x3a)...")
        args = []
        args += screen_id.to_bytes(1, byteorder='big')
        args += r.to_bytes(1, byteorder='big')
        args += g.to_bytes(1, byteorder='big')
        args += b.to_bytes(1, byteorder='big')
        args += num_points.to_bytes(1, byteorder='big')
        args.extend(offset_list)
        return await self.send_command("drawing mul pad ctrl", args)

    async def drawing_big_pad_ctrl(self, canvas_width: int, screen_id: int, r: int, g: int, b: int, num_points: int, offset_list: list):
        """Controlling the large screen drawing pad (0x3b)."""
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
        return await self.send_command("drawing big pad ctrl", args)

    async def drawing_pad_ctrl(self, r: int, g: int, b: int, num_points: int, offset_list: list):
        """Controlling the large screen drawing pad (0x58)."""
        self.logger.info(
            f"Drawing pad control: color=({r},{g},{b}), num_points={num_points} (0x58)...")
        args = []
        args += r.to_bytes(1, byteorder='big')
        args += g.to_bytes(1, byteorder='big')
        args += b.to_bytes(1, byteorder='big')
        args += num_points.to_bytes(1, byteorder='big')
        args.extend(offset_list)
        return await self.send_command("drawing pad ctrl", args)

    async def drawing_pad_exit(self):
        """Exiting the drawing pad (0x5a)."""
        self.logger.info("Drawing pad exit (0x5a)...")
        return await self.send_command("drawing pad exit")

    async def drawing_mul_encode_single_pic(self, screen_id: int, data_length: int, data: list):
        """Sending a single image encoded to multiple screens (0x5b)."""
        self.logger.info(
            f"Drawing mul encode single pic: screen_id={screen_id}, data_length={data_length} (0x5b)...")
        args = []
        args += screen_id.to_bytes(1, byteorder='big')
        args += data_length.to_bytes(2, byteorder='little')
        args.extend(data)
        return await self.send_command("drawing mul encode single pic", args)

    async def drawing_mul_encode_pic(self, screen_id: int, total_length: int, pic_id: int, pic_data: list):
        """Sending encoded animation data to multiple screens for later playback (0x5c)."""
        self.logger.info(
            f"Drawing mul encode pic: screen_id={screen_id}, total_length={total_length}, pic_id={pic_id} (0x5c)...")
        args = []
        args += screen_id.to_bytes(1, byteorder='big')
        args += total_length.to_bytes(2, byteorder='little')
        args += pic_id.to_bytes(1, byteorder='big')
        args.extend(pic_data)
        return await self.send_command("drawing mul encode pic", args)

    async def drawing_mul_encode_gif_play(self):
        """Instruct the device to start playing the animation that was previously sent (0x6b)."""
        self.logger.info("Drawing mul encode GIF play (0x6b)...")
        return await self.send_command("drawing mul encode gif play")

    async def drawing_encode_movie_play(self, frame_id: int, data_length: int, data: list):
        """Instruct the device to play a single-screen movie or animation (0x6c)."""
        self.logger.info(
            f"Drawing encode movie play: frame_id={frame_id}, data_length={data_length} (0x6c)...")
        args = []
        args += frame_id.to_bytes(2, byteorder='little')
        args += data_length.to_bytes(2, byteorder='little')
        args.extend(data)
        return await self.send_command("drawing encode movie play", args)

    async def drawing_mul_encode_movie_play(self, screen_id: int, frame_id: int, data_length: int, data: list):
        """Instruct the device to play a single-screen movie or animation on multiple screens (0x6d)."""
        self.logger.info(
            f"Drawing mul encode movie play: screen_id={screen_id}, frame_id={frame_id}, data_length={data_length} (0x6d)...")
        args = []
        args += screen_id.to_bytes(1, byteorder='big')
        args += frame_id.to_bytes(2, byteorder='little')
        args += data_length.to_bytes(2, byteorder='little')
        args.extend(data)
        return await self.send_command("drawing mul encode movie play", args)

    async def drawing_ctrl_movie_play(self, control_command: int):
        """Control the movie playback on the device (0x6e).
        control_command: 0x00 (Exit movie mode), 0x01 (Start movie playback)."""
        self.logger.info(
            f"Drawing control movie play: command={control_command} (0x6e)...")
        args = [control_command]
        return await self.send_command("drawing ctrl movie play", args)

    async def drawing_mul_pad_enter(self, r: int, g: int, b: int):
        """Enter the multiple screen mode drawing pad or perform a clear screen operation (0x6f)."""
        self.logger.info(
            f"Drawing mul pad enter: color=({r},{g},{b}) (0x6f)...")
        args = []
        args += r.to_bytes(1, byteorder='big')
        args += g.to_bytes(1, byteorder='big')
        args += b.to_bytes(1, byteorder='big')
        return await self.send_command("drawing mul pad enter", args)

    async def sand_paint_ctrl(self, control: int, device_id: int = None, image_length: int = None, image_data: list = None):
        """Control command structure for managing sand painting (0x34).
        control: 0 (Initialize), 1 (Reset)."""
        self.logger.info(f"Sand paint control: control={control} (0x34)...")
        args = [control]
        if control == 0:  # Initialize
            if device_id is not None and image_length is not None and image_data is not None:
                args += device_id.to_bytes(1, byteorder='big')
                args += image_length.to_bytes(2, byteorder='little')
                args.extend(image_data)
            else:
                self.logger.error(
                    "Missing parameters for Initialize sand paint control.")
                return False
        elif control == 1:  # Reset
            pass  # No additional data
        else:
            self.logger.warning(
                f"Unknown control for sand_paint_ctrl: {control}")
            return False
        return await self.send_command("sand paint ctrl", args)

    async def pic_scan_ctrl(self, control: int, mode: int = None, speed: int = None, total_length: int = None, pic_id: int = None, data: list = None):
        """Control command structure for implementing a multi-screen scrolling effect (0x35).
        control: 0 (Setting Scrolling Mode and Speed), 1 (Sending Image Data)."""
        self.logger.info(f"Picture scan control: control={control} (0x35)...")
        args = [control]
        if control == 0:  # Setting Scrolling Mode and Speed
            if mode is not None and speed is not None:
                args += mode.to_bytes(1, byteorder='big')
                args += speed.to_bytes(2, byteorder='little')
            else:
                self.logger.error(
                    "Missing 'mode' or 'speed' for Setting Scrolling Mode and Speed.")
                return False
        elif control == 1:  # Sending Image Data
            if total_length is not None and pic_id is not None and data is not None:
                args += total_length.to_bytes(2, byteorder='little')
                args += pic_id.to_bytes(1, byteorder='big')
                args.extend(data)
            else:
                self.logger.error("Missing parameters for Sending Image Data.")
                return False
        else:
            self.logger.warning(
                f"Unknown control for pic_scan_ctrl: {control}")
            return False
        return await self.send_command("pic scan ctrl", args)
