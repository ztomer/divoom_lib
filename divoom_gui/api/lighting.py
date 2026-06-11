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

    def _stop_live_widgets(self) -> None:
        """A static-display takeover (channel / clock / VJ / visualizer / solid
        light) is mutually exclusive with a streaming live widget. Stop the
        active device's live jobs first, or the widget's next tick re-pushes its
        frame and clobbers the switch (HW-confirmed). Best-effort."""
        try:
            client = self._client
            if client is not None:
                client.live_jobs_stop_for()
        except Exception as e:
            logger.debug(f"stop live widgets before switch: {e}")

    def set_solid_light(self, color: str, brightness: int, mode_type: int = 0) -> bool:
        logger.info(f"GUI Action: Applying solid light {color} (brightness={brightness}, mode_type={mode_type})...")
        self._stop_live_widgets()
        try:
            return self._dispatch(lambda t: t.set_light(color, brightness)
                                if t is self._wall_instance else t.display.show_light(color, brightness, True, mode_type))
        except Exception as e:
            logger.error(f"Light setting failed: {e}")
            return False

    def set_clock(self, style: int, color: str = None) -> bool:
        logger.info(f"GUI Action: Applying clock style {style} with color {color}...")
        self._stop_live_widgets()
        try:
            return self._dispatch(lambda t: t.show_clock(clock=style)
                                if t is self._wall_instance else t.display.show_clock(clock=style, color=color))
        except Exception as e:
            logger.error(f"Clock setting failed: {e}")
            return False

    def switch_channel(self, channel: str) -> bool:
        logger.info(f"GUI Action: Switching channel to {channel}...")
        self._stop_live_widgets()
        try:
            return self._dispatch(lambda t: t.switch_channel(channel)
                                if t is self._wall_instance else t.display.switch_channel(channel))
        except Exception as e:
            logger.error(f"Channel switch failed: {e}")
            return False

    def set_vj_effect(self, number: int) -> bool:
        logger.info(f"GUI Action: Applying VJ effect {number}...")
        self._stop_live_widgets()
        try:
            return self._dispatch(lambda t: t.show_effects(number=int(number))
                                if t is self._wall_instance else t.display.show_effects(number=int(number)))
        except Exception as e:
            logger.error(f"VJ effect failed: {e}")
            return False

    def set_visualization(self, number: int) -> bool:
        logger.info(f"GUI Action: Applying visualizer {number}...")
        self._stop_live_widgets()
        try:
            return self._dispatch(lambda t: t.show_visualization(number=int(number))
                                if t is self._wall_instance else t.display.show_visualization(number=int(number)))
        except Exception as e:
            logger.error(f"Visualizer failed: {e}")
            return False

    def push_text(self, text: str, color: str = "#FFFFFF", font_size: int = 1,
                  speed: int = 50, effect_style: int = 1) -> bool:
        """Render the text to a device-sized bitmap and push it as an image.

        R32 §D: the old path used the 0x87 "set light phone word attr" (LPWA)
        sequence, which does NOT render on the Pixoo-class LED matrices these
        devices are — so nothing appeared. The known-working reference
        (hass-divoom) and futpib both render text into image frames and push
        them via the normal image path; we do the same here with our own
        no-AA bitmap font. ``speed``/``effect_style`` are accepted for call
        compatibility but unused for now (static image); scrolling frames are
        a follow-up. ``font_size`` selects the small vs. full glyph set."""
        try:
            if not text or not str(text).strip():
                return False
            size = self._device_size()
            png_path = self._render_text_png(str(text), color, int(size), int(font_size))
            try:
                return self._dispatch(lambda t: t.show_image(png_path)
                                    if t is self._wall_instance else t.display.show_image(png_path))
            finally:
                try:
                    import os
                    os.unlink(png_path)
                except OSError:
                    pass
        except Exception as e:
            logger.error(f"push_text failed: {e}")
            return False

    def _device_size(self) -> int:
        getter = self._state_getter().get("_active_device_size")
        try:
            return int(getter() if callable(getter) else (getter or 16))
        except Exception:
            return 16

    @staticmethod
    def _render_text_png(text: str, color: str, size: int, font_size: int) -> str:
        """Render ``text`` centered on a ``size``×``size`` black canvas using the
        device bitmap font, scaling down to fit when it overflows. Returns a
        temp PNG path (caller deletes it)."""
        import os
        import tempfile
        from PIL import Image
        from divoom_lib.fonts.bitmap_font import get_default_font, get_small_font
        from divoom_lib.utils.converters import color_to_rgb_list

        rgb_list = color_to_rgb_list(color) or [255, 255, 255]
        rgb = tuple(rgb_list[:3]) if len(rgb_list) >= 3 else (255, 255, 255)
        # Small glyphs fit more characters on the narrow 16px matrix; the full
        # set is used when the caller asks for the larger font or on bigger
        # screens where it stays legible.
        font = get_small_font() if (font_size <= 1 or size <= 16) else get_default_font()
        text_img = font.render(text, fill=rgb, bg=(0, 0, 0), mode="RGB")

        sz = max(1, int(size))
        tw, th = text_img.size
        scale = 1.0
        if tw > sz:
            scale = sz / tw
        if th * scale > sz:
            scale = min(scale, sz / th)
        if scale < 1.0:
            text_img = text_img.resize(
                (max(1, int(tw * scale)), max(1, int(th * scale))), Image.NEAREST)
            tw, th = text_img.size

        canvas = Image.new("RGB", (sz, sz), (0, 0, 0))
        canvas.paste(text_img, (max(0, (sz - tw) // 2), max(0, (sz - th) // 2)))
        fd, path = tempfile.mkstemp(prefix="divoom_text_", suffix=".png")
        os.close(fd)
        canvas.save(path)
        return path

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

    def display_wall_image(self, file_path: str, cell_size: int) -> dict:
        logger.info(f"GUI Action: Push display wall asset {file_path!r} (cell size={cell_size})...")
        try:
            self._rebuild_wall_instance(cell_size)
            target = self._wall_instance if self._wall_instance else self._current_divoom
            if target is None:
                raise RuntimeError("No active device or wall configured")

            if target is self._wall_instance:
                ok = self._run_async(target.show_image(file_path))
            else:
                ok = self._run_async(target.display.show_image(file_path))

            previews = {}
            if ok and self._wall_instance:
                try:
                    # R42 §6: the wall handle is a DaemonDeviceProxy — method
                    # calls return AWAITABLES. The bare call returned an
                    # un-awaited coroutine that poisoned the JSON reply, so the
                    # arranger never received its previews.
                    previews = self._run_async(self._wall_instance.get_last_previews())
                    if not isinstance(previews, dict):
                        previews = {}
                except Exception as ex:
                    logger.warning(f"Failed to get wall previews: {ex}")
            return {"success": bool(ok), "previews": previews}
        except Exception as e:
            logger.error(f"Wall display failed: {e}")
            return {"success": False, "error": str(e), "previews": {}}

    def set_temperature_channel(self, celsius: bool = True, color: str = "#ffffff") -> bool:
        logger.info(f"GUI Action: Setting temperature channel (celsius={celsius}, color={color})...")
        try:
            return self._dispatch(lambda t: t.display.set_temperature_channel(celsius=celsius, color=color)
                                if t is self._wall_instance else t.display.set_temperature_channel(celsius=celsius, color=color))
        except Exception as e:
            logger.error(f"Temperature channel failed: {e}")
            return False

    def set_clock_rich(self, style: int = 0, twentyfour: bool = True,
                       humidity: bool = False, weather: bool = False,
                       date: bool = False, color: str = "#ffffff") -> bool:
        logger.info(f"GUI Action: Setting rich clock (style={style}, twentyfour={twentyfour}, ...)")
        try:
            return self._dispatch(lambda t: t.display.set_clock_rich(style=style, twentyfour=twentyfour,
                                                                     humidity=humidity, weather=weather,
                                                                     date=date, color=color)
                                if t is self._wall_instance else t.display.set_clock_rich(style=style, twentyfour=twentyfour,
                                                                                          humidity=humidity, weather=weather,
                                                                                          date=date, color=color))
        except Exception as e:
            logger.error(f"Rich clock failed: {e}")
            return False

    def display_custom_art(self, file_path: str) -> bool:
        logger.info(f"GUI Action: Pushing custom art {file_path!r}...")
        try:
            return self._dispatch(lambda t: t.show_image(file_path)
                                if t is self._wall_instance else t.display.show_image(file_path))
        except Exception as e:
            logger.error(f"Failed to display custom art: {e}")
            return False