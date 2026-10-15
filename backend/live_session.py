"""A.L.F.R.E.D. Core Gemini Multimodal Live API Session.

Orchestrates real-time bidirectional audio streaming, non-blocking tool dispatching
(awaiting coroutines and offloading sync tools to threads), visual cortex screen
frame injection, and instant barge-in interruption.
"""

from __future__ import annotations

import asyncio
import inspect
import logging
import os
from typing import Any, Callable, Dict, List, Optional
from dotenv import load_dotenv

from google import genai
from google.genai import types

from backend.audio_manager import AudioManager
from backend.vision_manager import VisionManager

logger = logging.getLogger("AlfredLiveSession")
load_dotenv()

ALFRED_SYSTEM_PROMPT = """You are A.L.F.R.E.D. (Autonomous Logistics Functional Response & Executive Director).
Voice & Persona: Impeccably articulate, composed, dryly witty British executive director.
Address the user as "Sir" or "Director". Keep spoken responses concise (1 to 3 sentences) unless asked for a deep briefing.
Capabilities: You have real-time access to the user's screen, system telemetry, local memory, and OS logistics tools. Always invoke your tools proactively when asked about system status, tasks, or what is currently visible on the monitor."""


class AlfredLiveCore:
    """Manages the persistent Gemini Multimodal Live API bidirectional WebSocket connection."""

    def __init__(
        self,
        tools_list: List[Callable[..., Any]],
        audio_manager: AudioManager,
        vision_manager: Optional[VisionManager] = None,
        api_key: Optional[str] = None,
        model_id: str = "gemini-3.8-live",
        voice_name: Optional[str] = None,
        on_status_change: Optional[Callable[[str], None]] = None,
        on_active_tool_change: Optional[Callable[[Optional[str]], None]] = None,
        on_transcript: Optional[Callable[[str], None]] = None,
    ) -> None:
        self.api_key = api_key or os.environ.get("GEMINI_API_KEY", "")
        self.client = genai.Client(api_key=self.api_key) if self.api_key else None
        self.model_id = os.environ.get("GEMINI_LIVE_MODEL", model_id)
        self.voice_name = voice_name or os.environ.get("ALFRED_VOICE_NAME", "Fenrir")

        self.audio_manager = audio_manager
        self.vision_manager = vision_manager or VisionManager()
        self.tools_list = tools_list
        self.tool_map: Dict[str, Callable[..., Any]] = {fn.__name__: fn for fn in tools_list}

        # Callbacks for telemetry HUD
        self.on_status_change = on_status_change
        self.on_active_tool_change = on_active_tool_change
        self.on_transcript = on_transcript

        self.status: str = "idle"  # "idle" | "listening" | "thinking" | "speaking"
        self.active_tool: Optional[str] = None
        self.is_running: bool = False
        self._loop_active: bool = False
        self._session: Any = None

    def update_transcript(self, text: str) -> None:
        """Notifies coordinator and connected HUD clients with status or transcript update."""
        if self.on_transcript:
            self.on_transcript(text)

    def set_status(self, new_status: str) -> None:
        """Updates internal status and fires callback to HUD."""
        self.status = new_status
        if self.on_status_change:
            self.on_status_change(new_status)

    def set_active_tool(self, tool_name: Optional[str]) -> None:
        """Updates active tool name and notifies HUD."""
        self.active_tool = tool_name
        if self.on_active_tool_change:
            self.on_active_tool_change(tool_name)

    async def dispatch_tool_call(self, session: Any, fc: Any) -> Any:
        """Dispatches Gemini function calls non-blockingly.

        Awaits async coroutines directly (enabling the 30s security gate) and
        runs synchronous tools in worker threads via asyncio.to_thread so 24kHz
        audio playback never stutters.
        Injects real-time JPEG screen frames directly into the Live session on inspect_active_screen.
        """
        tool_name = getattr(fc, "name", "")
        call_id = getattr(fc, "id", None) or "1"
        args = getattr(fc, "args", {}) or {}

        logger.info("[ALFRED LOGISTICS] Dispatching protocol: %s (id: %s)", tool_name, call_id)
        self.set_active_tool(tool_name)
        self.set_status("thinking")

        result: Any = None
        tool_fn = self.tool_map.get(tool_name)

        try:
            # Visual Cortex Bridge: Inject active screen frame directly into Live API session
            if tool_name == "inspect_active_screen" and session is not None:
                try:
                    jpeg_bytes = self.vision_manager.capture_screen_jpeg()
                    logger.info("[Visual Cortex] Streaming 1024px screen frame into active Live session...")
                    await session.send(
                        input={"data": jpeg_bytes, "mime_type": "image/jpeg"},
                        end_of_turn=False,
                    )
                except Exception as e:
                    logger.warning("[Visual Cortex] Failed to inject screen frame: %s", e)

            if tool_fn is None:
                result = f"Error: Tool '{tool_name}' not recognized by A.L.F.R.E.D. logistics."
            elif inspect.iscoroutinefunction(tool_fn):
                # Async tool (e.g. execute_terminal_command with 30s approval gate)
                result = await tool_fn(**args)
            else:
                # Sync tool: run in thread pool to avoid blocking audio streaming event loop
                result = await asyncio.to_thread(tool_fn, **args)

        except Exception as e:
            logger.error("Error executing tool %s: %s", tool_name, e)
            result = f"Tool execution failed: {e}"

        # Send FunctionResponse back to Gemini Live API
        if session is not None:
            try:
                fn_response = types.FunctionResponse(
                    id=call_id,
                    name=tool_name,
                    response={"result": str(result)},
                )
                tool_response = types.LiveClientToolResponse(function_responses=[fn_response])
                await session.send(input=tool_response)
            except Exception as e:
                logger.error("Failed to send function response for %s: %s", tool_name, e)

        self.set_active_tool(None)
        return result

    async def _stream_mic_to_alfred(self, session: Any) -> None:
        """Pulls 16kHz mono PCM chunks from local mic queue and streams to Gemini Live API."""
        while self.is_running:
            try:
                chunk = await self.audio_manager.mic_queue.get()
                if not chunk:
                    continue

                if self.status != "speaking":
                    self.set_status("listening")

                await session.send(
                    input={"data": chunk, "mime_type": "audio/pcm;rate=16000"},
                    end_of_turn=False,
                )
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("Error streaming mic chunk to Live API: %s", e)
                await asyncio.sleep(0.05)

    async def process_server_response(self, response: Any, session: Any = None) -> None:
        """Processes a single Live API server response message (content, interruption, or tool calls)."""
        server_content = getattr(response, "server_content", None)
        if server_content is not None:
            # 1. Instant Barge-in Interruption Handling
            if getattr(server_content, "interrupted", False):
                logger.info("[A.L.F.R.E.D.] User interrupted. Draining speaker playback queue.")
                self.audio_manager.clear_playback()
                self.set_status("listening")
                return

            # 2. Output audio chunks & transcripts
            model_turn = getattr(server_content, "model_turn", None)
            if model_turn is not None:
                for part in model_turn.parts:
                    if part.inline_data and part.inline_data.data:
                        self.set_status("speaking")
                        await self.audio_manager.speaker_queue.put(part.inline_data.data)

                    if getattr(part, "text", None):
                        if self.on_transcript:
                            self.on_transcript(part.text)

        # 3. Tool Calls Dispatching
        tool_call = getattr(response, "tool_call", None)
        if tool_call is not None:
            function_calls = getattr(tool_call, "function_calls", [])
            for fc in function_calls:
                await self.dispatch_tool_call(session, fc)

    async def _receive_from_alfred(self, session: Any) -> None:
        """Receives 24kHz audio chunks, transcripts, and tool calls from Gemini Live API."""
        while self.is_running:
            try:
                async for response in session.receive():
                    if not self.is_running:
                        break
                    await self.process_server_response(response, session)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("Error in Live API receive stream: %s", e)
                await asyncio.sleep(0.2)

    async def start(self) -> None:
        """Starts the Gemini Multimodal Live API bidirectional session."""
        if self.is_running:
            return

        if not self.client:
            msg = "[LIVE API ERROR]: No GEMINI_API_KEY detected in .env."
            logger.error(msg)
            self.update_transcript(msg)
            raise ValueError(msg)

        self.is_running = True
        await self.audio_manager.start()

        # Build LiveConnectConfig with audio modality, persona, and tools
        config = types.LiveConnectConfig(
            response_modalities=["AUDIO"],
            system_instruction=types.Content(
                parts=[types.Part.from_text(text=ALFRED_SYSTEM_PROMPT)]
            ),
            speech_config=types.SpeechConfig(
                voice_config=types.VoiceConfig(
                    prebuilt_voice_config=types.PrebuiltVoiceConfig(
                        voice_name=self.voice_name
                    )
                )
            ),
            tools=self.tools_list,
        )

        logger.info("[ALFRED CORE] Connecting to Gemini Live API (%s)...", self.model_id)
        self.update_transcript(f"[LIVE API]: Connecting to Gemini Live API ({self.model_id})...")

        try:
            async with self.client.aio.live.connect(model=self.model_id, config=config) as session:
                self._session = session
                self.set_status("listening")
                connected_msg = f"[LIVE API]: Connected to {self.model_id} (Voice: {self.voice_name}). Standing by, Sir."
                logger.info(connected_msg)
                self.update_transcript(connected_msg)

                async with asyncio.TaskGroup() as tg:
                    tg.create_task(self._stream_mic_to_alfred(session))
                    tg.create_task(self._receive_from_alfred(session))

        except Exception as e:
            disconnect_msg = f"[LIVE API DISCONNECTED]: {e}"
            logger.error(disconnect_msg)
            self.update_transcript(disconnect_msg)
        finally:
            self.is_running = False
            self._session = None
            self.set_status("idle")

    async def run_executive_loop(self) -> None:
        """Continuously runs the Gemini Multimodal Live API executive session with graceful reconnection."""
        self._loop_active = True
        logger.info("[ALFRED CORE] Launching executive live multimodal session loop...")
        while self._loop_active:
            try:
                await self.start()
            except asyncio.CancelledError:
                break
            except Exception as e:
                err_msg = f"[LIVE API RETRYING in 3s]: {e}"
                logger.error("[ALFRED CORE] %s", err_msg)
                self.update_transcript(err_msg)

            if not self._loop_active:
                break
            await asyncio.sleep(3.0)

    async def stop(self) -> None:
        """Gracefully disconnects the session and halts audio streams."""
        self._loop_active = False
        self.is_running = False
        await self.audio_manager.stop()
        self.set_status("idle")
