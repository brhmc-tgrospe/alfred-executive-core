# Phase 13.5: Permanent Microphone Restoration, Continuous Gemini Streaming & Speaker Lock Fix

## Executive Summary
Phase 13.5 fixes the microphone muting bug introduced in Phase 13, establishes continuous bidirectional audio streaming to Gemini Live API without local silence dropouts, configures default microphone hardware binding, adds the constraint-advisory directive to ALFRED's system prompt, and introduces a permanent regression test to guarantee the microphone never regresses.

---

### Root Causes & Architectural Fixes

1. **Resolution of Permanent Speaker Lock Muting (`backend/audio_manager.py`)**:
   - **Root Cause**: `_output_callback` was refreshing `self._last_playback_time = time.time()` on every continuous 20ms PortAudio tick even when `_playback_buffer` was empty (`len == 0`) and outputting silence. Consequently, `time.time() - self._last_playback_time` was perpetually `< 0.45s`, locking the speaker 100% of the time, forcing `visual_mic_level = 0.0`, and disabling audio transmission (`should_stream_mic() = False`).
   - **The Fix**:
     - In `_output_callback`, `self._last_playback_time = time.time()` is now updated **exclusively** within the active audio consumption branches where `len(self._playback_buffer) > 0`. When the buffer is empty (`buf_len == 0`), `_last_playback_time` is **never** touched, allowing the 450ms cooldown timer to elapse and cleanly release the speaker lock.
     - In `_input_callback`, `raw_rms`, `self.current_mic_rms`, and `self.update_mic_levels(rms)` (which powers `visual_mic_level`) are **always** computed on every single audio frame from physical hardware, ensuring the HUD's `LVL %` meter always reflects Director Qadir's actual vocal input. Only pushing frames to `self.mic_queue` is gated by `is_speaker_locked()` while ALFRED is actively speaking.

2. **Continuous Bidirectional Audio Streaming (`backend/live_session.py`)**:
   - Refactored `_stream_mic_to_alfred` so that whenever `not self.audio_manager.is_speaker_locked() and self.status != "speaking"`, every single 16kHz PCM audio chunk from `mic_queue` is streamed directly to Gemini via `await session.send_realtime_input(audio=types.Blob(data=chunk, mime_type="audio/pcm;rate=16000"))`.
   - Eliminated artificial local silence dropouts and cutoff timers. Gemini's native server-side VAD processes continuous audio context while listening, responding immediately and reliably every time Director Qadir speaks.

3. **Microphone Device Binding & Clean Filtering (`backend/audio_manager.py`)**:
   - `start()` opens `sd.InputStream` targeting the Windows System Default input device (`device=None`).
   - Added `"System Default Microphone"` (ID `-1`) at the top of `list_input_devices()`, defaulting to selected when ALFRED boots.
   - Filtered `list_input_devices()` to strictly match the Windows default Host API (`sd.default.hostapi` / MME) to prevent selecting muted or dead WDM-KS endpoints.

4. **Constraint-Advisory Directive in Persona (`backend/live_session.py`)**:
   - Updated `ALFRED_SYSTEM_PROMPT` with Director Qadir's rule:
     > *"If the tasks given to you are impossible because of some constraints, inform Director Qadir of such constraints and advise him on what to do for it to be doable."*

5. **Permanent Regression Test (`backend/tests/test_audio_manager.py`)**:
   - Added `test_speaker_lock_releases_when_output_buffer_empty`:
     - Feeds audio into `_playback_buffer`.
     - Drains buffer completely via `_output_callback`.
     - Runs multiple idle `_output_callback` ticks while buffer is empty.
     - Advances simulated time past 450ms and asserts `is_speaker_locked()` returns `False`.
     - Simulates microphone input and asserts `visual_mic_level > 0.30` and audio chunk is successfully pushed to `mic_queue`.
     - Re-asserts that even while speaker is locked, `visual_mic_level` continues to reflect live hardware speech.

---

### Verification Results

1. **Pytest Full Suite**:
   - **73/73 tests passed** (0 failures in 10.23s).
   - Includes new regression test `test_speaker_lock_releases_when_output_buffer_empty` and updated device enumeration test.

2. **Live Hardware & Gemini Multi-Turn Benchmark (`backend/diagnose_live.py`)**:
   - **Turn 1 (Startup Greeting)**: First audio at 842.1ms (44 audio chunks, buffer drained cleanly).
   - **Turn 2 (Status Report)**: First audio at 540.8ms (37 audio chunks, buffer drained cleanly).
   - **Turn 3 (Dev Ports Tool)**: Tool triggered (`inspect_local_dev_ports`), tool response sent, vocal reply at 967.9ms (31 audio chunks).
   - **Hardware Microphone Capture**: Active, queried `System Default Microphone` (ID -1) and `Microphone Array (Intel Smart Sound)` (ID 1).
   - **Overall Status**: `[PASS]` on all 3 diagnostic tiers with 0 output underflows.

3. **HUD Frontend Build**:
   - `npm run build` in `hud/`: 0 errors, production client and Electron bundles generated cleanly.
