"""LightingApi — light/clock/channel/vj/visualization/text (REVIEW §1.2).

Extracts the display/lighting command surface.
"""
from __future__ import annotations

import logging
from divoom_gui.api import ApiBase

logger = logging.getLogger("divoom_gui.api.lighting")


class LightingApi(ApiBase):
    def __init__(self, loop_thread, daemon_client_getter, state_getter):
        super().__init__(loop_thread, daemon_client_getter, state_getter)

    def set_solid_light(self, color: str, brightness: int, mode_type: int = 0) -> bool:
        logger.info(f"GUI Action: Applying solid light {color} (brightness={brightness}, mode_type={mode_type})...")
        try:
            return self._dispatch(lambda t: t.set_light(color, brightness)
                                if t is self._wall_instance else t.display.show_light(color, brightness, True, mode_type))
        except Exception as e:
            logger.error(f"Light setting failed: {e}")
            return False

    def set_clock(self, style: int, color: str = None) -> bool:
        logger.info(f"GUI Action: Applying clock style {style} with color {color}...")
        try:
            return self._dispatch(lambda t: t.show_clock(clock=style)
                                if t is self._wall_instance else t.display.show_clock(clock=style, color=color))
        except Exception as e:
            logger.error(f"Clock setting failed: {e}")
            return False

    def switch_channel(self, channel: str) -> bool:
        logger.info(f"GUI Action: Switching channel to {channel}...")
        try:
            return self._dispatch(lambda t: t.switch_channel(channel)
                                if t is self._wall_instance else t.display.switch_channel(channel))
        except Exception as e:
            logger.error(f"Channel switch failed: {e}")
            return False

    def set_vj_effect(self, number: int) -> bool:
        logger.info(f"GUI Action: Applying VJ effect {number}...")
        try:
            return self._dispatch(lambda t: t.show_effects(number=int(number))
                                if t is self._wall_instance else t.display.show_effects(number=int(number)))
        except Exception as e:
            logger.error(f"VJ effect failed: {e}")
            return False

    def set_visualization(self, number: int) -> bool:
        logger.info(f"GUI Action: Applying visualizer {number}...")
        try:
            return self._dispatch(lambda t: t.show_visualization(number=int(number))
                                if t is self._wall_instance else t.display.show_visualization(number=int(number)))
        except Exception as e:
            logger.error(f"Visualizer failed: {e}")
            return False

    def push_text(self, text: str, color: str = "#FFFFFF", font_size: int = 1,
                  speed: int = 50, effect_style: int = 1) -> bool:
        from divoom_lib.models import (
            LPWA_CONTROL_DISPLAY_BOX, LPWA_CONTROL_FONT, LPWA_CONTROL_COLOR,
            LPWA_CONTROL_SPEED, LPWA_CONTROL_EFFECTS, LPWA_CONTROL_CONTENT,
        )

        async def _push(divoom, size: int) -> bool:
            t = divoom.text
            box = 0
            await t.set_light_phone_word_attr(LPWA_CONTROL_DISPLAY_BOX, x=0, y=0,
                                              width=size, height=size, text_box_id=box)
            await t.set_light_phone_word_attr(LPWA_CONTROL_FONT, font_size=int(font_size), text_box_id=box)
            await t.set_light_phone_word_attr(LPWA_CONTROL_COLOR, color=color, text_box_id=box)
            await t.set_light_phone_word_attr(LPWA_CONTROL_SPEED, speed=int(speed), text_box_id=box)
            await t.set_light_phone_word_attr(LPWA_CONTROL_EFFECTS, effect_style=int(effect_style))
            res = await t.set_light_phone_word_attr(LPWA_CONTROL_CONTENT, text_content=str(text), text_box_id=box)
            return res is not False

        try:
            if not text or not str(text).strip():
                return False
            if self._current_target_mode == "wall":
                if not self._rebuild_wall_instance():
                    return False
                return self._run_async(self._wall_instance.push_text(
                    str(text), color=color, font_size=int(font_size),
                    speed=int(speed), effect_style=int(effect_style)))

            target = self._current_divoom
            if not target:
                return False
            size = self._state_getter().get("_active_device_size", lambda: 16)()
            return self._run_async(_push(target, int(size)))
        except Exception as e:
            logger.error(f"push_text failed: {e}")
            return False

    def set_brightness(self, brightness: int) -> bool:
        logger.info(f"GUI Action: Setting brightness to {brightness}...")
        try:
            val = int(brightness)
            return self._dispatch(lambda t: t.set_brightness(val)
                                if t is self._wall_instance else
                                (t.lan.set_brightness(val) if t.lan else t.device.set_brightness(val)))
        except Exception as e:
            logger.error(f"Brightness setting failed: {e}")
            return False

    def set_volume(self, volume: int) -> bool:
        logger.info(f"GUI Action: Setting volume to {volume}...")
        try:
            val = max(0, min(15, int(volume)))
            return self._dispatch(lambda t: t.set_volume(val)
                                if t is self._wall_instance else t.music.set_volume(val))
        except Exception as e:
            logger.error(f"Volume setting failed: {e}")
            return False

    def display_wall_image(self, file_path: str, cell_size: int) -> bool:
        logger.info(f"GUI Action: Push display wall asset {file_path!r} (cell size={cell_size})...")
        try:
            return self._dispatch(lambda t: t.show_image(file_path))
        except Exception as e:
            logger.error(f"Wall display failed: {e}")
            return False

    def display_custom_art(self, file_path: str) -> bool:
        logger.info(f"GUI Action: Pushing custom art {file_path!r}...")
        try:
            return self._dispatch(lambda t: t.show_image(file_path)
                                if t is self._wall_instance else t.display.show_image(file_path))
        except Exception as e:
            logger.error(f"Failed to display custom art: {e}")
            return False