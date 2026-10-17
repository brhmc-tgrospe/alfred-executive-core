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
from typing import Any, Dict, List, Optional, Set
import psutil
import httpx
from bs4 import BeautifulSoup

from backend.vision_manager import VisionManager

# Standard developer service ports
COMMON_DEV_PORTS: Set[int] = {80, 443, 3000, 5173, 8000, 8080, 3306, 8765}

# High-speed built-in shortcut and icon dictionary for executive interfaces
SOFTWARE_SHORTCUTS_AND_ICONS: Dict[str, Dict[str, str]] = {
    "word": {
        "save": "Ctrl+S (Save active document / floppy disk icon)",
        "bold": "Ctrl+B (Toggle bold on selection / 'B' icon in Home ribbon)",
        "italic": "Ctrl+I (Toggle italics / 'I' icon in Home ribbon)",
        "underline": "Ctrl+U (Toggle underline / 'U' icon)",
        "track changes": "Ctrl+Shift+E (Review ribbon -> Tracking -> Track Changes)",
        "comment": "Ctrl+Alt+M (Insert new comment / speech bubble icon with +)",
        "find": "Ctrl+F (Navigation pane / magnifying glass icon)",
        "replace": "Ctrl+H (Find and replace dialog)",
        "heading 1": "Ctrl+Alt+1 (Apply Heading 1 style)",
        "heading 2": "Ctrl+Alt+2 (Apply Heading 2 style)",
        "ribbon": "Alt or F10 (Activates ribbon access keys: Alt+H Home, Alt+N Insert, Alt+P Layout, Alt+R Review)",
        "undo": "Ctrl+Z (Curved arrow pointing left)",
        "redo": "Ctrl+Y (Curved arrow pointing right)",
        "word count": "Ctrl+Shift+G (Review ribbon -> Word Count)",
    },
    "excel": {
        "autosum": "Alt+= (Sigma ∑ icon in Editing group / AutoSum)",
        "filter": "Ctrl+Shift+L (Data ribbon -> Filter funnel icon)",
        "pivottable": "Alt+N+V (Insert -> PivotTable grid table icon)",
        "freeze panes": "Alt+W+F (View ribbon -> Freeze Panes with split line icon)",
        "format cells": "Ctrl+1 (Opens Format Cells dialog)",
        "insert row": "Ctrl+Shift++ (with row selected)",
        "delete row": "Ctrl+- (with row selected)",
        "flash fill": "Ctrl+E (Data ribbon -> Flash Fill lightning icon)",
        "save": "Ctrl+S (Floppy disk icon)",
        "sort": "Data -> Sort A to Z or Z to A icons",
    },
    "vscode": {
        "command palette": "Ctrl+Shift+P or F1 (Top central search bar)",
        "quick open": "Ctrl+P (Search files by name)",
        "toggle terminal": "Ctrl+` (Backtick - opens/closes integrated terminal)",
        "source control": "Ctrl+Shift+G (Git branch icon on activity bar)",
        "multi cursor": "Alt+Click or Ctrl+Alt+Up/Down",
        "format document": "Shift+Alt+F (Formats active source file)",
        "comment line": "Ctrl+/ (Toggles line comment)",
        "split editor": "Ctrl+\\ (Split editor right icon in tab corner)",
        "zen mode": "Ctrl+K Z (Full screen zen distraction-free mode)",
        "find in files": "Ctrl+Shift+F (Magnifying glass in activity bar)",
    },
    "browser": {
        "inspect": "Ctrl+Shift+I or F12 (Opens Chrome/Edge DevTools)",
        "hard refresh": "Ctrl+F5 or Ctrl+Shift+R (Bypasses cache)",
        "reopen closed tab": "Ctrl+Shift+T (Restores last closed tab)",
        "new incognito": "Ctrl+Shift+N (Private browsing window)",
        "dev tools console": "Ctrl+Shift+J (Directly opens DevTools Console tab)",
        "toggle device toolbar": "Ctrl+Shift+M (Mobile responsive simulator)",
        "clear browsing data": "Ctrl+Shift+Del",
        "downloads": "Ctrl+J",
        "bookmark": "Ctrl+D (Star icon in address bar)",
    },
}


# Statutory, legal, and domain reference corpus for instant offline/hybrid executive synthesis
STATUTORY_AND_DOMAIN_KNOWLEDGE: Dict[str, str] = {
    "labor code": (
        "Philippine Labor Code (Presidential Decree No. 442, as amended): "
        "Book I (Pre-Employment), Book II (Human Resources Development), "
        "Book III (Conditions of Employment: Art. 83 Normal Hours of Work = 8 hours/day; Art. 87 Overtime Work +25% regular / +30% holiday or rest day; Art. 91-93 Weekly Rest Periods & Holiday Pay; Art. 95 Service Incentive Leave = 5 days with pay after 1 year of service), "
        "Book IV (Health, Safety and Social Welfare Benefits), Book V (Labor Relations & Collective Bargaining), "
        "Book VI (Post-Employment: Art. 294 [formerly 279] Security of Tenure; Art. 297 [282] Just Causes for Termination requiring Twin-Notice & Hearing procedural due process; Art. 298-299 [283-284] Authorized Causes & Separation Pay)."
    ),
    "civil service": (
        "Civil Service Commission (CSC) Laws & Rules (1987 Constitution Art. IX-B; E.O. No. 292 Book V; 2017 ORAOHRA & 2017 RACCS): "
        "Governs all branches, subdivisions, instrumentalities, and agencies of the Philippine Government. "
        "Appointments are classified into Career Service (First, Second, and Third Levels requiring CSC Eligibility/CSPE) and Non-Career Service. "
        "Omnibus Rules on Leave: 15 days Vacation Leave (VL) and 15 days Sick Leave (SL) annually with full pay (cumulative), plus 3 days Special Privilege Leave (SPL) and 5 days Mandatory/Forced Leave. "
        "Security of tenure guarantees no civil service officer or employee shall be suspended or dismissed except for cause provided by law and after due process under the 2017 Rules on Administrative Cases in the Civil Service (RACCS)."
    ),
    "csc": (
        "Civil Service Commission (CSC) Statutory Digest (E.O. 292 / ORAOHRA / RACCS): "
        "Merit and fitness principle via competitive examination; 8 hours/day and 40 hours/week government work schedule; "
        "15 days Vacation Leave + 15 days Sick Leave cumulative credits per year; strict administrative due process (Formal Charge / Show-Cause Order, Answer, Investigation, Decision) for grave, less grave, and light offenses."
    ),
}


class DevLogistics:
    """Developer logistics tools for repository analysis, port auditing, network diagnostics, and deep topic/statutory research."""

    def __init__(self, vision_manager: Optional[VisionManager] = None, memory_store: Optional[Any] = None) -> None:
        self.vision = vision_manager or VisionManager()
        self.memory = memory_store

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

    def research_software_interface_and_docs(
        self, application_name: str, feature_or_icon_query: str = "", probe_hover_tooltip: bool = False
    ) -> str:
        """Researches official documentation, statutory/legal codes, technical frameworks, keyboard shortcuts, and UI icons, automatically persisting synthesized knowledge into long-term memory.

        Args:
            application_name: Name of target software, domain, or statute (e.g. 'Word', 'VS Code', 'Philippine Labor Code', 'Civil Service Commission').
            feature_or_icon_query: Specific topic, law, feature, icon, or action to research (e.g. 'Philippine Labor Code and CSC laws', 'track changes', 'extrude mesh').
            probe_hover_tooltip: If True, hovers at cursor for 450ms and captures a 2.0x Cursor Magnifier frame for tooltip inspection.

        Returns:
            Structured research digest with verified provisions/shortcuts and confirmation of semantic memory persistence.
        """
        app_clean = (application_name or "").strip()
        query_clean = (feature_or_icon_query or "").strip()
        if not app_clean and not query_clean:
            return "Error: Both application_name and feature_or_icon_query cannot be empty."
        if not query_clean:
            query_clean = app_clean
        if not app_clean:
            app_clean = "General Knowledge & Statutory Research"

        app_lower = app_clean.lower()
        query_lower = query_clean.lower()
        combined_lower = f"{app_lower} {query_lower}"

        # 1. Match against built-in high-speed software shortcut knowledge base
        matched_category = None
        if "word" in app_lower:
            matched_category = "word"
        elif "excel" in app_lower:
            matched_category = "excel"
        elif any(k in app_lower for k in ("code", "vs", "antigravity")):
            matched_category = "vscode"
        elif any(k in app_lower for k in ("chrome", "edge", "browser", "firefox", "brave")):
            matched_category = "browser"

        doc_result = None
        source_label = "Built-in High-Speed Interface Cache"
        synthesized_chunks: List[str] = []

        if matched_category and matched_category in SOFTWARE_SHORTCUTS_AND_ICONS:
            cat_dict = SOFTWARE_SHORTCUTS_AND_ICONS[matched_category]
            for key, val in cat_dict.items():
                if key in query_lower or query_lower in key:
                    doc_result = f"• Action/Feature: {key.title()}\n• Shortcut / UI Guidance: {val}"
                    synthesized_chunks.append(f"[{app_clean} - {key.title()}]: {val}")
                    break

        # 2. Match against Statutory & Domain Reference Corpus (e.g. Philippine Labor Code, CSC Laws)
        statutory_matches: List[str] = []
        for stat_key, stat_summary in STATUTORY_AND_DOMAIN_KNOWLEDGE.items():
            if stat_key in combined_lower:
                if stat_summary not in statutory_matches:
                    statutory_matches.append(stat_summary)

        if statutory_matches and not doc_result:
            source_label = "Executive Statutory & Domain Reference Corpus + Web Digest"
            for sm in statutory_matches:
                synthesized_chunks.append(sm)
            doc_result = "\n".join(f"• Statutory/Domain Provision: {sm}" for sm in statutory_matches)

        # 3. Live Web / Reference Scraper (strict 8.0s HTTP timeout)
        if not matched_category or not doc_result:
            if not doc_result:
                source_label = "Live Documentation & Topic Researcher"
            try:
                is_statutory_or_topic = bool(statutory_matches) or any(
                    w in combined_lower for w in ("law", "code", "csc", "civil service", "statute", "labor", "rule", "republic act", "policy")
                )
                search_query = (
                    f"{app_clean} {query_clean}"
                    if is_statutory_or_topic
                    else f"{app_clean} {query_clean} shortcut manual documentation"
                )
                url = f"https://html.duckduckgo.com/html/?q={search_query.replace(' ', '+')}"
                headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) ALFRED-Executive-Core/1.0"}
                resp = httpx.get(url, headers=headers, timeout=8.0, follow_redirects=True)
                if resp.status_code == 200:
                    soup = BeautifulSoup(resp.text, "html.parser")
                    snippets = []
                    for res in soup.find_all("a", class_="result__snippet", limit=4):
                        txt = res.get_text(strip=True)
                        if txt:
                            snippets.append(txt)
                    if not snippets:
                        for el in soup.find_all(["p", "li", "main"], limit=6):
                            txt = el.get_text(strip=True)
                            if len(txt) > 20:
                                snippets.append(txt)
                                if len(snippets) >= 3:
                                    break
                    if snippets:
                        joined_snippets = " ".join(snippets)[:650]
                        synthesized_chunks.append(joined_snippets)
                        if doc_result:
                            doc_result += f"\n• Web Reference Digest: {joined_snippets}"
                        else:
                            doc_result = f"• Retrieved Manual/Reference Snippet: {joined_snippets}\n• Search Target: '{search_query}'"
            except Exception as e:
                if not doc_result:
                    doc_result = (
                        f"• Standard Guidance: In {app_clean}, look for '{query_clean}' under the main menu bar or search with F1/Ctrl+Shift+P.\n"
                        f"• Diagnostic note: Web scraper offline/timeout ({e})."
                    )

        if not doc_result:
            doc_result = (
                f"• Guidance: Navigate to {app_clean} menu options or settings, or press Alt to reveal ribbon/menu access keys for '{query_clean}'."
            )

        # 4. Auto-Persist Synthesized Knowledge into Long-Term Semantic Memory (ChromaDB + SQLite)
        memory_status = "Skipped (no memory store attached)"
        if self.memory is not None and hasattr(self.memory, "remember_fact"):
            try:
                knowledge_payload = (
                    f"Topic [{app_clean} — {query_clean}]: "
                    + (" | ".join(synthesized_chunks) if synthesized_chunks else doc_result)
                )
                self.memory.remember_fact(category="research_knowledge", content=knowledge_payload[:1200])
                memory_status = "Committed to long-term semantic memory (category='research_knowledge')"
            except Exception as mem_err:
                memory_status = f"Persistence warning: {mem_err}"

        output_lines = [
            "=== Deep Topic, Statutory & Documentation Research Digest ===",
            f"• Target Domain / Application: {app_clean}",
            f"• Research Query: '{query_clean}'",
            f"• Knowledge Source: {source_label}",
            f"• Semantic Memory Ingestion: {memory_status}",
            doc_result,
        ]

        # 5. Native Hover Tooltip Probe (Constraint 5b)
        if probe_hover_tooltip:
            try:
                time.sleep(0.45)  # 450ms hover pause for native OS tooltip to render
                self.vision.capture_cursor_magnifier_jpeg()
                output_lines.append(
                    "• [Visual Tooltip Probe]: 450ms cursor hover executed. 2.0x Cursor Magnifier frame captured and injected for tooltip OCR inspection."
                )
            except Exception as err:
                output_lines.append(f"• [Visual Tooltip Probe]: Failed to capture tooltip frame: {err}")

        return "\n".join(output_lines)
