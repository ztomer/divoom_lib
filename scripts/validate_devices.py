#!/usr/bin/env python3
"""On-device validation harness for real Divoom hardware.

Run this from a terminal that has macOS Bluetooth permission (the agent's
sandboxed shell can't). It connects to each device and cycles the full command
matrix slowly so you can watch the screens, recording per-step success/error to
test_reports/device_validation.json.

Usage:
    # discover everything nearby and validate all:
    python3 scripts/validate_devices.py --scan

    # or target specific devices by BLE address / UUID:
    python3 scripts/validate_devices.py --addresses AA:BB:..,CC:DD:..

    # or by name substring (e.g. your four units):
    python3 scripts/validate_devices.py --names Timoo,Tivoo,Ditoo,Pixoo

Options:
    --dwell 2.5     seconds to hold each visual step (so you can look)
    --report PATH   output json (default test_reports/device_validation.json)
    --quick         shorter cycles (skip the full 0..15 sweeps)

While it runs, note for each device: do brightness/colors change, do the 6 clock
dials look distinct, do VJ effects animate, and — important for the UI — the
HIGHEST visualizer/EQ index (step "viz N") that shows a real pattern.
"""

import argparse
import asyncio
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.append(str(ROOT))

from divoom_lib.divoom import Divoom              # noqa: E402
from divoom_lib.utils import discovery             # noqa: E402
from divoom_lib.utils import media_source          # noqa: E402


async def _run_step(results, label, coro, dwell):
    print(f"    → {label} ...", end=" ", flush=True)
    try:
        res = await coro
        ok = res is not False  # None/True/dict all count as "sent ok"
        results.append({"step": label, "ok": bool(ok), "error": None})
        print("ok" if ok else "returned False")
    except Exception as e:
        results.append({"step": label, "ok": False, "error": str(e)})
        print(f"ERROR: {e}")
    await asyncio.sleep(dwell)


async def validate_device(address, name, dwell, quick):
    print(f"\n=== {name or 'device'} ({address}) ===")
    entry = {"address": address, "name": name, "connected": False, "steps": []}
    dev = Divoom(mac=address, use_ios_le_protocol=False)
    try:
        await dev.connect()
        entry["connected"] = bool(dev.is_connected)
        print(f"  connected: {entry['connected']}")
    except Exception as e:
        entry["error"] = f"connect failed: {e}"
        print(f"  CONNECT FAILED: {e}")
        return entry

    steps = entry["steps"]

    # Brightness
    await _run_step(steps, "brightness 30", dev.device.set_brightness(30), dwell)
    await _run_step(steps, "brightness 100", dev.device.set_brightness(100), dwell)

    # Solid colors
    for cname, hexv in (("red", "FF0000"), ("green", "00FF00"), ("blue", "0000FF")):
        await _run_step(steps, f"light {cname}", dev.display.show_light(hexv, 100, True), dwell)

    # Clock dials (2.f) — 6 real built-in types
    for n in range(6):
        await _run_step(steps, f"clock dial {n}", dev.display.show_clock(clock=n), dwell)

    # VJ effects (2.d) — 16 named
    vj_range = range(0, 16, 4) if quick else range(16)
    for n in vj_range:
        await _run_step(steps, f"vj effect {n}", dev.display.show_effects(number=n), dwell)

    # Visualizer / EQ (2.c) — sweep to find the real count
    viz_range = range(0, 16, 2) if quick else range(16)
    for n in viz_range:
        await _run_step(steps, f"viz {n}", dev.display.show_visualization(number=n), dwell)

    # Image push (5.a/5.c/area 7) — the path the two recent bug fixes were on
    size = _guess_size(name)
    try:
        ticker = media_source.render_stock_ticker_frame(
            "BTC", {"price": 64000, "change": 1.0, "pct_change": 1.0}, size=size)
        await _run_step(steps, "image: ticker", dev.display.show_image(str(ticker)), dwell + 1)
    except Exception as e:
        steps.append({"step": "image: ticker", "ok": False, "error": str(e)})
    try:
        stats = media_source.get_system_stats()
        sysmon = media_source.render_system_stats_frame(stats, size=size)
        await _run_step(steps, "image: sysmon", dev.display.show_image(str(sysmon)), dwell + 1)
    except Exception as e:
        steps.append({"step": "image: sysmon", "ok": False, "error": str(e)})

    try:
        await dev.disconnect()
    except Exception:
        pass
    return entry


def _guess_size(name):
    n = (name or "").lower()
    if "pixoo" in n and "64" in n:
        return 64
    return 16


async def _resolve_targets(args):
    if args.addresses:
        return [(a.strip(), None) for a in args.addresses.split(",") if a.strip()]
    found = await discovery.discover_all_divoom_devices(timeout=float(args.scan_timeout))
    targets = []
    names = [s.strip().lower() for s in args.names.split(",")] if args.names else None
    for d in found:
        nm = d.get("name", "")
        if names and not any(s in (nm or "").lower() for s in names):
            continue
        targets.append((d.get("address"), nm))
    return targets


async def main_async(args):
    targets = await _resolve_targets(args)
    if not targets:
        print("No target devices found. Try --addresses or check the device names.")
        return 1
    print(f"Validating {len(targets)} device(s): "
          + ", ".join(f"{n or '?'}({a})" for a, n in targets))

    report = {"devices": [], "summary": {}}
    for address, name in targets:
        report["devices"].append(await validate_device(address, name, args.dwell, args.quick))

    total_steps = sum(len(d["steps"]) for d in report["devices"])
    ok_steps = sum(1 for d in report["devices"] for s in d["steps"] if s["ok"])
    report["summary"] = {
        "devices": len(report["devices"]),
        "connected": sum(1 for d in report["devices"] if d["connected"]),
        "steps": total_steps,
        "ok": ok_steps,
        "failed": total_steps - ok_steps,
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
    }

    out = Path(args.report)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"\nReport written to {out}")
    print(f"Summary: {report['summary']}")
    # Surface any failures prominently.
    for d in report["devices"]:
        fails = [s for s in d["steps"] if not s["ok"]]
        if fails or not d["connected"]:
            print(f"  ⚠️ {d['name'] or d['address']}: "
                  + ("not connected" if not d["connected"] else f"{len(fails)} step(s) failed"))
            for s in fails:
                print(f"      - {s['step']}: {s['error']}")
    return 0


def main():
    p = argparse.ArgumentParser(description="Validate Divoom commands on real hardware")
    g = p.add_mutually_exclusive_group()
    g.add_argument("--addresses", help="comma-separated BLE addresses/UUIDs")
    g.add_argument("--scan", action="store_true", help="discover devices nearby")
    p.add_argument("--names", help="comma-separated name substrings to filter a scan")
    p.add_argument("--scan-timeout", type=float, default=10.0)
    p.add_argument("--dwell", type=float, default=2.5, help="seconds per visual step")
    p.add_argument("--quick", action="store_true", help="shorter 0..15 sweeps")
    p.add_argument("--report", default=str(ROOT / "test_reports" / "device_validation.json"))
    args = p.parse_args()
    raise SystemExit(asyncio.run(main_async(args)))


if __name__ == "__main__":
    main()
