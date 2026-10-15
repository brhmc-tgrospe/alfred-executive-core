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
