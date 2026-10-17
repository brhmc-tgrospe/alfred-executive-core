"""A.L.F.R.E.D. Vision Manager.

Captures monitor screenshots using mss and Pillow, supports 1920x1080 full-screen capture
at high quality (88), and provides high-resolution 2.0x zoomed cursor magnifier crops
at quality 95 with cyan targeting reticles for razor-sharp tooltip and UI inspection.
Includes resilient fallback for headless/non-interactive Windows desktop sessions.
"""

from __future__ import annotations

import ctypes
import io
import logging
import sys
from typing import Optional, Tuple
from PIL import Image, ImageDraw

logger = logging.getLogger("AlfredVision")

try:
    import mss
    import mss.exception
except ImportError:
    mss = None


class POINT(ctypes.Structure):
    _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]


def _get_os_cursor_pos() -> Optional[Tuple[int, int]]:
    """Retrieves physical OS cursor coordinates with pyautogui fallback."""
    if hasattr(ctypes, "windll") and sys.platform.startswith("win"):
        try:
            pt = POINT()
            if ctypes.windll.user32.GetCursorPos(ctypes.byref(pt)):
                return int(pt.x), int(pt.y)
        except Exception:
            pass
    try:
        import pyautogui
        pos = pyautogui.position()
        return int(pos.x), int(pos.y)
    except Exception:
        return None


class VisionManager:
    """Manages high-speed display capture, 1920x1080 full frames, and 2.0x cursor magnifier crops."""

    def __init__(self, target_width: int = 1920, jpeg_quality: int = 88) -> None:
        self.target_width = target_width
        self.jpeg_quality = jpeg_quality
        self._last_frame: Optional[bytes] = None

    def _generate_fallback_image(self, message: str = "A.L.F.R.E.D. Vision: Session Locked/Non-Interactive") -> Image.Image:
        """Generates a diagnostic fallback frame when Windows desktop GDI is inaccessible."""
        width = self.target_width
        height = int(width * 9 / 16)
        img = Image.new("RGB", (width, height), color=(15, 23, 42))  # Slate-900
        draw = ImageDraw.Draw(img)
        # Draw placeholder borders and text
        draw.rectangle([(20, 20), (width - 20, height - 20)], outline=(6, 182, 212), width=2)
        draw.text((40, 40), f"[ALFRED TELEMETRY] {message}", fill=(245, 158, 11))
        return img

    def _grab_raw_image(self, monitor_index: int = 1) -> Image.Image:
        """Captures raw native desktop image from the designated monitor without downscaling."""
        img: Optional[Image.Image] = None

        # 1. Attempt capture via mss
        if mss is not None:
            try:
                factory = getattr(mss, "MSS", getattr(mss, "mss", None))
                with factory() as sct:
                    monitors = sct.monitors
                    target_monitor = (
                        monitors[monitor_index]
                        if len(monitors) > monitor_index
                        else monitors[0]
                    )
                    sct_img = sct.grab(target_monitor)
                    img = Image.frombytes("RGB", sct_img.size, sct_img.bgra, "raw", "BGRX")
            except Exception as e:
                logger.debug("mss display grab failed (likely non-interactive session): %s", e)
                img = None

        # 2. Attempt fallback via PIL.ImageGrab
        if img is None:
            try:
                from PIL import ImageGrab
                grabbed = ImageGrab.grab()
                if grabbed is not None:
                    img = grabbed.convert("RGB")
            except Exception as e:
                logger.debug("PIL ImageGrab fallback failed: %s", e)
                img = None

        # 3. If Windows GDI is not accessible, return fallback image
        if img is None:
            img = self._generate_fallback_image()

        return img

    def capture_screen_jpeg(self, monitor_index: int = 1) -> bytes:
        """Captures designated monitor, scales to target_width (1920px default), and returns JPEG bytes.

        Args:
            monitor_index: Monitor index (1 = primary monitor in mss).

        Returns:
            bytes: Compressed JPEG image data.
        """
        img = self._grab_raw_image(monitor_index=monitor_index)

        # Downsample proportionally only if width exceeds target_width
        if img.width > self.target_width:
            aspect_ratio = img.height / img.width
            target_height = int(self.target_width * aspect_ratio)
            img = img.resize((self.target_width, target_height), Image.Resampling.LANCZOS)

        # Compress into JPEG buffer
        buffer = io.BytesIO()
        img.save(buffer, format="JPEG", quality=self.jpeg_quality, optimize=True)
        jpeg_bytes = buffer.getvalue()
        self._last_frame = jpeg_bytes
        return jpeg_bytes

    def capture_cursor_magnifier_jpeg(
        self,
        crop_width: int = 520,
        crop_height: int = 340,
        zoom: float = 2.0,
        monitor_index: int = 1,
    ) -> bytes:
        """Crops a region centered around the live OS cursor, draws a cyan reticle, and upscales 2.0x.

        Provides razor-sharp visibility of tiny hover tooltips, game item stats, small text,
        and subtle UI indicators that would otherwise blur in full-screen captures.

        Args:
            crop_width: Width of native-resolution crop box (default 520px).
            crop_height: Height of native-resolution crop box (default 340px).
            zoom: Upscale magnification factor (default 2.0x).
            monitor_index: Monitor index to capture from.

        Returns:
            bytes: Compressed high-quality JPEG data (quality=95) of the magnified cursor area.
        """
        raw_img = self._grab_raw_image(monitor_index=monitor_index)
        img_w, img_h = raw_img.width, raw_img.height

        # Query live hardware OS cursor coordinates
        cursor_pos = _get_os_cursor_pos()
        if cursor_pos is not None:
            mx, my = cursor_pos
        else:
            mx, my = img_w // 2, img_h // 2

        # Clamp center coordinate within valid desktop bounds
        clamped_mx = max(0, min(img_w - 1, mx))
        clamped_my = max(0, min(img_h - 1, my))

        crop_w = min(crop_width, img_w)
        crop_h = min(crop_height, img_h)

        # Calculate bounding box centered at (clamped_mx, clamped_my)
        left = clamped_mx - (crop_w // 2)
        top = clamped_my - (crop_h // 2)

        # Screen boundary clamping
        if left < 0:
            left = 0
        elif left + crop_w > img_w:
            left = max(0, img_w - crop_w)

        if top < 0:
            top = 0
        elif top + crop_h > img_h:
            top = max(0, img_h - crop_h)

        right = left + crop_w
        bottom = top + crop_h

        crop_img = raw_img.crop((left, top, right, bottom)).copy()

        # Relative cursor coordinates within the cropped image
        rel_x = max(0, min(crop_w - 1, clamped_mx - left))
        rel_y = max(0, min(crop_h - 1, clamped_my - top))

        # Draw subtle cyan targeting reticle at exact cursor position
        draw = ImageDraw.Draw(crop_img)
        reticle_color = (6, 182, 212)  # Cyan #06b6d4

        # Crosshair lines with center clearance
        draw.line([(rel_x - 14, rel_y), (rel_x - 4, rel_y)], fill=reticle_color, width=2)
        draw.line([(rel_x + 4, rel_y), (rel_x + 14, rel_y)], fill=reticle_color, width=2)
        draw.line([(rel_x, rel_y - 14), (rel_x, rel_y - 4)], fill=reticle_color, width=2)
        draw.line([(rel_x, rel_y + 4), (rel_x, rel_y + 14)], fill=reticle_color, width=2)

        # Subtle center reticle ring
        draw.ellipse([(rel_x - 3, rel_y - 3), (rel_x + 3, rel_y + 3)], outline=reticle_color, width=1)

        # Upscale 2.0x using Lanczos resampling for pristine pixel clarity
        target_w = int(crop_w * zoom)
        target_h = int(crop_h * zoom)
        zoomed_img = crop_img.resize((target_w, target_h), Image.Resampling.LANCZOS)

        # Compress into high-res JPEG buffer at quality 95
        buffer = io.BytesIO()
        zoomed_img.save(buffer, format="JPEG", quality=95, optimize=True)
        return buffer.getvalue()

    def get_image_dimensions(self, jpeg_bytes: bytes) -> Tuple[int, int]:
        """Utility helper to parse image dimensions from JPEG bytes without full decode."""
        with Image.open(io.BytesIO(jpeg_bytes)) as img:
            return img.width, img.height
