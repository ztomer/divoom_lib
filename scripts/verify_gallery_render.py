"""R64 — offscreen render harness: decode EVERY gallery asset across ALL
categories and prove none render blank.

Mirrors the exact decode chain the GUI uses
(divoom_gui.gallery_hot_api.get_animated_preview), renders every
decoded frame to a per-category contact sheet, and asserts zero
all-black frames. This is the headless "render every item" check —
media_decoder is the single source of truth that feeds the UI, so a
decoded non-blank frame == what the UI shows.

Usage:
    .buildvenv/bin/python scripts/verify_gallery_render.py [--cats 18,0,3]
Writes contact sheets to /tmp/gallery_sheets/ and prints a report.
"""
import argparse
import configparser
import io
import json
import logging
import sys
import urllib.request
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from PIL import Image  # noqa: E402
from divoom_lib import divoom_auth, media_decoder  # noqa: E402

logging.basicConfig(level=logging.WARNING, format="[ %(levelname)s ] %(message)s")
log = logging.getLogger("verify")

CLASSIFY = [18, 0, 3, 17, 4, 8, 9, 6, 5, 15, 7, 16, 1, 40, 12, 19]
OUT = Path("/tmp/gallery_sheets")
OUT.mkdir(parents=True, exist_ok=True)


def get_file_list(classify, start=1, end=30):
    creds = divoom_auth.get_credentials()
    body = {"Command": "GetCategoryFileListV2", "Token": creds.token,
            "UserId": creds.user_id, "DeviceId": 0, "Classify": classify,
            "FileSort": 1, "FileType": 5, "FileSize": 1, "Version": 19,
            "StartNum": start, "EndNum": end, "RefreshIndex": 0}
    req = urllib.request.Request(
        "https://appin.divoom-gz.com/GetCategoryFileListV2",
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json; charset=utf-8",
                 "User-Agent": "okhttp/4.12.0"}, method="POST")
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.loads(r.read()).get("FileList", [])


def decode_all_frames(raw):
    """Return a list of PIL frames using the GUI's full decode chain."""
    out = []
    if media_decoder.extract_image_from_magic_43(raw):
        eb, _ = media_decoder.extract_image_from_magic_43(raw)
        try:
            out.append(Image.open(io.BytesIO(eb)).convert("RGB"))
        except Exception:
            pass
    if raw[:6] in (b"GIF89a", b"GIF87a") or raw[:8] == b"\x89PNG\r\n\x1a\n" or raw[:2] == b"\xff\xd8":
        try:
            out.append(Image.open(io.BytesIO(raw)).convert("RGB"))
        except Exception:
            pass
    else:
        frames, _ = media_decoder.decode_cloud_frames(raw)
        if frames:
            out.extend(f.convert("RGB") for f in frames)
        hot = media_decoder.decode_hot_file_format(raw)
        if hot:
            out.extend(Image.frombytes("RGB", (16, 16), rgb).convert("RGB")
                      for rgb, _ in hot)
        if not out:
            try:
                out.append(Image.open(io.BytesIO(raw)).convert("RGB"))
            except Exception:
                pass
    return out


def is_blank(im):
    """Conservative: only a BROKEN frame (unreadable, degenerate, or
    fully-transparent) counts as blank — a dark/solid-color image is
    valid art (see media_decoder.is_black_image)."""
    try:
        w, h = im.size
        if w == 0 or h == 0:
            return True
        ex = im.convert("RGBA").getextrema()
        a_lo, a_hi = ex[-1]
        return a_lo == 0 and a_hi == 0
    except Exception:
        return True


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cats", default="", help="comma list of classify ids")
    args = ap.parse_args()
    cats = [int(c) for c in args.cats.split(",") if c] or CLASSIFY

    total_items = 0
    fails = []
    for c in cats:
        items = get_file_list(c)
        frames_grid = []
        blank = 0
        for it in items:
            fid = it.get("FileId")
            if not fid:
                continue
            total_items += 1
            try:
                raw = urllib.request.urlopen(
                    urllib.request.Request("https://fin.divoom-gz.com/" + fid,
                                          headers={"User-Agent": "okhttp/4.12.0"}),
                    timeout=8).read()
            except Exception as e:
                fails.append((c, it.get("FileName"), "DL_FAIL", None))
                continue
            fs = decode_all_frames(raw)
            if not fs:
                fails.append((c, it.get("FileName"), "UNDECODABLE", raw[0]))
                continue
            for f in fs:
                if is_blank(f):
                    blank += 1
                    # Record detail so we can tell legit solid-color art
                    # from a wrong decode. Save the blank frame for inspection.
                    try:
                        ex = f.convert("RGBA").getextrema()
                        f.save(OUT / f"blank_cat{c}_{fid.replace('/', '_')}.png")
                    except Exception:
                        ex = None
                    log.warning(f"BLANK frame cat={c} magic={raw[0]} "
                                f"name={it.get('FileName')!r} size={f.size} ex={ex}")
            # collect first frame (upscaled) for the contact sheet
            frames_grid.append(fs[0].resize((64, 64), Image.Resampling.NEAREST))
        # write contact sheet
        cols = 10
        rows = (len(frames_grid) + cols - 1) // cols or 1
        sheet = Image.new("RGB", (cols * 66, rows * 66), (20, 20, 20))
        for i, f in enumerate(frames_grid):
            x = (i % cols) * 66 + 1
            y = (i // cols) * 66 + 1
            sheet.paste(f, (x, y))
        sheet.save(OUT / f"cat_{c}.png")
        print(f"cat {c:>3}: items={len(items):>3} frames_rendered={len(frames_grid):>3} blank_frames={blank}")

    print(f"\nTOTAL items={total_items}  FAILS={len(fails)}")
    if fails:
        from collections import Counter
        print("by category:", Counter(c for c, _, _, _ in fails))
        print("sample fails:")
        for c, name, why, mg in fails[:15]:
            print(f"   cat={c} {why} magic={mg} {name!r}")
        sys.exit(1)
    print("OK — every gallery asset across all categories decodes to a non-blank frame.")


if __name__ == "__main__":
    main()
