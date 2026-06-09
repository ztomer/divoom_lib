import struct
import logging
from pathlib import Path
import ctypes

from .native_lib import library_path

logger = logging.getLogger("divoom_gui")

# Dynamically load native C shared library for fast pixel tile compacting
lib = None
try:
    lib_path = library_path()
    if lib_path.exists():
        lib = ctypes.CDLL(str(lib_path))
        lib.compact_tiles.argtypes = [
            ctypes.POINTER(ctypes.c_ubyte),  # const unsigned char* frame_data
            ctypes.c_int,                    # int frame_data_len
            ctypes.POINTER(ctypes.c_ubyte),  # unsigned char* output_pixels
            ctypes.c_int,                    # int row_count
            ctypes.c_int                     # int column_count
        ]
        lib.compact_tiles.restype = None
        logger.info("Successfully loaded native C compacting library!")
except Exception as e:
    logger.warning(f"Failed to load native compact library, using pure python fallback: {e}")

def extract_image_from_magic_43(file_data: bytes) -> tuple[bytes, str] | None:
    """Extracts raw GIF/PNG/JPG from Divoom Magic 43 payload."""
    if len(file_data) < 10 or file_data[0] != 43:
        return None
    try:
        text_len = struct.unpack("<I", file_data[6:10])[0]
        text_start = 10
        text_end = text_start + text_len
        
        img_len_offset = text_end
        if len(file_data) < img_len_offset + 4:
            return None
            
        img_len = struct.unpack("<I", file_data[img_len_offset:img_len_offset+4])[0]
        img_start = img_len_offset + 4
        img_end = img_start + img_len
        
        if img_end > len(file_data):
            img_end = len(file_data)
            
        img_data = file_data[img_start:img_end]
        if img_data.startswith(b"GIF89a") or img_data.startswith(b"GIF87a"):
            return img_data, ".gif"
        elif img_data.startswith(b"\x89PNG\r\n\x1a\n"):
            return img_data, ".png"
        elif img_data.startswith(b"\xff\xd8"):
            return img_data, ".jpg"
    except Exception as e:
        logger.warning(f"Failed to extract image from Magic 43: {e}")
    return None

def extract_gif_from_magic_43(file_data: bytes) -> bytes | None:
    """Helper to extract pure GIF from Magic 43 payload."""
    res = extract_image_from_magic_43(file_data)
    if res and res[1] == ".gif":
        return res[0]
    return None

# Divoom cloud-container crypto (same key/IV the official app uses; the
# devices themselves cannot decrypt these — see decode_cloud_frames).
_CLOUD_AES_KEY = b'78hrey23y28ogs89'
_CLOUD_AES_IV = b'1234567890123456'

CLOUD_CONTAINER_MAGICS = (9, 18, 26)


def decode_cloud_frames(raw_bytes: bytes, *, max_frames: int = 24):
    """Decode a Divoom cloud container (magic 9 / 18 / 26) into native-size
    PIL frames.

    Magic 9: ``[magic][total_frames][speed:2 BE]`` + AES-CBC-encrypted raw RGB
    16×16 frames (768 bytes each). Magic 18/26 add per-frame LZO compression
    and a row/column tile layout.

    R36: this is the SEND-path decoder, not just a preview helper — the cloud
    container is app-side ciphertext. The official APK decodes it
    (`PixelBean.initWithCloudData`) and re-encodes with `pixelEncode` before
    any BLE send; streaming the container raw gives the device undecodable
    bytes (it ACKs the transfer and renders nothing — the R36 Ditoo bug).

    Returns ``(frames, duration_ms)`` with frames at NATIVE pixel size
    (16×16 for magic 9; tiles×16 for 18/26), or ``(None, 0)`` if the payload
    isn't a decodable cloud container.
    """
    try:
        from Crypto.Cipher import AES
        from PIL import Image

        if not raw_bytes:
            return None, 0
        magic = raw_bytes[0]

        def decrypt_aes(data):
            return AES.new(_CLOUD_AES_KEY, AES.MODE_CBC, _CLOUD_AES_IV).decrypt(data)

        if magic == 9:
            encrypted = raw_bytes[4:]
            decrypted = decrypt_aes(encrypted)
            total_frames = raw_bytes[1]
            speed = struct.unpack('>H', raw_bytes[2:4])[0]
            frames = []
            for f_idx in range(min(total_frames, max_frames)):
                start = f_idx * 768
                end = start + 768
                if end > len(decrypted):
                    break
                frames.append(Image.frombytes("RGB", (16, 16), bytes(decrypted[start:end])))
            return (frames or None), (speed if speed >= 10 else 100)

        if magic in (18, 26):
            import lzallright
            total_frames, speed, row_count, column_count = struct.unpack('>BHBB', raw_bytes[1:6])
            decrypted = decrypt_aes(raw_bytes[6:])
            lzo = lzallright.LZOCompressor()
            uncompressed_size = row_count * column_count * 768
            frames = []
            pos = 0
            for f_idx in range(min(total_frames, max_frames)):
                if pos + 4 > len(decrypted):
                    break
                frame_size = struct.unpack('>I', decrypted[pos:pos + 4])[0]
                pos += 4
                if pos + frame_size > len(decrypted):
                    break
                compressed_frame = decrypted[pos:pos + frame_size]
                pos += frame_size
                try:
                    frame_data = lzo.decompress(compressed_frame, uncompressed_size)
                    frames.append(_compact_tiles(frame_data, row_count, column_count))
                except Exception as frame_err:
                    logger.warning(f"Failed to decompress frame {f_idx} for magic {magic}: {frame_err}")
                    break
            return (frames or None), (speed if speed >= 10 else 100)
    except Exception as e:
        logger.warning(f"Failed to decode cloud container (magic {raw_bytes[0] if raw_bytes else 0}): {e}")
    return None, 0


def decode_cloud_to_gif(raw_bytes: bytes, out_path: Path) -> bool:
    """Decode a cloud container to a native-size GIF on disk (R36 send path).
    Returns False when the payload isn't a decodable container."""
    frames, duration = decode_cloud_frames(raw_bytes)
    if not frames:
        return False
    try:
        frames[0].save(out_path, save_all=len(frames) > 1,
                       append_images=frames[1:], duration=duration, loop=0)
        return True
    except Exception as e:
        logger.warning(f"Failed to write decoded cloud GIF: {e}")
        return False


def decode_and_save_preview(raw_bytes: bytes, cache_file_png: Path) -> bool:
    """Decode a cloud container and save a 128x128 PNG (static) / GIF
    (animation) preview for the gallery cache. Thin wrapper around
    :func:`decode_cloud_frames` (R36 — one decoder for previews AND the send
    path)."""
    try:
        from PIL import Image
        frames, duration = decode_cloud_frames(raw_bytes)
        if not frames:
            return False
        magic = raw_bytes[0]
        previews = [f.resize((128, 128), Image.Resampling.NEAREST) for f in frames]
        previews[0].save(cache_file_png)  # static first-frame placeholder
        if len(previews) > 1:
            cache_file_gif = cache_file_png.with_suffix(".gif")
            previews[0].save(cache_file_gif, save_all=True,
                             append_images=previews[1:], duration=duration, loop=0)
            logger.info(f"Gallery Cache: Decoded Magic {magic} animation with {len(previews)} frames to {cache_file_gif.name}")
        else:
            logger.info(f"Gallery Cache: Decoded Magic {magic} static frame to {cache_file_png.name}")
        return True
    except Exception as e:
        logger.warning(f"Failed to transcode preview for Magic {raw_bytes[0] if raw_bytes else 0}: {e}")
    return False

def _compact_tiles(frame_data: bytes, row_count: int, column_count: int):
    from PIL import Image
    width, height = column_count * 16, row_count * 16
    
    if lib is not None:
        try:
            # Allocate ctypes array for output
            out_size = width * height * 3
            out_buf = (ctypes.c_ubyte * out_size)()
            
            # Copy input buffer to ctypes array
            in_len = len(frame_data)
            in_buf = (ctypes.c_ubyte * in_len).from_buffer_copy(frame_data)
            
            # Execute high-performance C compacting loop
            lib.compact_tiles(in_buf, in_len, out_buf, row_count, column_count)
            
            # Create PIL image directly from buffer bytes
            return Image.frombytes("RGB", (width, height), bytes(out_buf))
        except Exception as e:
            logger.warning(f"Native tile compacting failed, falling back to python: {e}")

    # Pure Python Fallback
    img = Image.new("RGB", (width, height))
    pixels = img.load()
    pos = 0
    for grid_y in range(row_count):
        for grid_x in range(column_count):
            for y in range(16):
                for x in range(16):
                    if pos + 3 <= len(frame_data):
                        pixels[grid_x * 16 + x, grid_y * 16 + y] = (frame_data[pos], frame_data[pos+1], frame_data[pos+2])
                        pos += 3
    return img
