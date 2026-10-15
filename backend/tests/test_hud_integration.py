"""Integration tests validating contract alignment between Python Coordinator and Electron HUD."""

import json
from unittest.mock import MagicMock
import pytest
from backend.main import AlfredHubCoordinator
from backend.audio_manager import AudioManager


@pytest.mark.asyncio
async def test_hud_contract_schema_alignment():
    """Verify that backend telemetry packets match hud/src/types.ts schema."""
    hub = AlfredHubCoordinator(port=8765)
    payload = hub.get_state_payload()

    # Required fields in AlfredStatePacket
    assert payload["type"] == "state"
    assert payload["status"] in ["idle", "listening", "thinking", "speaking"]
    assert isinstance(payload["rms_volume"], (int, float))
    assert isinstance(payload["cpu"], (int, float))
    assert isinstance(payload["ram"], (int, float))
    assert isinstance(payload["transcript"], str)
    assert payload["active_tool"] is None or isinstance(payload["active_tool"], str)
    assert payload["pending_approval"] is None or isinstance(payload["pending_approval"], dict)


@pytest.mark.asyncio
async def test_hud_pending_approval_contract():
    """Verify pending_approval payload structure sent to HUD."""
    mock_audio = MagicMock(spec=AudioManager)
    mock_audio.current_mic_rms = 0.42
    mock_audio.is_push_to_talk_pressed = False

    hub = AlfredHubCoordinator(port=8765, audio_manager=mock_audio)

    # Simulate triggering an approval request
    approval_packet = {
        "id": "req-9999",
        "action": "execute_terminal_command",
        "command": "rm -rf /critical/path",
        "risk_level": "HIGH",
    }
    await hub.handle_pending_approval(approval_packet)

    assert hub.pending_approval == approval_packet
    state = hub.get_state_payload()
    assert state["pending_approval"]["id"] == "req-9999"
    assert state["pending_approval"]["risk_level"] == "HIGH"
    assert state["pending_approval"]["command"] == "rm -rf /critical/path"

    # Simulate HUD Approval Response (Enter key / Authorize)
    response_msg = {
        "type": "approval_response",
        "id": "req-9999",
        "approved": True,
    }
    await hub.handle_hud_message(response_msg)
    assert hub.pending_approval is None


@pytest.mark.asyncio
async def test_hud_ptt_event_handling():
    """Verify PTT messages from globalShortcut / HUD update AudioManager state."""
    mock_audio = MagicMock(spec=AudioManager)
    hub = AlfredHubCoordinator(port=8765, audio_manager=mock_audio)

    # PTT Down
    await hub.handle_hud_message({"type": "ptt_event", "state": "down"})
    mock_audio.set_push_to_talk.assert_called_with(True)

    # PTT Up
    await hub.handle_hud_message({"type": "ptt_event", "state": "up"})
    mock_audio.set_push_to_talk.assert_called_with(False)
