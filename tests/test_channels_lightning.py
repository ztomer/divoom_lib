import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from divoom_lib.channels.lightning import LightningChannel
from divoom_lib.base import DivoomBase
from divoom_lib.constants import LightningType

@pytest.fixture
def mock_divoom_instance():
    """Fixture for a mock DivoomBase instance with conversion methods."""
    mock = AsyncMock(spec=DivoomBase)
    mock.send_command = AsyncMock()
    mock.color2HexString = MagicMock(side_effect=lambda x: x.replace("#", ""))
    mock.number2HexString = MagicMock(side_effect=lambda x: f"{x:02x}")
    mock.boolean2HexString = MagicMock(side_effect=lambda x: "01" if x else "00")
    return mock

@pytest.fixture(autouse=True)
def patch_asyncio_create_task():
    """Patch asyncio.create_task to allow awaiting the created task."""
    with patch('asyncio.create_task', new_callable=AsyncMock) as mock_create_task:
        # Make the mock return an awaitable that immediately runs the coroutine
        mock_create_task.side_effect = lambda coro: coro
        yield mock_create_task

@pytest.mark.asyncio
async def test_lightning_channel_init_defaults(mock_divoom_instance, patch_asyncio_create_task):
    """Test LightningChannel initialization with default options."""
    channel = LightningChannel(mock_divoom_instance)
    
    assert channel._divoom_instance == mock_divoom_instance
    assert channel._opts["type"] == LightningType.PlainColor
    assert channel._opts["brightness"] == 100
    assert channel._opts["power"] is True
    assert channel._opts["color"] == "FFFFFF"
    patch_asyncio_create_task.assert_called_once() # Called by __init__
    mock_divoom_instance.send_command.assert_called_once() # Called by _update_message

@pytest.mark.asyncio
async def test_lightning_channel_init_custom_opts(mock_divoom_instance, patch_asyncio_create_task):
    """Test LightningChannel initialization with custom options."""
    custom_opts = {
        "type": LightningType.Love,
        "brightness": 50,
        "power": False,
        "color": "00FF00"
    }
    channel = LightningChannel(mock_divoom_instance, opts=custom_opts)
    
    assert channel._opts["type"] == LightningType.Love
    assert channel._opts["brightness"] == 50
    assert channel._opts["power"] is False
    assert channel._opts["color"] == "00FF00"
    patch_asyncio_create_task.assert_called_once() # Called by __init__
    mock_divoom_instance.send_command.assert_called_once() # Called by _update_message

@pytest.mark.asyncio
async def test_lightning_channel_show(mock_divoom_instance, patch_asyncio_create_task):
    """Test the show method calls _update_message."""
    channel = LightningChannel(mock_divoom_instance)
    mock_divoom_instance.send_command.reset_mock() # Clear init call
    patch_asyncio_create_task.reset_mock()

    await channel.show()
    patch_asyncio_create_task.assert_called_once()
    mock_divoom_instance.send_command.assert_called_once()

@pytest.mark.asyncio
async def test_lightning_channel_update_message(mock_divoom_instance, patch_asyncio_create_task):
    """Test _update_message sends the correct command with converted arguments."""
    channel = LightningChannel(mock_divoom_instance, opts={"color": "#FF0000", "brightness": 75, "type": LightningType.Plants, "power": True})
    mock_divoom_instance.send_command.reset_mock() # Clear init call
    patch_asyncio_create_task.reset_mock()

    await channel._update_message()

    # Expected arguments based on _PACKAGE_PREFIX, color, brightness, type, power, _PACKAGE_SUFFIX
    # _PACKAGE_PREFIX = "4501" -> command_code = 0x45, first arg = 0x01
    # color = "#FF0000" -> "FF0000"
    # brightness = 75 -> "4b"
    # type = LightningType.Plants (2) -> "02"
    # power = True -> "01"
    # _PACKAGE_SUFFIX = "000000"
    # Combined hex string: "01FF00004b0201000000"
    # List of bytes: [0x01, 0xFF, 0x00, 0x00, 0x4B, 0x02, 0x01, 0x00, 0x00, 0x00]
    expected_args = [0x01, 0xFF, 0x00, 0x00, 0x4B, 0x02, 0x01, 0x00, 0x00, 0x00]
    mock_divoom_instance.send_command.assert_called_once_with(0x45, expected_args)
    mock_divoom_instance.color2HexString.assert_called_once_with("#FF0000")
    mock_divoom_instance.number2HexString.assert_any_call(75)
    mock_divoom_instance.number2HexString.assert_any_call(LightningType.Plants)
    mock_divoom_instance.boolean2HexString.assert_called_once_with(True)

@pytest.mark.asyncio
async def test_lightning_channel_type_setter(mock_divoom_instance, patch_asyncio_create_task):
    """Test the type setter updates option and calls _update_message."""
    channel = LightningChannel(mock_divoom_instance)
    mock_divoom_instance.send_command.reset_mock() # Clear init call
    patch_asyncio_create_task.reset_mock()

    channel.type = LightningType.Sleeping
    assert channel._opts["type"] == LightningType.Sleeping
    patch_asyncio_create_task.assert_called_once()
    mock_divoom_instance.send_command.assert_called_once()

@pytest.mark.asyncio
async def test_lightning_channel_color_setter(mock_divoom_instance, patch_asyncio_create_task):
    """Test the color setter updates option and calls _update_message."""
    channel = LightningChannel(mock_divoom_instance)
    mock_divoom_instance.send_command.reset_mock() # Clear init call
    patch_asyncio_create_task.reset_mock()

    channel.color = "0000FF"
    assert channel._opts["color"] == "0000FF"
    patch_asyncio_create_task.assert_called_once()
    mock_divoom_instance.send_command.assert_called_once()

@pytest.mark.asyncio
async def test_lightning_channel_power_setter(mock_divoom_instance, patch_asyncio_create_task):
    """Test the power setter updates option and calls _update_message."""
    channel = LightningChannel(mock_divoom_instance)
    mock_divoom_instance.send_command.reset_mock() # Clear init call
    patch_asyncio_create_task.reset_mock()

    channel.power = False
    assert channel._opts["power"] is False
    patch_asyncio_create_task.assert_called_once()
    mock_divoom_instance.send_command.assert_called_once()

@pytest.mark.asyncio
async def test_lightning_channel_brightness_setter(mock_divoom_instance, patch_asyncio_create_task):
    """Test the brightness setter updates option and calls _update_message."""
    channel = LightningChannel(mock_divoom_instance)
    mock_divoom_instance.send_command.reset_mock() # Clear init call
    patch_asyncio_create_task.reset_mock()

    channel.brightness = 25
    assert channel._opts["brightness"] == 25
    patch_asyncio_create_task.assert_called_once()
    mock_divoom_instance.send_command.assert_called_once()
