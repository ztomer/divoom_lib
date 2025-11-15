import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from divoom_lib.channels.scoreboard import ScoreBoardChannel
from divoom_lib.base import DivoomBase

@pytest.fixture
def mock_divoom_instance():
    """Fixture for a mock DivoomBase instance with _int2hexlittle method."""
    mock = AsyncMock(spec=DivoomBase)
    mock.send_command = AsyncMock()
    # Mock _int2hexlittle to return a 4-char hex string (2 bytes)
    mock._int2hexlittle = MagicMock(side_effect=lambda x: f"{(x & 0xFF):02x}{((x >> 8) & 0xFF):02x}")
    return mock

@pytest.fixture(autouse=True)
def patch_asyncio_create_task():
    """Patch asyncio.create_task to allow awaiting the created task."""
    with patch('asyncio.create_task', new_callable=AsyncMock) as mock_create_task:
        # Make the mock return an awaitable that immediately runs the coroutine
        mock_create_task.side_effect = lambda coro: coro
        yield mock_create_task

@pytest.mark.asyncio
async def test_scoreboard_channel_init_defaults(mock_divoom_instance, patch_asyncio_create_task):
    """Test ScoreBoardChannel initialization with default scores."""
    channel = ScoreBoardChannel(mock_divoom_instance)
    
    assert channel._divoom_instance == mock_divoom_instance
    assert channel._opts["red"] == 0
    assert channel._opts["blue"] == 0
    patch_asyncio_create_task.assert_called_once() # Called by __init__
    mock_divoom_instance.send_command.assert_called_once() # Called by _update_message

@pytest.mark.asyncio
async def test_scoreboard_channel_init_custom_opts(mock_divoom_instance, patch_asyncio_create_task):
    """Test ScoreBoardChannel initialization with custom scores."""
    custom_opts = {
        "red": 10,
        "blue": 5
    }
    channel = ScoreBoardChannel(mock_divoom_instance, opts=custom_opts)
    
    assert channel._opts["red"] == 10
    assert channel._opts["blue"] == 5
    patch_asyncio_create_task.assert_called_once() # Called by __init__
    mock_divoom_instance.send_command.assert_called_once() # Called by _update_message

@pytest.mark.asyncio
async def test_scoreboard_channel_show(mock_divoom_instance, patch_asyncio_create_task):
    """Test the show method calls _update_message."""
    channel = ScoreBoardChannel(mock_divoom_instance)
    mock_divoom_instance.send_command.reset_mock() # Clear init call
    patch_asyncio_create_task.reset_mock()

    await channel.show()
    patch_asyncio_create_task.assert_called_once()
    mock_divoom_instance.send_command.assert_called_once()

@pytest.mark.asyncio
async def test_scoreboard_channel_update_message(mock_divoom_instance, patch_asyncio_create_task):
    """Test _update_message sends the correct command with converted scores."""
    channel = ScoreBoardChannel(mock_divoom_instance, opts={"red": 123, "blue": 45})
    mock_divoom_instance.send_command.reset_mock() # Clear init call
    patch_asyncio_create_task.reset_mock()

    await channel._update_message()

    # _PACKAGE_PREFIX = "450600" -> command_code = 0x45, first two args = 0x06, 0x00
    # red = 123 -> _int2hexlittle(123) -> "7b00" (assuming little-endian 2-byte)
    # blue = 45 -> _int2hexlittle(45) -> "2d00" (assuming little-endian 2-byte)
    # Combined hex string: "06007b002d00"
    # List of bytes: [0x06, 0x00, 0x7B, 0x00, 0x2D, 0x00]
    expected_args = [0x06, 0x00, 0x7B, 0x00, 0x2D, 0x00]
    mock_divoom_instance.send_command.assert_called_once_with(0x45, expected_args)
    mock_divoom_instance._int2hexlittle.assert_any_call(123)
    mock_divoom_instance._int2hexlittle.assert_any_call(45)

@pytest.mark.asyncio
async def test_scoreboard_channel_red_setter(mock_divoom_instance, patch_asyncio_create_task):
    """Test the red setter updates option and calls _update_message, with clamping."""
    channel = ScoreBoardChannel(mock_divoom_instance)
    mock_divoom_instance.send_command.reset_mock() # Clear init call
    patch_asyncio_create_task.reset_mock()

    channel.red = 50
    assert channel._opts["red"] == 50
    patch_asyncio_create_task.assert_called_once()
    mock_divoom_instance.send_command.assert_called_once()
    mock_divoom_instance.send_command.reset_mock()
    patch_asyncio_create_task.reset_mock()

    channel.red = 1000 # Should be clamped to 999
    assert channel._opts["red"] == 999
    patch_asyncio_create_task.assert_called_once()
    mock_divoom_instance.send_command.assert_called_once()
    mock_divoom_instance.send_command.reset_mock()
    patch_asyncio_create_task.reset_mock()

    channel.red = -10 # Should be clamped to 0
    assert channel._opts["red"] == 0
    patch_asyncio_create_task.assert_called_once()
    mock_divoom_instance.send_command.assert_called_once()

@pytest.mark.asyncio
async def test_scoreboard_channel_blue_setter(mock_divoom_instance, patch_asyncio_create_task):
    """Test the blue setter updates option and calls _update_message, with clamping."""
    channel = ScoreBoardChannel(mock_divoom_instance)
    mock_divoom_instance.send_command.reset_mock() # Clear init call
    patch_asyncio_create_task.reset_mock()

    channel.blue = 75
    assert channel._opts["blue"] == 75
    patch_asyncio_create_task.assert_called_once()
    mock_divoom_instance.send_command.assert_called_once()
    mock_divoom_instance.send_command.reset_mock()
    patch_asyncio_create_task.reset_mock()

    channel.blue = 1001 # Should be clamped to 999
    assert channel._opts["blue"] == 999
    patch_asyncio_create_task.assert_called_once()
    mock_divoom_instance.send_command.assert_called_once()
    mock_divoom_instance.send_command.reset_mock()
    patch_asyncio_create_task.reset_mock()

    channel.blue = -5 # Should be clamped to 0
    assert channel._opts["blue"] == 0
    patch_asyncio_create_task.assert_called_once()
    mock_divoom_instance.send_command.assert_called_once()
