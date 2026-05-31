#!/usr/bin/env python3
"""
analyze_captures.py — Post-capture analysis tool.

After running the mitmproxy capture, run this to:
  1. Find all captured GetCategoryFileListV2 requests
  2. Show the exact headers and body that worked
  3. Generate a ready-to-use Python request snippet

Usage:
    python3 api_scraper/analyze_captures.py
"""

import json
import sys
from pathlib import Path


def print_info(message):
    print(f"[ ==> ] {message}")

def print_wrn(message):
    print(f"[ Wrn ] {message}")

def print_err(message):
    print(f"[ Err ] {message}")

def print_ok(message):
    print(f"[ Ok  ] {message}")


CAPTURES_DIR = Path(__file__).parent / "divoom_docs" / "captured"


def load_captures():
    if not CAPTURES_DIR.exists():
        print_err(f"No captures directory found: {CAPTURES_DIR}")
        print_err("Run 'mitmdump -s api_scraper/capture_divoom.py' first.")
        sys.exit(1)
    files = sorted(CAPTURES_DIR.glob("*.json"))
    if not files:
        print_wrn("No capture files found yet.")
        sys.exit(0)
    return files


def analyze():
    files = load_captures()
    print_info(f"Found {len(files)} captured request(s) in {CAPTURES_DIR}")
    print()

    gallery_captures = []
    all_commands = set()

    for f in files:
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
        except Exception as e:
            print_wrn(f"Could not parse {f.name}: {e}")
            continue

        path = data.get("path", "")
        rc   = data.get("response_body", {}).get("ReturnCode", -1)
        cmd  = data.get("request_body", {}).get("Command", path.lstrip("/"))
        all_commands.add(cmd)

        if "GetCategoryFileListV2" in path or cmd == "GetCategoryFileListV2":
            gallery_captures.append((f, data, rc))

    print_info(f"All captured commands: {sorted(all_commands)}")
    print()

    if not gallery_captures:
        print_wrn("No GetCategoryFileListV2 captures found.")
        print_wrn("Open the Divoom app → Gallery → browse some categories, then re-run.")
        return

    # Find a successful one (ReturnCode == 0) or show the best one we have
    successful = [(f, d, rc) for f, d, rc in gallery_captures if rc == 0]
    candidates = successful or gallery_captures

    print_ok(f"Found {len(gallery_captures)} GetCategoryFileListV2 capture(s), "
             f"{len(successful)} successful (RC=0)")
    print()

    # Show the first successful one in detail
    f, data, rc = candidates[0]
    print(f"{'='*60}")
    print(f"Capture file: {f.name}")
    print(f"Timestamp:    {data.get('timestamp')}")
    print(f"ReturnCode:   {rc}")
    print()

    req_headers = data.get("request_headers", {})
    req_body    = data.get("request_body", {})
    resp_body   = data.get("response_body", {})
    file_list   = resp_body.get("FileList", [])

    print("=== REQUEST HEADERS ===")
    for k, v in req_headers.items():
        print(f"  {k}: {v}")
    print()

    print("=== REQUEST BODY ===")
    print(json.dumps(req_body, indent=2))
    print()

    if file_list:
        print("=== FIRST RESPONSE ITEM ===")
        print(json.dumps(file_list[0], indent=2))
        print()
        # Construct CDN URL hypotheses
        file_id = file_list[0].get("FileId", "")
        print("=== CDN URL CANDIDATES ===")
        print(f"  https://fin.divoom-gz.com/{file_id}")
        print(f"  http://f.divoom-gz.com/{file_id}")
    print()

    # Generate a ready-to-use Python snippet
    print("=== GENERATED PYTHON SNIPPET ===")
    print("```python")
    print("import json, urllib.request")
    print()
    print("headers = {")
    important = {"content-type", "user-agent", "connection", "authorization",
                 "cookie", "token", "accept", "x-app-version"}
    for k, v in req_headers.items():
        if k.lower() in important:
            print(f'    "{k}": "{v}",')
    print("}")
    print()
    print("body = ", end="")
    print(json.dumps(req_body, indent=4))
    print()
    host_val = data.get("host", "appin.divoom-gz.com")
    path_val = data.get("path", "/GetCategoryFileListV2")
    print(f'url = "https://{host_val}{path_val}"')
    print("req = urllib.request.Request(url, json.dumps(body).encode(), headers, method='POST')")
    print("with urllib.request.urlopen(req, timeout=15) as r:")
    print("    response = json.loads(r.read())")
    print("    print(response['ReturnCode'], len(response.get('FileList', [])))")
    print("```")


if __name__ == "__main__":
    analyze()
