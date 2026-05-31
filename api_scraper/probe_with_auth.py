#!/usr/bin/env python3
import json
import urllib.request
import urllib.error
import sys
from pathlib import Path

# Add parent directory to path so we can import divoom_auth
sys.path.append(str(Path(__file__).parent))
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
    device_cache_path = Path(__file__).parent / "divoom_docs" / "virtual_device.json"
    if device_cache_path.exists():
        try:
            device_info = json.loads(device_cache_path.read_text(encoding="utf-8"))
            device_id = device_info.get("BluetoothDeviceId", 0)
            device_pw = device_info.get("DevicePassword", 0)
            print_ok(f"Loaded virtual device: DeviceId={device_id}, DevicePassword={device_pw}")
        except Exception as e:
            print_wrn(f"Failed to load virtual device: {e}")

    # Let's try GetCategoryFileListV2 with valid credentials and DeviceId
    body = {
        "Command": "GetCategoryFileListV2",
        "Token": creds.token,
        "UserId": creds.user_id,
        "DeviceId": device_id,
        "Classify": 18,  # Recommend
        "FileSort": 1,   # Popular
        "FileType": 5,
        "FileSize": 127, # All sizes
        "Version": 19,
        "StartNum": 1,
        "EndNum": 20,
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

    print_info(f"POST {url}")
    print_info(f"Body: {json.dumps(body, indent=2)}")

    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            raw = resp.read().decode("utf-8")
            print_ok(f"HTTP {resp.status}")
            data = json.loads(raw)
            print_ok(f"Response (truncated if large): {json.dumps(data, indent=2)[:2000]}")
            
            # Save a sample of the response to check
            sample_path = Path(__file__).parent / "divoom_docs" / "category_list_sample.json"
            sample_path.write_text(raw, encoding="utf-8")
            print_ok(f"Saved response to {sample_path}")
    except Exception as e:
        print_err(f"Request failed: {e}")

if __name__ == "__main__":
    main()
