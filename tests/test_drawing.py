import pytest
from unittest.mock import AsyncMock, MagicMock
from divoom_lib.divoom import Divoom
from divoom_lib.models import DivoomConfig

@pytest.fixture
def divoom_device():
    config = DivoomConfig(mac="XX:XX:XX:XX:XX:XX")
    device = Divoom(config)
    device.send_command = AsyncMock()
    return device

@pytest.mark.asyncio
async def test_set_light_pic(divoom_device):
    pic_data = [0x01, 0x02, 0x03]
    await divoom_device.drawing.set_light_pic(pic_data)
    divoom_device.send_command.assert_called_once_with("set light pic", pic_data)
