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

    # Let's try GetCategoryFileListV2
    body = {
        "Command": "GetCategoryFileListV2",
        "Token": creds.token,
        "UserId": creds.user_id,
        "DeviceId": device_id,
        "Classify": 18,  # Recommend
        "FileSort": 1,   # Popular
        "FileType": 5,   # All
        "FileSize": 127, # All sizes
        "Version": 19,
        "StartNum": 1,
        "EndNum": 30,    # Top 30
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
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            if data.get("ReturnCode") != 0:
                print_err(f"API Error: ReturnCode={data.get('ReturnCode')} Message={data.get('ReturnMessage')}")
                return
            
            file_list = data.get("FileList", [])
            print_ok(f"Received {len(file_list)} items.")
            
            extracted_count = 0
            for idx, item in enumerate(file_list):
                file_id = item.get("FileId")
                file_name = item.get("FileName")
                file_type = item.get("FileType")
                like_cnt = item.get("LikeCnt")
                
                print_info(f"[{idx+1}] Name: {file_name!r} | FileId: {file_id} | FileType: {file_type} | Likes: {like_cnt}")
                
                if not file_id:
                    continue
                
                # Download file
                download_url = f"https://fin.divoom-gz.com/{file_id}"
                try:
                    d_req = urllib.request.Request(
                        download_url,
                        headers={"User-Agent": "okhttp/4.12.0"}
                    )
                    with urllib.request.urlopen(d_req, timeout=10) as d_resp:
                        file_data = d_resp.read()
                        
                        if len(file_data) < 4:
                            print_wrn(f"  Downloaded data too small: {len(file_data)} bytes")
                            continue
                            
                        magic = file_data[0]
                        print_info(f"  Bytes: {len(file_data)} | Magic: {magic} (hex: {hex(magic)}) | Header: {file_data[:10].hex()}")
                        
                        if magic == 43: # 0x2b
                            print_ok("  Detected Magic 43 (0x2b) - GIF container!")
                            # Try to extract the GIF
                            try:
                                text_len = struct.unpack("<I", file_data[6:10])[0]
                                text_start = 10
                                text_end = text_start + text_len
                                text_content = file_data[text_start:text_end]
                                
                                gif_len_offset = text_end
                                gif_len = struct.unpack("<I", file_data[gif_len_offset:gif_len_offset+4])[0]
                                gif_start = gif_len_offset + 4
                                gif_end = gif_start + gif_len
                                
                                gif_data = file_data[gif_start:gif_end]
                                if gif_data.startswith(b"GIF89a") or gif_data.startswith(b"GIF87a"):
                                    print_ok(f"  Successfully extracted valid GIF ({len(gif_data)} bytes)!")
                                    # Save it
                                    clean_name = "".join([c if c.isalnum() else "_" for c in file_name])
                                    out_path = Path(__file__).parent.parent / "scratch" / f"extracted_{clean_name}_{idx+1}.gif"
                                    out_path.write_bytes(gif_data)
                                    print_ok(f"  Saved GIF to {out_path}")
                                    extracted_count += 1
                                else:
                                    print_err(f"  Extracted data header invalid: {gif_data[:10]}")
                            except Exception as parse_err:
                                print_err(f"  Failed parsing Magic 43 container: {parse_err}")
                        elif magic == 26:
                            print_info("  Detected Magic 26 (0x1a) - Obfuscated/Compressed")
                        elif file_data.startswith(b"GIF89a") or file_data.startswith(b"GIF87a"):
                            print_ok("  Detected Magic - Direct GIF!")
                            clean_name = "".join([c if c.isalnum() else "_" for c in file_name])
                            out_path = Path(__file__).parent.parent / "scratch" / f"direct_{clean_name}_{idx+1}.gif"
                            out_path.write_bytes(file_data)
                            print_ok(f"  Saved direct GIF to {out_path}")
                            extracted_count += 1
                except Exception as dl_err:
                    print_err(f"  Download failed: {dl_err}")
            
            print_ok(f"Finished. Extracted {extracted_count} GIFs.")
            
    except Exception as e:
        print_err(f"Request failed: {e}")

if __name__ == "__main__":
    main()
