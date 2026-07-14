# gui/aid_sleep.py

import logging

from divoom_lib.cloud import CloudClient

logger = logging.getLogger("divoom_gui")


class AidSleepMixin:
    """Mixin for browsing Divoom's cloud-hosted AidSleep sound library
    (AidSleep/GetAllList — see divoom_lib/cloud.py). Confirmed live working
    2026-07-14 after fixing the RC=3 "no bound device" precondition
    (divoom_auth.ensure_virtual_device). Playing a chosen sound is a
    separate device-touching call, on LightingApi.play_aid_sleep (BLE/SPP
    JSON straight to the device, no cloud round-trip) — forwarded from
    gui_api.py like every other device action.
    """

    def get_aid_sleep_list(self, sleep_type: int) -> list[dict]:
        try:
            return CloudClient().get_aid_sleep_list(sleep_type)
        except Exception as e:
            logger.error(f"get_aid_sleep_list failed: {e}")
            return []
