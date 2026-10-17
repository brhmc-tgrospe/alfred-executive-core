"""Unit tests for Phase 18: Visual-Spatial Grounding, Predictive Kinematics,
Software Interface Research, Playwright Resiliency, and Graceful Voice Shutdown.
"""

import asyncio
import json
import numpy as np
import pytest
from PIL import Image
from unittest.mock import MagicMock, patch, AsyncMock

from backend.vision_manager import VisionManager
from backend.tools.gui_automation import GuiAutomationLogistics
from backend.tools.game_interaction import GameInteractionLogistics
from backend.tools.dev_logistics import DevLogistics
from backend.tools.browser_automation import BrowserAutomationLogistics
from backend.tools.os_logistics import OSLogistics
from backend.audio_manager import AudioManager
from backend.main import AlfredHubCoordinator
from backend.memory.memory_store import MemoryStore


# ============================================================================
# Constraint 1, 3 & 4: SoM Grounding, Occlusion Bypass, and Tag Navigation
# ============================================================================

def test_som_detection_and_tag_caching():
    """Verify VisionManager detects UI contours, attaches numbered tags, and caches them."""
    vm = VisionManager()

    # Generate synthetic image with two distinct buttons/cards
    h, w = 600, 800
    img = np.zeros((h, w, 3), dtype=np.uint8)
    # Button 1: White rectangle at (100, 100) -> (250, 160)
    img[100:160, 100:250] = 255
    # Button 2: White rectangle at (300, 400) -> (360, 550)
    img[300:360, 400:550] = 255
    pil_img = Image.fromarray(img)

    with patch.object(vm, "capture_screen_raw", return_value=pil_img):
        jpeg_bytes, som_map = vm.detect_ui_elements_and_annotate_grid(window_title="active")

        assert isinstance(jpeg_bytes, bytes)
        assert len(jpeg_bytes) > 0
        assert isinstance(som_map, dict)
        assert len(som_map) >= 2

        # Check tag formatting
        assert "#1" in som_map
        tag1 = som_map["#1"]
        assert "center" in tag1
        assert "bbox" in tag1
        assert "type" in tag1

        # Check cache
        cache = vm.get_som_cache()
        assert cache == som_map


def test_screen_pixel_navigation_with_som_tag():
    """Verify screen_pixel_navigation resolves target coordinates from SoM cache without numeric X,Y."""
    gui = GuiAutomationLogistics()

    # Pre-populate cache
    VisionManager._som_cache = {
        "#1": {"center": (175, 130), "bbox": (100, 100, 150, 60), "type": "UI_ELEMENT"},
        "#2": {"center": (475, 330), "bbox": (400, 300, 150, 60), "type": "UI_ELEMENT"},
    }

    with patch("backend.tools.gui_automation.pyautogui") as mock_pg:
        mock_pg.size.return_value = (1920, 1080)
        # Click by tag "#2"
        res = gui.screen_pixel_navigation(action="click", target_label_or_tag="#2")
        assert "Successfully executed desktop mouse click at coordinates (475, 330)" in res
        mock_pg.click.assert_called_once_with(475, 330)

        # Invalid tag fallback
        res_invalid = gui.screen_pixel_navigation(action="click", target_label_or_tag="#99")
        assert "Could not resolve Set-of-Marks tag" in res_invalid


def test_resolve_window_occlusion_and_manage_desktop_window():
    """Verify Z-order window occlusion detection and bring-to-foreground restoration."""
    gui = GuiAutomationLogistics()

    mock_target_hwnd = 1001
    mock_occluding_hwnd = 1002

    def fake_enum_windows(callback, extra):
        # Z-order top to bottom: 1002 (occluding) is above 1001 (target)
        callback(mock_occluding_hwnd, None)
        callback(mock_target_hwnd, None)

    with patch("backend.tools.gui_automation.win32gui") as mock_w32:
        mock_w32.EnumWindows.side_effect = fake_enum_windows
        mock_w32.IsWindowVisible.return_value = True
        mock_w32.IsIconic.return_value = False
        mock_w32.GetWindowText.side_effect = lambda hwnd: "Target App - Executive" if hwnd == mock_target_hwnd else "Overlapping Window"
        # Overlapping bounding boxes
        mock_w32.GetWindowRect.side_effect = lambda hwnd: (100, 100, 800, 600) if hwnd == mock_target_hwnd else (200, 200, 600, 500)

        report = gui.resolve_window_occlusion("Target App")
        assert report["target_found"] is True
        assert report["occluded"] is True
        assert "Overlapping Window" in report["occluding_windows"]
        assert report["foreground_action"] == "Brought target window to foreground"
        mock_w32.SetForegroundWindow.assert_called_once_with(mock_target_hwnd)

        # Also verify manage_desktop_window action="resolve_occlusion"
        res = gui.manage_desktop_window(action="resolve_occlusion", window_title="Target App")
        assert "Occlusion Assessment for 'Target App" in res
        assert "Target Found: True" in res


# ============================================================================
# Constraint 2: Kinematic Motion Tracking & Predictive Intercept Calculation
# ============================================================================

def test_kinematic_motion_tracking_and_predictive_aim():
    """Verify 2-frame rapid burst measures velocity (vx, vy) and computes lead target intercept."""
    game = GameInteractionLogistics()

    # Generate frame 1: moving target at (200, 200)
    f1 = np.zeros((480, 640, 3), dtype=np.uint8)
    f1[190:210, 190:210] = 255

    # Generate frame 2: target moved right and down to (235, 235) after dt=0.035s
    f2 = np.zeros((480, 640, 3), dtype=np.uint8)
    f2[225:245, 225:245] = 255

    meta = {"width": 640, "height": 480, "rect": {"left": 0, "top": 0, "width": 640, "height": 480}}

    with patch.object(game, "_capture_window_bgr", side_effect=[(f1, meta), (f2, meta)]):
        obs_json = game.observe_game_state(window_title="active", detect_hud_bars=False)
        obs = json.loads(obs_json)

        assert "tracked_targets" in obs
        assert len(obs["tracked_targets"]) > 0

        target = obs["tracked_targets"][0]
        assert "velocity_px_s" in target
        assert "speed_px_s" in target
        assert "predictive_intercept" in target
        assert target["speed_px_s"] > 0

        # Verify evaluate_tactical_game_policy uses predictive intercept
        policy_res = game.evaluate_tactical_game_policy(game_genre="action_rpg")
        assert "Predictive intercept" in policy_res or "Kinetic lead engaged" in policy_res


# ============================================================================
# Constraint 5: Software Interface Research & Memory Management
# ============================================================================

def test_research_software_interface_and_docs_cached_and_scrape():
    """Verify DevLogistics provides fast shortcuts for known software and scrapes docs."""
    dev = DevLogistics()

    # 1. Built-in dictionary match for Word / Excel / VS Code
    word_res = dev.research_software_interface_and_docs(
        application_name="Microsoft Word",
        feature_or_icon_query="save as",
    )
    assert "F12" in word_res or "Ctrl+S" in word_res

    vscode_res = dev.research_software_interface_and_docs(
        application_name="Visual Studio Code",
        feature_or_icon_query="command palette",
    )
    assert "Ctrl+Shift+P" in vscode_res

    # 2. Live documentation query fallback with mock httpx
    mock_html = """
    <html>
      <head><title>Blender Hotkeys Manual</title></head>
      <body>
        <main>
          <h1>Blender Extrude Tool</h1>
          <p>Press E on your keyboard to extrude selected mesh faces or vertices along normals.</p>
        </main>
      </body>
    </html>
    """
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.text = mock_html

    with patch("backend.tools.dev_logistics.httpx.get", return_value=mock_resp):
        blender_res = dev.research_software_interface_and_docs(
            application_name="Blender",
            feature_or_icon_query="extrude mesh",
        )
        assert "Press E on your keyboard to extrude" in blender_res


def test_manage_semantic_memory(tmp_path):
    """Verify manage_semantic_memory consolidates remember and recall into 1 lean tool."""
    db_file = str(tmp_path / "mem.db")
    chroma_dir = str(tmp_path / "chroma")
    mem = MemoryStore(db_path=db_file, chroma_dir=chroma_dir)
    os_log = OSLogistics(memory_store=mem)

    # Remember
    store_res = os_log.manage_semantic_memory(
        action="remember",
        text_or_query="Director Qadir prefers dark theme across all development IDEs",
        category="preference",
    )
    assert "Committed to executive memory" in store_res or "preference" in store_res

    # Recall
    recall_res = os_log.manage_semantic_memory(
        action="recall",
        text_or_query="dark theme preference",
    )
    assert "Director Qadir" in recall_res
    assert "dark theme" in recall_res

    mem.close()


# ============================================================================
# Constraint 6: Dynamic JS UI, Popups & Portals in Browser Automation
# ============================================================================

@pytest.mark.asyncio
async def test_browser_automation_dialog_auto_accept_and_click_fallback():
    """Verify dialog auto-accept and click fallback chain in Playwright wrapper."""
    browser_log = BrowserAutomationLogistics()

    mock_page = AsyncMock()
    mock_page.url = "https://executive-internal.test"
    mock_page.title = AsyncMock(return_value="Executive Portal")

    # Mock dialog event registration
    mock_page.on = MagicMock()

    # Mock click fallback: click raises, dispatch_event succeeds
    mock_element = AsyncMock()
    mock_element.click.side_effect = Exception("Element is intercepted by modal overlay")
    mock_element.dispatch_event = AsyncMock()

    mock_locator = AsyncMock()
    mock_locator.count = AsyncMock(return_value=1)
    mock_locator.first = mock_element
    mock_page.locator = MagicMock(return_value=mock_locator)

    with patch.object(browser_log, "_ensure_browser", return_value=mock_page):
        # Test clicking element with fallback chain
        res = await browser_log.browser_interact_dom_element(
            action="click",
            target_selector_or_text="button#confirm-action",
        )
        assert "Successfully performed 'click'" in res
        mock_element.dispatch_event.assert_called_once_with("click", timeout=3000)


# ============================================================================
# Graceful Voice Drain & System Shutdown Protocol
# ============================================================================

@pytest.mark.asyncio
async def test_terminate_executive_commands_voice_drain_and_shutdown():
    """Verify terminate_executive_commands drains audio, broadcasts system_shutdown, and halts."""
    audio = AudioManager()
    mem = MemoryStore()
    os_log = OSLogistics(memory_store=mem)

    # Create coordinator with mocked audio and shutdown hooks
    coordinator = AlfredHubCoordinator(
        memory_store=mem,
        audio_manager=audio,
    )

    shutdown_called = False
    shutdown_farewell_msg = ""

    def test_shutdown_hook(msg: str):
        nonlocal shutdown_called, shutdown_farewell_msg
        shutdown_called = True
        shutdown_farewell_msg = msg

    coordinator.schedule_shutdown = test_shutdown_hook
    os_log.set_shutdown_callback(test_shutdown_hook)
    coordinator.live_core.set_shutdown_callback(test_shutdown_hook)

    # 1. Test direct invocation of terminate_executive_commands tool
    res = os_log.terminate_executive_commands("Terminating all executive commands now, Director Qadir.")
    assert "Terminating all executive commands" in res
    assert shutdown_called is True
    assert "Director Qadir" in shutdown_farewell_msg

    # 2. Test live_core dispatch_tool_call with terminate_executive_commands
    mock_fc = MagicMock()
    mock_fc.name = "terminate_executive_commands"
    mock_fc.id = "shutdown-call-1"
    mock_fc.args = {"farewell_message": "Standing down, Director Qadir."}

    mock_session = AsyncMock()
    shutdown_called = False
    await coordinator.live_core.dispatch_tool_call(mock_session, mock_fc)
    assert coordinator.live_core._shutdown_pending is True

    # Simulate speech drain completion
    with patch.object(audio, "wait_for_playback_drain", new_callable=AsyncMock) as mock_drain:
        await coordinator.live_core._wait_drain_and_transition()
        mock_drain.assert_called_once()
        assert shutdown_called is True
        assert "Standing down, Director Qadir." in shutdown_farewell_msg

    # 3. Test text directive phrase interception
    shutdown_called = False
    await coordinator.handle_hud_message({
        "type": "text_prompt",
        "text": "Terminate Executive Commands Alfred immediately",
    })
    assert shutdown_called is True

    mem.close()
