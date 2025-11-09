#!/usr/bin/env python3
"""Minimal API-driven test harness using the `divoom_api` package.

This script demonstrates using the library-level APIs and per-device cache.
"""
import argparse
import asyncio
import os
import logging
import datetime
from bleak import BleakClient
from bleak.exc import BleakError

from divoom_api.divoom_protocol import Divoom
from divoom_api.base import DivoomBase
from divoom_api.utils import cache
from divoom_api.utils import discovery

DEFAULT_CACHE_DIR = os.path.join(
    os.path.expanduser("~"), ".divoom-control", "cache")

async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--address",
                        help="BLE address / identifier of the target device")
    parser.add_argument("--name", default="Timoo",
                        help="Device name substring to search for when --address is not provided (case-insensitive). e.g. 'Timoo' or 'Tivoom'")
    parser.add_argument("--cache-dir", default=cache.DEFAULT_CACHE_DIR,
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

    cache.ensure_cache_dir(args.cache_dir)
    
    # Configure logging for library-level debug output (optional)
    logging.basicConfig(level=logging.INFO)

    ble_device, device_id = await discovery.discover_device(name_substring=args.name, address=args.address)

    if not ble_device:
        return

    args.address = device_id # Update args.address for consistency

    device_cache = cache.load_device_cache(args.cache_dir, device_id)

    # If cache lists a write/notify char and user didn't provide one, use cached
    write_char = args.write_char or (
        device_cache.get("write_characteristic_uuid") if device_cache else None)
    notify_char = args.notify_char or (
        device_cache.get("ack_characteristic_uuid") if device_cache else None)

    div = Divoom(mac=args.address, write_characteristic_uuid=write_char,
                     notify_characteristic_uuid=notify_char)

    # Apply cached preferences if available
    if device_cache:
        if "last_successful_use_ios_le" in device_cache:
            div.use_ios_le_protocol = bool(
                device_cache.get("last_successful_use_ios_le", div.use_ios_le_protocol))
        if "escapePayload" in device_cache:
            div.escapePayload = bool(
                device_cache.get("escapePayload", div.escapePayload))

    client = BleakClient(ble_device)
    try:
        await client.connect()
    except (OSError, RuntimeError, asyncio.TimeoutError) as e:
        print(f"Failed to connect to {args.address}: {e}")
        return

    write_chars, notify_chars, read_chars = await discovery.discover_characteristics(client)

    chosen_write = discovery.pick_char_uuid(write_char, write_chars)
    chosen_notify = discovery.pick_char_uuid(notify_char, notify_chars)
    chosen_read = None
    if read_chars:
        chosen_read = read_chars[0].uuid

    if not chosen_write:
        print("No writeable characteristic discovered; cannot proceed.")
        await client.disconnect()
        return

    if not chosen_notify and notify_chars:
        chosen_notify = notify_chars[0].uuid

    if not chosen_read:
        chosen_read = chosen_notify or chosen_write

    div.client = client
    div.WRITE_CHARACTERISTIC_UUID = chosen_write
    div.NOTIFY_CHARACTERISTIC_UUID = chosen_notify
    div.READ_CHARACTERISTIC_UUID = chosen_read

    try:
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

                client.write_gatt_char = write_wrapper
            except Exception as e:
                print(
                    f"Warning: diagnostic write wrapper installation failed: {e}")

        async def try_start_notify(char_uuid: str) -> bool:
            attempts = 0
            backoff = 0.15
            while attempts < 3:
                try:
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

        for c in notify_chars:
            ok = await try_start_notify(c.uuid)
            if not ok:
                print(f"Warning: failed to reliably start notify on {c.uuid}")
                if chosen_notify and c.uuid == chosen_notify:
                    print(
                        f"Failed to start notify on chosen notify {chosen_notify}. Dumping discovered characteristics for debugging.")
                    for s in client.services:
                        print(f"Service: {s.uuid}")
                        for ch in s.characteristics:
                            print(f"  Char: {ch.uuid} props={ch.properties}")

        await asyncio.sleep(1.0)

        if not div.client or not div.client.is_connected:
            print("Client is not connected after starting notify; aborting.")
            try:
                await client.disconnect()
            except (OSError, RuntimeError):
                pass
            return
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
                    await client.write_gatt_char(target, data, response=args.raw_write_response)
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

    if args.replay_saved:
        ok = await div.try_replay_saved(device_cache, args.cache_dir, args.address)
        print("Replay-saved result:", ok)
        await div.disconnect()
        return

    if args.set_canonical_light:
        ok = await div.light.set_canonical_light(args.cache_dir, args.address, device_cache)
        print("Canonical light set result:", ok)

    if not args.replay_saved and not args.set_canonical_light:
        print("Probing discovered write characteristics to find one that elicits responses (will send distinct colors per characteristic)")
        try:
            successful_uuid = await div.probe_write_characteristics_and_try_channel_switch(write_chars, notify_chars, read_chars, device_cache, args.cache_dir, args.address, args)
            if successful_uuid:
                print(
                    f"Found responsive write characteristic: {successful_uuid}")
            else:
                print("No write characteristic produced a response during probe.")
        except Exception as e:
            print(f"Error while probing write characteristics: {e}")

    try:
        mapping = {
            "write_characteristic_uuid": div.WRITE_CHARACTERISTIC_UUID,
            "ack_characteristic_uuid": div.NOTIFY_CHARACTERISTIC_UUID,
            "last_successful_use_ios_le": div.use_ios_le_protocol,
            "escapePayload": div.escapePayload,
        }
        existing = device_cache or {}
        existing.update(mapping)
        cache.save_device_cache(args.cache_dir, args.address, existing)
        print(f"Saved device mapping to cache for {args.address}")
    except OSError as e:
        print(f"Warning: failed to save mapping: {e}")

    await div.disconnect()


if __name__ == "__main__":
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
        print("Unhandled exception in api_test: printing traceback:")
        traceback.print_exc()
        print(f"Exception: {e}")
        sys.exit(1)
