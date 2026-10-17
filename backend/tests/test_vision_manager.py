"""Unit tests for backend/vision_manager.py."""

import io
from unittest.mock import patch
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


def test_vision_manager_default_resolution_and_quality():
    """Verify default 1920x1080 resolution at quality 88."""
    mgr = VisionManager()
    assert mgr.target_width == 1920
    assert mgr.jpeg_quality == 88

    jpeg_data = mgr.capture_screen_jpeg()
    w, h = mgr.get_image_dimensions(jpeg_data)
    assert w <= 1920
    assert h > 0


def test_capture_cursor_magnifier_jpeg():
    """Verify 2.0x zoomed cursor magnifier crop at quality 95."""
    mgr = VisionManager()
    crop_w, crop_h, zoom = 520, 340, 2.0
    mag_jpeg = mgr.capture_cursor_magnifier_jpeg(crop_width=crop_w, crop_height=crop_h, zoom=zoom)

    assert len(mag_jpeg) > 0
    assert mag_jpeg.startswith(b"\xff\xd8")

    img = Image.open(io.BytesIO(mag_jpeg))
    assert img.format == "JPEG"
    assert img.width == int(crop_w * zoom)
    assert img.height == int(crop_h * zoom)


def test_capture_cursor_magnifier_edge_clamping():
    """Verify magnifier handles extreme corner coordinates (0, 0) and (2000, 2000) gracefully."""
    mgr = VisionManager()
    synthetic = Image.new("RGB", (1920, 1080), color=(20, 30, 40))

    with patch.object(mgr, "_grab_raw_image", return_value=synthetic), \
         patch("backend.vision_manager._get_os_cursor_pos", return_value=(0, 0)):
        mag_jpeg = mgr.capture_cursor_magnifier_jpeg(crop_width=520, crop_height=340, zoom=2.0)
        img = Image.open(io.BytesIO(mag_jpeg))
        assert img.width == 1040
        assert img.height == 680

    with patch.object(mgr, "_grab_raw_image", return_value=synthetic), \
         patch("backend.vision_manager._get_os_cursor_pos", return_value=(2500, 1500)):
        mag_jpeg2 = mgr.capture_cursor_magnifier_jpeg(crop_width=520, crop_height=340, zoom=2.0)
        img2 = Image.open(io.BytesIO(mag_jpeg2))
        assert img2.width == 1040
        assert img2.height == 680
