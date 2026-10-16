"""Unit tests for backend/tools/os_logistics.py.

Validates system diagnostics, high-risk detection, and all 3 security gate paths:
1. Approval granted
2. Approval denied
3. Approval timed out (non-hanging)
"""

import asyncio
import pytest
from backend.memory.memory_store import MemoryStore
from backend.tools.os_logistics import OSLogistics


@pytest.fixture
def logistics(tmp_path):
    db_file = str(tmp_path / "test_logistics.db")
    chroma_dir = str(tmp_path / "test_chroma")
    mem = MemoryStore(db_path=db_file, chroma_dir=chroma_dir)
    return OSLogistics(memory_store=mem, approval_timeout=0.2)  # fast 0.2s timeout for tests


def test_system_diagnostics(logistics):
    diag = logistics.get_system_diagnostics()
    assert "System Diagnostics Telemetry" in diag
    assert "CPU Utilization" in diag
    assert "Memory Usage" in diag


def test_high_risk_classifier(logistics):
    # Safe commands
    assert logistics.is_high_risk_command("echo hello world") is False
    assert logistics.is_high_risk_command("git status") is False
    assert logistics.is_high_risk_command("dir") is False

    # High-risk commands
    assert logistics.is_high_risk_command("del /f important.txt") is True
    assert logistics.is_high_risk_command("Remove-Item -Recurse .") is True
    assert logistics.is_high_risk_command("taskkill /F /IM chrome.exe") is True
    assert logistics.is_high_risk_command("git push origin main") is True
    assert logistics.is_high_risk_command("shutdown /s /t 0") is True


@pytest.mark.asyncio
async def test_execute_safe_command(logistics):
    out = await logistics.execute_terminal_command("echo ALFRED_ONLINE")
    assert "ALFRED_ONLINE" in out


@pytest.mark.asyncio
async def test_execute_high_risk_approval_granted(tmp_path):
    received_payloads = []

    async def mock_hook(payload):
        received_payloads.append(payload)

    log = OSLogistics(approval_hook=mock_hook, approval_timeout=1.0)

    # Launch high-risk command in background task
    task = asyncio.create_task(
        log.execute_terminal_command("del non_existent_dummy_file.tmp")
    )

    # Allow hook to trigger
    await asyncio.sleep(0.05)
    assert len(received_payloads) == 1
    req_id = received_payloads[0]["id"]
    assert req_id.startswith("req-")
    assert received_payloads[0]["risk_level"] == "high"

    # Simulate Director approving
    resolved = log.resolve_approval(req_id, approved=True)
    assert resolved is True

    result = await task
    # del on non-existent file will execute and return either exit code or message
    assert "aborted" not in result.lower()


@pytest.mark.asyncio
async def test_execute_high_risk_approval_denied(tmp_path):
    received_payloads = []

    async def mock_hook(payload):
        received_payloads.append(payload)

    log = OSLogistics(approval_hook=mock_hook, approval_timeout=1.0)

    task = asyncio.create_task(
        log.execute_terminal_command("taskkill /F /IM explorer.exe")
    )

    await asyncio.sleep(0.05)
    assert len(received_payloads) == 1
    req_id = received_payloads[0]["id"]

    # Simulate Director denying
    log.resolve_approval(req_id, approved=False)

    result = await task
    assert "denied by the director" in result.lower()


@pytest.mark.asyncio
async def test_execute_high_risk_approval_timeout():
    received_payloads = []

    async def mock_hook(payload):
        received_payloads.append(payload)

    # Configure 0.15s timeout
    log = OSLogistics(approval_hook=mock_hook, approval_timeout=0.15)

    # Launch high-risk command and do NOT respond
    result = await log.execute_terminal_command("rm -rf /")

    assert "timed out" in result.lower()
    assert "aborted" in result.lower()


def test_deep_os_file_executive_search_and_actions(tmp_path):
    """Verifies recursive file search, formatting, and open/reveal execution dispatch."""
    from unittest.mock import patch

    # Create dummy directory structure
    sub_dir = tmp_path / "subproject"
    sub_dir.mkdir()
    target_file = sub_dir / "executive_report_2026.pdf"
    target_file.write_text("Executive Briefing Content")
    other_file = tmp_path / "scratch.py"
    other_file.write_text("print('hello')")

    log = OSLogistics()

    # 1. Validation tests
    assert "cannot be empty" in log.deep_os_file_executive(str(tmp_path), "")
    assert "does not exist" in log.deep_os_file_executive(str(tmp_path / "nonexistent_dir_999"), "*.pdf")

    # 2. Search action
    search_res = log.deep_os_file_executive(str(tmp_path), "executive_report", action="search")
    assert "Found 1 match" in search_res
    assert "executive_report_2026.pdf" in search_res
    assert str(target_file) in search_res

    # 3. Glob search
    glob_res = log.deep_os_file_executive(str(tmp_path), "*.py", action="search")
    assert "scratch.py" in glob_res

    # 4. Open / Execute action
    with patch("os.startfile", create=True) as mock_startfile:
        open_res = log.deep_os_file_executive(str(tmp_path), "executive_report", action="open")
        assert "Successfully launched" in open_res
        assert "executive_report_2026.pdf" in open_res
        mock_startfile.assert_called_once_with(str(target_file))

    # 5. Reveal action in Explorer
    with patch("subprocess.Popen") as mock_popen:
        reveal_res = log.deep_os_file_executive(str(tmp_path), "executive_report", action="reveal")
        assert "Successfully revealed" in reveal_res
        assert "Windows Explorer" in reveal_res
        mock_popen.assert_called_once()

