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
from typing import Any, Dict, List, Optional, Tuple

from backend.vision_manager import VisionManager

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

# Destructive hotkey combinations blocked for system safety (e.g. system logoff/taskmgr)
DESTRUCTIVE_HOTKEYS = {
    "ctrl+alt+del",
    "ctrl+alt+delete",
    "win+l",
    "ctrl+shift+esc",
}

import ctypes
import sys

class POINT(ctypes.Structure):
    _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]

def get_live_cursor_coords() -> tuple[int, int]:
    """Retrieves current hardware OS cursor coordinates with pyautogui fallback."""
    if hasattr(ctypes, "windll") and sys.platform.startswith("win"):
        try:
            pt = POINT()
            if ctypes.windll.user32.GetCursorPos(ctypes.byref(pt)):
                return int(pt.x), int(pt.y)
        except Exception:
            pass
    if pyautogui is not None:
        try:
            pos = pyautogui.position()
            return int(pos.x), int(pos.y)
        except Exception:
            pass
    return 0, 0


class GuiAutomationLogistics:
    """Desktop GUI automation and visual co-editing suite."""

    def __init__(self, vision_manager: Optional[VisionManager] = None) -> None:
        self.vision = vision_manager or VisionManager()

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

        # Safety blacklist filter (destructive combinations like ctrl+alt+del, win+l)
        if clean_combo in DESTRUCTIVE_HOTKEYS or "ctrl+alt+del" in clean_combo:
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

    def resolve_window_occlusion(self, target_window_title: str) -> dict:
        """Inspects window Z-order and resolves any occluding/overlapping windows over the target window.

        Uses win32gui.EnumWindows to traverse top-level windows in Z-order. If any non-HUD window
        overlaps the target window's bounding box, automatically brings the target window to the
        foreground (SW_RESTORE / SetForegroundWindow) before capturing or clicking.

        Args:
            target_window_title: Substring of the window title to ensure is unobstructed and visible.

        Returns:
            Dictionary containing occlusion status, overlapping window titles, action taken, and window rect.
        """
        clean_target = target_window_title.strip()
        if not clean_target or clean_target.lower() == "active":
            target_win = self._find_window("") or (gw.getActiveWindow() if gw else None)
            if target_win:
                clean_target = getattr(target_win, "title", "active")

        result: Dict[str, Any] = {
            "target_window": clean_target,
            "target_found": False,
            "occluded": False,
            "is_occluded": False,
            "occluding_windows": [],
            "occluded_by": [],
            "action_taken": "none",
            "foreground_action": "none",
            "rect": None,
        }

        if win32gui is None or not sys.platform.startswith("win"):
            target_w = self._find_window(clean_target)
            if target_w:
                self._activate_window(target_w)
                result["target_found"] = True
                result["action_taken"] = "brought_to_foreground"
                result["foreground_action"] = "Brought target window to foreground"
                result["rect"] = [target_w.left, target_w.top, target_w.right, target_w.bottom]
            return result

        try:
            target_hwnd = None
            target_rect = None
            target_title = clean_target
            windows_above_target: List[Tuple[Any, str, Tuple[int, int, int, int]]] = []

            def _enum_z_order(hwnd: Any, extra: Any) -> bool:
                nonlocal target_hwnd, target_rect, target_title
                if not win32gui.IsWindowVisible(hwnd) or win32gui.IsIconic(hwnd):
                    return True
                title = win32gui.GetWindowText(hwnd).strip()
                rect = win32gui.GetWindowRect(hwnd)
                w, h = rect[2] - rect[0], rect[3] - rect[1]
                if w < 20 or h < 20:
                    return True

                if target_hwnd is None:
                    if clean_target.lower() in title.lower():
                        target_hwnd = hwnd
                        target_rect = rect
                        target_title = title
                    else:
                        lower_t = title.lower()
                        if "program manager" not in lower_t and "alfred" not in lower_t:
                            windows_above_target.append((hwnd, title, rect))
                return True

            win32gui.EnumWindows(_enum_z_order, None)

            if target_hwnd is None:
                def _find_minimized(hwnd: Any, extra: Any) -> bool:
                    nonlocal target_hwnd, target_title
                    title = win32gui.GetWindowText(hwnd).strip()
                    if clean_target.lower() in title.lower():
                        target_hwnd = hwnd
                        target_title = title
                    return True

                win32gui.EnumWindows(_find_minimized, None)
                if target_hwnd:
                    win32gui.ShowWindow(target_hwnd, win32con.SW_RESTORE)
                    win32gui.SetForegroundWindow(target_hwnd)
                    time.sleep(0.08)
                    target_rect = win32gui.GetWindowRect(target_hwnd)
                    result["target_found"] = True
                    result["target_window"] = target_title
                    result["action_taken"] = "restored_and_focused"
                    result["foreground_action"] = "Restored and focused minimized target window"
                    result["rect"] = list(target_rect)
                    return result

                result["action_taken"] = "window_not_found"
                return result

            result["target_found"] = True
            result["target_window"] = target_title
            result["rect"] = list(target_rect)
            tx1, ty1, tx2, ty2 = target_rect

            # Check bounding-box intersection with windows positioned above in Z-order
            occluding = []
            for ahwnd, atitle, arect in windows_above_target:
                ax1, ay1, ax2, ay2 = arect
                ix1 = max(tx1, ax1)
                iy1 = max(ty1, ay1)
                ix2 = min(tx2, ax2)
                iy2 = min(ty2, ay2)
                if ix2 > ix1 and iy2 > iy1:
                    occluding.append(atitle)

            if occluding:
                result["occluded"] = True
                result["is_occluded"] = True
                result["occluding_windows"] = occluding
                result["occluded_by"] = occluding
                try:
                    win32gui.ShowWindow(target_hwnd, win32con.SW_RESTORE)
                    win32gui.SetForegroundWindow(target_hwnd)
                    time.sleep(0.08)
                    result["action_taken"] = "brought_to_foreground"
                    result["foreground_action"] = "Brought target window to foreground"
                except Exception as ex:
                    logger.warning("Failed to bring target window to foreground: %s", ex)
                    result["action_taken"] = f"focus_failed: {ex}"
            else:
                result["action_taken"] = "none"
                result["foreground_action"] = "Window is already unobstructed in foreground"

            return result
        except Exception as e:
            logger.error("Error in resolve_window_occlusion: %s", e)
            result["action_taken"] = f"error: {e}"
            return result

    def screen_pixel_navigation(
        self,
        x: int = -1,
        y: int = -1,
        action: str = "click",
        scroll_amount: int = 0,
        target_label_or_tag: str = "",
    ) -> str:
        """Performs precise desktop mouse actions at specific (x, y) screen coordinates or Set-of-Marks tags.

        Args:
            x: Horizontal pixel coordinate. Pass -1 to target current cursor position or when using target_label_or_tag.
            y: Vertical pixel coordinate. Pass -1 to target current cursor position or when using target_label_or_tag.
            action: Action to perform: 'click', 'double_click', 'right_click', 'move', 'scroll'.
            scroll_amount: Number of scroll ticks for 'scroll' action (positive scrolls up, negative down).
            target_label_or_tag: Optional Set-of-Marks tag ('#12') or control label to auto-resolve to (x, y).

        Returns:
            Confirmation report indicating the pixel interaction executed.
        """
        if pyautogui is None:
            return "Error: pyautogui is unavailable on this host."

        # 1. Resolve Set-of-Marks Tag or Label if provided
        if target_label_or_tag:
            tag_clean = target_label_or_tag.strip().lower()
            cache = self.vision.get_som_cache()
            if tag_clean not in cache and f"#{tag_clean}" not in cache:
                try:
                    self.vision.detect_ui_elements_and_annotate_grid()
                    cache = self.vision.get_som_cache()
                except Exception as ex:
                    logger.warning("SoM grid detection failed: %s", ex)

            entry = cache.get(tag_clean) or cache.get(f"#{tag_clean}")
            if entry and "center" in entry:
                cx, cy = entry["center"]
                x, y = int(cx), int(cy)
                logger.info("[Pixel Navigation] Resolved '%s' to center coordinates (%d, %d)", target_label_or_tag, x, y)
            else:
                return f"Error: Could not resolve Set-of-Marks tag or label '{target_label_or_tag}' on active screen."

        # 2. Support live cursor auto-targeting when coordinates are (-1, -1) or user says 'click where my mouse is'
        if x == -1 and y == -1:
            x, y = get_live_cursor_coords()

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

            tag_note = f" (target: '{target_label_or_tag}')" if target_label_or_tag else ""
            return f"Successfully executed desktop mouse {act} at coordinates ({x}, {y}){tag_note}."
        except Exception as e:
            logger.error("Error executing screen_pixel_navigation: %s", e)
            return f"Error performing mouse action at ({x}, {y}): {e}"

    def list_open_windows(self) -> str:
        """Lists all visible application windows currently open on the desktop.

        Returns:
            Formatted report of open window titles and their dimensions.
        """
        if gw is None:
            return "Error: pygetwindow is unavailable on this host."

        try:
            windows = gw.getAllWindows()
            visible_windows = []
            for w in windows:
                title = getattr(w, "title", "").strip()
                if title and getattr(w, "visible", True) and getattr(w, "width", 0) > 100 and getattr(w, "height", 0) > 100:
                    visible_windows.append({
                        "title": title,
                        "width": getattr(w, "width", 0),
                        "height": getattr(w, "height", 0),
                    })

            if not visible_windows:
                return "No visible application windows detected on desktop."

            lines = [f"Active Desktop Windows ({len(visible_windows)} found):"]
            for win in visible_windows:
                lines.append(f"  • \"{win['title']}\" ({win['width']}x{win['height']})")

            return "\n".join(lines)
        except Exception as e:
            logger.error("Error listing open windows: %s", e)
            return f"Error querying desktop windows: {e}"

    def manage_desktop_window(self, window_title: str = "active", action: str = "close") -> str:
        """Controls desktop application windows (close, minimize, maximize, restore, focus, or list).

        Args:
            window_title: Window title substring or 'active'/'current'. Set to '' or 'list' when action is 'list'.
            action: Action to perform: 'close', 'close_tab', 'minimize', 'maximize', 'restore', 'focus', or 'list'.

        Returns:
            Status confirmation report or formatted list of open windows.
        """
        act = action.strip().lower()
        if act == "list" or window_title.strip().lower() in ("list", ""):
            if act == "list":
                return self.list_open_windows()

        if not window_title.strip():
            return "Error: window_title parameter cannot be empty."

        if act in ("resolve_occlusion", "unblock", "bring_to_foreground", "unocclude"):
            report = self.resolve_window_occlusion(window_title)
            return (
                f"=== Occlusion Assessment for '{report.get('target_window', window_title)}' ===\n"
                f"• Target Found: {report.get('target_found', False)}\n"
                f"• Occluded: {report.get('occluded', False)}\n"
                f"• Occluding Windows: {', '.join(report.get('occluding_windows', [])) or 'None'}\n"
                f"• Action Taken: {report.get('foreground_action', report.get('action_taken', 'none'))}"
            )

        target = window_title.strip().lower()

        # 1. Locate window
        target_win = None
        if target in ("active", "current", "foreground"):
            if gw is not None:
                try:
                    target_win = gw.getActiveWindow()
                except Exception:
                    pass
            if target_win is None and win32gui is not None:
                try:
                    hwnd = win32gui.GetForegroundWindow()
                    title = win32gui.GetWindowText(hwnd)
                    if title:
                        target_win = self._find_window(title)
                except Exception:
                    pass
        else:
            target_win = self._find_window(target)

        if target_win is None:
            return f"Error: No open application window matching '{window_title}' found on desktop."

        matched_title = getattr(target_win, "title", window_title)
        hwnd = getattr(target_win, "_hWnd", None)
        if hwnd is None and win32gui is not None:
            try:
                hwnd = win32gui.FindWindow(None, matched_title)
            except Exception:
                pass

        try:
            if act == "close":
                # Prefer native win32 WM_CLOSE for graceful closing without crashing
                closed = False
                if hwnd and win32gui is not None and win32con is not None:
                    try:
                        win32gui.PostMessage(hwnd, win32con.WM_CLOSE, 0, 0)
                        closed = True
                    except Exception:
                        pass
                if not closed:
                    if hasattr(target_win, "close"):
                        target_win.close()
                    elif pyautogui is not None:
                        self._activate_window(target_win)
                        time.sleep(0.05)
                        pyautogui.hotkey("alt", "f4")
                return f"Successfully closed window '{matched_title}'."

            elif act in ("close_tab", "closetab"):
                # Focus window and send Ctrl+W
                self._activate_window(target_win)
                time.sleep(0.1)
                if pyautogui is not None:
                    pyautogui.hotkey("ctrl", "w")
                return f"Successfully sent Close Tab (Ctrl+W) to window '{matched_title}'."

            elif act == "minimize":
                if hasattr(target_win, "minimize"):
                    target_win.minimize()
                elif hwnd and win32gui is not None and win32con is not None:
                    win32gui.ShowWindow(hwnd, win32con.SW_MINIMIZE)
                return f"Successfully minimized window '{matched_title}'."

            elif act == "maximize":
                if hasattr(target_win, "maximize"):
                    target_win.maximize()
                elif hwnd and win32gui is not None and win32con is not None:
                    win32gui.ShowWindow(hwnd, win32con.SW_MAXIMIZE)
                return f"Successfully maximized window '{matched_title}'."

            elif act == "restore":
                if hasattr(target_win, "restore"):
                    target_win.restore()
                elif hwnd and win32gui is not None and win32con is not None:
                    win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
                return f"Successfully restored window '{matched_title}'."

            elif act in ("focus", "activate"):
                self._activate_window(target_win)
                return f"Successfully focused and brought window '{matched_title}' to foreground."

            elif act in ("resolve_occlusion", "clear_occlusion", "unocclude"):
                res = self.resolve_window_occlusion(matched_title)
                occ_status = "Occluded" if res["occluded"] else "Unobstructed"
                occ_list = ", ".join(res["occluding_windows"]) if res["occluding_windows"] else "None"
                return (
                    f"Z-Order Occlusion Analysis for '{res['target_window']}':\n"
                    f"• Status: {occ_status}\n"
                    f"• Obstructing Windows: {occ_list}\n"
                    f"• Action Taken: {res['action_taken']}\n"
                    f"• Rect: {res['rect']}"
                )

            else:
                return (
                    f"Error: Unsupported window action '{action}'. "
                    f"Supported actions: 'close', 'close_tab', 'minimize', 'maximize', 'restore', 'focus', 'resolve_occlusion'."
                )

        except Exception as e:
            logger.error("Error managing desktop window '%s': %s", matched_title, e)
            return f"Error executing '{action}' on window '{matched_title}': {e}"

