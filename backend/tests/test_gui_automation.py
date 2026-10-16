"""Unit tests for Live Visual Co-Editing & Desktop GUI Automation Suite (backend/tools/gui_automation.py)."""

from unittest.mock import MagicMock, patch
import pytest
from backend.tools.gui_automation import GuiAutomationLogistics, DESTRUCTIVE_HOTKEYS


@pytest.fixture
def gui():
    return GuiAutomationLogistics()


def test_visual_code_edit_create_new_file(gui, tmp_path):
    """Verifies that visual_code_edit safely scaffolds a new file on disk."""
    new_file = tmp_path / "test_module.py"
    code = "def greeting():\n    return 'Hello Executive'\n"

    result = gui.visual_code_edit(
        file_path=str(new_file),
        target_snippet="",
        replacement_snippet=code,
        line_number=1,
    )
    assert "Successfully applied visual code edit" in result
    assert "test_module.py" in result
    assert new_file.exists()
    assert new_file.read_text(encoding="utf-8") == code


def test_visual_code_edit_replace_snippet(gui, tmp_path):
    """Verifies modifying an existing source file and replacing a snippet."""
    existing_file = tmp_path / "service.py"
    original = "def calculate_tax():\n    rate = 0.15\n    return rate\n"
    existing_file.write_text(original, encoding="utf-8")

    result = gui.visual_code_edit(
        file_path=str(existing_file),
        target_snippet="rate = 0.15",
        replacement_snippet="rate = 0.20",
        line_number=2,
    )
    assert "Successfully applied visual code edit" in result
    updated = existing_file.read_text(encoding="utf-8")
    assert "rate = 0.20" in updated
    assert "rate = 0.15" not in updated


def test_visual_code_edit_empty_path(gui):
    """Verifies error handling on empty file_path."""
    result = gui.visual_code_edit(
        file_path="",
        target_snippet="",
        replacement_snippet="print(1)",
    )
    assert "Error: file_path cannot be empty." in result


def test_send_keyboard_shortcut_destructive_filter(gui):
    """Verifies that destructive system hotkeys are strictly blocked."""
    for dangerous in ("alt+f4", "ctrl+alt+del", "ctrl+alt+delete", "win+l", "ctrl+shift+esc", "alt+space"):
        result = gui.send_keyboard_shortcut("Notepad", dangerous)
        assert "Blocked:" in result
        assert "destructive system action" in result


def test_send_keyboard_shortcut_window_not_found(gui):
    """Verifies graceful error when target window does not exist."""
    result = gui.send_keyboard_shortcut("nonexistent_phantom_app_window_999", "ctrl+s")
    assert "Error: Window matching" in result
    assert "not found on desktop" in result


def test_type_into_application_empty_text(gui):
    """Verifies validation on empty text_content."""
    result = gui.type_into_application("Notepad", "")
    assert "Error: text_content cannot be empty." in result


def test_type_into_application_window_not_found(gui):
    """Verifies error report when custom window cannot be located."""
    result = gui.type_into_application("random_unopened_game_xyz", "Hello World")
    assert "Error: No open application window matching" in result


def test_type_into_application_mocked_typing(gui):
    """Verifies window activation and typing dispatch using mocked window and pyautogui."""
    mock_win = MagicMock()
    mock_win.title = "Mocked Visual Studio Code"

    with patch.object(gui, "_find_window", return_value=mock_win), \
         patch.object(gui, "_activate_window", return_value=True), \
         patch("backend.tools.gui_automation.pyautogui") as mock_pg, \
         patch("backend.tools.gui_automation.pyperclip") as mock_pc:

        result = gui.type_into_application(
            app_name="Visual Studio Code",
            text_content="const x = 10;\nconsole.log(x);",
            clear_existing=True,
        )

        assert "Successfully typed 2 line(s) into 'Mocked Visual Studio Code'" in result
        mock_pg.hotkey.assert_any_call("ctrl", "a")
        mock_pg.press.assert_any_call("backspace")
        assert mock_pc.copy.call_count == 2


def test_write_live_word_document_fallback(gui):
    """Verifies fallback when Word COM automation is unavailable."""
    with patch("win32com.client.Dispatch", side_effect=Exception("Word not installed")), \
         patch.object(gui, "type_into_application", return_value="Successfully typed in Notepad") as mock_type:

        result = gui.write_live_word_document("Quarterly Roadmap", "Paragraph 1\n\nParagraph 2")
        assert "Microsoft Word COM unavailable" in result
        mock_type.assert_called_once()


def test_screen_pixel_navigation_bounds_validation(gui):
    """Verifies that out-of-bounds coordinates are rejected with an informative error."""
    with patch("backend.tools.gui_automation.pyautogui") as mock_pg:
        mock_pg.size.return_value = (1920, 1080)

        err_negative = gui.screen_pixel_navigation(-10, 500, action="click")
        assert "outside screen bounds" in err_negative

        err_overflow = gui.screen_pixel_navigation(2500, 500, action="click")
        assert "outside screen bounds" in err_overflow


def test_screen_pixel_navigation_actions(gui):
    """Verifies all supported desktop mouse actions dispatch to pyautogui correctly."""
    with patch("backend.tools.gui_automation.pyautogui") as mock_pg:
        mock_pg.size.return_value = (1920, 1080)

        # 1. Click
        res_click = gui.screen_pixel_navigation(500, 300, action="click")
        assert "Successfully executed desktop mouse click" in res_click
        mock_pg.click.assert_called_with(500, 300)

        # 2. Double click
        res_dc = gui.screen_pixel_navigation(500, 300, action="double_click")
        assert "Successfully executed desktop mouse double_click" in res_dc
        mock_pg.doubleClick.assert_called_with(500, 300)

        # 3. Right click
        res_rc = gui.screen_pixel_navigation(500, 300, action="right_click")
        assert "Successfully executed desktop mouse right_click" in res_rc
        mock_pg.rightClick.assert_called_with(500, 300)

        # 4. Move
        res_move = gui.screen_pixel_navigation(500, 300, action="move")
        assert "Successfully executed desktop mouse move" in res_move
        mock_pg.moveTo.assert_called_with(500, 300, duration=0.2)

        # 5. Scroll
        res_scroll = gui.screen_pixel_navigation(500, 300, action="scroll", scroll_amount=-300)
        assert "Successfully executed desktop mouse scroll" in res_scroll
        mock_pg.scroll.assert_called_with(-300)

        # 6. Unsupported action
        res_bad = gui.screen_pixel_navigation(500, 300, action="triple_flip")
        assert "Unsupported mouse action" in res_bad

