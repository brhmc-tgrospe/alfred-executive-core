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
    mgr = AudioManager(barge_in_rms_threshold=0.20)

    # 1. Idle mode: not playing -> low rms mic audio is allowed
    mgr.is_playing = False
    assert mgr.should_stream_mic(rms=0.05) is True

    # 2. Speaking mode: ALFRED is speaking and PTT is inactive -> low rms mic audio is blocked
    mgr.set_push_to_talk(False)
    mgr.is_playing = True
    assert mgr.should_stream_mic(rms=0.05) is False

    # 3. Speaking mode with barge-in: loud user voice above threshold -> allowed
    assert mgr.should_stream_mic(rms=0.25) is True

    # 4. Push-to-Talk active -> always allowed regardless of speaker status
    mgr.set_push_to_talk(True)
    assert mgr.should_stream_mic(rms=0.01) is True


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
