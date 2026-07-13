"""Divoom cloud HTTP client (appin.divoom-gz.com).

Thin Python client mirroring ``divoomd/src/cloud.rs`` + the decompiled APK
(``LoginServer.java`` / ``BaseRequestJson.java``). Provides:

  * guest auth — the RC=10 fix lives in ``divoom_auth._login_guest`` (the server
    now requires ``Type``/``SubType``/``DeviceId``/``devicePassword`` on
    ``User/NewGuest``; we load those from the virtual-device file).
  * clock-face store — ``GetCategoryFileListV2``.
  * weather-city search — ``Weather/SearchCity``.

All network I/O goes through ``divoom_auth._post``; tests mock that single seam.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from divoom_lib import divoom_auth as _auth

BASE_URL = "https://appin.divoom-gz.com"

# GetCategoryFileListV2 "Classify" for the clock-face store. VERIFY against the
# APK — the gallery tab index the app uses for clock faces.
CLOCK_FACE_CLASSIFY = 0
WEATHER_SEARCH_CMD = "Weather/SearchCity"


@dataclass
class CloudFile:
    file_id: str
    name: str
    preview: str
    raw: dict


class CloudClient:
    """Client for the Divoom cloud HTTP API.

    ``creds``/``device_id``/``device_pw`` can be supplied directly (tests) or
    resolved lazily via :meth:`authenticate`.
    """

    def __init__(
        self,
        creds: _auth.DivoomCredentials | None = None,
        device_id: int = 0,
        device_pw: int = 0,
    ) -> None:
        self.creds = creds
        self.device_id = device_id
        self.device_pw = device_pw

    # ── auth ──────────────────────────────────────────────────────────────

    def authenticate(self, force: bool = False) -> _auth.DivoomCredentials:
        """Resolve (cached → email → guest) credentials and device identity."""
        self.creds = _auth.get_credentials(force_refresh=force)
        dev = _auth._load_virtual_device()
        self.device_id = int(dev.get("BluetoothDeviceId", self.device_id))
        self.device_pw = int(dev.get("DevicePassword", self.device_pw))
        return self.creds

    def _ensure_creds(self) -> _auth.DivoomCredentials:
        if self.creds is None:
            self.authenticate()
        assert self.creds is not None
        return self.creds

    # ── clock-face store ──────────────────────────────────────────────────

    def get_category_file_list(
        self,
        classify: int,
        *,
        file_sort: int = 0,
        file_type: int = 5,
        limit: int = 20,
        page: int = 1,
    ) -> list[dict]:
        creds = self._ensure_creds()
        start = (page - 1) * limit + 1
        end = page * limit * 2
        body: dict[str, Any] = {
            "Command": "GetCategoryFileListV2",
            "Token": creds.token,
            "UserId": creds.user_id,
            "DeviceId": self.device_id,
            "Classify": classify,
            "FileSort": file_sort,
            "FileType": file_type,
            "FileSize": 0,
            "Version": 19,
            "StartNum": start,
            "EndNum": end,
            "RefreshIndex": 0,
        }
        if self.device_pw:
            body["DevicePassword"] = self.device_pw
        data = _auth._post("GetCategoryFileListV2", body)
        rc = data.get("ReturnCode", -1)
        if rc != 0:
            raise RuntimeError(
                f"GetCategoryFileListV2 failed: RC={rc} {data.get('ReturnMessage')}"
            )
        return data.get("FileList", data.get("List", []))

    def list_clock_faces(self, limit: int = 20) -> list[dict]:
        """Browse the cloud clock-face store (``CLOCK_FACE_CLASSIFY``)."""
        return self.get_category_file_list(CLOCK_FACE_CLASSIFY, limit=limit)

    # ── weather city search ───────────────────────────────────────────────

    def search_weather_city(self, keyword: str) -> list[dict]:
        creds = self._ensure_creds()
        body: dict[str, Any] = {
            "Command": WEATHER_SEARCH_CMD,
            "Token": creds.token,
            "UserId": creds.user_id,
            "DeviceId": self.device_id,
            "KeyWord": keyword,
        }
        if self.device_pw:
            body["DevicePassword"] = self.device_pw
        data = _auth._post(WEATHER_SEARCH_CMD, body)
        rc = data.get("ReturnCode", -1)
        if rc != 0:
            raise RuntimeError(
                f"Weather/SearchCity failed: RC={rc} {data.get('ReturnMessage')}"
            )
        return data.get("CityList", data.get("List", []))
