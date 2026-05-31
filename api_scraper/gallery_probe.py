#!/usr/bin/env python3
"""
Prototype scraper for the Divoom cloud gallery API.

Based on static analysis of the Divoom APK (com.divoom.Divoom_3.8.22-622).
See: apk/REVERSE_ENGINEERING_NOTES.md for full findings.

Usage:
    python3 api_scraper/gallery_probe.py [--classify N] [--sort N] [--limit N]

This script probes the `GetCategoryFileListV2` endpoint and:
  - Prints the HTTP status + ReturnCode
  - Dumps the first N items to stdout as JSON
  - Saves the full raw response to api_scraper/divoom_docs/raw_response.json
"""

import argparse
import json
import sys
import urllib.request
import urllib.error
from datetime import datetime
from pathlib import Path

# ---------------------------------------------------------------------------
# Constants from reverse engineering
# ---------------------------------------------------------------------------
BASE_URL = "https://appin.divoom-gz.com"   # International server
CDN_URL  = "https://fin.divoom-gz.com"     # File CDN (hypothesis)

ENDPOINT_GALLERY = "GetCategoryFileListV2"

# Classify values (from CloudClassifyModel.java)
CLASSIFY = {
    0:  "New",
    1:  "Default",
    3:  "Cartoon",
    4:  "Emoji",
    5:  "Everyday",
    6:  "Nature",
    7:  "Symbol",
    8:  "Pattern",
    9:  "Creative",
    12: "Photo",
    15: "Dawu",
    16: "Business",
    17: "Holiday",
    18: "Recommend",
    19: "Planet",
    20: "Expert",
    29: "FillGame",
    30: "PixelMatch",
    31: "Plant",
    32: "Animal",
    33: "Person",
    34: "Emoji2",
    35: "Food",
    36: "Others",
    40: "AI",
}

# FileSort values
SORT_POPULAR = 1
SORT_LATEST  = 0

# FileSize bitmask (127 = all sizes)
FILESIZE_ALL = 127


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


def build_request_body(classify: int, file_sort: int, start: int = 0, end: int = 20) -> dict:
    """
    Build the JSON body for GetCategoryFileListV2.
    Based on GetCloudBaseRequestV2.java + BaseRequestJson.java.
    Token=0, UserId=0 for unauthenticated (guest) access.
    """
    return {
        "Command":      ENDPOINT_GALLERY,
        "Token":        0,
        "UserId":       0,
        "DeviceId":     0,
        "Classify":     classify,
        "FileSort":     file_sort,
        "FileType":     0,
        "FileSize":     FILESIZE_ALL,
        "Version":      19,
        "StartNum":     start,
        "EndNum":       end,
        "RefreshIndex": 0,
    }


def post_json(command: str, body: dict) -> dict:
    """
    POST JSON to the Divoom cloud API.
    URL: https://appin.divoom-gz.com/<command>
    Content-Type: application/json; charset=utf-8
    No auth headers, no signing — plain POST as confirmed by OkHttpUtils.
    """
    url = f"{BASE_URL}/{command}"
    payload = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=payload,
        headers={
            "Content-Type": "application/json; charset=utf-8",
            "Connection":   "close",
            "User-Agent":   "okhttp/4.x",   # mimic OkHttp user-agent
        },
        method="POST",
    )
    print_info(f"POST {url}")
    print_info(f"Body: {json.dumps(body, indent=2)}")

    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            raw = resp.read().decode("utf-8")
            print_ok(f"HTTP {resp.status}")
            return {"http_status": resp.status, "raw": raw}
    except urllib.error.HTTPError as e:
        print_err(f"HTTP error: {e.code} {e.reason}")
        raw = e.read().decode("utf-8", errors="replace")
        return {"http_status": e.code, "raw": raw, "error": str(e)}
    except Exception as e:
        print_err(f"Request failed: {e}")
        return {"http_status": None, "raw": "", "error": str(e)}


def probe_gallery(classify: int, file_sort: int, limit: int, output_dir: Path) -> None:
    """Probe the gallery API and dump results."""
    classify_name = CLASSIFY.get(classify, f"Unknown({classify})")
    sort_name = "Popular" if file_sort == SORT_POPULAR else "Latest"
    print_info(f"Probing gallery: Classify={classify} ({classify_name}), Sort={file_sort} ({sort_name})")

    body = build_request_body(classify=classify, file_sort=file_sort, start=0, end=limit)
    result = post_json(ENDPOINT_GALLERY, body)

    raw = result.get("raw", "")
    http_status = result.get("http_status")

    if not raw:
        print_err("Empty response body")
        return

    # Save raw response
    output_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    raw_path = output_dir / f"raw_response_{classify}_{file_sort}_{ts}.json"
    raw_path.write_text(raw, encoding="utf-8")
    print_ok(f"Raw response saved to: {raw_path}")

    # Parse JSON
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        print_err(f"JSON parse error: {e}")
        print_err(f"Raw response (first 500 chars): {raw[:500]}")
        return

    return_code = data.get("ReturnCode", "N/A")
    return_msg  = data.get("ReturnMessage", "")
    file_list   = data.get("FileList", [])

    print()
    print(f"  ReturnCode:    {return_code}")
    print(f"  ReturnMessage: {return_msg}")
    print(f"  FileList len:  {len(file_list)}")
    print()

    if return_code != 0:
        print_wrn(f"Non-zero ReturnCode: {return_code} — {return_msg}")
        print_wrn("Full response keys: " + str(list(data.keys())))
        return

    print_ok(f"Success! Got {len(file_list)} items")
    print()

    for i, item in enumerate(file_list[:limit]):
        gallery_id = item.get("GalleryId", "?")
        file_id    = item.get("FileId", "?")
        file_name  = item.get("FileName", "?")
        like_cnt   = item.get("LikeCnt", 0)
        watch_cnt  = item.get("WatchCnt", 0)
        classify_v = item.get("Classify", "?")
        file_size  = item.get("FileSize", "?")
        user_name  = item.get("userName", "?")
        cdn_url    = f"{CDN_URL}/{file_id}" if file_id != "?" else "?"
        print(f"  [{i+1:02d}] GalleryId={gallery_id:>8}  Likes={like_cnt:>5}  Views={watch_cnt:>6}  "
              f"Size={file_size:<4}  User={user_name:<20}  Name={file_name}")
        print(f"       FileId={file_id}")
        print(f"       CDN(hyp)={cdn_url}")
        print()


def main():
    parser = argparse.ArgumentParser(description="Probe the Divoom cloud gallery API")
    parser.add_argument(
        "--classify", type=int, default=18,
        help="Classify integer (default: 18=Recommend). See REVERSE_ENGINEERING_NOTES.md for values."
    )
    parser.add_argument(
        "--sort", type=int, default=SORT_POPULAR,
        help="FileSort: 1=Popular (default), 0=Latest"
    )
    parser.add_argument(
        "--limit", type=int, default=10,
        help="Number of items to display (default: 10)"
    )
    parser.add_argument(
        "--all-categories", action="store_true",
        help="Probe all known Classify values and report which ones succeed"
    )
    parser.add_argument(
        "--output-dir", type=Path,
        default=Path(__file__).parent / "divoom_docs",
        help="Directory to save raw responses"
    )
    args = parser.parse_args()

    if args.all_categories:
        print_info("Probing all known Classify values...")
        results = {}
        for classify_int, classify_name in sorted(CLASSIFY.items()):
            body = build_request_body(classify=classify_int, file_sort=args.sort, start=0, end=5)
            result = post_json(ENDPOINT_GALLERY, body)
            raw = result.get("raw", "")
            try:
                data = json.loads(raw)
                rc = data.get("ReturnCode", -1)
                count = len(data.get("FileList", []))
                results[classify_int] = {"name": classify_name, "ReturnCode": rc, "count": count}
                status = "OK" if rc == 0 else f"ERR({rc})"
                print(f"  Classify={classify_int:>3} ({classify_name:<15}) → {status}, items={count}")
            except Exception as e:
                results[classify_int] = {"name": classify_name, "error": str(e)}
                print_err(f"  Classify={classify_int} ({classify_name}) → PARSE ERROR: {e}")
        print()
        print_ok("Scan complete")
        return

    probe_gallery(
        classify=args.classify,
        file_sort=args.sort,
        limit=args.limit,
        output_dir=args.output_dir,
    )


if __name__ == "__main__":
    main()
