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


@pytest.mark.asyncio
async def test_send_startup_briefing(core_setup):
    """Verify executive startup briefing queries tools and sends prompt once."""
    core, logistics, audio, vision = core_setup
    mock_session = AsyncMock()
    mock_session.send = AsyncMock()

    # Pre-populate a briefing note
    logistics.manage_executive_briefing(action="add", task_item="Audit Phase 8 Ergonomics.")

    assert core._initial_briefing_sent is False
    success = await core.send_startup_briefing(mock_session)
    assert success is True
    assert core._initial_briefing_sent is True
    assert mock_session.send.await_count == 1

    call_kwargs = mock_session.send.call_args.kwargs
    assert "Audit Phase 8 Ergonomics" in call_kwargs["input"]
    assert "System Diagnostics" in call_kwargs["input"]
    assert call_kwargs["end_of_turn"] is True

    # Idempotent call: second attempt returns False and doesn't call send again
    second_try = await core.send_startup_briefing(mock_session)
    assert second_try is False
    assert mock_session.send.await_count == 1


@pytest.mark.asyncio
async def test_turn_complete_empty_buffer_transitions_to_listening(core_setup):
    """Regression test: verify status transitions immediately to listening when turn_complete arrives with empty buffer."""
    core, logistics, audio, vision = core_setup
    core.set_status("speaking")
    audio.clear_playback()

    class MockServerContent:
        interrupted = False
        model_turn = None
        turn_complete = True
        generation_complete = False

    class MockResponse:
        server_content = MockServerContent()
        tool_call = None

    await core.process_server_response(MockResponse())
    assert core.status == "listening"


@pytest.mark.asyncio
async def test_generation_complete_alone_does_not_transition_to_listening(core_setup):
    """Regression test: verify generation_complete alone does NOT end the model turn or transition to listening.
    Only turn_complete ends the model turn."""
    core, logistics, audio, vision = core_setup
    core.set_status("speaking")
    core._model_turn_open = True
    audio.clear_playback()

    class MockServerContent:
        interrupted = False
        model_turn = None
        turn_complete = False
        generation_complete = True

    class MockResponse:
        server_content = MockServerContent()
        tool_call = None

    await core.process_server_response(MockResponse())
    # Should STILL be speaking because turn_complete has not arrived yet!
    assert core.status == "speaking"
    assert core._model_turn_open is True

    # When turn_complete = True arrives:
    class MockTurnCompleteContent:
        interrupted = False
        model_turn = None
        turn_complete = True
        generation_complete = False

    class MockTurnCompleteResponse:
        server_content = MockTurnCompleteContent()
        tool_call = None

    await core.process_server_response(MockTurnCompleteResponse())
    assert core.status == "listening"
    assert core._model_turn_open is False


@pytest.mark.asyncio
async def test_speaking_watchdog_auto_reverts_to_listening(core_setup):
    """Regression test: verify speaking watchdog reverts status to listening if server stalls without turn_complete."""
    core, logistics, audio, vision = core_setup

    class MockPart:
        class InlineData:
            data = b"\x10\x00" * 512
        inline_data = InlineData()
        text = None

    class MockModelTurn:
        parts = [MockPart()]

    class MockServerContent:
        interrupted = False
        model_turn = MockModelTurn()
        turn_complete = False
        generation_complete = False

    class MockResponse:
        server_content = MockServerContent()
        tool_call = None

    await core.process_server_response(MockResponse())
    assert core.status == "speaking"

    # Playback drains
    audio.clear_playback()
    # Fast watchdog timeout for test
    core._arm_speaking_watchdog(timeout_sec=0.2)

    await asyncio.sleep(0.35)
    assert core.status == "listening"


@pytest.mark.asyncio
async def test_manual_interruption_cancels_drain_and_speaking_watchdogs(core_setup):
    """Verify manual user barge-in cancels speaking watchdog and drain task."""
    core, logistics, audio, vision = core_setup
    core.set_status("speaking")
    core._arm_speaking_watchdog(timeout_sec=5.0)
    core._schedule_drain_and_transition()

    assert core._speaking_watchdog_task is not None
    assert core._drain_task is not None

    # Trigger explicit manual barge-in
    core.interrupt()
    await asyncio.sleep(0.01)  # Yield so task can process cancellation
    assert core.status == "listening"
    assert core._speaking_watchdog_task is None
    assert core._drain_task.cancelled() or core._drain_task.done()
    assert core._model_turn_open is False


@pytest.mark.asyncio
async def test_server_interrupted_ignored_while_speaking_or_model_turn_open(core_setup):
    """Verify acoustic leakage triggering server_content.interrupted during active speech is ignored to prevent self-cutoff."""
    core, logistics, audio, vision = core_setup
    core.set_status("speaking")
    core._model_turn_open = True
    audio.speaker_queue.put_nowait(b"model_speech_chunk")

    class MockServerContent:
        interrupted = True
        model_turn = None
        turn_complete = False
        generation_complete = False

    class MockResponse:
        server_content = MockServerContent()
        tool_call = None

    await core.process_server_response(MockResponse())
    # Speech must NOT be interrupted or cleared by acoustic leakage
    assert core.status == "speaking"
    assert not audio.speaker_queue.empty()


@pytest.mark.asyncio
async def test_startup_briefing_mic_gate(core_setup):
    """Verify mic audio is NOT sent to Live session until startup briefing completes."""
    core, logistics, audio, vision = core_setup
    core.is_running = True
    core._startup_briefing_completed.clear()
    core.set_status("thinking")

    mock_session = AsyncMock()
    mock_session.send_realtime_input = AsyncMock()
    mock_session.send = AsyncMock()

    # Put a mic chunk into the queue
    audio.mic_queue.put_nowait(b"\x80\x00" * 256)

    # Start _stream_mic_to_alfred in background task
    stream_task = asyncio.create_task(core._stream_mic_to_alfred(mock_session))
    await asyncio.sleep(0.05)

    # Because _startup_briefing_completed is not set, no mic chunks should be sent to session!
    assert mock_session.send_realtime_input.await_count == 0
    assert mock_session.send.await_count == 0

    # Complete startup briefing
    core._startup_briefing_completed.set()
    core.set_status("listening")
    await asyncio.sleep(0.05)

    # Put speech chunk into queue
    speech_chunk = b"\x80\x00" * 256
    audio.visual_mic_level = 0.35
    audio.mic_queue.put_nowait(speech_chunk)
    await asyncio.sleep(0.05)

    # Now chunks should be streamed
    assert (mock_session.send_realtime_input.await_count > 0 or mock_session.send.await_count > 0)

    stream_task.cancel()
    try:
        await stream_task
    except asyncio.CancelledError:
        pass


@pytest.mark.asyncio
async def test_inter_sentence_pause_does_not_leave_speaking(core_setup):
    """Verify that when _playback_buffer dips to 0 bytes between sentences, _model_turn_open=True prevents premature transition to listening."""
    core, logistics, audio, vision = core_setup
    core.set_status("speaking")
    core._model_turn_open = True
    audio.clear_playback()  # Buffer reaches 0 bytes between sentences

    # Trigger drain check
    core._schedule_drain_and_transition()
    await asyncio.sleep(0.1)

    # Since _model_turn_open is still True, status must remain 'speaking'
    assert core.status == "speaking"

    # Now turn_complete arrives
    class MockTurnCompleteContent:
        interrupted = False
        model_turn = None
        turn_complete = True
        generation_complete = False

    class MockTurnCompleteResponse:
        server_content = MockTurnCompleteContent()
        tool_call = None

    await core.process_server_response(MockTurnCompleteResponse())
    # Advance past speaker lock cooldown
    audio._last_playback_time -= 1.0
    core._schedule_drain_and_transition()
    await asyncio.sleep(0.1)
    assert core.status == "listening"


@pytest.mark.asyncio
async def test_client_vad_turn_closer(core_setup):
    """Verify Client-Assisted VAD Turn Closer: 1.0s of silence after speech sends silence + audio_stream_end and transitions to 'thinking'."""
    core, logistics, audio, vision = core_setup
    core.is_running = True
    core._startup_briefing_completed.set()
    core.set_status("listening")

    mock_session = AsyncMock()
    mock_session.send_realtime_input = AsyncMock()
    mock_session.send = AsyncMock()

    stream_task = asyncio.create_task(core._stream_mic_to_alfred(mock_session))
    await asyncio.sleep(0.02)

    # 1. User speaks: push speech chunk
    speech_chunk = b"\x80\x00" * 256
    audio.visual_mic_level = 0.35
    audio.mic_queue.put_nowait(speech_chunk)
    await asyncio.sleep(0.05)

    # 2. User stops speaking: send quiet chunks over 1.1s
    audio.visual_mic_level = 0.05
    silence_sample = b"\x00\x00" * 256
    for _ in range(12):
        audio.mic_queue.put_nowait(silence_sample)
        await asyncio.sleep(0.1)

    # Should have triggered turn closer and transitioned to 'thinking'
    assert core.status == "thinking"
    assert core._thinking_watchdog_task is not None

    # Phase 16: Verify audio_stream_end=True is NEVER sent (keeps stream open)
    # and 1.5s of zero-filled PCM silence was sent to trigger server-side VAD
    for call in mock_session.send_realtime_input.call_args_list:
        assert call.kwargs.get("audio_stream_end") is not True
    assert mock_session.send_realtime_input.call_count >= 16

    core._disarm_thinking_watchdog()
    stream_task.cancel()
    try:
        await stream_task
    except asyncio.CancelledError:
        pass


