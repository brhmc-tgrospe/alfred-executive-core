"""Unit tests for backend/live_session.py.

Validates:
1. Tool dispatching for synchronous and asynchronous coroutines.
2. Visual cortex screen frame injection into active Live API session.
3. Sub-second barge-in interruption queue flushing.
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock
import pytest
from backend.audio_manager import AudioManager
from backend.vision_manager import VisionManager
from backend.memory.memory_store import MemoryStore
from backend.tools.os_logistics import OSLogistics
from backend.live_session import AlfredLiveCore


class DummyFunctionCall:
    def __init__(self, name: str, args: dict, call_id: str = "test-call-1"):
        self.name = name
        self.args = args
        self.id = call_id


@pytest.fixture
def core_setup(tmp_path):
    db_file = str(tmp_path / "test_live.db")
    chroma_dir = str(tmp_path / "test_live_chroma")
    mem = MemoryStore(db_path=db_file, chroma_dir=chroma_dir)
    audio = AudioManager()
    vision = VisionManager()
    logistics = OSLogistics(memory_store=mem, vision_manager=vision, approval_timeout=0.2)

    tools_list = [
        logistics.get_system_diagnostics,
        logistics.launch_application_or_url,
        logistics.inspect_active_screen,
        logistics.manage_executive_briefing,
        logistics.remember_fact,
        logistics.recall_context,
        logistics.execute_terminal_command,
    ]

    core = AlfredLiveCore(
        tools_list=tools_list,
        audio_manager=audio,
        vision_manager=vision,
        api_key="mock_key",
    )
    return core, logistics, audio, vision


@pytest.mark.asyncio
async def test_sync_tool_dispatching(core_setup):
    core, logistics, audio, vision = core_setup
    mock_session = AsyncMock()
    mock_session.send = AsyncMock()

    fc = DummyFunctionCall(name="get_system_diagnostics", args={}, call_id="fc-diag")

    # Dispatch tool
    result = await core.dispatch_tool_call(mock_session, fc)

    assert "System Diagnostics Telemetry" in result
    assert core.active_tool is None  # Must reset to None after execution
    assert mock_session.send.await_count == 1  # Sent FunctionResponse


@pytest.mark.asyncio
async def test_async_tool_dispatching(core_setup):
    core, logistics, audio, vision = core_setup
    mock_session = AsyncMock()
    mock_session.send = AsyncMock()

    fc = DummyFunctionCall(
        name="execute_terminal_command",
        args={"command": "echo LIVE_TEST_SUCCESS"},
        call_id="fc-term",
    )

    result = await core.dispatch_tool_call(mock_session, fc)
    assert "LIVE_TEST_SUCCESS" in result
    assert core.active_tool is None
    assert mock_session.send.await_count == 1


@pytest.mark.asyncio
async def test_visual_cortex_screen_injection(core_setup):
    core, logistics, audio, vision = core_setup
    mock_session = AsyncMock()
    mock_session.send = AsyncMock()

    fc = DummyFunctionCall(
        name="inspect_active_screen",
        args={"question": "What is shown in the terminal?"},
        call_id="fc-vision",
    )

    result = await core.dispatch_tool_call(mock_session, fc)
    assert "Screen frame captured" in result

    # Verify that mock_session.send was called twice:
    # 1st call: Image JPEG frame sent to Live API
    # 2nd call: Tool Response sent
    assert mock_session.send.await_count == 2
    first_call_kwargs = mock_session.send.call_args_list[0].kwargs
    assert first_call_kwargs["input"]["mime_type"] == "image/jpeg"
    assert len(first_call_kwargs["input"]["data"]) > 0


@pytest.mark.asyncio
async def test_barge_in_interruption_flushing(core_setup):
    core, logistics, audio, vision = core_setup

    # Put dummy audio packets into speaker queue
    audio.speaker_queue.put_nowait(b"audio_chunk_1")
    audio.speaker_queue.put_nowait(b"audio_chunk_2")
    audio.is_playing = True
    assert audio.speaker_queue.qsize() == 2

    # Simulate Gemini Live stream message with server_content.interrupted = True
    class MockServerContent:
        interrupted = True
        model_turn = None

    class MockResponse:
        server_content = MockServerContent()
        tool_call = None

    # Directly process server response with interruption
    await core.process_server_response(MockResponse())

    # Verify speaker queue is completely drained
    assert audio.speaker_queue.empty()
    assert audio.is_playing is False
    assert core.status == "listening"


@pytest.mark.asyncio
async def test_run_executive_loop_lifecycle(core_setup):
    """Verify run_executive_loop starts and stops cleanly."""
    core, logistics, audio, vision = core_setup

    async def mock_start():
        await asyncio.sleep(0.02)

    core.start = mock_start
    task = asyncio.create_task(core.run_executive_loop())
    await asyncio.sleep(0.01)
    assert core._loop_active is True

    await core.stop()
    await task
    assert core._loop_active is False
