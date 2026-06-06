"""Live device verification for the new image encoder.

Usage:
    python3 verify_encoder_live.py
"""
import asyncio
import logging
import time
from PIL import Image, ImageDraw
from divoom_lib import Divoom
from divoom_lib.utils.discovery import discover_device


def make_test_image(out_path: str, pattern: str = "quad") -> tuple[bytes, int, int]:
    """Create a clearly-distinguishable test image (16x16, 4-color quadrant)."""
    img = Image.new("RGB", (16, 16), (0, 0, 0))
    draw = ImageDraw.Draw(img)
    if pattern == "quad":
        # 4-color quadrants: red, green, blue, yellow
        draw.rectangle([(0, 0), (7, 7)], fill=(255, 0, 0))
        draw.rectangle([(8, 0), (15, 7)], fill=(0, 255, 0))
        draw.rectangle([(0, 8), (7, 15)], fill=(0, 0, 255))
        draw.rectangle([(8, 8), (15, 15)], fill=(255, 255, 0))
    elif pattern == "checker":
        for y in range(16):
            for x in range(16):
                if (x + y) % 2 == 0:
                    img.putpixel((x, y), (255, 255, 255))
                else:
                    img.putpixel((x, y), (0, 0, 0))
    elif pattern == "single_red":
        img = Image.new("RGB", (16, 16), (255, 0, 0))
    img.save(out_path)
    return img.tobytes(), 16, 16


async def main():
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s"
    )
    logger = logging.getLogger("verify_encoder_live")

    print("=" * 70)
    print("LIVE ENCODER VERIFICATION ON TIMOO")
    print("=" * 70)

    ble, addr = await discover_device(name_substring="Timoo")
    if not ble:
        print("No Timoo found")
        return
    print(f"Connected to: {addr}")
    divoom = Divoom(mac=addr, logger=logger, use_ios_le_protocol=True)
    await divoom.connect()
    comm = divoom._conn

    # Step 1: confirm device is on Animation channel via 0x46
    print("\n[1/4] Verifying device is on Animation channel (0x46)...")
    response = await comm.send_command_and_wait_for_response(0x46, timeout=2.0)
    if response and len(response) >= 1:
        current_channel = response[0]
        print(f"   ✓ Current channel: 0x{current_channel:02x} ({'Animation' if current_channel == 5 else 'other'})")
        if current_channel != 0x05:
            print("   ⚠ Device is NOT on Animation channel. Sending 0x45 0x05...")
            await divoom.display.show_design()
            await asyncio.sleep(0.5)
            response = await comm.send_command_and_wait_for_response(0x46, timeout=2.0)
            if response:
                current_channel = response[0]
                print(f"   ✓ Channel after switch: 0x{current_channel:02x}")
    else:
        print("   ✗ No response to 0x46")
        return

    # Step 2: encode a test image with the new encoder
    print("\n[2/4] Encoding test image with new encoder...")
    from divoom_lib.utils.divoom_image_encode import encode_static_image
    rgb, w, h = make_test_image("/tmp/verify_quad.png", pattern="quad")
    payload = encode_static_image(rgb, w, h)
    print(f"   ✓ Encoded {w}x{h} quad image → {len(payload)} bytes")
    print(f"   Header: {payload[:10].hex()}")
    print(f"   NN (num colors): {payload[9]}")
    print(f"   Palette: {payload[10:10+3*payload[9]].hex() if payload[9] > 0 else 'NN=0 (256 colors)'}")

    # Step 3: send the 0x44 image push directly via low-level send_command
    print("\n[3/4] Sending 0x44 image push (with preceding 0x45 0x05 channel switch)...")
    t0 = time.time()
    result = await divoom.display.show_image("/tmp/verify_quad.png")
    elapsed = time.time() - t0
    print(f"   ✓ show_image result: {result} (took {elapsed:.2f}s)")

    # Step 4: wait + poll the device for the response
    print("\n[4/4] Polling device state after push...")
    for i in range(4):
        await asyncio.sleep(0.5)
        response = await comm.send_command_and_wait_for_response(0x46, timeout=2.0)
        if response and len(response) >= 1:
            print(f"   t={(i+1)*0.5:.1f}s: channel=0x{response[0]:02x}")
        else:
            print(f"   t={(i+1)*0.5:.1f}s: no response")

    print("\n" + "=" * 70)
    print("PLEASE OBSERVE THE TIMOO SCREEN")
    print("=" * 70)
    print("Expected: 4-color quadrants — red (top-left), green (top-right),")
    print("          blue (bottom-left), yellow (bottom-right).")
    print()
    print("If the device shows the quadrants: the encoder is WORKING.")
    print("If the device shows nothing / a spinner / the previous screen: failure.")
    print()

    await divoom.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
