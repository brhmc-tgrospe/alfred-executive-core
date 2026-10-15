# Phase 9: Orb-Only Mode, Ping/FPS Telemetry & System Developer Logistics Suite

## 1. Architectural Summary & Scope of Changes

This phase implements Phase 8.5 (Orb-Only Minimalist Mode, Real-Time FPS, and 8.8.8.8 Ping Telemetry) alongside Phase 9 (System Developer Logistics Suite):

### A. 'Orb-Only' Minimalist Mode (`hud/src/App.tsx`, `TelemetryBar.tsx`, `hud/electron/main.ts`)
- **3-State Layout Cycle:** Upgraded the HUD layout state machine from 2 states (`cinema`, `docked`) to a 3-state cycle:
  `'cinema' -> 'docked' -> 'orb_only' -> 'cinema'`.
- **Panel Visibility:** In `'orb_only'` mode, both `TelemetryBar` and `TranscriptDrawer` are completely hidden from the desktop. Only the 3D Vanilla Three.js `AudioOrb` pulses on the display. High-priority security gates (`ApprovalModal`) remain active if human authorization is required.
- **Hover Mini-Pill:** When the operator hovers the mouse over the `AudioOrb` in `'orb_only'` mode, a subtle floating glassmorphic mini-pill appears below the orb (`group-hover:opacity-100`) providing quick one-click actions to switch back to `'cinema'` or `'docked'` mode.
- **System Tray & Hotkeys:** Added direct mode selectors (`Mode: Cinema`, `Mode: Docked`, `Mode: Orb-Only`) to the native Windows System Tray context menu, with global shortcut `Ctrl+Shift+A` cycling through all three modes.

### B. Real-Time FPS & 8.8.8.8 Ping Telemetry (`backend/main.py`, `hud/src/types.ts`, `TelemetryBar.tsx`, `useFps.ts`)
- **Non-Blocking Async Ping to 8.8.8.8:** In `backend/main.py`, the 2.0-second background metrics loop measures TCP network latency to Google DNS (`8.8.8.8:53`) using `asyncio.wait_for(asyncio.open_connection("8.8.8.8", 53), timeout=1.5)`. This avoids subprocess/console window spawning and never blocks the audio loop. Latency is packaged as `"ping_ms": float` in the WebSocket state JSON broadcast.
- **Real-Time Render Framerate (`useFps` hook):** Implemented `hud/src/hooks/useFps.ts` using `requestAnimationFrame` with a 1.0s sliding delta window to measure real-time HUD rendering framerate.
- **Telemetry UI:** Integrated `PING` (color-coded Emerald `<50ms`, Amber `50-150ms`, Rose `>150ms`/`ERR`) and `FPS` (Emerald `≥55`, Amber `30-54`, Rose `<30`) widgets into `TelemetryBar.tsx` alongside CPU and RAM meters.

### C. System Developer Logistics Suite (`backend/tools/dev_logistics.py`, `live_session.py`, `main.py`)
Created `DevLogistics` exposing 4 tools registered into `AlfredLiveCore` and `AlfredHubCoordinator`:
1. `inspect_git_workspace(repo_path: str = ".") -> str`: Queries active branch, working tree short status (`git status -sb`), diff stats (`git diff --stat`), and the last 3 commit titles.
2. `inspect_local_dev_ports(port: int = 0) -> str`: Audits active listening TCP processes on common developer ports (`80, 443, 3000, 5173, 8000, 8080, 3306, 8765`) or a specific port via `psutil.net_connections`.
3. `probe_network_target(host: str = "8.8.8.8", port: int = 53) -> str`: Resolves DNS and measures round-trip TCP latency in milliseconds to any host or IP.
4. `tail_log_file(log_path: str, lines: int = 25) -> str`: Safely reads the trailing lines of local log files via an in-memory ring buffer (up to 200 lines) for quick debugging.

---

## 2. Verification & Test Execution Results

### Backend Test Suite (`pytest -v`)
- **Total Tests:** **45 passed in 12.18s** (0 failures).
- **Test Modules:**
  - `tests/test_dev_logistics.py`: 9 passed (validating git inspection, port queries, network ping probes, and log tailing).
  - `tests/test_gemini_tool_declarations.py`: 1 passed (confirming `google-genai==2.31.0` parses all 11 tool schema declarations without errors).
  - `tests/test_main_ws.py`: 3 passed (validating `ping_ms` telemetry packet schema and WebSocket approval resolution).
  - `tests/test_hud_integration.py`: 4 passed (verifying contract schema alignment with `ping_ms`).
  - `tests/test_live_session.py`: 6 passed (tool dispatching, visual cortex injection, barge-in, startup briefing).
  - `tests/smoke_test.py`: 4 passed.
  - All remaining audio, memory, and OS logistics tests passed.

### Frontend Production Build (`npm run build`)
- `hud/build:renderer`: `tsc -b && vite build` completed in 403ms.
- `hud/build:electron`: `tsc -p tsconfig.electron.json` completed cleanly.
- Zero TypeScript compiler errors or bundle warnings.

---

## 3. Git Checkpoint
- **Files Modified & Added:**
  - `backend/tools/dev_logistics.py`
  - `backend/tests/test_dev_logistics.py`
  - `backend/main.py`
  - `backend/live_session.py`
  - `backend/tests/test_main_ws.py`
  - `backend/tests/test_hud_integration.py`
  - `hud/src/hooks/useFps.ts`
  - `hud/src/types.ts`
  - `hud/src/components/TelemetryBar.tsx`
  - `hud/src/App.tsx`
  - `hud/electron/main.ts`
  - `hud/electron/preload.ts`
