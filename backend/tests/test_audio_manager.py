"""Unit tests for backend/audio_manager.py."""

import struct
import pytest
from backend.audio_manager import calculate_rms, AudioManager


def test_calculate_rms_silence():
    # 512 samples of pure silence (all zeros)
    silence = b"\x00\x00" * 512
    rms = calculate_rms(silence)
    assert rms == 0.0


def test_calculate_rms_full_scale():
    # Maximum positive 16-bit PCM integer: 32767
    max_sample = struct.pack("<h", 32767)
    audio_data = max_sample * 512
    rms = calculate_rms(audio_data)
    # Should be close to 1.0 (normalized)
    assert 0.99 <= rms <= 1.0


def test_calculate_rms_empty():
    assert calculate_rms(b"") == 0.0


def test_barge_in_clear_playback():
    mgr = AudioManager()
    # Put dummy chunks into speaker queue
    mgr.speaker_queue.put_nowait(b"dummy_chunk_1")
    mgr.speaker_queue.put_nowait(b"dummy_chunk_2")
    mgr.speaker_queue.put_nowait(b"dummy_chunk_3")
    mgr.is_playing = True

    assert mgr.speaker_queue.qsize() == 3
    cleared = mgr.clear_playback()

    assert cleared == 3
    assert mgr.speaker_queue.empty()
    assert mgr.is_playing is False


def test_acoustic_gate_logic():
    import time
    mgr = AudioManager(barge_in_rms_threshold=0.20)

    # 1. Idle mode: not playing -> mic audio is allowed
    mgr.is_playing = False
    assert mgr.should_stream_mic(rms=0.05) is True

    # 2. Speaking mode: ALFRED is speaking -> half-duplex lock blocks mic audio to kill speaker echo
    mgr.is_playing = True
    assert mgr.should_stream_mic(rms=0.05) is False
    assert mgr.should_stream_mic(rms=0.25) is False

    # 3. Cooldown window: after speaking finishes, lock remains active for 450ms
    mgr.is_playing = False
    mgr._last_playback_time = time.time()
    assert mgr.is_speaker_locked() is True
    assert mgr.should_stream_mic(rms=0.10) is False

    # 4. After cooldown window expires: mic audio is allowed again
    mgr._last_playback_time = time.time() - 1.0
    assert mgr.is_speaker_locked() is False
    assert mgr.should_stream_mic(rms=0.10) is True


@pytest.mark.asyncio
async def test_input_callback_thread_safety():
    """Verify sounddevice PortAudio thread callback dispatches safely via call_soon_threadsafe."""
    import asyncio
    mgr = AudioManager()
    mgr.is_running = True
    mgr._loop = asyncio.get_running_loop()

    # Simulate raw PCM buffer from PortAudio thread (sample value 32 = 0x0020)
    raw_chunk = b"\x20\x00" * 256
    mgr._input_callback(raw_chunk, 256, None, None)

    # Let event loop process threadsafe dispatch
    await asyncio.sleep(0.01)

    assert not mgr.mic_queue.empty()
    queued = mgr.mic_queue.get_nowait()
    # Verifies digital pre-amp gain (* 2.5: 32 -> 80 = 0x0050)
    expected_chunk = b"\x50\x00" * 256
    assert queued == expected_chunk
    assert mgr.current_mic_rms > 0.0


def test_mic_peak_hold_and_visual_level():
    """Verify that a raw mic RMS of 0.010 produces visual_mic_level > 0.30 and holds across peak decay."""
    mgr = AudioManager()
    assert mgr.mic_rms_peak == 0.0
    assert mgr.visual_mic_level == 0.0

    # Simulate raw mic RMS of 0.010 (typical speech level)
    mgr.update_mic_levels(0.010)
    assert mgr.mic_rms_peak == 0.010
    assert mgr.visual_mic_level > 0.30
    assert mgr.visual_mic_level < 0.60

    # Next frame with silence: raw_rms = 0.0 -> peak decays by factor of 0.75
    prev_visual = mgr.visual_mic_level
    mgr.update_mic_levels(0.0)
    assert pytest.approx(mgr.mic_rms_peak, 0.0001) == 0.0075
    # Holds across decay: still > 0.25
    assert mgr.visual_mic_level > 0.25
    assert mgr.visual_mic_level < prev_visual


def test_list_input_devices_filtering_and_deduplication(monkeypatch):
    """Verify list_input_devices filters out mappers, loopbacks, kernel strings, and deduplicates cleanly."""
    mgr = AudioManager()

    mock_devices = [
        {"name": "Microsoft Sound Mapper - Input", "max_input_channels": 2, "hostapi": 0},
        {"name": "Microphone Array (Intel\xae Smart ", "max_input_channels": 4, "hostapi": 0},
        {"name": "Headset (ERAZER XF55)", "max_input_channels": 1, "hostapi": 0},
        {"name": "Primary Sound Capture Driver", "max_input_channels": 2, "hostapi": 1},
        {"name": "Microphone Array (Intel\xae Smart Sound Technology)", "max_input_channels": 4, "hostapi": 1},
        {"name": "Stereo Mix (Realtek HD Audio)", "max_input_channels": 2, "hostapi": 3},
        {"name": "PC Speaker (Realtek)", "max_input_channels": 2, "hostapi": 3},
        {"name": "Input (@System32\\drivers\\btha2dp.sys)", "max_input_channels": 2, "hostapi": 3},
        {"name": "Microphone Array 1 ()", "max_input_channels": 2, "hostapi": 3},
    ]
    mock_hostapis = [
        {"name": "MME"},
        {"name": "Windows DirectSound"},
        {"name": "Windows WASAPI"},
        {"name": "Windows WDM-KS"},
    ]

    import sounddevice as mock_sd
    monkeypatch.setattr(mock_sd, "query_devices", lambda: mock_devices)
    monkeypatch.setattr(mock_sd, "query_hostapis", lambda: mock_hostapis)
    monkeypatch.setattr(mock_sd.default, "device", [1, 0])
    monkeypatch.setattr(mock_sd, "check_input_settings", lambda **kwargs: None)

    devices = mgr.list_input_devices()
    names = [d["name"] for d in devices]

    # Verify virtual and invalid driver names are completely excluded
    for banned in ["Sound Mapper", "Primary Sound", "Stereo Mix", "PC Speaker", "@System32", "()"]:
        assert not any(banned.lower() in n.lower() for n in names)

    # Verify clean physical devices are present and deduplicated
    assert len(devices) == 2
    assert any("Microphone Array" in n for n in names)
    assert any("Headset (ERAZER XF55)" in n for n in names)
    # Check default flag
    default_dev = [d for d in devices if d["is_default"]]
    assert len(default_dev) == 1
    assert default_dev[0]["id"] == 1

