"""Unit tests for System Developer Logistics Suite (backend/tools/dev_logistics.py)."""

import os
import pytest
from backend.tools.dev_logistics import DevLogistics


@pytest.fixture
def dev():
    return DevLogistics()


def test_inspect_git_workspace_current_repo(dev):
    """Verifies git workspace telemetry on the active git repository."""
    result = dev.inspect_git_workspace(".")
    assert "=== Git Workspace Telemetry" in result
    assert "Branch:" in result
    assert "[Status Summary]" in result
    assert "[Recent Commits" in result


def test_inspect_git_workspace_nonexistent_path(dev):
    """Verifies graceful error message for non-existent path."""
    result = dev.inspect_git_workspace("non_existent_directory_xyz123")
    assert "Error: Repository path" in result
    assert "does not exist" in result


def test_inspect_local_dev_ports_general(dev):
    """Verifies port auditing across standard developer ports."""
    result = dev.inspect_local_dev_ports(port=0)
    assert isinstance(result, str)
    assert len(result) > 0


def test_inspect_local_dev_ports_specific_free_port(dev):
    """Verifies querying an unoccupied high port reports it as free."""
    result = dev.inspect_local_dev_ports(port=59871)
    assert "is currently free" in result


def test_probe_network_target_google_dns(dev):
    """Verifies TCP probe against 8.8.8.8:53."""
    result = dev.probe_network_target(host="8.8.8.8", port=53)
    assert "Network Target Telemetry" in result
    assert "8.8.8.8" in result
    assert ("ONLINE" in result or "Latency" in result)


def test_probe_network_target_invalid_host(dev):
    """Verifies DNS error on unresolvable host."""
    result = dev.probe_network_target(host="unresolvable.invalid.domain.abc12345xyz")
    assert "DNS resolution failed" in result


def test_tail_log_file_success(dev, tmp_path):
    """Verifies reading trailing lines from a log file."""
    log_file = tmp_path / "test_alfred.log"
    lines = [f"2026-10-15 [INFO] Log entry #{i}" for i in range(1, 51)]
    log_file.write_text("\n".join(lines), encoding="utf-8")

    result = dev.tail_log_file(str(log_file), lines=10)
    assert "=== Log Tail [" in result
    assert "Last 10 lines" in result
    assert "Log entry #50" in result
    assert "Log entry #41" in result
    # Earlier entries should not be present in the 10-line tail
    assert "Log entry #1\n" not in result


def test_tail_log_file_nonexistent(dev):
    """Verifies error handling on missing log file."""
    result = dev.tail_log_file("missing_log_file_123.log")
    assert "Error: Log file not found" in result


def test_tail_log_file_empty(dev, tmp_path):
    """Verifies empty log file handling."""
    empty_log = tmp_path / "empty.log"
    empty_log.write_text("", encoding="utf-8")
    result = dev.tail_log_file(str(empty_log), lines=5)
    assert "is currently empty" in result


def test_audit_source_file_success(dev, tmp_path):
    """Verifies source code file structural auditing and symbol extraction."""
    src_file = tmp_path / "sample_service.py"
    code = (
        "class UserService:\n"
        "    def __init__(self):\n"
        "        self.active = True\n"
        "\n"
        "    async def fetch_user(self, user_id: str):\n"
        "        return {'id': user_id}\n"
    )
    src_file.write_text(code, encoding="utf-8")

    result = dev.audit_source_file(str(src_file), max_lines=20)
    assert "=== Source Code Audit: [sample_service.py] ===" in result
    assert "UserService" in result
    assert "fetch_user" in result
    assert "class UserService" in result
    assert "async def fetch_user" in result
    assert "6 lines" in result


def test_audit_source_file_nonexistent(dev):
    """Verifies graceful error on missing source file."""
    result = dev.audit_source_file("nonexistent_component.tsx")
    assert "Error: Source file" in result
    assert "does not exist" in result


def test_inspect_sqlite_database_success(dev, tmp_path):
    """Verifies SQLite database schema and row count inspection."""
    import sqlite3
    db_file = tmp_path / "test_alfred.db"
    conn = sqlite3.connect(str(db_file))
    cur = conn.cursor()
    cur.execute("CREATE TABLE tasks (id INTEGER PRIMARY KEY, title TEXT, priority INTEGER);")
    cur.execute("INSERT INTO tasks (title, priority) VALUES ('Deploy HUD', 1);")
    cur.execute("INSERT INTO tasks (title, priority) VALUES ('Audit Logs', 2);")
    conn.commit()
    conn.close()

    result = dev.inspect_sqlite_database(str(db_file))
    assert "=== SQLite Database Schema [test_alfred.db] ===" in result
    assert "Table 'tasks' (2 rows):" in result
    assert "title (TEXT)" in result
    assert "priority (INTEGER)" in result
    assert "id (INTEGER) [PK]" in result


def test_inspect_sqlite_database_nonexistent(dev):
    """Verifies error handling on missing SQLite database."""
    result = dev.inspect_sqlite_database("nonexistent_database_999.db")
    assert "Error: SQLite database file not found" in result


def test_multi_target_network_sweep(dev):
    """Verifies concurrent network sweep across multiple target hosts."""
    targets = "8.8.8.8,1.1.1.1,127.0.0.1"
    result = dev.multi_target_network_sweep(hosts_csv=targets, port=53)
    assert "=== Multi-Target Network Sweep (Port 53/TCP) ===" in result
    assert "Targets Scanned: 3" in result
    assert "8.8.8.8" in result
    assert "1.1.1.1" in result
    assert "127.0.0.1" in result


def test_multi_target_network_sweep_empty(dev):
    """Verifies error on empty hosts string."""
    result = dev.multi_target_network_sweep(hosts_csv="", port=53)
    assert "Error: hosts_csv must contain at least one valid host target." in result
