"""Unit tests for Phase 16: Autonomous Habit & Continuous Learning Engine and Strict UTC+8 Timezone Enforcement."""

import pytest
from backend.memory.memory_store import MemoryStore, get_utc8_now_str, get_utc8_hour
from backend.live_session import get_dynamic_system_prompt, ALFRED_SYSTEM_PROMPT


@pytest.fixture
def memory_store(tmp_path):
    db_file = str(tmp_path / "test_habits.db")
    chroma_dir = str(tmp_path / "test_habits_chroma")
    store = MemoryStore(db_path=db_file, chroma_dir=chroma_dir)
    yield store
    store.close()


def test_strict_utc8_timestamp_format():
    """Verify get_utc8_now_str returns a valid UTC+8 timestamp."""
    ts = get_utc8_now_str()
    assert "UTC+8" in ts
    # Format: YYYY-MM-DD HH:MM:SS UTC+8
    parts = ts.split()
    assert len(parts) == 3
    assert len(parts[0].split("-")) == 3
    assert len(parts[1].split(":")) == 3
    assert parts[2] == "UTC+8"

    hour = get_utc8_hour()
    assert 0 <= hour <= 23


def test_sqlite_utc8_timestamps_on_inserts(memory_store):
    """Verify SQLite tasks and audit logs store explicit UTC+8 timestamps."""
    # 1. Add Task
    add_res = memory_store.manage_executive_briefing(action="add", task_item="Verify Phase 16 UTC+8 timestamps")
    assert "Task #1" in add_res

    cursor = memory_store.conn.cursor()
    cursor.execute("SELECT created_at FROM tasks WHERE id = 1")
    row = cursor.fetchone()
    assert row is not None
    assert "UTC+8" in row["created_at"]

    # 2. Add Fact
    fact_res = memory_store.remember_fact(category="preference", content="Always address Director Qadir respectfully")
    assert "Committed to executive memory" in fact_res

    cursor.execute("SELECT timestamp FROM audit_log ORDER BY id DESC LIMIT 1")
    row = cursor.fetchone()
    assert row is not None
    assert "UTC+8" in row["timestamp"]


def test_automatic_preference_and_correction_extraction(memory_store):
    """Verify observe_and_learn_interaction extracts preferences, corrections, and habits."""
    # Preference 1: Always pattern
    res1 = memory_store.observe_and_learn_interaction(directive="Always use UTC+8 timezone for all schedules.")
    assert res1["status"] == "learned"
    assert "Always use UTC+8 timezone" in res1["preference"]

    # Preference 2: I prefer pattern
    res2 = memory_store.observe_and_learn_interaction(directive="I prefer concise executive briefings under 3 sentences.")
    assert res2["status"] == "learned"
    assert "I prefer concise executive briefings" in res2["preference"]

    # Correction 1: Name pronunciation correction
    res3 = memory_store.observe_and_learn_interaction(directive="It's not Qaidr but Qadir, pronounced as ka-dir.")
    assert res3["status"] == "learned"
    assert res3["preference"] != ""

    # Verify rows in director_habits
    cursor = memory_store.conn.cursor()
    cursor.execute("SELECT pattern_description, habit_category, frequency_count FROM director_habits")
    habits = cursor.fetchall()
    descriptions = [h["pattern_description"] for h in habits]

    assert any("Always use UTC+8 timezone" in d for d in descriptions)
    assert any("I prefer concise executive briefings" in d for d in descriptions)

    # Verify interaction_episodes table has episodes logged
    cursor.execute("SELECT COUNT(*) as c FROM interaction_episodes")
    assert cursor.fetchone()["c"] >= 3


def test_habit_frequency_tracking_and_utc8_hours(memory_store):
    """Verify workflow execution tracking increments frequency and tracks UTC+8 hour."""
    # Observe coding workflow via tool_used
    for _ in range(4):
        memory_store.observe_and_learn_interaction(directive="", tool_used="visual_code_edit")

    # Observe diagnostics workflow
    for _ in range(2):
        memory_store.observe_and_learn_interaction(directive="", tool_used="get_system_diagnostics")

    cursor = memory_store.conn.cursor()
    cursor.execute("SELECT pattern_description, frequency_count, typical_hour_utc8, last_observed_utc8 FROM director_habits WHERE habit_category = 'workflow'")
    workflows = {w["pattern_description"]: w for w in cursor.fetchall()}

    assert "Workflow: Coding & Development" in workflows
    assert workflows["Workflow: Coding & Development"]["frequency_count"] == 4
    assert "UTC+8" in workflows["Workflow: Coding & Development"]["last_observed_utc8"]

    assert "Workflow: System Telemetry & Diagnostics" in workflows
    assert workflows["Workflow: System Telemetry & Diagnostics"]["frequency_count"] == 2


def test_dynamic_system_prompt_injection(memory_store):
    """Verify get_dynamic_system_prompt injects live UTC+8 time and Director Qadir's profile."""
    # Seed learned preferences and agenda
    memory_store.observe_and_learn_interaction(directive="Always keep voice responses under 3 sentences.")
    memory_store.observe_and_learn_interaction(directive="I prefer dark mode in all UI views.")
    memory_store.manage_executive_briefing(action="add", task_item="Deploy Phase 16 Habit Engine")

    prompt = get_dynamic_system_prompt(memory_store)

    # 1. Base mandate check
    assert "TIMEZONE MANDATE: You operate strictly in UTC+8" in prompt
    assert "Director Qadir (pronounced \"ka-dir\")" in prompt

    # 2. Dynamic live time injection
    assert "CURRENT EXECUTIVE SYSTEM TIME:" in prompt
    assert "UTC+8" in prompt

    # 3. Dynamic learned profile injection
    assert "Always keep voice responses" in prompt
    assert "Deploy Phase 16 Habit Engine" in prompt


def test_inspect_learned_habits_and_growth_tool(memory_store):
    """Verify the inspect_learned_habits_and_growth tool reports habits, preferences, and custom notes."""
    memory_store.observe_and_learn_interaction(directive="Always verify code changes with pytest.")
    memory_store.observe_and_learn_interaction(directive="", tool_used="observe_game_state")

    # 1. Summary action
    summary = memory_store.inspect_learned_habits_and_growth(action="summary")
    assert "Continuous Learning & Habit Adaptation Ledger" in summary
    assert "Total Habits & Patterns Tracked" in summary
    assert "Verified Preferences" in summary

    # 2. Preferences action
    prefs = memory_store.inspect_learned_habits_and_growth(action="preferences")
    assert "Learned Director Preferences" in prefs
    assert "Always verify code changes" in prefs

    # 3. Habits action
    habits = memory_store.inspect_learned_habits_and_growth(action="habits")
    assert "Director Operational Workflow Habits" in habits
    assert "Workflow: Tactical Gaming Interaction" in habits

    # 4. Log custom note
    note_res = memory_store.inspect_learned_habits_and_growth(action="log_note", habit_note="Prefers 60 FPS ThreeJS orbit ring speed")
    assert "Logged custom habit note" in note_res

    # Check that note is in summary
    updated_summary = memory_store.inspect_learned_habits_and_growth(action="summary")
    assert "Prefers 60 FPS ThreeJS" in updated_summary
