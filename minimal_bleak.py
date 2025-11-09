import asyncio
from bleak import BleakScanner, BleakClient
import logging
import json
import os
import argparse
import itertools


def _mapping_path():
    return os.path.join(os.path.dirname(__file__), ".divoom_last_working_char.json")


def save_working_mapping(client: BleakClient, write_char_uuid: str, ack_sender: str):
    """Save a descriptive mapping for future runs.

    We save the write characteristic UUID plus a human-friendly descriptor derived
    from the characteristic's service UUID and properties so we can try to match
    a similar characteristic on other devices instead of relying strictly on UUIDs.
    """
    cfg_path = _mapping_path()
    try:
        # Find characteristic object and its parent service
        svc_uuid = None
        props = []
        desc_text = None
        for service in client.services:
            for ch in service.characteristics:
                if ch.uuid == write_char_uuid:
                    svc_uuid = service.uuid
                    props = ch.properties
                    desc_text = getattr(ch, "description", None)
                    break
            if svc_uuid:
                break

        cfg = {
            "write_characteristic_uuid": write_char_uuid,
            "ack_characteristic_uuid": ack_sender,
            "service_uuid": svc_uuid,
            "properties": props,
            "description": desc_text,
        }
        with open(cfg_path, "w", encoding="utf-8") as fh:
            json.dump(cfg, fh)
        print(f"Saved last working characteristic mapping to {cfg_path}")
    except Exception as e:
        print(f"Failed to persist working characteristic: {e}")


def save_last_successful_payload(write_char_uuid: str, payload: list, use_ios_le: bool = True):
    """Save the exact payload and framing that produced a successful ACK so future runs can reuse it.

    This augments the same mapping file used by save_working_mapping. We store the payload as
    a hex list to keep the file human readable.
    """
    cfg_path = _mapping_path()
    try:
        cfg = {}
        if os.path.exists(cfg_path):
            with open(cfg_path, "r", encoding="utf-8") as fh:
                try:
                    cfg = json.load(fh) or {}
                except Exception:
                    cfg = {}

        cfg["last_successful_payload"] = [hex(x) for x in payload]
        cfg["last_successful_use_ios_le"] = bool(use_ios_le)
        cfg["last_successful_write_characteristic"] = write_char_uuid

        with open(cfg_path, "w", encoding="utf-8") as fh:
            json.dump(cfg, fh)
        print(f"Saved last successful payload to {cfg_path}")
    except Exception as e:
        print(f"Failed to save last successful payload: {e}")


def load_working_mapping():
    cfg_path = _mapping_path()
    if not os.path.exists(cfg_path):
        return None
    try:
        with open(cfg_path, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except Exception as e:
        print(f"Failed to load saved mapping {cfg_path}: {e}")
        return None


def find_best_matching_write_characteristic(client: BleakClient, saved: dict) -> str:
    """Given a saved mapping, try to find the best matching write characteristic uuid.

    Matching strategy (in order):
    - Exact UUID match
    - Service UUID + properties subset match
    - Description substring match (if description was saved and available)
    Returns the uuid string if found, else None.
    """
    if not saved:
        return None

    target_uuid = saved.get("write_characteristic_uuid")
    target_service = saved.get("service_uuid")
    target_props = set(saved.get("properties") or [])
    target_desc = saved.get("description")

    # Build a lookup of discovered characteristics
    chars = []
    for service in client.services:
        for ch in service.characteristics:
            chars.append((service.uuid, ch))

    # 1) Exact UUID
    for svc_uuid, ch in chars:
        if ch.uuid == target_uuid:
            return ch.uuid

    # 2) Service UUID + properties subset
    if target_service:
        for svc_uuid, ch in chars:
            if svc_uuid == target_service:
                if target_props and set(ch.properties) >= target_props:
                    return ch.uuid

    # 3) Description substring
    if target_desc:
        for svc_uuid, ch in chars:
            desc = getattr(ch, "description", "") or ""
            if target_desc and target_desc in desc:
                return ch.uuid

    return None


# Configure logging for bleak
logging.basicConfig(level=logging.DEBUG)
logging.getLogger("bleak").setLevel(logging.DEBUG)
logging.getLogger("bleak.backends.corebluetooth").setLevel(
    logging.DEBUG)  # For macOS
logging.getLogger("bleak.backends.bluez").setLevel(logging.DEBUG)  # For Linux
logging.getLogger("bleak.backends.windows").setLevel(
    logging.DEBUG)  # For Windows

# Divoom protocol constants
START_BYTE = 0x01
END_BYTE = 0x02

# Global flag for payload escaping
ENABLE_PAYLOAD_ESCAPING = True  # Set to True to enable escaping, False to disable

# Light Effect Types (from PROTOCOL.md - Set Light Effect 0x45, Mode 0x02)
LIGHT_EFFECT_TYPE_PLAIN_COLOR = 0x00
LIGHT_EFFECT_TYPE_FLASHING = 0x01
LIGHT_EFFECT_TYPE_RAINBOW = 0x02
LIGHT_EFFECT_TYPE_SCROLLING = 0x03
LIGHT_EFFECT_TYPE_CUSTOM = 0x04


def calculate_checksum(data_bytes: list) -> bytes:
    checksum_value = sum(data_bytes)
    return checksum_value.to_bytes(2, byteorder='little')


def escape_payload(payload: list) -> list:
    escaped_payload = []
    for byte in payload:
        if byte == 0x01:
            escaped_payload.extend([0x03, 0x04])
        elif byte == 0x02:
            escaped_payload.extend([0x03, 0x05])
        elif byte == 0x03:
            escaped_payload.extend([0x03, 0x06])
        else:
            escaped_payload.append(byte)
    return escaped_payload


def construct_packet(command_code: int, payload: list) -> bytes:
    full_payload = [command_code] + payload

    if ENABLE_PAYLOAD_ESCAPING:
        full_payload = escape_payload(full_payload)

    length_value = len(full_payload) + 2  # +2 for checksum bytes
    length_bytes = length_value.to_bytes(2, byteorder='little')

    checksum_data = list(length_bytes) + full_payload
    checksum = calculate_checksum(checksum_data)

    packet = bytes([START_BYTE]) + length_bytes + \
        bytes(full_payload) + checksum + bytes([END_BYTE])
    return packet


# Globals used to coordinate request/response during interactive testing
# _expected_command: integer command id we wait for (e.g. 0x45)
# _response_future: asyncio.Future set when notification contains expected command
# _last_ack_from: UUID of characteristic that delivered the ACK
_expected_command = None
_response_future = None
_last_ack_from = None


def notification_handler(sender, data: bytearray):
    """Global notification handler that looks for ACKs or command responses.

    It checks for patterns like [0x04, CMD, 0x55] anywhere in the payload
    (basic app/response) and resolves the pending _response_future if the
    expected command is seen.
    """
    global _expected_command, _response_future, _last_ack_from

    hexdata = data.hex()
    print(f"Notification from {sender}: {hexdata}")

    # Quick scan: look for pattern 04 <cmd> 55
    try:
        b = bytes(data)
    except Exception:
        b = data

    # Find occurrences of [0x04, cmd, 0x55]
    for i in range(0, len(b) - 2):
        if b[i] == 0x04 and b[i+2] == 0x55:
            cmd = b[i+1]
            print(f"Parsed potential response: cmd=0x{cmd:02x} at offset {i}")
            if _expected_command is not None and cmd == _expected_command:
                print(f"Matched expected command 0x{cmd:02x} from {sender}")
                _last_ack_from = sender
                if _response_future is not None and not _response_future.done():
                    _response_future.set_result((True, sender, b))
                return

    # Also, handle iOS LE style notifications: header FE EF AA 55 then payload where
    # command id may follow; look for header then a command id of interest anywhere after.
    header = b"\xfe\xef\xaaU"
    idx = b.find(header)
    if idx != -1:
        # Try to find any 0x04 ... 0x55 inside following data
        sub = b[idx+4:]
        for j in range(0, len(sub) - 2):
            if sub[j] == 0x04 and sub[j+2] == 0x55:
                cmd = sub[j+1]
                print(f"Parsed iOS-LE style response: cmd=0x{cmd:02x}")
                if _expected_command is not None and cmd == _expected_command:
                    _last_ack_from = sender
                    if _response_future is not None and not _response_future.done():
                        _response_future.set_result((True, sender, b))
                    return


async def discover_write_characteristics(client: BleakClient) -> list:
    write_characteristics = []
    for service in client.services:
        for char in service.characteristics:
            if "write" in char.properties or "write_without_response" in char.properties:
                write_characteristics.append(char.uuid)
                print(
                    f"Discovered writeable characteristic: {char.uuid} (Properties: {char.properties})")
    return write_characteristics


async def discover_notify_characteristics(client: BleakClient) -> list:
    notify_characteristics = []
    for service in client.services:
        for char in service.characteristics:
            if "notify" in char.properties:
                notify_characteristics.append(char.uuid)
                print(
                    f"Discovered notify characteristic: {char.uuid} (Properties: {char.properties})")
    return notify_characteristics


def construct_ios_le_packet(command_code: int, payload: list, packet_number: int = 0) -> bytes:
    """Construct an iOS LE style packet: header + len + cmd id + packet no + data + checksum."""
    header = [0xFE, 0xEF, 0xAA, 0x55]
    # data_bytes includes command and args
    data_bytes = [command_code] + payload

    # Packet number (4 bytes little-endian)
    pkt_bytes = list(packet_number.to_bytes(4, byteorder="little"))

    # Data length: 1 (cmd id) + 4 (packet num) + len(data_bytes) + 2 (checksum)
    data_length_value = 1 + 4 + len(data_bytes) + 2
    data_length_bytes = list(data_length_value.to_bytes(2, byteorder="little"))

    # Checksum is sum of data_length_bytes + command identifier + packet_number + data_bytes
    checksum_input = data_length_bytes + \
        [command_code] + pkt_bytes + data_bytes
    checksum_value = sum(checksum_input)
    checksum_bytes = list(checksum_value.to_bytes(2, byteorder="little"))

    final = bytes(header + data_length_bytes +
                  [command_code] + pkt_bytes + data_bytes + checksum_bytes)
    return final


async def switch_channel(client: BleakClient, write_characteristic_uuid: str, channel: int, *, use_ios_le: bool = False, timeout: float = 5.0):
    """Send a channel-switch command to the device.

    Tries the SPP/basic framing first (01 .. 02). If use_ios_le is True, will send an iOS-LE framed packet.
    """
    # Payload for switch channel: command 0x45 + channel byte
    command_code = 0x45
    payload = [channel]

    global _expected_command, _response_future, _last_ack_from

    loop = asyncio.get_running_loop()
    _expected_command = command_code
    _response_future = loop.create_future()
    _last_ack_from = None

    try:
        if use_ios_le:
            pkt = construct_ios_le_packet(command_code, payload)
            print(
                f"Sending iOS-LE framed channel switch (channel={channel}) to {write_characteristic_uuid}: {pkt.hex()}")
            await client.write_gatt_char(write_characteristic_uuid, pkt, response=True)
        else:
            # Fallback to SPP/basic framing using existing construct_packet
            pkt = construct_packet(command_code, payload)
            print(
                f"Sending SPP/basic framed channel switch (channel={channel}) to {write_characteristic_uuid}: {pkt.hex()}")
            # Prefer write with response to attempt to get an ACK from the device
            await client.write_gatt_char(write_characteristic_uuid, pkt, response=True)

        # Wait for the notification handler to resolve the future when an ACK is seen
        try:
            ok, sender, raw = await asyncio.wait_for(_response_future, timeout=timeout)
            print(
                f"Received ACK for command 0x{command_code:02x} from {sender}")
            return True, sender, raw
        except asyncio.TimeoutError:
            print(
                f"Timed out waiting for ACK for command 0x{command_code:02x} (timeout={timeout}s)")
            return False, None, None
    finally:
        _expected_command = None
        _response_future = None


async def send_command_and_wait_for_ack(client: BleakClient, write_characteristic_uuid: str, command_code: int, payload: list, *, use_ios_le: bool = False, timeout: float = 5.0):
    """Generic: send arbitrary command and wait for ACK via notifications.

    Returns (ok: bool, sender, raw_bytes)
    """
    global _expected_command, _response_future, _last_ack_from

    loop = asyncio.get_running_loop()
    _expected_command = command_code
    _response_future = loop.create_future()
    _last_ack_from = None

    try:
        if use_ios_le:
            pkt = construct_ios_le_packet(command_code, payload)
            print(
                f"Sending iOS-LE framed command 0x{command_code:02x} to {write_characteristic_uuid}: {pkt.hex()}")
            await client.write_gatt_char(write_characteristic_uuid, pkt, response=True)
        else:
            pkt = construct_packet(command_code, payload)
            print(
                f"Sending SPP/basic framed command 0x{command_code:02x} to {write_characteristic_uuid}: {pkt.hex()}")
            await client.write_gatt_char(write_characteristic_uuid, pkt, response=True)

        try:
            ok, sender, raw = await asyncio.wait_for(_response_future, timeout=timeout)
            print(
                f"Received ACK for command 0x{command_code:02x} from {sender}")
            return True, sender, raw
        except asyncio.TimeoutError:
            print(
                f"Timed out waiting for ACK for command 0x{command_code:02x} (timeout={timeout}s)")
            return False, None, None
    finally:
        _expected_command = None
        _response_future = None


async def send_light_effect_command(client: BleakClient, write_characteristic_uuid: str, effect_type: int, color: list, brightness: int, power_on: int):
    command_code = 0x45  # Command for Set Channel
    mode = 0x02  # Mode for Light Effect
    # Payload: [Mode, Type, R, G, B, Brightness, Power]
    payload = [mode, effect_type] + color + [brightness, power_on]
    packet_to_send = construct_packet(command_code, payload)

    print(
        f"Sending light effect packet (Type: {effect_type}, escaped: {ENABLE_PAYLOAD_ESCAPING}) to {write_characteristic_uuid}: {packet_to_send.hex()}")
    await client.write_gatt_char(write_characteristic_uuid, packet_to_send, response=False)
    print(
        f"Light effect command (Type: {effect_type}) sent to {write_characteristic_uuid}.")


async def try_lightning_variants(client: BleakClient, write_characteristic_uuid: str, *, timeout: float = 2.0):
    """Try a small matrix of Lightning (0x45) payload permutations to discover one that elicits an ACK.

    This will try different modes, brightness values, type flags, presence/absence of the trailing
    zero bytes and both SPP and iOS-LE framings. If a variant produces an ACK, it prints and
    persists the working mapping and returns True.
    """
    global ENABLE_PAYLOAD_ESCAPING
    original_escaping = ENABLE_PAYLOAD_ESCAPING

    rgb = [0xFF, 0xFF, 0xFF]
    modes = [0x01, 0x00]  # try Light Mode and Env Mode as permutations
    brightness_values = [100, 50, 255]
    # Try a range of effect modes (0..6) per API doc: 1==Night Light, 2==HOT, 3==VJ, etc.
    type_values = [0x00, 0x01, 0x02, 0x03, 0x04, 0x05, 0x06]
    power_values = [0x01, 0x00]
    suffix_options = [True, False]
    escaping_options = [True, False]
    framings = [False, True]  # SPP (False), iOS-LE (True)

    tried = 0
    for mode, bright, tval, pval, suffix, escaping, use_ios in itertools.product(
            modes, brightness_values, type_values, power_values, suffix_options, escaping_options, framings):
        ENABLE_PAYLOAD_ESCAPING = escaping
        payload = [mode] + rgb + [bright, tval, pval]
        if suffix:
            payload += [0x00, 0x00, 0x00]

        tried += 1
        print(
            f"[Probe] Trying variant #{tried}: mode=0x{mode:02x}, bright={bright}, type=0x{tval:02x}, power=0x{pval:02x}, suffix={suffix}, escaping={escaping}, ios_le={use_ios}")
        try:
            ok, ack_sender, raw = await send_command_and_wait_for_ack(client, write_characteristic_uuid, 0x45, payload, use_ios_le=use_ios, timeout=timeout)
            if ok:
                print(
                    f"[Probe] Success with variant #{tried} (ACK from {ack_sender}) payload={payload} framing={'iOS-LE' if use_ios else 'SPP'})")
                # Persist both the characteristic mapping and the exact successful payload/framing
                try:
                    save_working_mapping(
                        client, write_characteristic_uuid, str(ack_sender))
                except Exception as e:
                    print(f"[Probe] Failed to save mapping: {e}")
                try:
                    save_last_successful_payload(
                        write_characteristic_uuid, payload, use_ios_le=use_ios)
                except Exception as e:
                    print(f"[Probe] Failed to save successful payload: {e}")
                ENABLE_PAYLOAD_ESCAPING = original_escaping
                return True
        except Exception as e:
            print(f"[Probe] Error while trying variant #{tried}: {e}")

        # Small pause between attempts to give the device time to respond/reset
        await asyncio.sleep(0.25)

    ENABLE_PAYLOAD_ESCAPING = original_escaping
    print(f"[Probe] Exhausted {tried} variants with no ACK.")
    return False


async def send_work_mode_command(client: BleakClient, write_characteristic_uuid: str, mode: int):
    command_code = 0x05  # Command for Set Play Mode (Work Mode)
    payload = [mode]
    packet_to_send = construct_packet(command_code, payload)

    print(
        f"Sending work mode packet (Mode: {mode}, escaped: {ENABLE_PAYLOAD_ESCAPING}) to {write_characteristic_uuid}: {packet_to_send.hex()}")
    await client.write_gatt_char(write_characteristic_uuid, packet_to_send, response=False)
    print(
        f"Work mode command (Mode: {mode}) sent to {write_characteristic_uuid}.")


async def send_poweron_channel_command(client: BleakClient, write_characteristic_uuid: str, channel: int):
    command_code = 0x8a  # Command for Set Power On Channel
    payload = [channel]
    packet_to_send = construct_packet(command_code, payload)

    print(
        f"Sending poweron channel packet (Channel: {channel}, escaped: {ENABLE_PAYLOAD_ESCAPING}) to {write_characteristic_uuid}: {packet_to_send.hex()}")
    await client.write_gatt_char(write_characteristic_uuid, packet_to_send, response=False)
    print(
        f"Poweron channel command (Channel: {channel}) sent to {write_characteristic_uuid}.")


async def send_get_light_mode(client: BleakClient, write_characteristic_uuid: str, *, timeout: float = 3.0):
    """Send a Get Light Mode (0x46) request and wait for the device response via notifications.

    Returns tuple (ok: bool, sender, raw_bytes) when a response (ACK) is received, else (False, None, None).
    """
    command_code = 0x46
    # 0x46 has no payload
    print(f"Sending Get Light Mode (0x46) to {write_characteristic_uuid}")
    return await send_command_and_wait_for_ack(client, write_characteristic_uuid, command_code, [], use_ios_le=False, timeout=timeout)


async def find_and_connect_timoo(probe_lightning: bool = False, skip_channel_switch: bool = False):
    # If you encounter a "name 'packet_to_to_send' is not defined" error,
    # please check your local file for a typo and correct it to 'packet_to_send'.
    print("Scanning for Bluetooth devices...")
    devices = await BleakScanner.discover()

    timoo_device = None
    for device in devices:
        if device.name and "Timoo" in device.name:
            timoo_device = device
            print(
                f"Found Timoo device: {device.name} ({timoo_device.address})")
            break

    if timoo_device:
        print(
            f"Attempting to connect to {timoo_device.name} ({timoo_device.address})...")
        try:
            async with BleakClient(timoo_device.address) as client:
                if client.is_connected:
                    print(f"Successfully connected to {timoo_device.name}!")

                    write_characteristics = await discover_write_characteristics(client)
                    notify_characteristics = await discover_notify_characteristics(client)

                    # Load saved mapping early so we can try any previously-discovered
                    # successful payload before we perform any channel switching.
                    saved = load_working_mapping()

                    # Start notifications for discovered notify-characteristics so we can observe ACKs
                    for nchar in notify_characteristics:
                        try:
                            await client.start_notify(nchar, notification_handler)
                            print(f"Started notify for {nchar}")
                        except Exception as e:
                            print(f"Failed to start notify for {nchar}: {e}")

                    # If we have a saved mapping, try to prefer a matching characteristic
                    if saved:
                        best = find_best_matching_write_characteristic(
                            client, saved)
                        if best and best in write_characteristics:
                            # move the candidate to the front so we test it first
                            write_characteristics = [
                                best] + [u for u in write_characteristics if u != best]
                            print(
                                f"Preferring previously saved characteristic {best} based on saved descriptor")

                    if not write_characteristics:
                        print(
                            "No writeable characteristics found. Cannot send commands.")
                        return

                    for char_uuid in write_characteristics:
                        print(f"\n--- Testing characteristic: {char_uuid} ---")
                        try:
                            # If a saved successful payload exists, try it immediately
                            # before any channel switching; this avoids forcing the
                            # device into other channels during verification.
                            if saved and saved.get("last_successful_payload"):
                                try:
                                    saved_payload_hex = saved.get(
                                        "last_successful_payload", [])
                                    saved_payload = [int(x, 16)
                                                     for x in saved_payload_hex]
                                    saved_use_ios = bool(
                                        saved.get("last_successful_use_ios_le", True))
                                except Exception:
                                    saved_payload = None
                                    saved_use_ios = True

                                if saved_payload:
                                    print(
                                        f"Trying saved successful payload on {char_uuid} first (use_ios_le={saved_use_ios}): {saved_payload}")
                                    ok_saved, ack_saved, raw_saved = await send_command_and_wait_for_ack(
                                        client, char_uuid, 0x45, saved_payload, use_ios_le=saved_use_ios)
                                    if ok_saved:
                                        print(
                                            f"Saved payload succeeded on {char_uuid} (ACK from {ack_saved})")
                                        try:
                                            save_working_mapping(
                                                client, char_uuid, str(ack_saved))
                                        except Exception as e:
                                            print(
                                                f"Failed to save mapping after saved-payload success: {e}")
                                        # If we're just verifying saved payloads, optionally skip channel switching
                                        if skip_channel_switch:
                                            print(
                                                "--skip-channel-switch set, skipping remaining channel-switch operations for this characteristic.")
                                            # skip to next characteristic
                                            await asyncio.sleep(0.5)
                                            continue
                            # Try setting work mode to Divoom Show (0x09)
                            await send_work_mode_command(client, char_uuid, 0x09)
                            await asyncio.sleep(1)

                            # Try setting poweron channel to Light Effect (0x02)
                            await send_poweron_channel_command(client, char_uuid, 0x02)
                            await asyncio.sleep(1)

                            # Explicit channel switch using switch_channel helper (command 0x45)
                            # Try SPP/basic framing first and detect ACK automatically
                            ok, ack_sender, raw = await switch_channel(client, char_uuid, 0x02, use_ios_le=False)
                            if ok:
                                print(
                                    f"Channel switch succeeded via {char_uuid} (ACK from {ack_sender}), response={raw.hex()}")
                                # Persist the successful mapping so future runs prefer this characteristic
                                save_working_mapping(
                                    client, char_uuid, str(ack_sender))
                            else:
                                print(
                                    "SPP/basic framed attempt did not produce an ACK; trying iOS-LE framing...")

                            await asyncio.sleep(1)

                            # Optional: run an automated probe that tries many payload variants
                            if probe_lightning:
                                print(
                                    "Probe mode enabled: trying automated Lightning payload permutations...")
                                probe_ok = await try_lightning_variants(client, char_uuid)
                                if probe_ok:
                                    print(
                                        f"Probe discovered a working Lightning variant for {char_uuid} and saved mapping.")

                            # If the device expects iOS LE framing, try that as well
                            ok2, ack_sender2, raw2 = await switch_channel(client, char_uuid, 0x02, use_ios_le=True)
                            if ok2:
                                print(
                                    f"Channel switch (iOS-LE) succeeded via {char_uuid} (ACK from {ack_sender2}), response={raw2.hex()}")
                                save_working_mapping(
                                    client, char_uuid, str(ack_sender2))
                            await asyncio.sleep(1)

                            # Test different light effect types
                            # Plain Color (Red)
                            await send_light_effect_command(client, char_uuid, LIGHT_EFFECT_TYPE_PLAIN_COLOR, [0xFF, 0x00, 0x00], 0x32, 0x01)
                            await asyncio.sleep(1)

                            # Flashing (Green)
                            await send_light_effect_command(client, char_uuid, LIGHT_EFFECT_TYPE_FLASHING, [0x00, 0xFF, 0x00], 0x46, 0x01)
                            await asyncio.sleep(1)

                            # Rainbow (Blue - color might not be used for rainbow effect, but sending it anyway)
                            await send_light_effect_command(client, char_uuid, LIGHT_EFFECT_TYPE_RAINBOW, [0x00, 0x00, 0xFF], 0x64, 0x01)
                            await asyncio.sleep(2)

                            # --- Attempt to switch to Lightning/Light Mode (set light mode) ---
                            # Per API docs, for DIVOOM_DISP_LIGHT_MODE (data[0]=1) the payload format is:
                            # [data[0]=mode(1), data[1]=R, data[2]=G, data[3]=B, data[4]=brightness, data[5]=effect_mode, data[6]=on_off]
                            # We'll try the canonical 7-byte payload first (no trailing zeros), then fall back to the longer payloads if needed.
                            mode = 0x01  # DIVOOM_DISP_LIGHT_MODE
                            rgb = [0xFF, 0xFF, 0xFF]  # White
                            brightness = 100
                            effect_mode = 0x00  # Plain/solid color
                            power_state = 0x01  # On

                            # Before trying canonical variants, check whether a previous
                            # run (the probe) saved an exact working payload + framing.
                            # If present, try that first so we can quickly verify the
                            # discovered working variant without running the full probe.
                            success_light = False
                            if saved and saved.get("last_successful_payload"):
                                try:
                                    saved_payload_hex = saved.get(
                                        "last_successful_payload", [])
                                    saved_payload = [int(x, 16)
                                                     for x in saved_payload_hex]
                                    saved_use_ios = bool(
                                        saved.get("last_successful_use_ios_le", True))
                                except Exception:
                                    saved_payload = None
                                    saved_use_ios = True

                                if saved_payload:
                                    print(
                                        f"Found saved successful payload; trying it first on {char_uuid} (use_ios_le={saved_use_ios}): {saved_payload}")
                                    ok_saved, ack_saved, raw_saved = await send_command_and_wait_for_ack(
                                        client, char_uuid, 0x45, saved_payload, use_ios_le=saved_use_ios)
                                    if ok_saved:
                                        print(
                                            f"Saved payload succeeded on {char_uuid} (ACK from {ack_saved})")
                                        try:
                                            save_working_mapping(
                                                client, char_uuid, str(ack_saved))
                                        except Exception as e:
                                            print(
                                                f"Failed to save mapping after saved-payload success: {e}")
                                        try:
                                            save_last_successful_payload(
                                                char_uuid, saved_payload, use_ios_le=saved_use_ios)
                                        except Exception:
                                            pass
                                        success_light = True
                                    else:
                                        print(
                                            "Saved payload did not produce ACK; continuing with canonical attempts...")

                            # Build a list of canonical candidate variants to try.
                            # API doc suggests effect_mode=1 is Night Light; try that first,
                            # then fall back to other effect_mode values per the docs.
                            candidate_effect_modes = [
                                0x01, 0x00, 0x02, 0x03, 0x04, 0x05, 0x06]
                            brightness_values = [brightness]

                            print(
                                f"Querying current light mode before change via {char_uuid}...")
                            try:
                                ok_get, sender_get, raw_get = await send_get_light_mode(client, char_uuid)
                                if ok_get:
                                    print(
                                        f"Get light mode response from {sender_get}: {raw_get.hex()}")
                                else:
                                    print(
                                        "No response to Get Light Mode (0x46) query.")
                            except Exception as e:
                                print(f"Error querying light mode: {e}")

                            # Try canonical variants (effect modes prioritized) before fallback
                            success_light = False
                            for em in candidate_effect_modes:
                                for b in brightness_values:
                                    candidate = [mode] + rgb + \
                                        [b, em, power_state]
                                    print(
                                        f"Attempting canonical Light Mode payload to {char_uuid}: {[hex(x) for x in candidate]}")
                                    okL, ackL, rawL = await send_command_and_wait_for_ack(client, char_uuid, 0x45, candidate, use_ios_le=False)
                                    if okL:
                                        print(
                                            f"Light mode set (SPP/canonical) via {char_uuid}, ACK from {ackL}, response={rawL.hex()}")
                                        try:
                                            save_working_mapping(
                                                client, char_uuid, str(ackL))
                                        except Exception as e:
                                            print(
                                                f"Failed to save mapping after canonical success: {e}")
                                        success_light = True
                                        break

                                    print(
                                        "No ACK for canonical Light Mode (SPP); trying iOS-LE framed canonical payload...")
                                    okL2, ackL2, rawL2 = await send_command_and_wait_for_ack(client, char_uuid, 0x45, candidate, use_ios_le=True)
                                    if okL2:
                                        print(
                                            f"Light mode set (iOS-LE/canonical) via {char_uuid}, ACK from {ackL2}, response={rawL2.hex()}")
                                        try:
                                            save_working_mapping(
                                                client, char_uuid, str(ackL2))
                                        except Exception as e:
                                            print(
                                                f"Failed to save mapping after canonical/iOS success: {e}")
                                        success_light = True
                                        break
                                if success_light:
                                    break

                            if not success_light:
                                print(
                                    "Canonical payload did not produce ACK; falling back to broader probe (if enabled) or longer payloads...")
                                # If probe was enabled, the try_lightning_variants will run earlier; otherwise try the longer payload as before
                                long_payload = [
                                    mode] + rgb + [brightness, effect_mode, power_state, 0x00, 0x00, 0x00]
                                print(
                                    f"Attempting legacy/long Light payload: {[hex(x) for x in long_payload]}")
                                okL3, ackL3, rawL3 = await send_command_and_wait_for_ack(client, char_uuid, 0x45, long_payload, use_ios_le=False)
                                if okL3:
                                    print(
                                        f"Light mode set (SPP/long) via {char_uuid}, ACK from {ackL3}, response={rawL3.hex()}")
                                    try:
                                        save_working_mapping(
                                            client, char_uuid, str(ackL3))
                                    except Exception as e:
                                        print(
                                            f"Failed to save mapping after long payload success: {e}")
                                    success_light = True
                                else:
                                    okL4, ackL4, rawL4 = await send_command_and_wait_for_ack(client, char_uuid, 0x45, long_payload, use_ios_le=True)
                                    if okL4:
                                        print(
                                            f"Light mode set (iOS-LE/long) via {char_uuid}, ACK from {ackL4}, response={rawL4.hex()}")
                                        try:
                                            save_working_mapping(
                                                client, char_uuid, str(ackL4))
                                        except Exception as e:
                                            print(
                                                f"Failed to save mapping after long/iOS success: {e}")
                                        success_light = True
                                    else:
                                        print(
                                            f"Failed to set Light mode via {char_uuid} (no ACK from canonical or long payloads)")
                            await asyncio.sleep(1)
                        except Exception as write_e:
                            print(f"Error writing to {char_uuid}: {write_e}")

                    print(f"Disconnected from {timoo_device.name}.")
                else:
                    print(f"Failed to connect to {timoo_device.name}.")
        except Exception as e:
            print(f"An error occurred during connection: {e}")
    else:
        print("No 'Timoo' device found.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--probe-lightning", action="store_true",
                        help="Try a matrix of Lightning (0x45) payload permutations to discover one that elicits an ACK")
    args = parser.parse_args()
    asyncio.run(find_and_connect_timoo(probe_lightning=args.probe_lightning))
