#!/usr/bin/env python3
import struct
from pathlib import Path

def print_info(message):
    """Prints an informational message."""
    print(f"[ ==> ] {message}")

def print_wrn(message):
    """Prints a warning message."""
    print(f"[ Wrn ] {message}")

def print_err(message):
    """Prints an error message."""
    print(f"[ Err ] {message}")

def print_ok(message):
    """Prints a success message."""
    print(f"[ Ok  ] {message}")

def main():
    bin_path = Path("/Users/ztomer/Projects/divoom-control/api_scraper/divoom_docs/test_download.bin")
    if not bin_path.exists():
        print_err(f"File not found: {bin_path}")
        return

    data = bin_path.read_bytes()
    print_info(f"Loaded {len(data)} bytes from {bin_path}")
    print_info(f"First 20 bytes (hex): {data[:20].hex()}")

    magic = data[0]
    print_info(f"Magic byte: {magic} (hex: {hex(magic)})")

    if magic == 43: # 0x2b
        print_ok("Magic byte is 43 (0x2b) - Parsing as GIF container!")
        # Let's inspect the bytes around offset 6
        # text_len at offset 6 is 4 bytes
        if len(data) < 10:
            print_err("File too small to parse headers")
            return
        
        text_len = struct.unpack("<I", data[6:10])[0]
        print_info(f"Parsed text_len: {text_len}")

        # Check offsets
        text_start = 10
        text_end = text_start + text_len
        print_info(f"Text content: {repr(data[text_start:text_end])}")

        gif_len_offset = text_end
        if len(data) < gif_len_offset + 4:
            print_err("File too small to read gif_len")
            return

        gif_len = struct.unpack("<I", data[gif_len_offset:gif_len_offset+4])[0]
        print_info(f"Parsed gif_len: {gif_len}")

        gif_start = gif_len_offset + 4
        gif_end = gif_start + gif_len
        print_info(f"GIF bytes size in file: {len(data) - gif_start}")

        if gif_end > len(data):
            print_wrn(f"gif_end ({gif_end}) exceeds file length ({len(data)}), truncating to file end")
            gif_end = len(data)

        gif_data = data[gif_start:gif_end]
        print_info(f"Extracted {len(gif_data)} bytes of GIF data")
        print_info(f"GIF header: {gif_data[:6]}")

        if gif_data.startswith(b"GIF89a") or gif_data.startswith(b"GIF87a"):
            print_ok("Successfully extracted a valid GIF file!")
            out_path = bin_path.parent / "extracted_test.gif"
            out_path.write_bytes(gif_data)
            print_ok(f"Saved extracted GIF to {out_path}")
        else:
            print_err("Extracted data does not start with GIF magic bytes")
    else:
        print_wrn(f"Unhandled magic byte: {magic}")

if __name__ == "__main__":
    main()
