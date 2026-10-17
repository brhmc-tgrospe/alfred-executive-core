"""Unit tests for Phase 22:
1. Small Icon Over Changing Background Test (26x26 TaskBar Hero icon learned on dark bg, relocated to bright bg)
2. Large Icon / Button Recognition Test (220x90 custom button auto-bounded w>150, h>60, relocated & resized by 1.3x)
3. First-Boot Mic Auto-Unlock Test (_stream_mic_to_alfred unlocks within 4s even if _startup_briefing_completed is never set)
4. Mid-Speech Voice 'Stop' & Spoken Reply Test (saying 'stop' while status == 'speaking' flushes playback and triggers spoken stop confirmation)
"""

import asyncio
import os
import time
from unittest.mock import AsyncMock, MagicMock, patch
import cv2
import numpy as np
from PIL import Image
import pytest

from backend.audio_manager import AudioManager
from backend.live_session import AlfredLiveCore
from backend.main import AlfredHubCoordinator
from backend.memory.memory_store import MemoryStore
from backend.tools.gui_automation import GuiAutomationLogistics
from backend.vision_manager import VisionManager


# ============================================================================
# Synthetic Icon & Button Generators
# ============================================================================

def draw_taskbar_hero_26x26_icon(canvas: np.ndarray, cx: int, cy: int) -> None:
    """Draws a 26x26 brown-and-gold pixel-art TaskBar Hero menu icon centered at (cx, cy)."""
    half = 13  # 26x26 total size
    x1, y1 = cx - half, cy - half
    x2, y2 = cx + half, cy + half

    # Outer dark brown wooden frame (BGR: 30, 65, 110)
    cv2.rectangle(canvas, (x1, y1), (x2 - 1, y2 - 1), (30, 65, 110), -1)
    # Gold pixel-art trim border (BGR: 35, 195, 245)
    cv2.rectangle(canvas, (x1 + 2, y1 + 2), (x2 - 3, y2 - 3), (35, 195, 245), 2)
    # Inner rich brown shield fill (BGR: 45, 90, 150)
    cv2.rectangle(canvas, (x1 + 5, y1 + 5), (x2 - 6, y2 - 6), (45, 90, 150), -1)
    # Gold emblem cross + central ruby gem inside the tight core
    cv2.line(canvas, (cx - 5, cy), (cx + 5, cy), (40, 215, 255), 2)
    cv2.line(canvas, (cx, cy - 5), (cx, cy + 5), (40, 215, 255), 2)
    cv2.circle(canvas, (cx, cy), 3, (40, 50, 230), -1)


def draw_large_custom_button(canvas: np.ndarray, cx: int, cy: int, w: int = 220, h: int = 90) -> None:
    """Draws a large custom UI button centered at (cx, cy) with dimensions (w, h)."""
    x1, y1 = int(round(cx - w / 2.0)), int(round(cy - h / 2.0))
    x2, y2 = x1 + w, y1 + h

    # Deep royal blue button body (BGR: 140, 60, 25)
    cv2.rectangle(canvas, (x1, y1), (x2 - 1, y2 - 1), (140, 60, 25), -1)
    # Bright gold outer border
    border_t = max(2, int(round(3 * (w / 220.0))))
    cv2.rectangle(canvas, (x1, y1), (x2 - 1, y2 - 1), (30, 200, 250), border_t)
    # Inner decorative frame
    inset = max(6, int(round(8 * (w / 220.0))))
    cv2.rectangle(canvas, (x1 + inset, y1 + inset), (x2 - 1 - inset, y2 - 1 - inset), (180, 120, 40), 2)

    # Distinct geometric emblem on the left and bars on the right (scales proportionally)
    emblem_x = x1 + int(round(w * 0.25))
    emblem_r = int(round(min(w, h) * 0.22))
    cv2.circle(canvas, (emblem_x, cy), emblem_r, (50, 220, 255), -1)
    cv2.circle(canvas, (emblem_x, cy), max(2, emblem_r // 2), (140, 60, 25), -1)

    bar_x1 = x1 + int(round(w * 0.45))
    bar_x2 = x1 + int(round(w * 0.85))
    bar_h = max(3, int(round(h * 0.10)))
    cv2.rectangle(canvas, (bar_x1, cy - bar_h * 2), (bar_x2, cy - bar_h), (240, 240, 255), -1)
    cv2.rectangle(canvas, (bar_x1, cy + bar_h), (bar_x2 - int(w * 0.12), cy + bar_h * 2), (80, 210, 255), -1)


# ============================================================================
# Test a: Small Icon Over Changing Background Test
# ============================================================================

def test_small_icon_over_changing_background(tmp_path):
    """Place the 26x26 brown-and-gold TaskBar Hero menu icon on a dark background at (1800, 980),
    learn it, then move it to (350, 200) on a bright/completely different background—assert that
    Tight-Core template + HSV matching still finds (350, 200) within +-3px!
    """
    mem = MemoryStore(db_path=str(tmp_path / "mem.db"), chroma_dir=str(tmp_path / "chroma"))
    vision = VisionManager(memory_store=mem)
    gui = GuiAutomationLogistics(memory_store=mem)
    gui.vision = vision

    # 1. Dark background (BGR: 22, 20, 18) with 26x26 icon at (1800, 980)
    dark_screen = np.full((1080, 1920, 3), (22, 20, 18), dtype=np.uint8)
    draw_taskbar_hero_26x26_icon(dark_screen, cx=1800, cy=980)
    pil_dark = Image.fromarray(cv2.cvtColor(dark_screen, cv2.COLOR_BGR2RGB))

    with patch.object(vision, "capture_screen_raw", return_value=pil_dark), \
         patch.object(vision, "_grab_raw_image", return_value=pil_dark), \
         patch("pyautogui.moveTo"):

        report = gui.screen_pixel_navigation(
            action="learn_element",
            target_label_or_tag="taskbar hero menu",
            x=1800,
            y=980,
        )
        assert "taskbar hero menu" in report.lower()

    entry = mem.get_visual_ui_memory("taskbar hero menu")
    assert entry is not None
    assert os.path.exists(entry["template_png_path"])
    assert entry.get("core_png_path") and os.path.exists(entry["core_png_path"])
    # Detected natural bounds for 26x26 icon should be compact (not 44x44)
    assert 18 <= entry["width"] <= 34
    assert 18 <= entry["height"] <= 34

    # 2. Relocate the 26x26 icon to (350, 200) on a BRIGHT sky-blue/cream background with pattern
    bright_screen = np.full((1080, 1920, 3), (235, 225, 210), dtype=np.uint8)
    for y in range(0, 1080, 60):
        cv2.line(bright_screen, (0, y), (1920, y), (210, 195, 175), 2)
    draw_taskbar_hero_26x26_icon(bright_screen, cx=350, cy=200)
    pil_bright = Image.fromarray(cv2.cvtColor(bright_screen, cv2.COLOR_BGR2RGB))

    with patch.object(vision, "capture_screen_raw", return_value=pil_bright), \
         patch.object(vision, "_grab_raw_image", return_value=pil_bright):

        match = vision.autonomous_screen_search("taskbar hero menu")
        assert match["found"] is True, f"Expected to find icon on bright bg, got: {match}"
        fx, fy = match["center"]
        assert abs(fx - 350) <= 3, f"Expected X near 350, got {fx}"
        assert abs(fy - 200) <= 3, f"Expected Y near 200, got {fy}"
        assert match["confidence"] >= 0.68

    mem.close()


# ============================================================================
# Test b: Large Icon / Button Recognition Test
# ============================================================================

def test_large_button_adaptive_bounds_and_scaled_relocation(tmp_path):
    """Create a large 220x90 custom button, learn it with adaptive bounding-box detection
    (asserting stored width > 150 and height > 60, NOT hardcoded 44x44), relocate and resize
    it by 1.3x, and assert _match_learned_visual_template locates it accurately!
    """
    mem = MemoryStore(db_path=str(tmp_path / "mem.db"), chroma_dir=str(tmp_path / "chroma"))
    vision = VisionManager(memory_store=mem)
    gui = GuiAutomationLogistics(memory_store=mem)
    gui.vision = vision

    # 1. Create desktop with 220x90 custom button centered at (600, 400)
    screen1 = np.full((1080, 1920, 3), (30, 32, 36), dtype=np.uint8)
    draw_large_custom_button(screen1, cx=600, cy=400, w=220, h=90)
    pil1 = Image.fromarray(cv2.cvtColor(screen1, cv2.COLOR_BGR2RGB))

    with patch.object(vision, "capture_screen_raw", return_value=pil1), \
         patch.object(vision, "_grab_raw_image", return_value=pil1), \
         patch("pyautogui.moveTo"):

        report = gui.screen_pixel_navigation(
            action="learn_element",
            target_label_or_tag="launch battle button",
            x=600,
            y=400,
        )
        assert "launch battle button" in report.lower()

    entry = mem.get_visual_ui_memory("launch battle button")
    assert entry is not None
    # Assert adaptive bounding box detected the large button (>150x60, NOT hardcoded 44x44!)
    assert entry["width"] > 150, f"Expected width > 150, got {entry['width']}"
    assert entry["height"] > 60, f"Expected height > 60, got {entry['height']}"
    assert entry.get("orb_features"), "Expected ORB keypoint features to be stored"
    assert entry.get("hsv_hist"), "Expected HSV color histogram to be stored"

    # 2. Relocate button to (1150, 680) and resize by 1.3x (286x117)
    screen2 = np.full((1080, 1920, 3), (30, 32, 36), dtype=np.uint8)
    scaled_w = int(round(220 * 1.3))  # 286
    scaled_h = int(round(90 * 1.3))   # 117
    draw_large_custom_button(screen2, cx=1150, cy=680, w=scaled_w, h=scaled_h)
    pil2 = Image.fromarray(cv2.cvtColor(screen2, cv2.COLOR_BGR2RGB))

    with patch.object(vision, "capture_screen_raw", return_value=pil2), \
         patch.object(vision, "_grab_raw_image", return_value=pil2):

        match = vision._match_learned_visual_template("launch battle button")
        assert match is not None and match["found"] is True
        fx, fy = match["center"]
        assert abs(fx - 1150) <= 5, f"Expected X near 1150, got {fx}"
        assert abs(fy - 680) <= 5, f"Expected Y near 680, got {fy}"

    mem.close()


# ============================================================================
# Test c: First-Boot Mic Auto-Unlock Test
# ============================================================================

@pytest.mark.asyncio
async def test_first_boot_mic_auto_unlock_within_4s(tmp_path):
    """Verify _stream_mic_to_alfred unlocks within 4s even if _startup_briefing_completed is never externally set."""
    mem = MemoryStore(db_path=str(tmp_path / "mem.db"), chroma_dir=str(tmp_path / "chroma"))
    audio = AudioManager()
    vision = VisionManager(memory_store=mem)
    core = AlfredLiveCore(tools_list=[], audio_manager=audio, vision_manager=vision, memory_store=mem)

    core.is_running = True
    core._startup_briefing_completed.clear()
    core.set_status("listening")

    mock_session = AsyncMock()
    mock_session.send_realtime_input = AsyncMock()

    stream_task = asyncio.create_task(core._stream_mic_to_alfred(mock_session))

    # Wait up to 4.3s without ever calling _startup_briefing_completed.set() externally
    t0 = time.monotonic()
    while not core._startup_briefing_completed.is_set() and (time.monotonic() - t0) < 4.5:
        await asyncio.sleep(0.1)

    elapsed = time.monotonic() - t0
    assert core._startup_briefing_completed.is_set() is True, "Mic gate failed to auto-unlock within 4s!"
    assert elapsed <= 4.4, f"Expected auto-unlock within ~4.0s, took {elapsed:.2f}s"

    # Now push a speech chunk and verify it streams immediately to Gemini Live
    audio.visual_mic_level = 0.40
    audio.mic_queue.put_nowait(b"\x80\x00" * 256)
    await asyncio.sleep(0.05)

    assert mock_session.send_realtime_input.await_count >= 1

    stream_task.cancel()
    try:
        await stream_task
    except asyncio.CancelledError:
        pass
    mem.close()


# ============================================================================
# Test d: Mid-Speech Voice 'Stop' & Spoken Reply Test
# ============================================================================

@pytest.mark.asyncio
async def test_mid_speech_voice_stop_and_spoken_reply(tmp_path):
    """Verify that saying 'stop' while status == 'speaking' immediately flushes playback
    and triggers the spoken stop confirmation.
    """
    mem = MemoryStore(db_path=str(tmp_path / "mem.db"), chroma_dir=str(tmp_path / "chroma"))
    audio = AudioManager()
    vision = VisionManager(memory_store=mem)
    core = AlfredLiveCore(tools_list=[], audio_manager=audio, vision_manager=vision, memory_store=mem)

    mock_session = AsyncMock()
    mock_session.send = AsyncMock()
    core._session = mock_session
    core.is_running = True

    # Simulate ALFRED actively speaking with queued audio
    core.set_status("speaking")
    core._model_turn_open = True
    audio.feed_speaker_audio(b"\x40\x00" * 2400)
    assert audio.is_speaker_locked() is True

    # 1. Verify high-RMS barge-in voice chunk during speaking is allowed into mic_queue by AudioManager
    audio.is_running = True
    audio._loop = asyncio.get_running_loop()
    loud_barge_in_chunk = b"\xff\x7f" * 256  # Full-scale speech > barge_in_threshold
    audio._input_callback(loud_barge_in_chunk, 256, None, None)
    await asyncio.sleep(0.02)
    assert not audio.mic_queue.empty(), "Expected loud barge-in voice chunk to bypass speaker lock into mic_queue"

    # 2. Simulate input_audio_transcription arriving with 'stop' while status == 'speaking'
    class MockInputTranscription:
        text = "stop"

    class MockServerContent:
        interrupted = False
        user_turn = None
        input_transcription = MockInputTranscription()
        model_turn = None
        turn_complete = False

    class MockResponse:
        server_content = MockServerContent()
        tool_call = None

    await core.process_server_response(MockResponse(), session=mock_session)
    await asyncio.sleep(0.05)

    # Assert playback was flushed, status transitioned to listening, and spoken stop confirmation triggered
    assert core.status == "listening"
    assert core._model_turn_open is False
    assert audio.stop_confirmation_played_count >= 1 or mock_session.send.await_count >= 1
    assert len(audio.cached_stop_pcm) > 0

    # Verify the Gemini Live spoken stop directive was dispatched
    sent_inputs = [call.kwargs.get("input", "") for call in mock_session.send.call_args_list]
    assert any("Stopped, Director Qadir" in str(inp) for inp in sent_inputs)

    mem.close()
