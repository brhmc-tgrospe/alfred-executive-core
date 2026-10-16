# A.L.F.R.E.D. Project Guardrails & System Rules

## 1. Unified Google GenAI SDK Rule
* **MANDATORY**: Always use the modern `google-genai` Python SDK (`from google import genai`, `from google.genai import types`).
* **STRICT PROHIBITION**: NEVER use or import the legacy, deprecated `google-generativeai` package.

## 2. Monorepo Architecture
* `/backend`: Python 3.11+ asyncio server handling real-time audio, vision, memory, and OS logistics.
* `/hud`: Electron + React 19 + Vite + Tailwind CSS + Three.js transparent desktop overlay.

## 3. Communication & Port Contracts
* The backend exposes a WebSocket server on `ws://localhost:8765`.
* Telemetry format MUST adhere to the schema defined in `ARCHITECTURE.md`:
  `{"type": "state", "status": "idle|listening|thinking|speaking", "rms_volume": float, "cpu": float, "ram": float, "transcript": str, "active_tool": str|null, "pending_approval": dict|null}`.

## 4. Executive Safety Guardrail (Human-in-the-Loop)
* Any tool execution that modifies or deletes files, kills processes, alters system configuration, or pushes code to remote repositories MUST NOT execute immediately.
* It must send a `pending_approval` payload over the WebSocket and await an `asyncio.Future` with a 30-second timeout (`asyncio.wait_for`) to ensure the Gemini Live API session never permanently hangs if the user steps away.

## 5. Stable Dependencies
* Always pin and install stable releases of all libraries.
* Do not introduce experimental pre-releases or release candidates.

## 6. GitHub Account Configuration
* Whenever pushing or syncing changes to GitHub, always use the `brhmc-tgrospe` account for this project.

## 7. Mandatory Skill Invocation Rule
* For all development, architecture, and debugging tasks in this workspace, agents MUST proactively load and apply the relevant skills from our agentic-awesome-skills library—specifically `/systematic-debugging`, `/debugging-toolkit`, `/verification-before-completion`, `/test-driven-development`, `/python-pro`, `/fastapi-pro`, `/react-best-practices`, `/typescript-expert`, and `/browser-automation`.

