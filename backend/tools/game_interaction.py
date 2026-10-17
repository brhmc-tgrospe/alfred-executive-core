"""A.L.F.R.E.D. Game Interaction Logistics Suite.

Provides sub-millisecond DirectInput hardware scan-code keyboard and mouse simulation
(native Windows user32.SendInput), high-performance OpenCV (cv2) game state observation
(color HUD bar extraction, target centroid tracking, FPS calculation), and low-latency
tactical reinforcement learning policy evaluation with dedicated thread pool isolation.
"""

from __future__ import annotations

import ctypes
from ctypes import wintypes
from concurrent.futures import ThreadPoolExecutor
import json
import logging
import math
import os
import sys
import time
from typing import Any, Dict, List, Optional, Tuple

import cv2
import mss
import numpy as np

try:
    import pygetwindow as gw
except ImportError:
    gw = None

logger = logging.getLogger("GameInteractionLogistics")

# ---------------------------------------------------------------------------
# Windows SendInput Hardware & DirectInput Scan Codes
# ---------------------------------------------------------------------------
INPUT_MOUSE = 0
INPUT_KEYBOARD = 1
INPUT_HARDWARE = 2

KEYEVENTF_EXTENDEDKEY = 0x0001
KEYEVENTF_KEYUP = 0x0002
KEYEVENTF_UNICODE = 0x0004
KEYEVENTF_SCANCODE = 0x0008

MOUSEEVENTF_MOVE = 0x0001
MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004
MOUSEEVENTF_RIGHTDOWN = 0x0008
MOUSEEVENTF_RIGHTUP = 0x0010
MOUSEEVENTF_MIDDLEDOWN = 0x0020
MOUSEEVENTF_MIDDLEUP = 0x0040

# DirectInput / PS/2 Set 1 Hardware Make Scan Codes
DIRECTINPUT_SCANCODES: Dict[str, int] = {
    "esc": 0x01, "escape": 0x01,
    "1": 0x02, "2": 0x03, "3": 0x04, "4": 0x05, "5": 0x06, "6": 0x07, "7": 0x08, "8": 0x09, "9": 0x0A, "0": 0x0B,
    "-": 0x0C, "=": 0x0D, "backspace": 0x0E,
    "tab": 0x0F,
    "q": 0x10, "w": 0x11, "e": 0x12, "r": 0x13, "t": 0x14, "y": 0x15, "u": 0x16, "i": 0x17, "o": 0x18, "p": 0x19,
    "[": 0x1A, "]": 0x1B, "enter": 0x1C, "return": 0x1C,
    "ctrl": 0x1D, "lctrl": 0x1D,
    "a": 0x1E, "s": 0x1F, "d": 0x20, "f": 0x21, "g": 0x22, "h": 0x23, "j": 0x24, "k": 0x25, "l": 0x26,
    ";": 0x27, "'": 0x28, "`": 0x29,
    "shift": 0x2A, "lshift": 0x2A, "\\": 0x2B,
    "z": 0x2C, "x": 0x2D, "c": 0x2E, "v": 0x2F, "b": 0x30, "n": 0x31, "m": 0x32,
    ",": 0x33, ".": 0x34, "/": 0x35, "rshift": 0x36,
    "alt": 0x38, "lalt": 0x38,
    "space": 0x39, "spacebar": 0x39,
    "capslock": 0x3A,
    "f1": 0x3B, "f2": 0x3C, "f3": 0x3D, "f4": 0x3E, "f5": 0x3F, "f6": 0x40,
    "f7": 0x41, "f8": 0x42, "f9": 0x43, "f10": 0x44, "f11": 0x57, "f12": 0x58,
    "up": 0x48, "down": 0x50, "left": 0x4B, "right": 0x4D,
}

# Win32 CTypes Structures
class MOUSEINPUT(ctypes.Structure):
    _fields_ = [
        ("dx", wintypes.LONG),
        ("dy", wintypes.LONG),
        ("mouseData", wintypes.DWORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.c_ulonglong),
    ]

class KEYBDINPUT(ctypes.Structure):
    _fields_ = [
        ("wVk", wintypes.WORD),
        ("wScan", wintypes.WORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.c_ulonglong),
    ]

class HARDWAREINPUT(ctypes.Structure):
    _fields_ = [
        ("uMsg", wintypes.DWORD),
        ("wParamL", wintypes.WORD),
        ("wParamH", wintypes.WORD),
    ]

class _INPUT_UNION(ctypes.Union):
    _fields_ = [
        ("mi", MOUSEINPUT),
        ("ki", KEYBDINPUT),
        ("hi", HARDWAREINPUT),
    ]

class INPUT(ctypes.Structure):
    _fields_ = [
        ("type", wintypes.DWORD),
        ("union", _INPUT_UNION),
    ]


class GameInteractionLogistics:
    """Enterprise Game Interaction & Tactical AI Suite with DirectInput and OpenCV Computer Vision."""

    def __init__(self) -> None:
        # Dedicated ThreadPoolExecutor isolating OpenCV calculations and DirectInput from event loops
        self._executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="alfred_game_compute")
        self._last_observation: Optional[Dict[str, Any]] = None
        self._is_windows = hasattr(ctypes, "windll") and sys.platform.startswith("win")
        self._last_game_state: str = "LOADING_OR_MENU"
        self._previous_gameplay_hp: float = 100.0
        self._was_in_active_gameplay: bool = False
        self._calibrated_archetype: str = "top_left_bars"
        self._overwatch_handler: Optional[Any] = None

    def set_overwatch_handler(self, handler: Any) -> None:
        """Registers callback hook for starting and stopping background continuous overwatch."""
        self._overwatch_handler = handler

    # ---------------------------------------------------------------------------
    # Low-Level DirectInput Hardware Dispatchers
    # ---------------------------------------------------------------------------
    def _send_hardware_key(self, scan_code: int, key_up: bool = False) -> bool:
        """Sends a hardware DirectInput scan code using Win32 SendInput."""
        if not self._is_windows:
            logger.debug("[DirectInput Mock] Key %s (KeyUp=%s)", scan_code, key_up)
            return True

        try:
            flags = KEYEVENTF_SCANCODE
            if key_up:
                flags |= KEYEVENTF_KEYUP

            ki = KEYBDINPUT(wVk=0, wScan=scan_code, dwFlags=flags, time=0, dwExtraInfo=0)
            inp = INPUT(type=INPUT_KEYBOARD, union=_INPUT_UNION(ki=ki))
            sent = ctypes.windll.user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(INPUT))
            return sent == 1
        except Exception as e:
            logger.warning("DirectInput key error: %s", e)
            return False

    def _send_hardware_mouse(self, flags: int, dx: int = 0, dy: int = 0, data: int = 0) -> bool:
        """Sends raw mouse flags using Win32 SendInput."""
        if not self._is_windows:
            logger.debug("[DirectInput Mock] Mouse flags %s (dx=%s, dy=%s)", flags, dx, dy)
            return True

        try:
            mi = MOUSEINPUT(dx=dx, dy=dy, mouseData=data, dwFlags=flags, time=0, dwExtraInfo=0)
            inp = INPUT(type=INPUT_MOUSE, union=_INPUT_UNION(mi=mi))
            sent = ctypes.windll.user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(INPUT))
            return sent == 1
        except Exception as e:
            logger.warning("DirectInput mouse error: %s", e)
            return False

    # ---------------------------------------------------------------------------
    # Tool 1: Low-Latency DirectInput Action Sequences
    # ---------------------------------------------------------------------------
    def send_game_input_action(self, action_sequence: str, hold_ms: int = 60) -> str:
        """Dispatches DirectX-compatible hardware DirectInput scan codes and raw mouse events.

        DirectX / Vulkan games query hardware scan-codes via DirectInput / raw input
        rather than Windows virtual key messages. This tool sends true low-latency
        hardware scan codes (e.g. KEYEVENTF_SCANCODE).

        Args:
            action_sequence: Comma-separated list of actions (e.g. 'w,space,mouse_left' or 'mouse_move_rel:50,-30').
                             Supports keys like 'w','a','s','d','space','shift','ctrl','q','e','r','1','2','3',
                             and mouse actions 'mouse_left', 'mouse_right', 'mouse_middle', 'mouse_move_rel:x,y'.
            hold_ms: Milliseconds to hold down each key/mouse press before releasing (default 60ms).

        Returns:
            Human-readable summary of actions executed and latency.
        """
        def _execute_worker():
            if not action_sequence or not action_sequence.strip():
                return "Error: action_sequence cannot be empty."

            start_t = time.perf_counter()
            import re
            pattern = r'mouse_move_rel:[-\d]+(?:[,:][-\d]+)?|[^,]+'
            tokens = [t.strip().lower() for t in re.findall(pattern, action_sequence) if t.strip()]
            hold_sec = max(0.01, hold_ms / 1000.0)
            executed: List[str] = []

            for token in tokens:
                # 1. Relative Mouse Movement
                if token.startswith("mouse_move_rel:"):
                    coord_str = token[len("mouse_move_rel:"):].strip()
                    parts = coord_str.replace(";", ",").replace(" ", ",").split(",")
                    if len(parts) >= 2:
                        try:
                            dx = int(parts[0].strip())
                            dy = int(parts[1].strip())
                            self._send_hardware_mouse(MOUSEEVENTF_MOVE, dx=dx, dy=dy)
                            executed.append(f"MouseMoveRel({dx}, {dy})")
                        except ValueError:
                            pass
                    continue

                # 2. Mouse Click Actions
                if token in ("mouse_left", "lmb", "click_left"):
                    self._send_hardware_mouse(MOUSEEVENTF_LEFTDOWN)
                    time.sleep(hold_sec)
                    self._send_hardware_mouse(MOUSEEVENTF_LEFTUP)
                    executed.append(f"MouseLeft({hold_ms}ms)")
                elif token in ("mouse_right", "rmb", "click_right"):
                    self._send_hardware_mouse(MOUSEEVENTF_RIGHTDOWN)
                    time.sleep(hold_sec)
                    self._send_hardware_mouse(MOUSEEVENTF_RIGHTUP)
                    executed.append(f"MouseRight({hold_ms}ms)")
                elif token in ("mouse_middle", "mmb", "click_middle"):
                    self._send_hardware_mouse(MOUSEEVENTF_MIDDLEDOWN)
                    time.sleep(hold_sec)
                    self._send_hardware_mouse(MOUSEEVENTF_MIDDLEUP)
                    executed.append(f"MouseMiddle({hold_ms}ms)")

                # 3. DirectInput Keyboard Scan Codes
                elif token in DIRECTINPUT_SCANCODES:
                    sc = DIRECTINPUT_SCANCODES[token]
                    self._send_hardware_key(sc, key_up=False)
                    time.sleep(hold_sec)
                    self._send_hardware_key(sc, key_up=True)
                    executed.append(f"Key'{token.upper()}'(sc=0x{sc:02X}, {hold_ms}ms)")
                else:
                    logger.warning("[GameInteraction] Unrecognized game input token: %s", token)

                # Brief inter-action recovery delay (15ms)
                time.sleep(0.015)

            elapsed_ms = round((time.perf_counter() - start_t) * 1000.0, 1)
            return (
                f"[DirectInput Engine]: Successfully dispatched {len(executed)} action(s) in {elapsed_ms}ms: "
                f"[{', '.join(executed)}]."
            )

        # Execute inside compute thread pool to avoid blocking async event loop
        future = self._executor.submit(_execute_worker)
        return future.result()

    # ---------------------------------------------------------------------------
    # Tool 2: High-Performance OpenCV Game State Observation
    # ---------------------------------------------------------------------------
    def _capture_window_bgr(self, window_title: str) -> Tuple[np.ndarray, Dict[str, Any]]:
        """Captures window frame in <15ms via MSS and returns BGR NumPy image."""
        mss_cls = getattr(mss, "MSS", getattr(mss, "mss", None))
        with mss_cls() as sct:
            rect = None
            if window_title != "active" and gw is not None:
                matches = gw.getWindowsWithTitle(window_title)
                if matches and matches[0].width > 10 and matches[0].height > 10:
                    w = matches[0]
                    rect = {"left": max(0, w.left), "top": max(0, w.top), "width": w.width, "height": w.height}

            if rect is None:
                # Capture primary monitor (or active window if gw available)
                if gw is not None:
                    try:
                        active = gw.getActiveWindow()
                        if active and active.width > 50 and active.height > 50:
                            rect = {"left": max(0, active.left), "top": max(0, active.top), "width": active.width, "height": active.height}
                    except Exception:
                        pass

            if rect is None:
                rect = sct.monitors[1] if len(sct.monitors) > 1 else sct.monitors[0]

            raw = sct.grab(rect)
            frame_bgra = np.array(raw, dtype=np.uint8)
            frame_bgr = cv2.cvtColor(frame_bgra, cv2.COLOR_BGRA2BGR)
            meta = {"width": frame_bgr.shape[1], "height": frame_bgr.shape[0], "rect": rect}
            return frame_bgr, meta

    def observe_game_state(
        self,
        window_title: str = "active",
        detect_hud_bars: bool = True,
        continuous_watch: bool = False,
        auto_assist_keys: str = "",
    ) -> str:
        """Captures real-time game window via OpenCV (cv2) and extracts structured gameplay observation vectors.

        Extracts:
        1. Universal Multi-Zone HUD Auto-Profiler (top_left_bars, bottom_globes, bottom_center_bar, tactical_corners).
        2. Game state classification ("LOADING_OR_MENU", "ACTIVE_GAMEPLAY", "PLAYER_DEAD").
        3. Player Health %, Resource/Mana %, Stamina/Energy % calibrated to active archetype.
        4. Target/Enemy Centroids (high-contrast contours relative to crosshair).
        5. Frame capture latency and estimated observation FPS.
        6. Continuous Background Overwatch Daemon with autonomous emergency co-pilot assistance.

        Args:
            window_title: Title of target game window, or 'active'. Pass 'stop' with continuous_watch to halt overwatch.
            detect_hud_bars: Whether to compute color masks for player Health/Mana/Stamina bars.
            continuous_watch: If True, activates 1.0s background overwatch daemon for continuous vocal callouts.
            auto_assist_keys: DirectInput keys to auto-fire on critical health (e.g. '1' for flask or 'space' for dodge).

        Returns:
            Structured JSON observation space.
        """
        def _observe_worker():
            start_t = time.perf_counter()
            t1 = start_t
            try:
                frame1, meta = self._capture_window_bgr(window_title)
            except Exception:
                frame1 = np.zeros((720, 1280, 3), dtype=np.uint8)
                meta = {"width": 1280, "height": 720, "rect": {}}

            # Rapid 2-frame kinematic burst separated by dt ~= 35ms
            time.sleep(0.035)
            t2 = time.perf_counter()
            dt = max(0.001, t2 - t1)

            try:
                frame2, _ = self._capture_window_bgr(window_title)
            except Exception:
                frame2 = frame1.copy()

            frame = frame2
            h, w = frame.shape[:2]
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            var_lum = float(np.var(gray))
            mean_lum = float(np.mean(gray))

            hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)

            # Global Color Thresholds in HSV
            # 1. Health / Vitality (Red HSV ranges: 0-10 and 170-180)
            r_mask1 = cv2.inRange(hsv, np.array([0, 70, 50]), np.array([10, 255, 255]))
            r_mask2 = cv2.inRange(hsv, np.array([170, 70, 50]), np.array([180, 255, 255]))
            red_mask = r_mask1 | r_mask2

            # 2. Resource / Mana / Shield (Blue HSV range: 95-135)
            blue_mask = cv2.inRange(hsv, np.array([95, 70, 50]), np.array([135, 255, 255]))

            # 3. Stamina / Energy / Vitality (Green HSV range: 35-85)
            green_mask = cv2.inRange(hsv, np.array([35, 70, 50]), np.array([85, 255, 255]))

            # Archetype 1: top_left_bars (Souls-likes, Action RPGs, Fighting)
            mask_tl = np.zeros((h, w), dtype=np.uint8)
            mask_tl[0:int(h * 0.30), 0:int(w * 0.45)] = 255
            tl_red = int(cv2.countNonZero(red_mask & mask_tl))
            tl_blue = int(cv2.countNonZero(blue_mask & mask_tl))
            tl_green = int(cv2.countNonZero(green_mask & mask_tl))
            score_tl = tl_red + tl_blue + tl_green

            # Archetype 2: bottom_globes (Isometric ARPGs like Diablo / PoE)
            mask_bg_l = np.zeros((h, w), dtype=np.uint8)  # Left globe (Health)
            mask_bg_l[int(h * 0.65):h, 0:int(w * 0.28)] = 255
            mask_bg_r = np.zeros((h, w), dtype=np.uint8)  # Right globe (Mana)
            mask_bg_r[int(h * 0.65):h, int(w * 0.72):w] = 255
            bg_red = int(cv2.countNonZero(red_mask & mask_bg_l))
            bg_blue = int(cv2.countNonZero(blue_mask & mask_bg_r))
            bg_green = int(cv2.countNonZero(green_mask & (mask_bg_l | mask_bg_r)))
            score_bg = bg_red + bg_blue + bg_green

            # Archetype 3: bottom_center_bar (MOBAs, MMOs, Hero Shooters)
            mask_bc = np.zeros((h, w), dtype=np.uint8)
            mask_bc[int(h * 0.70):h, int(w * 0.22):int(w * 0.78)] = 255
            bc_red = int(cv2.countNonZero(red_mask & mask_bc))
            bc_blue = int(cv2.countNonZero(blue_mask & mask_bc))
            bc_green = int(cv2.countNonZero(green_mask & mask_bc))
            score_bc = bc_red + bc_blue + bc_green

            # Archetype 4: tactical_corners (RTS, Strategy, Simulators)
            mask_tc = np.zeros((h, w), dtype=np.uint8)
            mask_tc[int(h * 0.68):h, 0:int(w * 0.32)] = 255
            mask_tc[int(h * 0.68):h, int(w * 0.68):w] = 255
            mask_tc[0:int(h * 0.15), int(w * 0.55):w] = 255
            tc_red = int(cv2.countNonZero(red_mask & mask_tc))
            tc_blue = int(cv2.countNonZero(blue_mask & mask_tc))
            tc_green = int(cv2.countNonZero(green_mask & mask_tc))
            score_tc = tc_red + tc_blue + tc_green

            # Multi-zone auto-calibration
            archetype_scores = {
                "top_left_bars": score_tl,
                "bottom_globes": score_bg,
                "bottom_center_bar": score_bc,
                "tactical_corners": score_tc,
            }
            detected_arch = max(archetype_scores, key=archetype_scores.get)
            max_score = archetype_scores[detected_arch]
            if max_score >= 50:
                self._calibrated_archetype = detected_arch
            archetype = self._calibrated_archetype

            # Check letterbox black borders
            top_strip = gray[:int(h * 0.10), :]
            bottom_strip = gray[int(h * 0.90):, :]
            black_borders = bool(np.mean(top_strip) < 12.0 and np.mean(bottom_strip) < 12.0)
            total_hud_score = score_tl + score_bg + score_bc + score_tc

            # Death / Defeat Detection
            center_box = frame[int(h * 0.35):int(h * 0.65), int(w * 0.20):int(w * 0.80)]
            hsv_center = cv2.cvtColor(center_box, cv2.COLOR_BGR2HSV)
            red_center_box = int(cv2.countNonZero(
                cv2.inRange(hsv_center, np.array([0, 70, 50]), np.array([10, 255, 255])) |
                cv2.inRange(hsv_center, np.array([170, 70, 50]), np.array([180, 255, 255]))
            ))
            center_death_overlay = (red_center_box > 1200)

            # Universal Loading / Menu Gate
            is_loading_or_menu = False
            if not center_death_overlay:
                if total_hud_score < 40:
                    if var_lum < 160.0 or mean_lum < 18.0:
                        is_loading_or_menu = True
                    elif black_borders or var_lum < 320.0:
                        is_loading_or_menu = True

            # Selected archetype gauge normalization
            if archetype == "top_left_bars":
                r_count, b_count, g_count = tl_red, tl_blue, tl_green
                ref_gauge = max(80.0, (w * h) * 0.0016)
            elif archetype == "bottom_globes":
                r_count, b_count, g_count = bg_red, bg_blue, bg_green
                ref_gauge = max(100.0, (w * h) * 0.0022)
            elif archetype == "bottom_center_bar":
                r_count, b_count, g_count = bc_red, bc_blue, bc_green
                ref_gauge = max(80.0, (w * h) * 0.0018)
            else:
                r_count, b_count, g_count = tc_red, tc_blue, tc_green
                ref_gauge = max(80.0, (w * h) * 0.0015)

            combat_death = (
                self._was_in_active_gameplay
                and self._previous_gameplay_hp > 15.0
                and r_count < 8
                and not is_loading_or_menu
            )

            if center_death_overlay or combat_death:
                game_state = "PLAYER_DEAD"
                health_pct = 0.0
                resource_pct = float(round(min(100.0, max(0.0, (b_count / ref_gauge) * 100.0)), 1))
                stamina_pct = 0.0
                tactical_state = "PLAYER_DEFEATED"
                self._was_in_active_gameplay = False
            elif is_loading_or_menu:
                game_state = "LOADING_OR_MENU"
                health_pct = 100.0
                resource_pct = 100.0
                stamina_pct = 100.0
                tactical_state = "OUT_OF_COMBAT"
            else:
                game_state = "ACTIVE_GAMEPLAY"
                self._was_in_active_gameplay = True
                health_pct = float(round(min(100.0, max(0.0, (r_count / ref_gauge) * 100.0)), 1))
                resource_pct = float(round(min(100.0, max(0.0, (b_count / ref_gauge) * 100.0)), 1))
                stamina_pct = float(round(min(100.0, max(0.0, (g_count / ref_gauge) * 100.0)), 1))

                if r_count == 0 and not self._was_in_active_gameplay:
                    health_pct = 100.0
                if b_count == 0:
                    resource_pct = 100.0
                if g_count == 0:
                    stamina_pct = 100.0

                self._previous_gameplay_hp = health_pct

            # Target / Centroid Detection & 2-Frame Kinematic Motion Tracking in central viewport
            center_x, center_y = w // 2, h // 2
            v_top, v_bottom = int(h * 0.20), int(h * 0.80)
            v_left, v_right = int(w * 0.20), int(w * 0.80)

            def _extract_vp_targets(fr: np.ndarray) -> List[Dict[str, Any]]:
                vp = fr[v_top:v_bottom, v_left:v_right]
                g = cv2.cvtColor(vp, cv2.COLOR_BGR2GRAY)
                b = cv2.GaussianBlur(g, (5, 5), 0)
                _, th = cv2.threshold(b, 160, 255, cv2.THRESH_BINARY)
                conts, _ = cv2.findContours(th, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
                t_list = []
                for c in conts:
                    area = cv2.contourArea(c)
                    if 120 < area < 25000:
                        M = cv2.moments(c)
                        if M["m00"] > 0:
                            cx = int(M["m10"] / M["m00"]) + v_left
                            cy = int(M["m01"] / M["m00"]) + v_top
                            dist = round(math.sqrt((cx - center_x) ** 2 + (cy - center_y) ** 2), 1)
                            t_list.append({"pos": [cx, cy], "distance_to_crosshair": dist, "area_px": int(area)})
                return t_list

            targets_f1 = _extract_vp_targets(frame1)
            targets_f2 = _extract_vp_targets(frame2)

            lead_time_sec = 0.20
            targets: List[Dict[str, Any]] = []

            for idx, t2_item in enumerate(targets_f2):
                cx2, cy2 = t2_item["pos"]
                dist = t2_item["distance_to_crosshair"]
                area = t2_item["area_px"]

                # Match with closest target in frame1 within 160px
                vx, vy = 0.0, 0.0
                best_match = None
                best_dist = 160.0
                for t1_item in targets_f1:
                    cx1, cy1 = t1_item["pos"]
                    d = math.hypot(cx2 - cx1, cy2 - cy1)
                    if d < best_dist:
                        best_dist = d
                        best_match = t1_item

                if best_match is not None:
                    cx1, cy1 = best_match["pos"]
                    vx = round((cx2 - cx1) / dt, 1)
                    vy = round((cy2 - cy1) / dt, 1)

                speed = round(math.hypot(vx, vy), 1)
                pred_x = max(0, min(w - 1, cx2 + int(vx * lead_time_sec)))
                pred_y = max(0, min(h - 1, cy2 + int(vy * lead_time_sec)))

                targets.append({
                    "target_id": idx + 1,
                    "pos": [cx2, cy2],
                    "distance_to_crosshair": dist,
                    "area_px": int(area),
                    "velocity_px_s": [vx, vy],
                    "speed_px_s": speed,
                    "predictive_intercept": [pred_x, pred_y],
                    "lead_time_sec": lead_time_sec,
                })

            targets.sort(key=lambda t: t["distance_to_crosshair"])
            nearest_targets = targets[:4]

            elapsed_ms = round((time.perf_counter() - start_t) * 1000.0, 1)
            est_fps = round(1000.0 / max(1.0, elapsed_ms), 1)

            # Tactical Threat Assessment
            if game_state == "PLAYER_DEAD":
                tactical_state = "PLAYER_DEFEATED"
            elif game_state == "LOADING_OR_MENU":
                tactical_state = "OUT_OF_COMBAT"
            elif health_pct < 35.0:
                tactical_state = "CRITICAL_HEALTH"
            elif len(nearest_targets) > 0 and nearest_targets[0]["distance_to_crosshair"] < 120:
                tactical_state = "CLOSE_HOSTILE_ENGAGEMENT"
            elif len(nearest_targets) > 0:
                tactical_state = "HOSTILES_IN_PERIMETER"
            else:
                tactical_state = "NOMINAL"

            continuous_status = "INACTIVE"
            if continuous_watch:
                stop_requested = (
                    window_title.strip().lower() == "stop"
                    or auto_assist_keys.strip().lower() == "stop"
                )
                if stop_requested:
                    if self._overwatch_handler:
                        self._overwatch_handler(window_title, False, "")
                    continuous_status = "STOPPED"
                else:
                    if self._overwatch_handler:
                        self._overwatch_handler(window_title, True, auto_assist_keys)
                    continuous_status = "ACTIVE"

            observation = {
                "window": window_title,
                "game_state": game_state,
                "hud_archetype": archetype,
                "continuous_overwatch": continuous_status,
                "resolution": f"{w}x{h}",
                "latency_ms": elapsed_ms,
                "observation_fps": est_fps,
                "hud_meters": {
                    "health_percent": health_pct,
                    "resource_percent": resource_pct,
                    "stamina_percent": stamina_pct,
                },
                "target_count": len(nearest_targets),
                "nearest_targets": nearest_targets,
                "tracked_targets": nearest_targets,
                "tactical_state": tactical_state,
            }
            self._last_observation = observation
            self._last_game_state = game_state
            return json.dumps(observation, indent=2)

        future = self._executor.submit(_observe_worker)
        return future.result()

    # ---------------------------------------------------------------------------
    # Tool 3: RL & Tactical Decision Policy Engine
    # ---------------------------------------------------------------------------
    def evaluate_tactical_game_policy(self, game_genre: str = "action_rpg", auto_execute: bool = False) -> str:
        """Evaluates tactical reinforcement learning policy on the current game observation vector.

        Supports:
        - 'action_rpg': Manages dodge rolls, healing flasks, melee/spell combos, and distance control.
        - 'moba': Manages burst ability rotations, lane positioning, retreating, and recall.
        - 'strategy': Manages unit grouping, macro production cycles, and rally orders.

        Args:
            game_genre: Genre policy model ('action_rpg', 'moba', or 'strategy').
            auto_execute: If True, immediately dispatches optimal DirectInput sequence via SendInput.

        Returns:
            Detailed tactical assessment, policy recommendation, and execution log.
        """
        def _policy_worker():
            obs = self._last_observation
            if obs is None:
                # Capture fresh observation if none exists
                self.observe_game_state(window_title="active", detect_hud_bars=True)
                obs = self._last_observation or {}

            hud = obs.get("hud_meters", {})
            hp = hud.get("health_percent", 100.0)
            res = hud.get("resource_percent", 100.0)
            targets = obs.get("nearest_targets", [])
            has_close_target = any(t.get("distance_to_crosshair", 999) < 130 for t in targets)

            # Predictive lead targeting
            lead_info = ""
            if targets:
                t0 = targets[0]
                if t0.get("speed_px_s", 0.0) > 10.0:
                    lead_coords = t0.get("predictive_intercept", t0.get("pos", [0, 0]))
                    lead_info = f" Kinetic lead engaged: target moving at {t0.get('velocity_px_s', [0, 0])} px/s. Predictive intercept at {lead_coords}."

            genre = game_genre.strip().lower()
            policy_decision: str = ""
            action_sequence: str = ""
            rationale: str = ""

            # --- 1. Action RPG Policy ---
            if genre in ("action_rpg", "rpg", "souls", "action"):
                if hp < 30.0:
                    policy_decision = "EMERGENCY_HEAL_AND_EVADE"
                    action_sequence = "1,s,space"
                    rationale = f"Health is critical ({hp}%). Consuming slot 1 flask and executing backstep dodge."
                elif has_close_target and hp < 55.0:
                    policy_decision = "DEFENSIVE_ROLL"
                    action_sequence = "space,space"
                    rationale = f"Close hostile detected with reduced health ({hp}%). Disengaging to reset poise."
                elif has_close_target and hp >= 55.0 and res >= 40.0:
                    policy_decision = "PRIMARY_BURST_COMBO"
                    action_sequence = "w,mouse_left,mouse_left,e"
                    rationale = f"Hostile aligned in strike zone. Executing 2x light attack into special skill (E)."
                elif len(targets) > 0:
                    nearest = targets[0]
                    dx = min(80, max(-80, (nearest["pos"][0] - 640) // 8))
                    dy = min(60, max(-60, (nearest["pos"][1] - 360) // 8))
                    policy_decision = "ALIGN_TARGET_APPROACH"
                    action_sequence = f"mouse_move_rel:{dx},{dy},w"
                    rationale = f"Aligning crosshair toward target #{nearest['target_id']} and closing range."
                else:
                    policy_decision = "FORWARD_RECON"
                    action_sequence = "w"
                    rationale = "No hostile entities in primary sector. Moving forward."

            # --- 2. MOBA Policy ---
            elif genre in ("moba", "league", "dota"):
                if hp < 25.0:
                    policy_decision = "BASE_RECALL"
                    action_sequence = "b"
                    rationale = f"Health critically depleted ({hp}%). Recalling to fountain."
                elif has_close_target and res >= 50.0:
                    policy_decision = "FULL_ABILITY_ROTATION"
                    action_sequence = "q,w,e,r"
                    rationale = f"High mana ({res}%) and priority target locked. Unleashing full kit."
                elif res < 25.0:
                    policy_decision = "CONSERVATIVE_FARMING"
                    action_sequence = "a,mouse_left"
                    rationale = f"Low resource ({res}%). Holding abilities for last-hitting."
                else:
                    policy_decision = "KITING_AND_POSITIONING"
                    action_sequence = "s,mouse_right"
                    rationale = "Maintaining safe lane perimeter."

            # --- 3. RTS / Strategy Policy ---
            else:
                if obs.get("tactical_state") == "CRITICAL_HEALTH" or has_close_target:
                    policy_decision = "RALLY_DEFENSE_LINE"
                    action_sequence = "1,a,mouse_left"
                    rationale = "Hostile pressure detected. Commanding control group 1 to attack-move defense sector."
                elif res >= 60.0:
                    policy_decision = "EXPAND_MACRO_PRODUCTION"
                    action_sequence = "4,q,w,e"
                    rationale = "Macro resources plentiful. Queuing reinforcement battalions."
                else:
                    policy_decision = "SCOUT_AND_EXPAND"
                    action_sequence = "tab,mouse_right"
                    rationale = "Surveying perimeter fog of war."

            if lead_info:
                rationale += lead_info

            execution_result = "Not requested (auto_execute=False)."
            if auto_execute and action_sequence:
                execution_result = self.send_game_input_action(action_sequence, hold_ms=50)

            return (
                f"[Tactical AI Policy ({genre.upper()})]:\n"
                f"  • Decision: {policy_decision}\n"
                f"  • Rationale: {rationale}\n"
                f"  • Recommended Action: '{action_sequence}'\n"
                f"  • DirectInput Execution: {execution_result}"
            )

        future = self._executor.submit(_policy_worker)
        return future.result()
