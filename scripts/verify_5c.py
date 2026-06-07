"""Live test: try 0x6E first, then 0x5C with raw animation data.

Hypothesis: Timoo needs:
    1. 0x6E 0x01 — enter/start movie mode
    2. 0x5C — upload animation data (raw concatenated frames, no packet header)
    3. 0x6E 0x01 — actually start playback

Or maybe 0x5B (single screen encode) works.
"""
import asyncio
import logging
from PIL import Image
from divoom_lib import Divoom
from divoom_lib.utils.discovery import discover_device
from divoom_lib.utils.divoom_image_encode import (
    encode_animation_frame, encode_animation,
)


def make_frame(color: tuple[int, int, int]) -> tuple[bytes, int, int]:
    img = Image.new("RGB", (16, 16), color)
    return img.tobytes(), 16, 16


async def main() -> None:
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s"
    )
    logger = logging.getLogger("verify_5c")

    print("=" * 70)
    print("LIVE TEST: 0x6E start + 0x5C upload + 0x6E start")
    print("=" * 70)

    ble, addr = await discover_device(name_substring="Timoo")
    if not ble:
        print("No Timoo found")
        return
    divoom = Divoom(mac=addr, logger=logger, use_ios_le_protocol=True)
    await divoom.connect()
    comm = divoom._conn

    # Build raw concatenated frame data (no packet header, just frames)
    print("\n[Setup] Encoding raw concatenated frame data...")
    frames = [
        (*make_frame((255, 0, 0)), 500),
        (*make_frame((0, 255, 0)), 500),
        (*make_frame((0, 0, 255)), 500),
    ]
    raw_data = b"".join(encode_animation_frame(rgb, w, h, t) for rgb, w, h, t in frames)
    print(f"   raw_data: {len(raw_data)} bytes")
    print(f"   first 16 bytes: {raw_data[:16].hex()}")

    # 1. Switch to animation channel
    print("\n[1] Switch to Animation channel (0x45 0x05)")
    await divoom.display.show_design()
    await asyncio.sleep(0.5)
    ch = await comm.send_command_and_wait_for_response(0x46, timeout=2.0)
    print(f"   channel: 0x{ch[0]:02x}" if ch else "   no response")

    # 2. Send 0x6E 0x01 to enter movie mode
    print("\n[2] 0x6E 0x01 — enter movie mode")
    await comm.send_command(0x6E, [0x01])
    await asyncio.sleep(0.2)

    # 3. Upload via 0x5C (screen_id=0, total_length=N, pic_id=0, data=raw)
    print(f"\n[3] 0x5C — upload animation: screen_id=0, total_length={len(raw_data)}, pic_id=0")
    await comm.send_command(0x5C, [0x00] + list(len(raw_data).to_bytes(2, "little")) + [0x00] + list(raw_data))
    await asyncio.sleep(0.5)

    # 4. Trigger playback
    print("\n[4] 0x6E 0x01 — start playback")
    await comm.send_command(0x6E, [0x01])
    await asyncio.sleep(0.5)

    # 5. Also try 0x6B (mul encode gif play)
    print("\n[5] 0x6B (mul encode gif play) — try this too")
    await comm.send_command(0x6B, [])

    await asyncio.sleep(2.0)
    print("\n" + "=" * 70)
    print("OBSERVE: any cycling?")
    print("=" * 70)

    await divoom.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
