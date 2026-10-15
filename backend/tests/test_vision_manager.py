"""Unit tests for backend/vision_manager.py."""

import io
from PIL import Image
import pytest
from backend.vision_manager import VisionManager


def test_vision_manager_capture():
    mgr = VisionManager(target_width=1024, jpeg_quality=70)
    jpeg_data = mgr.capture_screen_jpeg()

    # 1. Verify JPEG signature (SOI marker: 0xFF, 0xD8)
    assert len(jpeg_data) > 0
    assert jpeg_data.startswith(b"\xff\xd8")

    # 2. Verify image can be parsed by PIL
    img = Image.open(io.BytesIO(jpeg_data))
    assert img.format == "JPEG"

    # 3. Verify width constraint (must be <= 1024px)
    assert img.width <= 1024
    assert img.height > 0

    # 4. Verify helper method
    w, h = mgr.get_image_dimensions(jpeg_data)
    assert w == img.width
    assert h == img.height
