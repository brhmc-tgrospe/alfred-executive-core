# Phase 21 Engineering Log: Visual Template Learning Engine & Voice Sync Turn Fencing

**Timestamp**: 2026-10-17 13:05:00 (Philippine Standard Time, UTC+8)  
**Author**: A.L.F.R.E.D. Executive Core / Antigravity Agentic Pair  
**Status**: COMPLETE (Verified & Passing — 142/142 Tests Passing, 100% Pass Rate, HUD Clean Production Build)

---

## 1. Executive Summary & Operational Context

Phase 21 resolves two critical operational anomalies encountered during Director Qadir's live runtime testing:

1. **Bug 1: Voice Responses Dropping to Text-Only & Delayed Out-of-Order Voice Playback**:
   - **Root Cause 1 (Watchdog Premature Fallback)**: The 8.0s `_thinking_watchdog_worker` fired while a tool (such as full-screen Set-of-Marks OpenCV analysis or template matching) was actively executing. This pushed a text-only fallback response to the HUD drawer without audio. Then, seconds later, Gemini Live streamed delayed voice audio for the *previous* command while Director Qadir was already giving the *next* command.
   - **Root Cause 2 (Stale Jitter Buffering & Missing Turn ID Fencing)**: When a new prompt or speech onset began, late audio chunks from prior turns were not fenced out, and a large 120ms prebuffer (`jitter_prebuffer_bytes = 5760`) trapped small audio chunks in `_playback_buffer`.
   - **Resolution**:
     - Enforced `response_modalities=["AUDIO"]` and introduced a monotonically increasing `_current_turn_id: int` on `AlfredLiveCore`. Whenever a new user prompt or speech onset begins, `_current_turn_id += 1` and `audio_manager.clear_playback()` is immediately executed.
     - Upgraded `_arm_thinking_watchdog` and `_thinking_watchdog_worker`: extended base timeout from 8.0s to 18.0s, and programmed the watchdog loop to continuously reset its elapsed timer whenever `self.active_tool is not None`.
     - In `main.py`'s `_execute_fallback_prompt`, verified `self.live_core.active_tool is None` before transmitting any fallback text.
     - Reduced `jitter_prebuffer_bytes` to 2400 (50ms) with an 80ms maximum drain timeout for responsive playback.

2. **Bug 2: ALFRED Pretends to Learn Visual Icons Without Storing Templates**:
   - **Root Cause**: Previously, teaching ALFRED a custom visual icon gave verbal acknowledgment with zero visual template storage. If the target application window moved, ALFRED failed to find the element.
   - **Resolution**:
     - Built the `visual_ui_memories` SQLite persistence table in `backend/memory/memory_store.py` and template directory `backend/memory/visual_templates/`.
     - Added `action="learn_element"` (or `"learn"`) to `screen_pixel_navigation` in `backend/tools/gui_automation.py` (maintaining strictly $\le 30$ registered tools):
       1. Nudges OS cursor (+120px) for 60ms to eliminate cursor occlusion.
       2. Captures clean 44x44 un-occluded PNG icon template.
       3. Moves cursor back for 300ms to engage hover state, captures 44x44 hover patch and 160x160 context patch.
       4. Computes `cv2.absdiff` hover delta and stores element key, aliases, coordinates, dimensions, and hover description in `visual_ui_memories`.
     - Upgraded `autonomous_screen_search` in `backend/vision_manager.py` with **Priority 1: Learned Visual Template Multi-Scale Matching** using `cv2.matchTemplate` with `cv2.TM_CCOEFF_NORMED` across scales `[0.85, 1.0, 1.15]`. If `max_val >= 0.75`, returns translation-invariant center coordinates.
     - Integrated `_auto_learn_on_click` on successful verified clicks (`change_pct >= 1.5%`).
     - Added `VISUAL ICON LEARNING RULE` to `ALFRED_BASE_SYSTEM_PROMPT`.

---

## 2. Technical Implementation Architecture

### 2.1 Turn Fencing & Audio Stream Synchronization

- **Monotonically Increasing Turn ID (`_current_turn_id`)**:
  - `AlfredLiveCore` maintains `self._current_turn_id = 0`.
  - On user speech onset (`_stream_mic_to_alfred`) or inbound text prompt (`send_text_prompt` and `handle_hud_message`), `self._current_turn_id += 1` and `self.audio_manager.clear_playback()` is called immediately.
  - Drops any late-arriving packets from previous turns so ALFRED never speaks a past command out of order.
- **Non-Interrupting Tool Watchdog**:
  - `_arm_thinking_watchdog` sets an 18.0s timeout.
  - `_thinking_watchdog_worker` samples every 0.2s: if `self.active_tool is not None`, `elapsed` resets to `0.0`.
  - In `main.py`, `_execute_fallback_prompt` guards with:
    ```python
    if getattr(self.live_core, "active_tool", None) is not None:
        return
    ```
- **Low-Latency Audio Jitter Buffer**:
  - Set `jitter_prebuffer_bytes = 2400` (50ms at 24kHz 16-bit mono).
  - Reduced buffer timeout in `_output_callback` from 150ms to 80ms.

### 2.2 Visual Template Learning Engine & Multi-Scale Matching

- **Schema Definition (`visual_ui_memories`)**:
  ```sql
  CREATE TABLE IF NOT EXISTS visual_ui_memories (
      element_key TEXT PRIMARY KEY,
      aliases TEXT,
      app_context TEXT,
      template_png_path TEXT,
      hover_template_png_path TEXT,
      width INTEGER,
      height INTEGER,
      hover_behavior_desc TEXT,
      last_seen_x INTEGER,
      last_seen_y INTEGER,
      updated_at_utc8 TEXT
  );
  ```
- **Two-Phase Template Capture (`learn_element`)**:
  1. Cursor offset (+120px) for 60ms $\rightarrow$ clean template capture (`cv2.imwrite`).
  2. Cursor return for 300ms $\rightarrow$ hover template capture + context patch.
  3. `cv2.absdiff` calculates pixel variance percentage for dynamic tooltip/border shift detection.
- **Multi-Scale Invariant Matching (`_match_learned_visual_template`)**:
  - Evaluates scales `[0.85, 1.0, 1.15]`.
  - Uses `cv2.matchTemplate(screen_bgr, scaled_tpl, cv2.TM_CCOEFF_NORMED)`.
  - Threshold `0.75` guarantees robust detection even when windows are dragged or resized.
- **Auto-Learning on Verified Click**:
  - In `screen_pixel_navigation`, if a verified click causes `change_pct >= 1.5%`, ALFRED automatically learns the clicked element template.

---

## 3. Verification & Invariant Audit

### 3.1 Unit & Regression Test Verification

- **New Test Suite (`backend/tests/test_phase21_visual_template_learning_and_voice_sync.py`)**:
  - `test_translation_invariant_icon_relocation`: PASSED (Icon relocated from `(1800, 980)` to `(420, 310)` matched within $\pm 3$px with `confidence >= 0.75`).
  - `test_hover_state_diff_detection`: PASSED (Calculated visual delta variance between clean and hovered state).
  - `test_turn_fencing_on_text_prompt_and_speech_onset`: PASSED (`_current_turn_id` increments, buffer cleared).
  - `test_non_interrupting_watchdog_during_active_tool`: PASSED (Watchdog paused during active tool execution).
  - `test_audio_prebuffer_low_latency_setting`: PASSED (`jitter_prebuffer_bytes == 2400`).
  - `test_strictly_30_registered_tools`: PASSED (Strictly 30 tools, zero duplicates).
- **Full Backend Suite**: **142/142 tests passing (100% pass rate)**.
- **HUD Production Build**: `npm run build` completed with zero errors.

### 3.2 Invariant Verification

| Invariant | Target | Result | Status |
|---|---|---|---|
| Total Registered Tools | $\le 30$ | Exactly 30 | **VERIFIED** |
| Timestamp Formatting | Strict UTC+8 | Enforced across all components | **VERIFIED** |
| Persona Address | Sir / Director Qadir | Enforced in prompts and transcripts | **VERIFIED** |
| Audio Prebuffer Latency | 50ms (2400 bytes) | 2400 bytes, 80ms timeout | **VERIFIED** |
| Watchdog Tool Pause | Pauses while active_tool is not None | Verified in worker loop & fallback guard | **VERIFIED** |
