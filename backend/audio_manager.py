"""A.L.F.R.E.D. Audio Manager.

Handles:
- 16kHz mono PCM microphone capture with digital pre-amp gain (*2.5) and dynamic device switching.
- 24kHz PCM speaker playback using a thread-safe continuous bytearray FIFO stream buffer
  with 120ms jitter pre-buffering (~5,760 bytes) and zero-underflow sounddevice.RawOutputStream.
- Acoustic gating and instantaneous barge-in interruption.
"""

from __future__ import annotations

import asyncio
import logging
import math
import re
import struct
import threading
import time
from typing import Optional, List, Dict, Any
import numpy as np

try:
    import sounddevice as sd
except ImportError:
    sd = None  # Handled gracefully in mock / non-device environments

logger = logging.getLogger("AlfredAudio")


def calculate_rms(pcm_data: bytes) -> float:
    """Calculates normalized Root Mean Square (RMS) audio amplitude from 16-bit PCM bytes.

    Returns a float between 0.0 and 1.0.
    """
    if not pcm_data:
        return 0.0

    num_samples = len(pcm_data) // 2
    if num_samples == 0:
        return 0.0

    try:
        # Unpack 16-bit signed integers (little-endian)
        samples = struct.unpack(f"<{num_samples}h", pcm_data[: num_samples * 2])
        sum_squares = sum(s * s for s in samples)
        mean_square = sum_squares / num_samples
        rms = math.sqrt(mean_square)
        # Normalize to 0.0 - 1.0 (max 16-bit amplitude is 32767)
        normalized_rms = min(rms / 32768.0, 1.0)
        return float(round(normalized_rms, 4))
    except Exception:
        return 0.0


class AudioManager:
    """Manages asynchronous bidirectional audio streams, continuous FIFO buffering, and acoustic gating."""

    current_device_id: Optional[int] = None
    input_gain: float = 2.5
    ptt_active: bool = True

    def __init__(
        self,
        input_sample_rate: int = 16000,
        output_sample_rate: int = 24000,
        channels: int = 1,
        barge_in_rms_threshold: float = 0.18,
        input_gain: float = 2.5,
    ) -> None:
        self.input_sample_rate = input_sample_rate
        self.output_sample_rate = output_sample_rate
        self.channels = channels
        self.barge_in_threshold = barge_in_rms_threshold
        self.input_gain = input_gain

        # Asynchronous queues
        self.mic_queue: asyncio.Queue[bytes] = asyncio.Queue()
        self.speaker_queue: asyncio.Queue[bytes] = asyncio.Queue()

        # Continuous thread-safe playback FIFO stream buffer
        self._playback_buffer: bytearray = bytearray()
        self._playback_lock: threading.Lock = threading.Lock()

        # 120ms Jitter Pre-Buffer (at 24kHz 16-bit mono: 0.12s * 24000 samples/s * 2 bytes/sample = 5760 bytes)
        self.jitter_prebuffer_bytes: int = int(0.12 * self.output_sample_rate * 2 * self.channels)
        self._prebuffering: bool = True
        self._turn_complete: bool = False
        self.underflow_count: int = 0

        # State flags: default to live listening (ptt_active = True)
        self.is_running: bool = False
        self.is_playing: bool = False
        self.ptt_active: bool = True
        self.current_mic_rms: float = 0.0
        self.mic_rms_peak: float = 0.0
        self.visual_mic_level: float = 0.0
        self.current_speaker_rms: float = 0.0
        self.current_device_id: Optional[int] = None

        # Half-Duplex Speaker Lock: 450ms cooldown window after speaker drain
        self._last_playback_time: float = 0.0
        self.speaker_cooldown_sec: float = 0.45

        # Sounddevice streams
        self._input_stream: Optional[Any] = None
        self._output_stream: Optional[Any] = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._feeder_task: Optional[asyncio.Task] = None

    def is_speaker_locked(self) -> bool:
        """Strict Half-Duplex Speaker Lock.

        Returns True if ALFRED is currently playing audio, has audio in the playback FIFO buffer,
        or is within the 450ms post-speech cooldown window. Completely mutes mic capture to prevent
        speaker echo from self-triggering barge-in or interrupting sentences.
        """
        with self._playback_lock:
            if self.is_playing or len(self._playback_buffer) > 0:
                return True
        return (time.time() - self._last_playback_time) < self.speaker_cooldown_sec

    def update_mic_levels(self, raw_rms: float) -> None:
        """Updates mic RMS peak and visual perceptual level using peak-hold envelope.

        Smooth peak-hold: peak = max(raw_rms, peak * 0.75).
        Perceptual boost: min(1.0, (peak * 18.0) ** 0.6) mapping normal speech (0.005-0.02) to 0.25-0.95.
        """
        self.mic_rms_peak = max(raw_rms, self.mic_rms_peak * 0.75)
        self.visual_mic_level = float(round(min(1.0, (self.mic_rms_peak * 18.0) ** 0.6), 4))

    def set_push_to_talk(self, active: bool) -> None:
        """Sets the manual Push-to-Talk / Live Listening state."""
        self.ptt_active = active

    def feed_speaker_audio(self, chunk: bytes) -> None:
        """Feeds an incoming 24kHz 16-bit PCM chunk into the continuous thread-safe FIFO buffer."""
        if not chunk:
            return
        with self._playback_lock:
            was_empty = (len(self._playback_buffer) == 0)
            self._playback_buffer.extend(chunk)
            self._last_playback_time = time.time()
            if was_empty:
                self._prebuffering = True
                self._turn_complete = False

    def mark_turn_complete(self) -> None:
        """Signals that Gemini has finished transmitting chunks for the current turn.

        Allows any remaining audio tail under the 120ms prebuffer threshold to play out completely.
        """
        with self._playback_lock:
            self._turn_complete = True
            if len(self._playback_buffer) > 0:
                self._prebuffering = False

    def is_playback_active(self) -> bool:
        """Returns True if audio is actively playing or queued in the playback FIFO buffer."""
        with self._playback_lock:
            return len(self._playback_buffer) > 0 or self.is_playing

    async def wait_for_playback_drain(self, timeout: float = 6.0) -> None:
        """Waits asynchronously until the playback bytearray buffer drains completely to 0 bytes."""
        start_time = asyncio.get_event_loop().time()
        # Give initial buffer a moment to begin playback
        await asyncio.sleep(0.04)
        while self.is_playback_active():
            if (asyncio.get_event_loop().time() - start_time) > timeout:
                logger.warning("[AudioManager] Playback drain timed out after %.1fs. Forcibly clearing playback.", timeout)
                self.clear_playback()
                break
            await asyncio.sleep(0.03)
        # Small latency settling window
        await asyncio.sleep(0.04)

    def clear_playback(self) -> int:
        """Immediately flushes the speaker playback buffer and queue for barge-in interruption."""
        cleared_count = 0
        while not self.speaker_queue.empty():
            try:
                self.speaker_queue.get_nowait()
                cleared_count += 1
            except asyncio.QueueEmpty:
                break

        with self._playback_lock:
            if len(self._playback_buffer) > 0:
                cleared_count += 1
            self._playback_buffer.clear()
            self._prebuffering = True
            self._turn_complete = False
            self.is_playing = False
            self.current_speaker_rms = 0.0
            self._last_playback_time = 0.0

        return cleared_count

    def should_stream_mic(self, rms: float) -> bool:
        """Determines whether mic audio chunk should be transmitted to the Live API."""
        if self.is_speaker_locked():
            return False
        return True

    def _input_callback(self, indata, frames, time_info, status):
        """Callback executed in sounddevice PortAudio audio thread for incoming mic data."""
        if not self.is_running or self._loop is None or self._loop.is_closed():
            return

        try:
            raw_bytes = indata.tobytes() if hasattr(indata, "tobytes") else bytes(indata)

            # Apply digital pre-amp gain (*2.5 clipped to int16 range)
            if self.input_gain != 1.0:
                samples = np.frombuffer(raw_bytes, dtype=np.int16)
                amplified = np.clip(samples.astype(np.float32) * self.input_gain, -32768, 32767).astype(np.int16)
                pcm_bytes = amplified.tobytes()
            else:
                pcm_bytes = raw_bytes

            rms = calculate_rms(pcm_bytes)
            # Scaled RMS curve (x2.0) for responsive HUD visualizer display (0.10 to 0.80 range)
            self.current_mic_rms = min(1.0, float(round(rms * 2.0, 4)))
            # ALWAYS compute mic_rms_peak and visual_mic_level on every incoming frame
            # so the HUD LVL % bar ALWAYS shows Director Qadir's real-time hardware mic level!
            self.update_mic_levels(rms)

            # Strict Half-Duplex Speaker Lock: ONLY gate pushing audio chunks into mic_queue for Gemini while speaking
            if not self.is_speaker_locked() and self.should_stream_mic(rms):
                self._loop.call_soon_threadsafe(self.mic_queue.put_nowait, pcm_bytes)
        except Exception:
            pass

    def _output_callback(self, outdata, frames, time_info, status):
        """Continuous stream callback for sounddevice RawOutputStream.

        Slices exact byte blocks from the continuous bytearray FIFO buffer.
        Guarantees jitter-free playback with 120ms prebuffering and zero-padding on drain.
        """
        needed = len(outdata)
        if status and getattr(status, "output_underflow", False):
            self.underflow_count += 1

        with self._playback_lock:
            buf_len = len(self._playback_buffer)

            # 1. Buffer exhausted: output silence, reset prebuffering & turn flag
            # CRITICAL: NEVER update self._last_playback_time when buffer is empty!
            if buf_len == 0:
                outdata[:] = b"\x00" * needed
                self.current_speaker_rms = 0.0
                self.is_playing = False
                self._prebuffering = True
                self._turn_complete = False
                return

            # 2. Jitter Pre-buffering: wait until 120ms of audio has arrived, or turn is explicitly complete,
            # or prebuffering timed out (>150ms since last chunk arrival) to prevent deadlocking short utterances
            if self._prebuffering:
                prebuffer_timed_out = (time.time() - self._last_playback_time) > 0.15
                if buf_len >= self.jitter_prebuffer_bytes or self._turn_complete or prebuffer_timed_out:
                    self._prebuffering = False
                    self.is_playing = True
                else:
                    outdata[:] = b"\x00" * needed
                    self.current_speaker_rms = 0.0
                    return

            self.is_playing = True

            # 3. Continuous FIFO Slicing: only update self._last_playback_time when actual audio bytes are being consumed!
            if buf_len >= needed:
                outdata[:] = self._playback_buffer[:needed]
                del self._playback_buffer[:needed]
                self._last_playback_time = time.time()
                try:
                    self.current_speaker_rms = calculate_rms(bytes(outdata))
                except Exception:
                    pass
            else:
                # Partial block remaining at end of turn (buf_len > 0)
                outdata[:buf_len] = self._playback_buffer[:buf_len]
                outdata[buf_len:] = b"\x00" * (needed - buf_len)
                self._playback_buffer.clear()
                self._prebuffering = True
                self._turn_complete = False
                self.is_playing = False
                self._last_playback_time = time.time()
                try:
                    self.current_speaker_rms = calculate_rms(bytes(outdata[:buf_len]))
                except Exception:
                    pass


    def list_input_devices(self) -> List[Dict[str, Any]]:
        """Lists available sounddevice audio input devices filtered for clean, physically active microphones.

        Filters out virtual mappers, loopbacks, kernel drivers, and disconnected devices.
        Restricts strictly to the Windows default Host API (sd.default.hostapi) so secondary/muted driver endpoints are ignored.
        Always includes 'System Default Microphone' at the top of the list.
        """
        if sd is None:
            return []
        devices: List[Dict[str, Any]] = []
        try:
            all_devs = sd.query_devices()
            default_in = sd.default.device[0] if hasattr(sd.default, "device") else -1
            if default_in >= 0 and default_in < len(all_devs):
                default_hostapi = all_devs[default_in].get("hostapi", getattr(sd.default, "hostapi", 0))
            else:
                try:
                    default_hostapi = getattr(sd.default, "hostapi", 0)
                except Exception:
                    default_hostapi = 0

            # System Default Microphone at the top
            devices.append({
                "id": -1,
                "name": "System Default Microphone",
                "channels": 1,
                "is_default": (self.current_device_id is None or self.current_device_id < 0),
            })

            banned_keywords = [
                "sound mapper",
                "primary sound",
                "stereo mix",
                "pc speaker",
                "@system32",
                "hands-free",
                "output",
            ]

            valid_candidates: List[Dict[str, Any]] = []
            for idx, dev in enumerate(all_devs):
                if dev.get("max_input_channels", 0) <= 0:
                    continue

                # Restrict strictly to the default Windows Host API
                if dev.get("hostapi", -1) != default_hostapi:
                    continue

                raw_name = str(dev.get("name", f"Microphone {idx}")).strip()
                lower_name = raw_name.lower()

                # Filter virtual/mapper/loopback/kernel strings
                if any(b in lower_name for b in banned_keywords):
                    continue

                # Filter empty parentheses like "Microphone Array 1 ()"
                if re.search(r"\(\s*\)$", raw_name) or "()" in raw_name:
                    continue

                # Verify device can actually be opened at input sample rate
                try:
                    sd.check_input_settings(device=idx, samplerate=self.input_sample_rate)
                except Exception:
                    continue

                valid_candidates.append({
                    "id": idx,
                    "name": raw_name,
                    "channels": dev.get("max_input_channels", 1),
                    "is_default": (self.current_device_id == idx) if self.current_device_id is not None else False,
                })

            # Deduplicate by normalized name and clean formatting
            seen_keys: set = set()
            for c in valid_candidates:
                name = c["name"].replace("\xae", "").replace("\ufffd", "").strip()
                # Remove unprintable / non-ascii artifacts
                name = re.sub(r"[^\x20-\x7E]", "", name).strip()
                # Balance truncated parentheses if any
                if name.count("(") > name.count(")"):
                    name = name + " Sound)"
                name = re.sub(r"\s+", " ", name)

                # Normalized deduplication key (first 14 alphanumeric chars)
                norm_key = re.sub(r"[^a-zA-Z0-9]", "", name).lower()[:14]
                if norm_key in seen_keys:
                    continue
                seen_keys.add(norm_key)

                devices.append({
                    "id": c["id"],
                    "name": name,
                    "channels": c["channels"],
                    "is_default": c["is_default"],
                })

        except Exception as e:
            logger.warning("Failed to query audio input devices: %s", e)
        return devices

    def switch_input_device(self, device_id: int | str) -> bool:
        """Hot-swaps the physical microphone input device live without stopping playback or other services."""
        if sd is None:
            return False
        try:
            dev_idx = int(device_id)
            self.current_device_id = None if dev_idx < 0 else dev_idx

            if self.is_running and self._input_stream is not None:
                self._input_stream.stop()
                self._input_stream.close()
                self._input_stream = None

                self._input_stream = sd.InputStream(
                    device=self.current_device_id,
                    samplerate=self.input_sample_rate,
                    channels=self.channels,
                    dtype="int16",
                    callback=self._input_callback,
                    blocksize=512,
                )
                self._input_stream.start()
                logger.info("[AudioManager] Successfully switched mic device to %s", self.current_device_id)
            return True
        except Exception as e:
            logger.error("[AudioManager] Failed to switch mic input device to %s: %s", device_id, e)
            return False

    async def _queue_feeder_worker(self) -> None:
        """Consumes any chunks placed in speaker_queue and forwards them to the continuous FIFO buffer."""
        while self.is_running:
            try:
                chunk = await self.speaker_queue.get()
                if chunk:
                    self.feed_speaker_audio(chunk)
            except asyncio.CancelledError:
                break
            except Exception:
                await asyncio.sleep(0.01)

    async def start(self) -> None:
        """Starts the audio hardware streams and playback worker."""
        if self.is_running:
            return

        self._loop = asyncio.get_running_loop()
        self.is_running = True

        if sd is not None:
            try:
                # 1. Microphone Input Stream (opens Windows System Default input device when current_device_id is None)
                stream_kwargs: Dict[str, Any] = {
                    "samplerate": self.input_sample_rate,
                    "channels": self.channels,
                    "dtype": "int16",
                    "callback": self._input_callback,
                    "blocksize": 512,
                }
                if self.current_device_id is not None and self.current_device_id >= 0:
                    stream_kwargs["device"] = self.current_device_id
                else:
                    stream_kwargs["device"] = None

                self._input_stream = sd.InputStream(**stream_kwargs)
                self._input_stream.start()
            except Exception as e:
                logger.warning("Could not initialize mic InputStream: %s", e)

            try:
                # 2. Continuous Jitter-Free RawOutputStream
                self._output_stream = sd.RawOutputStream(
                    samplerate=self.output_sample_rate,
                    channels=self.channels,
                    dtype="int16",
                    callback=self._output_callback,
                    blocksize=512,
                )
                self._output_stream.start()
            except Exception as e:
                logger.warning("Could not initialize speaker RawOutputStream: %s", e)

        # Start backward-compatible feeder task for speaker_queue
        self._feeder_task = asyncio.create_task(self._queue_feeder_worker())

    async def stop(self) -> None:
        """Stops all streams and workers gracefully."""
        self.is_running = False
        self.clear_playback()

        if self._feeder_task:
            self._feeder_task.cancel()
            try:
                await self._feeder_task
            except asyncio.CancelledError:
                pass

        if self._input_stream:
            try:
                self._input_stream.stop()
                self._input_stream.close()
            except Exception:
                pass
            self._input_stream = None

        if self._output_stream:
            try:
                self._output_stream.stop()
                self._output_stream.close()
            except Exception:
                pass
            self._output_stream = None

        if sd is not None:
            try:
                sd.stop()
            except Exception:
                pass
