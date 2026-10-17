"""Unit tests for Phase 23: Long-Idle Zombie Socket Recovery, 15s Tool Timeout Guard,
Deep Statutory/Topic Research Auto-Persistence, and Audio Stream Self-Healing.

Covers:
a) Zombie Socket Auto-Reconnect Test
b) Dead Socket Prompt Recovery Test
c) Tool Execution Timeout Guard Test
d) Deep Research Auto-Persistence & Audio Self-Healing Test
"""

import asyncio
import time
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch
import pytest

from backend.audio_manager import AudioManager
from backend.live_session import AlfredLiveCore, get_dynamic_system_prompt
from backend.memory.memory_store import MemoryStore
from backend.tools.dev_logistics import DevLogistics
from backend.vision_manager import VisionManager


class ConnectionClosedError(Exception):
    """Simulated WebSocket ConnectionClosedError."""


# ============================================================================
# Test a: Zombie Socket Auto-Reconnect & Silent Continuity Test
# ============================================================================

@pytest.mark.asyncio
async def test_zombie_socket_auto_reconnect_and_silent_continuity(tmp_path):
    """Simulate session.receive() ending after an idle timeout; verify _stream_mic_to_alfred
    immediately terminates its loop, run_executive_loop reconnects within 1s, and the second
    connection is silent (_initial_greeting_done == True, no duplicate intro) while preserving
    learned context.
    """
    mem = MemoryStore(db_path=str(tmp_path / "mem.db"), chroma_dir=str(tmp_path / "chroma"))
    mem.remember_fact("research_knowledge", "Philippine Labor Code Book III covers Hours of Work and Weekly Rest Periods.")

    audio = AudioManager()
    audio.start = AsyncMock()
    audio.stop = AsyncMock()
    vision = VisionManager(memory_store=mem)

    core = AlfredLiveCore(
        tools_list=[],
        audio_manager=audio,
        vision_manager=vision,
        memory_store=mem,
        api_key="test_key",
    )

    connect_configs = []
    session_1_sent = []
    session_2_sent = []
    connect_count = 0

    class MockSession:
        def __init__(self, idx: int):
            self.idx = idx

        async def send(self, input=None, end_of_turn=False):
            if self.idx == 1:
                session_1_sent.append(input)
            else:
                session_2_sent.append(input)

        async def send_realtime_input(self, **kwargs):
            pass

        async def receive(self):
            if self.idx == 1:
                # Session 1 stays open briefly for initial greeting, then WebSocket closes on idle timeout
                await asyncio.sleep(0.65)
                return
                yield  # pragma: no cover (makes this an async generator)
            else:
                # Session 2 stays open until test stops core
                while core.is_running and getattr(core, "_session_active", True):
                    await asyncio.sleep(0.05)
                return
                yield  # pragma: no cover

    @asynccontextmanager
    async def fake_connect(model, config):
        nonlocal connect_count
        connect_count += 1
        connect_configs.append(config)
        yield MockSession(connect_count)

    core.client = MagicMock()
    core.client.aio.live.connect = fake_connect

    loop_task = asyncio.create_task(core.run_executive_loop())

    # Wait up to 1.6s total (0.65s session 1 lifetime + <0.95s reconnect)
    t0 = time.monotonic()
    while connect_count < 2 and (time.monotonic() - t0) < 1.65:
        await asyncio.sleep(0.05)

    reconnect_elapsed = time.monotonic() - t0 - 0.65
    assert connect_count >= 2, (
        f"Zombie socket deadlock! Expected run_executive_loop to reconnect after session 1 closed, "
        f"but connect_count={connect_count}"
    )
    assert reconnect_elapsed < 1.0, f"Expected reconnect within 1.0s of socket close, took {reconnect_elapsed:.2f}s"

    # Wait briefly into session 2 to verify no duplicate startup briefing is sent
    await asyncio.sleep(0.65)
    assert getattr(core, "_initial_greeting_done", False) is True
    assert len(session_1_sent) == 1, "Expected initial greeting to be sent on first connection"
    assert len(session_2_sent) == 0, f"Expected second connection to be silent (no duplicate intro), but sent: {session_2_sent}"
    assert core.status == "listening"

    # Verify learned context was preserved in the second connection's system instruction
    second_sys_prompt = connect_configs[1].system_instruction.parts[0].text
    assert "Philippine Labor Code" in second_sys_prompt

    await core.stop()
    await asyncio.wait_for(loop_task, timeout=2.0)
    mem.close()


# ============================================================================
# Test b: Dead Socket Prompt Recovery Test
# ============================================================================

@pytest.mark.asyncio
async def test_dead_socket_prompt_recovery(tmp_path):
    """Simulate send_text_prompt when session.send raises ConnectionClosedError;
    verify it forces reconnection/fallback and never silently drops the user's prompt.
    """
    mem = MemoryStore(db_path=str(tmp_path / "mem.db"), chroma_dir=str(tmp_path / "chroma"))
    audio = AudioManager()
    vision = VisionManager(memory_store=mem)

    fallback_received = []

    async def on_timeout_fallback(prompt_text: str):
        fallback_received.append(prompt_text)

    core = AlfredLiveCore(
        tools_list=[],
        audio_manager=audio,
        vision_manager=vision,
        memory_store=mem,
        api_key="test_key",
        on_thinking_timeout=on_timeout_fallback,
    )

    # Case 1: Dead socket raises ConnectionClosedError when sending text prompt, and reconnects to healthy session
    dead_session = AsyncMock()
    dead_session.send = AsyncMock(side_effect=ConnectionClosedError("WebSocket 1006 connection closed abnormally"))

    healthy_session = AsyncMock()
    healthy_session.send = AsyncMock()

    core.is_running = True
    core._session = dead_session
    core._session_active = True

    async def simulate_background_reconnect():
        await asyncio.sleep(0.1)
        core._session = healthy_session
        core._session_active = True
        if hasattr(core, "_session_ready_event"):
            core._session_ready_event.set()

    core._loop_active = True
    reconnect_helper = asyncio.create_task(simulate_background_reconnect())

    await core.send_text_prompt("Explain Civil Service Commission leave rules")
    await reconnect_helper

    # Prompt must have been retried on the new healthy session OR handled by fallback (never dropped!)
    assert healthy_session.send.await_count >= 1 or len(fallback_received) >= 1
    if healthy_session.send.await_count >= 1:
        sent_kwargs = healthy_session.send.call_args.kwargs
        assert "Civil Service Commission" in sent_kwargs.get("input", "")

    # Case 2: If no background reconnect is available, fallback handler is invoked immediately so prompt is never dropped
    core._loop_active = False
    core._session = dead_session
    await core.send_text_prompt("Summarize Book IV of the Labor Code")
    assert "Summarize Book IV of the Labor Code" in fallback_received

    mem.close()


# ============================================================================
# Test c: Tool Execution Timeout Guard Test
# ============================================================================

@pytest.mark.asyncio
async def test_tool_execution_timeout_guard(tmp_path):
    """Simulate a hung tool taking 30s; verify live_session times it out cleanly at 15s
    (and configurable timeout) and returns a graceful LiveClientToolResponse without freezing.
    """
    mem = MemoryStore(db_path=str(tmp_path / "mem.db"), chroma_dir=str(tmp_path / "chroma"))
    audio = AudioManager()
    vision = VisionManager(memory_store=mem)

    def hung_sync_research_tool(query: str = "test") -> str:
        time.sleep(30.0)
        return "Unreachable"

    async def hung_async_tool(query: str = "test") -> str:
        await asyncio.sleep(30.0)
        return "Unreachable"

    core = AlfredLiveCore(
        tools_list=[hung_sync_research_tool, hung_async_tool],
        audio_manager=audio,
        vision_manager=vision,
        memory_store=mem,
        api_key="test_key",
    )

    # 1. Verify default hard timeout is strictly 15.0s
    assert getattr(core, "tool_execution_timeout_sec", None) == 15.0

    # Set timeout to 0.35s for fast deterministic test execution of a 30s hung tool
    core.tool_execution_timeout_sec = 0.35

    mock_session = AsyncMock()
    mock_session.send = AsyncMock()

    class DummyCall:
        def __init__(self, name: str, args: dict):
            self.name = name
            self.args = args
            self.id = f"call-{name}"

    t0 = time.monotonic()
    res_sync = await core.dispatch_tool_call(mock_session, DummyCall("hung_sync_research_tool", {"query": "CSC"}))
    elapsed_sync = time.monotonic() - t0

    assert elapsed_sync < 1.5, f"Hung sync tool was not timed out! Took {elapsed_sync:.2f}s"
    assert "timed out" in str(res_sync).lower()
    assert core.active_tool is None
    assert mock_session.send.await_count == 1

    res_async = await core.dispatch_tool_call(mock_session, DummyCall("hung_async_tool", {"query": "Labor Code"}))
    assert "timed out" in str(res_async).lower()
    assert core.active_tool is None
    assert mock_session.send.await_count == 2

    mem.close()


# ============================================================================
# Test d: Deep Research Auto-Persistence & Audio Stream Self-Healing Test
# ============================================================================

def test_deep_research_auto_persistence_and_audio_self_healing(tmp_path):
    """Verify that researching a topic like 'Philippine Labor Code and CSC laws'
    automatically persists the learned summary into memory_store and injects it into
    build_dynamic_director_profile(), and verify AudioManager.ensure_streams_healthy().
    """
    mem = MemoryStore(db_path=str(tmp_path / "mem.db"), chroma_dir=str(tmp_path / "chroma"))
    vision = VisionManager(memory_store=mem)
    dev = DevLogistics(vision_manager=vision, memory_store=mem)

    # 1. Research 'Philippine Labor Code and CSC laws'
    digest = dev.research_software_interface_and_docs(
        application_name="Statutory & Legal Research",
        feature_or_icon_query="Philippine Labor Code and Civil Service Commission (CSC) laws",
    )

    assert "Philippine Labor Code" in digest or "Civil Service Commission" in digest
    assert "research_knowledge" in digest or "Memory" in digest

    # 2. Verify knowledge was persisted into MemoryStore (recallable via recall_context)
    recalled = mem.recall_context("Philippine Labor Code and CSC laws")
    assert "Labor Code" in recalled or "Civil Service" in recalled

    # 3. Verify build_dynamic_director_profile() automatically includes the top 5 recently learned facts
    profile = mem.build_dynamic_director_profile()
    assert "Philippine Labor Code" in profile or "Civil Service Commission" in profile

    # 4. Verify AudioManager.ensure_streams_healthy() detects and recovers inactive streams
    audio = AudioManager()
    audio.is_running = True

    class DeadStream:
        active = False
        def stop(self): pass
        def close(self): pass

    audio._input_stream = DeadStream()
    audio._output_stream = DeadStream()

    mock_new_in = MagicMock()
    mock_new_in.active = True
    mock_new_out = MagicMock()
    mock_new_out.active = True

    with patch("backend.audio_manager.sd") as mock_sd:
        mock_sd.InputStream.return_value = mock_new_in
        mock_sd.RawOutputStream.return_value = mock_new_out

        healthy = audio.ensure_streams_healthy()
        assert healthy is True
        assert getattr(audio, "stream_recovery_count", 0) >= 1
        mock_new_in.start.assert_called_once()
        mock_new_out.start.assert_called_once()

    mem.close()
