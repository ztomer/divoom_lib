#!/usr/bin/env python3
import sys
import os
import asyncio
import glob
import time

# Ensure divoom_lib is on PATH
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from divoom_lib.divoom import Divoom
from divoom_lib.utils import discovery

# Helper functions per user rules
def print_info(message):
    print(f"[ ==> ] {message}")

def print_wrn(message):
    print(f"[ Wrn ] {message}")

def print_err(message):
    print(f"[ Err ] {message}")

def print_ok(message):
    print(f"[ Ok  ] {message}")

async def run_color_cycle(divoom: Divoom, name: str, config_desc: str):
    """
    Cycles between Blue, Red, Green, querying the status after each.
    """
    colors = [
        ("BLUE", "0000FF"),
        ("RED", "FF0000"),
        ("GREEN", "00FF00")
    ]
    
    success_count = 0
    
    # 1. Connect
    print_info(f"Connecting to {name} via {config_desc}...")
    try:
        await divoom.connect()
        print_ok(f"Connected to {name} successfully!")
    except Exception as e:
        print_wrn(f"Connection failed: {e}")
        return False

    try:
        # 2. Query initial status
        print_info("Querying initial light status (0x46)...")
        status = await divoom.light.get_light_mode()
        if status:
            print_ok(f"Initial Status: Brightness={status.get('brightness_level')}%, Color=#{status.get('rgb_color_values')[0]:02x}{status.get('rgb_color_values')[1]:02x}{status.get('rgb_color_values')[2]:02x}")
        else:
            print_wrn("Could not read initial status.")

        # 3. Cycle colors
        for color_name, color_hex in colors:
            print_info(f"Setting color to {color_name} (#{color_hex})...")
            # Set the color
            await divoom.display.show_light(color=color_hex, brightness=100)
            
            # Sleep to allow command transmission and device update
            await asyncio.sleep(1.5)
            
            # Query updated status
            print_info(f"Querying status after setting {color_name}...")
            status = await divoom.light.get_light_mode()
            if status:
                r, g, b = status.get('rgb_color_values', (0,0,0))
                color_read = f"{r:02x}{g:02x}{b:02x}".upper()
                print_ok(f"Readback Status: Color is #{color_read}")
                if color_read == color_hex:
                    print_ok(f"Success: Verified color {color_name} matches readback!")
                    success_count += 1
                else:
                    print_wrn(f"Mismatch: Sent #{color_hex}, but device read back #{color_read}")
            else:
                print_wrn("Failed to retrieve status update (timeout or empty response).")

    except Exception as e:
        print_err(f"Error during color cycle: {e}")
    finally:
        if divoom.is_connected:
            await divoom.disconnect()
            print_info(f"Disconnected from {name}.")
            
    return success_count == len(colors)

async def main():
    print_info("Discovering nearby and paired Divoom devices...")
    
    # 1. Discover via Bleak
    devices = []
    try:
        devices = await discovery.discover_all_divoom_devices(timeout=5.0)
    except Exception as e:
        print_wrn(f"BLE scan failed: {e}")

    # 2. Add macOS paired devices
    try:
        from IOBluetooth import IOBluetoothDevice
        paired = IOBluetoothDevice.pairedDevices() or []
        for dev in paired:
            name = dev.getName()
            if name and any(kw in name.lower() for kw in ["timoo", "tivoo", "ditoo", "pixoo", "timebox", "divoom"]):
                addr = dev.getAddressString()
                if not any(d.get("address") == addr or d.get("name") == name for d in devices):
                    devices.append({"name": name, "address": addr})
    except Exception as e:
        print_wrn(f"Could not read paired devices via IOBluetooth: {e}")

    if not devices:
        print_err("No Divoom devices discovered or paired.")
        return

    print_info(f"Found {len(devices)} device(s): {[d['name'] for d in devices]}")

    for dev_info in devices:
        name = dev_info["name"]
        addr = dev_info["address"]
        print_ok(f"\n========================================\nDiagnosing Device: {name} ({addr})\n========================================")
        
        # Test Config A: BLE (Basic Protocol)
        print_info("--- Configuration A: BLE (Basic Protocol) ---")
        divoom_a = Divoom(mac=addr, use_ios_le_protocol=False)
        success_a = await run_color_cycle(divoom_a, name, "BLE (Basic Protocol)")
        if success_a:
            print_ok(f"==> CONFIRMED WORKABLE: {name} works perfectly with BLE (Basic Protocol)!")
            continue
            
        # Test Config B: BLE (iOS-LE Protocol)
        print_info("--- Configuration B: BLE (iOS-LE Protocol) ---")
        divoom_b = Divoom(mac=addr, use_ios_le_protocol=True)
        success_b = await run_color_cycle(divoom_b, name, "BLE (iOS-LE Protocol)")
        if success_b:
            print_ok(f"==> CONFIRMED WORKABLE: {name} works perfectly with BLE (iOS-LE Protocol)!")
            continue

        # Test Config C: Classic SPP (RFCOMM Serial)
        print_info("--- Configuration C: Classic SPP (RFCOMM Serial) ---")
        # Check if matching virtual serial port exists
        ports = glob.glob("/dev/cu.*")
        matched = [p for p in ports if name.lower().replace("-", "") in p.lower().replace("-", "")]
        if not matched:
            print_wrn(f"No virtual serial port matches '{name}' for Configuration C. Skipping.")
        else:
            divoom_c = Divoom(mac=addr, device_name=name)
            success_c = await run_color_cycle(divoom_c, name, f"Classic SPP Serial ({matched[0]})")
            if success_c:
                print_ok(f"==> CONFIRMED WORKABLE: {name} works perfectly with Classic SPP Serial!")
                continue
                
        print_err(f"==> ALL CONFIGURATIONS FAILED for {name}! Physical device did not cycle colors.")

if __name__ == "__main__":
    asyncio.run(main())
