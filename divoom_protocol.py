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

    async def send_playstate(self, value=None):
        """Send play/pause state to the Divoom device"""
        args = []
        args += (0x01 if value == True or value ==
                 1 else 0x00).to_bytes(1, byteorder='big')
        return await self.send_command("set playstate", args)

    async def show_radio(self, value=None, frequency=None):
        """Show radio on the Divoom device and optionally changes to the given frequency"""
        args = []
        args += (0x01 if value == True or value ==
                 1 else 0x00).to_bytes(1, byteorder='big')
        result = await self.send_command("set radio", args)

        if (value == True or value == 1) and frequency != None:
            if isinstance(frequency, str):
                frequency = float(frequency)

            args = []
            args += self._parse_frequency(frequency)
            await self.send_command("set radio frequency", args)
        return result

    async def show_sleep(self, value=None, sleeptime=None, sleepmode=None, volume=None, color=None, brightness=None, frequency=None):
        """Show sleep mode on the Divoom device and optionally sets mode, volume, time, color, frequency and brightness"""
        if sleeptime == None:
            sleeptime = 120
        if sleepmode == None:
            sleepmode = 0
        if volume == None:
            volume = 100
        if brightness == None:
            brightness = 100
        if isinstance(sleeptime, str):
            sleeptime = int(sleeptime)
        if isinstance(sleepmode, str):
            sleepmode = int(sleepmode)
        if isinstance(volume, str):
            volume = int(volume)
        if isinstance(brightness, str):
            brightness = int(brightness)

        args = []
        args += sleeptime.to_bytes(1, byteorder='big')
        args += sleepmode.to_bytes(1, byteorder='big')
        args += (0x01 if value == True or value ==
                 1 else 0x00).to_bytes(1, byteorder='big')

        args += self._parse_frequency(frequency)
        args += volume.to_bytes(1, byteorder='big')

        if color is None or len(color) < 3:
            args += [0x00, 0x00, 0x00]
        else:
            args += self.convert_color(color)
        args += brightness.to_bytes(1, byteorder='big')

        return await self.send_command("set sleeptime", args)

    async def get_sd_play_name(self):
        """Get the current sd card music playing name (0x06)."""
        self.logger.info("Getting SD play name (0x06)...")
        response = await self._send_command_and_wait_for_response("get sd play name")
        if response and len(response) >= 2:
            name_len = int.from_bytes(response[0:2], byteorder='little')
            if len(response) >= 2 + name_len:
                name_bytes = bytes(response[2:2+name_len])
                return name_bytes.decode('utf-8')
        return None

    async def get_sd_music_list(self, start_id: int, end_id: int):
        """Get a list of SD card music (0x07)."""
        self.logger.info(
            f"Getting SD music list from {start_id} to {end_id} (0x07)...")
        args = []
        args += start_id.to_bytes(2, byteorder='little')
        args += end_id.to_bytes(2, byteorder='little')
        response = await self._send_command_and_wait_for_response("get sd music list", args)

        music_list = []
        if response and len(response) >= 4:
            # Response format: Music id (2 bytes) + Name len (2 bytes) + Name (variable)
            offset = 0
            while offset < len(response):
                music_id = int.from_bytes(
                    response[offset:offset+2], byteorder='little')
                offset += 2
                name_len = int.from_bytes(
                    response[offset:offset+2], byteorder='little')
                offset += 2
                if offset + name_len <= len(response):
                    name = bytes(
                        response[offset:offset+name_len]).decode('utf-8')
                    music_list.append({"id": music_id, "name": name})
                    offset += name_len
                else:
                    self.logger.warning(
                        "Incomplete music list entry in response.")
                    break
        return music_list

    async def get_volume(self):
        """Get the current volume (0x09)."""
        self.logger.info("Getting volume (0x09)...")
        response = await self._send_command_and_wait_for_response("get volume")
        if response and len(response) >= 1:
            return response[0]  # 0-15
        return None

    async def get_play_status(self):
        """Get the current play status (0x0b)."""
        self.logger.info("Getting play status (0x0b)...")
        response = await self._send_command_and_wait_for_response("get play status")
        if response and len(response) >= 1:
            return response[0]  # 0: Pause, 1: Play
        return None

    async def set_sd_play_music_id(self, music_id: int):
        """Set the current playing song by ID (0x11)."""
        self.logger.info(f"Setting SD play music ID to {music_id} (0x11)...")
        args = music_id.to_bytes(2, byteorder='little')
        return await self.send_command("set sd play music id", list(args))

    async def set_sd_last_next(self, action: int):
        """Control previous or next track (0x12).
        action: 0 for previous, 1 for next."""
        self.logger.info(
            f"Setting SD last/next track action: {action} (0x12)...")
        args = [action]
        return await self.send_command("set sd last next", args)

    async def send_sd_list_over(self):
        """Notify that the playlist has been fully sent (0x14)."""
        self.logger.info("Sending SD list over notification (0x14)...")
        return await self.send_command("send sd list over")

    async def get_sd_music_list_total_num(self):
        """Get the total number of music tracks on the SD card (0x7d)."""
        self.logger.info("Getting SD music list total number (0x7d)...")
        response = await self._send_command_and_wait_for_response("get sd music list total num")
        if response and len(response) >= 2:
            return int.from_bytes(response[0:2], byteorder='little')
        return None

    async def get_sd_music_info(self):
        """Get SD card music playback information (0xb4)."""
        self.logger.info("Getting SD music info (0xb4)...")
        response = await self._send_command_and_wait_for_response("get sd music info")
        if response and len(response) >= 9:
            # {uint16_t cur_time; uint16_t total_time; uint16_t music_id; uint8_t status; uint8_t vol; uint8_t play_mode;}
            cur_time = int.from_bytes(response[0:2], byteorder='little')
            total_time = int.from_bytes(response[2:4], byteorder='little')
            music_id = int.from_bytes(response[4:6], byteorder='little')
            status = response[6]
            volume = response[7]
            play_mode = response[8]
            return {
                "current_time": cur_time,
                "total_time": total_time,
                "music_id": music_id,
                "status": status,
                "volume": volume,
                "play_mode": play_mode,
            }
        return None

    async def set_sd_music_info(self, current_time: int, music_id: int, volume: int, status: int, play_mode: int):
        """Set SD card music playback information (0xb5)."""
        self.logger.info(f"Setting SD music info (0xb5)...")
        args = []
        args += current_time.to_bytes(2, byteorder='little')
        args += music_id.to_bytes(2, byteorder='little')
        args += volume.to_bytes(1, byteorder='big')
        args += status.to_bytes(1, byteorder='big')
        args += play_mode.to_bytes(1, byteorder='big')
        return await self.send_command("set sd music info", args)

    async def set_sd_music_position(self, position: int):
        """Set the SD card music playback position (0xb8).
        position: in seconds (2 bytes, little-endian)."""
        self.logger.info(f"Setting SD music position to {position}s (0xb8)...")
        args = position.to_bytes(2, byteorder='little')
        return await self.send_command("set sd music position", list(args))

    async def set_sd_music_play_mode(self, play_mode: int):
        """Set the current playback mode of SD card music (0xb9).
        play_mode: 1: List loop, 2: Single loop, 3: Random play."""
        self.logger.info(
            f"Setting SD music play mode to {play_mode} (0xb9)...")
        args = [play_mode]
        return await self.send_command("set sd music play mode", args)

    async def app_need_get_music_list(self):
        """App requests to get the music playlist (0x47)."""
        self.logger.info("App needs to get music list (0x47)...")
        return await self.send_command("app need get music list")

    async def get_alarm_time(self):
        """Get alarm time (0x42)."""
        self.logger.info("Getting alarm time (0x42)...")
        response = await self._send_command_and_wait_for_response("get alarm time")
        if response and len(response) >= 10:  # 10 sets of alarm info
            alarms = []
            for i in range(10):
                # Assuming data format is similar to set alarm time (excluding animation data)
                # Uint8 alarm_index, status, hour, minute, week, mode, trigger_mode, Fm[2], volume
                # Each alarm is 9 bytes (excluding index)
                alarm_data = response[i*9:(i+1)*9]
                if len(alarm_data) == 9:
                    alarms.append({
                        "status": alarm_data[0],
                        "hour": alarm_data[1],
                        "minute": alarm_data[2],
                        "week": alarm_data[3],
                        "mode": alarm_data[4],
                        "trigger_mode": alarm_data[5],
                        "fm_freq": int.from_bytes(alarm_data[6:8], byteorder='little'),
                        "volume": alarm_data[8],
                    })
            return alarms
        return None

    async def set_alarm_gif(self, alarm_index: int, total_length: int, gif_id: int, data: list):
        """Set the alarm animation for a specific alarm (0x51)."""
        self.logger.info(
            f"Setting alarm GIF for index {alarm_index} (0x51)...")
        args = []
        args += alarm_index.to_bytes(1, byteorder='big')
        args += total_length.to_bytes(2, byteorder='little')
        args += gif_id.to_bytes(1, byteorder='big')
        args.extend(data)
        return await self.send_command("set alarm gif", args)

    async def get_memorial_time(self):
        """Get memorial time (0x53)."""
        self.logger.info("Getting memorial time (0x53)...")
        response = await self._send_command_and_wait_for_response("get memorial time")
        if response and len(response) >= 10 * 39:  # 10 records, each 39 bytes
            memorials = []
            for i in range(10):
                memorial_data = response[i*39:(i+1)*39]
                if len(memorial_data) == 39:
                    memorials.append({
                        "dialy_id": memorial_data[0],
                        "on_off": memorial_data[1],
                        "month": memorial_data[2],
                        "day": memorial_data[3],
                        "hour": memorial_data[4],
                        "minute": memorial_data[5],
                        "have_flag": memorial_data[6],
                        "title_name": bytes(memorial_data[7:39]).decode('utf-8').strip('\x00')
                    })
            return memorials
        return None

    async def set_memorial_gif(self, memorial_index: int, total_length: int, gif_id: int, data: list):
        """Set the memorial animation for a specific memorial (0x55)."""
        self.logger.info(
            f"Setting memorial GIF for index {memorial_index} (0x55)...")
        args = []
        args += memorial_index.to_bytes(1, byteorder='big')
        args += total_length.to_bytes(2, byteorder='little')
        args += gif_id.to_bytes(1, byteorder='big')
        args.extend(data)
        return await self.send_command("set memorial gif", args)

    async def set_alarm_listen(self, on_off: int, mode: int, volume: int):
        """Enable or disable the alarm audition feature (0xa5)."""
        self.logger.info(
            f"Setting alarm listen: on_off={on_off}, mode={mode}, volume={volume} (0xa5)...")
        args = []
        args += on_off.to_bytes(1, byteorder='big')
        args += mode.to_bytes(1, byteorder='big')
        args += volume.to_bytes(1, byteorder='big')
        return await self.send_command("set alarm listen", args)

    async def set_alarm_volume(self, volume: int):
        """Set the volume level for the alarm audition feature (0xa6)."""
        self.logger.info(f"Setting alarm volume to {volume} (0xa6)...")
        args = volume.to_bytes(1, byteorder='big')
        return await self.send_command("set alarm vol", list(args))

    async def set_alarm_volume_control(self, control: int, index: int):
        """Control the voice alarm feature (0x82)."""
        self.logger.info(
            f"Setting alarm volume control: control={control}, index={index} (0x82)...")
        args = []
        args += control.to_bytes(1, byteorder='big')
        args += index.to_bytes(1, byteorder='big')
        return await self.send_command("set alarm vol ctrl", args)

    async def set_time_manage_info(self, total_records: int, record_id: int, start_hour: int, start_min: int, end_hour: int, end_min: int, total_time: int, voice_alarm_on_off: int, display_mode: int, cycle_mode: int, pic_len: int, pic_data: list):
        """Set time management information (0x56)."""
        self.logger.info(f"Setting time manage info (0x56)...")
        args = []
        args += total_records.to_bytes(1, byteorder='big')
        args += record_id.to_bytes(1, byteorder='big')
        args += start_hour.to_bytes(1, byteorder='big')
        args += start_min.to_bytes(1, byteorder='big')
        args += end_hour.to_bytes(1, byteorder='big')
        args += end_min.to_bytes(1, byteorder='big')
        args += total_time.to_bytes(1, byteorder='big')
        args += voice_alarm_on_off.to_bytes(1, byteorder='big')
        args += display_mode.to_bytes(1, byteorder='big')
        args += cycle_mode.to_bytes(1, byteorder='big')
        args += pic_len.to_bytes(2, byteorder='little')
        args.extend(pic_data)
        return await self.send_command("set time manage info", args)

    async def set_time_manage_control(self, control: int):
        """Control time management (0x57)."""
        self.logger.info(f"Setting time manage control to {control} (0x57)...")
        args = [control]
        return await self.send_command("set time manage ctrl", args)

    async def get_sleep_scene(self):
        """Get the current scene mode settings from the device (0xa2)."""
        self.logger.info("Getting sleep scene (0xa2)...")
        response = await self._send_command_and_wait_for_response("get sleep scene")
        if response and len(response) >= 10:
            return {
                "time": response[0],
                "mode": response[1],
                "on": response[2],
                "fm_freq": int.from_bytes(response[3:5], byteorder='little'),
                "volume": response[5],
                "color_r": response[6],
                "color_g": response[7],
                "color_b": response[8],
                "light": response[9],
            }
        return None

    async def set_sleep_scene_listen(self, on_off: int, mode: int, volume: int):
        """Set the sleep mode listen settings (0xa3)."""
        self.logger.info(
            f"Setting sleep scene listen: on_off={on_off}, mode={mode}, volume={volume} (0xa3)...")
        args = []
        args += on_off.to_bytes(1, byteorder='big')
        args += mode.to_bytes(1, byteorder='big')
        args += volume.to_bytes(1, byteorder='big')
        return await self.send_command("set sleep scene listen", args)

    async def set_scene_volume(self, volume: int):
        """Set the volume level for the sleep mode listen feature (0xa4)."""
        self.logger.info(f"Setting scene volume to {volume} (0xa4)...")
        args = volume.to_bytes(1, byteorder='big')
        return await self.send_command("set scene vol", list(args))

    async def set_sleep_color(self, color: list):
        """Set the sleep mode color (0xad)."""
        self.logger.info(f"Setting sleep color to {color} (0xad)...")
        if color is None or len(color) < 3:
            self.logger.error("Color must be a list of 3 RGB values.")
            return False
        args = self.convert_color(color)
        return await self.send_command("set sleep color", args)

    async def set_sleep_light(self, light: int):
        """Set the sleep mode brightness (0xae)."""
        self.logger.info(f"Setting sleep light to {light} (0xae)...")
        args = light.to_bytes(1, byteorder='big')
        return await self.send_command("set sleep light", list(args))

    async def show_sleep(self, value=None, sleeptime=None, sleepmode=None, volume=None, color=None, brightness=None, frequency=None, on: int = None):
        """Show sleep mode on the Divoom device and optionally sets mode, volume, time, color, frequency and brightness (0x40)."""
        if sleeptime == None:
            sleeptime = 120
        if sleepmode == None:
            sleepmode = 0
        if volume == None:
            volume = 100
        if brightness == None:
            brightness = 100
        if on == None:
            on = 1  # Default to on if not specified
        if isinstance(sleeptime, str):
            sleeptime = int(sleeptime)
        if isinstance(sleepmode, str):
            sleepmode = int(sleepmode)
        if isinstance(volume, str):
            volume = int(volume)
        if isinstance(brightness, str):
            brightness = int(brightness)

        args = []
        args += sleeptime.to_bytes(1, byteorder='big')
        args += sleepmode.to_bytes(1, byteorder='big')
        args += on.to_bytes(1, byteorder='big')  # Added 'on' parameter
        args += self._parse_frequency(frequency)
        args += volume.to_bytes(1, byteorder='big')

        if color is None or len(color) < 3:
            args += [0x00, 0x00, 0x00]
        else:
            args += self.convert_color(color)
        args += brightness.to_bytes(1, byteorder='big')

        return await self.send_command("set sleeptime", args)

    async def set_sleep_scene(self, mode: int, on: int, fm_freq: list, volume: int, color: list, light: int):
        """Set the scene mode, including the sleep mode, without a time parameter (0x41)."""
        self.logger.info(
            f"Setting sleep scene: mode={mode}, on={on}, fm_freq={fm_freq}, volume={volume}, color={color}, light={light} (0x41)...")
        args = []
        args += mode.to_bytes(1, byteorder='big')
        args += on.to_bytes(1, byteorder='big')
        args.extend(fm_freq)  # Expecting a list of 2 bytes
        args += volume.to_bytes(1, byteorder='big')
        args.extend(self.convert_color(color))
        args += light.to_bytes(1, byteorder='big')
        return await self.send_command("set sleep scene", args)

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
