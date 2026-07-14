"""Tests for the Divoom cloud HTTP client (divoom_lib.cloud).

Network is mocked at divoom_auth._post; no real requests are made.
"""
from __future__ import annotations

from unittest.mock import patch

from divoom_lib import divoom_auth
from divoom_lib import cloud


VDEV = {
    "BluetoothDeviceId": 600124449,
    "DevicePassword": 1780230545,
    "Type": 9,
    "SubType": 0,
}


def _fake_post(path, body):
    if path == "APP/GetServerUTC":
        return {"UTC": 1700000000}
    if path == "User/NewGuest":
        return {"ReturnCode": 0, "Token": 12345, "UserId": 67890}
    if path == "GetCategoryFileListV2":
        assert body["Command"] == "GetCategoryFileListV2"
        return {
            "ReturnCode": 0,
            "FileList": [
                {"FileId": "1", "FileName": "Neon", "Preview": "u1"},
                {"FileId": "2", "FileName": "Retro", "Preview": "u2"},
            ],
        }
    if path == "Weather/SearchCity":
        assert body["Command"] == "Weather/SearchCity"
        return {"ReturnCode": 0, "CityList": [{"CityId": "NYC", "Name": "New York"}]}
    if path == "Channel/StoreClockGetClassify":
        assert body["Command"] == "Channel/StoreClockGetClassify"
        return {
            "ReturnCode": 0,
            "ClassifyList": [
                {"ClassifyId": 1, "ClassifyName": "Popular"},
                {"ClassifyId": 2, "ClassifyName": "New"},
            ],
        }
    if path == "Channel/StoreClockGetList":
        assert body["Command"] == "Channel/StoreClockGetList"
        return {
            "ReturnCode": 0,
            "ClockList": [
                {"ClockId": 101, "ClockName": "Analog", "ClockType": 0,
                 "ImagePixelId": "px1", "AddFlag": 0},
            ],
        }
    raise AssertionError(f"unexpected path {path}")


def test_guest_login_sends_device_identity():
    """R61: User/NewGuest must carry Type/SubType/DeviceId/devicePassword
    (the missing fields that produced RC=10)."""
    with patch.object(divoom_auth, "_load_virtual_device", return_value=VDEV), \
         patch.object(divoom_auth, "_post", side_effect=_fake_post) as post:
        creds = divoom_auth._login_guest()
    assert creds.token == 12345 and creds.user_id == 67890
    # find the NewGuest call
    guest_calls = [c for c in post.call_args_list if c.args[0] == "User/NewGuest"]
    guest_body = guest_calls[0].args[1]
    assert guest_body["Type"] == 9
    assert guest_body["SubType"] == 0
    assert guest_body["DeviceId"] == 600124449
    assert guest_body["devicePassword"] == 1780230545
    assert guest_body["UTC"] == "1700000000"


def test_guest_login_rc10_raises():
    def fake_rc10(path, body):
        if path == "APP/GetServerUTC":
            return {"UTC": 1700000000}
        if path == "User/NewGuest":
            return {"ReturnCode": 10, "ReturnMessage": "guest disabled"}
        raise AssertionError(path)
    with patch.object(divoom_auth, "_load_virtual_device", return_value=VDEV), \
         patch.object(divoom_auth, "_post", side_effect=fake_rc10):
        try:
            divoom_auth._login_guest()
            assert False, "expected RuntimeError"
        except RuntimeError as e:
            assert "RC=10" in str(e)


def _client():
    c = cloud.CloudClient(
        creds=divoom_auth.DivoomCredentials(token=12345, user_id=67890),
        device_id=VDEV["BluetoothDeviceId"],
        device_pw=VDEV["DevicePassword"],
    )
    return c


def test_category_file_list_shape_and_parse():
    c = _client()
    with patch.object(divoom_auth, "_post", side_effect=_fake_post) as post:
        files = c.get_category_file_list(7, limit=10)
    assert len(files) == 2 and files[0]["FileName"] == "Neon"
    req = post.call_args_list[-1].args[1]
    assert req["Classify"] == 7
    assert req["DeviceId"] == 600124449
    assert req["DevicePassword"] == 1780230545
    assert req["StartNum"] == 1 and req["EndNum"] == 20  # page 1, limit 10 -> *2


def test_get_clock_classify_list_shape():
    c = _client()
    with patch.object(divoom_auth, "_post", side_effect=_fake_post) as post:
        classifies = c.get_clock_classify_list()
    assert classifies == [
        {"ClassifyId": 1, "ClassifyName": "Popular"},
        {"ClassifyId": 2, "ClassifyName": "New"},
    ]
    req = post.call_args_list[-1].args[1]
    assert req["Command"] == cloud.CLOCK_CLASSIFY_CMD


def test_get_clock_list_shape_and_params():
    c = _client()
    with patch.object(divoom_auth, "_post", side_effect=_fake_post) as post:
        clocks = c.get_clock_list(1, limit=10, page=2)
    assert clocks[0]["ClockName"] == "Analog"
    req = post.call_args_list[-1].args[1]
    assert req["Command"] == cloud.CLOCK_LIST_CMD
    assert req["ClassifyId"] == 1
    assert req["Flag"] == 0
    assert req["StartNum"] == 11 and req["EndNum"] == 20  # page 2, limit 10


def test_list_clock_faces_defaults_to_first_classify():
    """Mirrors the app's own default flow (WifiChannelModel.R() in the
    decompiled APK): no classify_id given -> fetch the classify list, use
    its first entry."""
    c = _client()
    with patch.object(divoom_auth, "_post", side_effect=_fake_post) as post:
        clocks = c.list_clock_faces(limit=5)
    assert clocks[0]["ClockName"] == "Analog"
    calls = [c.args[0] for c in post.call_args_list]
    assert calls == [cloud.CLOCK_CLASSIFY_CMD, cloud.CLOCK_LIST_CMD]
    list_req = post.call_args_list[-1].args[1]
    assert list_req["ClassifyId"] == 1  # first classify from the fake response


def test_list_clock_faces_with_explicit_classify_id_skips_classify_call():
    c = _client()
    with patch.object(divoom_auth, "_post", side_effect=_fake_post) as post:
        c.list_clock_faces(classify_id=2, limit=5)
    calls = [c.args[0] for c in post.call_args_list]
    assert calls == [cloud.CLOCK_LIST_CMD]


def test_search_weather_city():
    c = _client()
    with patch.object(divoom_auth, "_post", side_effect=_fake_post) as post:
        cities = c.search_weather_city("New")
    assert cities[0]["Name"] == "New York"
    req = post.call_args_list[-1].args[1]
    assert req["Command"] == "Weather/SearchCity"
    assert req["KeyWord"] == "New"
    assert req["DeviceId"] == 600124449


def test_category_file_list_rc_nonzero_raises():
    # RC 9/10/11 are the "expired token" family (retried, see the tests below) -
    # use a genuinely non-retryable code here to test the hard-failure path.
    def fake_fail(path, body):
        if path == "GetCategoryFileListV2":
            return {"ReturnCode": 5, "ReturnMessage": "bad"}
        raise AssertionError(path)
    c = _client()
    with patch.object(divoom_auth, "_post", side_effect=fake_fail):
        try:
            c.get_category_file_list(7)
            assert False, "expected RuntimeError"
        except RuntimeError as e:
            assert "RC=5" in str(e)


def test_category_file_list_retries_once_on_expired_token():
    """RC 9/10/11 ('token expired') self-heals with one forced credential
    refresh + retry, mirroring divoomd's fetch_gallery/get_category_file_list
    (cloud_category.rs) - this Python client was missing that retry."""
    calls = {"n": 0}

    def fake_expired_then_ok(path, body):
        if path == "APP/GetServerUTC":
            return {"UTC": 1700000000}
        if path == "User/NewGuest":
            return {"ReturnCode": 0, "Token": 99999, "UserId": 67890}
        if path == "GetCategoryFileListV2":
            calls["n"] += 1
            if calls["n"] == 1:
                return {"ReturnCode": 10, "ReturnMessage": "token expired"}
            assert body["Token"] == 99999  # used the refreshed token
            return {"ReturnCode": 0, "FileList": [{"FileId": "1", "FileName": "Neon"}]}
        raise AssertionError(path)

    c = _client()
    with patch.object(divoom_auth, "_load_virtual_device", return_value=VDEV), \
         patch.object(divoom_auth, "_post", side_effect=fake_expired_then_ok):
        files = c.get_category_file_list(7)
    assert calls["n"] == 2
    assert files[0]["FileName"] == "Neon"


def test_search_weather_city_rc_nonzero_raises():
    def fake_fail(path, body):
        if path == "Weather/SearchCity":
            return {"ReturnCode": 5, "ReturnMessage": "bad"}
        raise AssertionError(path)
    c = _client()
    with patch.object(divoom_auth, "_post", side_effect=fake_fail):
        try:
            c.search_weather_city("New")
            assert False, "expected RuntimeError"
        except RuntimeError as e:
            assert "RC=5" in str(e)


def test_ensure_creds_authenticates_lazily_when_none_supplied():
    """A CloudClient built with no creds authenticates on first real call."""
    c = cloud.CloudClient()
    with patch.object(divoom_auth, "_load_virtual_device", return_value=VDEV), \
         patch.object(divoom_auth, "_post", side_effect=_fake_post):
        files = c.get_category_file_list(7)
    assert files[0]["FileName"] == "Neon"
    assert c.creds is not None and c.device_id == VDEV["BluetoothDeviceId"]


def test_no_device_password_omits_field_from_request():
    """device_pw=0 (no bound device) must not send a DevicePassword field."""
    c = cloud.CloudClient(
        creds=divoom_auth.DivoomCredentials(token=12345, user_id=67890),
        device_id=VDEV["BluetoothDeviceId"], device_pw=0)
    with patch.object(divoom_auth, "_post", side_effect=_fake_post) as post:
        c.get_category_file_list(7)
        c.search_weather_city("New")
    for call in post.call_args_list:
        assert "DevicePassword" not in call.args[1]


def test_search_weather_city_retries_once_on_expired_token():
    calls = {"n": 0}

    def fake_expired_then_ok(path, body):
        if path == "APP/GetServerUTC":
            return {"UTC": 1700000000}
        if path == "User/NewGuest":
            return {"ReturnCode": 0, "Token": 99999, "UserId": 67890}
        if path == "Weather/SearchCity":
            calls["n"] += 1
            if calls["n"] == 1:
                return {"ReturnCode": 9, "ReturnMessage": "token expired"}
            assert body["Token"] == 99999
            return {"ReturnCode": 0, "CityList": [{"CityId": "NYC", "Name": "New York"}]}
        raise AssertionError(path)

    c = _client()
    with patch.object(divoom_auth, "_load_virtual_device", return_value=VDEV), \
         patch.object(divoom_auth, "_post", side_effect=fake_expired_then_ok):
        cities = c.search_weather_city("New")
    assert calls["n"] == 2
    assert cities[0]["Name"] == "New York"
