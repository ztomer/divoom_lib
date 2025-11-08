"""
Divoom Music Play Commands
"""

class Music:
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
