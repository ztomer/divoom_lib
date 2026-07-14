"""Divoom cloud HTTP client (appin.divoom-gz.com).

Thin Python client mirroring ``divoomd/src/cloud.rs`` + the decompiled APK
(``HttpCommand.java`` / ``BaseRequestJson.java`` — see
``references/apk/decompiled_src/sources/com/divoom/Divoom/http/``). Provides:

  * guest auth — the RC=10 fix lives in ``divoom_auth._login_guest`` (the server
    now requires ``Type``/``SubType``/``DeviceId``/``devicePassword`` on
    ``User/NewGuest``; we load those from the virtual-device file).
  * pixel-art gallery browse — ``GetCategoryFileListV2`` (monthly-best etc.).
  * clock-face store — ``Channel/StoreClockGetClassify`` +
    ``Channel/StoreClockGetList`` (a *different* endpoint pair from the
    gallery above — see ``get_clock_classify_list``/``get_clock_list``).
  * weather-city search — ``Weather/SearchCity``.

All network I/O goes through ``divoom_auth._post``; tests mock that single seam.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from divoom_lib import divoom_auth as _auth

BASE_URL = "https://appin.divoom-gz.com"

WEATHER_SEARCH_CMD = "Weather/SearchCity"
CLOCK_CLASSIFY_CMD = "Channel/StoreClockGetClassify"
CLOCK_LIST_CMD = "Channel/StoreClockGetList"


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

    # ── clock-face store (Channel/StoreClockGetClassify + …GetList) ────────
    #
    # Confirmed against the decompiled APK 2026-07-13
    # (references/apk/decompiled_src/sources/com/divoom/Divoom/view/fragment/
    # channelWifi/model/WifiChannelModel.java, method R()): the clock-face
    # store is NOT browsed via GetCategoryFileListV2 (that endpoint is the
    # pixel-art/monthly-best gallery — confirmed by its own callers, all in
    # CloudGalleriaFragment/CloudVerify*/FillGameModel, none clock-related).
    # It's a dedicated two-call flow: fetch the classify (category) list,
    # then fetch clocks for one classify id. The app's own default flow uses
    # Flag=0 and the FIRST classify entry returned. Request/response field
    # names below are taken verbatim from the APK's
    # MyClockStoreClockGet{Classify,List}{Request,Response}.java classes.
    #
    # STILL OPEN: a live round-trip against Channel/StoreClockGetClassify
    # returns RC=12 (HTTP_REQUEST_EMPTY, "request data is null") — reproduced
    # 2026-07-13 with BOTH a real logged-in email account and guest auth (not
    # a token/auth problem; GetCategoryFileListV2 and Weather/SearchCity both
    # succeed with the same credentials in the same session). The decompiled
    # `BaseParams._postSync` — the method that actually builds the generic
    # HTTP POST all non-device-routed commands go through, including this one
    # — is a JADX "Method not decompiled" stub, so the exact wire shape it
    # sends can't be read from source. Every field on the app's own
    # `BaseLoadMoreRequest`/`MyClockStoreClockGetListRequest` classes is
    # already included here; the gap is something outside what those request
    # classes describe (WHY WEATHER/SEARCHCITY WORKS shows it's not literally
    # about the URL having a "/" in it or fields sent minimal, so it's a
    # subtler per-endpoint requirement, e.g. the server-side handler for this
    # specific command may still require an actual bound device — DeviceId=0
    # was used in this test env, which has no real paired device). Code below
    # is correct per the app's request/response CLASSES; end-to-end proof
    # against the real server is unresolved.

    def get_clock_classify_list(self) -> list[dict]:
        """Fetch the clock-face store's category list (``ClassifyId``/``ClassifyName``)."""

        def _body(creds: _auth.DivoomCredentials) -> dict[str, Any]:
            body: dict[str, Any] = {
                "Command": CLOCK_CLASSIFY_CMD,
                "Token": creds.token,
                "UserId": creds.user_id,
                "DeviceId": self.device_id,
                "StartNum": 1,
                "EndNum": 30,
            }
            if self.device_pw:
                body["DevicePassword"] = self.device_pw
            return body

        data = self._post_with_refresh(CLOCK_CLASSIFY_CMD, _body)
        rc = data.get("ReturnCode", -1)
        if rc != 0:
            raise RuntimeError(
                f"{CLOCK_CLASSIFY_CMD} failed: RC={rc} {data.get('ReturnMessage')}"
            )
        return data.get("ClassifyList", [])

    def get_clock_list(
        self, classify_id: int, *, flag: int = 0, limit: int = 30, page: int = 1
    ) -> list[dict]:
        """Fetch clock faces (``ClockId``/``ClockName``/``ImagePixelId``/…) for one classify id."""
        start = (page - 1) * limit + 1
        end = page * limit

        def _body(creds: _auth.DivoomCredentials) -> dict[str, Any]:
            body: dict[str, Any] = {
                "Command": CLOCK_LIST_CMD,
                "Token": creds.token,
                "UserId": creds.user_id,
                "DeviceId": self.device_id,
                "ClassifyId": classify_id,
                "Flag": flag,
                "StartNum": start,
                "EndNum": end,
            }
            if self.device_pw:
                body["DevicePassword"] = self.device_pw
            return body

        data = self._post_with_refresh(CLOCK_LIST_CMD, _body)
        rc = data.get("ReturnCode", -1)
        if rc != 0:
            raise RuntimeError(
                f"{CLOCK_LIST_CMD} failed: RC={rc} {data.get('ReturnMessage')}"
            )
        return data.get("ClockList", [])

    def list_clock_faces(
        self, classify_id: int | None = None, limit: int = 30
    ) -> list[dict]:
        """Browse the cloud clock-face store.

        Mirrors the app's own default flow: with no ``classify_id``, fetch
        the classify list and use its first entry (same as
        ``WifiChannelModel.R()`` in the decompiled APK).
        """
        if classify_id is None:
            classifies = self.get_clock_classify_list()
            if not classifies:
                return []
            classify_id = classifies[0]["ClassifyId"]
        return self.get_clock_list(classify_id, limit=limit)

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
