import pytest
from unittest.mock import AsyncMock, MagicMock
from divoom_lib.display.vjeffect_channel import VJEffectChannel
from divoom_lib.divoom import Divoom as DivoomBase
from divoom_lib.models import VJEffectType

@pytest.fixture
def mock_divoom_instance():
    """Fixture for a mock DivoomBase instance with number2HexString method."""
    mock = AsyncMock(spec=DivoomBase)
    mock.send_command = AsyncMock()
    mock.number2HexString = MagicMock(side_effect=lambda x: f"{x:02x}")
    return mock

@pytest.mark.asyncio
async def test_vjeffect_channel_init_defaults(mock_divoom_instance):
    """Test VJEffectChannel initialization with default options."""
    channel = VJEffectChannel(mock_divoom_instance)
    
    assert channel._divoom_instance == mock_divoom_instance
    assert channel._opts["type"] == VJEffectType.Sparkles

@pytest.mark.asyncio
async def test_vjeffect_channel_init_custom_opts(mock_divoom_instance):
    """Test VJEffectChannel initialization with custom options."""
    custom_opts = {
        "type": VJEffectType.Lava
    }
    channel = VJEffectChannel(mock_divoom_instance, opts=custom_opts)
    
    assert channel._opts["type"] == VJEffectType.Lava

@pytest.mark.asyncio
async def test_vjeffect_channel_show(mock_divoom_instance):
    """Test the show method calls _update_message."""
    channel = VJEffectChannel(mock_divoom_instance)

    await channel.show()
    mock_divoom_instance.send_command.assert_called_once()

@pytest.mark.asyncio
async def test_vjeffect_channel_update_message(mock_divoom_instance):
    """Test _update_message sends the correct command with converted arguments."""
    channel = VJEffectChannel(mock_divoom_instance, opts={"type": VJEffectType.RainbowSwirl})

    await channel._update_message()

    # _PACKAGE_PREFIX = "4503" -> command_code = 0x45, first arg = 0x03
    # type = VJEffectType.RainbowSwirl (4) -> "04"
    # Combined hex string: "0304"
    # List of bytes: [0x03, 0x04]
    expected_args = [0x03, 0x04]
    mock_divoom_instance.send_command.assert_called_once_with(0x45, expected_args)
    mock_divoom_instance.number2HexString.assert_called_once_with(VJEffectType.RainbowSwirl)

@pytest.mark.asyncio
async def test_vjeffect_channel_type_setter(mock_divoom_instance):
    """Test the type setter updates option."""
    channel = VJEffectChannel(mock_divoom_instance)

    channel.type = VJEffectType.Fire
    assert channel._opts["type"] == VJEffectType.Fire
