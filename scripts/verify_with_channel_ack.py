"""Live device verification with explicit channel-switch + ACK + 0x46 confirmation."""
import asyncio
import logging
import time
from PIL import Image, ImageDraw
from divoom_lib import Divoom
from divoom_lib.utils.discovery import discover_device
from divoom_lib.models import COMMANDS


async def get_current_channel(comm, timeout: float = 2.0) -> int | None:
    response = await comm.send_command_and_wait_for_response(0x46, timeout=timeout)
    if response and len(response) >= 1:
        return response[0]
    return None


async def switch_to_animation(comm) -> bool:
    """Send 0x45 0x05 with response-wait and verify via 0x46."""
    SET_LIGHT_MODE = COMMANDS["set light mode"]
    args = [0x05] + [0x00] * 9
    response = await comm.send_command_and_wait_for_response(
        SET_LIGHT_MODE, args, timeout=2.0
    )
    if response is None:
        return False
    await asyncio.sleep(0.2)
    ch = await get_current_channel(comm)
    return ch == 0x05


async def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
    logger = logging.getLogger("verify_channel")

    print("=" * 70)
    print("LIVE ENCODER VERIFICATION — EXPLICIT CHANNEL-SWITCH + ACK")
    print("=" * 70)

    ble, addr = await discover_device(name_substring="Timoo")
    if not ble:
        print("No Timoo found")
        return
    print(f"Connected to: {addr}")
    divoom = Divoom(mac=addr, logger=logger, use_ios_le_protocol=True)
    await divoom.connect()
    comm = divoom._conn

    # 1. Initial channel state
    print("\n[1/5] Initial channel check...")
    ch = await get_current_channel(comm)
    print(f"   Channel = 0x{ch:02x}" if ch is not None else "   No response")

    # Hook notification handler to capture raw bytes
    raw_notifications = []
    original_handler = comm.notification_handler
    def capture_handler(sender, data):
        raw_notifications.append(bytes(data))
        if original_handler:
            return original_handler(sender, data)
    comm.notification_handler = capture_handler

    # 2. Explicit channel switch with ACK
    print("\n[2/5] Switching to Animation channel (0x45 0x05) with ACK-wait...")
    ok = await switch_to_animation(comm)
    print(f"   Switch OK: {ok}")
    ch = await get_current_channel(comm)
    print(f"   Channel after switch: 0x{ch:02x}" if ch is not None else "   No response")

    # 3. Encode + push the test image as 0x49 animation (1-frame)
    print("\n[3/5] Encoding and pushing 1-frame animation (0x49)...")
    from divoom_lib.utils.divoom_image_encode import encode_animation
    img = Image.new("RGB", (16, 16), (0, 0, 0))
    draw = ImageDraw.Draw(img)
    draw.rectangle([(0, 0), (7, 7)], fill=(255, 0, 0))
    draw.rectangle([(8, 0), (15, 7)], fill=(0, 255, 0))
    draw.rectangle([(0, 8), (7, 15)], fill=(0, 0, 255))
    draw.rectangle([(8, 8), (15, 15)], fill=(255, 255, 0))
    rgb = img.tobytes()
    frames = [(rgb, 16, 16, 1000)]
    packets = encode_animation(frames)
    print(f"   Total packets: {len(packets)}")
    for i, pkt in enumerate(packets):
        print(f"   packet {i}: {len(pkt)} bytes, header: {pkt[:8].hex()}")

    SET_ANIM = COMMANDS["set animation frame"]
    for i, pkt in enumerate(packets):
        t0 = time.time()
        response = await comm.send_command_and_wait_for_response(
            SET_ANIM, list(pkt), timeout=5.0
        )
        elapsed = time.time() - t0
        print(f"   packet {i}: response={response.hex() if response else 'None'} ({elapsed:.2f}s)")

    # 4. Poll the device state
    print("\n[4/5] Polling channel state after push...")
    for i in range(4):
        await asyncio.sleep(0.5)
        ch = await get_current_channel(comm)
        print(f"   t={(i+1)*0.5:.1f}s: channel=0x{ch:02x}" if ch is not None else f"   t={(i+1)*0.5:.1f}s: no response")

    # 4b. Dump all raw notifications captured
    print(f"\n[4b/5] Raw notifications captured: {len(raw_notifications)}")
    for idx, n in enumerate(raw_notifications[-10:]):
        print(f"   [{idx}] {n.hex()}")

    # 5. Dump what show_image does for comparison
    print("\n[5/5] Direct byte dump of what we sent (first 32 bytes)...")
    # Reconstruct the BLE packet the way it goes out
    print(f"   0x44 payload first 32 bytes: {payload[:32].hex()}")

    print("\n" + "=" * 70)
    print("PLEASE OBSERVE THE TIMOO SCREEN")
    print("=" * 70)
    print("Expected: 4-color quadrants — red (top-left), green (top-right),")
    print("          blue (bottom-left), yellow (bottom-right).")
    print()
    print("If the device shows the quadrants: the encoder is WORKING.")
    print("If the device shows nothing: failure.")
    print()

    await divoom.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
