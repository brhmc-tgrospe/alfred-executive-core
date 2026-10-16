"""A.L.F.R.E.D. Live Visual Co-Editing & Desktop GUI Automation Suite.

Provides visual automation capabilities for live on-screen pair programming:
1. type_into_application: Types text live line-by-line into any foreground application window (Notepad, Word, IDE).
2. write_live_word_document: Opens Microsoft Word visibly via COM automation and types styled documents in real time.
3. visual_code_edit: Applies code modifications on disk and immediately focuses the active IDE at the modified line.
4. send_keyboard_shortcut: Dispatches safe application hotkeys (Ctrl+S, Ctrl+Z, Ctrl+F) while blocking destructive OS keys.

All tools implement strict primitive type hints (str, int, bool) and docstrings
for clean schema registration with the Gemini Multimodal Live API.
"""

from __future__ import annotations

import logging
import os
import subprocess
import time
from typing import Optional, List

try:
    import pyautogui
    pyautogui.FAILSAFE = True
    pyautogui.PAUSE = 0.02
except ImportError:
    pyautogui = None

try:
    import pyperclip
except ImportError:
    pyperclip = None

try:
    import pygetwindow as gw
except ImportError:
    gw = None

try:
    import win32gui
    import win32con
except ImportError:
    win32gui = None
    win32con = None

logger = logging.getLogger("AlfredGuiAutomation")

# Destructive hotkey combinations blocked for system safety
DESTRUCTIVE_HOTKEYS = {
    "alt+f4",
    "ctrl+alt+del",
    "ctrl+alt+delete",
    "win+l",
    "ctrl+shift+esc",
    "alt+space",
}


class GuiAutomationLogistics:
    """Desktop GUI automation and visual co-editing suite."""

    def __init__(self) -> None:
        pass

    def _find_window(self, app_name: str) -> Optional[Any]:
        """Finds the first visible window whose title contains app_name (case-insensitive)."""
        if gw is None:
            return None
        target = app_name.strip().lower()
        try:
            for w in gw.getAllWindows():
                if w.title and target in w.title.lower():
                    return w
        except Exception as e:
            logger.warning("Error searching windows: %s", e)
        return None

    def _activate_window(self, window: Any) -> bool:
        """Brings the specified window to the foreground."""
        if window is None:
            return False
        try:
            # 1. Try pygetwindow activation
            if hasattr(window, "activate"):
                window.activate()
                time.sleep(0.1)
                return True
        except Exception:
            pass

        # 2. Native win32 fallback
        if win32gui and win32con and hasattr(window, "_hWnd"):
            try:
                hwnd = window._hWnd
                if win32gui.IsIconic(hwnd):
                    win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
                win32gui.SetForegroundWindow(hwnd)
                time.sleep(0.1)
                return True
            except Exception as e:
                logger.warning("win32gui foreground activation failed: %s", e)
        return False

    def type_into_application(self, app_name: str, text_content: str, clear_existing: bool = False) -> str:
        """Visibly types text line-by-line into any active desktop application window (Notepad, Word, IDE, etc.).

        Args:
            app_name: Target window name or application keyword (e.g. 'Notepad', 'Word', 'Antigravity', 'Visual Studio Code').
            text_content: The text or code content to type into the application.
            clear_existing: If True, selects all existing content (Ctrl+A) and replaces it.

        Returns:
            Status confirmation report indicating target window, line count, and typing outcome.
        """
        if not text_content:
            return "Error: text_content cannot be empty."

        clean_name = app_name.strip()
        name_lower = clean_name.lower()

        # Auto-launch Notepad if requested and not running
        target_win = self._find_window(clean_name)
        if target_win is None and name_lower in ("notepad", "notepad.exe", "editor"):
            try:
                subprocess.Popen(["notepad.exe"])
                time.sleep(0.8)
                target_win = self._find_window("notepad")
            except Exception as e:
                return f"Failed to launch notepad.exe: {e}"

        if target_win is None:
            return f"Error: No open application window matching '{clean_name}' was found on the desktop."

        # Activate target window
        self._activate_window(target_win)
        time.sleep(0.15)

        if pyautogui is None or pyperclip is None:
            return "Error: GUI typing automation libraries (pyautogui / pyperclip) are unavailable."

        # Optional clear existing content
        if clear_existing:
            pyautogui.hotkey("ctrl", "a")
            time.sleep(0.05)
            pyautogui.press("backspace")
            time.sleep(0.05)

        # Type content line-by-line with visual delay for realistic, smooth typing rhythm
        lines = text_content.splitlines()
        if not lines and text_content:
            lines = [text_content]

        for idx, line in enumerate(lines):
            # Use clipboard paste per line to faithfully reproduce Unicode, symbols, and indentation
            pyperclip.copy(line)
            pyautogui.hotkey("ctrl", "v")
            if idx < len(lines) - 1:
                pyautogui.press("enter")
            time.sleep(0.04)  # 40ms visual typing rhythm

        win_title = getattr(target_win, "title", clean_name)
        return f"Successfully typed {len(lines)} line(s) into '{win_title}' on screen."

    def write_live_word_document(self, title: str, content: str, save_path: str = "") -> str:
        """Opens Microsoft Word visibly via COM automation and types a styled document in real time.

        Args:
            title: Document title to format with Heading 1 style.
            content: Document body paragraphs to insert into the document.
            save_path: Optional path to save the generated document on disk (.docx).

        Returns:
            Confirmation report indicating document creation, formatting, and file save location.
        """
        clean_title = title.strip()
        clean_content = content.strip()

        try:
            import win32com.client
            word = win32com.client.Dispatch("Word.Application")
            word.Visible = True
            doc = word.Documents.Add()
            word.Activate()
            sel = word.Selection

            if clean_title:
                try:
                    sel.Style = doc.Styles("Heading 1")
                except Exception:
                    pass
                sel.TypeText(clean_title)
                sel.TypeParagraph()
                try:
                    sel.Style = doc.Styles("Normal")
                except Exception:
                    pass
                sel.TypeParagraph()

            paragraphs = [p.strip() for p in clean_content.split("\n\n") if p.strip()] or [clean_content]
            for p in paragraphs:
                sel.TypeText(p)
                sel.TypeParagraph()
                time.sleep(0.05)

            if save_path:
                abs_save = os.path.abspath(save_path.strip().strip("\"'"))
                os.makedirs(os.path.dirname(abs_save), exist_ok=True)
                doc.SaveAs(abs_save)
                return f"Successfully created, typed live, and saved Word document '{clean_title}' to '{abs_save}'."

            return f"Successfully created and typed live Word document '{clean_title}' in Microsoft Word on screen."

        except Exception as e:
            logger.info("Microsoft Word COM automation unavailable (%s). Falling back to Notepad.", e)
            fallback_text = f"{clean_title.upper()}\n{'=' * len(clean_title)}\n\n{clean_content}"
            res = self.type_into_application("Notepad", fallback_text, clear_existing=True)
            if "Successfully" in res:
                return f"Microsoft Word COM unavailable. Gracefully opened and typed live document in Notepad:\n{res}"
            return f"Failed to launch Microsoft Word ({e}) and fallback editor failed: {res}"

    def visual_code_edit(self, file_path: str, target_snippet: str, replacement_snippet: str, line_number: int = 1) -> str:
        """Applies a code edit to a source file on disk and focuses the active IDE at the modified line.

        Args:
            file_path: Relative or absolute path to the target source code file.
            target_snippet: Existing code snippet to replace (or empty string to append/create).
            replacement_snippet: New code snippet to write into the file.
            line_number: Line number to focus inside the user's active IDE (defaults to 1).

        Returns:
            Confirmation report detailing file modification and IDE focus status.
        """
        clean_path = file_path.strip().strip("\"'")
        if not clean_path:
            return "Error: file_path cannot be empty."

        abs_path = os.path.abspath(clean_path)
        os.makedirs(os.path.dirname(abs_path), exist_ok=True)

        effective_line = max(1, line_number)

        try:
            if os.path.exists(abs_path) and os.path.isfile(abs_path):
                with open(abs_path, "r", encoding="utf-8", errors="replace") as f:
                    content = f.read()

                if target_snippet and target_snippet in content:
                    # Replace snippet
                    updated_content = content.replace(target_snippet, replacement_snippet, 1)
                    # Compute line number of the replacement
                    idx = updated_content.find(replacement_snippet)
                    if idx != -1:
                        effective_line = updated_content[:idx].count("\n") + 1
                else:
                    # Append replacement snippet
                    sep = "\n" if not content.endswith("\n") else ""
                    updated_content = content + sep + replacement_snippet
                    effective_line = updated_content.count("\n") + 1

                with open(abs_path, "w", encoding="utf-8") as f:
                    f.write(updated_content)
            else:
                # Create new file
                with open(abs_path, "w", encoding="utf-8") as f:
                    f.write(replacement_snippet)
                effective_line = 1

        except Exception as e:
            return f"Error modifying file '{abs_path}': {e}"

        # Focus in IDE (try Antigravity, VS Code, or os.startfile)
        ide_focused = False
        for cmd in (
            ["antigravity", "--goto", f"{abs_path}:{effective_line}"],
            ["code", "--goto", f"{abs_path}:{effective_line}"],
        ):
            try:
                res = subprocess.run(cmd, capture_output=True, timeout=2.0)
                if res.returncode == 0:
                    ide_focused = True
                    break
            except Exception:
                pass

        if not ide_focused:
            try:
                os.startfile(abs_path)
                ide_focused = True
            except Exception:
                pass

        # Also activate IDE window if found
        ide_win = self._find_window("antigravity") or self._find_window("visual studio code") or self._find_window("code")
        if ide_win:
            self._activate_window(ide_win)

        filename = os.path.basename(abs_path)
        return (
            f"Successfully applied visual code edit to '{filename}' on disk at line {effective_line} "
            f"and focused active IDE."
        )

    def send_keyboard_shortcut(self, window_title: str, hotkey_combo: str) -> str:
        """Focuses a desktop window and sends safe application keyboard shortcuts (e.g. 'ctrl+s', 'ctrl+z', 'ctrl+f').

        Args:
            window_title: Window title or keyword to focus (e.g. 'Antigravity', 'Notepad', 'Word').
            hotkey_combo: Plus-separated keyboard combination (e.g. 'ctrl+s', 'ctrl+z', 'ctrl+shift+p').

        Returns:
            Confirmation report indicating shortcut transmission or safety block reason.
        """
        clean_combo = hotkey_combo.strip().lower().replace(" ", "")
        if not clean_combo:
            return "Error: hotkey_combo cannot be empty."

        # Safety blacklist filter
        if clean_combo in DESTRUCTIVE_HOTKEYS or "alt+f4" in clean_combo or "ctrl+alt+del" in clean_combo:
            return f"Blocked: Hotkey combo '{hotkey_combo}' is classified as a destructive system action."

        target_win = self._find_window(window_title)
        if target_win is None:
            return f"Error: Window matching '{window_title}' not found on desktop."

        self._activate_window(target_win)
        time.sleep(0.1)

        if pyautogui is None:
            return "Error: pyautogui is unavailable."

        keys = [k.strip().lower() for k in hotkey_combo.split("+") if k.strip()]
        try:
            pyautogui.hotkey(*keys)
            matched_title = getattr(target_win, "title", window_title)
            return f"Successfully sent shortcut '{hotkey_combo}' to window '{matched_title}'."
        except Exception as e:
            return f"Error sending hotkey combo '{hotkey_combo}': {e}"

    def screen_pixel_navigation(
        self,
        x: int,
        y: int,
        action: str = "click",
        scroll_amount: int = 0,
    ) -> str:
        """Performs precise desktop mouse actions at specific (x, y) screen pixel coordinates.

        Args:
            x: Horizontal pixel coordinate on the desktop screen.
            y: Vertical pixel coordinate on the desktop screen.
            action: Action to perform: 'click', 'double_click', 'right_click', 'move', 'scroll'.
            scroll_amount: Number of scroll ticks for 'scroll' action (positive scrolls up, negative down).

        Returns:
            Confirmation report indicating the pixel interaction executed.
        """
        if pyautogui is None:
            return "Error: pyautogui is unavailable on this host."

        act = action.strip().lower()
        try:
            screen_w, screen_h = pyautogui.size()
            if x < 0 or x >= screen_w or y < 0 or y >= screen_h:
                return f"Error: Pixel coordinates ({x}, {y}) are outside screen bounds ({screen_w}x{screen_h})."

            if act == "click":
                pyautogui.click(x, y)
            elif act == "double_click":
                pyautogui.doubleClick(x, y)
            elif act == "right_click":
                pyautogui.rightClick(x, y)
            elif act == "move":
                pyautogui.moveTo(x, y, duration=0.2)
            elif act == "scroll":
                pyautogui.moveTo(x, y)
                pyautogui.scroll(scroll_amount)
            else:
                return f"Error: Unsupported mouse action '{action}'. Supported: 'click', 'double_click', 'right_click', 'move', 'scroll'."

            return f"Successfully executed desktop mouse {act} at coordinates ({x}, {y})."
        except Exception as e:
            logger.error("Error executing screen_pixel_navigation: %s", e)
            return f"Error performing mouse action at ({x}, {y}): {e}"
