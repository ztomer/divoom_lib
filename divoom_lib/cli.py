#!/usr/bin/env python3
"""
divoom-control CLI — command-line interface for the divoom_lib.

Usage:
    divoom-control scan [--timeout SECONDS]
    divoom-control capabilities [--mac AA:BB:CC:DD:EE:FF]
    divoom-control set-volume N  [--mac ...]
    divoom-control set-brightness N [--mac ...]
    divoom-control set-radio FREQ  [--mac ...]   (e.g. 875 = 87.5 MHz)
    divoom-control set-alarm HH:MM [--mac ...]
    divoom-control push-image PATH  [--mac ...]
    divoom-control push-gif PATH    [--mac ...]
    divoom-control pair --mac ... --type TivooMax
    divoom-control identify

A thin wrapper over the lib — it does connect / disconnect + one operation,
then exits. The goal is to be scriptable from cron, the menubar, or
shell pipelines. Use the GUI for interactive use.

Design notes:
- No argparse tree that requires every command to be registered; the
  top-level dispatcher does the routing. New commands are easy to add.
- All commands log to stderr; results print to stdout (so they can be piped).
- Exit codes: 0 = success, 1 = runtime error, 2 = usage error.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
from pathlib import Path
from typing import Any, Awaitable, Callable

from divoom_lib import Divoom
from divoom_lib.models.capabilities import (
    DEVICE_CAPABILITIES,
    DeviceRegistry,
)


# ── Argument parsing ───────────────────────────────────────────────────


def build_parser() -> argparse.ArgumentParser:
    # Shared options that should also be accepted AFTER the subcommand.
    # `parents=` makes argparse attach the same args to the top-level
    # parser (where they're available as `args.mac` etc.) — argparse
    # allows parent-parser flags to appear before or after the
    # subcommand position, so users can write either order.
    shared = argparse.ArgumentParser(add_help=False)
    shared.add_argument("--mac", help="Target device MAC (default: first discovered).")
    shared.add_argument("--timeout", type=float, default=10.0,
                        help="BLE scan timeout in seconds (default: 10).")
    shared.add_argument("--type", dest="device_type",
                        help="Explicit device_type (overrides registry).")
    shared.add_argument("--json", action="store_true",
                        help="Output JSON instead of human-readable text.")
    shared.add_argument("--verbose", "-v", action="store_true",
                        help="Verbose logging.")

    p = argparse.ArgumentParser(
        prog="divoom-control",
        description="Command-line interface for the divoom_lib.",
        parents=[shared],
    )
    sub = p.add_subparsers(dest="command", required=True)

    sub.add_parser("scan", parents=[shared], help="Scan for nearby Divoom devices.")
    sub.add_parser("capabilities", parents=[shared], help="Print the active device's capabilities.")
    sub.add_parser("identify", parents=[shared], help="Print raw BLE manufacturer_data for a new device, for fingerprinting.")

    # SETTERS (require a value)
    p_vol = sub.add_parser("set-volume", parents=[shared], help="Set volume (0-15).")
    p_vol.add_argument("value", type=int)

    p_bri = sub.add_parser("set-brightness", parents=[shared], help="Set brightness (0-100).")
    p_bri.add_argument("value", type=int)

    p_fm = sub.add_parser("set-radio", parents=[shared], help="Set FM frequency (MHz × 10, e.g. 875 = 87.5).")
    p_fm.add_argument("freq_x10", type=int)

    p_al = sub.add_parser("set-alarm", parents=[shared], help="Set a one-shot alarm at HH:MM.")
    p_al.add_argument("time", help="HH:MM (24h)")

    p_img = sub.add_parser("push-image", parents=[shared], help="Push a local image to the device.")
    p_img.add_argument("path", type=Path)

    p_gif = sub.add_parser("push-gif", parents=[shared], help="Push a local animated GIF.")
    p_gif.add_argument("path", type=Path)

    # REGISTRY — pair reuses the shared --mac and --type, both required
    # at the handler level (see cmd_pair). Defining them again here would
    # conflict with the inherited definitions.
    sub.add_parser("pair", parents=[shared], help="Pair a MAC address with a device type (saves to registry).")
    return p


# ── Helpers ───────────────────────────────────────────────────────────


def _print(data: Any, *, as_json: bool = False) -> None:
    if as_json:
        if isinstance(data, (list, dict)):
            print(json.dumps(data, indent=2, default=str))
        else:
            print(json.dumps({"result": str(data)}, indent=2))
    else:
        if isinstance(data, list):
            for item in data:
                print(item)
        elif isinstance(data, dict):
            for k, v in data.items():
                print(f"{k}: {v}")
        else:
            print(data)


def _err(msg: str, code: int = 1) -> None:
    print(msg, file=sys.stderr)
    sys.exit(code)


async def _resolve_device(args: argparse.Namespace) -> tuple[Divoom, str]:
    """Connect to the requested device and return (Divoom instance, MAC)."""
    if args.command == "pair" or args.command == "identify":
        # These commands don't need a connected device.
        return None, (args.mac or "")
    mac = args.mac
    device_name = None
    if not mac:
        # Auto-discover the first Divoom device.
        from bleak import BleakScanner
        from divoom_lib.utils.discovery import discover_all_divoom_devices
        results = await discover_all_divoom_devices(timeout=args.timeout)
        if not results:
            _err("no Divoom devices found", 1)
        mac = results[0]["address"]
        device_name = results[0].get("name")

    kwargs: dict = {"mac": mac, "device_type": args.device_type}
    # Try to pass the manufacturer_data from the scan if we have it.
    if device_name:
        kwargs["device_name"] = device_name
    divoom = Divoom(**kwargs)
    await divoom.connect()
    return divoom, mac


# ── Commands ──────────────────────────────────────────────────────────


async def cmd_scan(args: argparse.Namespace) -> int:
    from divoom_lib.utils.discovery import discover_all_divoom_devices
    results = await discover_all_divoom_devices(timeout=args.timeout)
    if args.json:
        _print(results, as_json=True)
    else:
        if not results:
            print("(no Divoom devices found)")
        for r in results:
            print(f"{r['address']}  {r['name']}")
    return 0


async def cmd_capabilities(args: argparse.Namespace) -> int:
    d, mac = await _resolve_device(args)
    try:
        caps = d.capabilities
        if args.json:
            _print({
                "mac": mac,
                "panel_resolution": caps.panel_resolution,
                "has_fm": caps.has_fm,
                "has_sd": caps.has_sd,
                "has_scoreboard": caps.has_scoreboard,
                "has_anim_8b": caps.has_anim_8b,
                "has_orientation": caps.has_orientation,
                "has_screen_mirror": caps.has_screen_mirror,
                "has_alarm": caps.has_alarm,
                "has_sleep": caps.has_sleep,
                "has_weather": caps.has_weather,
                "has_mic": caps.has_mic,
                "notes": list(caps.notes),
            }, as_json=True)
        else:
            print(f"Device: {mac}")
            print(f"  panel_resolution: {caps.panel_resolution}×{caps.panel_resolution}")
            print(f"  has_fm:           {caps.has_fm}")
            print(f"  has_sd:           {caps.has_sd}")
            print(f"  has_scoreboard:   {caps.has_scoreboard}")
            print(f"  has_anim_8b:      {caps.has_anim_8b}")
            print(f"  has_orientation:  {caps.has_orientation}")
            print(f"  has_screen_mirror:{caps.has_screen_mirror}")
            print(f"  has_alarm:        {caps.has_alarm}")
            print(f"  has_sleep:        {caps.has_sleep}")
            print(f"  has_weather:      {caps.has_weather}")
            print(f"  has_mic:          {caps.has_mic}")
            if caps.notes:
                print(f"  notes: {'; '.join(caps.notes)}")
        return 0
    finally:
        if d is not None:
            await d.disconnect()


async def cmd_set_volume(args: argparse.Namespace) -> int:
    if not (0 <= args.value <= 15):
        _err("volume must be 0..15", 2)
    d, mac = await _resolve_device(args)
    try:
        ok = await d.music.set_volume(args.value)
        _print(f"set volume to {args.value}/15 (ok={ok})", as_json=args.json)
        return 0 if ok else 1
    finally:
        await d.disconnect()


async def cmd_set_brightness(args: argparse.Namespace) -> int:
    if not (0 <= args.value <= 100):
        _err("brightness must be 0..100", 2)
    d, mac = await _resolve_device(args)
    try:
        ok = await d.device.set_brightness(args.value)
        _print(f"set brightness to {args.value}% (ok={ok})", as_json=args.json)
        return 0 if ok else 1
    finally:
        await d.disconnect()


async def cmd_set_radio(args: argparse.Namespace) -> int:
    d, mac = await _resolve_device(args)
    try:
        if not d.capabilities.has_fm:
            _err(f"device {mac} has no FM radio (capabilities.has_fm=False)", 1)
        ok = await d.radio.set_radio_frequency(args.freq_x10)
        mhz = args.freq_x10 / 10.0
        _print(f"tuned FM to {mhz:.1f} MHz (ok={ok})", as_json=args.json)
        return 0 if ok else 1
    finally:
        await d.disconnect()


async def cmd_set_alarm(args: argparse.Namespace) -> int:
    """Set alarm 0 to HH:MM on every day (127 = all days).
    Note: a full alarm editor is the GUI's job; this is the scriptable path."""
    try:
        hh, mm = args.time.split(":")
        hh, mm = int(hh), int(mm)
    except ValueError:
        _err("time must be HH:MM (24h)", 2)
    d, mac = await _resolve_device(args)
    try:
        if not d.capabilities.has_alarm:
            _err(f"device {mac} has no alarm (capabilities.has_alarm=False)", 1)
        # Signature: set_alarm(alarm_index, status, hour, minute, week, mode, trigger_mode, fm_freq, volume)
        # week=127 = all days, mode=0=default, trigger_mode=0=default, fm_freq=0=off, volume=0=default
        ok = await d.alarm.set_alarm(0, 1, hh, mm, 127, 0, 0)
        _print(f"set alarm 0 to {hh:02d}:{mm:02d} every day (ok={ok})", as_json=args.json)
        return 0 if ok else 1
    finally:
        await d.disconnect()


async def cmd_push_image(args: argparse.Namespace) -> int:
    path: Path = args.path
    if not path.exists():
        _err(f"file not found: {path}", 2)
    d, mac = await _resolve_device(args)
    try:
        ok = await d.display.show_image(str(path))
        _print(f"pushed {path.name} to {mac} (ok={ok})", as_json=args.json)
        return 0 if ok else 1
    finally:
        await d.disconnect()


async def cmd_push_gif(args: argparse.Namespace) -> int:
    path: Path = args.path
    if not path.exists():
        _err(f"file not found: {path}", 2)
    d, mac = await _resolve_device(args)
    try:
        ok = await d.display.show_image(str(path))
        _print(f"pushed animated {path.name} to {mac} (ok={ok})", as_json=args.json)
        return 0 if ok else 1
    finally:
        await d.disconnect()


async def cmd_pair(args: argparse.Namespace) -> int:
    """Save MAC → device_type to the per-install registry."""
    if not args.mac:
        _err("--mac is required for `pair`", 2)
    if not args.device_type:
        _err("--type is required for `pair`", 2)
    if args.device_type not in DEVICE_CAPABILITIES:
        _err(f"unknown device_type {args.device_type!r}; "
             f"valid: {sorted(DEVICE_CAPABILITIES.keys())}", 2)
    reg = DeviceRegistry()
    reg.register(args.mac, args.device_type)
    if args.json:
        _print({"registered": args.mac, "device_type": args.device_type}, as_json=True)
    else:
        print(f"registered {args.mac} → {args.device_type}")
        print(f"registry file: {reg.path}")
    return 0


async def cmd_identify(args: argparse.Namespace) -> int:
    """Print the raw BLE manufacturer_data for a device. Used to populate
    the ADVERTISED_FINGERPRINTS table as the user identifies new devices."""
    from bleak import BleakScanner
    timeout = args.timeout
    print(f"Scanning for {timeout}s...", file=sys.stderr)
    # Use the callback API so we get the full AdvertisementData.
    found = {}
    def cb(device, adv):
        if adv.manufacturer_data:
            found[device.address] = (device.name, adv.manufacturer_data, adv.service_uuids)
    scanner = BleakScanner(detection_callback=cb)
    await scanner.start()
    import asyncio as _aio
    await _aio.sleep(timeout)
    await scanner.stop()

    if not found:
        _err("no devices with manufacturer_data found", 1)

    if args.json:
        out = {
            addr: {"name": name, "manufacturer_data": {hex(k): v.hex() for k, v in md.items()}, "service_uuids": list(uuids)}
            for addr, (name, md, uuids) in found.items()
        }
        _print(out, as_json=True)
    else:
        for addr, (name, md, uuids) in found.items():
            print(f"\n{addr}  {name}")
            for company_id, payload in md.items():
                print(f"  manufacturer_data: company_id=0x{company_id:04x} bytes={payload.hex()}")
            if uuids:
                print(f"  service_uuids:     {list(uuids)}")
        print("\nTo register a fingerprint, add to ADVERTISED_FINGERPRINTS in", file=sys.stderr)
        print("divoom_lib/models/capabilities.py and re-run identify.", file=sys.stderr)
    return 0


# ── Dispatcher ────────────────────────────────────────────────────────


COMMANDS: dict[str, Callable[[argparse.Namespace], Awaitable[int]]] = {
    "scan":          cmd_scan,
    "capabilities":  cmd_capabilities,
    "set-volume":    cmd_set_volume,
    "set-brightness":cmd_set_brightness,
    "set-radio":     cmd_set_radio,
    "set-alarm":     cmd_set_alarm,
    "push-image":    cmd_push_image,
    "push-gif":      cmd_push_gif,
    "pair":          cmd_pair,
    "identify":      cmd_identify,
}


async def amain(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        stream=sys.stderr,
    )
    handler = COMMANDS.get(args.command)
    if handler is None:
        parser.print_help()
        return 2
    return await handler(args)


def main() -> int:
    try:
        return asyncio.run(amain())
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    sys.exit(main())
