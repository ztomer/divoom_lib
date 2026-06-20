import asyncio
import logging
from bleak import BleakScanner, BleakClient
from bleak.exc import BleakError

logger = logging.getLogger(__name__)

# Known Divoom product-name keywords (lowercase). A scanned BLE peripheral is
# treated as a Divoom only if its advertised name contains one of these. Keep
# this list as the single source of truth for "is this a Divoom?" — extend it
# if a real device shows up named something not covered here.
DIVOOM_NAME_KEYWORDS = (
    "divoom",
    "timoo",
    "tivoo",
    "timebox",
    "pixoo",
    "ditoo",
    "backpack",
    "timegate",
    "aurabox",
    "planet",
)


def is_divoom_name(name: str | None) -> bool:
    """True if a BLE advertised name looks like a Divoom device."""
    if not name:
        return False
    lowered = name.lower()
    return any(kw in lowered for kw in DIVOOM_NAME_KEYWORDS)


async def discover_device(name_substring: str | None = None, address: str | None = None) -> tuple[BleakClient | str | None, str | None]:
    """
    Discovers a BLE device by name substring or address.
    Returns a tuple of (ble_device, device_id).
    """
    ble_device = None
    device_id = None

    if not address:
        logger.info(f"Scanning for Bluetooth devices searching for name containing '{name_substring}' (timeout=10.0s)...")
        devices = await BleakScanner.discover(timeout=10.0)
        found = None
        for d in devices:
            if d.name and name_substring and name_substring.lower() in d.name.lower():
                found = d
                break
        if not found:
            logger.error(f"No Bluetooth device found with name containing '{name_substring}'.")
            return None, None
        logger.info(f"Found device: {found.name} ({found.address}) — using this device.")
        ble_device = found
    else:
        logger.info(f"Resolving address {address} to BLEDevice (short scan)...")
        devices = await BleakScanner.discover(timeout=3.0)
        resolved = None
        for d in devices:
            if d.address == address or (d.name and address.lower() in d.name.lower()):
                resolved = d
                break
        if resolved:
            logger.info(f"Resolved address to BLEDevice: {resolved.name} ({resolved.address})")
            ble_device = resolved
        else:
            logger.warning("Could not resolve address to BLEDevice quickly; will attempt connect using raw address string.")
            ble_device = address

    if hasattr(ble_device, "address"):
        device_id = ble_device.address
    else:
        device_id = ble_device
    
    return ble_device, device_id

async def discover_characteristics(client: BleakClient) -> tuple[list, list, list]:
    """
    Discovers writeable, notify, and readable characteristics for a connected client.
    Returns a tuple of (write_chars, notify_chars, read_chars).
    """
    # Ensure service discovery finished; some backends (CoreBluetooth) can be
    # racy. Try a few short waits, then call get_services() as a fallback.
    # Wait for services to populate. Accessing client.services can raise
    # BleakError if discovery hasn't completed; handle that and poll a bit.
    tries = 0
    services_present = False
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
            logger.warning("Service discovery did not populate `client.services` after waiting; continuing but operations may fail.")

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
    return write_chars, notify_chars, read_chars

def pick_char_uuid(preferred_uuid: str | None, candidates: list, prefix_hint: str | None = '49535343') -> str | None:
    """
    Helper to pick a matching characteristic UUID from discovered list,
    prioritizing characteristics with both write and notify properties.
    """
    # 1. If a preferred_uuid is provided, try to match it exactly
    if preferred_uuid:
        for c in candidates:
            if c.uuid == preferred_uuid:
                return c.uuid

    # 2. Prioritize characteristics with both 'write' and 'notify' properties
    #    and matching the prefix hint
    write_notify_candidates_with_hint = []
    write_notify_candidates_no_hint = []

    for c in candidates:
        props = set(c.properties or [])
        is_writeable = 'write' in props or 'write-without-response' in props
        is_notifiable = 'notify' in props

        if is_writeable and is_notifiable:
            if prefix_hint and c.uuid.lower().startswith(prefix_hint.lower()):
                write_notify_candidates_with_hint.append(c.uuid)
            else:
                write_notify_candidates_no_hint.append(c.uuid)
    
    if write_notify_candidates_with_hint:
        return write_notify_candidates_with_hint[0]
    if write_notify_candidates_no_hint:
        return write_notify_candidates_no_hint[0]

    # 3. Fallback to existing logic: prefer ones that match prefix_hint (write-only or notify-only)
    if prefix_hint:
        for c in candidates:
            if c.uuid.lower().startswith(prefix_hint.lower()):
                return c.uuid
    
    # 4. Final fallback: return the first candidate if any
    return candidates[0].uuid if candidates else None


async def discover_all_divoom_devices(timeout: float = 5.0, expected: int = 0) -> list[dict]:
    """
    Scans BLE devices and returns a list of discovered Divoom devices.
    Matches devices by known Divoom name prefixes.

    Uses a live detection callback with **early-exit**: as soon as ``expected``
    distinct Divoom devices have been seen it stops scanning and returns, instead
    of always burning the full ``timeout`` (the old ``BleakScanner.discover(timeout)``
    waited the whole window even when every device showed up in the first 2s).
    ``expected<=0`` disables early-exit (scan the full window — used when the count
    is unknown and we want to find as many as possible). The scanner is always
    stopped in ``finally`` so a cancelled/early-exited scan never leaks the OS scan.

    No fallback to "all named devices": a Divoom-only control app must not list
    every random BLE peripheral (headphones, watches, etc.) in range. If a device
    is missing, it's powered off, out of range, or *currently connected* (a
    connected peripheral stops advertising) — or its name needs adding to
    DIVOOM_NAME_KEYWORDS.
    """
    logger.info(
        "Scanning for Divoom BLE devices (timeout=%.1fs, early-exit at %s)...",
        timeout, expected if expected > 0 else "off")

    found: dict[str, dict] = {}            # address -> {name, address}, deduped
    done = asyncio.Event()

    def _on_detect(device, _adv):
        if device.name and is_divoom_name(device.name) and device.address not in found:
            found[device.address] = {"name": device.name, "address": device.address}
            logger.info("Found Divoom device: %s (%s)", device.name, device.address)
            if expected > 0 and len(found) >= expected:
                done.set()                 # early-exit: we have them all

    scanner = BleakScanner(detection_callback=_on_detect)
    try:
        await asyncio.wait_for(scanner.start(), timeout=10.0)
        try:
            await asyncio.wait_for(done.wait(), timeout=timeout)
        except asyncio.TimeoutError:
            pass                           # window elapsed — return whatever we found
    finally:
        try:
            await asyncio.wait_for(scanner.stop(), timeout=5.0)
        except (asyncio.TimeoutError, BleakError, Exception) as e:
            logger.warning("scanner stop failed/timed out: %s", e)

    results = list(found.values())
    logger.info("Discovered %d Divoom BLE device(s).", len(results))
    return results