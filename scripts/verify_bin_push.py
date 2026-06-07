"""Live test: push a Magic 9 .bin file from cache directly via 0x49.

The cache_gallery/*.bin files are device-native Magic 9 format (encrypted).
If 0x49 accepts this format directly, the device should play the animation.

This tests the hypothesis: 0x49 expects the Magic 9 format, NOT the
RomRider palette+pixel format. If it works, we know the device's
animation channel expects this format and we need to build a Magic 9
encoder (with AES-CBC encryption) for our pipeline.
"""
import asyncio
import logging
from pathlib import Path
from divoom_lib import Divoom
from divoom_lib.utils.discovery import discover_device


CACHE_GALLERY = Path.home() / ".config" / "divoom-control" / "cache_gallery"
CHUNK_SIZE = 200


def encode_bin_as_packets(bin_data: bytes) -> list[bytes]:
    """Wrap a .bin file as 0x49 packets: [LE u16 total_len][u8 packet_num][chunk]."""
    total_len = len(bin_data) & 0xFFFF
    packets: list[bytes] = []
    for i, offset in enumerate(range(0, len(bin_data), CHUNK_SIZE), start=1):
        chunk = bin_data[offset:offset + CHUNK_SIZE]
        packet = total_len.to_bytes(2, "little") + bytes([i & 0xFF]) + chunk
        packets.append(packet)
    return packets


async def main() -> None:
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s"
    )
    logger = logging.getLogger("verify_bin_push")

    print("=" * 70)
    print("LIVE TEST: push a real .bin file from cache via 0x49")
    print("=" * 70)

    # Pick a small Magic 9 file (32 frames, 16x16)
    bin_path = CACHE_GALLERY / "group1_M00_02_B9_Ci0s8Wes4KWEKjNNAAAAAIeLeRw5898550.bin"
    if not bin_path.exists():
        print(f"File not found: {bin_path}")
        return
    bin_data = bin_path.read_bytes()
    magic, total_frames = bin_data[0], bin_data[1]
    speed = (bin_data[2] << 8) | bin_data[3]
    print(f"\nFile: {bin_path.name}")
    print(f"  size: {len(bin_data)} bytes")
    print(f"  magic: {magic}, frames: {total_frames}, speed: {speed}ms")
    print(f"  header: {bin_data[:4].hex()}")

    packets = encode_bin_as_packets(bin_data)
    print(f"  packets: {len(packets)} × ≤{CHUNK_SIZE + 3} bytes")

    ble, addr = await discover_device(name_substring="Timoo")
    if not ble:
        print("No Timoo found")
        return
    divoom = Divoom(mac=addr, logger=logger, use_ios_le_protocol=True)
    await divoom.connect()
    comm = divoom._conn

    # 1. Switch to animation channel
    print("\n[1/3] Switch to Animation channel")
    await divoom.display.show_design()
    await asyncio.sleep(0.5)

    # 2. Upload via 0x49
    print(f"\n[2/3] Upload {len(packets)} packets via 0x49")
    for i, pkt in enumerate(packets):
        await comm.send_command("set animation frame", list(pkt))
        print(f"   packet {i+1}/{len(packets)} sent ({len(pkt)} bytes)")
        await asyncio.sleep(0.03)

    # 3. Wait + observe
    print("\n[3/3] Waiting 4s for device to react...")
    await asyncio.sleep(4.0)

    print("\n" + "=" * 70)
    print("OBSERVE: should now show the cached animation (a 'no parking'")
    print("sign at 128x128, scaled down to 16x16 on Timoo).")
    print("=" * 70)

    await divoom.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
