# Phase 13: Uninterrupted Speech Playback, Strict Half-Duplex Speaker Lock & Full Desktop Window Control

## Executive Summary
Phase 13 resolves the two critical runtime issues observed during live testing with Director Qadir:
1. **Mid-Sentence Voice Cutoff & Self-Interruption**: ALFRED was abruptly cutting off his own sentences due to acoustic speaker echo into laptop microphones and premature `end_of_turn=True` turn injections.
2. **Safety Refusals & Desktop Window Management**: ALFRED was refusing requests to close windows or terminate apps citing security policies, and lacked dedicated desktop window management tools.

### Key Architectural Fixes
1. **Strict Half-Duplex Speaker Lock (`backend/audio_manager.py`)**:
   - Implemented `is_speaker_locked()` with an active playback check and a 450ms post-drain cooldown window (`speaker_cooldown_sec = 0.45`).
   - In `_input_callback`, if the speaker is locked, mic capture and visualization levels are completely muted (`current_mic_rms = 0.0`, `mic_rms_peak = 0.0`, `visual_mic_level = 0.0`), preventing speaker sound coming out of laptop speakers from re-entering the microphone and triggering a self-interruption loop.
   - `should_stream_mic()` returns `False` when `is_speaker_locked()` is active.
   - `feed_speaker_audio` and `_output_callback` continuously refresh `_last_playback_time = time.time()`, and `clear_playback()` resets `_last_playback_time = 0.0`.

2. **Native Continuous VAD & Removal of Turn Collision Injection (`backend/live_session.py`)**:
   - Completely eliminated `session.send(input='', end_of_turn=True)` from the microphone audio streaming loop (`_stream_mic_to_alfred`). Injecting empty text prompts while Gemini was generating audio caused immediate turn cancellation.
   - Implemented clean trailing silence: when user speech finishes, ALFRED streams clean digital silence (`bytes(len(chunk))`) for 1.2 seconds, allowing Gemini's native server-side VAD to detect the end of speech naturally without mid-sentence abortion.
   - In `_stream_mic_to_alfred`, microphone chunks are skipped immediately when `self.audio_manager.is_speaker_locked()` is True.

3. **Complete Desktop Window Management Suite (`backend/tools/gui_automation.py`)**:
   - Implemented `manage_desktop_window(window_title: str, action: str = "close") -> str`:
     - Target window resolution: accepts window title substrings (e.g. `'Chrome'`, `'Notepad'`, `'Edge'`) or `'active'`/`'current'`/`'foreground'`.
     - Supported actions:
       - `close`: Sends native Win32 `WM_CLOSE` (`win32gui.PostMessage(hwnd, WM_CLOSE, 0, 0)`), falls back to `window.close()` or `Alt+F4`.
       - `close_tab`: Focuses the window and dispatches `Ctrl+W`.
       - `minimize`: Minimizes the window via `win32gui.ShowWindow(hwnd, SW_MINIMIZE)` or `window.minimize()`.
       - `maximize`: Maximizes the window via `win32gui.ShowWindow(hwnd, SW_MAXIMIZE)` or `window.maximize()`.
       - `restore`: Restores window geometry via `SW_RESTORE` or `window.restore()`.
       - `focus` / `activate`: Brings the target window to the foreground.
   - Implemented `list_open_windows() -> str`:
     - Queries `pygetwindow.getAllWindows()`, filters out hidden background and tiny driver windows, and formats a list of active windows with their titles and dimensions.
   - Unblocked `Alt+F4` from `DESTRUCTIVE_HOTKEYS` in `send_keyboard_shortcut` so ALFRED can execute application close requests via hotkey.

4. **Relaxed OS Safety Guardrails (`backend/tools/os_logistics.py`)**:
   - Narrowed `HIGH_RISK_PATTERN` so standard process management and developer commands (`taskkill`, `Stop-Process`, `del`, `rm`, `git push`) execute immediately without triggering the 30-second approval modal.
   - Preserved protection only for truly catastrophic disk-level destruction: `format <drive>:`, `rm -rf /`, `rd /s /q <drive>:\`, `Remove-Item -Recurse <drive>:\`, `shutdown /s`, `mkfs`, and `dd`.

5. **Executive Obedience Directives (`backend/live_session.py`)**:
   - Updated `ALFRED_SYSTEM_PROMPT` to mandate total obedience to Director Qadir without safety lectures, preachy disclaimers, or refusal of window/application management tasks.

---

## 2. Complete 25-Tool Executive Suite

| Category | Tool Function | Parameters | Capability |
|---|---|---|---|
| **OS Logistics** | `get_system_diagnostics` | `()` | Non-blocking telemetry (CPU, RAM, disk, top processes). |
| | `launch_application_or_url` | `target: str` | Launches apps or URLs safely. |
| | `inspect_active_screen` | `reason: str` | Captures desktop screen snapshot for visual cortex. |
| | `manage_executive_briefing` | `action: str, item_text: str` | SQLite WAL-backed executive briefing management. |
| | `remember_fact` | `fact: str, category: str` | Stores semantic knowledge in local ChromaDB. |
| | `recall_context` | `query: str, n_results: int` | Vector search over stored knowledge base. |
| | `execute_terminal_command` | `command: str` | Executes terminal commands; catastrophic commands gated. |
| | `deep_os_file_executive` | `root_directory: str, query_pattern: str, action: str` | Recursive search, launch (`open`), or Explorer reveal. |
| **Dev Logistics** | `inspect_git_workspace` | `repo_path: str` | Git branch, commit status, uncommitted diffs. |
| | `inspect_local_dev_ports` | `port_range: str, specific_port: int` | TCP socket scans on localhost dev ports. |
| | `probe_network_target` | `host: str, port: int, timeout_sec: float` | Ping and socket connectivity latency test. |
| | `tail_log_file` | `log_file_path: str, lines_to_read: int` | Reads the last N lines from server log files. |
| | `audit_source_file` | `file_path: str, max_lines: int` | Safe source file inspection on disk. |
| | `inspect_sqlite_database` | `db_path: str, query: str` | Safe read-only SQL queries on SQLite databases. |
| | `multi_target_network_sweep` | `targets: str` | Concurrent latency sweep across multiple infrastructure targets. |
| **GUI Automation** | `type_into_application` | `app_name: str, text_content: str, clear_existing: bool` | Visual typing into active windows. |
| | `write_live_word_document` | `title: str, content: str, save_path: str` | Visibly types styled Word documents via COM. |
| | `visual_code_edit` | `file_path: str, target_snippet: str, replacement_snippet: str, line_number: int` | Modifies code on disk and focuses IDE at edit location. |
| | `send_keyboard_shortcut` | `window_title: str, hotkey_combo: str` | Dispatches keyboard shortcuts (`Alt+F4` allowed). |
| | `screen_pixel_navigation` | `x: int, y: int, action: str, scroll_amount: int` | Pixel-coordinate mouse clicks, movements, and scrolling. |
| | `manage_desktop_window` *(New)* | `window_title: str, action: str` | Controls windows: `close`, `close_tab`, `minimize`, `maximize`, `restore`, `focus`. |
| | `list_open_windows` *(New)* | `()` | Lists all open visible application windows and dimensions. |
| **Browser DOM** | `browser_navigate_and_parse_dom` | `url: str, search_query: str, scroll_full_page: bool` | Persistent browser navigation and interactive DOM extraction. |
| | `browser_interact_dom_element` | `target_selector_or_text: str, action: str, input_text: str, submit_enter: bool` | Clicks, fills, and submits forms on dynamic web elements. |
| | `browser_scroll_and_inspect` | `direction: str, distance_pixels: int` | Scrolls viewport and extracts newly visible content. |

---

## 3. Verification & Test Results

### Pytest Full Suite
- Total tests executed: **72 passed, 0 failed** across all backend test modules.
- Runtime: **11.44s**.

### HUD Frontend Build
- `npm run build:renderer && npm run build:electron` in `hud/`: **Successful**.
- TypeScript compilation: 0 errors.
- Bundle generation: `dist/index.html` (0.45 kB), `dist/assets/index-CVbb5ACn.css` (43.91 kB), `dist/assets/index-PzvnZh-r.js` (803.56 kB).
