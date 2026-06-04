#!/usr/bin/env python3
import sys
import os
import asyncio
import logging
import time
import subprocess
import glob
from typing import List

# Ensure divoom_lib is on PATH
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

try:
    from IOBluetooth import IOBluetoothDevice
except ImportError:
    print("[ Err ] IOBluetooth is not available on this system (requires macOS).")
    sys.exit(1)

from divoom_lib.bt_spp_transport import BTSppTransport, BtSppNotification
from divoom_lib.utils.discovery import discover_device
from bleak import BleakClient

# Formatting functions per user rules
def print_info(message):
    """Prints an informational message."""
    print(f"[ ==> ] {message}")

def print_wrn(message):
    """Prints a warning message."""
    print(f"[ Wrn ] {message}")

def print_err(message):
    """Prints an error message."""
    print(f"[ Err ] {message}")

def print_ok(message):
    """Prints a success message."""
    print(f"[ Ok  ] {message}")

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(name)s: %(message)s')
logging.getLogger("bleak").setLevel(logging.WARNING)
logger = logging.getLogger("hardware_debug")
logger.setLevel(logging.DEBUG)

# 1. System Profiler Probe
def run_system_profiler_probe(device_name: str) -> str:
    print_info("Querying system_profiler for Bluetooth configuration...")
    try:
        res = subprocess.run(["system_profiler", "SPBluetoothDataType"], capture_output=True, text=True, check=True)
        lines = res.stdout.splitlines()
        device_section = []
        in_device = False
        indent_level = 0
        
        for line in lines:
            if device_name in line:
                in_device = True
                device_section.append(line)
                indent_level = len(line) - len(line.lstrip())
                continue
            if in_device:
                current_indent = len(line) - len(line.lstrip())
                if line.strip() == "" or (current_indent <= indent_level and line.strip()):
                    in_device = False
                else:
                    device_section.append(line)
                    
        if device_section:
            print_ok(f"Found macOS system profiler entry for '{device_name}':")
            for l in device_section:
                print(f"  {l.strip()}")
            return "\n".join(device_section)
        else:
            print_wrn(f"Could not find a specific system_profiler section for '{device_name}'.")
    except Exception as e:
        print_err(f"Failed to run system_profiler: {e}")
    return ""

# 2. Check /dev/cu.* Serial Ports
def check_serial_ports(device_name: str):
    print_info("Checking for virtual serial ports in /dev/cu.*...")
    ports = glob.glob("/dev/cu.*")
    matched_ports = [p for p in ports if device_name.lower().replace("-", "") in p.lower().replace("-", "")]
    
    if not matched_ports:
        print_wrn(f"No serial ports matching '{device_name}' found in /dev/cu.*.")
        print(f"  (Available ports: {', '.join(ports[:5])}...)")
        return
        
    for port in matched_ports:
        print_ok(f"Found virtual serial port: {port}")
        try:
            import serial
            print_info(f"Attempting to open {port} using pyserial at 115200 bps...")
            with serial.Serial(port, 115200, timeout=2.0) as ser:
                print_ok(f"Successfully opened {port}!")
                # Send get_volume basic frame command
                get_vol_cmd = bytes.fromhex("010300090c0002") # Basic frame get_volume
                print_info(f"Writing get_vol_cmd (0x09) to {port}: {get_vol_cmd.hex()}")
                ser.write(get_vol_cmd)
                ser.flush()
                # Wait for response
                resp = ser.read(10)
                if resp:
                    print_ok(f"Received response from serial port: {resp.hex()}")
                else:
                    print_wrn("Zero bytes received back from serial port (timeout).")
                    
                # Test color change to GREEN via serial port
                green_payload = [0x45, 0x01, 0x00, 0xFF, 0x00, 100, 0x00, 0x01]
                from divoom_lib.framing import encode_basic_payload
                green_frame = encode_basic_payload(green_payload)
                print_info(f"Writing green_frame (0x45) to {port}: {green_frame.hex()}")
                ser.write(green_frame)
                ser.flush()
                print_ok("Sent green color command via serial port! Please verify if device screen turned green.")
                time.sleep(1.0)
        except ImportError:
            print_wrn("pyserial module not installed; skipping live serial port write test.")
        except Exception as e:
            print_err(f"Failed to communicate with serial port {port}: {e}")

# 3. BLE Standard Services Probe
async def test_ble_services(device_name: str):
    print_info(f"Scanning for BLE advertisements matching '{device_name}'...")
    try:
        ble_device, device_address = await discover_device(name_substring=device_name)
        if not ble_device:
            print_wrn(f"Could not find BLE advertisement for '{device_name}'.")
            return
            
        print_ok(f"Found BLE device: {ble_device.name} ({device_address})")
        print_info(f"Connecting to {device_address} over BLE...")
        
        async with BleakClient(device_address, timeout=10.0) as client:
            if client.is_connected:
                print_ok(f"Successfully connected over BLE to {device_address}!")
                print_info("Discovering BLE Services and Characteristics...")
                for service in client.services:
                    print(f"  - Service: {service.uuid} ({service.description})")
                    for char in service.characteristics:
                        properties = ", ".join(char.properties)
                        print(f"    - Char: {char.uuid} [{properties}]")
                        
                # Try to read Battery Level (if present)
                battery_char = "00002a19-0000-1000-8000-00805f9b34fb"
                try:
                    val = await client.read_gatt_char(battery_char)
                    print_ok(f"Battery Level read successfully: {int(val[0])}%")
                except Exception:
                    pass
            else:
                print_err("Bleak reports client is not connected.")
    except Exception as e:
        print_err(f"BLE connectivity test failed: {e}")

# 4. Standard Classic SPP Probe
async def test_channel_spp(mac: str, channel_id: int) -> bool:
    print_info(f"Testing SPP Connection to {mac} on RFCOMM Channel {channel_id}...")
    spp = BTSppTransport(mac_address=mac, channel_id=channel_id, logger=logger)
    
    try:
        spp.OPEN_TIMEOUT_S = 4.0
        await spp.connect()
        print_ok(f"Successfully connected to {mac} on RFCOMM Channel {channel_id}!")
        
        # 1. Test get_volume (0x09) with basic framing
        print_info("Sending SPP get_volume (0x09) with BASIC framing...")
        await spp.send([0x09], framing=spp.FRAMING_BASIC)
        try:
            notif = await spp.read_notification(timeout=2.0)
            print_ok(f"Received BASIC response: Cmd ID {notif.command_id:#x} | Payload: {notif.payload.hex()}")
        except Exception as e:
            print_wrn(f"No response to BASIC get_volume: {e}")

        # 2. Test get_volume (0x09) with iOS-LE framing
        print_info("Sending SPP get_volume (0x09) with iOS-LE framing...")
        await spp.send([0x09], framing=spp.FRAMING_IOS_LE)
        try:
            notif = await spp.read_notification(timeout=2.0)
            print_ok(f"Received iOS-LE response: Cmd ID {notif.command_id:#x} | Payload: {notif.payload.hex()}")
        except Exception as e:
            print_wrn(f"No response to iOS-LE get_volume: {e}")

        # 3. Test changing color to GREEN (0x45)
        print_info("Sending show_light command to change color to GREEN...")
        green_payload = [0x45, 0x01, 0x00, 0xFF, 0x00, 100, 0x00, 0x01]
        await spp.send(green_payload, framing=spp.FRAMING_BASIC)
        print_info("Green light command sent. Please visually verify if the screen changed color.")
        
        await asyncio.sleep(1.0)
        return True

    except Exception as e:
        print_err(f"Connection/Test failed on channel {channel_id}: {e}")
        return False
    finally:
        if spp.is_connected:
            await spp.disconnect()
            print_info(f"Disconnected from {mac} on Channel {channel_id}")

async def main():
    print_info("Listing paired Bluetooth devices via IOBluetooth...")
    paired_devices = IOBluetoothDevice.pairedDevices() or []
    if not paired_devices:
        print_wrn("No paired Bluetooth devices found on this Mac.")
        return

    divoom_devices = []
    for dev in paired_devices:
        name = dev.getName() or ""
        addr = dev.getAddressString() or ""
        if any(kw in name.lower() for kw in ["timoo", "tivoo", "ditoo", "pixoo", "timebox", "divoom"]):
            divoom_devices.append((name, addr, dev))
            print_ok(f"Found paired Divoom device: {name} ({addr})")
        else:
            print(f"  - Non-Divoom device: {name} ({addr})")

    if not divoom_devices:
        print_err("No paired Divoom devices found. Please pair your Divoom device in System Settings first.")
        return

    for name, addr, dev in divoom_devices:
        print("\n" + "="*80)
        print_info(f"DIAGNOSTIC TARGET: {name} ({addr})")
        print("="*80)
        
        # Section 1: system_profiler
        run_system_profiler_probe(name)
        
        # Section 2: Pyserial /dev/cu.*
        check_serial_ports(name)
        
        # Section 3: BLE scan and services
        await test_ble_services(name)

        # Section 4: SDP & Classic RFCOMM
        print_info("Performing Classic SDP query...")
        dev.performSDPQuery_(None)
        services = []
        for _ in range(50):
            services = dev.services() or []
            if services:
                break
            await asyncio.sleep(0.1)

        channels = set()
        print_info(f"Found {len(services)} services:")
        for s in services:
            s_name = s.getServiceName() or "Unknown"
            rfcomm_channel = -1
            try:
                rc, chan = s.getRFCOMMChannelID_(None)
                if rc == 0:
                    rfcomm_channel = chan
            except Exception:
                try:
                    rfcomm_channel = s.getRFCOMMChannelID()
                except Exception:
                    pass
            print(f"  - Service: {s_name} | RFCOMM Channel: {rfcomm_channel}")
            if rfcomm_channel > 0:
                channels.add(rfcomm_channel)

        if not channels:
            print_wrn("No RFCOMM channels found in SDP services. Testing default channels 1 and 2.")
            channels = {1, 2}

        # Test each channel
        for chan in sorted(list(channels)):
            success = await test_channel_spp(addr, chan)
            if success:
                print_ok(f"Channel {chan} connected successfully. Diagnostics completed.")
            else:
                print_err(f"Channel {chan} connection failed.")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print_wrn("Interrupted by user.")
    except Exception as e:
        print_err(f"Unhandled script exception: {e}")
