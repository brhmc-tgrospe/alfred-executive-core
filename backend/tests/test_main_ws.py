"""Integration and unit tests for backend/main.py WebSocket Hub."""

import asyncio
import json
import time
import pytest
from starlette.testclient import TestClient
from backend.main import app, hub


@pytest.fixture
def test_client():
    return TestClient(app)


def test_health_endpoint(test_client):
    response = test_client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "online"
    assert "telemetry" in data
    assert "cpu" in data["telemetry"]
    assert "ram" in data["telemetry"]
    assert "ping_ms" in data["telemetry"]


def test_websocket_telemetry_handshake_and_ptt(test_client):
    with test_client.websocket_connect("/hud") as ws:
        # 1. Receive initial state packet
        raw = ws.receive_text()
        state = json.loads(raw)
        assert state["type"] == "state"
        assert "status" in state
        assert "rms_volume" in state
        assert "cpu" in state
        assert "ram" in state
        assert "ping_ms" in state
        assert "active_tool" in state
        assert "pending_approval" in state

        # 2. Test sending PTT event
        ws.send_text(json.dumps({"type": "ptt_event", "state": "down"}))
        time.sleep(0.05)
        assert hub.audio.ptt_active is True

        ws.send_text(json.dumps({"type": "ptt_event", "state": "up"}))
        time.sleep(0.05)
        assert hub.audio.ptt_active is False


def test_websocket_approval_resolution(test_client):
    req_id = "req-test-approval"
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    future = loop.create_future()
    hub.logistics._pending_approvals[req_id] = future
    hub.pending_approval = {"id": req_id, "command": "del file.txt", "risk_level": "high"}

    with test_client.websocket_connect("/hud") as ws:
        # Send approval confirmation
        ws.send_text(json.dumps({
            "type": "approval_response",
            "id": req_id,
            "approved": True,
        }))
        time.sleep(0.05)

        # Verify future resolved
        assert future.done()
        assert future.result() is True
        assert hub.pending_approval is None


@pytest.mark.asyncio
async def test_broadcast_auto_heals_stuck_speaking_status():
    """Verify _broadcast_loop detects empty audio buffer and resets stuck speaking status to listening/idle."""
    hub.audio.ptt_active = True
    hub.live_core.set_status("speaking")
    hub.audio.clear_playback()
    hub.audio._last_playback_time = 0.0  # Cooled down past 450ms

    assert hub.live_core.status == "speaking"
    hub.is_running = True
    task = asyncio.create_task(hub._broadcast_loop())
    await asyncio.sleep(0.08)
    hub.is_running = False
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass

    assert hub.live_core.status == "listening"
