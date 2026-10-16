# Phase 13.6: Resolution of Stuck Executive Vocal Status

## Executive Summary
Phase 13.6 diagnoses and eliminates the issue where ALFRED remained indefinitely locked in `"speaking"` status (**"EXECUTIVE VOCAL"** on the HUD) following a vocal turn. Through systematic root-cause triage using `debugging-toolkit`, the failure was traced to a status inversion conditional in `live_session.py`, unhandled `generation_complete` signals from the Gemini Multimodal Live API, premature jitter prebuffering lockout on short utterances, the absence of a speaking state watchdog, and lack of background telemetry self-healing. All five defects have been resolved, backed by 5 new regression tests bringing the test suite to 78/78 passing tests.

---

### Root Causes & Architectural Fixes

1. **Status Transition Inversion Bug (`backend/live_session.py`)**:
   - **Root Cause**: When the server signaled `turn_complete`, if the continuous audio playback buffer had already finished draining to zero (`is_playback_active() == False`), the fallback handler executed:
     ```python
     if self.status != "speaking":
         self.set_status("listening")
     ```
     Because ALFRED was actively vocalizing (`status == "speaking"`), `self.status != "speaking"` evaluated to `False`. The status transition was bypassed, trapping ALFRED in `"speaking"` permanently.
   - **The Fix**: Removed the inverted check. Whenever `is_playback_active()` is `False` upon turn completion, status transitions unconditionally to `"listening"` (or `"idle"` if Push-to-Talk is disabled).

2. **Dual-Signal Turn Completion (`generation_complete` + `turn_complete`) (`backend/live_session.py`)**:
   - **Root Cause**: Per the Gemini Live API protocol (`BidiGenerateContentServerContent`), the server signals completion of model generation via `generation_complete: bool` which can precede or accompany `turn_complete: bool`. Previously, only `turn_complete` was inspected.
   - **The Fix**: Evaluated both signals simultaneously:
     ```python
     is_turn_done = bool(
         getattr(server_content, "turn_complete", False)
         or getattr(server_content, "generation_complete", False)
     )
     ```
     Ensures that buffer drain scheduling or immediate status transitions execute regardless of which completion flag the Gemini server emits first.

3. **Autonomous Speaking State Watchdog (`backend/live_session.py`)**:
   - **Root Cause**: While `"thinking"` was protected by an 8.0s timeout watchdog, `"speaking"` had no watchdog. If server audio transmission paused, network packets dropped, or Gemini omitted turn signals, ALFRED remained stuck in `"speaking"` indefinitely. Because `live_session.py` gates microphone transmission while `status == "speaking"`, the system was rendered permanently deaf.
   - **The Fix**: Implemented `_arm_speaking_watchdog(timeout_sec=2.5)`, `_disarm_speaking_watchdog()`, and `_speaking_watchdog_worker()`. Armed on every incoming audio chunk. While audio is playing or queued in `AudioManager`, the timer resets. If playback becomes inactive and 2.5 seconds elapse without further server chunks, it automatically resets status to `"listening"` (or `"idle"`).
   - In addition, user barge-in interruptions cleanly disarm both watchdogs and cancel any pending drain tasks.

4. **Short Utterance Pre-buffering Timeout Auto-Release & Drain Safety (`backend/audio_manager.py`)**:
   - **Root Cause**: In `_output_callback`, jitter prebuffering required either 120ms (`5,760` bytes) of queued audio or `_turn_complete == True` before releasing audio to the speakers. For concise vocal replies under 120ms where `_turn_complete` was delayed, the buffer outputted silence indefinitely while reporting `is_playback_active() == True` and `is_speaker_locked() == True`. In `wait_for_playback_drain()`, a timeout broke the loop without flushing leftover bytes.
   - **The Fix**:
     - Added `prebuffer_timed_out = (time.time() - self._last_playback_time) > 0.15` in `_output_callback`. If >150ms elapses without new audio arrivals, prebuffering releases and plays the queued audio immediately.
     - Reduced `wait_for_playback_drain` timeout to 6.0s and added `self.clear_playback()` on timeout to prevent stale audio bytes from permanently locking the speaker.

5. **Telemetry Hub Auto-Healing Fail-Safe (`backend/main.py`)**:
   - **Root Cause**: If any external process, WebSocket disconnect, or async task cancellation disrupted the normal state machine, the 20Hz telemetry broadcast loop continued broadcasting stale `"speaking"` state.
   - **The Fix**: Added an auto-healing check inside `_broadcast_loop`:
     ```python
     if (
         self.live_core.status == "speaking"
         and not self.audio.is_playback_active()
         and not self.audio.is_speaker_locked()
     ):
         self.live_core.set_status("listening" if self.audio.ptt_active else "idle")
     ```
     The moment hardware audio is drained and the 450ms half-duplex speaker cooldown elapses, any dangling `"speaking"` status automatically self-heals to `"listening"`.

---

### Verification Results

1. **Pytest Full Suite (78/78 Passed)**:
   - Added `test_turn_complete_empty_buffer_transitions_to_listening`: Verifies immediate transition to listening when turn_complete arrives with drained buffer.
   - Added `test_generation_complete_transitions_to_listening`: Verifies generation_complete signals turn completion.
   - Added `test_speaking_watchdog_auto_reverts_to_listening`: Verifies autonomous timeout reversion when server stalls without turn_complete.
   - Added `test_interruption_cancels_drain_and_speaking_watchdogs`: Verifies barge-in disarms all watchdogs and drain tasks.
   - Added `test_broadcast_auto_heals_stuck_speaking_status`: Verifies 20Hz broadcast loop auto-heals dangling speaking status.
   - **78/78 tests passed** (0 failures in 12.31s).

2. **HUD Frontend Production Build**:
   - Executed `npm run build` in `/hud`.
   - Renderer bundle (`dist/index.html`, `dist/assets/`) and Electron main process bundle (`dist-electron/`) built with zero errors.

3. **Git History**:
   - Committed changes under commit `4613198`: *"fix(live): resolve stuck Executive Vocal status via speaking watchdog, generation_complete handling, and drain safety"*.
