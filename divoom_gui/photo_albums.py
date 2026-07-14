# gui/photo_albums.py

import logging

from divoom_lib.cloud import CloudClient

logger = logging.getLogger("divoom_gui")


class PhotoAlbumsMixin:
    """Mixin for browsing the photo albums ("clocks") configured for the
    active device (Photo/GetAlbumList — see divoom_lib/cloud.py). Playing an
    album is a separate, LAN-only device-touching call, on
    LightingApi.play_album — forwarded from gui_api.py like every other
    device action.
    """

    def get_photo_albums(self) -> list[dict]:
        try:
            return CloudClient().get_photo_albums()
        except Exception as e:
            logger.error(f"get_photo_albums failed: {e}")
            return []
