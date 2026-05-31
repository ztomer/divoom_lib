#!/usr/bin/env python3
import sys
import json
import urllib.request
import urllib.error
import struct
from pathlib import Path

# Add parent directory to path so we can import divoom_auth
sys.path.append(str(Path(__file__).parent.parent / "api_scraper"))
import divoom_auth

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

def main():
    print_info("Obtaining credentials...")
    creds = divoom_auth.get_credentials()
    print_ok(f"Credentials loaded: UserId={creds.user_id}, Token={creds.token}")

    # Load virtual device info if available
    device_id = 0
    device_pw = 0
    device_cache_path = Path(__file__).parent.parent / "api_scraper" / "divoom_docs" / "virtual_device.json"
    if device_cache_path.exists():
        try:
            device_info = json.loads(device_cache_path.read_text(encoding="utf-8"))
            device_id = device_info.get("BluetoothDeviceId", 0)
            device_pw = device_info.get("DevicePassword", 0)
            print_ok(f"Loaded virtual device: DeviceId={device_id}, DevicePassword={device_pw}")
        except Exception as e:
            print_wrn(f"Failed to load virtual device: {e}")

    # Let's try to search multiple Classifications
    # Classify 18 (Recommend), Classify 0 (New/Default), Classify 3 (Cartoon), Classify 9 (Creative)
    classifications = [18, 0, 3, 9]
    magic_counts = {}
    magic_43_files = []
    direct_gif_files = []

    for classify in classifications:
        print_info(f"Querying Category {classify}...")
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
            "EndNum": 50,    # Top 50 of this category
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

        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                if data.get("ReturnCode") != 0:
                    print_err(f"API Error for Category {classify}: ReturnCode={data.get('ReturnCode')}")
                    continue
                
                file_list = data.get("FileList", [])
                print_ok(f"Received {len(file_list)} items for Category {classify}.")
                
                for item in file_list[:20]: # Check first 20 in each to save time/bandwidth
                    file_id = item.get("FileId")
                    file_name = item.get("FileName")
                    
                    if not file_id:
                        continue
                    
                    download_url = f"https://fin.divoom-gz.com/{file_id}"
                    try:
                        d_req = urllib.request.Request(
                            download_url,
                            headers={"User-Agent": "okhttp/4.12.0"}
                        )
                        with urllib.request.urlopen(d_req, timeout=10) as d_resp:
                            file_data = d_resp.read()
                            if len(file_data) < 4:
                                continue
                            
                            magic = file_data[0]
                            magic_counts[magic] = magic_counts.get(magic, 0) + 1
                            
                            if magic == 43:
                                print_ok(f"Found Magic 43: {file_name} ({file_id})")
                                magic_43_files.append((file_name, file_id))
                            elif file_data.startswith(b"GIF89a") or file_data.startswith(b"GIF87a"):
                                print_ok(f"Found Direct GIF: {file_name} ({file_id})")
                                direct_gif_files.append((file_name, file_id))
                    except Exception as e:
                        pass
        except Exception as e:
            print_err(f"Category {classify} failed: {e}")

    print_ok("Magic Byte Counts:")
    for magic, count in magic_counts.items():
        print(f"  Magic {magic} (hex: {hex(magic)}): {count}")

    print_ok(f"Total Magic 43 files found: {len(magic_43_files)}")
    print_ok(f"Total Direct GIF files found: {len(direct_gif_files)}")

if __name__ == "__main__":
    main()
