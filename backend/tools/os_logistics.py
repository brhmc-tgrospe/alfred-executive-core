"""A.L.F.R.E.D. OS Logistics & Executive Tools.

Provides system telemetry diagnostics, safe application launching,
screen inspection integration, and a non-hanging 30-second security approval
gate for high-risk terminal commands.
All functions use strict Python type hints and docstrings for google-genai schema reflection.
"""

from __future__ import annotations

import asyncio
import os
import re
import subprocess
import sys
import uuid
import webbrowser
from typing import Awaitable, Callable, Optional
import psutil

from backend.memory.memory_store import MemoryStore
from backend.vision_manager import VisionManager

# High-risk command patterns requiring explicit human authorization
HIGH_RISK_PATTERN = re.compile(
    r"\b(rm|del|rmdir|rd|Remove-Item|ri|taskkill|Stop-Process|spps|git\s+push|format|reg|shutdown|mkfs|dd)\b",
    re.IGNORECASE,
)


class OSLogistics:
    """Executive OS Logistics tool suite with human-in-the-loop safety gate."""

    def __init__(
        self,
        memory_store: Optional[MemoryStore] = None,
        vision_manager: Optional[VisionManager] = None,
        approval_hook: Optional[Callable[[dict], Awaitable[None]]] = None,
        approval_timeout: float = 30.0,
    ) -> None:
        self.memory = memory_store or MemoryStore()
        self.vision = vision_manager or VisionManager()
        self.approval_hook = approval_hook
        self.approval_timeout = approval_timeout
        self._pending_approvals: dict[str, asyncio.Future[bool]] = {}

    def is_high_risk_command(self, command: str) -> bool:
        """Determines if a shell command carries risk of data loss or process termination."""
        return bool(HIGH_RISK_PATTERN.search(command.strip()))

    def resolve_approval(self, req_id: str, approved: bool) -> bool:
        """Resolves a pending executive authorization request from HUD or WebSocket."""
        future = self._pending_approvals.get(req_id)
        if future is not None and not future.done():
            future.set_result(approved)
            return True
        return False

    def get_system_diagnostics(self) -> str:
        """Returns real-time operating system telemetry including CPU, RAM, disk, and top processes.

        Returns:
            A formatted diagnostic briefing of system health and resource consumption.
        """
        try:
            cpu = psutil.cpu_percent(interval=None)
            mem = psutil.virtual_memory()
            disk = psutil.disk_usage(os.path.abspath(os.sep))

            battery = psutil.sensors_battery()
            battery_str = f"{battery.percent}% {'(Plugged in)' if battery.power_plugged else '(On battery)'}" if battery else "N/A (Desktop)"

            # Get top 5 processes by memory usage
            processes = []
            for p in psutil.process_iter(["pid", "name", "memory_percent", "cpu_percent"]):
                try:
                    processes.append(p.info)
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass

            processes.sort(key=lambda x: x.get("memory_percent") or 0.0, reverse=True)
            top_procs = processes[:5]

            proc_lines = []
            for p in top_procs:
                name = p.get("name") or "Unknown"
                mem_pct = p.get("memory_percent") or 0.0
                proc_lines.append(f"  • {name} (PID {p.get('pid')}): {mem_pct:.1f}% RAM")

            diagnostics = [
                "System Diagnostics Telemetry:",
                f"• CPU Utilization: {cpu:.1f}%",
                f"• Memory Usage: {mem.percent:.1f}% ({mem.used // (1024**2)}MB / {mem.total // (1024**2)}MB)",
                f"• Disk Space: {disk.percent:.1f}% used ({disk.free // (1024**3)}GB free)",
                f"• Battery Status: {battery_str}",
                "• Top Resource Processes:",
                *proc_lines,
            ]
            return "\n".join(diagnostics)
        except Exception as e:
            return f"Failed to retrieve system diagnostics: {e}"

    def launch_application_or_url(self, target: str) -> str:
        """Opens a web URL in the default browser or launches a local desktop application safely.

        Args:
            target: The URL (http/https) or executable path / application name to open.

        Returns:
            Status message confirming the application or URL launch.
        """
        target_clean = target.strip()
        if not target_clean:
            return "Error: Cannot launch an empty target."

        if target_clean.startswith("http://") or target_clean.startswith("https://"):
            try:
                webbrowser.open(target_clean)
                return f"Opening browser to '{target_clean}', Sir."
            except Exception as e:
                return f"Failed to open URL '{target_clean}': {e}"

        # Local application execution
        try:
            if sys.platform == "win32":
                os.startfile(target_clean)
            else:
                subprocess.Popen([target_clean], shell=False)
            return f"Launched application '{target_clean}', Sir."
        except Exception as e:
            return f"Failed to launch application '{target_clean}': {e}"

    def inspect_active_screen(self, question: str) -> str:
        """Captures a screenshot of the active monitor so ALFRED can analyze code, documents, or errors.

        Args:
            question: Specific visual question or element to look for on the screen.

        Returns:
            Confirmation of visual capture with resolution metadata.
        """
        try:
            jpeg_bytes = self.vision.capture_screen_jpeg()
            w, h = self.vision.get_image_dimensions(jpeg_bytes)
            return f"Screen frame captured ({w}x{h}px, {len(jpeg_bytes)//1024}KB). Visual analysis for: '{question}'."
        except Exception as e:
            return f"Screen inspection failed: {e}"

    def manage_executive_briefing(self, action: str, task_item: str = "") -> str:
        """Manages the daily executive briefing tasks (add, list, complete).

        Args:
            action: Action to perform. Options: 'add', 'list', 'complete'.
            task_item: The task description or ID to manage.

        Returns:
            Status briefing from the executive agenda database.
        """
        return self.memory.manage_executive_briefing(action=action, task_item=task_item)

    def remember_fact(self, category: str, content: str) -> str:
        """Stores a persistent fact or preference into semantic vector memory.

        Args:
            category: Tag classification (e.g. 'preference', 'project', 'client').
            content: The specific fact to commit to long-term memory.

        Returns:
            Confirmation that the fact has been memorized.
        """
        return self.memory.remember_fact(category=category, content=content)

    def recall_context(self, query: str) -> str:
        """Recalls relevant semantic facts and preferences based on a query.

        Args:
            query: The subject or question to look up in semantic memory.

        Returns:
            Relevant retrieved memories formatted as context.
        """
        return self.memory.recall_context(query=query)

    async def execute_terminal_command(self, command: str) -> str:
        """Executes a shell command with an automated human-in-the-loop security gate for high-risk actions.

        Args:
            command: The terminal command to execute.

        Returns:
            Command stdout/stderr output or authorization status.
        """
        cmd_clean = command.strip()
        if not cmd_clean:
            return "Error: Cannot execute an empty terminal command."

        # Check for destructive/high-risk command
        if self.is_high_risk_command(cmd_clean):
            req_id = f"req-{uuid.uuid4().hex[:6]}"
            loop = asyncio.get_running_loop()
            future: asyncio.Future[bool] = loop.create_future()
            self._pending_approvals[req_id] = future

            # Broadcast pending approval payload to HUD / WebSocket
            if self.approval_hook is not None:
                payload = {
                    "id": req_id,
                    "action": "execute_terminal_command",
                    "command": cmd_clean,
                    "risk_level": "high",
                }
                try:
                    await self.approval_hook(payload)
                except Exception as e:
                    print(f"[OSLogistics] Error dispatching approval hook: {e}")

            print(f"[A.L.F.R.E.D. SAFETY GATE] High-risk command '{cmd_clean}' intercepted ({req_id}). Awaiting Director authorization...")

            # Await authorization with 30-second non-hanging timeout
            try:
                approved = await asyncio.wait_for(future, timeout=self.approval_timeout)
            except asyncio.TimeoutError:
                self._pending_approvals.pop(req_id, None)
                return f"Execution aborted: Authorization timed out after {int(self.approval_timeout)} seconds without confirmation."
            finally:
                self._pending_approvals.pop(req_id, None)

            if not approved:
                return f"Execution aborted: Command '{cmd_clean}' was denied by the Director."

        # Execute command safely via subprocess
        try:
            result = await asyncio.to_thread(
                subprocess.run,
                cmd_clean,
                shell=True,
                capture_output=True,
                text=True,
                timeout=15,
            )
            stdout = result.stdout.strip()
            stderr = result.stderr.strip()

            if result.returncode == 0:
                return stdout if stdout else "Command executed successfully (no output)."
            return f"Command exited with code {result.returncode}:\n{stderr or stdout}"
        except subprocess.TimeoutExpired:
            return f"Command execution timed out after 15 seconds."
        except Exception as e:
            return f"Command execution failed: {e}"
