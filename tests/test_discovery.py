import pytest
import asyncio
import logging
from unittest.mock import AsyncMock, MagicMock, patch
from bleak import BleakScanner, BleakClient
from bleak.exc import BleakError
from divoom_lib.utils import discovery

# Suppress logging output during tests for cleaner output
@pytest.fixture(autouse=True)
def no_logging(caplog):
    caplog.set_level(logging.CRITICAL)

@pytest.fixture
def mock_bleak_device():
    """Mock a Bleak device object."""
    device = MagicMock()
    device.name = "Divoom Mock"
    device.address = "AA:BB:CC:DD:EE:FF"
    return device

@pytest.fixture
def mock_bleak_scanner_discover():
    """Mock BleakScanner.discover."""
    with patch('divoom_lib.utils.discovery.BleakScanner.discover', new_callable=AsyncMock) as mock_discover:
        yield mock_discover

@pytest.fixture
def mock_bleak_client():
    """Mock a BleakClient instance."""
    client = AsyncMock(spec=BleakClient)
    client.services = [] # Initialize with empty services
    return client

@pytest.mark.asyncio
async def test_discover_device_by_name_success(mock_bleak_scanner_discover, mock_bleak_device):
    """Test discover_device by name substring success."""
    mock_bleak_scanner_discover.return_value = [mock_bleak_device]
    
    device, device_id = await discovery.discover_device(name_substring="Divoom Mock")
    assert device == mock_bleak_device
    assert device_id == mock_bleak_device.address
    mock_bleak_scanner_discover.assert_called_once_with(timeout=10.0)

@pytest.mark.asyncio
async def test_discover_device_by_name_not_found(mock_bleak_scanner_discover):
    """Test discover_device by name substring not found."""
    mock_bleak_scanner_discover.return_value = []
    
    device, device_id = await discovery.discover_device(name_substring="NonExistent")
    assert device is None
    assert device_id is None
    mock_bleak_scanner_discover.assert_called_once_with(timeout=10.0)

@pytest.mark.asyncio
async def test_discover_device_by_address_resolved(mock_bleak_scanner_discover, mock_bleak_device):
    """Test discover_device by address when resolved."""
    mock_bleak_scanner_discover.return_value = [mock_bleak_device]
    
    device, device_id = await discovery.discover_device(address="AA:BB:CC:DD:EE:FF")
    assert device == mock_bleak_device
    assert device_id == mock_bleak_device.address
    mock_bleak_scanner_discover.assert_called_once_with(timeout=3.0)

@pytest.mark.asyncio
async def test_discover_device_by_address_not_resolved(mock_bleak_scanner_discover):
    """Test discover_device by address when not resolved quickly."""
    mock_bleak_scanner_discover.return_value = [] # No device found in short scan
    
    device, device_id = await discovery.discover_device(address="AA:BB:CC:DD:EE:FF")
    assert device == "AA:BB:CC:DD:EE:FF" # Should return the address string
    assert device_id == "AA:BB:CC:DD:EE:FF"
    mock_bleak_scanner_discover.assert_called_once_with(timeout=3.0)

@pytest.mark.asyncio
async def test_discover_characteristics_success(mock_bleak_client):
    """Test discover_characteristics successfully finds characteristics."""
    # Mock services and characteristics
    mock_char_write = MagicMock(uuid="write_uuid", properties=["write"])
    mock_char_notify = MagicMock(uuid="notify_uuid", properties=["notify"])
    mock_char_read = MagicMock(uuid="read_uuid", properties=["read"])
    mock_char_write_notify = MagicMock(uuid="write_notify_uuid", properties=["write", "notify"])

    mock_service = MagicMock()
    mock_service.characteristics = [mock_char_write, mock_char_notify, mock_char_read, mock_char_write_notify]
    mock_bleak_client.services = [mock_service]

    write_chars, notify_chars, read_chars = await discovery.discover_characteristics(mock_bleak_client)

    assert len(write_chars) == 2 # write_uuid, write_notify_uuid
    assert mock_char_write in write_chars
    assert mock_char_write_notify in write_chars

    assert len(notify_chars) == 2 # notify_uuid, write_notify_uuid
    assert mock_char_notify in notify_chars
    assert mock_char_write_notify in notify_chars

    assert len(read_chars) == 1 # read_uuid
    assert mock_char_read in read_chars

@pytest.mark.asyncio
async def test_discover_characteristics_no_services(mock_bleak_client):
    """Test discover_characteristics when no services are found."""
    mock_bleak_client.services = [] # No services
    
    write_chars, notify_chars, read_chars = await discovery.discover_characteristics(mock_bleak_client)
    assert write_chars == []
    assert notify_chars == []
    assert read_chars == []

@pytest.mark.asyncio
async def test_discover_characteristics_bleak_error(mock_bleak_client):
    """Test discover_characteristics handles BleakError during service access."""
    # Simulate BleakError when accessing client.services
    type(mock_bleak_client).services = property(MagicMock(side_effect=BleakError("Service error")))

    write_chars, notify_chars, read_chars = await discovery.discover_characteristics(mock_bleak_client)
    assert write_chars == []
    assert notify_chars == []
    assert read_chars == []

def test_pick_char_uuid_preferred_uuid_exact_match():
    """Test pick_char_uuid with exact preferred_uuid match."""
    mock_char1 = MagicMock(uuid="1234-5678-90ab", properties=["write"])
    mock_char2 = MagicMock(uuid="abcd-efgh-ijkl", properties=["notify"])
    candidates = [mock_char1, mock_char2]
    assert discovery.pick_char_uuid("1234-5678-90ab", candidates) == "1234-5678-90ab"

def test_pick_char_uuid_preferred_uuid_no_match():
    """Test pick_char_uuid with preferred_uuid but no exact match."""
    mock_char1 = MagicMock(uuid="1234-5678-90ab", properties=["write"])
    candidates = [mock_char1]
    assert discovery.pick_char_uuid("non-existent-uuid", candidates) == "1234-5678-90ab" # Falls back to other logic

def test_pick_char_uuid_write_notify_with_hint():
    """Test pick_char_uuid prioritizes write+notify with hint."""
    mock_char1 = MagicMock(uuid="49535343-1111-2222", properties=["write"])
    mock_char2 = MagicMock(uuid="49535343-3333-4444", properties=["write", "notify"])
    mock_char3 = MagicMock(uuid="abcd-efgh-ijkl", properties=["write", "notify"])
    candidates = [mock_char1, mock_char2, mock_char3]
    assert discovery.pick_char_uuid(None, candidates, prefix_hint="49535343") == "49535343-3333-4444"

def test_pick_char_uuid_write_notify_no_hint():
    """Test pick_char_uuid prioritizes write+notify without hint."""
    mock_char1 = MagicMock(uuid="1234-5678-90ab", properties=["write"])
    mock_char2 = MagicMock(uuid="abcd-efgh-ijkl", properties=["write", "notify"])
    candidates = [mock_char1, mock_char2]
    assert discovery.pick_char_uuid(None, candidates, prefix_hint="non-matching") == "abcd-efgh-ijkl"

def test_pick_char_uuid_fallback_hint_match():
    """Test pick_char_uuid falls back to hint match."""
    mock_char1 = MagicMock(uuid="1234-5678-90ab", properties=["write"])
    mock_char2 = MagicMock(uuid="49535343-3333-4444", properties=["read"])
    candidates = [mock_char1, mock_char2]
    assert discovery.pick_char_uuid(None, candidates, prefix_hint="49535343") == "49535343-3333-4444"

def test_pick_char_uuid_fallback_first_candidate():
    """Test pick_char_uuid falls back to first candidate."""
    mock_char1 = MagicMock(uuid="1234-5678-90ab", properties=["read"])
    mock_char2 = MagicMock(uuid="abcd-efgh-ijkl", properties=["notify"])
    candidates = [mock_char1, mock_char2]
    assert discovery.pick_char_uuid(None, candidates, prefix_hint="non-matching") == "1234-5678-90ab"

def test_pick_char_uuid_empty_candidates():
    """Test pick_char_uuid with empty candidates list."""
    assert discovery.pick_char_uuid(None, []) is None
    assert discovery.pick_char_uuid("any-uuid", []) is None
