#!/usr/bin/env python3
import json
import urllib.request
from pathlib import Path

def print_info(message):
    print(f"[ ==> ] {message}")

def print_ok(message):
    print(f"[ Ok  ] {message}")

def print_err(message):
    print(f"[ Err ] {message}")

def main():
    file_id = "group1/M00/1E/11/eEwpPWRHwySESJoKAAAAAEnILhs8539141"
    cdn_urls = [
        f"https://fin.divoom-gz.com/{file_id}",
        f"http://f.divoom-gz.com/{file_id}",
    ]

    for url in cdn_urls:
        print_info(f"Trying to download from: {url}")
        try:
            req = urllib.request.Request(
                url,
                headers={
                    "User-Agent": "okhttp/4.12.0",
                }
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = resp.read()
                print_ok(f"Successfully downloaded {len(data)} bytes!")
                print_info(f"First 20 bytes (hex): {data[:20].hex()}")
                print_info(f"First 20 bytes (ASCII/repr): {repr(data[:20])}")
                
                # Check for magic bytes
                if data.startswith(b"GIF89a") or data.startswith(b"GIF87a"):
                    print_ok("Detected format: GIF image")
                    suffix = ".gif"
                elif data.startswith(b"PK\x03\x04"):
                    print_ok("Detected format: ZIP file")
                    suffix = ".zip"
                elif b"ezip" in data[:100].lower():
                    print_ok("Detected format: Ezip / Divoom Animation")
                    suffix = ".ezip"
                else:
                    print_ok("Detected format: Unknown custom bytes")
                    suffix = ".bin"

                out_path = Path(__file__).parent / "divoom_docs" / f"test_download{suffix}"
                out_path.write_bytes(data)
                print_ok(f"Saved to {out_path}")
                break
        except Exception as e:
            print_err(f"Failed to download from {url}: {e}")

if __name__ == "__main__":
    main()
