# ARCHITECTURE.md — A.L.F.R.E.D. Master Specification
**A.L.F.R.E.D.** (*Autonomous Logistics Functional Response & Executive Director*)  
*A real-time multimodal desktop AI assistant blending Bruce Wayne's Pennyworth persona with Stark-level HUD telemetry.*

---

## 1. System Overview & Understanding Summary

* **Role & Identity**: Impeccably articulate, composed, dryly witty British executive director addressing the user as "Sir" or "Director". Spoken responses are concise (1–3 sentences) unless an in-depth briefing is requested.
* **Core Capabilities**: Real-time bidirectional voice (sub-second streaming), on-demand high-resolution screen vision, system telemetry monitoring, local structured and semantic memory, and safe OS tool execution.
* **Architecture Pattern**: Decoupled Monorepo with an Asynchronous IPC WebSocket Hub (`/backend`) driving a frameless, transparent Electron overlay HUD (`/hud`).

---

## 2. Decision Log

| # | Decision | Alternatives Considered | Rationale |
| :--- | :--- | :--- | :--- |
| **D1** | **Native Desktop Overlay (Electron)** | Browser Web App only | Enables transparent, always-on-top positioning, global hotkeys, and mouse forwarding without obstructing background desktop workflows. |
| **D2** | **Modular Async IPC Hub over WebSocket** | Electron Stdio Child Process, Direct Browser Gemini Live | Clean separation of concerns between OS/C-libraries (`sounddevice`, ONNX, `psutil`, `fastapi`/`uvicorn`) and UI rendering; enables modular, headless testing. |
| **D3** | **Hybrid Audio Trigger & Global Hotkey** | Wake-word only, Push-to-Talk only | Push-to-Talk (`Ctrl+Space`) registered via Electron `globalShortcut` ensures input works even when transparent HUD lacks window focus; local wake-word (`openwakeword`) provides hands-free activation. |
| **D4** | **On-Demand Vision Streaming** | Continuous 1 FPS stream | Prevents network and WebSocket saturation while eliminating unnecessary token consumption; captures 1024px JPEG snapshots when requested. |
| **D5** | **Non-Hanging Gated Shell Execution** | Unchecked terminal execution, Infinite wait | Destructive commands (`rm`, `del`, `taskkill`, `git push`) require explicit human confirmation via HUD modal, backed by a 30-second timeout (`asyncio.wait_for`) to prevent Gemini Live session hangs. |
| **D6** | **Vanilla Three.js Visualizer** | @react-three/fiber | Uses direct canvas `useRef` with vanilla `three` to ensure zero React 19 peer dependency errors while keeping frame rates locked at 60 FPS. |

---

## 3. Assumptions & Risk Mitigations

1. **Python Environment Stability**: Pinned to Python 3.11/3.12 managed via `uv` to ensure 100% pre-built binary wheel compatibility for `sounddevice`, `numpy`, `openwakeword` ONNX runtime, and `chromadb` on Windows.
2. **Audio Feedback & Echo Elimination**: An acoustic gate automatically mutes microphone streaming while the speaker output queue is actively playing unless the user presses Push-to-Talk (`Ctrl+Space`) or exceeds an interruption threshold.
3. **Global Push-to-Talk Hotkey**: Because the transparent HUD runs with `win.setIgnoreMouseEvents(true, { forward: true })`, it will not hold native OS window focus. Push-to-Talk is registered via Electron's `globalShortcut.register('CommandOrControl+Space', ...)` and dispatched over WebSocket.
4. **Non-Hanging Approval Gate**: Awaiting user authorization uses `asyncio.wait_for(future, timeout=30.0)`. If the user does not respond within 30 seconds, the action is automatically aborted and reported back to Gemini Live without stalling the connection.
5. **HUD Telemetry Performance**: System CPU and RAM metrics via `psutil` are polled and cached on a 2.0-second interval, while audio `rms_volume` streams at a high frequency (15–20Hz) for fluid visualizer response.
6. **Bandwidth Preservation**: High-resolution screen captures are downsampled to 1024px with 70% JPEG quality (~100KB), completing transmission in under 50ms.

---

## 4. Directory Structure

```
alfred-executive-core/
├── .env                       # Environment variables (GEMINI_API_KEY, ALFRED_WS_PORT, ALFRED_VOICE_NAME)
├── ARCHITECTURE.md            # Master technical specification (this file)
├── .antigravity/rules.md      # Safety rules and SDK policies
├── backend/                   # Python 3.11+ asyncio service
│   ├── pyproject.toml / reqs  # google-genai, sounddevice, numpy, mss, Pillow, psutil, chromadb, openwakeword, fastapi, uvicorn
│   ├── main.py                # FastAPI / WebSocket server & hub coordinator (ws://localhost:8765)
│   ├── audio_manager.py       # sounddevice 16kHz capture, 24kHz playback, RMS calculation
│   ├── vision_manager.py      # mss monitor capture, JPEG resize & encoding
│   ├── live_session.py        # google-genai Live API WebSocket client, audio loop & barge-in
│   ├── wake_word.py           # openwakeword ONNX listener + Push-to-Talk trigger handler
│   ├── memory/
│   │   └── memory_store.py    # alfred_executive.db (SQLite) + local ChromaDB vector client
│   ├── tools/
│   │   └── os_logistics.py    # psutil diagnostics, app launcher, gated shell runner (30s timeout)
│   └── tests/
│       ├── test_audio_manager.py
│       ├── test_os_logistics.py
│       └── test_tools.py      # Pytest validation suite for tools and memory
├── hud/                       # Electron + React 19 + Vite + Tailwind CSS + Three.js
│   ├── electron/
│   │   ├── main.ts            # Frameless, transparent window, globalShortcut, and click-through
│   │   └── preload.ts         # Secure IPC bridge
│   ├── src/
│   │   ├── components/        # AudioOrb (vanilla Three.js), TelemetryBar, ApprovalModal, Transcript
│   │   ├── hooks/useAlfredWs.ts # WebSocket state sync & reconnect logic
│   │   └── App.tsx            # Dark glassmorphic layout
│   └── package.json
└── start_alfred.bat           # Windows single-click launcher activating venv + launching HUD
```

---

## 5. Telemetry & Data Contracts

### Local WebSocket (`ws://localhost:8765`)

#### Backend ➔ HUD (`type: "state"`)
```json
{
  "type": "state",
  "status": "idle" | "listening" | "thinking" | "speaking",
  "rms_volume": 0.048,
  "cpu": 14.2,
  "ram": 48.6,
  "transcript": "Good afternoon, Sir. All telemetry systems are operational.",
  "active_tool": "get_system_diagnostics" | null,
  "pending_approval": {
    "id": "req-9410",
    "action": "execute_terminal_command",
    "command": "git push origin main",
    "risk_level": "high"
  } | null
}
```

#### HUD ➔ Backend
* **Approval Modal Response**: `{"type": "approval_response", "id": "req-9410", "approved": true}`
* **Push-to-Talk Event**: `{"type": "ptt_event", "state": "down" | "up"}`
* **Screen Trigger**: `{"type": "inspect_screen_trigger"}`

---

## 6. Phase-by-Phase Implementation Roadmap

1. **Phase 1: Workspace Anchoring & Master Blueprint**
   * Write `ARCHITECTURE.md` and `.antigravity/rules.md`.
   * Initialize Python 3.11/3.12 `.venv` via `uv` and configure dependencies.
2. **Phase 2: Multimodal Backend Core & Audio Loop**
   * Build `audio_manager.py`, `vision_manager.py`, and `live_session.py`.
   * Implement acoustic gating, RMS volume calculation, and sub-second barge-in.
   * Run hardware device enumeration verification test.
3. **Phase 3: OS Logistics Tools, Memory & Test Suite**
   * Build `memory/memory_store.py` (SQLite + ChromaDB) and `tools/os_logistics.py`.
   * Implement high-risk shell safety gate with WebSocket hold.
   * Verify all tools with automated `pytest` suite.
4. **Phase 4: Executive HUD Desktop Widget**
   * Initialize `/hud` with Vite, React 19, Tailwind CSS, and Three.js.
   * Wrap with Electron for frameless transparency and mouse click-through forwarding.
   * Build 3D gyroscopic `AudioOrb`, telemetry gauges, and approval modal.
5. **Phase 5: Full-Stack Integration & Verification**
   * Wire `/backend/main.py` WebSocket coordinator with Live API session.
   * Create `start_alfred.bat` single-click launcher and perform end-to-end smoke test.
