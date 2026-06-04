#!/usr/bin/env python3
"""
monthly_best_daemon.py — Divoom Cloud monthly best scraper and BLE display daemon.
Queries popular/recommend animations from the Divoom public gallery and streams them
directly over BLE to the Divoom device.
"""

import sys
import json
import urllib.request
import urllib.error
import struct
import argparse
import asyncio
import logging
from pathlib import Path
from PIL import Image

# Add divoom-control paths so we can import divoom_lib and divoom_auth
sys.path.append(str(Path(__file__).parent.parent))
sys.path.append(str(Path(__file__).parent))

from divoom_lib import divoom_auth
from divoom_lib.divoom import Divoom
from divoom_lib.utils import discovery
from divoom_lib.models import (
    ANSGC_CONTROL_START_SENDING,
    ANSGC_CONTROL_SENDING_DATA,
    ANSGC_CONTROL_TERMINATE_SENDING
)

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


BASE_URL = "https://appin.divoom-gz.com"


def extract_gif_from_magic_43(file_data: bytes) -> bytes | None:
    """
    If the file is a Magic 43 container, extracts the embedded raw GIF bytes.
    Magic 43 format:
      Offset 0: Magic byte 43 (0x2b)
      Offset 6: 4-byte little-endian integer text_len
      Offset 10: start of text content (text_len bytes)
      Offset 10 + text_len: 4-byte little-endian integer gif_len (iL2)
      Offset 10 + text_len + 4: start of raw GIF data (gif_len bytes)
    """
    if len(file_data) < 10 or file_data[0] != 43:
        return None
    try:
        text_len = struct.unpack("<I", file_data[6:10])[0]
        text_start = 10
        text_end = text_start + text_len
        
        gif_len_offset = text_end
        if len(file_data) < gif_len_offset + 4:
            return None
            
        gif_len = struct.unpack("<I", file_data[gif_len_offset:gif_len_offset+4])[0]
        gif_start = gif_len_offset + 4
        gif_end = gif_start + gif_len
        
        if gif_end > len(file_data):
            gif_end = len(file_data)
            
        gif_data = file_data[gif_start:gif_end]
        if gif_data.startswith(b"GIF89a") or gif_data.startswith(b"GIF87a"):
            return gif_data
    except Exception as e:
        print_wrn(f"Failed to extract GIF from Magic 43: {e}")
    return None


async def stream_raw_bin_payload(divoom: Divoom, file_data: bytes) -> bool:
    """
    Streams a Divoom-native pre-compiled binary payload (magic 9, 18, 26)
    directly to the device using the 0x8b chunked transfer protocol.
    """
    file_size = len(file_data)
    print_info(f"Initiating chunked BLE transfer for native payload ({file_size} bytes)...")
    
    # 1. Start sending (Control Word 0)
    success = await divoom.animation.app_new_send_gif_cmd(
        control_word=ANSGC_CONTROL_START_SENDING,
        file_size=file_size
    )
    if not success:
        print_err("Failed to start chunked transfer command (0x8b, CW=0)")
        return False
        
    await asyncio.sleep(0.5)  # Let the device allocate buffers
    
    # 2. Transmit data in chunks (Control Word 1)
    chunk_size = 200  # Safe BLE transfer chunk size
    offset_id = 0
    
    for i in range(0, file_size, chunk_size):
        chunk = list(file_data[i:i+chunk_size])
        print_info(f"Sending chunk {offset_id} (bytes {i} to {i+len(chunk)} / {file_size})...")
        success = await divoom.animation.app_new_send_gif_cmd(
            control_word=ANSGC_CONTROL_SENDING_DATA,
            file_size=file_size,
            file_offset_id=offset_id,
            file_data=chunk
        )
        if not success:
            print_err(f"Failed to send chunk {offset_id}")
            return False
        offset_id += 1
        await asyncio.sleep(0.1)  # Brief sleep to avoid GATT congestion
        
    # 3. Terminate sending (Control Word 2)
    print_info("Terminating chunked BLE transfer...")
    await asyncio.sleep(0.5)
    success = await divoom.animation.app_new_send_gif_cmd(
        control_word=ANSGC_CONTROL_TERMINATE_SENDING
    )
    if success:
        print_ok("Successfully streamed Divoom bin file to device!")
        return True
    else:
        print_err("Failed to terminate chunked transfer command (0x8b, CW=2)")
        return False


async def main_async():
    parser = argparse.ArgumentParser(description="Divoom Monthly Best Automation Scraper & BLE Daemon")
    parser.add_argument("--address", help="BLE address of the physical Divoom device")
    parser.add_argument("--name", default="Timoo", help="Device name substring to search for (e.g. 'Timoo')")
    parser.add_argument("--limit", type=int, default=5, help="Number of gallery items to download and display (default: 5)")
    parser.add_argument("--classify", type=int, default=18, help="Divoom gallery classification ID (default: 18 = Recommend)")
    parser.add_argument("--dry-run", action="store_true", help="Run without connecting to physical BLE device (downloads only)")
    parser.add_argument("--loop", action="store_true", help="Run as a daemon looping indefinitely")
    parser.add_argument("--interval", type=int, default=3600, help="Loop interval in seconds (default: 3600)")
    parser.add_argument("--use-config", action="store_true",
                        help="Drive classify/interval/targets from the GUI-persisted "
                             "hot-channel config (~/.config/divoom-control/hotchannel.json)")
    args = parser.parse_args()

    # Configure logging
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    logger = logging.getLogger("monthly_best_daemon")

    # Resolve run parameters. With --use-config, the GUI-selected targets and
    # schedule drive the daemon so automatic syncs run headless (request 4.d).
    from divoom_lib import hotchannel_config
    hc_cfg = hotchannel_config.load_config()
    if args.use_config:
        classify = hc_cfg["classify"]
        interval = hc_cfg["interval"]
        targets = list(hc_cfg["targets"])
        if not args.loop:
            args.loop = bool(hc_cfg["enabled"])
        if not targets:
            print_wrn("Hot-channel config has no selected target devices; "
                      "select devices in the Monthly Best tab first.")
    else:
        classify = args.classify
        interval = args.interval
        # None => fall back to name-based discovery (existing behavior).
        targets = [args.address] if args.address else [None]

    # Load credentials
    print_info("Loading credentials from divoom_auth...")
    try:
        creds = divoom_auth.get_credentials()
        print_ok(f"Credentials loaded: UserId={creds.user_id}")
    except Exception as e:
        print_err(f"Failed to load credentials: {e}")
        sys.exit(1)

    # Load virtual device info
    device_id = 0
    device_pw = 0
    device_cache_path = Path.home() / ".config" / "divoom-control" / "virtual_device.json"
    if device_cache_path.exists():
        try:
            device_info = json.loads(device_cache_path.read_text(encoding="utf-8"))
            device_id = device_info.get("BluetoothDeviceId", 0)
            device_pw = device_info.get("DevicePassword", 0)
            print_ok(f"Loaded virtual device ID: {device_id}")
        except Exception as e:
            print_wrn(f"Failed to load virtual device config: {e}")

    scratch_dir = Path(__file__).parent.parent / "scratch"
    scratch_dir.mkdir(parents=True, exist_ok=True)

    while True:
        print_info("Querying Divoom community gallery API...")
        body = {
            "Command": "GetCategoryFileListV2",
            "Token": creds.token,
            "UserId": creds.user_id,
            "DeviceId": device_id,
            "Classify": classify,
            "FileSort": 1,   # Popular
            "FileType": 5,   # All
            "FileSize": 127, # All sizes
            "Version": 19,
            "StartNum": 1,
            "EndNum": args.limit * 2,  # Fetch slightly more in case some download fail
            "RefreshIndex": 0
        }
        if device_pw:
            body["DevicePassword"] = device_pw

        url = f"{BASE_URL}/GetCategoryFileListV2"
        payload = json.dumps(body).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=payload,
            headers={
                "Content-Type": "application/json; charset=utf-8",
                "Connection": "close",
                "User-Agent": "okhttp/4.12.0",
            },
            method="POST"
        )

        items_to_display = []

        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                resp_data = json.loads(resp.read().decode("utf-8"))
                if resp_data.get("ReturnCode") != 0:
                    print_err(f"GetCategoryFileListV2 failed: RC={resp_data.get('ReturnCode')} msg={resp_data.get('ReturnMessage')}")
                    if not args.loop:
                        sys.exit(1)
                else:
                    file_list = resp_data.get("FileList", [])
                    print_ok(f"Found {len(file_list)} items in the gallery.")
                    
                    # Select and download the top popular items up to limit
                    downloaded_count = 0
                    for item in file_list:
                        if downloaded_count >= args.limit:
                            break
                        
                        file_id = item.get("FileId")
                        file_name = item.get("FileName", "unnamed")
                        file_type = item.get("FileType")
                        
                        if not file_id:
                            continue
                            
                        print_info(f"Downloading {file_name!r} ({file_id})...")
                        dl_url = f"https://fin.divoom-gz.com/{file_id}"
                        try:
                            d_req = urllib.request.Request(dl_url, headers={"User-Agent": "okhttp/4.12.0"})
                            with urllib.request.urlopen(d_req, timeout=10) as d_resp:
                                file_bytes = d_resp.read()
                                if len(file_bytes) < 4:
                                    continue
                                    
                                magic = file_bytes[0]
                                print_ok(f"Downloaded {len(file_bytes)} bytes. Magic: {magic} (hex: {hex(magic)})")
                                
                                # Process magic bytes
                                extracted_gif = extract_gif_from_magic_43(file_bytes)
                                if extracted_gif:
                                    print_ok("Extracted valid GIF from Magic 43 payload.")
                                    gif_path = scratch_dir / f"extracted_{downloaded_count}.gif"
                                    gif_path.write_bytes(extracted_gif)
                                    items_to_display.append({"type": "gif", "path": str(gif_path), "name": file_name})
                                elif file_bytes.startswith(b"GIF89a") or file_bytes.startswith(b"GIF87a"):
                                    print_ok("Identified as direct standard GIF.")
                                    gif_path = scratch_dir / f"direct_{downloaded_count}.gif"
                                    gif_path.write_bytes(file_bytes)
                                    items_to_display.append({"type": "gif", "path": str(gif_path), "name": file_name})
                                else:
                                    # Native Divoom BIN file
                                    print_info("Identified as Divoom-native pre-compiled binary format.")
                                    bin_path = scratch_dir / f"native_{downloaded_count}.bin"
                                    bin_path.write_bytes(file_bytes)
                                    items_to_display.append({"type": "bin", "path": str(bin_path), "name": file_name, "bytes": file_bytes})
                                    
                                downloaded_count += 1
                        except Exception as dl_err:
                            print_wrn(f"Failed to download {file_name!r}: {dl_err}")
        except Exception as api_err:
            print_err(f"Gallery query failed: {api_err}")
            if not args.loop:
                sys.exit(1)

        print_ok(f"Preparation complete. Downloaded {len(items_to_display)} files successfully.")

        if args.dry_run:
            print_ok("Dry run enabled. Skipping physical BLE connection.")

        else:
            # Physical BLE display execution
            if len(items_to_display) == 0:
                print_wrn("No items downloaded to display.")
            elif not targets:
                print_wrn("No target devices configured; skipping push this cycle.")
            else:
                # Push the monthly-best set to every selected target (4.b/4.d).
                for target in targets:
                    await _push_items_to_target(target, args.name, items_to_display, logger)

        if not args.loop:
            break
        print_info(f"Sleeping for {interval} seconds until the next cycle...")
        await asyncio.sleep(interval)


async def _push_items_to_target(target_addr, name_substring, items_to_display, logger):
    """Connect to one device (by address, or by name when address is None) and
    push every downloaded artwork to it, then disconnect."""
    divoom = None
    try:
        device_name = None
        if not target_addr:
            print_info(f"Discovering BLE device with name containing {name_substring!r}...")
            ble_device, device_addr = await discovery.discover_device(name_substring=name_substring, address=None)
            if not ble_device:
                raise RuntimeError(f"No Divoom device found with name substring {name_substring!r}")
            target_addr = device_addr
            device_name = ble_device.name if hasattr(ble_device, "name") else None

        print_info(f"Connecting to BLE device at {target_addr}...")
        divoom = Divoom(mac=target_addr, logger=logger, use_ios_le_protocol=True, device_name=device_name)
        await divoom.connect()
        print_ok(f"Connected to {target_addr} successfully!")

        for idx, item in enumerate(items_to_display):
            print_info(f"[{target_addr}] Displaying item [{idx+1}/{len(items_to_display)}]: {item['name']!r} ({item['type']})")
            if item["type"] == "gif":
                success = await divoom.display.show_image(item["path"])
            elif item["type"] == "bin":
                success = await stream_raw_bin_payload(divoom, item["bytes"])
            else:
                success = False
            print_ok(f"Pushed {item['name']!r}") if success else print_err(f"Failed to push {item['name']!r}")

            if idx < len(items_to_display) - 1:
                print_info("Waiting 15 seconds before showing next artwork...")
                await asyncio.sleep(15.0)
    except Exception as ble_err:
        print_err(f"BLE Communication error for {target_addr}: {ble_err}")
    finally:
        if divoom and divoom.is_connected:
            await divoom.disconnect()
            print_info(f"Disconnected from {target_addr}.")

if __name__ == "__main__":
    try:
        asyncio.run(main_async())
    except KeyboardInterrupt:
        print_info("Exiting on user interrupt.")
