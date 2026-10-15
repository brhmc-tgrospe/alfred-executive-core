"""Test that google-genai properly parses tool declarations from os_logistics functions."""

import inspect
import typing
import pytest
from google import genai
from google.genai import types
from backend.memory.memory_store import MemoryStore
from backend.tools.os_logistics import OSLogistics


def test_gemini_tool_declaration_parsing(tmp_path):
    db_file = str(tmp_path / "gemini.db")
    chroma_dir = str(tmp_path / "gemini_chroma")
    mem = MemoryStore(db_path=db_file, chroma_dir=chroma_dir)
    logistics = OSLogistics(memory_store=mem, approval_timeout=1.0)

    # Exposed tool functions for Gemini Live API
    tools_list = [
        logistics.get_system_diagnostics,
        logistics.launch_application_or_url,
        logistics.inspect_active_screen,
        logistics.manage_executive_briefing,
        logistics.remember_fact,
        logistics.recall_context,
        logistics.execute_terminal_command,
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
    assert len(config.tools) == 7

    mem.close()
