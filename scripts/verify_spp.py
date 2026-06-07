"""Live device verification via SPP basic protocol with byte capture."""
import asyncio
import logging
import time
from PIL import Image, ImageDraw
from divoom_lib import Divoom
from divoom_lib.utils.discovery import discover_device
from divoom_lib.models import COMMANDS


async def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
    logger = logging.getLogger("verify_spp")

    print("=" * 70)
    print("LIVE ENCODER VERIFICATION — SPP / BASIC PROTOCOL")
    print("=" * 70)

    ble, addr = await discover_device(name_substring="Timoo")
    print(f"Connected to: {addr}")
    divoom = Divoom(mac=addr, logger=logger, use_ios_le_protocol=False)
    await divoom.connect()
    comm = divoom._conn

    # 1. Channel check
    print("\n[1/3] Channel check...")
    response = await comm.send_command_and_wait_for_response(0x46, timeout=2.0)
    if response:
        print(f"   Channel: 0x{response[0]:02x}")
    else:
        print("   No response")

    # 2. Switch to animation
    print("\n[2/3] Switching to animation channel (0x45 0x05)...")
    args = [0x05] + [0x00] * 9
    response = await comm.send_command_and_wait_for_response("set light mode", args, timeout=2.0)
    print(f"   Switch response: {response.hex() if response else 'None'}")

    # 3. Encode + push
    print("\n[3/3] Encoding and pushing 16x16 quadrant (0x44)...")
    img = Image.new("RGB", (16, 16), (0, 0, 0))
    draw = ImageDraw.Draw(img)
    draw.rectangle([(0, 0), (7, 7)], fill=(255, 0, 0))
    draw.rectangle([(8, 0), (15, 7)], fill=(0, 255, 0))
    draw.rectangle([(0, 8), (7, 15)], fill=(0, 0, 255))
    draw.rectangle([(8, 8), (15, 15)], fill=(255, 255, 0))

    from divoom_lib.utils.divoom_image_encode import encode_static_image
    rgb = img.tobytes()
    payload = encode_static_image(rgb, 16, 16)
    print(f"   Payload: {len(payload)} bytes")
    print(f"   Header: {payload[:7].hex()}")

    t0 = time.time()
    response = await comm.send_command_and_wait_for_response(
        "set image", list(payload), timeout=5.0
    )
    elapsed = time.time() - t0
    print(f"   Push response: {response.hex() if response else 'None'} ({elapsed:.2f}s)")

    print("\n" + "=" * 70)
    print("PLEASE OBSERVE THE TIMOO SCREEN")
    print("=" * 70)
    print("Expected: 4-color quadrants — red, green, blue, yellow")
    print()

    await divoom.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
