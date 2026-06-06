"""Live device verification: half green / half red image via 0x49 animation."""
import asyncio
import logging
import time
from PIL import Image
from divoom_lib import Divoom
from divoom_lib.utils.discovery import discover_device


async def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
    logger = logging.getLogger("verify_half")

    print("=" * 70)
    print("DOUBLE VERIFY: 16x16 half-green (top) / half-red (bottom)")
    print("=" * 70)

    ble, addr = await discover_device(name_substring="Timoo")
    print(f"Connected to: {addr}")
    divoom = Divoom(mac=addr, logger=logger, use_ios_le_protocol=True)
    await divoom.connect()
    comm = divoom._conn

    print("\n[1/3] Channel check...")
    response = await comm.send_command_and_wait_for_response(0x46, timeout=2.0)
    print(f"   Channel: 0x{response[0]:02x}" if response else "   No response")

    print("\n[2/3] Switching to animation channel (0x45 0x05)...")
    args = [0x05] + [0x00] * 9
    response = await comm.send_command_and_wait_for_response("set light mode", args, timeout=2.0)
    print(f"   Switch response: {response.hex() if response else 'None'}")

    print("\n[3/3] Encoding and pushing half-green/half-red 16x16 (0x49)...")
    img = Image.new("RGB", (16, 16), (0, 0, 0))
    for y in range(16):
        for x in range(16):
            if y < 8:
                img.putpixel((x, y), (0, 255, 0))  # green top
            else:
                img.putpixel((x, y), (255, 0, 0))  # red bottom
    img.save("/tmp/half_green_red.png")

    from divoom_lib.utils.divoom_image_encode import encode_animation
    rgb = img.tobytes()
    frames = [(rgb, 16, 16, 1000)]
    packets = encode_animation(frames)
    print(f"   Packets: {len(packets)}")
    print(f"   First packet first 24 bytes: {packets[0][:24].hex()}")
    print(f"   First packet total size: {len(packets[0])} bytes")

    SET_ANIM = "set animation frame"
    for i, pkt in enumerate(packets):
        t0 = time.time()
        response = await comm.send_command_and_wait_for_response(SET_ANIM, list(pkt), timeout=5.0)
        elapsed = time.time() - t0
        print(f"   packet {i}: response={response.hex() if response else 'None'} ({elapsed:.2f}s)")

    print("\n" + "=" * 70)
    print("PLEASE OBSERVE THE TIMOO SCREEN")
    print("=" * 70)
    print("Expected: GREEN on the top 8 rows, RED on the bottom 8 rows.")
    print()
    print("If correct: encoder + display path are confirmed working.")
    print("If not: something is wrong with the encoder or device state.")
    print()

    await divoom.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
