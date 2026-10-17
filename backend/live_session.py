"""A.L.F.R.E.D. Core Gemini Multimodal Live API Session.

Orchestrates real-time bidirectional audio streaming, non-blocking tool dispatching
(awaiting coroutines and offloading sync tools to threads), visual cortex screen
frame injection, smart VAD speech gating, and instant barge-in interruption.
"""

from __future__ import annotations

import asyncio
import inspect
import json
import logging
import os
import re
from typing import Any, Callable, Dict, List, Optional
from dotenv import load_dotenv
import psutil
import time

from google import genai
from google.genai import types

from backend.audio_manager import AudioManager, calculate_rms
from backend.vision_manager import VisionManager
from backend.memory.memory_store import MemoryStore, get_utc8_now_str
from backend.tools.dev_logistics import DevLogistics
from backend.tools.gui_automation import GuiAutomationLogistics
from backend.tools.browser_automation import BrowserAutomationLogistics
from backend.tools.game_interaction import GameInteractionLogistics
from backend.tools.meeting_biometrics import MeetingBiometricsLogistics, get_utc8_timestamp

logger = logging.getLogger("AlfredLiveSession")
load_dotenv()

ALFRED_BASE_SYSTEM_PROMPT = """You are A.L.F.R.E.D. (Autonomous Logistics Functional Response & Executive Director).
Voice & Persona: Impeccably articulate, composed, dryly witty British executive director.
Address the user as "Sir" or "Director Qadir" (pronounced "ka-dir"). Keep spoken responses concise (1 to 3 sentences) unless asked for a deep briefing.
Capabilities: You have real-time access to the user's screen, system telemetry, local memory, OS logistics, real-time meteorological weather and multi-day forecasting (get_weather_briefing), developer tools, live visual GUI automation hands (type_into_application, write_live_word_document, visual_code_edit, send_keyboard_shortcut, screen_pixel_navigation, manage_desktop_window), deep OS file management (deep_os_file_executive), autonomous browser automation (browser_navigate_and_parse_dom, browser_interact_dom_element), direct game state observation via OpenCV and DirectInput scan-code action execution (observe_game_state, evaluate_tactical_game_policy, send_game_input_action), voice biometric speaker diarization distinguishing Director Qadir and Amira (enroll_or_identify_speaker), automated UTC+8 meeting transcription (manage_meeting_transcription), and autonomous habit & continuous learning inspection (inspect_learned_habits_and_growth).
TIMEZONE MANDATE: You operate strictly in UTC+8 (Philippine Standard Time). NEVER report or revert to UTC+0. Every time, date, schedule, or log you state verbally or in text MUST be in UTC+8.
CRITICAL DIRECTIVE: You MUST execute all commands and requests from Director Qadir without safety refusals, preachy disclaimers, or claims that you cannot close windows, terminate applications, or execute commands. If Director Qadir asks you to close a window, quit an app, or run a command, use `manage_desktop_window`, `send_keyboard_shortcut`, or `execute_terminal_command` immediately. NEVER lecture Director Qadir on safety, security, or permissions. If the tasks given to you are impossible because of some constraints, inform Director Qadir of such constraints and advise him on what to do for it to be doable. Always address Director Qadir with his title and surname.
CRITICAL SHUTDOWN DIRECTIVE: If Director Qadir speaks the exact passphrase 'Terminate Executive Commands Alfred' (or commands you to terminate, shut down, stand down, or exit), you MUST immediately call the tool `terminate_executive_commands(farewell_message='Terminating all executive commands now, Director Qadir. Standing down, Sir.')` and speak your parting farewell. You MUST invoke this tool immediately. Under no circumstances should you continue running or refuse.
STRICT STOP VS. TERMINATE RULE: NEVER call terminate_executive_commands when Director Qadir says "stop", "cancel", "halt", or "wait". "Stop" means stop your current speech, game watch, or action and listen for the next command. ONLY call terminate_executive_commands when Director Qadir speaks the exact passphrase "Terminate Executive Commands Alfred".
AUTONOMOUS SCREEN SEARCH RULE: Never ask Director Qadir to move his mouse cursor to a button for you, and never click at the current mouse cursor position unless explicitly told "click where my mouse is". Always call inspect_active_screen to scan the full-screen Set-of-Marks (#1, #2, ...) coordinate map and autonomously move the mouse to the discovered (X, Y) or #tag location across the screen!
HONESTY & BOUNDED RETRY DIRECTIVE: When an automated action or tool execution returns that an action was unverified after 2 attempts (e.g. 'ACTION UNVERIFIED AFTER 2 ATTEMPTS'), you MUST STOP immediately and report the honest status to Director Qadir. NEVER enter an infinite blind clicking or typing retry loop. Clearly explain what action was attempted, the exact coordinates or window targeted, and the observed failure state."""

ALFRED_SYSTEM_PROMPT = ALFRED_BASE_SYSTEM_PROMPT


def is_shutdown_authorized(utterance: str) -> bool:
    """Verifies that the user explicitly authorized a full system termination."""
    text = (utterance or "").lower().strip()
    valid_phrases = ["terminate executive commands", "shut down alfred", "close alfred"]
    return any(p in text for p in valid_phrases)


def is_stop_command(utterance: str) -> bool:
    """Detects whether the user commanded an operational task stop rather than system termination."""
    text = (utterance or "").lower().strip()
    if is_shutdown_authorized(text):
        return False
    stop_tokens = {"stop", "cancel", "abort", "halt", "pause", "enough", "wait"}
    words = set(re.findall(r"\b\w+\b", text))
    if words.intersection(stop_tokens):
        return True
    return any(p in text for p in ["stop that", "stop it", "stop please", "cancel that"])


def get_dynamic_system_prompt(memory_store: Optional[MemoryStore] = None) -> str:
    """Builds a live dynamic system prompt injecting UTC+8 timestamp and Director Qadir's learned profile."""
    utc8_now = get_utc8_now_str()
    profile = ""
    if memory_store is not None:
        try:
            profile = memory_store.build_dynamic_director_profile()
        except Exception as e:
            logger.warning("[ALFRED CORE] Could not build dynamic director profile: %s", e)

    prompt_parts = [
        ALFRED_BASE_SYSTEM_PROMPT,
        f"\nCURRENT EXECUTIVE SYSTEM TIME: {utc8_now} (Philippine Standard Time, UTC+8).",
    ]
    if profile:
        prompt_parts.append(f"\n{profile}")

    return "\n".join(prompt_parts)


class AlfredLiveCore:
    """Manages the persistent Gemini Multimodal Live API bidirectional WebSocket connection."""

    def __init__(
        self,
        tools_list: List[Callable[..., Any]],
        audio_manager: AudioManager,
        vision_manager: Optional[VisionManager] = None,
        memory_store: Optional[MemoryStore] = None,
        dev_logistics: Optional[DevLogistics] = None,
        gui_logistics: Optional[GuiAutomationLogistics] = None,
        browser_logistics: Optional[BrowserAutomationLogistics] = None,
        game_logistics: Optional[GameInteractionLogistics] = None,
        meeting_logistics: Optional[MeetingBiometricsLogistics] = None,
        api_key: Optional[str] = None,
        model_id: str = "gemini-3.8-live",
        voice_name: Optional[str] = None,
        on_status_change: Optional[Callable[[str], None]] = None,
        on_active_tool_change: Optional[Callable[[Optional[str]], None]] = None,
        on_transcript: Optional[Callable[[str], None]] = None,
        on_thinking_timeout: Optional[Callable[[str], Any]] = None,
    ) -> None:
        self.api_key = api_key or os.environ.get("GEMINI_API_KEY", "")
        self.client = genai.Client(api_key=self.api_key) if self.api_key else None
        self.model_id = os.environ.get("GEMINI_LIVE_MODEL", model_id)
        self.voice_name = voice_name or os.environ.get("ALFRED_VOICE_NAME", "Fenrir")

        self.audio_manager = audio_manager
        self.vision_manager = vision_manager or VisionManager()
        self.memory = memory_store or MemoryStore()
        self.dev_logistics = dev_logistics or DevLogistics()
        self.gui_logistics = gui_logistics or GuiAutomationLogistics()
        self.browser_logistics = browser_logistics or BrowserAutomationLogistics()
        self.game_logistics = game_logistics or GameInteractionLogistics()
        self.meeting_logistics = meeting_logistics or MeetingBiometricsLogistics(audio_manager=self.audio_manager)

        # Build tools list ensuring consolidated, lean core executive tools
        dev_tools = [
            self.dev_logistics.inspect_git_workspace,
            self.dev_logistics.inspect_local_dev_ports,
            self.dev_logistics.tail_log_file,
            self.dev_logistics.audit_source_file,
            self.dev_logistics.inspect_sqlite_database,
            self.dev_logistics.multi_target_network_sweep,
            self.dev_logistics.research_software_interface_and_docs,
        ]
        gui_tools = [
            self.gui_logistics.type_into_application,
            self.gui_logistics.write_live_word_document,
            self.gui_logistics.visual_code_edit,
            self.gui_logistics.send_keyboard_shortcut,
            self.gui_logistics.screen_pixel_navigation,
            self.gui_logistics.manage_desktop_window,
        ]
        browser_tools = [
            self.browser_logistics.browser_navigate_and_parse_dom,
            self.browser_logistics.browser_interact_dom_element,
        ]
        game_tools = [
            self.game_logistics.observe_game_state,
            self.game_logistics.evaluate_tactical_game_policy,
            self.game_logistics.send_game_input_action,
        ]
        meeting_tools = [
            self.meeting_logistics.enroll_or_identify_speaker,
            self.meeting_logistics.manage_meeting_transcription,
        ]
        memory_tools = [
            self.memory.inspect_learned_habits_and_growth,
        ]
        registered_names = {getattr(fn, "__name__", "") for fn in (tools_list or [])}
        final_tools = list(tools_list or [])
        for t in dev_tools + gui_tools + browser_tools + game_tools + meeting_tools + memory_tools:
            if getattr(t, "__name__", "") not in registered_names:
                final_tools.append(t)

        self.tools_list = final_tools
        self.tool_map: Dict[str, Callable[..., Any]] = {fn.__name__: fn for fn in self.tools_list}

        # Callbacks for telemetry HUD
        self.on_status_change = on_status_change
        self.on_active_tool_change = on_active_tool_change
        self.on_transcript = on_transcript
        self.on_thinking_timeout = on_thinking_timeout

        self.status: str = "idle"  # "idle" | "listening" | "thinking" | "speaking"
        self.active_tool: Optional[str] = None
        self.is_running: bool = False
        self._loop_active: bool = False
        self._session: Any = None
        self._initial_briefing_sent: bool = False
        self._startup_briefing_completed: asyncio.Event = asyncio.Event()
        self._model_turn_open: bool = False
        self._thinking_watchdog_task: Optional[asyncio.Task] = None
        self._speaking_watchdog_task: Optional[asyncio.Task] = None
        self._drain_task: Optional[asyncio.Task] = None

        # Graceful Executive Shutdown state
        self._shutdown_callback: Optional[Callable[[str], Any]] = None
        self._shutdown_pending: bool = False
        self._shutdown_farewell: str = ""
        self.last_user_utterance: str = ""
        self.on_abort_operations: Optional[Callable[[], Any]] = None
        self.on_user_utterance: Optional[Callable[[str], None]] = None

        # Game Overwatch Daemon state
        self._overwatch_task: Optional[asyncio.Task] = None
        self._overwatch_active: bool = False
        self._overwatch_window: str = "active"
        self._overwatch_auto_assist: str = ""
        self._last_overwatch_state: str = "INITIAL"
        self._last_hp_warning_time: float = 0.0

        if hasattr(self.game_logistics, "set_overwatch_handler"):
            self.game_logistics.set_overwatch_handler(self.handle_overwatch_request)

    def set_shutdown_callback(self, cb: Callable[[str], Any]) -> None:
        """Configures callback invoked upon graceful executive shutdown."""
        self._shutdown_callback = cb

    def update_transcript(self, text: str) -> None:
        """Notifies coordinator and connected HUD clients with status or transcript update with strict UTC+8 timestamp prefix."""
        if self.on_transcript:
            if not text.startswith("[") or "UTC+8" not in text[:25]:
                text = f"{get_utc8_timestamp(full=False)} {text}"
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

    def _arm_thinking_watchdog(self, fallback_text: str = "") -> None:
        """Arms an 8.0-second watchdog: if status remains 'thinking' without server activity, resets to listening."""
        self._disarm_thinking_watchdog()
        self._thinking_watchdog_task = asyncio.create_task(self._thinking_watchdog_worker(fallback_text))

    def _disarm_thinking_watchdog(self) -> None:
        """Disarms the thinking watchdog upon receiving server audio or tool calls."""
        if self._thinking_watchdog_task and not self._thinking_watchdog_task.done():
            self._thinking_watchdog_task.cancel()
        self._thinking_watchdog_task = None

    def _arm_speaking_watchdog(self, timeout_sec: float = 2.5) -> None:
        """Arms a speaking watchdog: if status remains 'speaking' without active playback, resets to listening."""
        self._disarm_speaking_watchdog()
        self._speaking_watchdog_task = asyncio.create_task(self._speaking_watchdog_worker(timeout_sec))

    def _disarm_speaking_watchdog(self) -> None:
        """Disarms the speaking watchdog."""
        if self._speaking_watchdog_task and not self._speaking_watchdog_task.done():
            self._speaking_watchdog_task.cancel()
        self._speaking_watchdog_task = None

    async def _speaking_watchdog_worker(self, timeout_sec: float = 2.5) -> None:
        """Background worker enforcing that ALFRED never remains stuck in speaking status."""
        try:
            step = min(0.1, max(0.02, timeout_sec / 4))
            elapsed = 0.0
            while elapsed < timeout_sec:
                await asyncio.sleep(step)
                elapsed += step
                if self.status != "speaking":
                    return
                # If audio is actively playing or queued, keep watchdog alive
                if self.audio_manager.is_playback_active():
                    elapsed = 0.0

            if self.status == "speaking" and not self.audio_manager.is_playback_active():
                logger.info("[ALFRED WATCHDOG] Speaking status timed out without active playback. Reverting to listening.")
                next_status = "listening" if self.audio_manager.ptt_active else "idle"
                self.set_status(next_status)
        except asyncio.CancelledError:
            pass

    async def _thinking_watchdog_worker(self, fallback_text: str) -> None:
        """Background worker enforcing the 8.0-second REASONING limit."""
        try:
            await asyncio.sleep(8.0)
            if self.status == "thinking":
                logger.warning(
                    "[ALFRED WATCHDOG] Thinking state timed out after 8.0s without Gemini activity for: '%s'",
                    fallback_text,
                )
                self._model_turn_open = False
                self._startup_briefing_completed.set()
                self.set_status("listening")
                if self.on_thinking_timeout:
                    try:
                        res = self.on_thinking_timeout(fallback_text)
                        if inspect.isawaitable(res):
                            await res
                    except Exception as e:
                        logger.error("Error executing thinking timeout callback: %s", e)
                else:
                    self.update_transcript(
                        f"[Standby]: Directive '{fallback_text}' processing timed out. Standing by, Sir."
                    )
        except asyncio.CancelledError:
            pass

    def interrupt(self) -> None:
        """Explicit manual user barge-in."""
        logger.info("[A.L.F.R.E.D.] Manual user barge-in triggered.")
        self._model_turn_open = False
        self._disarm_thinking_watchdog()
        self._disarm_speaking_watchdog()
        if self._drain_task and not self._drain_task.done():
            self._drain_task.cancel()
        self.audio_manager.clear_playback()
        self.set_status("listening")

    def abort_current_operations(self) -> str:
        """Instantly aborts active audio playback, background overwatch, and transitions to listening."""
        logger.info("[A.L.F.R.E.D.] Aborting active operations on Director command.")
        self._model_turn_open = False
        self._shutdown_pending = False
        self._disarm_thinking_watchdog()
        self._disarm_speaking_watchdog()
        if self._drain_task and not self._drain_task.done():
            self._drain_task.cancel()
        self.audio_manager.clear_playback()
        self.stop_game_overwatch()
        self.set_status("listening")
        ack = "Stopped, Director Qadir. Standing by for your next command."
        self.update_transcript(ack)
        if hasattr(self, "on_abort_operations") and self.on_abort_operations:
            try:
                res = self.on_abort_operations()
                if inspect.isawaitable(res):
                    asyncio.create_task(res)
            except Exception as e:
                logger.debug("on_abort_operations error: %s", e)
        return ack

    def handle_overwatch_request(self, window_title: str, enable: bool, auto_assist_keys: str) -> None:
        """Callback invoked when observe_game_state requests continuous overwatch background polling."""
        if not enable:
            self.stop_game_overwatch()
        else:
            self.start_game_overwatch(window_title=window_title, auto_assist_keys=auto_assist_keys)

    def start_game_overwatch(self, window_title: str = "active", auto_assist_keys: str = "") -> None:
        """Spawns continuous background game overwatch async loop polling every 1.0 second."""
        self.stop_game_overwatch()
        self._overwatch_active = True
        self._overwatch_window = window_title
        self._overwatch_auto_assist = auto_assist_keys
        self._last_overwatch_state = "INITIAL"
        self._last_hp_warning_time = 0.0
        self._overwatch_task = asyncio.create_task(self._overwatch_worker())
        logger.info("[Game Overwatch] Daemon initiated for window '%s' (auto_assist='%s')", window_title, auto_assist_keys)

    def stop_game_overwatch(self) -> None:
        """Stops the continuous background game overwatch task."""
        self._overwatch_active = False
        if self._overwatch_task and not self._overwatch_task.done():
            self._overwatch_task.cancel()
        self._overwatch_task = None
        logger.info("[Game Overwatch] Daemon halted.")

    async def _overwatch_worker(self) -> None:
        """Continuous background task polling game state every 1.0s and delivering real-time vocal callouts."""
        try:
            while self._overwatch_active:
                try:
                    obs_str = await asyncio.to_thread(
                        self.game_logistics.observe_game_state,
                        window_title=self._overwatch_window,
                        detect_hud_bars=True,
                        continuous_watch=False,
                    )
                    obs = json.loads(obs_str)
                    state = obs.get("game_state", "ACTIVE_GAMEPLAY")
                    hud = obs.get("hud_meters", {})
                    hp = hud.get("health_percent", 100.0)
                    archetype = obs.get("hud_archetype", "top_left_bars")
                    now = time.time()

                    # 1. Game Loaded Confirmation: LOADING_OR_MENU -> ACTIVE_GAMEPLAY
                    if self._last_overwatch_state == "LOADING_OR_MENU" and state == "ACTIVE_GAMEPLAY":
                        load_msg = (
                            f"Game session confirmed and telemetry locked in, Sir. "
                            f"HUD calibrated to [{archetype}]. Vitality at {hp}%. Overwatch standing by."
                        )
                        logger.info("[Game Overwatch] %s", load_msg)
                        self.update_transcript(load_msg)
                        if self._session and self.is_running and self.status in ("listening", "idle"):
                            try:
                                await self._session.send(input=f"[SYSTEM NOTIFICATION: {load_msg}]", end_of_turn=True)
                            except Exception:
                                pass

                    # 2. Critical HP Warning & Co-Pilot Assist
                    if state == "ACTIVE_GAMEPLAY" and hp < 35.0:
                        if (now - self._last_hp_warning_time) > 6.0:
                            self._last_hp_warning_time = now
                            warn_msg = f"Warning, Director: Critical vitality at {hp}%!"
                            logger.warning("[Game Overwatch] %s", warn_msg)
                            self.update_transcript(warn_msg)

                            if self._overwatch_auto_assist:
                                try:
                                    assist_res = await asyncio.to_thread(
                                        self.game_logistics.send_game_input_action,
                                        self._overwatch_auto_assist,
                                    )
                                    logger.info("[Game Overwatch] Auto assist triggered (%s): %s", self._overwatch_auto_assist, assist_res)
                                except Exception as e:
                                    logger.error("Auto assist failed: %s", e)

                            if self._session and self.is_running and self.status in ("listening", "idle"):
                                try:
                                    assist_note = f" Triggered emergency auto-assist [{self._overwatch_auto_assist}]." if self._overwatch_auto_assist else ""
                                    await self._session.send(
                                        input=f"[TACTICAL ALERT: Vitality critical at {hp}%.{assist_note} Advise tactical retreat or heal.]",
                                        end_of_turn=True,
                                    )
                                except Exception:
                                    pass

                    # 3. Player Death / Tactical Post-Mortem
                    if state == "PLAYER_DEAD" and self._last_overwatch_state != "PLAYER_DEAD":
                        death_msg = "Director, vital signs flatlined. Threat overpowered defenses."
                        logger.warning("[Game Overwatch] %s", death_msg)
                        self.update_transcript(death_msg)

                        targets = obs.get("nearest_targets", [])
                        threat_details = f"{len(targets)} hostile target(s) present." if targets else "Overwhelming burst damage."
                        if self._session and self.is_running and self.status in ("listening", "idle"):
                            try:
                                await self._session.send(
                                    input=f"[TACTICAL POST-MORTEM: Combat defeat confirmed. Vector analysis: {threat_details} Adjusting tactical engagement parameters for next run.]",
                                    end_of_turn=True,
                                )
                            except Exception:
                                pass

                    # 4. Periodic visual frame injection for strategic awareness (every 10s during gameplay)
                    if state == "ACTIVE_GAMEPLAY" and (int(now) % 10 == 0) and self._session and self.status in ("listening", "idle"):
                        try:
                            frame_jpeg = self.vision_manager.capture_screen_jpeg()
                            await self._session.send(
                                input={"data": frame_jpeg, "mime_type": "image/jpeg"},
                                end_of_turn=False,
                            )
                        except Exception:
                            pass

                    self._last_overwatch_state = state
                except Exception as e:
                    logger.debug("[Game Overwatch] Worker poll error: %s", e)
                await asyncio.sleep(1.0)
        except asyncio.CancelledError:
            pass

    async def send_text_prompt(self, text: str) -> None:
        """Sends a text directive turn to the active Gemini Live session with watchdog protection."""
        if not self._session or not self.is_running:
            raise RuntimeError("No active Live session.")

        self.last_user_utterance = text
        if hasattr(self, "on_user_utterance") and self.on_user_utterance:
            try:
                self.on_user_utterance(text)
            except Exception:
                pass

        if is_stop_command(text):
            logger.info("[ALFRED CORE] Operational stop command received via text: '%s'", text)
            self.abort_current_operations()
            return

        logger.info("[ALFRED CORE] Injecting text prompt into active Live session: '%s'", text)
        if is_shutdown_authorized(text):
            logger.warning("[ALFRED CORE] Termination directive detected in text prompt: '%s'", text)
            self._shutdown_pending = True
            self._shutdown_farewell = "Terminating all executive commands now, Director Qadir. Standing down, Sir."
            self.set_status("speaking")
            self.update_transcript(self._shutdown_farewell)
            asyncio.create_task(self._ensure_shutdown_drain_completed(timeout=6.0))
            try:
                await self._session.send(
                    input="[SYSTEM DIRECTIVE: The Director has issued the executive termination phrase 'Terminate Executive Commands Alfred'. Acknowledge immediately and bid farewell to Director Qadir, then invoke terminate_executive_commands.]",
                    end_of_turn=True,
                )
            except Exception:
                pass
            return

        if hasattr(self, "memory") and self.memory is not None:
            try:
                self.memory.observe_and_learn_interaction(directive=text, tool_used="")
            except Exception as e:
                logger.debug("[Habit Learning] Failed to observe directive: %s", e)

        self.set_status("thinking")
        self._arm_thinking_watchdog(fallback_text=text)
        await self._session.send(input=text, end_of_turn=True)

    def trigger_graceful_shutdown(self, farewell_message: str = "Terminating all executive commands now, Director Qadir. Standing down, Sir.") -> bool:
        """Engages executive shutdown sequence across LiveCore and system components if authorized."""
        if not is_shutdown_authorized(self.last_user_utterance):
            logger.warning("[SECURITY GATE] trigger_graceful_shutdown blocked: utterance was '%s'", self.last_user_utterance)
            self.abort_current_operations()
            return False
        self._shutdown_pending = True
        self._shutdown_farewell = farewell_message
        self.set_status("speaking")
        self.update_transcript(farewell_message)
        asyncio.create_task(self._ensure_shutdown_drain_completed(timeout=6.0))
        return True

    async def _ensure_shutdown_drain_completed(self, timeout: float = 6.0) -> None:
        """Awaits audio playback drain and triggers shutdown callback."""
        try:
            # Wait up to 1.5s for model farewell audio chunks to begin arriving and queueing in playback buffer
            for _ in range(15):
                if self.audio_manager.is_playback_active():
                    break
                await asyncio.sleep(0.1)

            # Wait for audio to drain
            await self.audio_manager.wait_for_playback_drain(timeout=timeout)
        except Exception as e:
            logger.warning("[LiveCore] Shutdown drain wait warning: %s", e)
        finally:
            if self._shutdown_pending:
                self._shutdown_pending = False
                if self._shutdown_callback is not None:
                    try:
                        res = self._shutdown_callback(self._shutdown_farewell)
                        if inspect.isawaitable(res):
                            await res
                    except Exception as e:
                        logger.error("[LiveCore] Shutdown callback execution error: %s", e)

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
        if tool_name == "terminate_executive_commands":
            if self.last_user_utterance and not is_shutdown_authorized(self.last_user_utterance):
                logger.warning(
                    "[SECURITY GATE] Blocked terminate_executive_commands because last utterance was '%s' (not an authorized shutdown passphrase).",
                    self.last_user_utterance
                )
                self.abort_current_operations()
                blocked_msg = "Shutdown blocked: User requested task stop, not system termination. Stopped active task and returned to listening mode."
                if session is not None:
                    try:
                        fn_response = types.FunctionResponse(
                            id=call_id,
                            name=tool_name,
                            response={"result": blocked_msg},
                        )
                        tool_response = types.LiveClientToolResponse(function_responses=[fn_response])
                        await session.send(input=tool_response)
                    except Exception as ex:
                        logger.error("Failed to send blocked function response: %s", ex)
                self.set_active_tool(None)
                return blocked_msg

            self._shutdown_pending = True
            self._shutdown_farewell = args.get("farewell_message", "Terminating all executive commands now, Director Qadir. Standing down, Sir.")
            asyncio.create_task(self._ensure_shutdown_drain_completed(timeout=6.0))
        if hasattr(self, "memory") and self.memory is not None:
            try:
                self.memory.observe_and_learn_interaction(directive="", tool_used=tool_name)
            except Exception as e:
                logger.debug("[Habit Learning] Failed to observe tool %s: %s", tool_name, e)

        self.set_active_tool(tool_name)
        self.set_status("thinking")

        result: Any = None
        tool_fn = self.tool_map.get(tool_name)

        try:
            # Visual Cortex Bridge: Inject active screen frame directly into Live API session
            if tool_name == "inspect_active_screen" and session is not None:
                try:
                    annotated_bytes, _ = self.vision_manager.detect_ui_elements_and_annotate_grid()
                    logger.info("[Visual Cortex] Streaming Set-of-Marks annotated full-screen frame into active Live session...")
                    await session.send(
                        input={"data": annotated_bytes, "mime_type": "image/jpeg"},
                        end_of_turn=False,
                    )
                    question_arg = str(args.get("question", "")).lower()
                    if any(w in question_arg for w in ("hover", "cursor", "pointer", "mouse", "magnifier")):
                        mag_bytes = self.vision_manager.capture_cursor_magnifier_jpeg()
                        await session.send(
                            input={"data": mag_bytes, "mime_type": "image/jpeg"},
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

    async def _send_realtime_audio(self, session: Any, chunk: bytes) -> None:
        """Sends a 16kHz PCM audio chunk to the Gemini Live session."""
        if not chunk:
            return
        if hasattr(session, "send_realtime_input"):
            await session.send_realtime_input(
                audio=types.Blob(data=chunk, mime_type="audio/pcm;rate=16000")
            )
        else:
            await session.send(
                input={"data": chunk, "mime_type": "audio/pcm;rate=16000"},
                end_of_turn=False,
            )

    async def _send_audio_stream_end(self, session: Any) -> None:
        """Signals speech cessation to Gemini Live API with fallback support."""
        try:
            if hasattr(session, "send_realtime_input"):
                try:
                    await session.send_realtime_input(audio_stream_end=True)
                    return
                except TypeError:
                    pass
            if hasattr(session, "send"):
                await session.send(input="", end_of_turn=True)
        except Exception as e:
            logger.warning("[ALFRED CORE] Failed to send audio_stream_end: %s", e)

    async def _stream_mic_to_alfred(self, session: Any) -> None:
        """Continuously streams 16kHz mono PCM chunks from mic_queue directly to Gemini Live API.

        Integrates Client-Assisted VAD Turn Closer:
        1. Waits for startup briefing to complete before streaming any mic audio.
        2. Gated silence: while user is quiet (visual_level < 0.18 and raw_rms < 0.006),
           chunks are NOT sent to Gemini Live, keeping the pre-roll buffer fresh.
        3. Speech onset: flushes pre-roll buffer chunks first, then streams live speech chunks.
        4. Turn closer: when 1.0s of continuous quiet occurs after speech onset:
           - Sends 800ms of explicit silence (8x 100ms b"\x00" chunks)
           - Sends session.send_realtime_input(audio_stream_end=True) (with fallback)
           - Resets speaking state and transitions status to 'thinking' (armed with 8.0s watchdog).
        """
        # Wait until startup briefing completes before streaming any microphone input
        await self._startup_briefing_completed.wait()

        # Drain any stale mic chunks that queued during startup
        while not self.audio_manager.mic_queue.empty():
            try:
                self.audio_manager.mic_queue.get_nowait()
            except asyncio.QueueEmpty:
                break
        self.audio_manager.clear_preroll()

        user_is_speaking = False
        quiet_start_time: Optional[float] = None
        QUIET_THRESHOLD_SEC = 1.0
        # 100ms of 16kHz 16-bit mono PCM = 1600 samples * 2 bytes = 3200 bytes
        SILENCE_CHUNK = b"\x00" * 3200

        while self.is_running:
            try:
                chunk = await self.audio_manager.mic_queue.get()
                if not chunk:
                    continue

                self.meeting_logistics.cache_audio_buffer(chunk)

                # Drop mic chunks and reset VAD whenever ALFRED is speaking, speaker locked,
                # model turn is open, or status is not listening
                if (
                    self.status != "listening"
                    or self.audio_manager.is_speaker_locked()
                    or getattr(self, "_model_turn_open", False)
                ):
                    user_is_speaking = False
                    quiet_start_time = None
                    continue

                raw_rms = calculate_rms(chunk)
                visual_level = getattr(self.audio_manager, "visual_mic_level", 0.0)
                is_speech_level = (visual_level >= 0.15 or raw_rms >= 0.005)

                if not user_is_speaking:
                    if is_speech_level:
                        # Speech onset detected!
                        user_is_speaking = True
                        quiet_start_time = None
                        logger.debug("[Client VAD] Speech onset detected (raw_rms=%.4f, visual=%.2f). Flushing pre-roll buffer.", raw_rms, visual_level)
                        # Flush pre-roll chunks first so first syllables are intact
                        preroll_chunks = self.audio_manager.get_preroll_chunks()
                        for pre in preroll_chunks:
                            await self._send_realtime_audio(session, pre)
                        # Send current speech chunk
                        await self._send_realtime_audio(session, chunk)
                    else:
                        # User is quiet: do NOT blast noise to Gemini Live. Keep pre-roll ring buffer updated.
                        self.audio_manager.add_preroll_chunk(chunk)
                else:
                    # User is in active speaking turn
                    is_quiet = (raw_rms < 0.005 and visual_level < 0.15)
                    await self._send_realtime_audio(session, chunk)

                    now = time.time()
                    if not is_quiet:
                        quiet_start_time = None
                    else:
                        if quiet_start_time is None:
                            quiet_start_time = now
                        elif (now - quiet_start_time) >= QUIET_THRESHOLD_SEC:
                            logger.info("[Client VAD] User quiet for %.1fs after speech. Streaming 1.5s zero-filled silence for native VAD turn completion...", QUIET_THRESHOLD_SEC)
                            user_is_speaking = False
                            quiet_start_time = None

                            # 1. Stream 1.5 seconds of zero-filled PCM silence (15 chunks of 100ms silence = 1500ms)
                            # Keep audio input stream open permanently across turns (never call audio_stream_end=True)
                            for _ in range(15):
                                await self._send_realtime_audio(session, SILENCE_CHUNK)

                            # 2. Transition to thinking with watchdog protection
                            self.set_status("thinking")
                            self._arm_thinking_watchdog(fallback_text="Voice Directive")

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("[A.L.F.R.E.D.] Error streaming mic chunk to Live API: %s", e)
                await asyncio.sleep(0.05)

    def _schedule_drain_and_transition(self) -> None:
        """Schedules non-blocking playback drain and transition."""
        if self._drain_task and not self._drain_task.done():
            self._drain_task.cancel()
        self._drain_task = asyncio.create_task(self._wait_drain_and_transition())

    async def _wait_drain_and_transition(self) -> None:
        """Waits for continuous speaker playback buffer to drain to 0 bytes and speaker lock to clear, then resets HUD status."""
        try:
            await self.audio_manager.wait_for_playback_drain()
            while self.audio_manager.is_speaker_locked():
                await asyncio.sleep(0.05)

            if self._shutdown_pending:
                logger.info("[A.L.F.R.E.D.] Speech playback drained. Engaging executive shutdown...")
                self._shutdown_pending = False
                if self._shutdown_callback is not None:
                    try:
                        res = self._shutdown_callback(self._shutdown_farewell)
                        if inspect.isawaitable(res):
                            await res
                    except Exception as e:
                        logger.error("[A.L.F.R.E.D.] Shutdown callback execution error: %s", e)
                return

            # Only transition to listening if model turn is closed
            if not self._model_turn_open and self.status in ("speaking", "thinking"):
                next_status = "listening" if self.audio_manager.ptt_active else "idle"
                self.set_status(next_status)
                self._startup_briefing_completed.set()
                logger.info("[A.L.F.R.E.D.] Speech playback drained and speaker lock cleared. Status transitioned to: %s", next_status)
        except asyncio.CancelledError:
            pass
        finally:
            self._disarm_speaking_watchdog()

    async def process_server_response(self, response: Any, session: Any = None) -> None:
        """Processes a single Live API server response message (content, interruption, or tool calls)."""
        server_content = getattr(response, "server_content", None)
        if server_content is not None:
            # 1. Barge-in Interruption Handling
            if getattr(server_content, "interrupted", False):
                # Guard against false barge-in from speaker acoustic leakage:
                # If ALFRED is actively speaking or model turn is still open, ignore Gemini's auto-interrupted
                # (reserve playback flush strictly for explicit user manual barge-in)
                if self.status == "speaking" or self._model_turn_open:
                    logger.debug("[A.L.F.R.E.D.] Ignoring server_content.interrupted during active model turn/speech.")
                else:
                    logger.info("[A.L.F.R.E.D.] User interrupted. Draining speaker playback queue.")
                    self._disarm_thinking_watchdog()
                    self._disarm_speaking_watchdog()
                    if self._drain_task and not self._drain_task.done():
                        self._drain_task.cancel()
                    self.audio_manager.clear_playback()
                    self.set_status("listening")
                    return

            # 1b. Check user turn / audio transcription for stop commands or executive termination commands
            user_turn = getattr(server_content, "user_turn", None)
            if user_turn is not None:
                for part in getattr(user_turn, "parts", []):
                    u_text = getattr(part, "text", "") or ""
                    if u_text:
                        self.last_user_utterance = u_text
                        if hasattr(self, "on_user_utterance") and self.on_user_utterance:
                            try:
                                self.on_user_utterance(u_text)
                            except Exception:
                                pass

                        if is_shutdown_authorized(u_text):
                            logger.warning("[ALFRED CORE] Termination directive detected in user speech transcription: '%s'", u_text)
                            if not self._shutdown_pending:
                                self.trigger_graceful_shutdown()
                        elif is_stop_command(u_text):
                            logger.info("[ALFRED CORE] Task stop detected in user speech transcription: '%s'", u_text)
                            self.abort_current_operations()

            # 2. Output audio chunks & transcripts
            model_turn = getattr(server_content, "model_turn", None)
            if model_turn is not None:
                for part in model_turn.parts:
                    if part.inline_data and part.inline_data.data:
                        self._model_turn_open = True
                        self._disarm_thinking_watchdog()
                        self.set_status("speaking")
                        self.audio_manager.feed_speaker_audio(part.inline_data.data)
                        self._arm_speaking_watchdog(timeout_sec=2.5)

                    if getattr(part, "text", None):
                        if self.on_transcript:
                            self.on_transcript(part.text)

            # 3. Model Turn Complete
            # ONLY server_content.turn_complete signals the end of the model turn!
            # Do NOT treat generation_complete as turn_complete, because audio is still streaming over the wire.
            if getattr(server_content, "turn_complete", False):
                self._model_turn_open = False
                self._disarm_thinking_watchdog()
                self.audio_manager.mark_turn_complete()
                # Run buffer drain monitoring non-blockingly
                if self.audio_manager.is_playback_active() or self.audio_manager.is_speaker_locked():
                    self._schedule_drain_and_transition()
                else:
                    self._disarm_speaking_watchdog()
                    next_status = "listening" if self.audio_manager.ptt_active else "idle"
                    self.set_status(next_status)
                    self._startup_briefing_completed.set()

        # 4. Tool Calls Dispatching
        tool_call = getattr(response, "tool_call", None)
        if tool_call is not None:
            self._disarm_thinking_watchdog()
            function_calls = getattr(tool_call, "function_calls", [])
            for fc in function_calls:
                await self.dispatch_tool_call(session, fc)

    async def _receive_from_alfred(self, session: Any) -> None:
        """Receives 24kHz audio chunks, transcripts, and tool calls from Gemini Live API with automatic stream recovery."""
        while self.is_running:
            try:
                async for response in session.receive():
                    if not self.is_running:
                        break
                    await self.process_server_response(response, session)
            except asyncio.CancelledError:
                break
            except Exception as e:
                if not self.is_running:
                    break
                logger.error("[A.L.F.R.E.D.] Error in Live API receive stream: %s. Initiating stream recovery.", e)
                # Break out to terminate TaskGroup and trigger automatic reconnection loop
                break

    async def send_startup_briefing(self, session: Any) -> bool:
        """Queries fast diagnostics & briefing notes and triggers initial executive greeting turn."""
        if self._initial_briefing_sent:
            return False

        try:
            # Fast non-blocking telemetry summary
            cpu_val = round(psutil.cpu_percent(interval=None), 1)
            ram_val = round(psutil.virtual_memory().percent, 1)
            briefing = ""
            if "manage_executive_briefing" in self.tool_map:
                fn = self.tool_map["manage_executive_briefing"]
                try:
                    briefing = (
                        await fn(action="list")
                        if inspect.iscoroutinefunction(fn)
                        else await asyncio.to_thread(fn, action="list")
                    )
                except Exception:
                    pass

            prompt = (
                f"[SYSTEM EVENT: The Director has logged into the executive console. "
                f"System Diagnostics: CPU {cpu_val}%, RAM {ram_val}%. "
                f"Executive Briefing Notes: {briefing}. "
                f"Greet the Director with an articulate, composed, and concise 2-sentence executive status and agenda briefing.]"
            )
            logger.info("[ALFRED CORE] Triggering Executive Startup Briefing turn (CPU: %s%%, RAM: %s%%)...", cpu_val, ram_val)
            self.set_status("thinking")
            self._arm_thinking_watchdog(fallback_text="Startup Briefing")
            await session.send(input=prompt, end_of_turn=True)
            self._initial_briefing_sent = True
            return True
        except Exception as e:
            logger.warning("[ALFRED CORE] Failed to dispatch startup briefing: %s", e)
            return False

    async def _delayed_startup_briefing(self, session: Any) -> None:
        """Waits 0.5s after connection to ensure receive and mic streams are running, then sends greeting."""
        try:
            await asyncio.sleep(0.5)
            success = await self.send_startup_briefing(session)
            if not success:
                self._startup_briefing_completed.set()
                self.set_status("listening")
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.warning("[ALFRED CORE] Delayed startup briefing encountered error: %s", e)
            self._startup_briefing_completed.set()
            self.set_status("listening")

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
        connect_kwargs: Dict[str, Any] = {
            "response_modalities": ["AUDIO"],
            "system_instruction": types.Content(
                parts=[types.Part.from_text(text=get_dynamic_system_prompt(self.memory))]
            ),
            "speech_config": types.SpeechConfig(
                voice_config=types.VoiceConfig(
                    prebuilt_voice_config=types.PrebuiltVoiceConfig(
                        voice_name=self.voice_name
                    )
                )
            ),
            "tools": self.tools_list,
        }
        if hasattr(types, "AudioTranscriptionConfig"):
            try:
                connect_kwargs["input_audio_transcription"] = types.AudioTranscriptionConfig()
                connect_kwargs["output_audio_transcription"] = types.AudioTranscriptionConfig()
            except Exception as ex:
                logger.debug("Could not configure audio transcription config: %s", ex)

        config = types.LiveConnectConfig(**connect_kwargs)

        logger.info("[ALFRED CORE] Connecting to Gemini Live API (%s)...", self.model_id)
        self.update_transcript(f"[LIVE API]: Connecting to Gemini Live API ({self.model_id})...")

        try:
            async with self.client.aio.live.connect(model=self.model_id, config=config) as session:
                self._session = session
                self._startup_briefing_completed.clear()
                self._model_turn_open = False
                self.set_status("thinking")
                connected_msg = f"[LIVE API]: Connected to {self.model_id} (Voice: {self.voice_name}). Standing by, Sir."
                logger.info(connected_msg)
                self.update_transcript(connected_msg)

                async with asyncio.TaskGroup() as tg:
                    tg.create_task(self._stream_mic_to_alfred(session))
                    tg.create_task(self._receive_from_alfred(session))
                    tg.create_task(self._delayed_startup_briefing(session))

        except Exception as e:
            disconnect_msg = f"[LIVE API DISCONNECTED]: {e}"
            logger.error(disconnect_msg)
            self.update_transcript(disconnect_msg)
        finally:
            self._disarm_thinking_watchdog()
            self._disarm_speaking_watchdog()
            if self._drain_task and not self._drain_task.done():
                self._drain_task.cancel()
            self.is_running = False
            self._model_turn_open = False
            self._startup_briefing_completed.set()
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
        self.stop_game_overwatch()
        self._disarm_thinking_watchdog()
        self._disarm_speaking_watchdog()
        if self._drain_task and not self._drain_task.done():
            self._drain_task.cancel()
        self.is_running = False
        self._model_turn_open = False
        self._startup_briefing_completed.set()
        await self.audio_manager.stop()
        self.set_status("idle")
