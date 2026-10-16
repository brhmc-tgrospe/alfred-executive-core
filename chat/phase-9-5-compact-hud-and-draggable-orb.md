# Phase 9.5: Compact HUD Layout & Draggable/Resizable 3D Gyroscope Orb

**Date:** 2026-10-16  
**Status:** Verification Passed (45/45 Tests Passed, 0 Linter Warnings, Production Build Clean)  
**Workspace:** `d:\alfred-executive-core`  

---

## 1. Executive Summary

Phase 9.5 resolves the layout crowding observed in the live HUD overlay and upgrades the 3D AudioOrb into a freely draggable, resizable desktop widget across all layout modes:
1. **Compact 2-Row Telemetry Bar (`hud/src/components/TelemetryBar.tsx`)**: Eliminated the vertical 6-row control wrap and horizontal clipping of the `INSPECT` button. Restructured into a clean 2-row layout with status and telemetry on Row 1, and all controls inline on Row 2.
2. **Compact Transcript Drawer (`hud/src/components/TranscriptDrawer.tsx`)**: Relocated the Quick-Test simulation action chips (`Pulse RMS`, `'Status report'`, `'Inspect screen'`, `'Diagnostics'`) into the header row beside the title and vocal status, reducing drawer height and eliminating secondary toolbars.
3. **Freely Draggable & Resizable 3D Gyroscope Orb (`hud/src/App.tsx` & `AudioOrb.tsx`)**:
   - Decoupled Three.js WebGL resize from scene initialization: scene, torus rings, glowing icosahedron, and particle cloud are initialized once on mount; size adjustments update `renderer.setSize(size, size)` and camera projection matrix without context destruction.
   - Made the Orb draggable anywhere on screen across Cinema, Docked, and Orb-Only modes via pointer events (`onPointerDown`, `pointermove`, `pointerup`).
   - Enabled mouse wheel resizing (`onWheel` ±16px per notch, clamped between 100px and 500px).
   - Added an ambient hover mini-pill anchored under the Orb with `[-]`, `{size}px` readout, `[+]`, `[Center]` screen reset, and `[Cinema | Docked | Orb-Only]` mode switchers.
   - Persisted `orbPos` and `orbSize` in `localStorage` with window resize boundary clamping.

---

## 2. Detailed Implementation

### 2.1 Compact 2-Row Telemetry Bar (`TelemetryBar.tsx`)
- **Row 1 (Status & Telemetry)**:
  - **Left**: Rotating Core disc, connection heartbeat dot, `A.L.F.R.E.D. CORE v1.0` badge, dynamic status pill (`STANDBY`, `LISTENING`, `REASONING`, `EXECUTIVE VOCAL`), and active tool badge (`TOOL: ...`).
  - **Right**: Compact CPU usage meter, RAM usage meter, TCP socket latency to `8.8.8.8` (`PING`), and real-time render rate (`FPS`).
- **Row 2 (Inline Controls)**:
  - **Left**: `MIC LIVE` / `MIC MUTED` toggle-to-talk button, live RMS level bar (`LVL`), hardware microphone device `<select>` (`max-w-[180px] truncate`).
  - **Right**: `CLICK-THROUGH: ON/OFF` desktop passthrough lock, `LAYOUT: CINEMA/DOCKED/ORB_ONLY` cycle button, `STEALTH: ON/OFF` screen protection toggle, and `INSPECT` active screen trigger button.
  - Zero vertical stacking; fits within `max-w-5xl` with horizontal scroll fallback on narrow windows.

### 2.2 Header-Integrated Quick Tests (`TranscriptDrawer.tsx`)
- Header bar houses `EXECUTIVE DIALOGUE`, vocal status indicator, and quick-test buttons:
  - `Pulse RMS (0.85)`: Simulates microphone volume pulse to test 60 FPS Gyroscope Orb reactions.
  - `"Status report"`: Sends text directive to Gemini Live session.
  - `"Inspect screen"`: Triggers visual screen capture and Gemini live injection.
  - `"Diagnostics"`: Runs OS logistics diagnostics.
- `onClick={(e) => e.stopPropagation()}` prevents quick-test clicks from toggling the drawer accordion.
- Drawer body contains only the scrollable transcript log and the directive prompt input field.

### 2.3 Draggable & Resizable AudioOrb (`App.tsx` & `AudioOrb.tsx`)
- **WebGL Performance Decoupling**:
  - `AudioOrb.tsx` scene setup runs once on mount (`useEffect([], ...)`).
  - A lightweight `useEffect([size])` dynamically updates camera aspect and renderer dimensions:
    ```typescript
    useEffect(() => {
      sizeRef.current = size;
      if (rendererRef.current && cameraRef.current) {
        rendererRef.current.setSize(size, size);
        cameraRef.current.aspect = 1;
        cameraRef.current.updateProjectionMatrix();
      }
    }, [size]);
    ```
- **Desktop Dragging (`App.tsx`)**:
  - Attached pointer handlers to fixed container (`position: fixed; left: ${actualX}px; top: ${actualY}px`).
  - Filters out clicks on buttons/inputs so clicking mini-pill buttons doesn't trigger drag.
  - Coordinates persist to `localStorage.getItem("alfred_orb_pos")`.
- **Mouse Wheel & Hover Controls**:
  - `onWheel` over Orb adjusts size in ±16px increments.
  - Hover mini-pill reveals on hover under the Orb:
    - Drag grip indicator (`⋮⋮`)
    - `[-]` and `[+]` size adjustments
    - Current size readout (e.g. `280px`)
    - `[Center]` button: snaps Orb to exact screen center
    - `[Cinema]`: switches to cinema mode and centers Orb
    - `[Docked]`: switches to docked mode and moves Orb to bottom-right corner
    - `[Orb-Only]`: hides top and bottom HUD panels, leaving only the floating Orb

---

## 3. Verification & Test Results

### 3.1 Frontend Build & Static Analysis
```
> hud@1.0.0 lint
> oxlint
Found 0 warnings and 0 errors.
Finished in 21ms on 12 files with 116 rules using 20 threads.

> hud@1.0.0 build
> npm run build:renderer && npm run build:electron
✓ 1928 modules transformed.
dist/index.html                   0.45 kB
dist/assets/index-MTCOwWWO.css   43.67 kB
dist/assets/index-B8iSyRRF.js   803.30 kB
✓ built in 458ms
```

### 3.2 Backend Test Suite (Pytest)
```
============================= test session starts =============================
platform win32 -- Python 3.11.15, pytest-9.1.1, pluggy-1.6.0
collected 45 items

tests\smoke_test.py::test_hud_build_artifacts_exist PASSED               [  2%]
tests\smoke_test.py::test_audio_vision_subsystems_nominal PASSED         [  4%]
tests\smoke_test.py::test_memory_and_logistics_gate PASSED               [  6%]
tests\smoke_test.py::test_coordinator_lifecycle PASSED                   [  8%]
tests\test_audio_manager.py::test_calculate_rms_silence PASSED           [ 11%]
tests\test_audio_manager.py::test_calculate_rms_full_scale PASSED        [ 13%]
tests\test_audio_manager.py::test_calculate_rms_empty PASSED             [ 15%]
tests\test_audio_manager.py::test_barge_in_clear_playback PASSED         [ 17%]
tests\test_audio_manager.py::test_acoustic_gate_logic PASSED             [ 20%]
tests\test_audio_manager.py::test_input_callback_thread_safety PASSED    [ 22%]
tests\test_dev_logistics.py::test_inspect_git_workspace_current_repo PASSED [ 24%]
tests\test_dev_logistics.py::test_inspect_git_workspace_nonexistent_path PASSED [ 26%]
tests\test_dev_logistics.py::test_inspect_local_dev_ports_general PASSED [ 28%]
tests\test_dev_logistics.py::test_inspect_local_dev_ports_specific_free_port PASSED [ 31%]
tests\test_dev_logistics.py::test_probe_network_target_google_dns PASSED [ 33%]
tests\test_dev_logistics.py::test_probe_network_target_invalid_host PASSED [ 35%]
tests\test_dev_logistics.py::test_tail_log_file_success PASSED           [ 37%]
tests\test_dev_logistics.py::test_tail_log_file_nonexistent PASSED       [ 40%]
tests\test_dev_logistics.py::test_tail_log_file_empty PASSED             [ 42%]
tests\test_gemini_tool_declarations.py::test_gemini_tool_declaration_parsing PASSED [ 44%]
tests\test_hud_integration.py::test_hud_contract_schema_alignment PASSED [ 46%]
tests\test_hud_integration.py::test_hud_pending_approval_contract PASSED [ 48%]
tests\test_hud_integration.py::test_hud_ptt_event_handling PASSED        [ 51%]
tests\test_hud_integration.py::test_hud_text_prompt_handling PASSED      [ 53%]
tests\test_live_session.py::test_sync_tool_dispatching PASSED            [ 55%]
tests\test_live_session.py::test_async_tool_dispatching PASSED           [ 57%]
tests\test_live_session.py::test_visual_cortex_screen_injection PASSED   [ 60%]
tests\test_live_session.py::test_barge_in_interruption_flushing PASSED   [ 62%]
tests\test_live_session.py::test_run_executive_loop_lifecycle PASSED     [ 64%]
tests\test_live_session.py::test_send_startup_briefing PASSED            [ 66%]
tests\test_main_ws.py::test_health_endpoint PASSED                       [ 68%]
tests\test_main_ws.py::test_websocket_telemetry_handshake_and_ptt PASSED [ 71%]
tests\test_main_ws.py::test_websocket_approval_resolution PASSED         [ 73%]
tests\test_memory_store.py::test_sqlite_wal_and_custom_paths PASSED      [ 75%]
tests\test_memory_store.py::test_manage_executive_briefing PASSED        [ 77%]
tests\test_memory_store.py::test_remember_and_recall_fact PASSED         [ 80%]
tests\test_memory_store.py::test_thread_safety PASSED                    [ 82%]
tests\test_os_logistics.py::test_system_diagnostics PASSED               [ 84%]
tests\test_os_logistics.py::test_high_risk_classifier PASSED             [ 86%]
tests\test_os_logistics.py::test_execute_safe_command PASSED             [ 88%]
tests\test_os_logistics.py::test_execute_high_risk_approval_granted PASSED [ 91%]
tests\test_os_logistics.py::test_execute_high_risk_approval_denied PASSED [ 93%]
tests\test_os_logistics.py::test_execute_high_risk_approval_timeout PASSED [ 95%]
tests\test_vision_manager.py::test_vision_manager_capture PASSED         [ 97%]
tests\test_wake_word.py::test_wake_word_detector_initialization PASSED   [100%]

============================= 45 passed in 17.65s =============================
```

---

## 4. Modified Files
- `hud/src/components/TelemetryBar.tsx`: Refactored to strictly 2 horizontal rows with inline controls and no button clipping.
- `hud/src/components/TranscriptDrawer.tsx`: Moved quick-test actions into header bar and streamlined drawer body.
- `hud/src/components/AudioOrb.tsx`: Decoupled dynamic WebGL resizing from Three.js scene creation.
- `hud/src/App.tsx`: Added pointer drag handlers, mouse wheel resizing, hover mini-pill, and localStorage persistence.
- `hud/src/hooks/useFps.ts`: Cleaned up initial ref value for React Compiler purity.
