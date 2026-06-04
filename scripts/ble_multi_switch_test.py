#!/usr/bin/env python3
import sys
import os
import asyncio
import logging

# Ensure divoom_lib is on PATH
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from divoom_lib.divoom import Divoom
from divoom_lib.utils import discovery

# Formatting functions per user rules
def print_info(message):
    print(f"[ ==> ] {message}")

def print_wrn(message):
    print(f"[ Wrn ] {message}")

def print_err(message):
    print(f"[ Err ] {message}")

def print_ok(message):
    print(f"[ Ok  ] {message}")

logging.basicConfig(level=logging.DEBUG, format='%(asctime)s [%(levelname)s] %(name)s: %(message)s')
logging.getLogger("bleak").setLevel(logging.WARNING)
logger = logging.getLogger("ble_multi_switch")

async def main():
    print_info("Discovering Divoom device via BLE...")
    ble_device, device_id = await discovery.discover_device(name_substring="Timoo", address=None)
    if not ble_device:
        print_err("No Divoom device found.")
        return
        
    print_ok(f"Found device: {ble_device.name} ({device_id})")
    
    divoom = Divoom(mac=device_id, logger=logger)
    
    # We force BLE mode (disable SPP to test BLE path explicitly)
    divoom._conn._use_spp = False
    
    print_info("Connecting via BLE...")
    await divoom.connect()
    print_ok("Connected!")
    
    try:
        # Phase 1: Set color to GREEN
        print_info("Phase 1: Setting color to GREEN (00FF00)...")
        res1 = await divoom.display.show_light(color="00FF00", brightness=100)
        print_info(f"Green command sent successfully? {res1}")
        print_info("Waiting 3 seconds...")
        await asyncio.sleep(3.0)
        
        # Phase 2: Set color to RED
        print_info("Phase 2: Setting color to RED (FF0000)...")
        res2 = await divoom.display.show_light(color="FF0000", brightness=100)
        print_info(f"Red command sent successfully? {res2}")
        print_info("Waiting 3 seconds...")
        await asyncio.sleep(3.0)
        
        # Phase 3: Set color to BLUE
        print_info("Phase 3: Setting color to BLUE (0000FF)...")
        res3 = await divoom.display.show_light(color="0000FF", brightness=100)
        print_info(f"Blue command sent successfully? {res3}")
        print_info("Waiting 3 seconds...")
        await asyncio.sleep(3.0)
        
    except Exception as e:
        print_err(f"Exception during multi-switch: {e}")
    finally:
        print_info("Disconnecting...")
        await divoom.disconnect()
        print_ok("Disconnected.")

if __name__ == "__main__":
    asyncio.run(main())
