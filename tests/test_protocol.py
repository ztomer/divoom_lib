import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from divoom_lib.protocol import DivoomProtocol
from divoom_lib import models
import logging

@pytest.fixture
def mock_protocol_instance():
    """Fixture for a mock DivoomProtocol instance."""
    with patch('divoom_lib.protocol.BleakClient', new_callable=AsyncMock) as mock_bleak_client:
        protocol = DivoomProtocol(mac="AA:BB:CC:DD:EE:FF", device_name="MockDevice")
        protocol.client = mock_bleak_client
        protocol.client.is_connected = True
        protocol.WRITE_CHARACTERISTIC_UUID = "mock_write_char_uuid"
        protocol.NOTIFY_CHARACTERISTIC_UUID = "mock_notify_char_uuid"
        protocol.READ_CHARACTERISTIC_UUID = "mock_read_char_uuid"
        protocol.use_ios_le_protocol = False
        protocol.escapePayload = False
        yield protocol

@pytest.mark.asyncio
async def test_protocol_init(mock_protocol_instance):
    """Test DivoomProtocol initialization."""
    protocol = mock_protocol_instance
    assert protocol.mac == "AA:BB:CC:DD:EE:FF"
    assert protocol.device_name == "MockDevice"
    assert protocol.use_ios_le_protocol is False
    assert protocol.escapePayload is False
    assert protocol.notification_queue.empty()
    assert protocol._expected_response_command is None
    assert protocol.message_buf == []

@pytest.mark.asyncio
async def test_make_message(mock_protocol_instance):
    """Test _make_message for basic protocol."""
    protocol = mock_protocol_instance
    payload = [0x45, 0x01, 0xFF, 0x00, 0x00, 0x64, 0x00, 0x01]
    message = protocol._make_message(payload)
    # Expected: 01 (start) + 0a00 (len) + 4501ff0000640001 (payload) + 4a01 (crc) + 02 (end)
    assert message == "010a004501ff00006400014a0102"

@pytest.mark.asyncio
async def test_make_message_with_escaping(mock_protocol_instance):
    """Test _make_message with payload escaping."""
    protocol = mock_protocol_instance
    protocol.escapePayload = True
    payload = [0x01, 0x02, 0x03, 0x04]
    message = protocol._make_message(payload)
    # Expected: 01 (start) + 0900 (len) + 03040305030604 (escaped payload) + 1c00 (crc) + 02 (end)
    assert message == "010900030403050306041c0002"

@pytest.mark.asyncio
async def test_make_message_ios_le(mock_protocol_instance):
    """Test _make_message_ios_le for iOS LE protocol."""
    protocol = mock_protocol_instance
    payload = [0x45, 0x01, 0xFF, 0x00, 0x00, 0x64, 0x00, 0x01]
    message = protocol._make_message_ios_le(payload)
    # Expected: feefaa55 (header) + 1000 (len) + 45 (cmd) + 00000000 (packet num) + 4501ff0000640001 (payload) + 5a01 (crc)
    assert message == "feefaa55100045000000004501ff00006400015a01"

@pytest.mark.asyncio
async def test_escape_payload(mock_protocol_instance):
    """Test _escape_payload."""
    protocol = mock_protocol_instance
    payload = [0x01, 0x02, 0x03, 0x04]
    escaped_payload = protocol._escape_payload(payload)
    assert escaped_payload == [0x03, 0x04, 0x03, 0x05, 0x03, 0x06, 0x04]

@pytest.mark.asyncio
async def test_get_crc(mock_protocol_instance):
    """Test _getCRC."""
    protocol = mock_protocol_instance
    payload = [0x0a, 0x00, 0x45, 0x01, 0xff, 0x00, 0x00, 0x64, 0x00, 0x01]
    crc = protocol._getCRC(payload)
    assert crc == "4a01"

@pytest.mark.asyncio
async def test_notification_handler_basic(mock_protocol_instance):
    """Test notification_handler for basic protocol."""
    protocol = mock_protocol_instance
    protocol.use_ios_le_protocol = False
    # 0108000446550100a80002
    data = bytearray.fromhex("0108000446550100a80002")
    protocol.notification_handler(12, data)
    assert not protocol.notification_queue.empty()
    response = await protocol.notification_queue.get()
    assert response['command_id'] == 0x46
    assert response['payload'] == bytearray.fromhex("0100")

@pytest.mark.asyncio
async def test_notification_handler_ios_le(mock_protocol_instance):
    """Test notification_handler for iOS LE protocol."""
    protocol = mock_protocol_instance
    protocol.use_ios_le_protocol = True
    protocol._expected_response_command = 0x46
    data = bytearray.fromhex("feefaa550e00460000000001005901")
    protocol.notification_handler(12, data)
    assert not protocol.notification_queue.empty()
    response = await protocol.notification_queue.get()
    assert response['command_id'] == 0x46
    assert response['payload'] == bytearray.fromhex("0100")

@pytest.mark.asyncio
async def test_wait_for_response(mock_protocol_instance):
    """Test wait_for_response."""
    protocol = mock_protocol_instance
    protocol.notification_queue.put_nowait({'command_id': 0x46, 'payload': b'test'})
    response = await protocol.wait_for_response(0x46, timeout=1)
    assert response == b'test'

@pytest.mark.asyncio
async def test_wait_for_response_timeout(mock_protocol_instance):
    """Test wait_for_response timeout."""
    protocol = mock_protocol_instance
    response = await protocol.wait_for_response(0x46, timeout=0.1)
    assert response is None

@pytest.mark.asyncio
async def test_send_command(mock_protocol_instance):
    """Test send_command."""
    protocol = mock_protocol_instance
    with patch.object(protocol, 'send_payload', new_callable=AsyncMock) as mock_send_payload:
        await protocol.send_command("set volume", [10])
        mock_send_payload.assert_called_once_with([models.COMMANDS["set volume"], 10], write_with_response=False)

@pytest.mark.asyncio
async def test_send_payload_basic(mock_protocol_instance):
    """Test send_payload for basic protocol."""
    protocol = mock_protocol_instance
    protocol.use_ios_le_protocol = False
    payload = [0x45, 0x01]
    await protocol.send_payload(payload)
    protocol.client.write_gatt_char.assert_called_once_with(
        "mock_write_char_uuid",
        bytes.fromhex("01040045014a0002"),
        response=False
    )

@pytest.mark.asyncio
async def test_send_payload_ios_le(mock_protocol_instance):
    """Test send_payload for iOS LE protocol."""
    protocol = mock_protocol_instance
    protocol.use_ios_le_protocol = True
    payload = [0x45, 0x01]
    await protocol.send_payload(payload)
    protocol.client.write_gatt_char.assert_called_once_with(
        "mock_write_char_uuid",
        bytes.fromhex("feefaa550a0045000000004501f400"),
        response=False
    )

@pytest.mark.asyncio
async def test_connect(mock_protocol_instance):
    """Test connect method."""
    protocol = mock_protocol_instance
    protocol.client.is_connected = False
    await protocol.connect()
    protocol.client.connect.assert_called_once()
    protocol.client.start_notify.assert_called_once_with(
        "mock_notify_char_uuid",
        protocol.notification_handler
    )

@pytest.mark.asyncio
async def test_disconnect(mock_protocol_instance):
    """Test disconnect method."""
    protocol = mock_protocol_instance
    await protocol.disconnect()
    protocol.client.disconnect.assert_called_once()

@pytest.mark.asyncio
async def test_send_command_and_wait_for_response(mock_protocol_instance):
    """Test send_command_and_wait_for_response."""
    protocol = mock_protocol_instance
    with patch.object(protocol, 'send_command', new_callable=AsyncMock) as mock_send_command, \
         patch.object(protocol, 'wait_for_response', new_callable=AsyncMock) as mock_wait_for_response:
        mock_wait_for_response.return_value = b'test'
        response = await protocol.send_command_and_wait_for_response("set volume", [10])
        mock_send_command.assert_called_once_with("set volume", [10], write_with_response=True)
        mock_wait_for_response.assert_called_once_with(models.COMMANDS["set volume"], 10)
        assert response == b'test'

@pytest.mark.asyncio
async def test_send_payload_error(mock_protocol_instance):
    """Test error handling in send_payload."""
    protocol = mock_protocol_instance
    protocol.client.write_gatt_char.side_effect = Exception("Test error")
    result = await protocol.send_payload([0x01])
    assert result is False

@pytest.mark.asyncio
async def test_framing_context(mock_protocol_instance):
    """Test _framing_context correctly sets and restores framing preferences."""
    protocol = mock_protocol_instance
    original_use_ios = protocol.use_ios_le_protocol
    original_escape = protocol.escapePayload

    async with protocol._framing_context(use_ios=True, escape=True):
        assert protocol.use_ios_le_protocol is True
        assert protocol.escapePayload is True

    assert protocol.use_ios_le_protocol == original_use_ios
    assert protocol.escapePayload == original_escape
