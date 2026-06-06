"""Live device test: 3-frame animation cycling on Timoo.

Verifies the fix for the `set animation frame` → 0x49 remap. Before the fix,
multi-frame animations were sent with command 0x44, which made the device
render only the first frame. After the fix, the device should cycle through
all 3 frames at 500ms each.
"""
import asyncio
import logging
from PIL import Image, ImageDraw
from divoom_lib import Divoom
from divoom_lib.utils.discovery import discover_device
from divoom_lib.utils.divoom_image_encode import encode_animation


def make_frame(color: tuple[int, int, int]) -> tuple[bytes, int, int]:
    img = Image.new("RGB", (16, 16), color)
    return img.tobytes(), 16, 16


async def main() -> None:
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s"
    )
    logger = logging.getLogger("verify_anim_3frame")

    print("=" * 70)
    print("LIVE 3-FRAME ANIMATION TEST ON TIMOO (post-fix)")
    print("=" * 70)

    ble, addr = await discover_device(name_substring="Timoo")
    if not ble:
        print("No Timoo found")
        return
    print(f"Connected to: {addr}")
    divoom = Divoom(mac=addr, logger=logger, use_ios_le_protocol=True)
    await divoom.connect()
    comm = divoom._conn

    # 1. Switch to Animation channel
    print("\n[1/3] Switching to Animation channel...")
    await divoom.display.show_design()
    await asyncio.sleep(0.5)
    ch = await comm.send_command_and_wait_for_response(0x46, timeout=2.0)
    print(f"   channel after switch: 0x{ch[0]:02x}" if ch else "   no response")

    # 2. Encode 3 frames (red, green, blue, 500ms each)
    print("\n[2/3] Encoding 3-frame animation (red, green, blue, 500ms)...")
    frames = [
        (*make_frame((255, 0, 0)), 500),
        (*make_frame((0, 255, 0)), 500),
        (*make_frame((0, 0, 255)), 500),
    ]
    packets = encode_animation(frames)
    for i, pkt in enumerate(packets):
        print(f"   packet {i+1}: {len(pkt)} bytes, header: {pkt[:8].hex()}")

    # 3. Send each packet (now uses command 0x49, post-fix)
    print("\n[3/3] Sending packets via 'set animation frame' (now → 0x49)...")
    for i, pkt in enumerate(packets):
        ok = await comm.send_command("set animation frame", list(pkt))
        print(f"   packet {i+1}: sent ok={ok}")
        await asyncio.sleep(0.05)  # small gap to avoid BLE race

    print("\n" + "=" * 70)
    print("PLEASE OBSERVE THE TIMOO SCREEN FOR 5 SECONDS")
    print("Expected: cycling red → green → blue at 500ms intervals.")
    print("=" * 70)

    await divoom.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
