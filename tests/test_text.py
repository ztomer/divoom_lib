import pytest
from unittest.mock import AsyncMock, MagicMock
from divoom_lib.divoom import Divoom
from divoom_lib.models import DivoomConfig, LPWA_CONTROL_CONTENT

@pytest.fixture
def divoom_device():
    config = DivoomConfig(mac="XX:XX:XX:XX:XX:XX")
    device = Divoom(config)
    device.send_command = AsyncMock()
    return device

@pytest.mark.asyncio
async def test_set_text_content(divoom_device):
    text = "Hello"
    text_box_id = 1
    await divoom_device.text.set_text_content(text, text_box_id=text_box_id)
    
    content_bytes = text.encode('utf-8')
    expected_payload = [LPWA_CONTROL_CONTENT] + list(len(content_bytes).to_bytes(2, byteorder='little')) + list(content_bytes) + [text_box_id]
    
    divoom_device.send_command.assert_called_once_with("set light phone word attr", expected_payload)
