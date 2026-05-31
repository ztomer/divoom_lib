#!/usr/bin/env python3
import json
import urllib.request
import urllib.error
import sys
import time
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

    utc_time = divoom_auth._get_server_utc()
    utc_str = str(utc_time)
    utc_encrypt = divoom_auth._hmac_md5(utc_str)

    # Let's register device type 9 (Ditoo) or type 2 (Timebox Evo / Timoo-light-4)
    # The summary mentions "virtual BLE device (e.g., Ditoo type 9)"
    device_type = 9
    device_subtype = 0

    body = {
        "Command": "BlueDevice/NewDevice",
        "Token": creds.token,
        "UserId": creds.user_id,
        "UTC": utc_str,
        "UTCEncrypt": utc_encrypt,
        "Type": device_type,
        "SubType": device_subtype
    }

    url = f"{BASE_URL}/BlueDevice/NewDevice"
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
            print_ok(f"Response: {json.dumps(data, indent=2)}")
            
            # Save the registered device credentials if successful
            if data.get("ReturnCode") == 0:
                dev_id = data.get("BluetoothDeviceId")
                dev_pw = data.get("DevicePassword")
                print_ok(f"Successfully registered virtual BLE device!")
                print_ok(f"BluetoothDeviceId: {dev_id}")
                print_ok(f"DevicePassword:    {dev_pw}")
                
                # Write to a device cache file so we can reuse it
                device_cache_path = Path(__file__).parent / "divoom_docs" / "virtual_device.json"
                device_cache_path.write_text(json.dumps({
                    "BluetoothDeviceId": dev_id,
                    "DevicePassword": dev_pw,
                    "Type": device_type,
                    "SubType": device_subtype,
                    "registered_at": int(time.time())
                }, indent=2), encoding="utf-8")
                print_info(f"Virtual device saved to {device_cache_path}")
            else:
                print_err(f"Registration failed: {data.get('ReturnMessage')}")
    except Exception as e:
        print_err(f"Request failed: {e}")

if __name__ == "__main__":
    main()
