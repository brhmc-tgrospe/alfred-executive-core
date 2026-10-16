"""A.L.F.R.E.D. System Developer Logistics Suite.

Provides developer-centric inspection tools:
1. inspect_git_workspace: Git branch, status, diff stats, and recent commits.
2. inspect_local_dev_ports: Process inspection on active developer ports via psutil.
3. probe_network_target: DNS resolution and TCP connection latency measurement.
4. tail_log_file: Safe inspection of local log files and stack traces.
5. audit_source_file: Reads source code files, detects declared symbols, and provides previews.
6. inspect_sqlite_database: Lists schema, tables, column types, and row counts of local databases.
7. multi_target_network_sweep: Concurrently probes latency and reachability across multiple hosts.

All functions expose strict primitive type hints (str, int, bool) and docstrings
for clean schema registration with the Gemini Multimodal Live API.
"""

from __future__ import annotations

import collections
from concurrent.futures import ThreadPoolExecutor, as_completed
import os
import re
import socket
import sqlite3
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

    def audit_source_file(self, file_path: str, max_lines: int = 120) -> str:
        """Reads a source code file (PHP, Vue, TS, Python, JS, etc.), analyzes its structure, and returns key contents.

        Args:
            file_path: Relative or absolute path to the source file to audit.
            max_lines: Maximum number of lines of content to return (default 120, capped between 10 and 500).

        Returns:
            Structural audit including file size, total lines, detected classes/functions/symbols, and source lines.
        """
        path_clean = file_path.strip().strip("\"'")
        if not path_clean:
            return "Error: file_path cannot be empty."

        abs_path = os.path.abspath(path_clean)
        if not os.path.exists(abs_path):
            return f"Error: Source file '{abs_path}' does not exist."
        if not os.path.isfile(abs_path):
            return f"Error: Path '{abs_path}' is not a regular file."

        limit = max(10, min(max_lines, 500))

        try:
            with open(abs_path, "r", encoding="utf-8", errors="replace") as f:
                lines = f.readlines()

            total_lines = len(lines)
            size_bytes = os.path.getsize(abs_path)

            # Detect key structural declarations across Python, TypeScript/JS, Vue, PHP, Rust, Go
            symbol_patterns = [
                re.compile(r"^\s*(async\s+def|def|class)\s+([a-zA-Z_][a-zA-Z0-9_]*)"),
                re.compile(r"^\s*(export\s+(?:default\s+)?(?:async\s+)?function|function|export\s+class|class|export\s+interface|interface|export\s+type|type)\s+([a-zA-Z_][a-zA-Z0-9_]*)"),
                re.compile(r"^\s*(?:export\s+)?const\s+([a-zA-Z_][a-zA-Z0-9_]*)\s*=\s*(?:async\s*)?\("),
            ]

            symbols: List[str] = []
            for idx, line in enumerate(lines):
                for pat in symbol_patterns:
                    m = pat.search(line)
                    if m:
                        if len(m.groups()) == 2:
                            symbols.append(f"Line {idx+1}: {m.group(1)} {m.group(2)}")
                        else:
                            symbols.append(f"Line {idx+1}: const {m.group(1)}")
                        break

            symbols_summary = "\n".join(symbols[:30]) if symbols else "No top-level class/function declarations detected."
            if len(symbols) > 30:
                symbols_summary += f"\n... and {len(symbols) - 30} more symbols."

            preview_lines = lines[:limit]
            preview = "".join(f"{i+1:4d} | {line}" for i, line in enumerate(preview_lines))
            truncated_notice = f"\n[... truncated {total_lines - limit} additional lines ...]" if total_lines > limit else ""

            return (
                f"=== Source Code Audit: [{os.path.basename(abs_path)}] ===\n"
                f"Path: {abs_path}\n"
                f"Metrics: {total_lines} lines | {size_bytes} bytes\n\n"
                f"[Declared Symbols ({len(symbols)})]\n"
                f"{symbols_summary}\n\n"
                f"[Source Content (First {len(preview_lines)} of {total_lines} lines)]\n"
                f"{preview}{truncated_notice}"
            )
        except Exception as e:
            return f"Error auditing source file '{abs_path}': {e}"

    def inspect_sqlite_database(self, db_path: str = "backend/memory/alfred_executive.db") -> str:
        """Lists all tables, row counts, and schema columns in a local SQLite database for backend debugging.

        Args:
            db_path: Path to the SQLite database file on disk (defaults to 'backend/memory/alfred_executive.db').

        Returns:
            Formatted report detailing tables, record counts, and column definitions.
        """
        path_clean = db_path.strip().strip("\"'")
        if not path_clean:
            return "Error: db_path cannot be empty."

        abs_path = os.path.abspath(path_clean)
        if not os.path.exists(abs_path):
            return f"Error: SQLite database file not found at '{abs_path}'."
        if not os.path.isfile(abs_path):
            return f"Error: Path '{abs_path}' is not a regular file."

        try:
            conn = sqlite3.connect(f"file:{abs_path}?mode=ro", uri=True)
            cursor = conn.cursor()

            # Query all user tables
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name;")
            tables = [row[0] for row in cursor.fetchall()]

            if not tables:
                conn.close()
                return f"SQLite Database [{os.path.basename(abs_path)}] is valid but contains no user tables."

            report_lines = [
                f"=== SQLite Database Schema [{os.path.basename(abs_path)}] ===",
                f"Location: {abs_path}",
                f"Tables Found: {len(tables)}\n",
            ]

            for table in tables:
                # Row count
                try:
                    cursor.execute(f"SELECT COUNT(*) FROM \"{table}\";")
                    row_count = cursor.fetchone()[0]
                except Exception:
                    row_count = "N/A"

                # Columns schema
                cursor.execute(f"PRAGMA table_info(\"{table}\");")
                cols = cursor.fetchall()
                col_defs = [f"{col[1]} ({col[2] or 'ANY'})" + (" [PK]" if col[5] else "") for col in cols]
                cols_str = ", ".join(col_defs) if col_defs else "No columns"

                report_lines.append(f"• Table '{table}' ({row_count} rows):")
                report_lines.append(f"  Columns: {cols_str}\n")

            conn.close()
            return "\n".join(report_lines)
        except Exception as e:
            return f"Error inspecting SQLite database at '{abs_path}': {e}"

    def multi_target_network_sweep(
        self, hosts_csv: str = "8.8.8.8,1.1.1.1,127.0.0.1", port: int = 53
    ) -> str:
        """Concurrently probes multiple IP addresses or hosts and reports latency and reachability status.

        Args:
            hosts_csv: Comma-separated list of hostnames or IP addresses to probe (e.g. '8.8.8.8,1.1.1.1,127.0.0.1').
            port: Destination TCP port to test connection on each target (default 53).

        Returns:
            Table of probe results with host, resolved IP, latency in milliseconds, and status.
        """
        targets = [h.strip() for h in hosts_csv.split(",") if h.strip()]
        if not targets:
            return "Error: hosts_csv must contain at least one valid host target."

        if len(targets) > 16:
            targets = targets[:16]

        def _probe_single(host: str) -> dict:
            t0 = time.perf_counter()
            try:
                ip = socket.gethostbyname(host)
            except Exception as e:
                return {
                    "host": host,
                    "ip": "N/A",
                    "status": f"DNS_FAIL ({e})",
                    "latency_ms": -1.0,
                }

            s = None
            try:
                s = socket.create_connection((ip, port), timeout=1.5)
                lat = round((time.perf_counter() - t0) * 1000.0, 1)
                return {
                    "host": host,
                    "ip": ip,
                    "status": "ONLINE",
                    "latency_ms": lat,
                }
            except socket.timeout:
                return {
                    "host": host,
                    "ip": ip,
                    "status": "TIMEOUT",
                    "latency_ms": -1.0,
                }
            except ConnectionRefusedError:
                lat = round((time.perf_counter() - t0) * 1000.0, 1)
                return {
                    "host": host,
                    "ip": ip,
                    "status": "PORT_CLOSED",
                    "latency_ms": lat,
                }
            except Exception as e:
                return {
                    "host": host,
                    "ip": ip,
                    "status": f"FAIL ({e})",
                    "latency_ms": -1.0,
                }
            finally:
                if s:
                    try:
                        s.close()
                    except Exception:
                        pass

        results = []
        with ThreadPoolExecutor(max_workers=min(len(targets), 8)) as executor:
            future_to_host = {executor.submit(_probe_single, h): h for h in targets}
            for fut in as_completed(future_to_host):
                results.append(fut.result())

        # Sort results in original order
        order = {h: i for i, h in enumerate(targets)}
        results.sort(key=lambda r: order.get(r["host"], 999))

        lines = [
            f"=== Multi-Target Network Sweep (Port {port}/TCP) ===",
            f"Targets Scanned: {len(results)}\n",
        ]
        for r in results:
            lat_str = f"{r['latency_ms']} ms" if r["latency_ms"] >= 0 else "---"
            status_tag = f"[{r['status']}]"
            lines.append(f"• {r['host']:<18} -> {r['ip']:<15} | Port {port} | Latency: {lat_str:<9} | {status_tag}")

        return "\n".join(lines)
