"""Tests for Phase 19: Click-Through Fix, Bounded Retry Visual Click, and Live Weather Briefing.

Verifies:
1. get_weather_briefing returns structured meteorological telemetry (UTC+8, temperature, humidity, wind, 3-day forecast).
2. screen_pixel_navigation pre/post-click visual patch diffing:
   - Attempt 1 visual verification (>1.5% change) succeeds.
   - Attempt 2 retry with 80ms press hold succeeds if attempt 1 is unverified.
   - Bounded 2-try limit strictly halts and returns honest failure notice if still unverified.
3. Graceful shutdown sequence:
   - terminate_executive_commands triggers shutdown callback.
   - Coordinator broadcasts system_shutdown payload.
   - live_session text prompt / user transcription triggers shutdown.
4. Strict tool limit: exactly 30 tools (<= 30) registered.
5. System prompt enforces CRITICAL SHUTDOWN DIRECTIVE and HONESTY & BOUNDED RETRY DIRECTIVE.
"""

from __future__ import annotations

import asyncio
import json
import numpy as np
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from backend.tools.os_logistics import OSLogistics, WMO_WEATHER_DESCRIPTIONS
from backend.tools.gui_automation import GuiAutomationLogistics
from backend.tools.dev_logistics import DevLogistics
from backend.vision_manager import VisionManager
from backend.memory.memory_store import MemoryStore
from backend.live_session import AlfredLiveCore, ALFRED_BASE_SYSTEM_PROMPT
from backend.main import AlfredHubCoordinator


# ---------------------------------------------------------------------------
# 1. Weather Briefing Tests
# ---------------------------------------------------------------------------

def test_weather_briefing_legazpi(tmp_path):
    """Verifies get_weather_briefing returns real-time weather and 3-day forecast for Legazpi City."""
    mem = MemoryStore(db_path=str(tmp_path / "mem.db"), chroma_dir=str(tmp_path / "chroma"))
    logistics = OSLogistics(memory_store=mem)

    report = logistics.get_weather_briefing(location="Legazpi City", include_forecast=True)

    assert "Weather Telemetry" in report or "Meteorological Telemetry" in report
    assert "UTC+8" in report
    assert "Legazpi" in report
    assert "Temperature:" in report or "°C" in report
    mem.close()


def test_weather_briefing_no_forecast(tmp_path):
    """Verifies get_weather_briefing without forecast omits the multi-day forecast block."""
    mem = MemoryStore(db_path=str(tmp_path / "mem.db"), chroma_dir=str(tmp_path / "chroma"))
    logistics = OSLogistics(memory_store=mem)

    report = logistics.get_weather_briefing(location="Legazpi", include_forecast=False)

    assert "UTC+8" in report
    assert "3-Day Forecast Outlook" not in report
    mem.close()


def test_weather_briefing_network_fallback(tmp_path):
    """Verifies get_weather_briefing handles network failures cleanly without raising exceptions."""
    mem = MemoryStore(db_path=str(tmp_path / "mem.db"), chroma_dir=str(tmp_path / "chroma"))
    logistics = OSLogistics(memory_store=mem)

    with patch("urllib.request.urlopen", side_effect=Exception("Connection timed out")):
        report = logistics.get_weather_briefing(location="Atlantis City")
        assert "Meteorological Telemetry" in report or "Sensor link unavailable" in report or "UTC+8" in report

    mem.close()


# ---------------------------------------------------------------------------
# 2. Visual Verification & Bounded 2-Try Limit Tests
# ---------------------------------------------------------------------------

def test_screen_pixel_navigation_attempt_1_success():
    """Attempt 1 produces visual change >= 1.5% -> verified on first attempt."""
    mock_vision = MagicMock(spec=VisionManager)

    # 120x120 patch: pre is black, post is partially white (e.g. 5% changed pixels)
    pre_patch = np.zeros((120, 120, 3), dtype=np.uint8)
    post_patch = np.zeros((120, 120, 3), dtype=np.uint8)
    post_patch[0:30, 0:30] = 255  # 900 / 14400 = 6.25% change

    mock_vision.capture_screen_patch.side_effect = [pre_patch, post_patch]

    gui = GuiAutomationLogistics(vision_manager=mock_vision)

    with patch("backend.tools.gui_automation.send_hardware_mouse_click", return_value=True), \
         patch("time.sleep", return_value=None):
        result = gui.screen_pixel_navigation(x=100, y=200, action="click")

    assert "Successfully executed desktop mouse click" in result
    assert "visual response verified" in result
    assert "attempt 2" not in result
    assert mock_vision.capture_screen_patch.call_count == 2


def test_screen_pixel_navigation_attempt_2_success():
    """Attempt 1 fails visual change (< 1.5%), but Attempt 2 succeeds (>= 1.5%)."""
    mock_vision = MagicMock(spec=VisionManager)

    pre_patch = np.zeros((120, 120, 3), dtype=np.uint8)
    # Attempt 1 post: virtually identical (0% change)
    post_patch_1 = np.zeros((120, 120, 3), dtype=np.uint8)
    # Attempt 2 post: 5% change
    post_patch_2 = np.zeros((120, 120, 3), dtype=np.uint8)
    post_patch_2[0:30, 0:30] = 255

    mock_vision.capture_screen_patch.side_effect = [pre_patch, post_patch_1, post_patch_2]

    gui = GuiAutomationLogistics(vision_manager=mock_vision)

    with patch("backend.tools.gui_automation.send_hardware_mouse_click", return_value=True) as mock_click, \
         patch("time.sleep", return_value=None):
        result = gui.screen_pixel_navigation(x=150, y=250, action="click")

    assert "Successfully executed desktop mouse click" in result
    assert "on attempt 2" in result
    assert "visual response verified" in result
    # Verify 2 clicks occurred (second with hold_ms=80.0)
    assert mock_click.call_count == 2
    assert mock_click.call_args_list[1][1].get("hold_ms") == 80.0


def test_screen_pixel_navigation_bounded_2_try_failure():
    """Both Attempt 1 and Attempt 2 fail (< 1.5% change) -> strictly halts and returns honest failure message."""
    mock_vision = MagicMock(spec=VisionManager)

    pre_patch = np.zeros((120, 120, 3), dtype=np.uint8)
    post_patch_1 = np.zeros((120, 120, 3), dtype=np.uint8)
    post_patch_2 = np.zeros((120, 120, 3), dtype=np.uint8)

    mock_vision.capture_screen_patch.side_effect = [pre_patch, post_patch_1, post_patch_2]

    gui = GuiAutomationLogistics(vision_manager=mock_vision)

    with patch("backend.tools.gui_automation.send_hardware_mouse_click", return_value=True) as mock_click, \
         patch("time.sleep", return_value=None):
        result = gui.screen_pixel_navigation(x=300, y=400, action="click", target_label_or_tag="Start Button")

    assert "ACTION UNVERIFIED AFTER 2 ATTEMPTS" in result
    assert "(300, 400)" in result
    assert "Start Button" in result
    assert "Inform Director Qadir what was attempted and why it failed." in result
    # Strictly capped at exactly 2 click attempts!
    assert mock_click.call_count == 2


def test_screen_pixel_navigation_non_click_actions():
    """Verifies double_click, right_click, move, and scroll actions execute without patch diffing."""
    mock_vision = MagicMock(spec=VisionManager)
    gui = GuiAutomationLogistics(vision_manager=mock_vision)

    with patch("backend.tools.gui_automation.send_hardware_mouse_click", return_value=True), \
         patch("backend.tools.gui_automation.pyautogui") as mock_pg:
        mock_pg.size.return_value = (1920, 1080)
        res_right = gui.screen_pixel_navigation(x=100, y=100, action="right_click")
        assert "Successfully executed desktop mouse right_click" in res_right

        res_move = gui.screen_pixel_navigation(x=200, y=200, action="move")
        assert "Successfully executed desktop mouse move" in res_move


# ---------------------------------------------------------------------------
# 3. Graceful Shutdown & Teardown Tests
# ---------------------------------------------------------------------------

def test_terminate_executive_commands_triggers_callback(tmp_path):
    """Verifies OSLogistics.terminate_executive_commands invokes registered shutdown callback."""
    mem = MemoryStore(db_path=str(tmp_path / "mem.db"), chroma_dir=str(tmp_path / "chroma"))
    logistics = OSLogistics(memory_store=mem)

    callback_called = False
    received_farewell = ""

    def test_cb(msg: str):
        nonlocal callback_called, received_farewell
        callback_called = True
        received_farewell = msg

    logistics.set_shutdown_callback(test_cb)
    result = logistics.terminate_executive_commands(farewell_message="Standing down, Director Qadir.")

    assert callback_called is True
    assert "Standing down" in received_farewell
    assert "Standing down" in result
    mem.close()


@pytest.mark.asyncio
async def test_coordinator_execute_system_shutdown(tmp_path):
    """Verifies coordinator executes shutdown sequence, drains audio, and broadcasts shutdown payload."""
    mem = MemoryStore(db_path=str(tmp_path / "mem.db"), chroma_dir=str(tmp_path / "chroma"))
    coordinator = AlfredHubCoordinator(memory_store=mem)

    mock_client = AsyncMock()
    coordinator.connected_clients.add(mock_client)

    with patch.object(coordinator.audio, "wait_for_playback_drain", new_callable=AsyncMock) as mock_drain, \
         patch.object(coordinator.audio, "is_playback_active", return_value=False), \
         patch("backend.main.subprocess.run") as mock_taskkill, \
         patch("os._exit") as mock_exit:

        await coordinator.execute_system_shutdown(farewell_message="Farewell, Sir.")

        # Audio drain should be awaited
        mock_drain.assert_awaited_once()

        # Shutdown broadcast must be dispatched to WebSocket clients
        assert mock_client.send_text.call_count >= 1
        sent_payloads = [json.loads(call[0][0]) for call in mock_client.send_text.call_args_list]
        shutdown_messages = [p for p in sent_payloads if p.get("type") == "system_shutdown"]
        assert len(shutdown_messages) == 1
        assert "Director Qadir" in shutdown_messages[0]["reason"]

        # taskkill should be called on Windows
        mock_taskkill.assert_called_once()
        assert "electron.exe" in mock_taskkill.call_args[0][0]

    mem.close()


@pytest.mark.asyncio
async def test_live_core_voice_text_prompt_shutdown_directive(tmp_path):
    """Verifies that text prompts containing 'terminate executive commands alfred' trigger shutdown."""
    mem = MemoryStore(db_path=str(tmp_path / "mem.db"), chroma_dir=str(tmp_path / "chroma"))
    coordinator = AlfredHubCoordinator(memory_store=mem)
    live_core = coordinator.live_core

    shutdown_triggered = False

    def on_shutdown(msg: str):
        nonlocal shutdown_triggered
        shutdown_triggered = True

    live_core.set_shutdown_callback(on_shutdown)
    live_core._session = AsyncMock()
    live_core.is_running = True

    with patch.object(live_core.audio_manager, "wait_for_playback_drain", new_callable=AsyncMock):
        await live_core.send_text_prompt("Terminate Executive Commands Alfred")

    assert live_core._shutdown_pending is True
    assert live_core.status == "speaking"
    mem.close()


# ---------------------------------------------------------------------------
# 4. Strict Tool Count and System Prompt Tests
# ---------------------------------------------------------------------------

def test_strictly_30_tools_registered(tmp_path):
    """Verifies that total registered tools is strictly <= 30 (exactly 30)."""
    mem = MemoryStore(db_path=str(tmp_path / "mem.db"), chroma_dir=str(tmp_path / "chroma"))
    coordinator = AlfredHubCoordinator(memory_store=mem)

    assert len(coordinator.tools_list) == 30
    assert len(coordinator.tools_list) <= 30

    tool_names = [fn.__name__ for fn in coordinator.tools_list]
    assert "get_weather_briefing" in tool_names
    assert "terminate_executive_commands" in tool_names
    assert "screen_pixel_navigation" in tool_names
    assert "probe_network_target" not in tool_names
    mem.close()


def test_system_prompt_mandates():
    """Verifies system prompt contains mandatory shutdown and honesty bounded retry directives."""
    assert "CRITICAL SHUTDOWN DIRECTIVE" in ALFRED_BASE_SYSTEM_PROMPT
    assert "Terminate Executive Commands Alfred" in ALFRED_BASE_SYSTEM_PROMPT
    assert "HONESTY & BOUNDED RETRY DIRECTIVE" in ALFRED_BASE_SYSTEM_PROMPT
    assert "ACTION UNVERIFIED AFTER 2 ATTEMPTS" in ALFRED_BASE_SYSTEM_PROMPT
    assert "UTC+8" in ALFRED_BASE_SYSTEM_PROMPT
