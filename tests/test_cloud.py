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


def test_list_clock_faces_uses_clock_classify():
    c = _client()
    with patch.object(divoom_auth, "_post", side_effect=_fake_post) as post:
        c.list_clock_faces(limit=5)
    req = post.call_args_list[-1].args[1]
    assert req["Command"] == "GetCategoryFileListV2"
    assert req["Classify"] == cloud.CLOCK_FACE_CLASSIFY
    assert req["EndNum"] == 10  # limit 5 -> *2


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
    def fake_fail(path, body):
        if path == "GetCategoryFileListV2":
            return {"ReturnCode": 9, "ReturnMessage": "bad"}
        raise AssertionError(path)
    c = _client()
    with patch.object(divoom_auth, "_post", side_effect=fake_fail):
        try:
            c.get_category_file_list(7)
            assert False, "expected RuntimeError"
        except RuntimeError as e:
            assert "RC=9" in str(e)
