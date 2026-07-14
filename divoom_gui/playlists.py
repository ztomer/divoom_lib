# gui/playlists.py

import logging

from divoom_lib.cloud import CloudClient

logger = logging.getLogger("divoom_gui")


class PlaylistsMixin:
    """Mixin for browsing the user's cloud-hosted playlists
    (Playlist/GetMyList — see divoom_lib/cloud.py). Confirmed live working
    2026-07-14. Pushing a playlist to the device is a separate
    device-touching call, on LightingApi.push_playlist (needs the daemon
    client, not just cloud auth) — forwarded from gui_api.py like every
    other device action.
    """

    def get_my_playlists(self) -> list[dict]:
        try:
            return CloudClient().get_my_playlists()
        except Exception as e:
            logger.error(f"get_my_playlists failed: {e}")
            return []
