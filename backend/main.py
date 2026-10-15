"""A.L.F.R.E.D. Main Hub Coordinator & WebSocket Telemetry Server.

Runs the asynchronous event loop on ws://localhost:8765, serving:
- High-frequency (15-20Hz) audio amplitude and state broadcasts to the Electron HUD.
- Low-frequency (2.0s cached) psutil CPU/RAM metrics to prevent CPU overhead.
- Bidirectional dispatch of HUD approvals, PTT hotkeys, and manual vision triggers.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from contextlib import asynccontextmanager
from typing import Optional, Set
from dotenv import load_dotenv
import psutil
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse
import uvicorn

from backend.audio_manager import AudioManager
from backend.vision_manager import VisionManager
from backend.memory.memory_store import MemoryStore
from backend.tools.os_logistics import OSLogistics
from backend.live_session import AlfredLiveCore

load_dotenv()
logger = logging.getLogger("AlfredMain")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manages coordinator lifecycle on server startup and shutdown."""
    await hub.start(start_live_session=bool(os.environ.get("GEMINI_API_KEY")))
    yield
    await hub.stop()


app = FastAPI(title="A.L.F.R.E.D. Executive Core", version="1.0.0", lifespan=lifespan)


class AlfredHubCoordinator:
    """Coordinates backend audio, vision, logistics, Live API, and HUD WebSocket telemetry."""

    def __init__(
        self,
        port: int = 8765,
        memory_store: Optional[MemoryStore] = None,
        audio_manager: Optional[AudioManager] = None,
        vision_manager: Optional[VisionManager] = None,
    ) -> None:
        self.port = port
        self.connected_clients: Set[WebSocket] = set()
        self._lock = asyncio.Lock()

        # Telemetry Cache
        self.cached_cpu: float = 0.0
        self.cached_ram: float = 0.0
        self.current_transcript: str = "A.L.F.R.E.D. core initialized. Systems nominal."
        self.pending_approval: Optional[dict] = None

        # Core Components
        self.memory = memory_store or MemoryStore()
        self.audio = audio_manager or AudioManager()
        self.vision = vision_manager or VisionManager()

        # OS Logistics Tools with approval hook
        self.logistics = OSLogistics(
            memory_store=self.memory,
            vision_manager=self.vision,
            approval_hook=self.handle_pending_approval,
            approval_timeout=30.0,
        )

        # List of tools to register with Gemini Live API
        self.tools_list = [
            self.logistics.get_system_diagnostics,
            self.logistics.launch_application_or_url,
            self.logistics.inspect_active_screen,
            self.logistics.manage_executive_briefing,
            self.logistics.remember_fact,
            self.logistics.recall_context,
            self.logistics.execute_terminal_command,
        ]

        # Gemini Live Core
        self.live_core = AlfredLiveCore(
            tools_list=self.tools_list,
            audio_manager=self.audio,
            vision_manager=self.vision,
            on_status_change=self.on_status_change,
            on_active_tool_change=self.on_active_tool_change,
            on_transcript=self.on_transcript_update,
        )

        # Background task references
        self._metrics_task: Optional[asyncio.Task] = None
        self._broadcast_task: Optional[asyncio.Task] = None
        self._live_task: Optional[asyncio.Task] = None
        self.is_running: bool = False

    async def handle_pending_approval(self, payload: dict) -> None:
        """Callback invoked by OSLogistics when a high-risk command requires HUD approval."""
        self.pending_approval = payload
        await self.broadcast_state_packet()

    def on_status_change(self, new_status: str) -> None:
        """Called when Live session status changes."""
        logger.debug("State changed: %s", new_status)

    def on_active_tool_change(self, tool_name: Optional[str]) -> None:
        """Called when tool starts or finishes."""
        logger.debug("Active tool: %s", tool_name)

    def on_transcript_update(self, text: str) -> None:
        """Updates scrolling transcript."""
        self.current_transcript = text

    def get_state_payload(self) -> dict:
        """Assembles the current HUD state JSON packet."""
        return {
            "type": "state",
            "status": self.live_core.status,
            "rms_volume": self.audio.current_mic_rms,
            "cpu": self.cached_cpu,
            "ram": self.cached_ram,
            "transcript": self.current_transcript,
            "active_tool": self.live_core.active_tool,
            "pending_approval": self.pending_approval,
        }

    async def broadcast_state_packet(self) -> None:
        """Sends the latest state packet to all connected HUD clients."""
        if not self.connected_clients:
            return

        payload = self.get_state_payload()
        message = json.dumps(payload)

        disconnected = set()
        for client in self.connected_clients:
            try:
                await client.send_text(message)
            except Exception:
                disconnected.add(client)

        if disconnected:
            async with self._lock:
                self.connected_clients.difference_update(disconnected)

    async def _metrics_polling_loop(self) -> None:
        """Polls psutil metrics every 2.0 seconds to eliminate CPU polling overhead."""
        while self.is_running:
            try:
                self.cached_cpu = round(psutil.cpu_percent(interval=None), 1)
                self.cached_ram = round(psutil.virtual_memory().percent, 1)
                await asyncio.sleep(2.0)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.warning("Error in metrics polling: %s", e)
                await asyncio.sleep(2.0)

    async def _broadcast_loop(self) -> None:
        """Broadcasts telemetry to HUD at 20Hz (every 50ms) for high-framerate visualizer response."""
        while self.is_running:
            try:
                await self.broadcast_state_packet()
                await asyncio.sleep(0.05)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("Error in telemetry broadcast loop: %s", e)
                await asyncio.sleep(0.05)

    async def handle_hud_message(self, message_data: dict) -> None:
        """Routes inbound commands from the Electron HUD."""
        msg_type = message_data.get("type", "")

        if msg_type == "approval_response":
            req_id = message_data.get("id", "")
            approved = message_data.get("approved", False)
            resolved = self.logistics.resolve_approval(req_id, approved)
            logger.info("Approval resolved for %s: %s (result: %s)", req_id, approved, resolved)
            self.pending_approval = None
            await self.broadcast_state_packet()

        elif msg_type == "ptt_event":
            state = message_data.get("state")
            pressed = (state == "down") or message_data.get("pressed", False)
            self.audio.set_push_to_talk(pressed)
            logger.debug("Push-to-Talk set: %s", pressed)

        elif msg_type == "inspect_screen_trigger":
            logger.info("Manual inspect screen triggered from HUD.")
            if self.live_core._session:
                jpeg_bytes = self.vision.capture_screen_jpeg()
                await self.live_core._session.send(
                    input={"data": jpeg_bytes, "mime_type": "image/jpeg"},
                    end_of_turn=False,
                )

    async def start(self, start_live_session: bool = True) -> None:
        """Starts background workers and optionally connects to Gemini Live API."""
        if self.is_running:
            return

        self.is_running = True
        self._metrics_task = asyncio.create_task(self._metrics_polling_loop())
        self._broadcast_task = asyncio.create_task(self._broadcast_loop())

        if start_live_session and os.environ.get("GEMINI_API_KEY"):
            self._live_task = asyncio.create_task(self.live_core.start())

        logger.info("[A.L.F.R.E.D. HUB] Coordinator started on port %s", self.port)

    async def stop(self) -> None:
        """Gracefully shuts down all workers and connections."""
        self.is_running = False

        if self._metrics_task:
            self._metrics_task.cancel()
        if self._broadcast_task:
            self._broadcast_task.cancel()
        if self._live_task:
            self._live_task.cancel()

        await self.live_core.stop()
        self.memory.close()


# Global Hub Coordinator Instance
hub = AlfredHubCoordinator(port=int(os.environ.get("ALFRED_WS_PORT", 8765)))


@app.get("/health")
async def health_check():
    return JSONResponse({
        "status": "online",
        "service": "A.L.F.R.E.D. Executive Core",
        "telemetry": hub.get_state_payload(),
    })


@app.websocket("/")
@app.websocket("/hud")
async def websocket_hud_endpoint(websocket: WebSocket):
    """WebSocket endpoint connecting the Electron transparent HUD overlay."""
    await websocket.accept()
    async with hub._lock:
        hub.connected_clients.add(websocket)

    # Send initial state packet immediately upon connection
    await websocket.send_text(json.dumps(hub.get_state_payload()))
    logger.info("HUD client connected from %s. Active clients: %d", websocket.client, len(hub.connected_clients))

    try:
        while True:
            text = await websocket.receive_text()
            try:
                data = json.loads(text)
                await hub.handle_hud_message(data)
            except json.JSONDecodeError:
                logger.warning("Received invalid JSON from HUD: %s", text)
    except WebSocketDisconnect:
        logger.info("HUD client disconnected.")
    finally:
        async with hub._lock:
            hub.connected_clients.discard(websocket)


def run_server():
    """Runs the uvicorn server."""
    port = int(os.environ.get("ALFRED_WS_PORT", 8765))
    uvicorn.run("backend.main:app", host="127.0.0.1", port=port, log_level="info")


if __name__ == "__main__":
    run_server()
