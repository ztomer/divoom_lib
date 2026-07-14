"""Divoom cloud HTTP client (appin.divoom-gz.com).

Thin Python client mirroring ``divoomd/src/cloud.rs`` + the decompiled APK
(``HttpCommand.java`` / ``BaseRequestJson.java`` — see
``references/apk/decompiled_src/sources/com/divoom/Divoom/http/``). Provides:

  * guest auth — the RC=10 fix lives in ``divoom_auth._login_guest`` (the server
    now requires ``Type``/``SubType``/``DeviceId``/``devicePassword`` on
    ``User/NewGuest``; we load those from the virtual-device file).
  * pixel-art gallery browse — ``GetCategoryFileListV2`` (monthly-best etc.).
  * clock-face store — ``Channel/GetDialType`` + ``Channel/GetDialList``,
    Divoom's public unauthenticated developer API (a *different* endpoint
    pair from the phone-app-internal gallery above — see
    ``get_dial_types``/``get_dial_list``).
  * weather-city search — ``Weather/SearchCity``.

All network I/O goes through ``divoom_auth._post``; tests mock that single seam.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from divoom_lib import divoom_auth as _auth

BASE_URL = "https://appin.divoom-gz.com"

WEATHER_SEARCH_CMD = "Weather/SearchCity"
DIAL_TYPE_CMD = "Channel/GetDialType"
DIAL_LIST_CMD = "Channel/GetDialList"


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

    # RC 9/10/11 are the server's "token expired/invalid" family (same codes
    # gallery_sync.py's fetch_gallery already retries on) — one retry with a
    # forced credential refresh self-heals a stale token instead of hard-failing.
    _EXPIRED_RCS = (9, 10, 11)

    def _post_with_refresh(self, cmd: str, body_fn) -> dict:
        creds = self._ensure_creds()
        data = _auth._post(cmd, body_fn(creds))
        rc = data.get("ReturnCode", -1)
        if rc in self._EXPIRED_RCS:
            creds = self.authenticate(force=True)
            data = _auth._post(cmd, body_fn(creds))
        return data

    def get_category_file_list(
        self,
        classify: int,
        *,
        file_sort: int = 0,
        file_type: int = 5,
        limit: int = 20,
        page: int = 1,
    ) -> list[dict]:
        start = (page - 1) * limit + 1
        end = page * limit * 2

        def _body(creds: _auth.DivoomCredentials) -> dict[str, Any]:
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
            return body

        data = self._post_with_refresh("GetCategoryFileListV2", _body)
        rc = data.get("ReturnCode", -1)
        if rc != 0:
            raise RuntimeError(
                f"GetCategoryFileListV2 failed: RC={rc} {data.get('ReturnMessage')}"
            )
        return data.get("FileList", data.get("List", []))

    # ── clock-face store (Channel/GetDialType + Channel/GetDialList) ───────
    #
    # This is Divoom's PUBLIC developer API (doc.divoom-gz.com/web/#/12?
    # page_id=190), not part of HttpCommand.java's phone-app-internal command
    # catalog — confirmed live 2026-07-13 (real ClockId/Name data returned)
    # and requires NO auth at all (no Token/UserId/DeviceId in the request).
    # Field names/URL paths confirmed against the independent r12f/divoom
    # Rust crate (github.com/r12f/divoom, MIT), which documents the same
    # official doc.divoom-gz.com page as its source.
    #
    # A phone-app-internal alternative, Channel/StoreClockGetClassify +
    # Channel/StoreClockGetList (per HttpCommand.java + WifiChannelModel.java
    # in the decompiled APK), was tried first and abandoned: it returns RC=12
    # (HTTP_REQUEST_EMPTY) against the real server for a reason the
    # decompiled source can't confirm (BaseParams._postSync, the method that
    # builds the actual POST, is a JADX "not decompiled" stub; OkHttpUtils.
    # postSyncInternal — which _postSync calls into — IS fully decompiled and
    # confirms no hidden headers/signing beyond `Connection: close`, so the
    # gap is specifically in that endpoint's expected body/account state, not
    # the transport). Not worth chasing further now that a confirmed-working
    # public alternative exists.
    #
    # Applying a selected ClockId to a device: ``divoom_lib.display.
    # show_clock(clock=clock_id)`` already routes large ids through
    # ``lan.set_clock()`` (``Channel/SetClockSelectId`` posted directly to
    # the device's own LAN IP) when the device has LAN connectivity — no new
    # device-apply plumbing needed.

    def get_dial_types(self) -> list[str]:
        """Fetch the clock-face store's category names (``Channel/GetDialType``)."""
        data = _auth._post(DIAL_TYPE_CMD, {})
        rc = data.get("ReturnCode", -1)
        if rc != 0:
            raise RuntimeError(
                f"{DIAL_TYPE_CMD} failed: RC={rc} {data.get('ReturnMessage')}"
            )
        return data.get("DialTypeList", [])

    def get_dial_list(self, dial_type: str, page: int = 1) -> list[dict]:
        """Fetch clock faces (``ClockId``/``Name``) for one category name."""
        data = _auth._post(DIAL_LIST_CMD, {"DialType": dial_type, "Page": page})
        rc = data.get("ReturnCode", -1)
        if rc != 0:
            raise RuntimeError(
                f"{DIAL_LIST_CMD} failed: RC={rc} {data.get('ReturnMessage')}"
            )
        return data.get("DialList", [])

    def list_clock_faces(
        self, dial_type: str | None = None, page: int = 1
    ) -> list[dict]:
        """Browse the cloud clock-face store. With no ``dial_type``, use the
        first category from :meth:`get_dial_types`."""
        if dial_type is None:
            types = self.get_dial_types()
            if not types:
                return []
            dial_type = types[0]
        return self.get_dial_list(dial_type, page=page)

    # ── weather city search ───────────────────────────────────────────────

    def search_weather_city(self, keyword: str) -> list[dict]:
        def _body(creds: _auth.DivoomCredentials) -> dict[str, Any]:
            body: dict[str, Any] = {
                "Command": WEATHER_SEARCH_CMD,
                "Token": creds.token,
                "UserId": creds.user_id,
                "DeviceId": self.device_id,
                "KeyWord": keyword,
            }
            if self.device_pw:
                body["DevicePassword"] = self.device_pw
            return body

        data = self._post_with_refresh(WEATHER_SEARCH_CMD, _body)
        rc = data.get("ReturnCode", -1)
        if rc != 0:
            raise RuntimeError(
                f"Weather/SearchCity failed: RC={rc} {data.get('ReturnMessage')}"
            )
        return data.get("CityList", data.get("List", []))
