# divoom_api/utils/image_processing.py
from PIL import Image

from .divoom_image_encode import Frame


def process_image(file, time: int | None = None):
    """Processes an image file (GIF or static image) into a format suitable for Divoom devices.

    Args:
        file: Path to the image file. Any format PIL supports.
        time: Optional default frame duration in milliseconds. Used for
            static images (where PIL doesn't provide a duration) and as
            a fallback for GIF frames with no per-frame duration set.

    Returns:
        (frames, frames_count, width, height):
          frames: list of (rgb_bytes, width, height, duration_ms) tuples,
              one per image frame. The rgb_bytes is in PIL's `tobytes()`
              order (left-to-right, top-to-bottom). width and height
              are the same for all frames in a single image.
          frames_count: number of frames (1 for static, n for GIF).
          width: image width in pixels.
          height: image height in pixels.

        On file error, returns ([], 0, 0, 0).
    """
    default_duration_ms = 1000 if time is None else int(time)

    try:
        img = Image.open(file)
    except FileNotFoundError:
        print(f"Error: Image file not found at {file}")
        return [], 0, 0, 0
    except Exception as e:
        print(f"Error opening image file {file}: {e}")
        return [], 0, 0, 0

    width, height = img.size
    frames: list[Frame] = []

    if hasattr(img, "is_animated") and img.is_animated:
        for frame_idx in range(img.n_frames):
            img.seek(frame_idx)
            rgb = img.convert("RGB").tobytes()
            # PIL exposes per-frame duration in ms via .info.get("duration")
            duration = img.info.get("duration", default_duration_ms)
            frames.append((rgb, width, height, int(duration)))
    else:
        rgb = img.convert("RGB").tobytes()
        frames.append((rgb, width, height, default_duration_ms))

    return frames, len(frames), width, height
