"""
mitmproxy addon: capture_divoom.py

Intercepts all HTTP(S) traffic to *.divoom-gz.com and logs it with full
headers and body. Run with:

    mitmdump -s api_scraper/capture_divoom.py --listen-port 8080

This script:
  - Logs every Divoom API request/response to stdout with formatting
  - Saves each request+response pair to api_scraper/divoom_docs/captured/<timestamp>_<command>.json
  - Detects the GetCategoryFileListV2 command and highlights it

Setup (Android device):
  1. Run this script on your Mac:
       mitmdump -s api_scraper/capture_divoom.py --listen-port 8080
  2. On Android: Settings → Wi-Fi → (hold network) → Modify → Advanced → Proxy → Manual
       Host: 192.168.0.147   Port: 8080
  3. Visit http://mitm.it on Android browser → download and install CA cert
       (Settings → Security → Install from storage)
  4. Open the Divoom app → tap Gallery → browse Monthly Best / Hall of Fame / etc.
  5. Watch this terminal for captured requests. Press Ctrl+C when done.
"""

import json
import os
import re
from datetime import datetime
from pathlib import Path

# Output directory for saved captures
CAPTURES_DIR = Path(__file__).parent / "divoom_docs" / "captured"
CAPTURES_DIR.mkdir(parents=True, exist_ok=True)

DIVOOM_HOST_RE = re.compile(r"divoom-gz\.com", re.IGNORECASE)

HIGHLIGHT = "\033[92m"  # green
DIM       = "\033[2m"
BOLD      = "\033[1m"
RESET     = "\033[0m"
YELLOW    = "\033[93m"
RED       = "\033[91m"
CYAN      = "\033[96m"


def _safe_json(data: bytes) -> dict | str:
    try:
        return json.loads(data.decode("utf-8", errors="replace"))
    except Exception:
        return data.decode("utf-8", errors="replace")[:2000]


def request(flow):
    host = flow.request.pretty_host
    if not DIVOOM_HOST_RE.search(host):
        return

    path    = flow.request.path
    method  = flow.request.method
    headers = dict(flow.request.headers)
    body    = flow.request.content

    body_parsed = _safe_json(body) if body else {}

    command = ""
    if isinstance(body_parsed, dict):
        command = body_parsed.get("Command", "")
        if not command:
            # Command is sometimes embedded in the URL path
            command = path.lstrip("/").split("?")[0]

    is_gallery = "GetCategoryFileListV2" in path or command == "GetCategoryFileListV2"
    marker = f"{HIGHLIGHT}{BOLD}★ GALLERY ★{RESET} " if is_gallery else ""

    print()
    print(f"{BOLD}{CYAN}{'='*70}{RESET}")
    print(f"{marker}{BOLD}→ {method} https://{host}{path}{RESET}")
    print(f"{DIM}  Time: {datetime.now().strftime('%H:%M:%S.%f')}{RESET}")
    print()
    print(f"{YELLOW}  Headers:{RESET}")
    for k, v in headers.items():
        if k.lower() in {"content-type", "user-agent", "connection", "authorization",
                          "cookie", "x-forwarded-for", "x-real-ip", "token", "accept"}:
            print(f"    {k}: {v}")
    print()
    print(f"{YELLOW}  Body:{RESET}")
    print("   ", json.dumps(body_parsed, indent=4, ensure_ascii=False)
          if isinstance(body_parsed, dict) else repr(body_parsed))

    # Attach context for response handler
    flow.request._divoom_command = command
    flow.request._divoom_body    = body_parsed
    flow.request._divoom_headers = headers
    flow.request._divoom_path    = path
    flow.request._divoom_host    = host


def response(flow):
    host = flow.request.pretty_host
    if not DIVOOM_HOST_RE.search(host):
        return

    status  = flow.response.status_code
    rbody   = flow.response.content
    resp_parsed = _safe_json(rbody) if rbody else {}

    command = getattr(flow.request, "_divoom_command", flow.request.path.lstrip("/"))
    rc = resp_parsed.get("ReturnCode", "?") if isinstance(resp_parsed, dict) else "?"
    items = len(resp_parsed.get("FileList", [])) if isinstance(resp_parsed, dict) else 0

    color = HIGHLIGHT if rc == 0 else RED
    print()
    print(f"  {color}← HTTP {status}  ReturnCode={rc}  FileList items={items}{RESET}")
    if isinstance(resp_parsed, dict) and rc != 0:
        print(f"  {RED}  Message: {resp_parsed.get('ReturnMessage', '')}{RESET}")
    if items > 0:
        first = resp_parsed["FileList"][0]
        print(f"  {HIGHLIGHT}  First item: GalleryId={first.get('GalleryId')}  "
              f"FileId={first.get('FileId')}  Likes={first.get('LikeCnt')}{RESET}")

    # Save to file
    ts = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    safe_cmd = re.sub(r"[^a-zA-Z0-9_\-]", "_", command)[:60]
    out_path = CAPTURES_DIR / f"{ts}_{safe_cmd}.json"
    capture = {
        "timestamp":      datetime.now().isoformat(),
        "host":           getattr(flow.request, "_divoom_host", host),
        "path":           getattr(flow.request, "_divoom_path", flow.request.path),
        "method":         flow.request.method,
        "request_headers": getattr(flow.request, "_divoom_headers", {}),
        "request_body":   getattr(flow.request, "_divoom_body", {}),
        "response_status": status,
        "response_body":  resp_parsed,
    }
    out_path.write_text(json.dumps(capture, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"  {DIM}  Saved: {out_path}{RESET}")
