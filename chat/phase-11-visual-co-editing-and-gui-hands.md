# Phase 11: Live Visual Co-Editing & Desktop GUI Automation Suite

## Executive Summary
Phase 11 equips A.L.F.R.E.D. with **Visual GUI Automation Hands**, enabling live on-screen co-editing and application control:
1. **Installed GUI Dependencies**: Added and verified `pyautogui`, `pyperclip`, `pygetwindow`, and `pywin32` via `uv pip install`.
2. **Built `GuiAutomationLogistics` (`backend/tools/gui_automation.py`)**: 4 visual co-editing tools with strict primitive type hints (`str, int, bool`):
   - `type_into_application`: Types code and text live line-by-line into active foreground windows (Notepad, Word, IDEs) with a 40ms human-like visual rhythm.
   - `write_live_word_document`: Visibly opens Microsoft Word via native COM automation (`win32com.client`), formats styled Heading 1 titles and paragraphs live on screen, with graceful fallback to Notepad/WordPad.
   - `visual_code_edit`: Applies code diffs or scaffolds files on disk and immediately focuses the active IDE (`antigravity --goto` or `code --goto`) at the exact modified line.
   - `send_keyboard_shortcut`: Focuses target windows and sends editor/app shortcuts (`Ctrl+S`, `Ctrl+Z`, `Ctrl+F`) while strictly enforcing safety blacklists against destructive OS commands (`Alt+F4`, `Ctrl+Alt+Del`).
3. **Updated Persona & Prompt**: Instructed ALFRED in `ALFRED_SYSTEM_PROMPT` to address the Director as **"Director Qadir"** (pronounced "ka-dir") and proactively utilize his GUI automation tools to type visibly on screen rather than claiming inability to type into desktop applications.
4. **Verification**:
   - **61 / 61 tests passed** (`pytest -v`) in 11.27s.
   - All 18 tools (7 OS + 7 Dev + 4 GUI) verified for Gemini Live API schema parsing in `test_gemini_tool_declarations.py`.
   - Production HUD build (`npm run build`) succeeded with zero errors.
   - Live 3-turn multi-turn benchmark passed with 0 underflow errors.

---

## 1. Tool Implementation & Capabilities

| Tool Name | Parameters | Capabilities |
|---|---|---|
| `type_into_application` | `app_name: str, text_content: str, clear_existing: bool = False` | Locates target window via `pygetwindow`/`win32gui`, auto-launches `notepad.exe` if requested and not running, activates window, optionally selects all (`Ctrl+A`), and types content line-by-line via clipboard paste with 40ms visual delay. |
| `write_live_word_document` | `title: str, content: str, save_path: str = ""` | Visibly launches Word (`win32com.client.Dispatch("Word.Application")`, `word.Visible = True`), inserts Heading 1 title, streams body paragraphs, and optionally saves `.docx`. Gracefully falls back to Notepad typing if MS Word is not installed. |
| `visual_code_edit` | `file_path: str, target_snippet: str, replacement_snippet: str, line_number: int = 1` | Applies code edits on disk, computes modified line index, and opens/focuses the active IDE (`antigravity --goto`, `code --goto`, or `os.startfile`) so Director Qadir immediately sees the live changes. |
| `send_keyboard_shortcut` | `window_title: str, hotkey_combo: str` | Focuses the application window and sends keystrokes (`pyautogui.hotkey`). Safety filters block `alt+f4`, `ctrl+alt+del`, `win+l`, and `ctrl+shift+esc`. |

---

## 2. Updated Persona & System Instruction

In `backend/live_session.py`:
```python
ALFRED_SYSTEM_PROMPT = """You are A.L.F.R.E.D. (Autonomous Logistics Functional Response & Executive Director).
Voice & Persona: Impeccably articulate, composed, dryly witty British executive director.
Address the user as "Sir" or "Director Qadir" (pronounced "ka-dir"). Keep spoken responses concise (1 to 3 sentences) unless asked for a deep briefing.
Capabilities: You have real-time access to the user's screen, system telemetry, local memory, OS logistics, developer tools, and full visual GUI automation hands (type_into_application, write_live_word_document, visual_code_edit, send_keyboard_shortcut). NEVER tell Director Qadir that you cannot type into Notepad, Microsoft Word, or the Antigravity IDE—proactively use these visual tools so Director Qadir can watch you write and edit live on screen. From now on, address Director Qadir with his title and surname."""
```

---

## 3. Test Suite & Verification Results

### Pytest (`pytest -v`)
```
============================= 61 passed in 11.27s =============================
```
- `test_visual_code_edit_create_new_file`: Verified file creation and IDE focus logic.
- `test_visual_code_edit_replace_snippet`: Verified snippet replacement on disk.
- `test_send_keyboard_shortcut_destructive_filter`: Verified `alt+f4`, `ctrl+alt+del`, `win+l` are blocked.
- `test_type_into_application_mocked_typing`: Verified window activation, `Ctrl+A` clear, and line-by-line typing.
- `test_write_live_word_document_fallback`: Verified graceful fallback when MS Word COM is unavailable.
- `test_gemini_tool_declaration_parsing`: Verified all 18 tools (7 OS + 7 Dev + 4 GUI) are accepted by `types.LiveConnectConfig`.

### HUD Frontend Build (`npm run build`)
```
✓ 1928 modules transformed.
dist/index.html                   0.45 kB │ gzip:   0.29 kB
dist/assets/index-CVbb5ACn.css   43.91 kB │ gzip:   7.50 kB
dist/assets/index-PzvnZh-r.js   803.56 kB │ gzip: 215.19 kB
✓ built in 516ms
```

### Live Multi-Turn Hardware Benchmark (`backend/diagnose_live.py`)
```
======================================================================
                 MULTI-TURN LATENCY BENCHMARKS
======================================================================
• Turn 1 (Startup Greeting): First Audio: 814.5ms  | Duration: 12.22s
• Turn 2 (Status Report):    First Audio: 1024.3ms | Duration: 8.89s
• Turn 3 (Dev Ports Tool):   First Audio: 890.3ms  | Tool Called: True | Duration: 10.21s
• Output Underflow Errors:   0
• Overall Multi-Turn Status: [PASSED]
======================================================================
```
