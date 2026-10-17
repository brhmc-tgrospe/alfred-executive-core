"""Unit tests for Phase 20:
1. Strict Passphrase Verification Gate on Shutdown (stopping vs terminating)
2. Instant Task Stop & Abort Handler (abort_current_operations)
3. Autonomous Full-Screen Visual Search (autonomous_screen_search)
4. Elimination of Lazy Cursor Clicking in screen_pixel_navigation
5. Set-of-Marks Full-Screen Annotated Grid Streaming for inspect_active_screen
"""

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch
import numpy as np
import pytest

from backend.audio_manager import AudioManager
from backend.live_session import (
    AlfredLiveCore,
    is_shutdown_authorized,
    is_stop_command,
    ALFRED_BASE_SYSTEM_PROMPT,
)
from backend.main import AlfredHubCoordinator
from backend.memory.memory_store import MemoryStore
from backend.tools.gui_automation import GuiAutomationLogistics
from backend.tools.os_logistics import OSLogistics
from backend.vision_manager import VisionManager


# ============================================================================
# 1. Passphrase Gate & Stop Detection Unit Tests
# ============================================================================

def test_is_shutdown_authorized():
    """Verify is_shutdown_authorized only accepts explicit executive shutdown passphrases."""
    assert is_shutdown_authorized("Terminate Executive Commands Alfred") is True
    assert is_shutdown_authorized("terminate executive commands alfred") is True
    assert is_shutdown_authorized("please terminate executive commands alfred immediately") is True
    assert is_shutdown_authorized("shut down alfred") is True
    assert is_shutdown_authorized("close alfred now") is True

    # Stop words MUST NEVER authorize shutdown
    assert is_shutdown_authorized("stop") is False
    assert is_shutdown_authorized("Stop!") is False
    assert is_shutdown_authorized("stop what you are doing") is False
    assert is_shutdown_authorized("cancel that") is False
    assert is_shutdown_authorized("abort mission") is False
    assert is_shutdown_authorized("halt") is False
    assert is_shutdown_authorized("pause") is False
    assert is_shutdown_authorized("enough") is False
    assert is_shutdown_authorized("wait") is False
    assert is_shutdown_authorized("") is False


def test_is_stop_command():
    """Verify is_stop_command accurately detects operational interrupts."""
    assert is_stop_command("stop") is True
    assert is_stop_command("Stop!") is True
    assert is_stop_command("stop what you are doing") is True
    assert is_stop_command("cancel") is True
    assert is_stop_command("cancel that") is True
    assert is_stop_command("abort") is True
    assert is_stop_command("halt") is True
    assert is_stop_command("pause") is True
    assert is_stop_command("enough") is True
    assert is_stop_command("stop that") is True

    # Shutdown passphrases are NOT mere stop commands
    assert is_stop_command("Terminate Executive Commands Alfred") is False
    assert is_stop_command("shut down alfred") is False

    # Regular conversational commands are NOT stop commands
    assert is_stop_command("open chrome") is False
    assert is_stop_command("what is the weather today?") is False


# ============================================================================
# 2. Bug 1: Stop Command Aborts Tasks Without System Termination
# ============================================================================

@pytest.mark.asyncio
async def test_text_prompt_stop_triggers_abort_not_shutdown(tmp_path):
    """Sending 'stop' via text_prompt halts playback and watchdogs, reverting to listening without shutdown."""
    mem = MemoryStore(db_path=str(tmp_path / "mem.db"), chroma_dir=str(tmp_path / "chroma"))
    audio = AudioManager()
    audio.clear_playback = MagicMock()
    coordinator = AlfredHubCoordinator(memory_store=mem, audio_manager=audio)

    shutdown_mock = MagicMock()
    coordinator.schedule_shutdown = shutdown_mock
    coordinator.execute_system_shutdown = AsyncMock()

    # User says "stop"
    await coordinator.handle_hud_message({
        "type": "text_prompt",
        "text": "Stop what you are doing!",
    })

    # Shutdown MUST NOT be triggered
    shutdown_mock.assert_not_called()
    assert coordinator.live_core.status == "listening"
    audio.clear_playback.assert_called()
    assert "Stopped, Director Qadir" in coordinator.current_transcript
    mem.close()


@pytest.mark.asyncio
async def test_passphrase_gate_blocks_terminate_executive_commands_when_user_said_stop(tmp_path):
    """If Gemini calls terminate_executive_commands after user said 'stop', the gate blocks shutdown."""
    mem = MemoryStore(db_path=str(tmp_path / "mem.db"), chroma_dir=str(tmp_path / "chroma"))
    os_log = OSLogistics(memory_store=mem)
    shutdown_hook = MagicMock()
    os_log.set_shutdown_callback(shutdown_hook)

    # User only said "stop"
    os_log.set_last_user_utterance("stop")

    res = os_log.terminate_executive_commands("Terminating now, Director.")
    assert "Shutdown blocked: User requested task stop" in res
    shutdown_hook.assert_not_called()

    # User said full passphrase
    os_log.set_last_user_utterance("Terminate Executive Commands Alfred immediately")
    res_ok = os_log.terminate_executive_commands("Terminating all executive commands now, Director Qadir.")
    assert "Terminating all executive commands now" in res_ok
    shutdown_hook.assert_called_once()

    mem.close()


@pytest.mark.asyncio
async def test_live_session_dispatch_blocks_shutdown_on_stop_utterance():
    """AlfredLiveCore.dispatch_tool_call intercepts unauthorized terminate_executive_commands."""
    audio = AudioManager()
    audio.clear_playback = MagicMock()
    core = AlfredLiveCore(tools_list=[], audio_manager=audio)

    # Simulate user last utterance was "cancel"
    core.last_user_utterance = "cancel that right now"

    mock_session = AsyncMock()
    mock_fc = MagicMock()
    mock_fc.name = "terminate_executive_commands"
    mock_fc.id = "call-1"
    mock_fc.args = {"farewell_message": "Standing down, Sir."}

    result = await core.dispatch_tool_call(mock_session, mock_fc)

    assert "Shutdown blocked: User requested task stop" in str(result)
    assert core._shutdown_pending is False
    assert core.status == "listening"
    audio.clear_playback.assert_called()


# ============================================================================
# 3. Bug 2: Autonomous Full-Screen Visual Search (No Lazy Cursor Default)
# ============================================================================

def test_screen_pixel_navigation_rejects_lazy_cursor():
    """screen_pixel_navigation(-1, -1) without 'cursor' tag MUST NOT lazily click mouse position."""
    gui = GuiAutomationLogistics()
    with patch("backend.tools.gui_automation.get_live_cursor_coords", return_value=(555, 444)):
        # -1, -1 with no target tag must return an error
        res = gui.screen_pixel_navigation(x=-1, y=-1, action="click")
        assert "Error: Must provide either screen coordinates (x, y)" in res or "Could not resolve" in res

        # Explicit target_label_or_tag='cursor' is allowed to click at cursor
        with patch.object(gui.vision, "capture_screen_patch") as mock_patch, \
             patch("backend.tools.gui_automation.send_hardware_mouse_click") as mock_click, \
             patch("backend.tools.gui_automation.pyautogui") as mock_pg:
            mock_pg.size.return_value = (1920, 1080)
            p1 = np.zeros((120, 120, 3), dtype=np.uint8)
            p2 = np.zeros((120, 120, 3), dtype=np.uint8)
            p2[0:30, 0:30] = 255
            mock_patch.side_effect = [p1, p2]

            res_cursor = gui.screen_pixel_navigation(x=-1, y=-1, action="click", target_label_or_tag="cursor")
            assert "Successfully executed desktop mouse click at coordinates (555, 444)" in res_cursor
            mock_click.assert_called_with(555, 444, button="left", hold_ms=0.0)


def test_autonomous_screen_search_resolves_spatial_and_som_tags():
    """VisionManager.autonomous_screen_search discovers tags, Win32 child elements, and spatial regions."""
    vm = VisionManager()

    # Pre-populate dummy SoM cache
    VisionManager._som_cache = {
        "#1": {"center": (100, 100), "rect": (80, 80, 40, 40), "bbox": (80, 80, 40, 40), "type": "UI_ELEMENT", "label": "File"},
        "#2": {"center": (1850, 20), "rect": (1830, 10, 40, 20), "bbox": (1830, 10, 40, 20), "type": "UI_ELEMENT", "label": "Close"},
        "#3": {"center": (960, 1050), "rect": (940, 1040, 40, 20), "bbox": (940, 1040, 40, 20), "type": "UI_ELEMENT", "label": "Start"},
    }

    # 1. Search by tag #2
    found_tag = vm.autonomous_screen_search("#2")
    assert found_tag["found"] is True
    assert found_tag["center"] == (1850, 20)

    # 2. Search by label "file"
    found_label = vm.autonomous_screen_search("file")
    assert found_label["found"] is True
    assert found_label["center"] == (100, 100)

    # 3. Search by spatial region "top right" or "close button"
    found_spatial = vm.autonomous_screen_search("close button")
    assert found_spatial["found"] is True
    assert found_spatial["center"] == (1850, 20)

    # 4. Search by spatial region "taskbar"
    found_taskbar = vm.autonomous_screen_search("taskbar")
    assert found_taskbar["found"] is True
    assert found_taskbar["center"] == (960, 1050)


def test_screen_pixel_navigation_autonomously_searches_screen():
    """screen_pixel_navigation with target_label_or_tag autonomously finds coordinates on screen."""
    gui = GuiAutomationLogistics()

    VisionManager._som_cache = {
        "#7": {"center": (640, 480), "rect": (600, 460, 80, 40), "bbox": (600, 460, 80, 40), "type": "UI_ELEMENT", "label": "Submit"},
    }

    with patch.object(gui.vision, "capture_screen_patch") as mock_patch, \
         patch("backend.tools.gui_automation.send_hardware_mouse_click") as mock_click, \
         patch("backend.tools.gui_automation.pyautogui") as mock_pg:
        mock_pg.size.return_value = (1920, 1080)
        p1 = np.zeros((120, 120, 3), dtype=np.uint8)
        p2 = np.zeros((120, 120, 3), dtype=np.uint8)
        p2[0:30, 0:30] = 255
        mock_patch.side_effect = [p1, p2]

        res = gui.screen_pixel_navigation(action="click", target_label_or_tag="Submit")
        assert "Successfully executed desktop mouse click at coordinates (640, 480)" in res
        mock_click.assert_called_with(640, 480, button="left", hold_ms=0.0)


# ============================================================================
# 4. Invariants & System Prompt Directives
# ============================================================================

def test_strictly_30_tools_registered_phase20(tmp_path):
    """Verify tool declarations stay strictly <= 30 on AlfredHubCoordinator."""
    mem = MemoryStore(db_path=str(tmp_path / "mem.db"), chroma_dir=str(tmp_path / "chroma"))
    coordinator = AlfredHubCoordinator(memory_store=mem)
    assert len(coordinator.tools_list) == 30
    assert len(coordinator.tools_list) <= 30
    tool_names = [fn.__name__ for fn in coordinator.tools_list]
    assert "terminate_executive_commands" in tool_names
    assert "inspect_active_screen" in tool_names
    assert "screen_pixel_navigation" in tool_names
    assert "get_weather_briefing" in tool_names
    mem.close()


def test_system_prompt_phase20_mandates():
    """Verify system prompt contains mandatory Stop vs Terminate and Autonomous Screen Search rules."""
    assert "STRICT STOP VS. TERMINATE RULE" in ALFRED_BASE_SYSTEM_PROMPT
    assert "AUTONOMOUS SCREEN SEARCH RULE" in ALFRED_BASE_SYSTEM_PROMPT
    assert "CRITICAL SHUTDOWN DIRECTIVE" in ALFRED_BASE_SYSTEM_PROMPT
