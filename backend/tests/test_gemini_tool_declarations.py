"""Test that google-genai properly parses tool declarations from os_logistics functions."""

import inspect
import typing
import pytest
from google import genai
from google.genai import types
from backend.memory.memory_store import MemoryStore
from backend.tools.os_logistics import OSLogistics
from backend.tools.dev_logistics import DevLogistics
from backend.tools.gui_automation import GuiAutomationLogistics


def test_gemini_tool_declaration_parsing(tmp_path):
    db_file = str(tmp_path / "gemini.db")
    chroma_dir = str(tmp_path / "gemini_chroma")
    mem = MemoryStore(db_path=db_file, chroma_dir=chroma_dir)
    logistics = OSLogistics(memory_store=mem, approval_timeout=1.0)
    dev = DevLogistics()
    gui = GuiAutomationLogistics()

    # Exposed tool functions for Gemini Live API (7 OS + 7 Dev + 4 GUI = 18 tools)
    tools_list = [
        logistics.get_system_diagnostics,
        logistics.launch_application_or_url,
        logistics.inspect_active_screen,
        logistics.manage_executive_briefing,
        logistics.remember_fact,
        logistics.recall_context,
        logistics.execute_terminal_command,
        dev.inspect_git_workspace,
        dev.inspect_local_dev_ports,
        dev.probe_network_target,
        dev.tail_log_file,
        dev.audit_source_file,
        dev.inspect_sqlite_database,
        dev.multi_target_network_sweep,
        gui.type_into_application,
        gui.write_live_word_document,
        gui.visual_code_edit,
        gui.send_keyboard_shortcut,
    ]

    # Verify functions have valid docstrings and strict type hints
    for fn in tools_list:
        hints = typing.get_type_hints(fn)
        assert fn.__doc__ is not None, f"Function {fn.__name__} missing docstring"
        assert len(fn.__doc__.strip()) > 10, f"Function {fn.__name__} docstring too short"

        sig = inspect.signature(fn)
        for param_name, param in sig.parameters.items():
            hint = hints.get(param_name, param.annotation)
            assert hint in (str, int, bool, 'str', 'int', 'bool', inspect._empty), (
                f"Parameter '{param_name}' of '{fn.__name__}' has non-primitive type: {hint}"
            )

    # Verify google-genai LiveConnectConfig accepts these tools directly
    config = types.LiveConnectConfig(
        response_modalities=["AUDIO"],
        tools=tools_list,
    )
    assert config is not None
    assert len(config.tools) == 18

    mem.close()
