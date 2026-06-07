"""Live device test: 3-frame animation with movie play trigger.

Tests the hypothesis that 0x49 is just the upload, and we need 0x6E 0x01
to actually trigger playback. The Timoo firmware (per APK SPP path
in F2/c.java:345-347) does:
    1. 0x6E 0x01 — start movie mode
    2. upload animation data (via SPP z1 or BLE 0x49/0x5C)
    3. 0x6E ...  — set speed
"""
import asyncio
import logging
from PIL import Image
from divoom_lib import Divoom
from divoom_lib.utils.discovery import discover_device
from divoom_lib.utils.divoom_image_encode import encode_animation
from divoom_lib.models.commands import COMMANDS


def make_frame(color: tuple[int, int, int]) -> tuple[bytes, int, int]:
    img = Image.new("RGB", (16, 16), color)
    return img.tobytes(), 16, 16


async def main() -> None:
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s"
    )
    logger = logging.getLogger("verify_anim_movie")

    print("=" * 70)
    print("LIVE MOVIE-PLAY TEST: 0x49 upload + 0x6E trigger")
    print("=" * 70)

    ble, addr = await discover_device(name_substring="Timoo")
    if not ble:
        print("No Timoo found")
        return
    divoom = Divoom(mac=addr, logger=logger, use_ios_le_protocol=True)
    await divoom.connect()
    comm = divoom._conn

    # 1. Switch to animation channel
    print("\n[1/5] Switch to Animation channel")
    await divoom.display.show_design()
    await asyncio.sleep(0.5)
    ch = await comm.send_command_and_wait_for_response(0x46, timeout=2.0)
    print(f"   channel: 0x{ch[0]:02x}" if ch else "   no response")

    # 2. Encode 3 frames
    print("\n[2/5] Encode 3-frame animation (R/G/B, 500ms)")
    frames = [
        (*make_frame((255, 0, 0)), 500),
        (*make_frame((0, 255, 0)), 500),
        (*make_frame((0, 0, 255)), 500),
    ]
    packets = encode_animation(frames)
    for i, pkt in enumerate(packets):
        print(f"   packet {i+1}: {len(pkt)} bytes")

    # 3. Upload via 0x49
    print("\n[3/5] Upload via 0x49 (set animation frame)")
    for i, pkt in enumerate(packets):
        await comm.send_command("set animation frame", list(pkt))
        print(f"   packet {i+1} sent")
        await asyncio.sleep(0.05)

    # 4. Trigger playback via 0x6E 0x01
    print("\n[4/5] Trigger playback: 0x6E + 0x01")
    resp = await comm.send_command_and_wait_for_response(0x6E, [0x01], timeout=3.0)
    print(f"   response: {resp.hex() if resp else 'None'}")

    await asyncio.sleep(2.0)
    print("\n" + "=" * 70)
    print("OBSERVE: should be cycling R/G/B. If still showing old animation,")
    print("try sending 0x6E 0x00 (exit) then 0x6E 0x01 (start) first.")
    print("=" * 70)

    await divoom.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
