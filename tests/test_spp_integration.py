import sys
from unittest.mock import MagicMock, AsyncMock, patch

# Mock the entire IOBluetooth module to bypass PyObjC limitations
mock_iobluetooth = MagicMock()
sys.modules["IOBluetooth"] = mock_iobluetooth

import pytest
from divoom_lib.divoom import Divoom
from divoom_lib.exceptions import DeviceConnectionError

@pytest.mark.asyncio
async def test_spp_connection_resolution():
    """Verify that a device with a classic name triggers SPP connection and resolves Classic MAC via IOBluetooth."""
    mock_paired_device = MagicMock()
    mock_paired_device.getName.return_value = "Timoo-audio-4"
    mock_paired_device.getAddressString.return_value = "11-75-58-54-b9-13"
    
    mock_iobluetooth.IOBluetoothDevice.pairedDevices.return_value = [mock_paired_device]
    
    # Construct Divoom with name Timoo
    divoom = Divoom(mac="11-75-58-54-b9-13", device_name="Timoo")
    
    # Mock BTSppTransport connect & properties
    with patch("divoom_lib.bt_spp_transport.BTSppTransport") as MockTransport:
        mock_spp = AsyncMock()
        mock_spp.is_connected = False
        mock_spp.mac_address = "11-75-58-54-b9-13"
        
        async def mock_connect():
            mock_spp.is_connected = True
        mock_spp.connect.side_effect = mock_connect

        MockTransport.return_value = mock_spp
        
        await divoom.connect()
        
        assert divoom._conn._use_spp is True
        assert divoom._conn._spp_client is mock_spp
        mock_spp.connect.assert_called_once()
        
        # Disconnect
        mock_spp.is_connected = False
        await divoom.disconnect()
        mock_spp.disconnect.assert_called_once()

@pytest.mark.asyncio
async def test_spp_send_payload():
    """Verify that sending a command on an active SPP connection routes through the SPP client using basic framing."""
    mock_paired_device = MagicMock()
    mock_paired_device.getName.return_value = "Timoo-audio-4"
    mock_paired_device.getAddressString.return_value = "11-75-58-54-b9-13"
    
    mock_iobluetooth.IOBluetoothDevice.pairedDevices.return_value = [mock_paired_device]
    
    with patch("divoom_lib.bt_spp_transport.BTSppTransport") as MockTransport:
        mock_spp = AsyncMock()
        mock_spp.is_connected = True
        mock_spp.mac_address = "11-75-58-54-b9-13"
        mock_spp.FRAMING_BASIC = "basic"
        mock_spp.FRAMING_IOS_LE = "ios_le"
        MockTransport.return_value = mock_spp
        
        divoom = Divoom(mac="11-75-58-54-b9-13", device_name="Timoo")
        # Connect manually to trigger setup
        divoom._conn._use_spp = True
        divoom._conn._spp_client = mock_spp
        
        # Send a light mode change command (0x45)
        await divoom.display.show_light(color="00FF00", brightness=100)
        
        # Verify it used SPP send
        mock_spp.send.assert_called_once()
        called_args, called_kwargs = mock_spp.send.call_args
        assert called_args[0][0] == 0x45 # set channel light command
        assert called_kwargs.get("framing") == "basic"
