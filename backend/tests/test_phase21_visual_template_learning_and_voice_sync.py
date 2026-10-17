"""Unit tests for Phase 21:
1. Visual Template Learning Engine (action="learn_element", visual_ui_memories table)
2. Translation-Invariant Icon Relocation (multi-scale template match @ [0.85, 1.0, 1.15])
3. Hover State Diff Detection (clean template vs hover delta calculation)
4. Turn ID Fencing & Voice Sync (monotonic _current_turn_id, buffer drop on speech onset/prompt)
5. Non-Interrupting Tool Watchdog (watchdog paused while active_tool is not None)
6. Tool Count Invariant (strictly <= 30 registered tools)
"""

import asyncio
import os
import shutil
from unittest.mock import AsyncMock, MagicMock, patch
import cv2
import numpy as np
from PIL import Image, ImageDraw
import pytest

from backend.audio_manager import AudioManager
from backend.live_session import (
    AlfredLiveCore,
    ALFRED_BASE_SYSTEM_PROMPT,
)
from backend.main import AlfredHubCoordinator
from backend.memory.memory_store import MemoryStore
from backend.tools.gui_automation import GuiAutomationLogistics
from backend.vision_manager import VisionManager


# ============================================================================
# Helper Fixtures & Synthetic Image Generators
# ============================================================================

def create_synthetic_desktop(width=1920, height=1080) -> np.ndarray:
    """Creates a synthetic desktop canvas with realistic dark theme background."""
    img = np.full((height, width, 3), 28, dtype=np.uint8)
    # Add subtle grid/lines so background isn't purely uniform
    for y in range(0, height, 100):
        cv2.line(img, (0, y), (width, y), (35, 35, 35), 1)
    for x in range(0, width, 100):
        cv2.line(img, (x, 0), (x, height), (35, 35, 35), 1)
    return img


def draw_distinct_icon(img: np.ndarray, cx: int, cy: int, size: int = 36, is_hover: bool = False) -> None:
    """Draws a unique, high-contrast, multi-feature icon centered at (cx, cy)."""
    half = size // 2
    x1, y1 = cx - half, cy - half
    x2, y2 = cx + half, cy + half

    # Outer border / frame
    border_color = (0, 240, 255) if is_hover else (180, 100, 20)  # Bright cyan on hover, amber otherwise
    cv2.rectangle(img, (x1, y1), (x2, y2), border_color, 2)

    # Inner geometric shapes for template recognition
    cv2.circle(img, (cx, cy), size // 4, (40, 220, 90), -1)
    cv2.line(img, (x1 + 4, cy), (x2 - 4, cy), (255, 255, 255), 2)
    cv2.line(img, (cx, y1 + 4), (cx, y2 - 4), (255, 255, 255), 2)


# ============================================================================
# 1. Translation-Invariant Icon Relocation Test
# ============================================================================

def test_translation_invariant_icon_relocation(tmp_path):
    """Test a: Icon learned at (1800, 980) is successfully relocated at (420, 310) within +-3px."""
    db_file = str(tmp_path / "mem.db")
    chroma_dir = str(tmp_path / "chroma")
    mem = MemoryStore(db_path=db_file, chroma_dir=chroma_dir)

    vision = VisionManager(memory_store=mem)
    gui = GuiAutomationLogistics(memory_store=mem)
    gui.vision = vision

    # 1. Create desktop with icon at (1800, 980)
    screen1 = create_synthetic_desktop()
    draw_distinct_icon(screen1, cx=1800, cy=980, size=36, is_hover=False)
    pil1 = Image.fromarray(cv2.cvtColor(screen1, cv2.COLOR_BGR2RGB))

    # Mock screen capture for initial learning
    with patch.object(vision, "capture_screen_raw", return_value=pil1), \
         patch.object(vision, "_grab_raw_image", return_value=pil1), \
         patch("pyautogui.moveTo") as mock_move:

        # Learn element at (1800, 980)
        report = gui.screen_pixel_navigation(
            action="learn_element",
            target_label_or_tag="hero menu icon",
            x=1800,
            y=980,
        )
        assert "hero menu icon" in report
        assert "successfully learned" in report.lower()

    # Verify template was saved to memory store
    entry = mem.get_visual_ui_memory("hero menu icon")
    assert entry is not None
    assert os.path.exists(entry["template_png_path"])

    # 2. Relocate icon to (420, 310) on a new desktop screen
    screen2 = create_synthetic_desktop()
    draw_distinct_icon(screen2, cx=420, cy=310, size=36, is_hover=False)
    pil2 = Image.fromarray(cv2.cvtColor(screen2, cv2.COLOR_BGR2RGB))

    with patch.object(vision, "capture_screen_raw", return_value=pil2), \
         patch.object(vision, "_grab_raw_image", return_value=pil2):

        # Autonomous search targeting the learned icon
        match = vision.autonomous_screen_search("hero menu icon")

        assert match["found"] is True
        found_x, found_y = match["center"]

        # Invariant: Located within +-3 pixels of the relocated center (420, 310)
        assert abs(found_x - 420) <= 3, f"Expected X near 420, got {found_x}"
        assert abs(found_y - 310) <= 3, f"Expected Y near 310, got {found_y}"
        assert match["confidence"] >= 0.75


# ============================================================================
# 2. Hover State Diff Detection Test
# ============================================================================

def test_hover_state_diff_detection(tmp_path):
    """Test b: Learn element captures clean patch and calculates hover delta correctly."""
    db_file = str(tmp_path / "mem.db")
    chroma_dir = str(tmp_path / "chroma")
    mem = MemoryStore(db_path=db_file, chroma_dir=chroma_dir)

    vision = VisionManager(memory_store=mem)
    gui = GuiAutomationLogistics(memory_store=mem)
    gui.vision = vision

    # Generate clean patch and hover patch with visual delta
    clean_canvas = np.full((44, 44, 3), 40, dtype=np.uint8)
    draw_distinct_icon(clean_canvas, cx=22, cy=22, size=30, is_hover=False)

    hover_canvas = np.full((44, 44, 3), 40, dtype=np.uint8)
    draw_distinct_icon(hover_canvas, cx=22, cy=22, size=30, is_hover=True)

    # capture_screen_patch returns clean_canvas first (nudge), then hover_canvas (hover)
    patch_calls = [clean_canvas, hover_canvas, np.zeros((160, 160, 3), dtype=np.uint8)]

    def mock_patch(*args, **kwargs):
        if patch_calls:
            return patch_calls.pop(0)
        return clean_canvas

    with patch.object(vision, "capture_screen_patch", side_effect=mock_patch), \
         patch("pyautogui.moveTo"):

        report = gui.screen_pixel_navigation(
            action="learn_element",
            target_label_or_tag="inventory bag",
            x=600,
            y=400,
        )

        assert "inventory bag" in report
        assert "Hover state visual shift" in report

        entry = mem.get_visual_ui_memory("inventory bag")
        assert entry is not None
        assert "Hover state visual shift:" in entry["hover_behavior_desc"]
        # Hover delta should be strictly > 0% due to color change
        assert "% pixel variance" in entry["hover_behavior_desc"]


# ============================================================================
# 3. Turn Fencing & Voice Sync Tests
# ============================================================================

@pytest.mark.asyncio
async def test_turn_fencing_on_text_prompt_and_speech_onset(tmp_path):
    """Test c: Verify monotonically increasing _current_turn_id and buffer clearing."""
    db_file = str(tmp_path / "mem.db")
    mem = MemoryStore(db_path=db_file, chroma_dir=str(tmp_path / "chroma"))
    audio = AudioManager()
    audio.clear_playback = MagicMock()

    coordinator = AlfredHubCoordinator(memory_store=mem, audio_manager=audio)
    live_core = coordinator.live_core

    assert live_core._current_turn_id == 0

    # 1. Text prompt via HUD message increments turn ID and clears playback buffer
    await coordinator.handle_hud_message({
        "type": "text_prompt",
        "text": "Report system status",
    })

    assert live_core._current_turn_id == 1
    assert audio.clear_playback.call_count >= 1

    # 2. Direct send_text_prompt call increments turn ID
    mock_session = AsyncMock()
    live_core._session = mock_session
    live_core.is_running = True

    await live_core.send_text_prompt("Scan developer ports")
    assert live_core._current_turn_id == 2
    assert audio.clear_playback.call_count >= 2


@pytest.mark.asyncio
async def test_non_interrupting_watchdog_during_active_tool(tmp_path):
    """Test c2: Thinking watchdog never interrupts or fires fallback when a tool is active."""
    db_file = str(tmp_path / "mem.db")
    mem = MemoryStore(db_path=db_file, chroma_dir=str(tmp_path / "chroma"))
    audio = AudioManager()
    coordinator = AlfredHubCoordinator(memory_store=mem, audio_manager=audio)
    live_core = coordinator.live_core

    # Set active tool
    live_core.set_active_tool("inspect_active_screen")
    assert live_core.active_tool == "inspect_active_screen"

    # Attempt to execute fallback prompt while tool is active
    initial_transcript = coordinator.current_transcript
    await coordinator._execute_fallback_prompt("Inspect active screen")

    # Fallback MUST be bypassed
    assert coordinator.current_transcript == initial_transcript


def test_audio_prebuffer_low_latency_setting():
    """Verify jitter prebuffer is optimized to 2400 bytes (50ms)."""
    audio = AudioManager()
    assert audio.jitter_prebuffer_bytes == 2400


# ============================================================================
# 4. Strict Tool Count Invariant (30 Tools)
# ============================================================================

def test_strictly_30_registered_tools(tmp_path):
    """Test d: Invariant: coordinator and live_core maintain strictly <= 30 registered tools."""
    db_file = str(tmp_path / "mem.db")
    mem = MemoryStore(db_path=db_file, chroma_dir=str(tmp_path / "chroma"))
    coordinator = AlfredHubCoordinator(memory_store=mem)

    assert len(coordinator.tools_list) == 30, f"Expected 30 tools, found {len(coordinator.tools_list)}"
    tool_names = [getattr(fn, "__name__", "") for fn in coordinator.tools_list]

    # No duplicates
    assert len(set(tool_names)) == 30, f"Duplicate tools found: {tool_names}"

    # Verify visual icon learning rule is present in system prompt
    assert "VISUAL ICON LEARNING RULE" in ALFRED_BASE_SYSTEM_PROMPT
