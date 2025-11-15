import pytest
import os
from PIL import Image, ImageDraw
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
    """Test process_image with a static PNG image."""
    frames, frames_count = image_processing.process_image(create_static_image_file)
    assert frames_count == 1
    assert len(frames) == 1
    frame_data, frame_size = frames[0]
    assert isinstance(frame_data, list)
    assert frame_size == 16 * 16 * 3 # 16x16 pixels, 3 bytes per pixel (RGB)
    # Check a few pixel values (red image)
    assert frame_data[0] == 255 # R
    assert frame_data[1] == 0   # G
    assert frame_data[2] == 0   # B

def test_process_image_gif(create_gif_image_file):
    """Test process_image with an animated GIF image."""
    frames, frames_count = image_processing.process_image(create_gif_image_file)
    assert frames_count == 3
    assert len(frames) == 3
    
    # Check first frame (0,0,0)
    frame_data_0, frame_size_0 = frames[0]
    assert frame_size_0 == 16 * 16 * 3
    assert frame_data_0[0] == 0
    assert frame_data_0[1] == 0
    assert frame_data_0[2] == 0

    # Check second frame (50,100,150)
    frame_data_1, frame_size_1 = frames[1]
    assert frame_size_1 == 16 * 16 * 3
    assert frame_data_1[0] == 50
    assert frame_data_1[1] == 100
    assert frame_data_1[2] == 150

def test_process_image_file_not_found():
    """Test process_image with a non-existent file."""
    frames, frames_count = image_processing.process_image("non_existent_file.png")
    assert frames_count == 0
    assert frames == []

def test_chunks():
    """Test the chunks utility function."""
    test_list = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]
    
    # Perfect division
    result = list(image_processing.chunks(test_list, 5))
    assert result == [[1, 2, 3, 4, 5], [6, 7, 8, 9, 10]]

    # Uneven division
    result = list(image_processing.chunks(test_list, 3))
    assert result == [[1, 2, 3], [4, 5, 6], [7, 8, 9], [10]]

    # Chunk size larger than list
    result = list(image_processing.chunks(test_list, 15))
    assert result == [[1, 2, 3, 4, 5, 6, 7, 8, 9, 10]]

    # Empty list
    result = list(image_processing.chunks([], 3))
    assert result == []

    # Chunk size 1
    result = list(image_processing.chunks(test_list, 1))
    assert result == [[1], [2], [3], [4], [5], [6], [7], [8], [9], [10]]

def test_make_framepart():
    """Test make_framepart function constructs correct byte array."""
    total_size = 1024
    frame_id = 0
    data = [0xAA, 0xBB, 0xCC] # Example data bytes

    # Expected structure:
    # total_size (2 bytes, little-endian) -> 0x00 0x04
    # frame_id (1 byte, big-endian, signed) -> 0x00
    # len(data) (2 bytes, little-endian) -> 0x03 0x00
    # data -> 0xAA 0xBB 0xCC
    expected_frame = [0x00, 0x04, 0x00, 0x03, 0x00, 0xAA, 0xBB, 0xCC]
    
    result = image_processing.make_framepart(total_size, frame_id, data)
    assert result == expected_frame

    # Test with negative frame_id (for static images, -1)
    total_size_static = 500
    frame_id_static = -1
    data_static = [0x11, 0x22]
    # frame_id -1 (signed) -> 0xFF
    expected_frame_static = [0xF4, 0x01, 0xFF, 0x02, 0x00, 0x11, 0x22]
    result_static = image_processing.make_framepart(total_size_static, frame_id_static, data_static)
    assert result_static == expected_frame_static
