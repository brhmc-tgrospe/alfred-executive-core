"""A.L.F.R.E.D. Vision Manager.

Captures monitor screenshots using mss and Pillow, downsamples to 1024px JPEG bytes
for high-efficiency streaming to the Gemini Multimodal Live API.
Includes resilient fallback for headless/non-interactive Windows desktop sessions.
"""

from __future__ import annotations

import io
import logging
from typing import Optional, Tuple
from PIL import Image, ImageDraw

logger = logging.getLogger("AlfredVision")

try:
    import mss
    import mss.exception
except ImportError:
    mss = None


class VisionManager:
    """Manages high-speed display capture and JPEG compression."""

    def __init__(self, target_width: int = 1024, jpeg_quality: int = 70) -> None:
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

    def capture_screen_jpeg(self, monitor_index: int = 1) -> bytes:
        """Captures the designated monitor, scales it proportionally, and returns JPEG bytes.

        Args:
            monitor_index: Monitor index (1 = primary monitor in mss).

        Returns:
            bytes: Compressed JPEG image data.
        """
        img: Optional[Image.Image] = None

        # 1. Attempt capture via mss
        if mss is not None:
            try:
                # Use mss.MSS() or mss.mss()
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

        # 3. If Windows GDI is not accessible (headless/Session 0), use cached frame or diagnostic frame
        if img is None:
            if self._last_frame is not None:
                return self._last_frame
            img = self._generate_fallback_image()

        # Downsample proportionally if width exceeds target_width
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

    def get_image_dimensions(self, jpeg_bytes: bytes) -> Tuple[int, int]:
        """Utility helper to parse image dimensions from JPEG bytes without full decode."""
        with Image.open(io.BytesIO(jpeg_bytes)) as img:
            return img.width, img.height
