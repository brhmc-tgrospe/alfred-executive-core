"""Unit tests for backend/wake_word.py."""

from backend.wake_word import WakeWordDetector


def test_wake_word_detector_initialization():
    detector = WakeWordDetector()
    assert detector is not None
    # Trigger manually (PTT fallback)
    detector.trigger_manually()
    assert detector.process_pcm_chunk(b"\x00" * 1024) is True
    # Next chunk without trigger should be False
    assert detector.process_pcm_chunk(b"\x00" * 1024) is False
