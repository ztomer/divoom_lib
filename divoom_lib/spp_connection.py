# divoom_lib/spp_connection.py

import asyncio
import logging
from typing import Any
from . import models

logger = logging.getLogger("divoom_lib")

def resolve_classic_mac(name: str, mac_or_uuid: str, log=None) -> str | None:
    """Resolves Classic Bluetooth MAC address using IOBluetooth on macOS."""
    if log is None:
        log = logger
    if mac_or_uuid and len(mac_or_uuid) == 17 and ("-" in mac_or_uuid or ":" in mac_or_uuid):
        return mac_or_uuid.replace(":", "-")
    try:
        from IOBluetooth import IOBluetoothDevice
        paired = IOBluetoothDevice.pairedDevices() or []
        if name:
            for dev in paired:
                dev_name = dev.getName()
                if dev_name and dev_name.lower() == name.lower():
                    return dev.getAddressString()
        if name:
            for dev in paired:
                dev_name = dev.getName()
                if dev_name and (name.lower() in dev_name.lower() or dev_name.lower() in name.lower()):
                    return dev.getAddressString()
        if name:
            base_name = name.split("-")[0].split(" ")[0].lower()
            for dev in paired:
                dev_name = dev.getName()
                if dev_name and base_name in dev_name.lower():
                    return dev.getAddressString()
    except Exception as e:
        log.warning(f"Failed to resolve Classic MAC address via IOBluetooth: {e}")
    return None

async def read_spp_notifications_loop(conn: Any) -> None:
    """SPP background loop to read incoming notifications."""
    while conn.is_connected:
        try:
            notif = await conn._spp_client.read_notification(timeout=1.0)
            response_payload = {
                'command_id': notif.command_id,
                'payload': bytearray(notif.payload)
            }
            expected_cmd = conn._expected_response_command
            is_expected_response = expected_cmd is not None and notif.command_id == expected_cmd
            is_generic_ack = expected_cmd is not None and notif.command_id == models.GENERIC_ACK_COMMAND_ID and expected_cmd in models.GENERIC_ACK_COMMANDS
            
            if is_expected_response or is_generic_ack:
                conn.notification_queue.put_nowait(response_payload)
                conn._expected_response_command = None
            else:
                conn.notification_queue.put_nowait(response_payload)
        except asyncio.TimeoutError:
            continue
        except asyncio.CancelledError:
            break
        except Exception as e:
            conn.logger.error(f"Error in SPP notification loop: {e}")
            break

async def disconnect_spp(conn: Any) -> None:
    """Cleanly disconnects the SPP client and cancels the notification loop."""
    if hasattr(conn, "_spp_rx_task") and conn._spp_rx_task:
        conn._spp_rx_task.cancel()
        try:
            await conn._spp_rx_task
        except asyncio.CancelledError:
            pass
        conn._spp_rx_task = None
    if conn._spp_client:
        try:
            await conn._spp_client.disconnect()
            conn.logger.info("Disconnected from Divoom device via BT Classic SPP.")
        except Exception as e:
            conn.logger.error(f"Error disconnecting SPP: {e}")
