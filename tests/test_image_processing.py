import pytest
import os
from PIL import Image
from divoom_lib.utils import image_processing
import tempfile
import logging

# Suppress logging output during tests for cleaner output
@pytest.fixture(autouse=True)
def no_logging(caplog):
    caplog.set_level(logging.CRITICAL)

@pytest.fixture
def create_static_image_file():
    """Fixture to create a temporary static image file."""
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
        img = Image.new('RGB', (16, 16), color = 'red')
        img.save(tmp.name)
        yield tmp.name
    os.remove(tmp.name)

@pytest.fixture
def create_gif_image_file():
    """Fixture to create a temporary animated GIF file."""
    with tempfile.NamedTemporaryFile(suffix=".gif", delete=False) as tmp:
        images = []
        for i in range(3):
            img = Image.new('RGB', (16, 16), color = (i*50, i*100, i*150))
            images.append(img)
        images[0].save(tmp.name, save_all=True, append_images=images[1:], duration=100, loop=0)
        yield tmp.name
    os.remove(tmp.name)

def test_process_image_static(create_static_image_file):
    """process_image with a static PNG returns 1 frame with width/height/duration."""
    frames, frames_count, width, height = image_processing.process_image(create_static_image_file)
    assert frames_count == 1
    assert len(frames) == 1
    rgb, w, h, duration_ms = frames[0]
    assert isinstance(rgb, bytes)
    assert len(rgb) == 16 * 16 * 3  # 16x16 pixels, 3 bytes per pixel (RGB)
    assert width == 16
    assert height == 16
    assert w == 16 and h == 16
    assert duration_ms == 1000  # default for static
    # Check a few pixel values (red image)
    assert rgb[0] == 255  # R
    assert rgb[1] == 0    # G
    assert rgb[2] == 0    # B

def test_process_image_gif(create_gif_image_file):
    """process_image with a GIF returns N frames with per-frame durations."""
    frames, frames_count, width, height = image_processing.process_image(create_gif_image_file)
    assert frames_count == 3
    assert len(frames) == 3
    assert width == 16 and height == 16

    # First frame: (0, 0, 0)
    rgb_0, w_0, h_0, dur_0 = frames[0]
    assert len(rgb_0) == 16 * 16 * 3
    assert rgb_0[0] == 0
    assert rgb_0[1] == 0
    assert rgb_0[2] == 0
    assert dur_0 == 100  # GIF duration was 100ms

    # Second frame: (50, 100, 150)
    rgb_1, w_1, h_1, dur_1 = frames[1]
    assert len(rgb_1) == 16 * 16 * 3
    assert rgb_1[0] == 50
    assert rgb_1[1] == 100
    assert rgb_1[2] == 150
    assert dur_1 == 100

def test_process_image_file_not_found():
    """process_image with a non-existent file returns an empty result."""
    frames, frames_count, width, height = image_processing.process_image("non_existent_file.png")
    assert frames_count == 0
    assert frames == []
    assert width == 0 and height == 0

def test_process_image_passes_time_to_static_frame():
    """The `time` parameter sets the static frame's duration."""
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
        Image.new('RGB', (4, 4), color='red').save(tmp.name)
        try:
            frames, count, w, h = image_processing.process_image(tmp.name, time=500)
            assert count == 1
            assert frames[0][3] == 500
        finally:
            os.remove(tmp.name)
