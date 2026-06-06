"""Live test: push a smaller .bin file (8 frames, 769 bytes) via 0x49.

This is the smallest Magic 9 file in the cache. Should be quick to test.
"""
import asyncio
import logging
from pathlib import Path
from divoom_lib import Divoom
from divoom_lib.utils.discovery import discover_device


CACHE_GALLERY = Path.home() / ".config" / "divoom-control" / "cache_gallery"
CHUNK_SIZE = 200


def encode_bin_as_packets(bin_data: bytes) -> list[bytes]:
    total_len = len(bin_data) & 0xFFFF
    packets: list[bytes] = []
    for i, offset in enumerate(range(0, len(bin_data), CHUNK_SIZE), start=1):
        chunk = bin_data[offset:offset + CHUNK_SIZE]
        packet = total_len.to_bytes(2, "little") + bytes([i & 0xFF]) + chunk
        packets.append(packet)
    return packets


async def main() -> None:
    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger("verify_bin_small")

    # Find smallest Magic 9 file
    candidates = sorted(CACHE_GALLERY.glob("*.bin"), key=lambda p: p.stat().st_size)
    bin_path = None
    for p in candidates:
        data = p.read_bytes()
        if data[:1] == b"\x09":
            bin_path = p
            break
    if not bin_path:
        print("No Magic 9 file found")
        return
    bin_data = bin_path.read_bytes()
    print(f"File: {bin_path.name}")
    print(f"  size: {len(bin_data)} bytes")
    print(f"  magic={bin_data[0]} frames={bin_data[1]} speed={(bin_data[2]<<8)|bin_data[3]}")
    packets = encode_bin_as_packets(bin_data)
    print(f"  packets: {len(packets)}")

    ble, addr = await discover_device(name_substring="Timoo")
    if not ble:
        return
    divoom = Divoom(mac=addr, logger=logger, use_ios_le_protocol=True)
    await divoom.connect()
    comm = divoom._conn

    # Switch to animation channel
    await divoom.display.show_design()
    await asyncio.sleep(0.5)

    # Push
    print(f"\nUploading {len(packets)} packets...")
    for i, pkt in enumerate(packets):
        await comm.send_command("set animation frame", list(pkt))
        await asyncio.sleep(0.03)
    print("Done uploading.")

    await asyncio.sleep(3.0)
    print("\nOBSERVE: Timoo should now show the cached animation.")
    await divoom.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
