import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from divoom_lib.base import DivoomBase
from divoom_lib import constants
import logging
from bleak import BleakClient
from bleak.exc import BleakError

# Mock BleakClient for DivoomBase
@pytest.fixture
def mock_bleak_client():
    client = AsyncMock(spec=BleakClient)
    client.is_connected = False
    client.address = "AA:BB:CC:DD:EE:FF"
    return client

@pytest.fixture
def divoom_base_instance(mock_bleak_client):
    # Patch BleakClient during DivoomBase instantiation
    with patch('divoom_lib.base.BleakClient', return_value=mock_bleak_client):
        instance = DivoomBase(
            mac="AA:BB:CC:DD:EE:FF",
            logger=logging.getLogger(__name__),
            write_characteristic_uuid="write_uuid",
            notify_characteristic_uuid="notify_uuid",
            read_characteristic_uuid="read_uuid",
            client=mock_bleak_client # Pass the mocked client
        )
        yield instance

@pytest.mark.asyncio
async def test_divoom_base_init(divoom_base_instance, mock_bleak_client):
    """Test DivoomBase initialization."""
    base = divoom_base_instance
    assert base.mac == "AA:BB:CC:DD:EE:FF"
    assert base.device_name is None
    assert base.WRITE_CHARACTERISTIC_UUID == "write_uuid"
    assert base.NOTIFY_CHARACTERISTIC_UUID == "notify_uuid"
    assert base.READ_CHARACTERISTIC_UUID == "read_uuid"
    assert base.client == mock_bleak_client
    assert not base.use_ios_le_protocol
    assert isinstance(base.notification_queue, asyncio.Queue)
    assert base._expected_response_command is None
    assert base.message_buf == []

@pytest.mark.asyncio
async def test_is_connected_property(divoom_base_instance, mock_bleak_client):
    """Test the is_connected property."""
    base = divoom_base_instance
    mock_bleak_client.is_connected = True
    assert base.is_connected is True
    mock_bleak_client.is_connected = False
    assert base.is_connected is False

@pytest.mark.asyncio
async def test_connect_success(divoom_base_instance, mock_bleak_client):
    """Test successful connection."""
    base = divoom_base_instance
    mock_bleak_client.connect.return_value = None
    mock_bleak_client.is_connected = True # Simulate successful connection
    
    await base.connect()
    mock_bleak_client.connect.assert_called_once()
    mock_bleak_client.start_notify.assert_called_once_with(base.NOTIFY_CHARACTERISTIC_UUID, base.notification_handler)
    assert base.is_connected

@pytest.mark.asyncio
async def test_connect_already_connected(divoom_base_instance, mock_bleak_client):
    """Test connect when already connected."""
    base = divoom_base_instance
    mock_bleak_client.is_connected = True
    
    await base.connect()
    mock_bleak_client.connect.assert_not_called()
    mock_bleak_client.start_notify.assert_not_called()

@pytest.mark.asyncio
async def test_connect_no_mac_address(divoom_base_instance):
    """Test connect with no MAC address."""
    base = divoom_base_instance
    base.mac = None
    with pytest.raises(ValueError, match="No MAC address provided or discovered. Cannot connect."):
        await base.connect()

@pytest.mark.asyncio
async def test_connect_missing_uuids(divoom_base_instance):
    """Test connect with missing characteristic UUIDs."""
    base = divoom_base_instance
    base.WRITE_CHARACTERISTIC_UUID = None
    with pytest.raises(ValueError, match="Characteristic UUIDs not fully set. Cannot connect."):
        await base.connect()

@pytest.mark.asyncio
async def test_connect_bleak_error(divoom_base_instance, mock_bleak_client):
    """Test connect with BleakError."""
    base = divoom_base_instance
    mock_bleak_client.connect.side_effect = BleakError("Connection failed")
    with pytest.raises(ConnectionError, match="Failed to connect to AA:BB:CC:DD:EE:FF: Connection failed"):
        await base.connect()

@pytest.mark.asyncio
async def test_disconnect_success(divoom_base_instance, mock_bleak_client):
    """Test successful disconnection."""
    base = divoom_base_instance
    mock_bleak_client.is_connected = True
    mock_bleak_client.disconnect.return_value = None
    
    await base.disconnect()
    mock_bleak_client.disconnect.assert_called_once()
    assert not base.is_connected

@pytest.mark.asyncio
async def test_disconnect_not_connected(divoom_base_instance, mock_bleak_client):
    """Test disconnect when not connected."""
    base = divoom_base_instance
    mock_bleak_client.is_connected = False
    
    await base.disconnect()
    mock_bleak_client.disconnect.assert_not_called()

def test_convert_color(divoom_base_instance):
    """Test color conversion."""
    base = divoom_base_instance
    assert base.convert_color("#FF0000") == [255, 0, 0]
    assert base.convert_color((0, 255, 0)) == [0, 255, 0]
    assert base.convert_color([0, 0, 255]) == [0, 0, 255]
    assert base.convert_color("red") == [255, 0, 0]

@pytest.mark.asyncio
async def test_handle_ios_le_notification_expected_response(divoom_base_instance):
    """Test iOS LE notification handler with an expected response."""
    base = divoom_base_instance
    base.use_ios_le_protocol = True
    base._expected_response_command = 0x01 # Example command ID

    # Mock iOS LE data: Header (4 bytes), Length (2 bytes, little-endian), Cmd ID (1 byte), Packet Num (4 bytes), Data (variable), Checksum (2 bytes)
    # Example: 0x0104000000 (Header) 0x0B00 (Length 11) 0x01 (Cmd ID) 0x00000000 (Packet Num) 0x1234 (Data) 0xXXYY (Checksum)
    # For simplicity, let's construct a valid looking one
    cmd_id = 0x01
    packet_num = 0x00000000
    data_payload = [0x12, 0x34]
    
    # Calculate length and checksum for the mock
    # Length = Cmd ID (1) + Packet Num (4) + Data (2) + Checksum (2) = 9
    # Data length in header is for (Cmd ID + Packet Num + Data + Checksum)
    data_len_val = 1 + 4 + len(data_payload) + 2 # 9
    data_len_bytes = data_len_val.to_bytes(2, 'little')

    checksum_input = list(data_len_bytes) + [cmd_id] + list(packet_num.to_bytes(4, 'little')) + data_payload
    checksum_val = sum(checksum_input)
    checksum_bytes = checksum_val.to_bytes(2, 'little')

    mock_data = bytearray(constants.IOS_LE_HEADER) + bytearray(data_len_bytes) + bytearray([cmd_id]) + bytearray(packet_num.to_bytes(4, 'little')) + bytearray(data_payload) + bytearray(checksum_bytes)

    result = base._handle_ios_le_notification(mock_data)
    assert result is True
    assert not base.notification_queue.empty()
    response = await base.notification_queue.get()
    assert response['command_id'] == cmd_id
    assert response['payload'] == bytearray(data_payload)
    assert base._expected_response_command is None

@pytest.mark.asyncio
async def test_handle_ios_le_notification_generic_ack(divoom_base_instance):
    """Test iOS LE notification handler with a generic ACK response."""
    base = divoom_base_instance
    base.use_ios_le_protocol = True
    base._expected_response_command = 0x45 # A command that expects a generic ACK

    # Mock generic ACK (0x33)
    cmd_id = 0x33
    packet_num = 0x00000000
    data_payload = [] # Generic ACK might have empty payload
    
    data_len_val = 1 + 4 + len(data_payload) + 2 # 7
    data_len_bytes = data_len_val.to_bytes(2, 'little')

    checksum_input = list(data_len_bytes) + [cmd_id] + list(packet_num.to_bytes(4, 'little')) + data_payload
    checksum_val = sum(checksum_input)
    checksum_bytes = checksum_val.to_bytes(2, 'little')

    mock_data = bytearray(constants.IOS_LE_HEADER) + bytearray(data_len_bytes) + bytearray([cmd_id]) + bytearray(packet_num.to_bytes(4, 'little')) + bytearray(data_payload) + bytearray(checksum_bytes)

    # Temporarily add 0x45 to GENERIC_ACK_COMMANDS for this test
    original_generic_acks = constants.GENERIC_ACK_COMMANDS
    constants.GENERIC_ACK_COMMANDS = original_generic_acks + (0x45,)

    try:
        result = base._handle_ios_le_notification(mock_data)
        assert result is True
        assert not base.notification_queue.empty()
        response = await base.notification_queue.get()
        assert response['command_id'] == cmd_id
        assert response['payload'] == bytearray(data_payload)
        assert base._expected_response_command is None # Should clear on generic ACK
    finally:
        constants.GENERIC_ACK_COMMANDS = original_generic_acks # Restore original

@pytest.mark.asyncio
async def test_handle_ios_le_notification_unexpected_response(divoom_base_instance):
    """Test iOS LE notification handler with an unexpected response."""
    base = divoom_base_instance
    base.use_ios_le_protocol = True
    base._expected_response_command = 0x01 # Expecting 0x01

    # Mock iOS LE data for command 0x02 (unexpected)
    cmd_id = 0x02
    packet_num = 0x00000000
    data_payload = [0x56, 0x78]
    
    data_len_val = 1 + 4 + len(data_payload) + 2 # 9
    data_len_bytes = data_len_val.to_bytes(2, 'little')

    checksum_input = list(data_len_bytes) + [cmd_id] + list(packet_num.to_bytes(4, 'little')) + data_payload
    checksum_val = sum(checksum_input)
    checksum_bytes = checksum_val.to_bytes(2, 'little')

    mock_data = bytearray(constants.IOS_LE_HEADER) + bytearray(data_len_bytes) + bytearray([cmd_id]) + bytearray(packet_num.to_bytes(4, 'little')) + bytearray(data_payload) + bytearray(checksum_bytes)

    result = base._handle_ios_le_notification(mock_data)
    assert result is False # Should return False for unexpected
    assert base.notification_queue.empty() # Should not put in queue
    assert base._expected_response_command == 0x01 # Should not clear expectation

@pytest.mark.asyncio
async def test_handle_basic_protocol_notification_single_message(divoom_base_instance):
    """Test basic protocol notification handler with a single valid message."""
    base = divoom_base_instance
    base.use_ios_le_protocol = False
    base._expected_response_command = 0x01

    # Mock basic protocol data: START (1), LEN (2), CMD (1), PAYLOAD (variable), CHECKSUM (2), END (1)
    # Example: 0x01 0x0500 (len 5) 0x01 (cmd) 0x1234 (payload) 0xXXYY (checksum) 0x02
    cmd_id = 0x01
    payload_data = [0x12, 0x34]
    
    # Length = Cmd (1) + Payload (2) + Checksum (2) = 5
    length_val = 1 + len(payload_data) + 2
    length_bytes = length_val.to_bytes(2, 'little')

    checksum_input = list(length_bytes) + [cmd_id] + payload_data
    checksum_val = sum(checksum_input)
    checksum_bytes = checksum_val.to_bytes(2, 'little')

    mock_data = bytearray([constants.MESSAGE_START_BYTE]) + bytearray(length_bytes) + bytearray([cmd_id]) + bytearray(payload_data) + bytearray(checksum_bytes) + bytearray([constants.MESSAGE_END_BYTE])

    result = base._handle_basic_protocol_notification(mock_data)
    assert result is True
    assert not base.notification_queue.empty()
    response = await base.notification_queue.get()
    assert response['command_id'] == cmd_id
    assert response['payload'] == bytearray(payload_data)
    # _expected_response_command is cleared by wait_for_response, not by handler

@pytest.mark.asyncio
async def test_handle_basic_protocol_notification_multiple_messages(divoom_base_instance):
    """Test basic protocol notification handler with multiple messages in one data chunk."""
    base = divoom_base_instance
    base.use_ios_le_protocol = False
    base._expected_response_command = 0x01

    # Message 1
    cmd_id_1 = 0x01
    payload_data_1 = [0x11, 0x22]
    length_val_1 = 1 + len(payload_data_1) + 2
    length_bytes_1 = length_val_1.to_bytes(2, 'little')
    checksum_input_1 = list(length_bytes_1) + [cmd_id_1] + payload_data_1
    checksum_val_1 = sum(checksum_input_1)
    checksum_bytes_1 = checksum_val_1.to_bytes(2, 'little')
    message_1 = bytearray([constants.MESSAGE_START_BYTE]) + bytearray(length_bytes_1) + bytearray([cmd_id_1]) + bytearray(payload_data_1) + bytearray(checksum_bytes_1) + bytearray([constants.MESSAGE_END_BYTE])

    # Message 2
    cmd_id_2 = 0x02
    payload_data_2 = [0x33, 0x44, 0x55]
    length_val_2 = 1 + len(payload_data_2) + 2
    length_bytes_2 = length_val_2.to_bytes(2, 'little')
    checksum_input_2 = list(length_bytes_2) + [cmd_id_2] + payload_data_2
    checksum_val_2 = sum(checksum_input_2)
    checksum_bytes_2 = checksum_val_2.to_bytes(2, 'little')
    message_2 = bytearray([constants.MESSAGE_START_BYTE]) + bytearray(length_bytes_2) + bytearray([cmd_id_2]) + bytearray(payload_data_2) + bytearray(checksum_bytes_2) + bytearray([constants.MESSAGE_END_BYTE])

    mock_data = message_1 + message_2

    result = base._handle_basic_protocol_notification(mock_data)
    assert result is True
    assert not base.notification_queue.empty()

    response1 = await base.notification_queue.get()
    assert response1['command_id'] == cmd_id_1
    assert response1['payload'] == bytearray(payload_data_1)

    response2 = await base.notification_queue.get()
    assert response2['command_id'] == cmd_id_2
    assert response2['payload'] == bytearray(payload_data_2)
    assert base.notification_queue.empty()

@pytest.mark.asyncio
async def test_handle_basic_protocol_notification_junk_data_then_message(divoom_base_instance):
    """Test basic protocol notification handler with junk data before a valid message."""
    base = divoom_base_instance
    base.use_ios_le_protocol = False
    base._expected_response_command = 0x01

    cmd_id = 0x01
    payload_data = [0x12, 0x34]
    length_val = 1 + len(payload_data) + 2
    length_bytes = length_val.to_bytes(2, 'little')
    checksum_input = list(length_bytes) + [cmd_id] + payload_data
    checksum_val = sum(checksum_input)
    checksum_bytes = checksum_val.to_bytes(2, 'little')
    message = bytearray([constants.MESSAGE_START_BYTE]) + bytearray(length_bytes) + bytearray([cmd_id]) + bytearray(payload_data) + bytearray(checksum_bytes) + bytearray([constants.MESSAGE_END_BYTE])

    junk_data = bytearray([0xFF, 0xEE, 0xDD])
    mock_data = junk_data + message

    result = base._handle_basic_protocol_notification(mock_data)
    assert result is True
    assert not base.notification_queue.empty()
    response = await base.notification_queue.get()
    assert response['command_id'] == cmd_id
    assert response['payload'] == bytearray(payload_data)

@pytest.mark.asyncio
async def test_handle_basic_protocol_notification_incomplete_message(divoom_base_instance):
    """Test basic protocol notification handler with an incomplete message."""
    base = divoom_base_instance
    base.use_ios_le_protocol = False
    base._expected_response_command = 0x01

    cmd_id = 0x01
    payload_data = [0x12, 0x34]
    length_val = 1 + len(payload_data) + 2
    length_bytes = length_val.to_bytes(2, 'little')
    checksum_input = list(length_bytes) + [cmd_id] + payload_data
    checksum_val = sum(checksum_input)
    checksum_bytes = checksum_val.to_bytes(2, 'little')
    
    # Missing end byte
    incomplete_message = bytearray([constants.MESSAGE_START_BYTE]) + bytearray(length_bytes) + bytearray([cmd_id]) + bytearray(payload_data) + bytearray(checksum_bytes)

    result = base._handle_basic_protocol_notification(incomplete_message)
    assert result is True # It processes what it can and leaves the rest in buffer
    assert base.notification_queue.empty()
    assert base.message_buf == list(incomplete_message) # Should still be in buffer

@pytest.mark.asyncio
async def test_handle_basic_protocol_notification_checksum_mismatch(divoom_base_instance):
    """Test basic protocol notification handler with a checksum mismatch."""
    base = divoom_base_instance
    base.use_ios_le_protocol = False
    base._expected_response_command = 0x01

    cmd_id = 0x01
    payload_data = [0x12, 0x34]
    length_val = 1 + len(payload_data) + 2
    length_bytes = length_val.to_bytes(2, 'little')
    
    # Incorrect checksum
    incorrect_checksum_bytes = (0x0000).to_bytes(2, 'little') # Deliberately wrong

    mock_data = bytearray([constants.MESSAGE_START_BYTE]) + bytearray(length_bytes) + bytearray([cmd_id]) + bytearray(payload_data) + bytearray(incorrect_checksum_bytes) + bytearray([constants.MESSAGE_END_BYTE])

    result = base._handle_basic_protocol_notification(mock_data)
    assert result is True
    assert base.notification_queue.empty() # Should discard due to checksum mismatch

@pytest.mark.asyncio
async def test_wait_for_response_success(divoom_base_instance):
    """Test wait_for_response with a successful match."""
    base = divoom_base_instance
    expected_cmd = 0x01
    expected_payload = b'\x11\x22\x33'
    
    base._expected_response_command = expected_cmd
    await base.notification_queue.put({'command_id': expected_cmd, 'payload': expected_payload})

    response = await base.wait_for_response(expected_cmd, timeout=1)
    assert response == expected_payload
    assert base._expected_response_command is None

@pytest.mark.asyncio
async def test_wait_for_response_generic_ack_then_success(divoom_base_instance):
    """Test wait_for_response with a generic ACK followed by a successful match."""
    base = divoom_base_instance
    expected_cmd = 0x45 # A command that expects a generic ACK
    expected_payload = b'\x11\x22\x33'
    
    base._expected_response_command = expected_cmd
    
    # Temporarily add 0x45 to GENERIC_ACK_COMMANDS for this test
    original_generic_acks = constants.GENERIC_ACK_COMMANDS
    constants.GENERIC_ACK_COMMANDS = original_generic_acks + (0x45,)

    try:
        await base.notification_queue.put({'command_id': 0x33, 'payload': b''}) # Generic ACK
        await base.notification_queue.put({'command_id': expected_cmd, 'payload': expected_payload}) # Actual response

        response = await base.wait_for_response(expected_cmd, timeout=1)
        assert response == expected_payload
        assert base._expected_response_command is None
    finally:
        constants.GENERIC_ACK_COMMANDS = original_generic_acks

@pytest.mark.asyncio
async def test_wait_for_response_timeout(divoom_base_instance):
    """Test wait_for_response with a timeout."""
    base = divoom_base_instance
    base._expected_response_command = 0x01
    response = await base.wait_for_response(0x01, timeout=0.1)
    assert response is None
    assert base._expected_response_command == 0x01 # Should not clear on timeout

@pytest.mark.asyncio
async def test_send_command_and_wait_for_response_success(divoom_base_instance, mock_bleak_client):
    """Test send_command_and_wait_for_response with success."""
    base = divoom_base_instance
    mock_bleak_client.is_connected = True
    expected_payload = b'\x11\x22\x33'
    
    # Mock send_command to put a response in the queue
    async def mock_send_command(command, args, write_with_response):
        await base.notification_queue.put({'command_id': command, 'payload': expected_payload})
        return True
    base.send_command = AsyncMock(side_effect=mock_send_command)

    response = await base.send_command_and_wait_for_response(0x01, [], timeout=1)
    assert response == expected_payload
    base.send_command.assert_called_once_with(0x01, [], write_with_response=True)
    assert base._expected_response_command is None

@pytest.mark.asyncio
async def test_send_command_and_wait_for_response_not_connected(divoom_base_instance, mock_bleak_client):
    """Test send_command_and_wait_for_response when not connected."""
    base = divoom_base_instance
    mock_bleak_client.is_connected = False
    response = await base.send_command_and_wait_for_response(0x01, [], timeout=1)
    assert response is None
    assert base._expected_response_command is None

@pytest.mark.asyncio
async def test_send_command_success(divoom_base_instance, mock_bleak_client):
    """Test send_command success."""
    base = divoom_base_instance
    mock_bleak_client.is_connected = True
    base._send_basic_protocol_payload = AsyncMock(return_value=True) # Mock the actual sending

    result = await base.send_command(0x01, [0x12, 0x34])
    assert result is True
    base._send_basic_protocol_payload.assert_called_once()

@pytest.mark.asyncio
async def test_send_command_with_string_command(divoom_base_instance, mock_bleak_client):
    """Test send_command with a string command name."""
    base = divoom_base_instance
    mock_bleak_client.is_connected = True
    base._send_basic_protocol_payload = AsyncMock(return_value=True)

    result = await base.send_command("set light mode", [0x12, 0x34])
    assert result is True
    base._send_basic_protocol_payload.assert_called_once()

@pytest.mark.asyncio
async def test_send_payload_ios_le_success(divoom_base_instance, mock_bleak_client):
    """Test send_payload with iOS LE protocol success."""
    base = divoom_base_instance
    base.use_ios_le_protocol = True
    mock_bleak_client.is_connected = True
    base._send_ios_le_payload = AsyncMock(return_value=True)

    result = await base.send_payload([0x01, 0x12, 0x34])
    assert result is True
    base._send_ios_le_payload.assert_called_once()

@pytest.mark.asyncio
async def test_send_payload_basic_protocol_success(divoom_base_instance, mock_bleak_client):
    """Test send_payload with Basic Protocol success."""
    base = divoom_base_instance
    base.use_ios_le_protocol = False
    mock_bleak_client.is_connected = True
    base._send_basic_protocol_payload = AsyncMock(return_value=True)

    result = await base.send_payload([0x01, 0x12, 0x34])
    assert result is True
    base._send_basic_protocol_payload.assert_called_once()

@pytest.mark.asyncio
async def test_send_payload_reconnect_success(divoom_base_instance, mock_bleak_client):
    """Test send_payload with initial disconnection and successful reconnection."""
    base = divoom_base_instance
    mock_bleak_client.is_connected = False # Initially disconnected
    base.connect = AsyncMock(return_value=None)
    base._send_basic_protocol_payload = AsyncMock(return_value=True)

    result = await base.send_payload([0x01, 0x12, 0x34])
    assert result is True
    base.connect.assert_called_once()
    base._send_basic_protocol_payload.assert_called_once()

@pytest.mark.asyncio
async def test_send_payload_reconnect_failure(divoom_base_instance, mock_bleak_client):
    """Test send_payload with initial disconnection and failed reconnection."""
    base = divoom_base_instance
    mock_bleak_client.is_connected = False # Initially disconnected
    base.connect = AsyncMock(side_effect=ConnectionError("Failed to connect"))
    base._send_basic_protocol_payload = AsyncMock(return_value=True)

    result = await base.send_payload([0x01, 0x12, 0x34], max_retries=1)
    assert result is False
    base.connect.assert_called_once()
    base._send_basic_protocol_payload.assert_not_called()

def test_int2hexlittle(divoom_base_instance):
    """Test _int2hexlittle conversion."""
    base = divoom_base_instance
    assert base._int2hexlittle(0x1234) == "3412"
    assert base._int2hexlittle(0x0001) == "0100"
    assert base._int2hexlittle(0xFFFF) == "ffff"

def test_escape_payload(divoom_base_instance):
    """Test _escape_payload function."""
    base = divoom_base_instance
    payload = [0x01, 0x02, 0x03, 0x11, 0x13, 0x14, 0x04]
    expected_escaped = [0x01, 0x02, 0x03, 0x11, 0x13, 0x14, 0x11, 0x04] # 0x04 becomes 0x11 0x04
    assert base._escape_payload(payload) == expected_escaped

    payload_with_all_escapes = [0x01, 0x02, 0x03, constants.ESCAPE_BYTE_1, constants.ESCAPE_BYTE_2, constants.ESCAPE_BYTE_3, 0x04]
    expected_all_escaped = [0x01, 0x02, 0x03] + constants.ESCAPE_SEQUENCE_1 + constants.ESCAPE_SEQUENCE_2 + constants.ESCAPE_SEQUENCE_3 + [0x04]
    assert base._escape_payload(payload_with_all_escapes) == expected_all_escaped

def test_getCRC(divoom_base_instance):
    """Test _getCRC checksum calculation."""
    base = divoom_base_instance
    assert base._getCRC([0x01, 0x02, 0x03]) == "0600"
    assert base._getCRC([0xFF, 0xFF]) == "fe00" # 0x1FE -> 0xFE01 (little endian)
    assert base._getCRC([0x00]) == "0000"

def test_make_message_basic_protocol(divoom_base_instance):
    """Test _make_message for basic protocol."""
    base = divoom_base_instance
    base.escapePayload = False
    payload_bytes = [0x01, 0x12, 0x34]
    # Length = Cmd (1) + Payload (3) + Checksum (2) = 6
    # Length bytes: 0x06 0x00
    # Checksum input: 0x06 0x00 0x01 0x12 0x34 = 0x4D -> 0x4D 0x00
    # Expected: 0x01 0x0600 0x011234 0x4D00 0x02
    expected_hex = "0106000112344d0002"
    assert base._make_message(payload_bytes) == expected_hex

def test_make_message_basic_protocol_escaped(divoom_base_instance):
    """Test _make_message for basic protocol with escaping."""
    base = divoom_base_instance
    base.escapePayload = True
    payload_bytes = [0x01, 0x04, 0x02] # 0x04 should be escaped
    # Escaped payload: [0x01, 0x11, 0x04, 0x02]
    # Length = Cmd (1) + Escaped Payload (4) + Checksum (2) = 7
    # Length bytes: 0x07 0x00
    # Checksum input: 0x07 0x00 0x01 0x11 0x04 0x02 = 0x1F -> 0x1F 0x00
    # Expected: 0x01 0x0700 0x01110402 0x1F00 0x02
    expected_hex = "010700011104021f0002"
    assert base._make_message(payload_bytes) == expected_hex

def test_make_message_ios_le(divoom_base_instance):
    """Test _make_message_ios_le for iOS LE protocol."""
    base = divoom_base_instance
    payload_bytes = [0x01, 0x12, 0x34] # Cmd ID 0x01, Data 0x12, 0x34
    packet_number = 0x00000000

    # Header: 0x0104000000
    # Data Length: Cmd ID (1) + Packet Num (4) + Data (2) + Checksum (2) = 9 -> 0x0900
    # Cmd ID: 0x01
    # Packet Num: 0x00000000
    # Data: 0x1234
    # Checksum input: 0x0900 0x01 0x00000000 0x1234 = 0x50 -> 0x5000
    # Expected: 0x0104000000 0x0900 0x01 0x00000000 0x1234 0x5000
    expected_hex = "01040000000900010000000012345000"
    assert base._make_message_ios_le(payload_bytes, packet_number) == expected_hex
