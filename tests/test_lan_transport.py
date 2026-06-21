"""R53.44: the LAN HTTP transport must not report a device-rejected command as
success. The Divoom local API returns HTTP 200 with {"error_code": N}; N != 0
means the command failed (bad LocalToken, out-of-range value, unsupported on this
model). post() used to return that body verbatim → the daemon reported success
(ACK != success). _validate_lan_response now raises on non-200, non-JSON, or a
non-zero error_code.

These are the FIRST tests for LanTransport (the bug went unnoticed because there
were none).
"""
import sys
from pathlib import Path

import pytest

sys.path.append(str(Path(__file__).parent.parent))

from divoom_lib.lan_transport import LanTransportError, _validate_lan_response


def test_success_error_code_zero_returns_dict():
    out = _validate_lan_response(200, '{"error_code": 0, "SelectIndex": 2}', "Channel/GetIndex")
    assert out == {"error_code": 0, "SelectIndex": 2}


def test_missing_error_code_is_tolerated():
    out = _validate_lan_response(200, '{"SelectIndex": 2}', "Channel/GetIndex")
    assert out == {"SelectIndex": 2}


def test_nonzero_error_code_raises():
    with pytest.raises(LanTransportError) as ei:
        _validate_lan_response(200, '{"error_code": 5}', "Channel/SetBrightness")
    assert "error_code=5" in str(ei.value)


def test_non_200_status_raises():
    with pytest.raises(LanTransportError):
        _validate_lan_response(500, '{"error_code": 0}', "Channel/SetIndex")


def test_non_json_body_raises():
    with pytest.raises(LanTransportError):
        _validate_lan_response(200, "<html>not a divoom device</html>", "Channel/GetIndex")
