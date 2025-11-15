import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from divoom_lib.channels.time import TimeChannel
from divoom_lib.base import DivoomBase
from divoom_lib.constants import TimeDisplayType

@pytest.fixture
def mock_divoom_instance():
    """Fixture for a mock DivoomBase instance with color2HexString method."""
    mock = AsyncMock(spec=DivoomBase)
    mock.send_command = AsyncMock()
    mock.color2HexString = MagicMock(side_effect=lambda x: x.replace("#", ""))
    return mock

@pytest.fixture(autouse=True)
def patch_asyncio_create_task():
    """Patch asyncio.create_task to allow awaiting the created task."""
    with patch('asyncio.create_task', new_callable=AsyncMock) as mock_create_task:
        # Make the mock return an awaitable that immediately runs the coroutine
        mock_create_task.side_effect = lambda coro: coro
        yield mock_create_task

@pytest.mark.asyncio
async def test_time_channel_init_defaults(mock_divoom_instance, patch_asyncio_create_task):
    """Test TimeChannel initialization with default options."""
    channel = TimeChannel(mock_divoom_instance)
    
    assert channel._divoom_instance == mock_divoom_instance
    assert channel._opts["type"] == TimeDisplayType.FullScreen
    assert channel._opts["showTime"] is True
    assert channel._opts["showWeather"] is False
    assert channel._opts["showTemp"] is False
    assert channel._opts["showCalendar"] is False
    assert channel._opts["color"] == "FFFFFF"
    patch_asyncio_create_task.assert_called_once() # Called by __init__
    mock_divoom_instance.send_command.assert_called_once() # Called by _update_message

@pytest.mark.asyncio
async def test_time_channel_init_custom_opts(mock_divoom_instance, patch_asyncio_create_task):
    """Test TimeChannel initialization with custom options."""
    custom_opts = {
        "type": TimeDisplayType.Rainbow,
        "showTime": False,
        "showWeather": True,
        "showTemp": True,
        "showCalendar": True,
        "color": "00FF00"
    }
    channel = TimeChannel(mock_divoom_instance, opts=custom_opts)
    
    assert channel._opts["type"] == TimeDisplayType.Rainbow
    assert channel._opts["showTime"] is False
    assert channel._opts["showWeather"] is True
    assert channel._opts["showTemp"] is True
    assert channel._opts["showCalendar"] is True
    assert channel._opts["color"] == "00FF00"
    patch_asyncio_create_task.assert_called_once() # Called by __init__
    mock_divoom_instance.send_command.assert_called_once() # Called by _update_message

@pytest.mark.asyncio
async def test_time_channel_show(mock_divoom_instance, patch_asyncio_create_task):
    """Test the show method calls _update_message."""
    channel = TimeChannel(mock_divoom_instance)
    mock_divoom_instance.send_command.reset_mock() # Clear init call
    patch_asyncio_create_task.reset_mock()

    await channel.show()
    patch_asyncio_create_task.assert_called_once()
    mock_divoom_instance.send_command.assert_called_once()

@pytest.mark.asyncio
async def test_time_channel_update_message(mock_divoom_instance, patch_asyncio_create_task):
    """Test _update_message sends the correct command with converted arguments."""
    channel = TimeChannel(mock_divoom_instance, opts={
        "type": TimeDisplayType.WithBox,
        "showTime": True,
        "showWeather": False,
        "showTemp": True,
        "showCalendar": False,
        "color": "#FF00FF"
    })
    mock_divoom_instance.send_command.reset_mock() # Clear init call
    patch_asyncio_create_task.reset_mock()

    await channel._update_message()

    # _PACKAGE_PREFIX = "450001" -> command_code = 0x45, first two args = 0x00, 0x01
    # type = TimeDisplayType.WithBox (2)
    # showTime = True -> 1
    # showWeather = False -> 0
    # showTemp = True -> 1
    # showCalendar = False -> 0
    # color = "#FF00FF" -> FF00FF (bytes.fromhex) -> [0xFF, 0x00, 0xFF]
    # Expected args: [0x00, 0x01, 0x02, 0x01, 0x00, 0x01, 0x00, 0xFF, 0x00, 0xFF]
    expected_args = [0x00, 0x01, TimeDisplayType.WithBox, 1, 0, 1, 0, 0xFF, 0x00, 0xFF]
    mock_divoom_instance.send_command.assert_called_once_with(0x45, expected_args)
    mock_divoom_instance.color2HexString.assert_called_once_with("#FF00FF")

@pytest.mark.asyncio
async def test_time_channel_type_setter(mock_divoom_instance, patch_asyncio_create_task):
    """Test the type setter updates option and calls _update_message."""
    channel = TimeChannel(mock_divoom_instance)
    mock_divoom_instance.send_command.reset_mock() # Clear init call
    patch_asyncio_create_task.reset_mock()

    channel.type = TimeDisplayType.AnalogRound
    assert channel._opts["type"] == TimeDisplayType.AnalogRound
    patch_asyncio_create_task.assert_called_once()
    mock_divoom_instance.send_command.assert_called_once()

@pytest.mark.asyncio
async def test_time_channel_color_setter(mock_divoom_instance, patch_asyncio_create_task):
    """Test the color setter updates option and calls _update_message."""
    channel = TimeChannel(mock_divoom_instance)
    mock_divoom_instance.send_command.reset_mock() # Clear init call
    patch_asyncio_create_task.reset_mock()

    channel.color = "000000"
    assert channel._opts["color"] == "000000"
    patch_asyncio_create_task.assert_called_once()
    mock_divoom_instance.send_command.assert_called_once()

@pytest.mark.asyncio
async def test_time_channel_show_time_setter(mock_divoom_instance, patch_asyncio_create_task):
    """Test the show_time setter updates option and calls _update_message."""
    channel = TimeChannel(mock_divoom_instance)
    mock_divoom_instance.send_command.reset_mock() # Clear init call
    patch_asyncio_create_task.reset_mock()

    channel.show_time = False
    assert channel._opts["showTime"] is False
    patch_asyncio_create_task.assert_called_once()
    mock_divoom_instance.send_command.assert_called_once()

@pytest.mark.asyncio
async def test_time_channel_show_weather_setter(mock_divoom_instance, patch_asyncio_create_task):
    """Test the show_weather setter updates option and calls _update_message."""
    channel = TimeChannel(mock_divoom_instance)
    mock_divoom_instance.send_command.reset_mock() # Clear init call
    patch_asyncio_create_task.reset_mock()

    channel.show_weather = True
    assert channel._opts["showWeather"] is True
    patch_asyncio_create_task.assert_called_once()
    mock_divoom_instance.send_command.assert_called_once()

@pytest.mark.asyncio
async def test_time_channel_show_temp_setter(mock_divoom_instance, patch_asyncio_create_task):
    """Test the show_temp setter updates option and calls _update_message."""
    channel = TimeChannel(mock_divoom_instance)
    mock_divoom_instance.send_command.reset_mock() # Clear init call
    patch_asyncio_create_task.reset_mock()

    channel.show_temp = True
    assert channel._opts["showTemp"] is True
    patch_asyncio_create_task.assert_called_once()
    mock_divoom_instance.send_command.assert_called_once()

@pytest.mark.asyncio
async def test_time_channel_show_calendar_setter(mock_divoom_instance, patch_asyncio_create_task):
    """Test the show_calendar setter updates option and calls _update_message."""
    channel = TimeChannel(mock_divoom_instance)
    mock_divoom_instance.send_command.reset_mock() # Clear init call
    patch_asyncio_create_task.reset_mock()

    channel.show_calendar = True
    assert channel._opts["showCalendar"] is True
    patch_asyncio_create_task.assert_called_once()
    mock_divoom_instance.send_command.assert_called_once()
