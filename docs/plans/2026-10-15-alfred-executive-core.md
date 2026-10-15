# A.L.F.R.E.D. Implementation Plan

> **For Agent:** REQUIRED SUB-SKILL: Follow the tasks incrementally with automated test verification gates.

**Goal:** Build and integrate **A.L.F.R.E.D.** (*Autonomous Logistics Functional Response & Executive Director*), a real-time multimodal desktop AI assistant with a Python asyncio backend (`google-genai` Live API, SQLite/ChromaDB memory, OS logistics tools) and an Electron + React 19 + Three.js dark glassmorphic desktop HUD overlay.

**Architecture:** Monorepo architecture where `/backend` runs an asynchronous IPC hub over WebSocket (`ws://localhost:8765`), streaming audio/telemetry with Gemini Multimodal Live API and managing OS tools, while `/hud` runs a transparent, frameless, always-on-top desktop widget with an audio-reactive 3D gyroscopic visualizer and human-in-the-loop approval modal.

**Tech Stack:**
* Backend: Python 3.11+, `google-genai` (Gemini Multimodal Live API), `sounddevice`, `numpy`, `mss`, `Pillow`, `websockets`, `psutil`, `chromadb`, `pytest`.
* Frontend: Electron, React 19, TypeScript, Vite, Tailwind CSS v4, Three.js, Lucide React.
* Coordination: WebSocket on `ws://localhost:8765`, Windows single-click batch script (`start_alfred.bat`).

---

### Task 1: Python Environment & Monorepo Directory Scaffold

**Files:**
* Create: `.gitignore`
* Create: `backend/requirements.txt`
* Setup: `.venv` via `uv`

**Step 1: Create .gitignore**
Ignore virtual environment, node_modules, dist, temporary database, and log files.

**Step 2: Create backend/requirements.txt**
Specify pinned stable versions of dependencies:
```text
google-genai>=1.0.0
sounddevice>=0.5.1
numpy>=1.26.0
mss>=9.0.1
Pillow>=10.3.0
websockets>=12.0
fastapi>=0.115.0
uvicorn>=0.30.0
psutil>=6.0.0
python-dotenv>=1.0.1
chromadb>=0.5.0
openwakeword>=0.6.0
pytest>=8.2.0
pytest-asyncio>=0.23.0
```

**Step 3: Initialize virtual environment**
Run: `uv venv .venv --python 3.11` (or fallback to 3.12/current stable)
Run: `uv pip install -r backend/requirements.txt`

**Step 4: Verify installation**
Run: `.venv\Scripts\python -c "import google.genai, sounddevice, numpy, mss, PIL, websockets, psutil, chromadb; print('Backend environment verified!')"`
Expected output: `Backend environment verified!`

**Step 5: Git commit**
```bash
git add .gitignore backend/requirements.txt ARCHITECTURE.md .antigravity/rules.md
git commit -m "chore: scaffold monorepo and install backend dependencies"
```

---

### Task 2: Audio Device Enumeration & Hardware Verification

**Files:**
* Create: `backend/verify_audio.py`

**Step 1: Write verify_audio.py**
Enumerate input (microphone) and output (speaker/headphones) devices using `sounddevice` and verify 16kHz input / 24kHz output support.

**Step 2: Run verification script**
Run: `.venv\Scripts\python backend/verify_audio.py`
Expected output: Lists default microphone and speaker devices without ALSA/C-runtime exceptions.

**Step 3: Git commit**
```bash
git add backend/verify_audio.py
git commit -m "feat(audio): add audio hardware enumeration script"
```

---

### Task 3: Core Audio Manager with Acoustic Echo Gating

**Files:**
* Create: `backend/audio_manager.py`
* Test: `backend/tests/test_audio_manager.py`

**Step 1: Write failing test in backend/tests/test_audio_manager.py**
Test RMS volume calculation on silent and synthetic PCM audio buffers.

**Step 2: Run test to verify failure**
Run: `.venv\Scripts\pytest backend/tests/test_audio_manager.py -v`
Expected: FAIL (module not found).

**Step 3: Implement backend/audio_manager.py**
* Class `AudioManager`:
  * `mic_queue: asyncio.Queue[bytes]` (16kHz, 16-bit mono PCM).
  * `speaker_queue: asyncio.Queue[bytes]` (24kHz PCM from Gemini).
  * Non-blocking `sounddevice.InputStream` callback pushing to `mic_queue`.
  * Non-blocking `sounddevice.OutputStream` callback playing from `speaker_queue`.
  * `calculate_rms(chunk: bytes) -> float` for HUD volume reactivity.
  * Acoustic echo gate: suppression flag `is_speaking` when `speaker_queue` is actively streaming unless Push-to-Talk is triggered.
  * `drain_speaker_queue()` method for instantaneous barge-in interruption.

**Step 4: Run test to verify pass**
Run: `.venv\Scripts\pytest backend/tests/test_audio_manager.py -v`
Expected: PASS.

**Step 5: Git commit**
```bash
git add backend/audio_manager.py backend/tests/test_audio_manager.py
git commit -m "feat(audio): implement AudioManager with RMS and acoustic gating"
```

---

### Task 4: Vision Manager for Desktop Capture

**Files:**
* Create: `backend/vision_manager.py`
* Test: `backend/tests/test_vision_manager.py`

**Step 1: Write test in backend/tests/test_vision_manager.py**
Verify `capture_screen_jpeg()` returns valid JPEG byte buffer with width <= 1024px.

**Step 2: Run test to verify failure**
Run: `.venv\Scripts\pytest backend/tests/test_vision_manager.py -v`
Expected: FAIL.

**Step 3: Implement backend/vision_manager.py**
* Use `mss` to capture primary monitor bounding box in <15ms.
* Convert raw pixels to `PIL.Image`.
* Downsample proportionally to max width 1024px.
* Compress into JPEG buffer (quality 70) and return raw bytes.

**Step 4: Run test to verify pass**
Run: `.venv\Scripts\pytest backend/tests/test_vision_manager.py -v`
Expected: PASS.

**Step 5: Git commit**
```bash
git add backend/vision_manager.py backend/tests/test_vision_manager.py
git commit -m "feat(vision): implement VisionManager with JPEG compression"
```

---

### Task 5: Memory Store (SQLite Structured Briefings + ChromaDB Vector Store)

**Files:**
* Create: `backend/memory/memory_store.py`
* Test: `backend/tests/test_memory_store.py`

**Step 1: Write tests in backend/tests/test_memory_store.py**
Test SQLite task creation, listing, completion, and ChromaDB fact storage and semantic recall.

**Step 2: Run test to verify failure**
Run: `.venv\Scripts\pytest backend/tests/test_memory_store.py -v`
Expected: FAIL.

**Step 3: Implement backend/memory/memory_store.py**
* Initialize SQLite database `alfred_executive.db` with tables `tasks` and `audit_log`.
* Expose `manage_executive_briefing(action: str, task_item: str)`.
* Initialize local ChromaDB persistent client with collection `alfred_facts`.
* Expose `remember_fact(category: str, content: str)` and `recall_context(query: str) -> list[str]`.

**Step 4: Run test to verify pass**
Run: `.venv\Scripts\pytest backend/tests/test_memory_store.py -v`
Expected: PASS.

**Step 5: Git commit**
```bash
git add backend/memory/memory_store.py backend/tests/test_memory_store.py
git commit -m "feat(memory): implement SQLite task briefings and ChromaDB semantic memory"
```

---

### Task 6: OS Logistics Tools & Safety Interceptor Gate

**Files:**
* Create: `backend/tools/os_logistics.py`
* Test: `backend/tests/test_os_logistics.py`

**Step 1: Write tests in backend/tests/test_os_logistics.py**
Test `get_system_diagnostics()`, safe command vs high-risk command detection.

**Step 2: Run test to verify failure**
Run: `.venv\Scripts\pytest backend/tests/test_os_logistics.py -v`
Expected: FAIL.

**Step 3: Implement backend/tools/os_logistics.py**
* `get_system_diagnostics() -> dict`: CPU, RAM, disk, battery, top 5 processes.
* `launch_application_or_url(target: str) -> str`: Safe application/web URL launch.
* `execute_terminal_command(command: str) -> str`: Checks against risk rules (destructive commands, file deletion, process kills). If high risk, pauses execution, creates an `asyncio.Future`, and invokes HUD approval hook awaiting response with `asyncio.wait_for(future, timeout=30.0)`. If the 30-second window elapses without human authorization, the command automatically aborts and notifies Gemini Live without hanging the connection. Safe read-only commands execute directly via `subprocess.run`.

**Step 4: Run test to verify pass**
Run: `.venv\Scripts\pytest backend/tests/test_os_logistics.py -v`
Expected: PASS.

**Step 5: Git commit**
```bash
git add backend/tools/os_logistics.py backend/tests/test_os_logistics.py
git commit -m "feat(tools): implement OS logistics tools and non-hanging shell safety gate"
```

---

### Task 7: Gemini Multimodal Live API Session & Interruption Core

**Files:**
* Create: `backend/live_session.py`
* Test: `backend/tests/test_live_session_config.py`

**Step 1: Write test for configuration and prompt structure**
Ensure `types.LiveConnectConfig` properly binds tools and sets `ALFRED_SYSTEM_PROMPT`.

**Step 2: Implement backend/live_session.py**
* Class `AlfredLiveCore`:
  * Initialize `genai.Client(api_key=...)`.
  * Set model to `gemini-2.5-flash` with audio modality (`types.LiveModality.AUDIO`).
  * Run concurrent async tasks:
    * `send_mic_audio(session)`: Streams 16kHz PCM chunks to Gemini.
    * `receive_model_stream(session)`: Receives 24kHz PCM chunks, handles `server_content.interrupted` by immediately clearing `speaker_queue`, and executes function calls.
    * `send_screen_frame(session)`: Sends 1024px JPEG frame when requested.

**Step 3: Run test**
Run: `.venv\Scripts\pytest backend/tests/test_live_session_config.py -v`
Expected: PASS.

**Step 4: Git commit**
```bash
git add backend/live_session.py backend/tests/test_live_session_config.py
git commit -m "feat(live): implement AlfredLiveCore with Gemini Live API and barge-in"
```

---

### Task 8: Backend Main WebSocket Hub Coordinator & Telemetry Caching

**Files:**
* Create: `backend/main.py`
* Test: `backend/tests/test_main_ws.py`

**Step 1: Write test for WebSocket handshake and state broadcast**
Verify connection to `ws://localhost:8765` receives `{ type: "state" }` telemetry packet including `active_tool: str|null`.

**Step 2: Implement backend/main.py**
* Asynchronous WebSocket server using `FastAPI` / `uvicorn` and `websockets`.
* Broadcasts HUD telemetry:
  * Cache `psutil` CPU/RAM metrics on a 2.0-second interval to minimize CPU overhead.
  * Stream audio `rms_volume` at 15–20Hz for fluid HUD visualizer response.
  * Broadcast state transitions (`idle`, `listening`, `thinking`, `speaking`) and `active_tool: str|null`.
* Receives HUD actions: approval responses, PTT hotkey events, screen triggers.
* Coordinates `AudioManager`, `VisionManager`, `MemoryStore`, and `AlfredLiveCore`.

**Step 3: Run test**
Run: `.venv\Scripts\pytest backend/tests/test_main_ws.py -v`
Expected: PASS.

**Step 4: Git commit**
```bash
git add backend/main.py backend/tests/test_main_ws.py
git commit -m "feat(hub): implement WebSocket coordinator on port 8765 with cached telemetry"
```

---

### Task 9: Initialize HUD with Vite, React 19, Tailwind CSS & Three.js

**Files:**
* Directory: `hud/`
* Create: `hud/package.json`
* Create: `hud/vite.config.ts`
* Create: `hud/tailwind.config.js` or Tailwind v4 setup

**Step 1: Scaffold Vite React TypeScript app**
Run: `npm create vite@latest hud -- --template react-ts`
Install dependencies: `cd hud && npm install tailwindcss lucide-react three @types/three`

**Step 2: Verify Vite dev server build**
Run: `npm run build`
Expected: Successfully generates `dist/`.

**Step 3: Git commit**
```bash
git add hud/
git commit -m "chore(hud): scaffold React 19 + TypeScript + Tailwind Vite application"
```

---

### Task 10: Electron Desktop Wrapper, Global Shortcuts & Click-Through Window

**Files:**
* Create: `hud/electron/main.ts`
* Create: `hud/electron/preload.ts`
* Modify: `hud/package.json` (add Electron dev scripts)

**Step 1: Implement hud/electron/main.ts**
* `BrowserWindow` with `transparent: true`, `frame: false`, `alwaysOnTop: true`, `hasShadow: false`.
* Register `win.setIgnoreMouseEvents(true, { forward: true })` by default.
* IPC handler: `set-ignore-mouse-events` toggles mouse forwarding when pointer enters HUD panels or modal.
* Register global hotkey via Electron's `globalShortcut.register('CommandOrControl+Space', ...)` so Push-to-Talk works even when the transparent HUD has `setIgnoreMouseEvents(true)` and lacks native window focus.

**Step 2: Implement hud/electron/preload.ts**
* Expose safe IPC bindings to `window.alfredElectron` (`setIgnoreMouse(ignore: boolean)`, `onPttEvent(callback)`).

**Step 3: Test Electron window launch**
Run: `npm run electron:dev`
Expected: Transparent frameless window renders over Windows desktop.

**Step 4: Git commit**
```bash
git add hud/electron/
git commit -m "feat(hud): implement Electron frameless transparent window with globalShortcut PTT"
```

---

### Task 11: Vanilla Three.js Gyroscopic Audio Orb & Telemetry HUD Components

**Files:**
* Create: `hud/src/hooks/useAlfredWs.ts`
* Create: `hud/src/components/AudioOrb.tsx`
* Create: `hud/src/components/TelemetryBar.tsx`
* Create: `hud/src/components/TranscriptDrawer.tsx`
* Create: `hud/src/components/ApprovalModal.tsx`
* Modify: `hud/src/App.tsx`

**Step 1: Implement hooks/useAlfredWs.ts**
Maintains connection to `ws://localhost:8765`, auto-reconnects on drop, parses state packets with `active_tool`, and provides helper functions to send approvals.

**Step 2: Implement components/AudioOrb.tsx using Vanilla Three.js**
* Built using direct `<canvas ref={canvasRef} />` and vanilla `three` (strictly avoiding `@react-three/fiber` to eliminate React 19 peer dependency conflicts).
* Multi-ring gyroscopic particle sphere:
  * Cyan (`#06b6d4`) on Idle/Listening.
  * Amber/Gold (`#f59e0b`) on Thinking/Executing.
  * Emerald (`#10b981`) on Speaking.
* Scale rotation speed and particle pulse dynamically with high-frequency `rms_volume`.

**Step 3: Implement TelemetryBar & ApprovalModal**
* Real-time CPU & RAM gauges.
* Approval Modal with high-contrast warning, command display, and keyboard shortcut listeners (`Enter` / `Esc`).

**Step 4: Build and test UI**
Run: `npm run build`
Expected: Pass without TypeScript errors.

**Step 5: Git commit**
```bash
git add hud/src/
git commit -m "feat(hud): build Three.js AudioOrb, telemetry gauges, and approval modal"
```

---

### Task 12: Full-Stack Integration, Single-Click Launcher & Smoke Test

**Files:**
* Create: `start_alfred.bat` (Windows single-click runner)
* Create: `start_alfred.sh` (POSIX runner)
* Create: `backend/tests/smoke_test.py`

**Step 1: Create start_alfred.bat**
Script that:
1. Validates `.env` and `.venv`.
2. Starts Python backend (`main.py`) in background.
3. Launches Electron HUD concurrently.
4. Handles clean shutdown on exit.

**Step 2: Execute end-to-end smoke test**
Run: `.venv\Scripts\python backend/tests/smoke_test.py`
Verify:
* WebSocket server binds to `ws://localhost:8765`.
* Audio queues initialize.
* Diagnostics tools return live metrics.
* Approval gate halts destructive commands.

**Step 3: Git commit**
```bash
git add start_alfred.bat start_alfred.sh backend/tests/smoke_test.py
git commit -m "feat(integration): create single-click launcher and end-to-end smoke test"
```
