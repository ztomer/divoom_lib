#!/usr/bin/env python3
"""Minimal API-driven test harness using the `divoom_api` package.

This script intentionally mirrors the behaviour of `minimal_bleak.py` but
uses the higher-level `divoom_api.Divoom` class and a per-device cache
directory (~/.divoom-control/cache by default) to persist the last working
payload and characteristic mapping for each device.

Important: `minimal_bleak.py` is left unchanged and remains the canonical
reference implementation — this file is a lightweight user-facing wrapper
that demonstrates using the library-level APIs and per-device cache.
"""
import argparse
import asyncio
import json
import os
from pathlib import Path
import logging
import datetime
from bleak import BleakScanner
from bleak.exc import BleakError

from divoom_api.divoom_protocol import Divoom
from divoom_api.base import DivoomBase
from bleak import BleakClient

DEFAULT_CACHE_DIR = os.path.join(
    os.path.expanduser("~"), ".divoom-control", "cache")


def ensure_cache_dir(cache_dir: str) -> None:
    Path(cache_dir).mkdir(parents=True, exist_ok=True)


def device_cache_path(cache_dir: str, device_id: str) -> str:
    # Sanitize device id for filesystem (replace ':' with '_')
    safe_id = device_id.replace(':', '_')
    return os.path.join(cache_dir, f"{safe_id}.json")


def load_device_cache(cache_dir: str, device_id: str) -> dict | None:
    p = device_cache_path(cache_dir, device_id)
    if not os.path.exists(p):
        return None
    try:
        with open(p, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, json.JSONDecodeError):
        return None


def save_device_cache(cache_dir: str, device_id: str, data: dict) -> None:
    ensure_cache_dir(cache_dir)
    p = device_cache_path(cache_dir, device_id)
    with open(p, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2)


async def try_replay_saved(divoom: Divoom, cache: dict, cache_dir: str, device_id: str) -> bool:
    """If cache contains a last_successful_payload entry, try it once."""
    if not cache:
        print("No device cache available.")
        return False

    payload_hex = cache.get("last_successful_payload")
    if not payload_hex:
        print("No saved payload in cache.")
        return False

    try:
        payload = [int(x, 16) for x in payload_hex]
    except ValueError as e:
        print(f"Failed to decode saved payload: {e}")
        return False

    use_ios = bool(cache.get("last_successful_use_ios_le", True))
    write_char = cache.get("write_characteristic_uuid")
    if write_char:
        divoom.WRITE_CHARACTERISTIC_UUID = write_char

    # Apply saved framing/escaping preferences to the divoom instance
    divoom.use_ios_le_protocol = use_ios
    divoom.escapePayload = bool(
        cache.get("escapePayload", divoom.escapePayload))

    print(
        f"Trying saved payload on {divoom.mac} using {'iOS-LE' if use_ios else 'SPP'} framing: {payload}")
    # send_command expects a command id; saved payload is inner args for 0x45
    res = await divoom.send_command_and_wait_for_response(0x45, payload, timeout=4)
    if res is not None:
        print(f"Saved payload produced a response: {res}")
        # Persist successful payload and framing preferences
        try:
            existing = cache or {}
            existing.update({
                "last_successful_payload": payload_hex,
                "last_successful_use_ios_le": bool(use_ios),
                "escapePayload": divoom.escapePayload,
            })
            save_device_cache(cache_dir, device_id, existing)
            print(f"Persisted successful payload to cache for {device_id}")
        except OSError as e:
            print(f"Warning: failed to persist successful payload: {e}")
        return True
    else:
        print("Saved payload did not elicit a response (timeout or no notify)")
        return False


async def set_canonical_light(divoom: Divoom, cache_dir: str, device_id: str, cache: dict | None = None):
    # Build canonical 7-byte payload: [mode(1), R,G,B, brightness, effect_mode, on_off]
    mode = 0x01
    rgb = [0xFF, 0xFF, 0xFF]
    brightness = 100
    effect_mode = 0x00
    power_state = 0x01
    args = [mode] + rgb + [brightness, effect_mode, power_state]

    print(
        f"Attempting canonical Light Mode payload: {[hex(x) for x in args]} (SPP)")
    ok = await divoom.send_command_and_wait_for_response(0x45, args, timeout=3)
    if ok is not None:
        print(f"Canonical (SPP) response: {ok}")
        # Save successful payload to cache
        try:
            existing = cache or {}
            existing.update({
                "last_successful_payload": [f"{b:02x}" for b in args],
                "last_successful_use_ios_le": False,
                "escapePayload": divoom.escapePayload,
            })
            save_device_cache(cache_dir, device_id, existing)
            print(f"Persisted canonical SPP payload to cache for {device_id}")
        except OSError as e:
            print(f"Warning: failed to persist canonical payload: {e}")
        return True

    print("No response for canonical (SPP). Trying iOS-LE framing...")
    divoom.use_ios_le_protocol = True
    ok2 = await divoom.send_command_and_wait_for_response(0x45, args, timeout=3)
    if ok2 is not None:
        print(f"Canonical (iOS-LE) response: {ok2}")
        try:
            existing = cache or {}
            existing.update({
                "last_successful_payload": [f"{b:02x}" for b in args],
                "last_successful_use_ios_le": True,
                "escapePayload": divoom.escapePayload,
            })
            save_device_cache(cache_dir, device_id, existing)
            print(
                f"Persisted canonical iOS-LE payload to cache for {device_id}")
        except OSError as e:
            print(f"Warning: failed to persist canonical payload: {e}")
        return True

    print("Canonical payload did not produce a response.")
    return False


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--address",
                        help="BLE address / identifier of the target device")
    parser.add_argument("--name", default="Timoo",
                        help="Device name substring to search for when --address is not provided (case-insensitive). e.g. 'Timoo' or 'Tivoom'")
    parser.add_argument("--cache-dir", default=DEFAULT_CACHE_DIR,
                        help="Directory to store per-device cache files")
    parser.add_argument(
        "--write-char", help="(Optional) Explicit write characteristic UUID to use")
    parser.add_argument(
        "--notify-char", help="(Optional) Explicit notify characteristic UUID to use")
    parser.add_argument("--replay-saved", action="store_true",
                        help="Try saved payload (if any) from device cache and exit")
    parser.add_argument("--set-canonical-light", action="store_true",
                        help="Attempt canonical light mode payloads (SPP then iOS-LE)")
    parser.add_argument("--diagnostic", action="store_true",
                        help="Enable diagnostic logging of writes and notifications")
    parser.add_argument("--raw-write", action='append', default=[],
                        help="Send a raw hex payload (e.g. 'feefaa55...') after subscribing to notifies; may be specified multiple times")
    parser.add_argument("--raw-write-response", action="store_true",
                        help="When sending --raw-write payloads, request write-with-response")
    args = parser.parse_args()

    ensure_cache_dir(args.cache_dir)
    # If no explicit address provided, try to discover a device matching --name
    ble_device = None
    if not args.address:
        print(
            f"Scanning for Bluetooth devices searching for name containing '{args.name}'...")
        devices = await BleakScanner.discover()
        found = None
        for d in devices:
            if d.name and args.name.lower() in d.name.lower():
                found = d
                break
        if not found:
            print(
                f"No Bluetooth device found with name containing '{args.name}'. Exiting.")
            return
        print(
            f"Found device: {found.name} ({found.address}) — using this device.")
        ble_device = found
    else:
        # Try to resolve provided address to a BLEDevice to avoid implicit
        # discovery on connect (which can cause backend races). If discover
        # doesn't find it quickly, fall back to using the raw address string.
        print(f"Resolving address {args.address} to BLEDevice (short scan)...")
        devices = await BleakScanner.discover(timeout=3.0)
        resolved = None
        for d in devices:
            if d.address == args.address or (d.name and args.address.lower() in d.name.lower()):
                resolved = d
                break
        if resolved:
            print(
                f"Resolved address to BLEDevice: {resolved.name} ({resolved.address})")
            ble_device = resolved
        else:
            print(
                "Could not resolve address to BLEDevice quickly; will attempt connect using raw address string.")
            ble_device = args.address

    # Determine a stable string device id to use for cache files and library
    # initialization. If we have a BLEDevice, use its .address; otherwise
    # use the raw address string we were given.
    if hasattr(ble_device, "address"):
        device_id = ble_device.address
    else:
        device_id = ble_device

    # Update args.address so the rest of the script (and DivoomBase) see a
    # consistent address string.
    args.address = device_id

    cache = load_device_cache(args.cache_dir, device_id)

    # Configure logging for library-level debug output (optional)
    logging.basicConfig(level=logging.INFO)

    # If cache lists a write/notify char and user didn't provide one, use cached
    write_char = args.write_char or (
        cache.get("write_characteristic_uuid") if cache else None)
    notify_char = args.notify_char or (
        cache.get("ack_characteristic_uuid") if cache else None)

    # Use the lightweight base class to avoid side-effects during instantiation
    # (higher-level `Divoom` instantiates many subsystems which may call
    # commands at import/runtime and produce large noisy logs). For this
    # minimal test harness we only need basic send/connect behaviour.
    div = DivoomBase(mac=args.address, write_characteristic_uuid=write_char,
                     notify_characteristic_uuid=notify_char)

    # Apply cached preferences if available
    if cache:
        if "last_successful_use_ios_le" in cache:
            div.use_ios_le_protocol = bool(
                cache.get("last_successful_use_ios_le", div.use_ios_le_protocol))
        if "escapePayload" in cache:
            div.escapePayload = bool(
                cache.get("escapePayload", div.escapePayload))

    # Establish a low-level BleakClient first so we can discover characteristics
    # Use the BLEDevice (if resolved) when constructing the client to avoid
    # implicit scanner calls during connect on some backends.
    client = BleakClient(ble_device)
    try:
        await client.connect()
    except (OSError, RuntimeError, asyncio.TimeoutError) as e:
        print(f"Failed to connect to {args.address}: {e}")
        return

    # Discover services/characteristics via the connected client
    # Ensure services are populated. Some backends populate `client.services` on connect.
    # If an explicit `get_services()` async method is available, call it; otherwise continue.
    # Ensure service discovery finished; some backends (CoreBluetooth) can be
    # racy. Try a few short waits, then call get_services() as a fallback.
    # Wait for services to populate. Accessing client.services can raise
    # BleakError if discovery hasn't completed; handle that and poll a bit.
    tries = 0
    while tries < 6:
        try:
            services_present = getattr(
                client, "services", None) and any(client.services)
        except BleakError:
            services_present = False
        if services_present:
            break
        await asyncio.sleep(0.15)
        tries += 1

    if not services_present:
        extra_tries = 0
        while extra_tries < 40:
            try:
                services_present = getattr(
                    client, "services", None) and any(client.services)
            except BleakError:
                services_present = False
            if services_present:
                break
            await asyncio.sleep(0.1)
            extra_tries += 1
        if not services_present:
            print("Warning: service discovery did not populate `client.services` after waiting; continuing but operations may fail.")

    # Build lists of discovered writeable and notify characteristics
    write_chars = []
    notify_chars = []
    read_chars = []
    for service in client.services:
        for ch in service.characteristics:
            props = set(ch.properties or [])
            if 'write' in props or 'write-without-response' in props or 'write_without_response' in props:
                write_chars.append(ch)
            if 'notify' in props:
                notify_chars.append(ch)
            if 'read' in props:
                read_chars.append(ch)

    # Helper to pick a matching characteristic UUID from discovered list
    def pick_char_uuid(preferred_uuid: str | None, candidates: list, prefix_hint: str | None = '49535343') -> str | None:
        if preferred_uuid:
            for c in candidates:
                if c.uuid == preferred_uuid:
                    return c.uuid
        # prefer ones that match prefix_hint
        if prefix_hint:
            for c in candidates:
                if c.uuid.lower().startswith(prefix_hint.lower()):
                    return c.uuid
        # fallback to first candidate
        return candidates[0].uuid if candidates else None

    # Determine final characteristic UUIDs (prefer CLI args, then cache, then discovery heuristics)
    write_char = args.write_char or (
        cache.get("write_characteristic_uuid") if cache else None)
    notify_char = args.notify_char or (
        cache.get("ack_characteristic_uuid") if cache else None)

    chosen_write = pick_char_uuid(write_char, write_chars)
    chosen_notify = pick_char_uuid(notify_char, notify_chars)
    chosen_read = None
    if read_chars:
        chosen_read = read_chars[0].uuid

    if not chosen_write:
        print("No writeable characteristic discovered; cannot proceed.")
        await client.disconnect()
        return

    # If notify not found, try to fall back to any characteristic that supports notify
    if not chosen_notify and notify_chars:
        chosen_notify = notify_chars[0].uuid

    # If no read char, fall back to notify or write to satisfy DivoomBase.connect requirements
    if not chosen_read:
        chosen_read = chosen_notify or chosen_write

    # Apply discovered characteristics to the high-level Divoom instance and reuse the same client
    div.client = client
    div.WRITE_CHARACTERISTIC_UUID = chosen_write
    div.NOTIFY_CHARACTERISTIC_UUID = chosen_notify
    div.READ_CHARACTERISTIC_UUID = chosen_read

    # We've already established a low-level BleakClient. Instead of calling
    # the high-level `div.connect()` which may re-run discovery/start_notify
    # (and can race on some backends), start notifications explicitly for the
    # chosen notify characteristic(s) and then sleep briefly to let the
    # peripheral settle. This avoids service-discovery races on CoreBluetooth.
    try:
        # Start notify with retries to handle transient CoreBluetooth glitches.
        # Diagnostic: if requested, wrap client's write to log exact bytes and meta
        if args.diagnostic:
            try:
                orig_write = client.write_gatt_char

                async def write_wrapper(char_uuid, data, response=False):
                    ts = datetime.datetime.now().isoformat()
                    hex_data = data.hex()
                    print(
                        f"[DIAG WRITE] {ts} char={char_uuid} response={response} bytes={hex_data}")
                    try:
                        res = await orig_write(char_uuid, data, response=response)
                        print(
                            f"[DIAG WRITE DONE] {ts} char={char_uuid} len={len(data)}")
                        return res
                    except Exception as e:
                        print(
                            f"[DIAG WRITE ERROR] {ts} char={char_uuid} err={e}")
                        raise

                # Monkey-patch the client write method used by the library
                client.write_gatt_char = write_wrapper
            except Exception as e:
                print(
                    f"Warning: diagnostic write wrapper installation failed: {e}")

        async def try_start_notify(char_uuid: str) -> bool:
            attempts = 0
            backoff = 0.15
            while attempts < 3:
                try:
                    # If diagnostics enabled, use a thin wrapper that logs the
                    # notification before delegating to the library handler.
                    handler = div.notification_handler
                    if args.diagnostic:
                        def notify_wrapper(sender, data):
                            ts = datetime.datetime.now().isoformat()
                            try:
                                hex_data = data.hex()
                            except Exception:
                                hex_data = repr(data)
                            print(
                                f"[DIAG NOTIFY] {ts} from={sender} bytes={hex_data}")
                            try:
                                div.notification_handler(sender, data)
                            except Exception as e:
                                print(
                                    f"[DIAG NOTIFY ERROR] {ts} handler err={e}")

                        handler = notify_wrapper

                    await client.start_notify(char_uuid, handler)
                    print(f"Started notify on {char_uuid}")
                    return True
                except (BleakError, OSError, RuntimeError) as e:
                    print(
                        f"Warning: start_notify attempt {attempts+1} failed for {char_uuid}: {e}")
                    attempts += 1
                    await asyncio.sleep(backoff)
                    backoff *= 1.5
            return False

        # Start notifications on all discovered notify characteristics. Some devices
        # send ACKs on a different notify characteristic than the one we pick for
        # writes, so subscribe to all of them to ensure we observe responses.
        for c in notify_chars:
            ok = await try_start_notify(c.uuid)
            if not ok:
                print(f"Warning: failed to reliably start notify on {c.uuid}")
                # Dump services/characteristics for debugging if the chosen_notify failed
                if chosen_notify and c.uuid == chosen_notify:
                    print(
                        f"Failed to start notify on chosen notify {chosen_notify}. Dumping discovered characteristics for debugging.")
                    for s in client.services:
                        print(f"Service: {s.uuid}")
                        for ch in s.characteristics:
                            print(f"  Char: {ch.uuid} props={ch.properties}")

        # Give the device a moment to process subscription requests
        await asyncio.sleep(1.0)

        # Attach client to div instance (already set earlier) and skip calling div.connect()
        # because we've handled the necessary steps (connected client, set char UUIDs,
        # and enabled notifications).
        div.client = client

        # Sanity check: ensure client reports as connected
        if not div.client or not div.client.is_connected:
            print("Client is not connected after starting notify; aborting.")
            try:
                await client.disconnect()
            except (OSError, RuntimeError):
                pass
            return
        # Diagnostic: optionally send raw hex writes now that notifications are active.
        if args.diagnostic and args.raw_write:
            for hexstr in args.raw_write:
                try:
                    data = bytes.fromhex(hexstr)
                except ValueError:
                    print(f"[DIAG RAWWRITE] invalid hex payload: {hexstr}")
                    continue
                target = div.WRITE_CHARACTERISTIC_UUID or chosen_write
                if not target:
                    print(
                        "[DIAG RAWWRITE] No write characteristic available to send raw write")
                    break
                try:
                    ts = datetime.datetime.now().isoformat()
                    print(
                        f"[DIAG RAWWRITE] {ts} -> char={target} len={len(data)} hex={hexstr} response={args.raw_write_response}")
                    # client.write_gatt_char may be wrapped by diagnostic wrapper above
                    await client.write_gatt_char(target, data, response=args.raw_write_response)
                    # Allow a short window to capture any notifications triggered by this write
                    await asyncio.sleep(2.0)
                except Exception as e:
                    print(f"[DIAG RAWWRITE ERROR] {e}")
    except (OSError, RuntimeError, asyncio.TimeoutError) as e:
        print(f"Failed to initialize notification subscriptions: {e}")
        try:
            await client.disconnect()
        except OSError:
            pass
        return

    # If replay-saved requested, try it and exit
    if args.replay_saved:
        ok = await try_replay_saved(div, cache, args.cache_dir, args.address)
        print("Replay-saved result:", ok)
        await div.disconnect()
        return

    # If set-canonical-light requested, try that
    if args.set_canonical_light:
        ok = await set_canonical_light(div, args.cache_dir, args.address, cache)
        print("Canonical light set result:", ok)

    # If no special flags provided, attempt to probe all discovered write characteristics
    # This mirrors `minimal_bleak.py` behaviour: try saved payload per-character, then
    # send a distinct color payload per-character so the user can visually/diagnostically
    # determine which characteristic elicits responses.
    async def probe_write_characteristics_and_try_channel_switch():
        if not write_chars:
            print("No writeable characteristics to probe.")
            return None

        colors = [
            (0xFF, 0x00, 0x00),
            (0x00, 0xFF, 0x00),
            (0x00, 0x00, 0xFF),
            (0xFF, 0xFF, 0x00),
            (0xFF, 0x00, 0xFF),
            (0x00, 0xFF, 0xFF),
        ]

        for idx, ch in enumerate(write_chars):
            uuid = ch.uuid
            print(
                f"Probing write characteristic {uuid} ({idx+1}/{len(write_chars)})")
            # Temporarily set div instance to use this write characteristic
            prev_write = getattr(div, "WRITE_CHARACTERISTIC_UUID", None)
            div.WRITE_CHARACTERISTIC_UUID = uuid

            # 1) If cache has a saved payload, try that first on this characteristic
            if cache and cache.get("last_successful_payload"):
                payload_hex = cache.get("last_successful_payload")
                try:
                    payload = [int(x, 16) for x in payload_hex]
                except Exception:
                    payload = None
                if payload:
                    # Use stored framing preference for this attempt
                    prev_use_ios = div.use_ios_le_protocol
                    prev_escape = getattr(div, "escapePayload", False)
                    div.use_ios_le_protocol = bool(
                        cache.get("last_successful_use_ios_le", div.use_ios_le_protocol))
                    div.escapePayload = bool(
                        cache.get("escapePayload", div.escapePayload))
                    print(
                        f"Trying saved payload on {uuid}: {[hex(x) for x in payload]} (use_ios={div.use_ios_le_protocol} escape={div.escapePayload})")
                    resp = await div.send_command_and_wait_for_response(0x45, payload, timeout=3)
                    # restore framing prefs
                    div.use_ios_le_protocol = prev_use_ios
                    div.escapePayload = prev_escape
                    if resp is not None:
                        print(
                            f"Saved payload produced a response on {uuid}: {resp}")
                        # persist mapping and payload
                        existing = cache or {}
                        existing.update({
                            "write_characteristic_uuid": uuid,
                            "ack_characteristic_uuid": div.NOTIFY_CHARACTERISTIC_UUID,
                            "last_successful_payload": [f"{b:02x}" for b in payload],
                            "last_successful_use_ios_le": div.use_ios_le_protocol,
                            "escapePayload": div.escapePayload,
                        })
                        save_device_cache(
                            args.cache_dir, args.address, existing)
                        return uuid

            # 2) Send a distinguishing color payload for this characteristic
            r, g, b = colors[idx % len(colors)]
            args_payload = [0x01, r, g, b, 100, 0x00, 0x01]
            print(
                f"Sending diagnostic color payload to {uuid}: R={r} G={g} B={b}")

            # Try SPP first (escaped), then iOS-LE fallback
            prev_escape = getattr(div, "escapePayload", False)
            prev_use_ios = div.use_ios_le_protocol

            # SPP attempt
            div.escapePayload = True
            div.use_ios_le_protocol = False
            resp_spp = await div.send_command_and_wait_for_response(0x45, args_payload, timeout=3)
            if resp_spp is not None:
                print(
                    f"Response to SPP diagnostic payload on {uuid}: {resp_spp}")
                existing = cache or {}
                existing.update({
                    "write_characteristic_uuid": uuid,
                    "ack_characteristic_uuid": div.NOTIFY_CHARACTERISTIC_UUID,
                    "last_successful_payload": [f"{b:02x}" for b in args_payload],
                    "last_successful_use_ios_le": False,
                    "escapePayload": div.escapePayload,
                })
                save_device_cache(args.cache_dir, args.address, existing)
                # restore prefs
                div.escapePayload = prev_escape
                div.use_ios_le_protocol = prev_use_ios
                return uuid

            # iOS-LE attempt
            div.escapePayload = prev_escape
            div.use_ios_le_protocol = True
            resp_ios = await div.send_command_and_wait_for_response(0x45, args_payload, timeout=3)
            # restore prefs
            div.escapePayload = prev_escape
            div.use_ios_le_protocol = prev_use_ios
            if resp_ios is not None:
                print(
                    f"Response to iOS-LE diagnostic payload on {uuid}: {resp_ios}")
                existing = cache or {}
                existing.update({
                    "write_characteristic_uuid": uuid,
                    "ack_characteristic_uuid": div.NOTIFY_CHARACTERISTIC_UUID,
                    "last_successful_payload": [f"{b:02x}" for b in args_payload],
                    "last_successful_use_ios_le": True,
                    "escapePayload": div.escapePayload,
                })
                save_device_cache(args.cache_dir, args.address, existing)
                return uuid

            # restore previous write char if none succeeded for this char
            div.WRITE_CHARACTERISTIC_UUID = prev_write

        # Nothing produced a response
        return None

    if not args.replay_saved and not args.set_canonical_light:
        print("Probing discovered write characteristics to find one that elicits responses (will send distinct colors per characteristic)")
        try:
            successful_uuid = await probe_write_characteristics_and_try_channel_switch()
            if successful_uuid:
                print(
                    f"Found responsive write characteristic: {successful_uuid}")
            else:
                print("No write characteristic produced a response during probe. Falling back to single-character channel-switch attempt.")
                # Fallback: run the original channel-switch sequence on the chosen_write
                try:
                    print(
                        "Attempting channel-switch sequence: set work mode, power-on channel, then switch to channel 0x02")
                    await div.send_command(0x05, [0x09])
                    await asyncio.sleep(1.0)
                    await div.send_command(0x8a, [0x02])
                    await asyncio.sleep(1.0)
                    prev_escape = getattr(div, "escapePayload", False)
                    div.escapePayload = True
                    div.use_ios_le_protocol = False
                    res = await div.send_command_and_wait_for_response(0x45, [0x02], timeout=3)
                    if res is not None:
                        print(
                            f"Channel switch (SPP) succeeded: response={res}")
                    else:
                        print(
                            "No response for SPP channel switch; trying iOS-LE framing...")
                        div.escapePayload = prev_escape
                        div.use_ios_le_protocol = True
                        res2 = await div.send_command_and_wait_for_response(0x45, [0x02], timeout=3)
                        if res2 is not None:
                            print(
                                f"Channel switch (iOS-LE) succeeded: response={res2}")
                        else:
                            print(
                                "Channel switch did not produce a response with either framing.")
                    div.escapePayload = prev_escape
                except (asyncio.TimeoutError, BleakError, RuntimeError, OSError) as e:
                    print(f"Error during channel-switch sequence: {e}")
        except Exception as e:
            print(f"Error while probing write characteristics: {e}")

    # Save current mapping if we have both write and notify characteristics discovered
    try:
        # Attempt to persist mapping for future runs
        mapping = {
            "write_characteristic_uuid": div.WRITE_CHARACTERISTIC_UUID,
            "ack_characteristic_uuid": div.NOTIFY_CHARACTERISTIC_UUID,
            "last_successful_use_ios_le": div.use_ios_le_protocol,
            "escapePayload": div.escapePayload,
        }
        # Do not overwrite last_successful_payload unintentionally here.
        existing = cache or {}
        existing.update(mapping)
        save_device_cache(args.cache_dir, args.address, existing)
        print(f"Saved device mapping to cache for {args.address}")
    except OSError as e:
        print(f"Warning: failed to save mapping: {e}")

    await div.disconnect()


if __name__ == "__main__":
    # Run main with a guarded wrapper so we print a full traceback for
    # unexpected exceptions. This makes debugging runtime failures easier
    # for the harness since BLE backends can raise backend-specific errors.
    import traceback
    import sys

    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Interrupted by user")
        try:
            sys.exit(0)
        except SystemExit:
            pass
    except (OSError, RuntimeError, asyncio.TimeoutError, AttributeError) as e:
        print("Unhandled exception in minimal_api: printing traceback:")
        traceback.print_exc()
        print(f"Exception: {e}")
        sys.exit(1)
