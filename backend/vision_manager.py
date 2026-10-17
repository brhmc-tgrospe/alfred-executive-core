"""A.L.F.R.E.D. Vision Manager.

Captures monitor screenshots using mss and Pillow, supports 1920x1080 full-screen capture
at high quality (88), and provides high-resolution 2.0x zoomed cursor magnifier crops
at quality 95 with cyan targeting reticles for razor-sharp tooltip and UI inspection.
Includes resilient fallback for headless/non-interactive Windows desktop sessions.
"""

from __future__ import annotations

import ctypes
import io
import json
import logging
import os
import sys
from typing import Any, Dict, List, Optional, Tuple
import cv2
import numpy as np
from PIL import Image, ImageDraw

try:
    import win32gui
except ImportError:
    win32gui = None

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

    def __init__(
        self,
        target_width: int = 1920,
        jpeg_quality: int = 88,
        memory_store: Optional[Any] = None,
    ) -> None:
        self.target_width = target_width
        self.jpeg_quality = jpeg_quality
        self.memory = memory_store
        self._last_frame: Optional[bytes] = None
        self._som_cache: Dict[str, Any] = {}

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

    _som_cache: Dict[str, Any] = {}

    def get_image_dimensions(self, jpeg_bytes: bytes) -> Tuple[int, int]:
        """Utility helper to parse image dimensions from JPEG bytes without full decode."""
        with Image.open(io.BytesIO(jpeg_bytes)) as img:
            return img.width, img.height

    def capture_screen_raw(self, monitor_index: int = 1) -> Image.Image:
        """Captures raw uncompressed PIL Image of the screen or monitor."""
        return self._grab_raw_image(monitor_index=monitor_index)

    def capture_screen_patch(
        self,
        center_x: int,
        center_y: int,
        patch_size: int = 120,
        monitor_index: int = 1,
    ) -> np.ndarray:
        """Captures a native-resolution square patch centered at (center_x, center_y) as a BGR numpy array.

        Args:
            center_x: Horizontal center coordinate on the desktop.
            center_y: Vertical center coordinate on the desktop.
            patch_size: Width and height of the square patch (default: 120).
            monitor_index: Monitor index to capture from (default: 1).

        Returns:
            A BGR numpy array of dimensions (patch_size, patch_size, 3).
        """
        raw_pil = self._grab_raw_image(monitor_index=monitor_index)
        img_w, img_h = raw_pil.width, raw_pil.height

        half = patch_size // 2
        left = max(0, min(max(0, img_w - patch_size), center_x - half))
        top = max(0, min(max(0, img_h - patch_size), center_y - half))
        right = min(img_w, left + patch_size)
        bottom = min(img_h, top + patch_size)

        crop = raw_pil.crop((left, top, right, bottom))
        if crop.size != (patch_size, patch_size):
            crop = crop.resize((patch_size, patch_size), Image.Resampling.NEAREST)

        rgb_arr = np.array(crop.convert("RGB"))
        return cv2.cvtColor(rgb_arr, cv2.COLOR_RGB2BGR)

    def get_som_cache(self) -> Dict[str, Any]:
        """Returns the cached Set-of-Marks mapping tags and control labels to pixel coordinates."""
        return VisionManager._som_cache or getattr(self, "_som_cache", {})

    def detect_ui_elements_and_annotate_grid(
        self, window_title: str = "active", monitor_index: int = 1
    ) -> Tuple[bytes, Dict[str, Any]]:
        """Uses OpenCV adaptive thresholding, Canny edges, and contour clustering (plus Win32 controls)

        to detect interactive buttons, icons, tabs, and inputs on custom or unfamiliar software UIs.
        Draws numbered cyan Set-of-Marks tags (#1, #2, ...) and a 10x10 spatial grid onto the frame,
        caching a lookup dictionary mapping each tag and control label to its exact center pixel (x, y).

        Args:
            window_title: Window title or 'active' for current foreground window.
            monitor_index: Display index to capture (default: 1).

        Returns:
            Tuple of (annotated_jpeg_bytes, som_lookup_dict).
        """
        raw_pil = self.capture_screen_raw(monitor_index=monitor_index)
        img_np = np.array(raw_pil.convert("RGB"))
        bgr = cv2.cvtColor(img_np, cv2.COLOR_RGB2BGR)
        h, w = bgr.shape[:2]

        # 1. Edge & Adaptive Thresholding for UI contours
        gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
        thresh = cv2.adaptiveThreshold(
            gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY_INV, 11, 2
        )
        edges = cv2.Canny(gray, 50, 150)
        combined = cv2.bitwise_or(thresh, edges)

        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
        dilated = cv2.dilate(combined, kernel, iterations=1)
        contours, _ = cv2.findContours(dilated, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE)

        candidate_boxes: List[Tuple[int, int, int, int, str]] = []
        min_w, max_w = 16, int(w * 0.45)
        min_h, max_h = 14, int(h * 0.25)

        for c in contours:
            bx, by, bw, bh = cv2.boundingRect(c)
            area = bw * bh
            aspect = bw / float(bh) if bh > 0 else 0
            if (min_w <= bw <= max_w) and (min_h <= bh <= max_h) and (200 <= area <= 60000) and (0.15 <= aspect <= 7.5):
                candidate_boxes.append((bx, by, bw, bh, ""))

        # 2. Win32 Child Windows (if available on Windows)
        if win32gui is not None and sys.platform.startswith("win"):
            try:
                target_hwnd = None
                if window_title == "active":
                    target_hwnd = win32gui.GetForegroundWindow()
                else:
                    def _find_target(hwnd, extra):
                        if win32gui.IsWindowVisible(hwnd):
                            txt = win32gui.GetWindowText(hwnd)
                            if window_title.lower() in txt.lower():
                                extra.append(hwnd)
                        return True
                    found = []
                    win32gui.EnumWindows(_find_target, found)
                    if found:
                        target_hwnd = found[0]

                if target_hwnd and win32gui.IsWindow(target_hwnd):
                    child_hwnds = []
                    def _enum_ch(chwnd, extra):
                        if win32gui.IsWindowVisible(chwnd):
                            extra.append(chwnd)
                        return True
                    try:
                        win32gui.EnumChildWindows(target_hwnd, _enum_ch, child_hwnds)
                    except Exception:
                        pass

                    for ch in child_hwnds:
                        try:
                            crect = win32gui.GetWindowRect(ch)
                            cx1, cy1, cx2, cy2 = crect
                            cw, ch_h = cx2 - cx1, cy2 - cy1
                            ctext = win32gui.GetWindowText(ch).strip()
                            if 14 <= cw <= max_w and 14 <= ch_h <= max_h and 0 <= cx1 < w and 0 <= cy1 < h:
                                candidate_boxes.append((cx1, cy1, cw, ch_h, ctext))
                        except Exception:
                            continue
            except Exception as e:
                logger.debug("Win32 child window inspection skipped: %s", e)

        # 3. Non-Maximum Suppression (NMS) to eliminate duplicate/contained candidate boxes
        candidate_boxes.sort(key=lambda b: (b[2] * b[3]), reverse=True)
        filtered_boxes: List[Tuple[int, int, int, int, str]] = []
        for box in candidate_boxes:
            bx, by, bw, bh, _ = box
            overlap = False
            for fb in filtered_boxes:
                fx, fy, fw, fh, _ = fb
                ix1 = max(bx, fx)
                iy1 = max(by, fy)
                ix2 = min(bx + bw, fx + fw)
                iy2 = min(by + bh, fy + fh)
                if ix2 > ix1 and iy2 > iy1:
                    inter_area = (ix2 - ix1) * (iy2 - iy1)
                    box_area = bw * bh
                    fb_area = fw * fh
                    iou = inter_area / float(box_area + fb_area - inter_area)
                    if iou > 0.40 or (inter_area / float(box_area)) > 0.70:
                        overlap = True
                        break
            if not overlap:
                filtered_boxes.append(box)

        # Sort spatially in natural reading order (top-to-bottom, left-to-right)
        filtered_boxes.sort(key=lambda b: (int(b[1] / 50) * 50, b[0]))
        selected_boxes = filtered_boxes[:60]

        annotated = bgr.copy()
        som_dict: Dict[str, Any] = {}

        # 4. Draw 10x10 Spatial Coordinate Grid
        grid_overlay = annotated.copy()
        grid_color = (255, 200, 0)  # Cyan line
        for i in range(1, 10):
            gx = int(w * i / 10)
            cv2.line(grid_overlay, (gx, 0), (gx, h), grid_color, 1)
            gy = int(h * i / 10)
            cv2.line(grid_overlay, (0, gy), (w, gy), grid_color, 1)
            cv2.putText(grid_overlay, f"C{i}", (gx + 4, 18), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (200, 200, 200), 1)
            cv2.putText(grid_overlay, f"R{i}", (6, gy - 4), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (200, 200, 200), 1)

        cv2.addWeighted(grid_overlay, 0.20, annotated, 0.80, 0, annotated)

        # 5. Draw Set-of-Marks Cyan Tags (#1, #2, ...)
        tag_color = (255, 255, 0)   # Bright Cyan (BGR)
        badge_bg = (15, 23, 42)     # Dark Slate

        for idx, (bx, by, bw, bh, blabel) in enumerate(selected_boxes, start=1):
            tag = f"#{idx}"
            center_x = bx + bw // 2
            center_y = by + bh // 2

            entry = {
                "tag": tag,
                "center": (int(center_x), int(center_y)),
                "rect": (int(bx), int(by), int(bw), int(bh)),
                "bbox": (int(bx), int(by), int(bw), int(bh)),
                "type": "UI_ELEMENT",
                "label": blabel,
            }
            som_dict[tag] = entry
            som_dict[str(idx)] = entry
            if blabel:
                som_dict[blabel.lower()] = entry

            cv2.rectangle(annotated, (bx, by), (bx + bw, by + bh), tag_color, 1)

            tag_text = tag if not blabel else f"{tag}:{blabel[:8]}"
            font_scale = 0.42
            thickness = 1
            (tw, th), _ = cv2.getTextSize(tag_text, cv2.FONT_HERSHEY_SIMPLEX, font_scale, thickness)

            badge_y1 = max(0, by - th - 5)
            badge_y2 = max(th + 5, by)
            badge_x2 = min(w, bx + tw + 6)
            cv2.rectangle(annotated, (bx, badge_y1), (badge_x2, badge_y2), badge_bg, -1)
            cv2.rectangle(annotated, (bx, badge_y1), (badge_x2, badge_y2), tag_color, 1)
            cv2.putText(
                annotated,
                tag_text,
                (bx + 3, badge_y2 - 3),
                cv2.FONT_HERSHEY_SIMPLEX,
                font_scale,
                tag_color,
                thickness,
                cv2.LINE_AA,
            )

        VisionManager._som_cache = som_dict
        self._som_cache = som_dict

        # Encode to JPEG buffer at quality 88
        _, enc = cv2.imencode(".jpg", annotated, [cv2.IMWRITE_JPEG_QUALITY, 88])
        return enc.tobytes(), som_dict

    def _compute_hsv_hist(self, bgr_patch: np.ndarray) -> np.ndarray:
        """Computes a normalized 3D HSV color histogram (8x8x8 bins) for color verification."""
        if bgr_patch is None or bgr_patch.size == 0:
            return np.zeros(512, dtype=np.float32)
        hsv = cv2.cvtColor(bgr_patch, cv2.COLOR_BGR2HSV)
        hist = cv2.calcHist([hsv], [0, 1, 2], None, [8, 8, 8], [0, 180, 0, 256, 0, 256])
        cv2.normalize(hist, hist)
        return hist.flatten().astype(np.float32)

    def _compare_hsv_hist(self, h1: np.ndarray, h2: np.ndarray) -> float:
        """Computes correlation between two normalized HSV histograms in [-1.0, 1.0]."""
        if h1 is None or h2 is None or h1.size == 0 or h2.size == 0 or h1.shape != h2.shape:
            return 0.0
        corr = float(cv2.compareHist(h1.astype(np.float32), h2.astype(np.float32), cv2.HISTCMP_CORREL))
        if np.isnan(corr):
            diff = float(np.linalg.norm(h1 - h2))
            return max(0.0, 1.0 - diff)
        return corr

    def _extract_orb_descriptors(self, bgr_patch: np.ndarray) -> Optional[np.ndarray]:
        """Extracts ORB keypoint descriptors from a UI patch (upscaling small patches for keypoint stability)."""
        if bgr_patch is None or bgr_patch.size == 0:
            return None
        try:
            gray = cv2.cvtColor(bgr_patch, cv2.COLOR_BGR2GRAY)
            h, w = gray.shape[:2]
            if h < 64 or w < 64:
                scale = max(64.0 / max(1, h), 64.0 / max(1, w))
                gray = cv2.resize(
                    gray,
                    (int(round(w * scale)), int(round(h * scale))),
                    interpolation=cv2.INTER_CUBIC,
                )
            orb = cv2.ORB_create(nfeatures=64, edgeThreshold=5, patchSize=15, fastThreshold=5)
            _, des = orb.detectAndCompute(gray, None)
            if des is None or des.size == 0:
                gh, gw = gray.shape[:2]
                grid_kps = [
                    cv2.KeyPoint(float(gx), float(gy), 15.0)
                    for gy in (gh * 0.25, gh * 0.5, gh * 0.75)
                    for gx in (gw * 0.25, gw * 0.5, gw * 0.75)
                ]
                _, des = orb.compute(gray, grid_kps)
            return des
        except Exception:
            return None

    def _compute_orb_match_score(self, des1: Optional[np.ndarray], candidate_bgr: np.ndarray) -> float:
        """Computes normalized ORB BFMatcher similarity score [0.0, 1.0] between stored descriptors and candidate patch."""
        if des1 is None or des1.size == 0:
            return 0.0
        try:
            des2 = self._extract_orb_descriptors(candidate_bgr)
            if des2 is None or des2.size == 0:
                return 0.0
            bf = cv2.BFMatcher(cv2.NORM_HAMMING, crossCheck=True)
            matches = bf.match(des1.astype(np.uint8), des2.astype(np.uint8))
            if not matches:
                return 0.0
            good = [m for m in matches if m.distance < 68]
            denom = max(1, min(len(des1), len(des2)))
            return float(min(1.0, len(good) / float(denom)))
        except Exception:
            return 0.0

    def _extract_core_crop(self, full_bgr: np.ndarray, ratio: float = 0.65) -> np.ndarray:
        """Extracts the symmetric central 65% inner core of a template with zero outer background bleed."""
        fh, fw = full_bgr.shape[:2]
        core_w = max(12, int(round(fw * ratio)))
        core_h = max(12, int(round(fh * ratio)))
        if core_w < fw and (fw - core_w) % 2 != 0:
            core_w += 1
        if core_h < fh and (fh - core_h) % 2 != 0:
            core_h += 1
        core_w = min(fw, core_w)
        core_h = min(fh, core_h)
        cx_off = (fw - core_w) // 2
        cy_off = (fh - core_h) // 2
        return full_bgr[cy_off : cy_off + core_h, cx_off : cx_off + core_w].copy()

    def _extract_adaptive_icon_templates(
        self,
        cx: int,
        cy: int,
        search_size: int = 400,
        monitor_index: int = 1,
        fallback_patch: Optional[np.ndarray] = None,
    ) -> Dict[str, Any]:
        """Scans a 400x400 region around (cx, cy) using color segmentation, Canny edges, and connected contours
        to automatically detect the natural bounding box (w, h) of the UI icon or button (from 18x18 up to 380x240).

        Returns:
            Dict containing 'full_template', 'core_template', 'width', 'height', 'orb_features', and 'hsv_hist'.
        """
        raw_pil = self.capture_screen_raw(monitor_index=monitor_index)
        screen_bgr = cv2.cvtColor(np.array(raw_pil.convert("RGB")), cv2.COLOR_RGB2BGR)
        sh, sw = screen_bgr.shape[:2]

        cx_c = max(0, min(sw - 1, int(cx)))
        cy_c = max(0, min(sh - 1, int(cy)))

        half = search_size // 2
        x1 = max(0, cx_c - half)
        y1 = max(0, cy_c - half)
        x2 = min(sw, cx_c + half)
        y2 = min(sh, cy_c + half)

        roi = screen_bgr[y1:y2, x1:x2]
        rh, rw = roi.shape[:2]
        rel_x = cx_c - x1
        rel_y = cy_c - y1

        # 1. Color segmentation against outer perimeter background median
        top_b = roi[:6, :, :].reshape(-1, 3)
        bot_b = roi[max(0, rh - 6) :, :, :].reshape(-1, 3)
        left_b = roi[:, :6, :].reshape(-1, 3)
        right_b = roi[:, max(0, rw - 6) :, :].reshape(-1, 3)
        border_px = np.vstack([top_b, bot_b, left_b, right_b])
        bg_median = np.median(border_px, axis=0).astype(np.int16)

        color_diff = np.max(np.abs(roi.astype(np.int16) - bg_median), axis=2).astype(np.uint8)
        fg_mask = (color_diff > 18).astype(np.uint8) * 255

        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (5, 5))
        closed_fg = cv2.morphologyEx(fg_mask, cv2.MORPH_CLOSE, kernel, iterations=2)
        contours_fg, _ = cv2.findContours(closed_fg, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        candidates: List[Tuple[int, int, int, int]] = []
        max_bw = min(385, rw - 2)
        max_bh = min(385, rh - 2)

        for c in contours_fg:
            bx, by, bw, bh = cv2.boundingRect(c)
            if 14 <= bw <= max_bw and 14 <= bh <= max_bh:
                if (bx - 8 <= rel_x <= bx + bw + 8) and (by - 8 <= rel_y <= by + bh + 8):
                    candidates.append((bx, by, bw, bh))

        # 2. Fallback to Canny edge contours if color segmentation found no enclosing contour
        if not candidates:
            gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
            edges = cv2.Canny(gray, 40, 120)
            closed_edges = cv2.morphologyEx(edges, cv2.MORPH_CLOSE, kernel, iterations=2)
            contours_edge, _ = cv2.findContours(closed_edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            for c in contours_edge:
                bx, by, bw, bh = cv2.boundingRect(c)
                if 14 <= bw <= max_bw and 14 <= bh <= max_bh:
                    if (bx - 8 <= rel_x <= bx + bw + 8) and (by - 8 <= rel_y <= by + bh + 8):
                        candidates.append((bx, by, bw, bh))

        full_template: Optional[np.ndarray] = None
        if candidates:
            # Select contour whose center is closest to (rel_x, rel_y)
            best_box = min(
                candidates,
                key=lambda b: ((b[0] + b[2] / 2.0 - rel_x) ** 2 + (b[1] + b[3] / 2.0 - rel_y) ** 2),
            )
            bx, by, bw, bh = best_box
            full_template = roi[by : by + bh, bx : bx + bw].copy()
        elif fallback_patch is not None and fallback_patch.size > 0:
            full_template = fallback_patch.copy()
        else:
            def_half = 16
            bx1 = max(0, rel_x - def_half)
            by1 = max(0, rel_y - def_half)
            bx2 = min(rw, bx1 + 32)
            by2 = min(rh, by1 + 32)
            full_template = roi[by1:by2, bx1:bx2].copy()

        fh, fw = full_template.shape[:2]
        core_template = self._extract_core_crop(full_template, ratio=0.65)

        hsv_arr = self._compute_hsv_hist(core_template)
        hsv_json = json.dumps([round(float(v), 5) for v in hsv_arr.tolist()])

        orb_des = self._extract_orb_descriptors(full_template)
        orb_json = json.dumps(orb_des.tolist()) if orb_des is not None and orb_des.size > 0 else "[]"

        return {
            "full_template": full_template,
            "core_template": core_template,
            "width": int(fw),
            "height": int(fh),
            "orb_features": orb_json,
            "hsv_hist": hsv_json,
        }

    def _match_learned_visual_template(self, target_query: str) -> Optional[Dict[str, Any]]:
        """Multi-stage 11-scale OpenCV template, HSV histogram, and ORB feature matching against learned visual UI memories."""
        if not hasattr(self, "memory") or self.memory is None:
            return None
        if not hasattr(self.memory, "get_visual_ui_memory"):
            return None

        mem = self.memory.get_visual_ui_memory(target_query)
        if not mem:
            return None

        tpl_path = mem.get("template_png_path", "")
        if not tpl_path or not os.path.exists(tpl_path):
            return None

        try:
            full_template = cv2.imread(tpl_path, cv2.IMREAD_COLOR)
            if full_template is None or full_template.size == 0:
                return None

            core_path = mem.get("core_png_path", "")
            if core_path and os.path.exists(core_path):
                core_template = cv2.imread(core_path, cv2.IMREAD_COLOR)
                if core_template is None or core_template.size == 0:
                    core_template = self._extract_core_crop(full_template, ratio=0.65)
            else:
                core_template = self._extract_core_crop(full_template, ratio=0.65)

            screen_pil = self._grab_raw_image()
            if screen_pil is None:
                return None
            screen_bgr = cv2.cvtColor(np.array(screen_pil), cv2.COLOR_RGB2BGR)

            th, tw = full_template.shape[:2]
            sh, sw = screen_bgr.shape[:2]
            if th > sh or tw > sw:
                return None

            core_hist = self._compute_hsv_hist(core_template)
            full_hist = self._compute_hsv_hist(full_template)

            stored_orb_des: Optional[np.ndarray] = None
            orb_str = mem.get("orb_features", "")
            if orb_str:
                try:
                    orb_list = json.loads(orb_str)
                    if orb_list:
                        stored_orb_des = np.array(orb_list, dtype=np.uint8)
                except Exception:
                    stored_orb_des = None
            if stored_orb_des is None:
                stored_orb_des = self._extract_orb_descriptors(full_template)

            scales = [0.5, 0.65, 0.75, 0.85, 0.92, 1.0, 1.08, 1.15, 1.3, 1.6, 2.0]
            tiers = [
                ("core", core_template, core_hist),
                ("full", full_template, full_hist),
            ]

            best_score = -1.0
            best_ncc = -1.0
            best_hsv = 0.0
            best_center = (0, 0)
            best_rect = (0, 0, tw, th)
            best_scale = 1.0
            best_tier = "full"

            for tier_name, tpl_img, tpl_hist in tiers:
                t_h, t_w = tpl_img.shape[:2]
                for s in scales:
                    sw_s = int(round(t_w * s))
                    sh_s = int(round(t_h * s))
                    if sw_s > sw or sh_s > sh or sw_s < 6 or sh_s < 6:
                        continue

                    if s == 1.0:
                        scaled_tpl = tpl_img
                    else:
                        scaled_tpl = cv2.resize(
                            tpl_img,
                            (sw_s, sh_s),
                            interpolation=cv2.INTER_AREA if s < 1.0 else cv2.INTER_LINEAR,
                        )

                    res = cv2.matchTemplate(screen_bgr, scaled_tpl, cv2.TM_CCOEFF_NORMED)

                    # Evaluate up to 3 top peaks so wrong-colored background clutter never masks the true icon
                    res_work = None
                    for peak_idx in range(3):
                        cur_map = res if res_work is None else res_work
                        _, max_val, _, max_loc = cv2.minMaxLoc(cur_map)
                        if max_val < 0.55:
                            break

                        bx, by = max_loc
                        cand_patch = screen_bgr[by : by + sh_s, bx : bx + sw_s]
                        cand_hist = self._compute_hsv_hist(cand_patch)
                        hsv_corr = self._compare_hsv_hist(tpl_hist, cand_hist)

                        # Verified threshold: ncc >= 0.68 with hsv_corr >= 0.70, OR high ncc >= 0.80
                        is_verified = (max_val >= 0.68 and hsv_corr >= 0.70) or (max_val >= 0.80 and hsv_corr >= 0.45)
                        if is_verified:
                            orb_score = 0.0
                            if tw >= 60 or th >= 45:
                                orb_score = self._compute_orb_match_score(stored_orb_des, cand_patch)

                            score = 0.70 * float(max_val) + 0.30 * max(0.0, hsv_corr) + 0.03 * orb_score
                            # Full bounding-box alignment bonus when full border matches strongly
                            if tier_name == "full" and max_val >= 0.82:
                                score += 0.04

                            if score > best_score:
                                best_score = score
                                best_ncc = float(max_val)
                                best_hsv = float(hsv_corr)
                                cx = int(round(bx + sw_s / 2.0))
                                cy = int(round(by + sh_s / 2.0))
                                best_center = (cx, cy)
                                best_rect = (bx, by, sw_s, sh_s)
                                best_scale = s
                                best_tier = tier_name
                            break

                        # Suppress rejected peak and check next peak
                        if peak_idx < 2:
                            if res_work is None:
                                res_work = res.copy()
                            sup_x1 = max(0, bx - max(4, sw_s // 2))
                            sup_y1 = max(0, by - max(4, sh_s // 2))
                            sup_x2 = min(res_work.shape[1], bx + max(4, sw_s // 2))
                            sup_y2 = min(res_work.shape[0], by + max(4, sh_s // 2))
                            res_work[sup_y1:sup_y2, sup_x1:sup_x2] = -1.0

            logger.info(
                "[Visual Template Match] Query '%s' -> '%s' best tier=%s ncc=%.3f hsv=%.3f score=%.3f (scale=%.2f)",
                target_query,
                mem.get("element_key", ""),
                best_tier,
                best_ncc,
                best_hsv,
                best_score,
                best_scale,
            )

            if best_score >= 0.68 and best_ncc >= 0.68:
                return {
                    "found": True,
                    "center": best_center,
                    "tag": mem.get("element_key", ""),
                    "label": (
                        f"Learned Visual Template: {mem.get('element_key', '')} "
                        f"(tier={best_tier}, scale={best_scale:.2f}, conf={best_ncc:.2f}, hsv={best_hsv:.2f})"
                    ),
                    "rect": best_rect,
                    "confidence": float(max(best_ncc, min(1.0, best_score))),
                }
        except Exception as e:
            logger.warning("[Visual Template Match] Error matching template for '%s': %s", target_query, e)

        return None

    def autonomous_screen_search(self, target_query: str, window_title: str = "active") -> Dict[str, Any]:
        """Autonomously searches the full screen/window for a target UI element, button, or spatial region.

        Priority 1: Learned Visual Template Multi-Scale Matching (cv2.TM_CCOEFF_NORMED @ 0.85x, 1.0x, 1.15x).
        Priority 2: Existing Set-of-Marks Cache lookup.
        Priority 3: Full-screen contour and Win32 UI refresh.
        Priority 4: Spatial keyword regions (e.g. 'top right', 'taskbar', 'close button').

        Args:
            target_query: The name, label, tag, or spatial description of the element to find.
            window_title: Window title or 'active' for foreground window.

        Returns:
            Dict containing {"found": bool, "center": (x, y), "tag": str, "label": str, ...}
        """
        q = (target_query or "").strip().lower()
        if not q:
            return {"found": False, "center": (-1, -1), "tag": "", "label": "", "reason": "Empty target query."}

        # Priority 1: Learned Visual Template Multi-Scale Matching
        learned_match = self._match_learned_visual_template(q)
        if learned_match is not None:
            return learned_match

        def _search_in_cache(c: dict) -> Optional[Dict[str, Any]]:
            if not c:
                return None

            # 1. Direct Tag Match (#1, 1, #12, etc.)
            tag_key = q if q.startswith("#") else f"#{q}"
            if tag_key in c:
                entry = c[tag_key]
                return {
                    "found": True,
                    "center": entry.get("center", (-1, -1)),
                    "tag": entry.get("tag", tag_key),
                    "label": entry.get("label", ""),
                    "rect": entry.get("rect", (0, 0, 0, 0)),
                }
            if q in c:
                entry = c[q]
                return {
                    "found": True,
                    "center": entry.get("center", (-1, -1)),
                    "tag": entry.get("tag", ""),
                    "label": entry.get("label", ""),
                    "rect": entry.get("rect", (0, 0, 0, 0)),
                }

            # 2. Label Substring Match across detected elements
            for k, entry in c.items():
                if not isinstance(entry, dict):
                    continue
                lbl = entry.get("label", "").lower()
                if lbl and (q in lbl or lbl in q):
                    return {
                        "found": True,
                        "center": entry.get("center", (-1, -1)),
                        "tag": entry.get("tag", k),
                        "label": entry.get("label", ""),
                        "rect": entry.get("rect", (0, 0, 0, 0)),
                    }

            # 3. Spatial Keyword Region Matching
            w, h = 1920, 1080
            if c:
                max_x = max((e.get("center", (0, 0))[0] for e in c.values() if isinstance(e, dict)), default=1920)
                max_y = max((e.get("center", (0, 0))[1] for e in c.values() if isinstance(e, dict)), default=1080)
                w = max(1920, max_x + 50)
                h = max(1080, max_y + 50)

            spatial_box = None
            if "close" in q or "exit button" in q:
                spatial_box = (int(w * 0.85), 0, w, int(h * 0.10))
            elif "top right" in q:
                spatial_box = (int(w * 0.66), 0, w, int(h * 0.33))
            elif "top left" in q:
                spatial_box = (0, 0, int(w * 0.33), int(h * 0.33))
            elif "top center" in q or "top middle" in q:
                spatial_box = (int(w * 0.33), 0, int(w * 0.66), int(h * 0.33))
            elif "bottom right" in q:
                spatial_box = (int(w * 0.66), int(h * 0.66), w, h)
            elif "bottom left" in q:
                spatial_box = (0, int(h * 0.66), int(w * 0.33), h)
            elif "taskbar" in q or "bottom bar" in q or "start" in q:
                spatial_box = (0, int(h * 0.88), w, h)
            elif "center" in q or "middle" in q:
                spatial_box = (int(w * 0.33), int(h * 0.33), int(w * 0.66), int(h * 0.66))

            if spatial_box:
                sx1, sy1, sx2, sy2 = spatial_box
                matching_candidates = []
                for k, entry in c.items():
                    if not isinstance(entry, dict) or not str(k).startswith("#"):
                        continue
                    cx, cy = entry.get("center", (-1, -1))
                    if sx1 <= cx <= sx2 and sy1 <= cy <= sy2:
                        matching_candidates.append(entry)

                if matching_candidates:
                    if "close" in q:
                        matching_candidates.sort(key=lambda e: (e["center"][0] - e["center"][1]), reverse=True)
                    elif "taskbar" in q or "start" in q:
                        matching_candidates.sort(key=lambda e: e["center"][1], reverse=True)
                    else:
                        target_cx = (sx1 + sx2) / 2
                        target_cy = (sy1 + sy2) / 2
                        matching_candidates.sort(key=lambda e: (e["center"][0] - target_cx)**2 + (e["center"][1] - target_cy)**2)

                    best = matching_candidates[0]
                    return {
                        "found": True,
                        "center": best.get("center", (-1, -1)),
                        "tag": best.get("tag", ""),
                        "label": best.get("label", ""),
                        "rect": best.get("rect", (0, 0, 0, 0)),
                    }

                scx = (sx1 + sx2) // 2
                scy = (sy1 + sy2) // 2
                return {
                    "found": True,
                    "center": (scx, scy),
                    "tag": "",
                    "label": f"Spatial region '{q}' center",
                    "rect": (sx1, sy1, sx2 - sx1, sy2 - sy1),
                }

            return None

        # 1. Search existing cache first
        cache = self.get_som_cache()
        cached_result = _search_in_cache(cache)
        if cached_result is not None:
            return cached_result

        # 2. If not found in cache, refresh full-screen Set-of-Marks detection
        try:
            _, refreshed = self.detect_ui_elements_and_annotate_grid(window_title=window_title)
            if refreshed:
                fresh_result = _search_in_cache(refreshed)
                if fresh_result is not None:
                    return fresh_result
        except Exception as e:
            logger.debug("[Autonomous Screen Search] Screen detection refresh exception: %s", e)

        return {
            "found": False,
            "center": (-1, -1),
            "tag": "",
            "label": "",
            "reason": f"No matching element or spatial region found for '{target_query}'.",
        }

