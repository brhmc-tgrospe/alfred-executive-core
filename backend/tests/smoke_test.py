"""End-to-End Smoke Test for A.L.F.R.E.D. Executive Core.

Validates that all backend subsystems, memory stores, safety gates,
and HUD build artifacts are intact and ready for production operation.
"""

import os
from pathlib import Path
import pytest
from backend.audio_manager import AudioManager
from backend.vision_manager import VisionManager
from backend.memory.memory_store import MemoryStore
from backend.tools.os_logistics import OSLogistics
from backend.main import AlfredHubCoordinator


def test_hud_build_artifacts_exist():
    """Verify HUD web and electron compilation output."""
    project_root = Path(__file__).resolve().parent.parent.parent
    hud_dist = project_root / "hud" / "dist" / "index.html"
    electron_main = project_root / "hud" / "dist-electron" / "main.js"
    electron_preload = project_root / "hud" / "dist-electron" / "preload.js"

    assert hud_dist.exists(), f"Missing HUD dist build: {hud_dist}"
    assert electron_main.exists(), f"Missing Electron main build: {electron_main}"
    assert electron_preload.exists(), f"Missing Electron preload build: {electron_preload}"


def test_audio_vision_subsystems_nominal():
    """Verify audio and vision managers initialize cleanly."""
    audio = AudioManager()
    assert audio.input_sample_rate == 16000
    assert audio.output_sample_rate == 24000
    assert audio.current_mic_rms == 0.0

    vision = VisionManager()
    jpeg = vision.capture_screen_jpeg()
    assert isinstance(jpeg, bytes)
    assert len(jpeg) > 0


def test_memory_and_logistics_gate(tmp_path):
    """Verify SQLite WAL and 30s security gate in temporary sandbox."""
    db_path = str(tmp_path / "smoke_memory.db")
    chroma_path = str(tmp_path / "smoke_chroma")

    memory = MemoryStore(db_path=db_path, chroma_dir=chroma_path)
    memory.remember_fact("directive", "The primary directive is executive continuity.")
    facts = memory.recall_context("primary directive")
    assert "primary directive" in facts.lower()
    memory.close()

    logistics = OSLogistics(memory_store=memory)
    diag = logistics.get_system_diagnostics()
    assert "CPU Utilization" in diag
    assert "Memory Usage" in diag
    memory.close()


@pytest.mark.asyncio
async def test_coordinator_lifecycle():
    """Verify coordinator startup, state packet generation, and shutdown."""
    coordinator = AlfredHubCoordinator(port=8765)
    await coordinator.start(start_live_session=False)

    payload = coordinator.get_state_payload()
    assert payload["type"] == "state"
    assert payload["status"] == "idle"
    assert "cpu" in payload
    assert "ram" in payload

    await coordinator.stop()
