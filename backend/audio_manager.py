"""A.L.F.R.E.D. Audio Manager.

Handles 16kHz mono PCM microphone capture and 24kHz PCM speaker playback
using non-blocking asyncio queues, sounddevice streams, RMS amplitude calculations,
and acoustic feedback gating.
"""

from __future__ import annotations

import asyncio
import math
import struct
from typing import Optional, Callable
import numpy as np

try:
    import sounddevice as sd
except ImportError:
    sd = None  # Handled gracefully in mock / non-device environments


def calculate_rms(pcm_data: bytes) -> float:
    """Calculates normalized Root Mean Square (RMS) audio amplitude from 16-bit PCM bytes.

    Returns a float between 0.0 and 1.0.
    """
    if not pcm_data:
        return 0.0

    # Ensure even number of bytes for 16-bit samples
    num_samples = len(pcm_data) // 2
    if num_samples == 0:
        return 0.0

    try:
        # Unpack 16-bit signed integers (little-endian)
        samples = struct.unpack(f"<{num_samples}h", pcm_data[: num_samples * 2])
        # Calculate mean square
        sum_squares = sum(s * s for s in samples)
        mean_square = sum_squares / num_samples
        rms = math.sqrt(mean_square)
        # Normalize to 0.0 - 1.0 (max 16-bit amplitude is 32767)
        normalized_rms = min(rms / 32768.0, 1.0)
        return float(round(normalized_rms, 4))
    except Exception:
        return 0.0


class AudioManager:
    """Manages asynchronous bidirectional audio streams and acoustic gating."""

    def __init__(
        self,
        input_sample_rate: int = 16000,
        output_sample_rate: int = 24000,
        channels: int = 1,
        barge_in_rms_threshold: float = 0.18,
    ) -> None:
        self.input_sample_rate = input_sample_rate
        self.output_sample_rate = output_sample_rate
        self.channels = channels
        self.barge_in_threshold = barge_in_rms_threshold

        # Asynchronous queues
        self.mic_queue: asyncio.Queue[bytes] = asyncio.Queue()
        self.speaker_queue: asyncio.Queue[bytes] = asyncio.Queue()

        # State flags
        self.is_running = False
        self.is_playing = False
        self.ptt_active = False
        self.current_mic_rms = 0.0

        # Sounddevice streams
        self._input_stream: Optional[sd.InputStream] = None
        self._output_stream: Optional[sd.OutputStream] = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._playback_task: Optional[asyncio.Task] = None

    def set_push_to_talk(self, active: bool) -> None:
        """Sets the manual Push-to-Talk state."""
        self.ptt_active = active

    def clear_playback(self) -> None:
        """Immediately flushes the speaker playback queue for barge-in interruption."""
        cleared_count = 0
        while not self.speaker_queue.empty():
            try:
                self.speaker_queue.get_nowait()
                cleared_count += 1
            except asyncio.QueueEmpty:
                break
        self.is_playing = False
        return cleared_count

    def should_stream_mic(self, rms: float) -> bool:
        """Determines whether mic audio chunk should be transmitted to the Live API.

        Applies acoustic gating to prevent ALFRED from interrupting himself.
        """
        # If user explicitly pressed Push-to-Talk, always stream
        if self.ptt_active:
            return True

        # If ALFRED is speaking (output active), only stream if user exceeds barge-in threshold
        if self.is_playing:
            return rms >= self.barge_in_threshold

        # Otherwise, user is speaking in quiet room, allow stream
        return True

    def _input_callback(self, indata, frames, time_info, status):
        """Callback executed in sounddevice PortAudio audio thread for incoming mic data.

        Safely dispatches raw PCM buffers to asyncio.Queue using loop.call_soon_threadsafe
        so the async consumer loop wakes up immediately without thread contention.
        """
        if not self.is_running or self._loop is None or self._loop.is_closed():
            return

        try:
            pcm_bytes = indata.tobytes() if hasattr(indata, "tobytes") else bytes(indata)
            rms = calculate_rms(pcm_bytes)
            self.current_mic_rms = rms

            if self.should_stream_mic(rms):
                self._loop.call_soon_threadsafe(self.mic_queue.put_nowait, pcm_bytes)
        except Exception:
            # Shield PortAudio audio thread from uncaught Python exceptions
            pass

    def _output_callback(self, outdata, frames, time_info, status):
        """Callback for sounddevice output stream."""
        # Non-blocking pull handled via asyncio worker task feeding speaker
        pass

    async def start(self) -> None:
        """Starts the audio hardware streams and playback worker."""
        if self.is_running:
            return

        self._loop = asyncio.get_running_loop()
        self.is_running = True

        if sd is not None:
            try:
                self._input_stream = sd.InputStream(
                    samplerate=self.input_sample_rate,
                    channels=self.channels,
                    dtype="int16",
                    callback=self._input_callback,
                    blocksize=512,
                )
                self._input_stream.start()
            except Exception as e:
                print(f"[AudioManager] Warning: Could not initialize mic InputStream: {e}")

        # Start playback consumer task
        self._playback_task = asyncio.create_task(self._playback_worker())

    async def _playback_worker(self) -> None:
        """Consumes PCM chunks from speaker_queue and outputs to sounddevice."""
        while self.is_running:
            try:
                chunk = await self.speaker_queue.get()
                if not chunk:
                    continue

                self.is_playing = True
                if sd is not None:
                    # Convert raw 16-bit PCM to numpy array and play via sd.play
                    audio_array = np.frombuffer(chunk, dtype=np.int16)
                    sd.play(audio_array, samplerate=self.output_sample_rate, blocking=False)
                    # Estimate playback duration
                    duration = len(audio_array) / self.output_sample_rate
                    await asyncio.sleep(duration)
                else:
                    await asyncio.sleep(0.02)

                if self.speaker_queue.empty():
                    self.is_playing = False
            except asyncio.CancelledError:
                break
            except Exception as e:
                print(f"[AudioManager] Playback error: {e}")
                self.is_playing = False

    async def stop(self) -> None:
        """Stops all streams and workers gracefully."""
        self.is_running = False
        self.clear_playback()

        if self._playback_task:
            self._playback_task.cancel()
            try:
                await self._playback_task
            except asyncio.CancelledError:
                pass

        if self._input_stream:
            self._input_stream.stop()
            self._input_stream.close()
            self._input_stream = None

        if sd is not None:
            sd.stop()
