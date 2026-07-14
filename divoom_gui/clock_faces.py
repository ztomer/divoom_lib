# gui/clock_faces.py

import logging

from divoom_lib.cloud import CloudClient

logger = logging.getLogger("divoom_gui")


class ClockFacesMixin:
    """Mixin for browsing Divoom's public clock-face catalog
    (Channel/GetDialType + Channel/GetDialList — see divoom_lib/cloud.py for
    the full writeup on why this is a different, unauthenticated endpoint
    pair from the pixel-art gallery). Applying a selected clock face reuses
    the existing set_clock() -> display.show_clock() path (LightingApi).
    """

    def get_dial_types(self) -> list[str]:
        try:
            return CloudClient().get_dial_types()
        except Exception as e:
            logger.error(f"get_dial_types failed: {e}")
            return []

    def get_dial_list(self, dial_type: str, page: int = 1) -> list[dict]:
        try:
            return CloudClient().get_dial_list(dial_type, page=page)
        except Exception as e:
            logger.error(f"get_dial_list({dial_type!r}) failed: {e}")
            return []
