"""A.L.F.R.E.D. System Developer Logistics Suite.

Provides developer-centric inspection tools:
1. inspect_git_workspace: Git branch, status, diff stats, and recent commits.
2. inspect_local_dev_ports: Process inspection on active developer ports via psutil.
3. probe_network_target: DNS resolution and TCP connection latency measurement.
4. tail_log_file: Safe inspection of local log files and stack traces.

All functions expose strict primitive type hints (str, int, bool) and docstrings
for clean schema registration with the Gemini Multimodal Live API.
"""

from __future__ import annotations

import collections
import os
import socket
import subprocess
import time
from typing import List, Set
import psutil

# Standard developer service ports
COMMON_DEV_PORTS: Set[int] = {80, 443, 3000, 5173, 8000, 8080, 3306, 8765}


class DevLogistics:
    """Developer logistics tools for repository analysis, port auditing, and network diagnostics."""

    def __init__(self) -> None:
        pass

    def inspect_git_workspace(self, repo_path: str = ".") -> str:
        """Inspects the local git repository: active branch, status, diff summary, and recent commits.

        Args:
            repo_path: Root path of the git repository to inspect (defaults to current directory).

        Returns:
            Formatted report detailing current branch, working tree changes, diff stat, and last 3 commits.
        """
        target_dir = os.path.abspath(repo_path)
        if not os.path.exists(target_dir):
            return f"Error: Repository path '{target_dir}' does not exist."

        try:
            # 1. Active branch
            branch_proc = subprocess.run(
                ["git", "branch", "--show-current"],
                cwd=target_dir,
                capture_output=True,
                text=True,
                timeout=5.0,
            )
            branch = branch_proc.stdout.strip() or "HEAD (detached)"

            # 2. Status short
            status_proc = subprocess.run(
                ["git", "status", "-sb"],
                cwd=target_dir,
                capture_output=True,
                text=True,
                timeout=5.0,
            )
            status_out = status_proc.stdout.strip() or "Clean working directory."

            # 3. Diff stat
            diff_proc = subprocess.run(
                ["git", "diff", "--stat"],
                cwd=target_dir,
                capture_output=True,
                text=True,
                timeout=5.0,
            )
            diff_out = diff_proc.stdout.strip() or "No unstaged changes."

            # 4. Last 3 commits
            log_proc = subprocess.run(
                ["git", "log", "-n", "3", "--oneline"],
                cwd=target_dir,
                capture_output=True,
                text=True,
                timeout=5.0,
            )
            log_out = log_proc.stdout.strip() or "No commit history."

            return (
                f"=== Git Workspace Telemetry [{target_dir}] ===\n"
                f"Branch: {branch}\n\n"
                f"[Status Summary]\n{status_out}\n\n"
                f"[Diff Stat]\n{diff_out}\n\n"
                f"[Recent Commits (Last 3)]\n{log_out}"
            )
        except subprocess.TimeoutExpired:
            return "Error: Git command timed out after 5.0 seconds."
        except FileNotFoundError:
            return "Error: 'git' executable not found on host system PATH."
        except Exception as e:
            return f"Error inspecting git repository: {e}"

    def inspect_local_dev_ports(self, port: int = 0) -> str:
        """Audits local TCP listening ports and identifies running developer server processes.

        Args:
            port: Specific port number to query (e.g. 8765, 5173). If 0, audits standard developer ports (80, 443, 3000, 5173, 8000, 8080, 3306, 8765).

        Returns:
            Table of active listening ports, PID, process name, and binding address.
        """
        target_ports = {port} if port > 0 else COMMON_DEV_PORTS
        found: List[str] = []

        try:
            connections = psutil.net_connections(kind="inet")
        except Exception as e:
            return f"Error querying local network connections: {e}"

        for conn in connections:
            if conn.status == psutil.CONN_LISTEN and conn.laddr:
                lport = conn.laddr.port
                if lport in target_ports:
                    pid = conn.pid or 0
                    pname = "unknown"
                    if pid > 0:
                        try:
                            proc = psutil.Process(pid)
                            pname = proc.name()
                        except (psutil.NoSuchProcess, psutil.AccessDenied):
                            pname = "access_denied"

                    ip_bind = conn.laddr.ip
                    found.append(f"- Port {lport}: PID {pid} ({pname}) bound to {ip_bind}")

        if not found:
            if port > 0:
                return f"Port {port} is currently free (no process listening)."
            return "All common developer ports (80, 443, 3000, 5173, 8000, 8080, 3306, 8765) are currently free."

        header = f"Active Developer Listening Ports ({len(found)} detected):\n"
        return header + "\n".join(sorted(found))

    def probe_network_target(self, host: str = "8.8.8.8", port: int = 53) -> str:
        """Resolves DNS and measures TCP round-trip latency in milliseconds to any host or IP.

        Args:
            host: Hostname or IP to probe (default '8.8.8.8').
            port: Destination TCP port to test connection (default 53).

        Returns:
            Latency telemetry report with resolved IP address and round-trip duration in milliseconds.
        """
        host_clean = host.strip()
        if not host_clean:
            return "Error: Host target cannot be empty."

        # 1. DNS Resolution
        try:
            resolved_ip = socket.gethostbyname(host_clean)
        except socket.gaierror as e:
            return f"DNS resolution failed for '{host_clean}': {e}"
        except Exception as e:
            return f"Host lookup error for '{host_clean}': {e}"

        # 2. TCP Latency Timing
        t0 = time.perf_counter()
        sock = None
        try:
            sock = socket.create_connection((resolved_ip, port), timeout=2.5)
            latency_ms = round((time.perf_counter() - t0) * 1000.0, 2)
            return (
                f"Network Target Telemetry:\n"
                f"- Target: {host_clean} (Resolved IP: {resolved_ip})\n"
                f"- Port: {port} (TCP)\n"
                f"- Status: REACHABLE / ONLINE\n"
                f"- Latency: {latency_ms} ms"
            )
        except socket.timeout:
            return f"Target {host_clean}:{port} ({resolved_ip}) timed out after 2.5s."
        except ConnectionRefusedError:
            latency_ms = round((time.perf_counter() - t0) * 1000.0, 2)
            return f"Target {host_clean}:{port} ({resolved_ip}) connection refused (latency: {latency_ms}ms, host active but port closed)."
        except Exception as e:
            return f"Connection probe failed for {host_clean}:{port} ({resolved_ip}): {e}"
        finally:
            if sock:
                try:
                    sock.close()
                except Exception:
                    pass

    def tail_log_file(self, log_path: str, lines: int = 25) -> str:
        """Safely reads the trailing lines of a local log file to diagnose exceptions and stack traces.

        Args:
            log_path: Path to the log file on disk.
            lines: Number of trailing lines to return (default 25, clamped between 1 and 200).

        Returns:
            The trailing lines of the log file, or an explanatory error.
        """
        path_clean = log_path.strip().strip("\"'")
        if not path_clean:
            return "Error: log_path cannot be empty."

        abs_path = os.path.abspath(path_clean)
        if not os.path.exists(abs_path):
            return f"Error: Log file not found at '{abs_path}'."
        if not os.path.isfile(abs_path):
            return f"Error: Path '{abs_path}' is not a regular file."

        num_lines = max(1, min(lines, 200))
        try:
            # Memory-efficient ring-buffer of trailing lines
            deque_lines: collections.deque[str] = collections.deque(maxlen=num_lines)
            with open(abs_path, "r", encoding="utf-8", errors="replace") as f:
                for line in f:
                    deque_lines.append(line.rstrip("\r\n"))

            if not deque_lines:
                return f"Log file '{abs_path}' is currently empty (0 bytes)."

            tail_content = "\n".join(deque_lines)
            return f"=== Log Tail [{abs_path}] (Last {len(deque_lines)} lines) ===\n{tail_content}"
        except PermissionError:
            return f"Permission denied reading log file at '{abs_path}'."
        except Exception as e:
            return f"Error reading log file at '{abs_path}': {e}"
