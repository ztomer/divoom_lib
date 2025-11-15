import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from divoom_lib.channels.vjeffect import VJEffectChannel
from divoom_lib.base import DivoomBase
from divoom_lib.constants import VJEffectType

@pytest.fixture
def mock_divoom_instance():
    """Fixture for a mock DivoomBase instance with number2HexString method."""
    mock = AsyncMock(spec=DivoomBase)
    mock.send_command = AsyncMock()
    mock.number2HexString = MagicMock(side_effect=lambda x: f"{x:02x}")
    return mock

@pytest.fixture(autouse=True)
def patch_asyncio_create_task():
    """Patch asyncio.create_task to allow awaiting the created task."""
    with patch('asyncio.create_task', new_callable=AsyncMock) as mock_create_task:
        # Make the mock return an awaitable that immediately runs the coroutine
        mock_create_task.side_effect = lambda coro: coro
        yield mock_create_task

@pytest.mark.asyncio
async def test_vjeffect_channel_init_defaults(mock_divoom_instance, patch_asyncio_create_task):
    """Test VJEffectChannel initialization with default options."""
    channel = VJEffectChannel(mock_divoom_instance)
    
    assert channel._divoom_instance == mock_divoom_instance
    assert channel._opts["type"] == VJEffectType.Sparkles
    patch_asyncio_create_task.assert_called_once() # Called by __init__
    mock_divoom_instance.send_command.assert_called_once() # Called by _update_message

@pytest.mark.asyncio
async def test_vjeffect_channel_init_custom_opts(mock_divoom_instance, patch_asyncio_create_task):
    """Test VJEffectChannel initialization with custom options."""
    custom_opts = {
        "type": VJEffectType.Lava
    }
    channel = VJEffectChannel(mock_divoom_instance, opts=custom_opts)
    
    assert channel._opts["type"] == VJEffectType.Lava
    patch_asyncio_create_task.assert_called_once() # Called by __init__
    mock_divoom_instance.send_command.assert_called_once() # Called by _update_message

@pytest.mark.asyncio
async def test_vjeffect_channel_show(mock_divoom_instance, patch_asyncio_create_task):
    """Test the show method calls _update_message."""
    channel = VJEffectChannel(mock_divoom_instance)
    mock_divoom_instance.send_command.reset_mock() # Clear init call
    patch_asyncio_create_task.reset_mock()

    await channel.show()
    patch_asyncio_create_task.assert_called_once()
    mock_divoom_instance.send_command.assert_called_once()

@pytest.mark.asyncio
async def test_vjeffect_channel_update_message(mock_divoom_instance, patch_asyncio_create_task):
    """Test _update_message sends the correct command with converted arguments."""
    channel = VJEffectChannel(mock_divoom_instance, opts={"type": VJEffectType.RainbowSwirl})
    mock_divoom_instance.send_command.reset_mock() # Clear init call
    patch_asyncio_create_task.reset_mock()

    await channel._update_message()

    # _PACKAGE_PREFIX = "4503" -> command_code = 0x45, first arg = 0x03
    # type = VJEffectType.RainbowSwirl (4) -> "04"
    # Combined hex string: "0304"
    # List of bytes: [0x03, 0x04]
    expected_args = [0x03, 0x04]
    mock_divoom_instance.send_command.assert_called_once_with(0x45, expected_args)
    mock_divoom_instance.number2HexString.assert_called_once_with(VJEffectType.RainbowSwirl)

@pytest.mark.asyncio
async def test_vjeffect_channel_type_setter(mock_divoom_instance, patch_asyncio_create_task):
    """Test the type setter updates option and calls _update_message."""
    channel = VJEffectChannel(mock_divoom_instance)
    mock_divoom_instance.send_command.reset_mock() # Clear init call
    patch_asyncio_create_task.reset_mock()

    channel.type = VJEffectType.Fire
    assert channel._opts["type"] == VJEffectType.Fire
    patch_asyncio_create_task.assert_called_once()
    mock_divoom_instance.send_command.assert_called_once()
