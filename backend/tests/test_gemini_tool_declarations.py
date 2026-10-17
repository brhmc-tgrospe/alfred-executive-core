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
from backend.tools.browser_automation import BrowserAutomationLogistics
from backend.tools.game_interaction import GameInteractionLogistics
from backend.tools.meeting_biometrics import MeetingBiometricsLogistics


def test_gemini_tool_declaration_parsing(tmp_path):
    db_file = str(tmp_path / "gemini.db")
    chroma_dir = str(tmp_path / "gemini_chroma")
    mem = MemoryStore(db_path=db_file, chroma_dir=chroma_dir)
    logistics = OSLogistics(memory_store=mem, approval_timeout=1.0)
    dev = DevLogistics()
    gui = GuiAutomationLogistics()
    browser = BrowserAutomationLogistics(profile_dir=str(tmp_path / "browser_profile"))
    game = GameInteractionLogistics()
    meeting = MeetingBiometricsLogistics(meetings_dir=str(tmp_path / "meetings"))

    # Exposed tool functions for Gemini Live API (consolidated lean set of 30 tools <= 30)
    tools_list = [
        logistics.get_system_diagnostics,
        logistics.launch_application_or_url,
        logistics.inspect_active_screen,
        logistics.manage_executive_briefing,
        logistics.manage_semantic_memory,
        logistics.execute_terminal_command,
        logistics.deep_os_file_executive,
        logistics.terminate_executive_commands,
        mem.inspect_learned_habits_and_growth,
        dev.inspect_git_workspace,
        dev.inspect_local_dev_ports,
        dev.probe_network_target,
        dev.tail_log_file,
        dev.audit_source_file,
        dev.inspect_sqlite_database,
        dev.multi_target_network_sweep,
        dev.research_software_interface_and_docs,
        gui.type_into_application,
        gui.write_live_word_document,
        gui.visual_code_edit,
        gui.send_keyboard_shortcut,
        gui.screen_pixel_navigation,
        gui.manage_desktop_window,
        browser.browser_navigate_and_parse_dom,
        browser.browser_interact_dom_element,
        game.observe_game_state,
        game.evaluate_tactical_game_policy,
        game.send_game_input_action,
        meeting.enroll_or_identify_speaker,
        meeting.manage_meeting_transcription,
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
    assert len(config.tools) == 30
    assert len(config.tools) <= 30

    mem.close()
