# divoom_api/utils/image_processing.py
import math
from PIL import Image

def process_image(file, time=None):
    """
    Processes an image file (GIF or static image) into a format suitable for Divoom devices.
    Returns a tuple: (list of frames, number of frames).
    Each frame in the list is a tuple: (list of bytes for the frame, size of the frame).
    """
    frames = []
    framesCount = 0

    try:
        img = Image.open(file)
    except FileNotFoundError:
        print(f"Error: Image file not found at {file}")
        return [], 0
    except Exception as e:
        print(f"Error opening image file {file}: {e}")
        return [], 0

    if hasattr(img, 'is_animated') and img.is_animated:
        # Process GIF
        framesCount = img.n_frames
        for frame_idx in range(framesCount):
            img.seek(frame_idx)
            frame_data = img.convert("RGB").tobytes()
            frames.append((list(frame_data), len(frame_data)))
    else:
        # Process static image
        framesCount = 1
        frame_data = img.convert("RGB").tobytes()
        frames.append((list(frame_data), len(frame_data)))

    return frames, framesCount

def chunks(lst, n):
    """Yield successive n-sized chunks from lst."""
    for i in range(0, len(lst), n):
        yield lst[i:i + n]
