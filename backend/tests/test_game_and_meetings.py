"""Comprehensive Unit Tests for Game Interaction & Meeting Biometrics Suites.

Validates:
1. OpenCV game HUD state extraction (Health, Resource, Stamina color masks & target centroids).
2. DirectInput scan-code structure, mouse relative displacement, and tactical RL policy evaluation.
3. Voice biometric acoustic extraction (F0 pitch, centroid, rolloff, ZCR) and diarization distinguishing
   Director Qadir (~110Hz) and Amira (~225Hz).
4. Strict UTC+8 timestamping and automated meeting transcription markdown generation.
"""

import json
from pathlib import Path
import re
from unittest.mock import patch, AsyncMock, MagicMock
import numpy as np
import pytest

from backend.tools.game_interaction import (
    GameInteractionLogistics,
    DIRECTINPUT_SCANCODES,
)
from backend.tools.meeting_biometrics import (
    MeetingBiometricsLogistics,
    get_utc8_timestamp,
    get_utc8_date_str,
    extract_acoustic_features,
)


# ===========================================================================
# 1. OpenCV Game State & HUD Extraction Tests
# ===========================================================================
def test_observe_game_state_extraction(monkeypatch):
    """Verify observe_game_state extracts HUD meters, target centroids, and valid JSON observation."""
    game = GameInteractionLogistics()

    # Create synthetic 720p game frame (BGR)
    # Background: dark grey
    synthetic_frame = np.full((720, 1280, 3), 30, dtype=np.uint8)

    # Draw synthetic Red Health Bar at top-left: [20:50, 40:240] in BGR (0, 0, 220)
    synthetic_frame[20:50, 40:240] = [0, 0, 220]

    # Draw synthetic Blue Mana Bar: [60:80, 40:180] in BGR (220, 100, 0)
    synthetic_frame[60:80, 40:180] = [220, 100, 0]

    # Draw synthetic Green Stamina Bar: [90:105, 40:160] in BGR (0, 200, 0)
    synthetic_frame[90:105, 40:160] = [0, 200, 0]

    # Draw synthetic high-contrast enemy target near center: circle at (600, 340) in white
    import cv2
    cv2.circle(synthetic_frame, (600, 340), 20, (255, 255, 255), -1)

    # Monkeypatch _capture_window_bgr to return synthetic frame
    monkeypatch.setattr(
        game,
        "_capture_window_bgr",
        lambda title: (synthetic_frame, {"width": 1280, "height": 720, "rect": {}}),
    )

    result_json = game.observe_game_state(window_title="test_game", detect_hud_bars=True)
    obs = json.loads(result_json)

    assert obs["window"] == "test_game"
    assert obs["resolution"] == "1280x720"
    assert obs["latency_ms"] >= 0.0
    assert obs["observation_fps"] > 0.0

    hud = obs["hud_meters"]
    assert hud["health_percent"] > 0.0
    assert hud["resource_percent"] > 0.0
    assert hud["stamina_percent"] > 0.0

    assert obs["target_count"] >= 1
    nearest = obs["nearest_targets"][0]
    assert "distance_to_crosshair" in nearest
    # Target center (600, 340) should be close to screen center (640, 360)
    assert nearest["distance_to_crosshair"] < 100.0


# ===========================================================================
# 2. DirectInput & Tactical Policy Tests
# ===========================================================================
def test_directinput_scancode_sequences():
    """Verify send_game_input_action parses keyboard scan codes and mouse actions properly."""
    game = GameInteractionLogistics()

    # Verify standard gaming keys are mapped in DIRECTINPUT_SCANCODES
    assert DIRECTINPUT_SCANCODES["w"] == 0x11
    assert DIRECTINPUT_SCANCODES["a"] == 0x1E
    assert DIRECTINPUT_SCANCODES["s"] == 0x1F
    assert DIRECTINPUT_SCANCODES["d"] == 0x20
    assert DIRECTINPUT_SCANCODES["space"] == 0x39
    assert DIRECTINPUT_SCANCODES["q"] == 0x10
    assert DIRECTINPUT_SCANCODES["e"] == 0x12
    assert DIRECTINPUT_SCANCODES["1"] == 0x02

    # Dispatch multi-token action sequence
    res = game.send_game_input_action("w,space,mouse_left,mouse_move_rel:10,-15", hold_ms=10)
    assert "[DirectInput Engine]" in res
    assert "4 action(s)" in res
    assert "Key'W'" in res
    assert "Key'SPACE'" in res
    assert "MouseLeft" in res
    assert "MouseMoveRel(10, -15)" in res

    # Empty sequence check
    err = game.send_game_input_action("")
    assert "Error" in err


def test_tactical_game_policy_action_rpg():
    """Verify evaluate_tactical_game_policy recommends emergency heal when health is critical."""
    game = GameInteractionLogistics()

    # Pre-seed critical health observation
    game._last_observation = {
        "hud_meters": {"health_percent": 22.0, "resource_percent": 80.0, "stamina_percent": 60.0},
        "nearest_targets": [{"target_id": 1, "pos": [600, 340], "distance_to_crosshair": 50.0}],
        "tactical_state": "CRITICAL_HEALTH",
    }

    report = game.evaluate_tactical_game_policy(game_genre="action_rpg", auto_execute=False)
    assert "EMERGENCY_HEAL_AND_EVADE" in report
    assert "1,s,space" in report
    assert "DirectInput Execution: Not requested" in report


def test_tactical_game_policy_moba_and_auto_execute():
    """Verify MOBA policy and auto_execute integration."""
    game = GameInteractionLogistics()

    # Pre-seed low health MOBA state
    game._last_observation = {
        "hud_meters": {"health_percent": 18.0, "resource_percent": 30.0},
        "nearest_targets": [],
        "tactical_state": "CRITICAL_HEALTH",
    }

    report = game.evaluate_tactical_game_policy(game_genre="moba", auto_execute=True)
    assert "BASE_RECALL" in report
    assert "'b'" in report
    assert "DirectInput Engine" in report


# ===========================================================================
# 3. Voice Biometrics & Speaker Diarization Tests
# ===========================================================================
def _generate_synthetic_voice(freq_hz: float, duration_s: float = 0.5, sample_rate: int = 16000) -> bytes:
    """Generates synthetic harmonic voice tone for testing acoustic pitch detection."""
    t = np.linspace(0, duration_s, int(sample_rate * duration_s), endpoint=False)
    # Fundamental + 2nd harmonic + 3rd harmonic to emulate human vocal cords
    signal = 0.6 * np.sin(2 * np.pi * freq_hz * t) + 0.3 * np.sin(2 * np.pi * 2 * freq_hz * t) + 0.1 * np.sin(2 * np.pi * 3 * freq_hz * t)
    return (signal * 32767).astype(np.int16).tobytes()


def test_acoustic_feature_extraction():
    """Verify FFT & autocorrelation extract accurate fundamental pitch F0."""
    # 1. Low male pitch: 110 Hz
    audio_110 = _generate_synthetic_voice(freq_hz=110.0)
    feat_110 = extract_acoustic_features(audio_110)
    assert 100.0 <= feat_110["f0_hz"] <= 120.0
    assert feat_110["spectral_centroid_hz"] > 0.0
    assert feat_110["spectral_rolloff_hz"] > 0.0

    # 2. Higher female pitch: 220 Hz
    audio_220 = _generate_synthetic_voice(freq_hz=220.0)
    feat_220 = extract_acoustic_features(audio_220)
    assert 210.0 <= feat_220["f0_hz"] <= 230.0


def test_speaker_diarization_director_qadir_vs_amira(tmp_path):
    """Verify voice biometric diarization correctly distinguishes Director Qadir from Amira."""
    voiceprints_file = str(tmp_path / ".alfred_voiceprints.json")
    meetings_dir = str(tmp_path / "meetings")
    mb = MeetingBiometricsLogistics(voiceprints_file=voiceprints_file, meetings_dir=meetings_dir)

    # 1. Test Director Qadir (110 Hz synthetic voice)
    qadir_voice = _generate_synthetic_voice(110.0)
    mb.cache_audio_buffer(qadir_voice)
    result_qadir = mb.enroll_or_identify_speaker(speaker_name="auto")
    assert "Identified Speaker: 'Director Qadir'" in result_qadir

    # 2. Test Amira (225 Hz synthetic voice)
    amira_voice = _generate_synthetic_voice(225.0)
    mb.cache_audio_buffer(amira_voice)
    result_amira = mb.enroll_or_identify_speaker(speaker_name="auto")
    assert "Identified Speaker: 'Amira'" in result_amira


def test_speaker_enrollment(tmp_path):
    """Verify custom speaker voiceprint calibration and persistence."""
    voiceprints_file = str(tmp_path / ".test_voiceprints.json")
    meetings_dir = str(tmp_path / "meetings")
    mb = MeetingBiometricsLogistics(voiceprints_file=voiceprints_file, meetings_dir=meetings_dir)

    custom_voice = _generate_synthetic_voice(150.0)
    mb.cache_audio_buffer(custom_voice)
    enroll_res = mb.enroll_or_identify_speaker(speaker_name="Special Guest")

    assert "Speaker: 'Special Guest' successfully calibrated" in enroll_res
    assert Path(voiceprints_file).exists()

    data = json.loads(Path(voiceprints_file).read_text(encoding="utf-8"))
    assert "Special Guest" in data
    assert 140.0 <= data["Special Guest"]["f0_hz"] <= 160.0


# ===========================================================================
# 4. UTC+8 Timestamping & Meeting Markdown Ledger Tests
# ===========================================================================
def test_strict_utc8_timestamp_formatting():
    """Verify get_utc8_timestamp returns strict [YYYY-MM-DD HH:MM:SS UTC+8] format."""
    ts_full = get_utc8_timestamp(full=True)
    assert re.match(r"^\[\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2} UTC\+8\]$", ts_full)

    ts_short = get_utc8_timestamp(full=False)
    assert re.match(r"^\[\d{2}:\d{2}:\d{2} UTC\+8\]$", ts_short)

    date_str = get_utc8_date_str()
    assert re.match(r"^\d{4}-\d{2}-\d{2}$", date_str)


def test_meeting_transcription_lifecycle(tmp_path):
    """Verify full meeting lifecycle: start, log with auto/explicit speaker, stop, and summary."""
    voiceprints_file = str(tmp_path / ".alfred_voiceprints.json")
    meetings_dir = str(tmp_path / "meetings")
    mb = MeetingBiometricsLogistics(voiceprints_file=voiceprints_file, meetings_dir=meetings_dir)

    # 1. Start meeting
    start_res = mb.manage_meeting_transcription(action="start")
    assert "Session started successfully" in start_res

    today_str = get_utc8_date_str()
    meeting_file = Path(meetings_dir) / f"meeting_{today_str}.md"
    assert meeting_file.exists()
    content = meeting_file.read_text(encoding="utf-8")
    assert "Executive Briefing & Meeting Log" in content
    assert "UTC+8" in content

    # 2. Log entry for Director Qadir
    qadir_voice = _generate_synthetic_voice(110.0)
    mb.cache_audio_buffer(qadir_voice)
    log_res_1 = mb.manage_meeting_transcription(
        action="log",
        speaker_label="auto",
        note="Approved Phase 15 Direct Game Interaction Suite deployment.",
    )
    assert "Recorded statement for [Director Qadir]" in log_res_1

    # 3. Log entry for Amira
    amira_voice = _generate_synthetic_voice(225.0)
    mb.cache_audio_buffer(amira_voice)
    log_res_2 = mb.manage_meeting_transcription(
        action="log",
        speaker_label="auto",
        note="Confirmed DirectInput scan-codes tested without virtual key latency.",
    )
    assert "Recorded statement for [Amira]" in log_res_2

    # 4. Check summary
    summary = mb.manage_meeting_transcription(action="summary")
    assert "[Director Qadir]" in summary
    assert "[Amira]" in summary
    assert "Approved Phase 15" in summary

    # 5. Stop meeting
    stop_res = mb.manage_meeting_transcription(action="stop")
    assert "Meeting concluded" in stop_res
    final_content = meeting_file.read_text(encoding="utf-8")
    assert "Session Concluded" in final_content
    assert "**Total Directives Logged**: 2" in final_content


# ===========================================================================
# 5. Phase 17 Universal Gaming Strategist & Continuous Overwatch Tests
# ===========================================================================
def test_multi_zone_hud_auto_profiler_archetypes(monkeypatch):
    """Verify auto-profiler correctly classifies bottom_globes, bottom_center_bar, and tactical_corners."""
    import cv2
    game = GameInteractionLogistics()

    # 1. Test bottom_globes (Diablo/PoE style)
    globe_frame = np.full((720, 1280, 3), 40, dtype=np.uint8)
    # Red Health globe at bottom-left: [500:680, 50:180] in BGR
    cv2.circle(globe_frame, (110, 590), 60, (0, 0, 220), -1)
    # Blue Mana globe at bottom-right: [500:680, 1100:1230] in BGR
    cv2.circle(globe_frame, (1170, 590), 60, (220, 100, 0), -1)

    monkeypatch.setattr(
        game,
        "_capture_window_bgr",
        lambda title: (globe_frame, {"width": 1280, "height": 720, "rect": {}}),
    )
    obs1 = json.loads(game.observe_game_state("arpg_window"))
    assert obs1["hud_archetype"] == "bottom_globes"
    assert obs1["game_state"] == "ACTIVE_GAMEPLAY"
    assert obs1["hud_meters"]["health_percent"] > 0.0

    # 2. Test bottom_center_bar (MOBA/MMO/Shooter style)
    center_frame = np.full((720, 1280, 3), 40, dtype=np.uint8)
    # Red health bar in bottom-center: [560:640, 440:840]
    center_frame[560:640, 440:840] = [0, 0, 220]

    monkeypatch.setattr(
        game,
        "_capture_window_bgr",
        lambda title: (center_frame, {"width": 1280, "height": 720, "rect": {}}),
    )
    obs2 = json.loads(game.observe_game_state("moba_window"))
    assert obs2["hud_archetype"] == "bottom_center_bar"
    assert obs2["game_state"] == "ACTIVE_GAMEPLAY"
    assert obs2["hud_meters"]["health_percent"] > 0.0


def test_loading_or_menu_screen_gate(monkeypatch):
    """Verify loading/menu gate flags LOADING_OR_MENU and NEVER triggers false low-HP warnings."""
    game = GameInteractionLogistics()

    # 1. Dark loading screen (luminance variance near 0)
    dark_loading_frame = np.full((720, 1280, 3), 8, dtype=np.uint8)
    monkeypatch.setattr(
        game,
        "_capture_window_bgr",
        lambda title: (dark_loading_frame, {"width": 1280, "height": 720, "rect": {}}),
    )
    obs = json.loads(game.observe_game_state("loading_screen"))
    assert obs["game_state"] == "LOADING_OR_MENU"
    assert obs["tactical_state"] == "OUT_OF_COMBAT"
    # Essential requirement: Never report 0% HP on loading screen!
    assert obs["hud_meters"]["health_percent"] == 100.0


def test_player_death_detection(monkeypatch):
    """Verify detection when calibrated HP drops from >20% to 0% during combat or on death overlay."""
    import cv2
    game = GameInteractionLogistics()

    # Step 1: Active gameplay frame with top-left health bar
    active_frame = np.full((720, 1280, 3), 45, dtype=np.uint8)
    active_frame[20:50, 40:240] = [0, 0, 220]

    monkeypatch.setattr(
        game,
        "_capture_window_bgr",
        lambda title: (active_frame, {"width": 1280, "height": 720, "rect": {}}),
    )
    obs_active = json.loads(game.observe_game_state("souls_game"))
    assert obs_active["game_state"] == "ACTIVE_GAMEPLAY"
    assert obs_active["hud_meters"]["health_percent"] > 20.0
    assert game._was_in_active_gameplay is True

    # Step 2: Sudden death overlay (large crimson center banner "YOU DIED")
    death_frame = np.full((720, 1280, 3), 35, dtype=np.uint8)
    # Draw crimson center banner [300:440, 350:930]
    death_frame[300:440, 350:930] = [0, 0, 210]

    monkeypatch.setattr(
        game,
        "_capture_window_bgr",
        lambda title: (death_frame, {"width": 1280, "height": 720, "rect": {}}),
    )
    obs_dead = json.loads(game.observe_game_state("souls_game"))
    assert obs_dead["game_state"] == "PLAYER_DEAD"
    assert obs_dead["tactical_state"] == "PLAYER_DEFEATED"
    assert obs_dead["hud_meters"]["health_percent"] == 0.0


def test_continuous_overwatch_daemon_lifecycle():
    """Verify continuous_watch parameter sets overwatch hook and parses stop directive."""
    game = GameInteractionLogistics()
    hook_calls = []

    def mock_hook(window_title, enable, auto_assist_keys):
        hook_calls.append((window_title, enable, auto_assist_keys))

    game.set_overwatch_handler(mock_hook)

    # Start overwatch
    obs_start = json.loads(game.observe_game_state("game.exe", continuous_watch=True, auto_assist_keys="1,space"))
    assert obs_start["continuous_overwatch"] == "ACTIVE"
    assert len(hook_calls) == 1
    assert hook_calls[-1] == ("game.exe", True, "1,space")

    # Stop overwatch via 'stop'
    obs_stop = json.loads(game.observe_game_state("stop", continuous_watch=True))
    assert obs_stop["continuous_overwatch"] == "STOPPED"
    assert len(hook_calls) == 2
    assert hook_calls[-1] == ("stop", False, "")


@pytest.mark.asyncio
async def test_live_session_overwatch_alerts_and_auto_assist():
    """Verify AlfredLiveCore continuous overwatch worker triggers vocal callouts and emergency inputs."""
    import asyncio
    from unittest.mock import AsyncMock, MagicMock
    from backend.live_session import AlfredLiveCore
    from backend.audio_manager import AudioManager
    from backend.vision_manager import VisionManager

    audio_mgr = AudioManager()
    vision_mgr = VisionManager()
    game_logistics = GameInteractionLogistics()

    transcript_history = []
    core = AlfredLiveCore(
        tools_list=[game_logistics.observe_game_state],
        audio_manager=audio_mgr,
        vision_manager=vision_mgr,
        game_logistics=game_logistics,
        on_transcript=lambda text: transcript_history.append(text),
    )

    core.is_running = True
    core.status = "listening"
    core._session = AsyncMock()

    # 1. Test Game Loaded Confirmation
    core._last_overwatch_state = "LOADING_OR_MENU"
    mock_active_obs = json.dumps({
        "game_state": "ACTIVE_GAMEPLAY",
        "hud_archetype": "top_left_bars",
        "hud_meters": {"health_percent": 100.0, "resource_percent": 100.0, "stamina_percent": 100.0},
        "nearest_targets": [],
    })
    with patch.object(game_logistics, "observe_game_state", return_value=mock_active_obs):
        # Trigger single cycle of overwatch logic
        core._overwatch_active = True
        core._overwatch_window = "elden_ring"
        task = asyncio.create_task(core._overwatch_worker())
        await asyncio.sleep(1.1)
        core.stop_game_overwatch()
        await task

    assert any("Game session confirmed" in t for t in transcript_history)

    # 2. Test Critical Health (<35%) and Auto-Assist Input
    transcript_history.clear()
    assist_executed = []
    mock_critical_obs = json.dumps({
        "game_state": "ACTIVE_GAMEPLAY",
        "hud_archetype": "top_left_bars",
        "hud_meters": {"health_percent": 24.5, "resource_percent": 50.0, "stamina_percent": 80.0},
        "nearest_targets": [{"target_id": 1, "distance_to_crosshair": 60}],
    })

    with patch.object(game_logistics, "observe_game_state", return_value=mock_critical_obs), \
         patch.object(game_logistics, "send_game_input_action", side_effect=lambda keys: assist_executed.append(keys)):
        core._overwatch_active = True
        core._overwatch_window = "elden_ring"
        core._overwatch_auto_assist = "1"  # Flask key
        core._last_overwatch_state = "ACTIVE_GAMEPLAY"
        core._last_hp_warning_time = 0.0

        task = asyncio.create_task(core._overwatch_worker())
        await asyncio.sleep(1.1)
        core.stop_game_overwatch()
        await task

    assert any("Critical vitality at 24.5%" in t for t in transcript_history)
    assert assist_executed == ["1"]
