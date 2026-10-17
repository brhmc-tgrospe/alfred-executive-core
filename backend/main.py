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
import sys
import subprocess
import time
from contextlib import asynccontextmanager
import ctypes
from typing import Optional, Set
from dotenv import load_dotenv
import psutil
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse
import uvicorn

class POINT(ctypes.Structure):
    _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]

def get_cursor_position() -> tuple[int, int]:
    """Retrieves hardware OS mouse coordinates via Win32 GetCursorPos with pyautogui fallback."""
    if hasattr(ctypes, "windll") and sys.platform.startswith("win"):
        try:
            pt = POINT()
            if ctypes.windll.user32.GetCursorPos(ctypes.byref(pt)):
                return int(pt.x), int(pt.y)
        except Exception:
            pass
    try:
        import pyautogui
        pos = pyautogui.position()
        return int(pos.x), int(pos.y)
    except Exception:
        return 0, 0

from backend.audio_manager import AudioManager
from backend.vision_manager import VisionManager
from backend.memory.memory_store import MemoryStore, get_utc8_now_str
from backend.tools.os_logistics import OSLogistics
from backend.tools.dev_logistics import DevLogistics
from backend.tools.gui_automation import GuiAutomationLogistics
from backend.tools.browser_automation import BrowserAutomationLogistics
from backend.tools.game_interaction import GameInteractionLogistics
from backend.tools.meeting_biometrics import MeetingBiometricsLogistics, get_utc8_timestamp
from backend.live_session import AlfredLiveCore, is_shutdown_authorized, is_stop_command

load_dotenv()
logger = logging.getLogger("AlfredMain")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manages coordinator lifecycle on server startup and shutdown."""
    is_testing = "PYTEST_CURRENT_TEST" in os.environ or "pytest" in sys.modules
    if not is_testing:
        # Explicitly invoke audio_manager.start() for physical microphone
        await hub.audio_manager.start()
        # Spawn live_session.run_executive_loop() if API key is present
        if os.environ.get("GEMINI_API_KEY"):
            hub._live_task = asyncio.create_task(hub.live_session.run_executive_loop())

    await hub.start(start_live_session=False if is_testing else bool(os.environ.get("GEMINI_API_KEY")))
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
        self.cached_ping: float = 0.0
        self.current_transcript: str = "A.L.F.R.E.D. core initialized. Systems nominal."
        self.pending_approval: Optional[dict] = None

        # Core Components
        self.memory = memory_store or MemoryStore()
        self.audio = audio_manager or AudioManager()
        self.vision = vision_manager or VisionManager(memory_store=self.memory)
        if not getattr(self.vision, "memory", None):
            self.vision.memory = self.memory

        # OS Logistics Tools with approval hook
        self.logistics = OSLogistics(
            memory_store=self.memory,
            vision_manager=self.vision,
            approval_hook=self.handle_pending_approval,
            approval_timeout=30.0,
        )

        # Developer Logistics Tools
        self.dev_logistics = DevLogistics()

        # GUI Automation Logistics Tools
        self.gui_logistics = GuiAutomationLogistics(memory_store=self.memory)
        if not getattr(self.gui_logistics, "memory", None):
            self.gui_logistics.memory = self.memory

        # Browser Automation Logistics Tools
        self.browser_logistics = BrowserAutomationLogistics()

        # Game Interaction Logistics Tools
        self.game_logistics = GameInteractionLogistics()

        # Meeting Biometrics Logistics Tools
        self.meeting_logistics = MeetingBiometricsLogistics(audio_manager=self.audio)

        # List of tools to register with Gemini Live API (30 total tools)
        self.tools_list = [
            self.logistics.get_system_diagnostics,
            self.logistics.launch_application_or_url,
            self.logistics.inspect_active_screen,
            self.logistics.manage_executive_briefing,
            self.logistics.manage_semantic_memory,
            self.logistics.execute_terminal_command,
            self.logistics.deep_os_file_executive,
            self.logistics.terminate_executive_commands,
            self.dev_logistics.inspect_git_workspace,
            self.dev_logistics.inspect_local_dev_ports,
            self.logistics.get_weather_briefing,
            self.dev_logistics.tail_log_file,
            self.dev_logistics.audit_source_file,
            self.dev_logistics.inspect_sqlite_database,
            self.dev_logistics.multi_target_network_sweep,
            self.dev_logistics.research_software_interface_and_docs,
            self.memory.inspect_learned_habits_and_growth,
            self.gui_logistics.type_into_application,
            self.gui_logistics.write_live_word_document,
            self.gui_logistics.visual_code_edit,
            self.gui_logistics.send_keyboard_shortcut,
            self.gui_logistics.screen_pixel_navigation,
            self.gui_logistics.manage_desktop_window,
            self.browser_logistics.browser_navigate_and_parse_dom,
            self.browser_logistics.browser_interact_dom_element,
            self.game_logistics.observe_game_state,
            self.game_logistics.evaluate_tactical_game_policy,
            self.game_logistics.send_game_input_action,
            self.meeting_logistics.enroll_or_identify_speaker,
            self.meeting_logistics.manage_meeting_transcription,
        ]

        # Gemini Live Core
        self.live_core = AlfredLiveCore(
            tools_list=self.tools_list,
            audio_manager=self.audio,
            vision_manager=self.vision,
            memory_store=self.memory,
            dev_logistics=self.dev_logistics,
            gui_logistics=self.gui_logistics,
            browser_logistics=self.browser_logistics,
            game_logistics=self.game_logistics,
            meeting_logistics=self.meeting_logistics,
            on_status_change=self.on_status_change,
            on_active_tool_change=self.on_active_tool_change,
            on_transcript=self.on_transcript_update,
            on_thinking_timeout=self._execute_fallback_prompt,
        )

        # Track last user utterance across coordinator and logistics
        self.last_user_utterance: str = ""
        self.os_logistics = self.logistics

        # Connect graceful shutdown and abort hooks
        self.logistics.set_abort_callback(self.abort_current_operations)
        self.logistics.set_shutdown_callback(self.trigger_graceful_shutdown)
        self.live_core.set_shutdown_callback(self.trigger_graceful_shutdown)
        self.live_core.on_abort_operations = self.broadcast_state_packet
        self.live_core.on_user_utterance = self.on_user_utterance

        # Direct aliases for clear architectural access
        self.audio_manager = self.audio
        self.live_session = self.live_core

        # Background task references
        self._metrics_task: Optional[asyncio.Task] = None
        self._broadcast_task: Optional[asyncio.Task] = None
        self._live_task: Optional[asyncio.Task] = None
        self._pulse_task: Optional[asyncio.Task] = None
        self._fallback_task: Optional[asyncio.Task] = None
        self.simulated_rms: float = 0.0
        self.cached_devices = self.audio.list_input_devices()
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
        """Updates scrolling transcript with strict UTC+8 timestamp prefix."""
        if not text.startswith("[") or "UTC+8" not in text[:25]:
            text = f"{get_utc8_timestamp(full=False)} {text}"
        self.current_transcript = text

    def get_state_payload(self) -> dict:
        """Assembles the current HUD state JSON packet with perceptual mic level and speaker RMS."""
        visual_mic = getattr(self.audio, "visual_mic_level", 0.0)
        speaker_rms = getattr(self.audio, "current_speaker_rms", 0.0)

        # In listening/idle mode, map visual_mic_level to rms_volume so 3D AudioOrb pulses visibly when user speaks
        if self.live_core.status in ("listening", "idle"):
            effective_rms = max(visual_mic, self.simulated_rms)
        elif self.live_core.status == "speaking":
            effective_rms = max(speaker_rms, self.audio.current_mic_rms, self.simulated_rms)
        else:
            effective_rms = max(self.audio.current_mic_rms, self.simulated_rms)

        mx, my = get_cursor_position()

        return {
            "type": "state",
            "status": self.live_core.status,
            "rms_volume": effective_rms,
            "mic_level": visual_mic,
            "cpu": self.cached_cpu,
            "ram": self.cached_ram,
            "ping_ms": self.cached_ping,
            "mouse_x": mx,
            "mouse_y": my,
            "transcript": self.current_transcript,
            "active_tool": self.live_core.active_tool,
            "pending_approval": self.pending_approval,
            "input_devices": self.cached_devices,
            "current_device_id": getattr(self.audio, "current_device_id", None),
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

    def on_user_utterance(self, text: str) -> None:
        """Tracks latest user utterance across coordinator, live core, and os logistics."""
        self.last_user_utterance = text
        self.live_core.last_user_utterance = text
        self.logistics.set_last_user_utterance(text)

    def abort_current_operations(self) -> str:
        """Instantly halts audio playback, background overwatch, and returns HUD to listening state."""
        logger.info("[COORDINATOR] Aborting active operations on Director command.")
        self.audio.clear_playback()
        ack = self.live_core.abort_current_operations()
        self.current_transcript = f"{get_utc8_timestamp(full=False)} {ack}"
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(self.broadcast_state_packet())
        except RuntimeError:
            pass
        return ack

    def trigger_graceful_shutdown(self, farewell_message: str = "Terminating all executive commands now, Director Qadir. Standing down, Sir.") -> bool:
        """Shared graceful shutdown trigger wired across live_core, logistics, and coordinator."""
        if self.last_user_utterance and not is_shutdown_authorized(self.last_user_utterance):
            logger.warning("[COORDINATOR] Blocked trigger_graceful_shutdown: last utterance '%s' is not authorized", self.last_user_utterance)
            self.abort_current_operations()
            return False
        self.schedule_shutdown(farewell_message)
        return True

    def schedule_shutdown(self, farewell_message: str = "Terminating all executive commands now, Director Qadir. Standing down, Sir.") -> None:
        """Schedules non-blocking graceful executive shutdown sequence."""
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(self.execute_system_shutdown(farewell_message))
        except RuntimeError:
            pass

    async def execute_system_shutdown(self, farewell_message: str = "Terminating all executive commands now, Director Qadir. Standing down, Sir.") -> None:
        """Broadcasts system_shutdown to Electron HUD and exits Python process cleanly after audio playback drains."""
        logger.warning("[COORDINATOR] System shutdown sequence engaged: %s", farewell_message)
        if farewell_message:
            self.on_transcript_update(farewell_message)
            self.live_core.set_status("speaking")
            await self.broadcast_state_packet()

        # Wait up to 1.5s for farewell speech chunks to begin arriving in playback buffer
        for _ in range(15):
            if self.audio.is_playback_active():
                break
            await asyncio.sleep(0.1)

        # Wait for audio playback buffer to drain completely
        try:
            await self.audio.wait_for_playback_drain(timeout=6.0)
        except Exception as e:
            logger.warning("[COORDINATOR] Audio playback drain error during shutdown: %s", e)

        # Broadcast shutdown event to WebSocket clients (Electron HUD)
        await self.broadcast_shutdown(reason="Director Qadir termination command")
        await asyncio.sleep(0.4)

        # Forcefully terminate Electron overlay process if running on Windows
        if sys.platform.startswith("win"):
            try:
                subprocess.run(["taskkill", "/F", "/IM", "electron.exe"], capture_output=True)
            except Exception as e:
                logger.debug("taskkill electron error: %s", e)

        # Stop audio hardware streams
        try:
            await self.audio.stop()
        except Exception:
            pass

        self.is_running = False
        asyncio.create_task(self._delayed_exit())

    async def _delayed_exit(self) -> None:
        """Small pause to let network packets flush before process exit."""
        await asyncio.sleep(0.2)
        os._exit(0)

    async def broadcast_shutdown(self, reason: str = "Director Qadir termination command") -> None:
        """Broadcasts system_shutdown message to all connected WebSocket clients (Electron HUD)."""
        payload = {
            "type": "system_shutdown",
            "reason": reason,
            "timestamp": get_utc8_now_str(),
        }
        message = json.dumps(payload)
        for client in list(self.connected_clients):
            try:
                await client.send_text(message)
            except Exception:
                pass

    async def _metrics_polling_loop(self) -> None:
        """Polls psutil metrics and measures 8.8.8.8 TCP ping every 2.0 seconds."""
        while self.is_running:
            try:
                self.cached_cpu = round(psutil.cpu_percent(interval=None), 1)
                self.cached_ram = round(psutil.virtual_memory().percent, 1)

                # Async socket ping to 8.8.8.8 (port 53)
                start_t = time.perf_counter()
                try:
                    reader, writer = await asyncio.wait_for(
                        asyncio.open_connection("8.8.8.8", 53), timeout=1.5
                    )
                    writer.close()
                    await writer.wait_closed()
                    self.cached_ping = round((time.perf_counter() - start_t) * 1000.0, 1)
                except Exception:
                    self.cached_ping = -1.0

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
                # Watchdog safeguard: auto-heal stuck speaking status when playback buffer is empty, speaker cooldown elapsed, and model turn is closed
                if (
                    self.live_core.status == "speaking"
                    and not getattr(self.live_core, "_model_turn_open", False)
                    and not self.audio.is_playback_active()
                    and not self.audio.is_speaker_locked()
                ):
                    self.live_core.set_status("listening" if self.audio.ptt_active else "idle")

                await self.broadcast_state_packet()
                await asyncio.sleep(0.05)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("Error in telemetry broadcast loop: %s", e)
                await asyncio.sleep(0.05)

    async def trigger_simulated_pulse(self, intensity: float = 0.85) -> None:
        """Simulates an elevated audio RMS pulse decaying over ~800ms."""
        if self._pulse_task and not self._pulse_task.done():
            self._pulse_task.cancel()

        async def _decay():
            try:
                self.simulated_rms = intensity
                steps = 16
                for i in range(steps):
                    await asyncio.sleep(0.05)
                    self.simulated_rms = max(0.0, intensity * (1.0 - (i + 1) / steps))
            except asyncio.CancelledError:
                pass
            finally:
                self.simulated_rms = 0.0

        self._pulse_task = asyncio.create_task(_decay())

    async def _execute_fallback_prompt(self, text: str) -> None:
        """Generates an immediate executive fallback response when Gemini Live is in standby or offline."""
        if getattr(self.live_core, "active_tool", None) is not None:
            logger.info("[Fallback Ignored] A tool is currently executing (%s). Bypassing fallback.", self.live_core.active_tool)
            return

        self.live_core.set_status("thinking")
        self.current_transcript = f"› Directive: \"{text}\""
        await self.broadcast_state_packet()
        await asyncio.sleep(0.3)

        lower = text.lower()
        if "terminate executive commands alfred" in lower:
            farewell = "Terminating all executive commands now, Director Qadir. Standing down, Sir."
            self.live_core.set_status("speaking")
            self.current_transcript = farewell
            await self.broadcast_state_packet()
            self.schedule_shutdown(farewell)
            return
        elif "status" in lower or "report" in lower:
            response = f"Systems nominal, Sir. CPU load is at {self.cached_cpu}%, memory consumption at {self.cached_ram}%. Executive logistics core is fully operational."
        elif "diagnostic" in lower or "telemetry" in lower or "system" in lower:
            response = f"Diagnostics complete. CPU: {self.cached_cpu}%, RAM: {self.cached_ram}%. All secondary buffers operational."
        elif "screen" in lower or "inspect" in lower or "look" in lower:
            screen_res = self.logistics.inspect_active_screen("Manual inspection")
            response = f"Visual cortex engaged. Screen snapshot captured and verified, Sir."
        elif "port" in lower:
            port_report = self.dev_logistics.inspect_local_dev_ports()
            response = f"Developer ports report: {port_report}"
        elif "briefing" in lower:
            brief = self.logistics.manage_executive_briefing(action="list")
            response = f"Executive briefing on record: {brief}"
        else:
            response = f"Directive acknowledged: \"{text}\". Core logistics standing by, Sir."

        self.live_core.set_status("speaking")
        self.current_transcript = response
        await self.trigger_simulated_pulse(0.75)
        await self.broadcast_state_packet()
        await asyncio.sleep(1.2)
        if self.live_core.status == "speaking":
            self.live_core.set_status("listening" if self.audio.ptt_active else "idle")
            await self.broadcast_state_packet()

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
            if state == "toggle":
                pressed = not self.audio.ptt_active
            else:
                pressed = (state == "down") or message_data.get("pressed", False)
            self.audio.set_push_to_talk(pressed)
            logger.debug("Push-to-Talk set: %s (state: %s)", pressed, state)
            await self.broadcast_state_packet()

        elif msg_type == "interrupt":
            logger.info("Manual interrupt requested from HUD.")
            if hasattr(self.live_core, "interrupt"):
                self.live_core.interrupt()
            else:
                self.audio.clear_playback()
                self.live_core.set_status("listening")
            await self.broadcast_state_packet()

        elif msg_type == "set_input_device":
            device_id = message_data.get("device_id")
            if device_id is not None:
                self.audio.switch_input_device(device_id)
                self.cached_devices = self.audio.list_input_devices()
                logger.info("Microphone input device switched to ID %s", device_id)
                await self.broadcast_state_packet()

        elif msg_type == "simulate_pulse":
            intensity = float(message_data.get("intensity", 0.85))
            logger.info("Triggering backend simulated audio pulse (intensity: %.2f)", intensity)
            await self.trigger_simulated_pulse(intensity)
            await self.broadcast_state_packet()

        elif msg_type == "simulate_approval":
            logger.info("Triggering simulated security approval gate from HUD")
            req_id = f"sim-{os.urandom(2).hex()}"
            command = message_data.get("command", "Stop-Process -Name 'anomalous_worker' -Force")
            payload = {
                "id": req_id,
                "action": "execute_terminal_command",
                "command": command,
                "risk_level": "HIGH",
                "timeout": 30.0,
            }
            await self.handle_pending_approval(payload)

        elif msg_type == "text_prompt":
            text = message_data.get("text", "").strip()
            if not text:
                return

            self.on_user_utterance(text)
            self.live_core._current_turn_id += 1
            self.audio.clear_playback()

            if is_shutdown_authorized(text):
                logger.warning("Directive 'terminate executive commands alfred' received via text_prompt!")
                farewell = "Terminating all executive commands now, Director Qadir. Standing down, Sir."
                self.current_transcript = farewell
                self.live_core.set_status("speaking")
                await self.broadcast_state_packet()
                self.schedule_shutdown(farewell)
                return

            if is_stop_command(text):
                logger.info("Operational stop command received via text_prompt: '%s'", text)
                self.abort_current_operations()
                return

            if self.live_core._session and self.live_core.is_running:
                try:
                    logger.info("Injecting text prompt into active Live session: %s", text)
                    self.current_transcript = f"› Directive: \"{text}\""
                    await self.broadcast_state_packet()
                    await self.live_core.send_text_prompt(text)
                except Exception as e:
                    logger.warning("Failed to send prompt to Live session (%s), falling back", e)
                    await self._execute_fallback_prompt(text)
            else:
                logger.info("No active Live session. Executing executive fallback for: %s", text)
                await self._execute_fallback_prompt(text)

        elif msg_type == "inspect_screen_trigger":
            logger.info("Manual inspect screen triggered from HUD.")
            if self.live_core._session and self.live_core.is_running:
                try:
                    annotated_bytes, _ = self.vision.detect_ui_elements_and_annotate_grid()
                    await self.live_core._session.send(
                        input={"data": annotated_bytes, "mime_type": "image/jpeg"},
                        end_of_turn=False,
                    )
                    logger.info("Injected Set-of-Marks annotated full-screen frame to Live session.")
                except Exception as e:
                    logger.warning("Failed to stream screen to Live session: %s", e)
            else:
                await self._execute_fallback_prompt("Inspect active screen.")

    async def start(self, start_live_session: bool = True) -> None:
        """Starts background workers and optionally connects to Gemini Live API."""
        if self.is_running:
            return

        self.is_running = True
        self._metrics_task = asyncio.create_task(self._metrics_polling_loop())
        self._broadcast_task = asyncio.create_task(self._broadcast_loop())

        if start_live_session and os.environ.get("GEMINI_API_KEY") and not self._live_task:
            self._live_task = asyncio.create_task(self.live_session.run_executive_loop())

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
        if self._pulse_task:
            self._pulse_task.cancel()
        if self._fallback_task:
            self._fallback_task.cancel()

        await self.live_core.stop()
        await self.browser_logistics.close()
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
