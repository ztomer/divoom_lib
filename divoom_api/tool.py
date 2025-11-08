"""
Divoom Tool Commands
"""

from .base import DivoomCommand, DivoomBase

class Tool(DivoomBase):
    GET_TOOL_INFO = DivoomCommand(0x71)
    SET_TOOL_INFO = DivoomCommand(0x72)

    async def show_countdown(self, value=None, countdown=None):
        """Show countdown tool on the Divoom device"""
        if value == None:
            value = 1
        if isinstance(value, str):
            value = int(value)

        args = [0x03]
        args += (0x01 if value == True or value ==
                 1 else 0x00).to_bytes(1, byteorder='big')
        if countdown != None:
            args += int(countdown[0:2]).to_bytes(1, byteorder='big')
            args += int(countdown[3:]).to_bytes(1, byteorder='big')
        else:
            args += [0x00, 0x00]
        return await self.send_command(Tool.SET_TOOL_INFO, args)

    async def show_noise(self, value=None):
        """Show noise tool on the Divoom device"""
        if value == None:
            value = 0
        if isinstance(value, str):
            value = int(value)

        args = [0x02]
        args += (0x01 if value == True or value ==
                 1 else 0x02).to_bytes(1, byteorder='big')
        return await self.send_command("set tool", args)

    async def show_timer(self, value=None):
        """Show timer tool on the Divoom device"""
        if value == None:
            value = 2
        if isinstance(value, str):
            value = int(value)

        args = [0x00]
        args += value.to_bytes(1, byteorder='big')
        return await self.send_command("set tool", args)

    async def get_tool_info(self, tool_type: int):
        """Get information about the tools available in the device (0x71)."""
        self.logger.info(f"Getting tool info for type {tool_type} (0x71)...")
        args = [tool_type]
        response = await self._send_command_and_wait_for_response("get tool info", args)
        if response:
            if tool_type == 0:  # DIVOOM_DISP_WATCH_MODE (Timer)
                if len(response) >= 1:
                    # 0: paused, 1: started, 2: reset, 3: entering stopwatch
                    return {"status": response[0]}
            elif tool_type == 1:  # DIVOOM_DISP_SCORE_MODE (Score)
                if len(response) >= 5:
                    return {
                        "on_off": response[0],
                        "red_score": int.from_bytes(response[1:3], byteorder='little'),
                        "blue_score": int.from_bytes(response[3:5], byteorder='little'),
                    }
            elif tool_type == 2:  # DIVOOM_DISP_NOISE_MODE (Noise)
                if len(response) >= 1:
                    return {"status": response[0]}  # 1: start, 2: stop
            elif tool_type == 3:  # DIVOOM_DISP_COUNT_TIME_DOWN (Countdown)
                if len(response) >= 3:
                    return {
                        "status": response[0],  # 0: start, 1: cancel
                        "minutes": response[1],
                        "seconds": response[2],
                    }
            elif tool_type == 0xFF:  # Not in any game mode
                return {"status": "not in game mode"}
        return None

    async def set_tool_info(self, game_mode_index: int, **kwargs):
        """Set information for the tools (games) available in the device (0x72).
        Handles different data structures based on game_mode_index."""
        self.logger.info(
            f"Setting tool info for game mode {game_mode_index} (0x72)...")
        args = [game_mode_index]

        if game_mode_index == 0:  # DIVOOM_DISP_WATCH_MODE (Timer)
            ctrl_flag = kwargs.get("ctrl_flag")
            if ctrl_flag is not None:
                args.append(ctrl_flag)
            else:
                self.logger.error("Missing 'ctrl_flag' for Timer mode.")
                return False
        elif game_mode_index == 1:  # DIVOOM_DISP_SCORE_MODE (Score)
            on_off = kwargs.get("on_off")
            red_score = kwargs.get("red_score", 0)
            blue_score = kwargs.get("blue_score", 0)
            if on_off is not None:
                args.append(on_off)
                args += red_score.to_bytes(2, byteorder='little')
                args += blue_score.to_bytes(2, byteorder='little')
            else:
                self.logger.error("Missing 'on_off' for Score mode.")
                return False
        elif game_mode_index == 2:  # DIVOOM_DISP_NOISE_MODE (Noise)
            ctrl_flag = kwargs.get("ctrl_flag")
            if ctrl_flag is not None:
                args.append(ctrl_flag)
            else:
                self.logger.error("Missing 'ctrl_flag' for Noise mode.")
                return False
        elif game_mode_index == 3:  # DIVOOM_DISP_COUNT_TIME_DOWN (Countdown)
            ctrl_flag = kwargs.get("ctrl_flag")
            minutes = kwargs.get("minutes")
            seconds = kwargs.get("seconds")
            if all(v is not None for v in [ctrl_flag, minutes, seconds]):
                args.append(ctrl_flag)
                args.append(minutes)
                args.append(seconds)
            else:
                self.logger.error(
                    "Missing 'ctrl_flag', 'minutes', or 'seconds' for Countdown mode.")
                return False
        else:
            self.logger.warning(f"Unknown game_mode_index: {game_mode_index}")
            return False

        return await self.send_command("set tool", args)