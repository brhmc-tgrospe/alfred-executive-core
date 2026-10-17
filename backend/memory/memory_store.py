"""A.L.F.R.E.D. Dual-Layer Memory Store.

Combines SQLite (WAL mode, thread-safe) for structured tasks and logs
with ChromaDB for long-term semantic context and preference memory.
Exposes strict type-hinted functions compatible with Gemini tool declarations.
Uses a fast, zero-dependency offline embedding model to eliminate cloud download stalls.
"""

from __future__ import annotations

import json
import os
import re
import sqlite3
import threading
import uuid
from datetime import datetime, timezone, timedelta
from typing import Optional, List, Dict, Any
import numpy as np

def get_utc8_now_str() -> str:
    """Returns current timestamp string in strict UTC+8 timezone."""
    return datetime.now(timezone(timedelta(hours=8))).strftime("%Y-%m-%d %H:%M:%S UTC+8")

def get_utc8_hour() -> int:
    """Returns current hour (0-23) in strict UTC+8 timezone."""
    return datetime.now(timezone(timedelta(hours=8))).hour

try:
    import chromadb
    from chromadb.api.types import Documents, EmbeddingFunction, Embeddings
except ImportError:
    chromadb = None
    Documents = list
    Embeddings = list
    EmbeddingFunction = object


class FastLocalEmbeddingFunction(EmbeddingFunction[Documents]):
    """High-speed, zero-download local text embedding function for ChromaDB.

    Maps words and character tri-grams to a normalized dense vector space,
    providing instant offline semantic similarity without 80MB S3 downloads.
    """

    def __init__(self, dim: int = 256) -> None:
        self.dim = dim

    @staticmethod
    def name() -> str:
        return "fast_local_embedding"

    def get_config(self) -> dict:
        return {"dim": self.dim}

    @staticmethod
    def build_from_config(config: dict) -> "FastLocalEmbeddingFunction":
        return FastLocalEmbeddingFunction(dim=config.get("dim", 256))

    def __call__(self, input: Documents) -> Embeddings:
        embeddings: List[List[float]] = []
        for text in input:
            vec = np.zeros(self.dim, dtype=np.float32)
            clean_text = text.lower()
            words = clean_text.split()

            # Hash full words
            for word in words:
                idx = hash(word) % self.dim
                vec[idx] += 2.0

            # Hash character 3-grams for sub-word semantic capture
            for i in range(len(clean_text) - 2):
                ngram = clean_text[i : i + 3]
                idx = hash(ngram) % self.dim
                vec[idx] += 0.5

            norm = np.linalg.norm(vec)
            if norm > 0:
                vec /= norm
            embeddings.append(vec.tolist())

        return embeddings


class MemoryStore:
    """Manages SQLite structured memory and ChromaDB vector persistence."""

    def __init__(
        self,
        db_path: Optional[str] = None,
        chroma_dir: Optional[str] = None,
        embedding_function: Optional[EmbeddingFunction] = None,
    ) -> None:
        # 1. Initialize SQLite Database
        if db_path is None:
            base_dir = os.path.dirname(os.path.abspath(__file__))
            db_path = os.path.join(base_dir, "alfred_executive.db")
        self.db_path = db_path
        self._lock = threading.RLock()

        # Connect with WAL mode and thread safety
        self.conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self._init_sqlite()

        # Visual template storage directory
        base_dir = os.path.dirname(os.path.abspath(__file__))
        self.visual_templates_dir = os.path.join(base_dir, "visual_templates")
        os.makedirs(self.visual_templates_dir, exist_ok=True)

        # 2. Initialize ChromaDB Vector Store
        if chroma_dir is None:
            chroma_dir = os.path.join(base_dir, "chroma_data")
        self.chroma_dir = chroma_dir
        self.embedding_fn = embedding_function or FastLocalEmbeddingFunction()
        self.chroma_client = None
        self.facts_collection = None
        self._init_chroma()

    def _init_sqlite(self) -> None:
        """Configures SQLite WAL journal mode and required tables with strict UTC+8 timestamps."""
        with self._lock:
            cursor = self.conn.cursor()
            cursor.execute("PRAGMA journal_mode=WAL;")
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS tasks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    task TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'pending',
                    created_at TEXT NOT NULL
                );
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS audit_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    event TEXT NOT NULL,
                    details TEXT,
                    timestamp TEXT NOT NULL
                );
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS director_habits (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    habit_category TEXT NOT NULL,
                    pattern_description TEXT NOT NULL UNIQUE,
                    frequency_count INTEGER DEFAULT 1,
                    typical_hour_utc8 INTEGER,
                    last_observed_utc8 TEXT NOT NULL
                );
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS interaction_episodes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp_utc8 TEXT NOT NULL,
                    user_directive TEXT NOT NULL,
                    alfred_action TEXT,
                    learned_insight TEXT
                );
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS visual_ui_memories (
                    element_key TEXT PRIMARY KEY,
                    aliases TEXT NOT NULL DEFAULT '[]',
                    app_context TEXT DEFAULT '',
                    template_png_path TEXT NOT NULL,
                    core_png_path TEXT DEFAULT '',
                    hover_template_png_path TEXT DEFAULT '',
                    width INTEGER NOT NULL,
                    height INTEGER NOT NULL,
                    orb_features TEXT DEFAULT '',
                    hsv_hist TEXT DEFAULT '',
                    hover_behavior_desc TEXT DEFAULT '',
                    last_seen_x INTEGER DEFAULT -1,
                    last_seen_y INTEGER DEFAULT -1,
                    updated_at_utc8 TEXT NOT NULL
                );
            """)
            # Safe schema migrations for existing SQLite databases
            for col_def in (
                "core_png_path TEXT DEFAULT ''",
                "orb_features TEXT DEFAULT ''",
                "hsv_hist TEXT DEFAULT ''",
            ):
                try:
                    cursor.execute(f"ALTER TABLE visual_ui_memories ADD COLUMN {col_def};")
                except sqlite3.OperationalError:
                    pass
            self.conn.commit()

    def _init_chroma(self) -> None:
        """Initializes ChromaDB persistent client and collection."""
        if chromadb is None:
            return

        try:
            os.makedirs(self.chroma_dir, exist_ok=True)
            self.chroma_client = chromadb.PersistentClient(path=self.chroma_dir)
            self.facts_collection = self.chroma_client.get_or_create_collection(
                name="alfred_facts",
                embedding_function=self.embedding_fn,
            )
        except Exception as e:
            print(f"[MemoryStore] Warning: Could not initialize ChromaDB: {e}")
            self.chroma_client = None
            self.facts_collection = None

    def manage_executive_briefing(self, action: str, task_item: str = "") -> str:
        """Manages the daily executive briefing tasks.

        Args:
            action: Action to perform. Must be 'add', 'list', or 'complete'.
            task_item: The task description or ID to add or complete.

        Returns:
            A concise status briefing string for the Director.
        """
        action_clean = action.strip().lower()

        with self._lock:
            cursor = self.conn.cursor()

            if action_clean == "add":
                if not task_item.strip():
                    return "Error: Cannot add an empty task description."
                cursor.execute(
                    "INSERT INTO tasks (task, status, created_at) VALUES (?, 'pending', ?)",
                    (task_item.strip(), get_utc8_now_str()),
                )
                task_id = cursor.lastrowid
                self.conn.commit()
                return f"Task #{task_id} logged to executive agenda: '{task_item}'."

            if action_clean == "list":
                cursor.execute("SELECT id, task, status FROM tasks WHERE status = 'pending' ORDER BY id ASC")
                rows = cursor.fetchall()
                if not rows:
                    return "There are currently no pending tasks on your agenda, Sir."
                lines = ["Active Executive Agenda:"]
                for row in rows:
                    lines.append(f"• [#{row['id']}] {row['task']}")
                return "\n".join(lines)

            if action_clean == "complete":
                if not task_item.strip():
                    return "Error: Please specify the task ID or name to complete."

                # If numeric, complete by ID
                if task_item.strip().isdigit():
                    cursor.execute("UPDATE tasks SET status = 'completed' WHERE id = ?", (int(task_item.strip()),))
                else:
                    cursor.execute("UPDATE tasks SET status = 'completed' WHERE task LIKE ?", (f"%{task_item.strip()}%",))

                if cursor.rowcount > 0:
                    self.conn.commit()
                    return f"Task item '{task_item}' marked as completed, Sir."
                return f"No pending task found matching '{task_item}'."

            return f"Unrecognized action '{action}'. Available actions: 'add', 'list', 'complete'."

    def remember_fact(self, category: str, content: str) -> str:
        """Stores a persistent fact or preference into semantic vector memory.

        Args:
            category: Classification tag (e.g. 'preference', 'project', 'contact').
            content: The specific information or fact to commit to long-term memory.

        Returns:
            Confirmation that the fact has been memorized.
        """
        if not content.strip():
            return "Error: Cannot store empty memory content."

        fact_id = f"fact_{uuid.uuid4().hex[:8]}"

        # Store in ChromaDB if available
        if self.facts_collection is not None:
            try:
                self.facts_collection.add(
                    ids=[fact_id],
                    documents=[content],
                    metadatas=[{"category": category.lower().strip()}],
                )
            except Exception as e:
                return f"Failed to persist fact to vector store: {e}"

        # Also record in SQLite audit log
        with self._lock:
            cursor = self.conn.cursor()
            cursor.execute(
                "INSERT INTO audit_log (event, details, timestamp) VALUES (?, ?, ?)",
                (f"REMEMBER_{category.upper()}", content, get_utc8_now_str()),
            )
            self.conn.commit()

        return f"Committed to executive memory under '{category}': {content}"

    def recall_context(self, query: str) -> str:
        """Recalls relevant semantic facts and preferences based on a query.

        Args:
            query: The question or subject to search across semantic memories.

        Returns:
            Relevant retrieved facts formatted as context, or an empty notice.
        """
        if not query.strip():
            return "Please provide a query to recall context."

        if self.facts_collection is None:
            # Fallback search SQLite audit log
            with self._lock:
                cursor = self.conn.cursor()
                cursor.execute(
                    "SELECT details FROM audit_log WHERE details LIKE ? LIMIT 3",
                    (f"%{query.strip()}%",),
                )
                rows = cursor.fetchall()
                if rows:
                    results = [f"• {r['details']}" for r in rows]
                    return "Retrieved memories:\n" + "\n".join(results)
                return "No relevant memories found in archive."

        try:
            results = self.facts_collection.query(
                query_texts=[query],
                n_results=3,
            )
            documents = results.get("documents", [[]])[0]
            if not documents:
                return f"No memories found matching '{query}', Sir."

            formatted = [f"• {doc}" for doc in documents]
            return "Retrieved context from memory:\n" + "\n".join(formatted)
        except Exception as e:
            return f"Error recalling context: {e}"

    def observe_and_learn_interaction(self, directive: str = "", tool_used: str = "") -> Dict[str, Any]:
        """Observes user directives and tool execution, extracting habits, preferences, and episode logs in UTC+8.

        Args:
            directive: Natural language prompt or spoken turn from Director Qadir.
            tool_used: Name of the logistics tool executed (if any).

        Returns:
            Dictionary containing extracted insights and updated habit counts.
        """
        dir_clean = (directive or "").strip()
        tool_clean = (tool_used or "").strip()
        if not dir_clean and not tool_clean:
            return {"status": "skipped", "reason": "empty input"}

        utc8_now = get_utc8_now_str()
        current_hour = get_utc8_hour()
        learned_items: List[str] = []

        # 1. Map tool_used or directive keywords to high-level workflow
        workflow_name = ""
        if tool_clean:
            tool_lower = tool_clean.lower()
            if any(k in tool_lower for k in ("git", "code", "tail", "audit_source", "port")):
                workflow_name = "Workflow: Coding & Development"
            elif any(k in tool_lower for k in ("diagnostic", "network", "probe")):
                workflow_name = "Workflow: System Telemetry & Diagnostics"
            elif any(k in tool_lower for k in ("game", "policy", "scancode")):
                workflow_name = "Workflow: Tactical Gaming Interaction"
            elif any(k in tool_lower for k in ("meeting", "speaker", "diariz")):
                workflow_name = "Workflow: Executive Meeting Biometrics"
            elif any(k in tool_lower for k in ("word", "type_into", "keyboard", "window", "pixel")):
                workflow_name = "Workflow: Desktop GUI Automation"
            elif any(k in tool_lower for k in ("browser", "dom")):
                workflow_name = "Workflow: Autonomous Web Navigation"
            else:
                workflow_name = f"Workflow: {tool_clean}"
        elif dir_clean:
            dir_lower = dir_clean.lower()
            if any(k in dir_lower for k in ("code", "python", "script", "repo", "git", "debug")):
                workflow_name = "Workflow: Coding & Development"
            elif any(k in dir_lower for k in ("diagnostic", "cpu", "ram", "health", "system")):
                workflow_name = "Workflow: System Telemetry & Diagnostics"
            elif any(k in dir_lower for k in ("game", "rpg", "moba", "boss", "tactical")):
                workflow_name = "Workflow: Tactical Gaming Interaction"
            elif any(k in dir_lower for k in ("meeting", "transcribe", "minutes", "amira")):
                workflow_name = "Workflow: Executive Meeting Biometrics"

        # 2. Extract Preference and Correction Patterns from directive
        preference_extracted = ""
        category = "preference"

        patterns = [
            (r"(?i)\b(always\s+[^.!?\n,;]+)", "preference"),
            (r"(?i)\b(never\s+[^.!?\n,;]+)", "preference"),
            (r"(?i)\b(i\s+prefer\s+[^.!?\n,;]+)", "preference"),
            (r"(?i)\b(prefer\s+[^.!?\n,;]+)", "preference"),
            (r"(?i)\b(my\s+habit\s+is\s+[^.!?\n,;]+)", "preference"),
            (r"(?i)\b(use\s+utc\+8[^.!?\n,;]*)", "preference"),
            (r"(?i)\b(it'?s\s+not\s+[^.!?\n,;]+\s+but\s+[^.!?\n,;]+)", "correction"),
            (r"(?i)\b(pronounced\s+(?:as\s+)?[^.!?\n,;]+)", "correction"),
        ]

        if dir_clean:
            for pat, cat in patterns:
                m = re.search(pat, dir_clean)
                if m:
                    raw_pref = m.group(1).strip()
                    cleaned = raw_pref[0].upper() + raw_pref[1:]
                    cleaned = re.sub(r"\s+", " ", cleaned).strip()
                    preference_extracted = cleaned
                    category = cat
                    break

        with self._lock:
            cursor = self.conn.cursor()

            # Record workflow frequency
            if workflow_name:
                cursor.execute("""
                    INSERT INTO director_habits (habit_category, pattern_description, frequency_count, typical_hour_utc8, last_observed_utc8)
                    VALUES ('workflow', ?, 1, ?, ?)
                    ON CONFLICT(pattern_description) DO UPDATE SET
                        frequency_count = frequency_count + 1,
                        typical_hour_utc8 = excluded.typical_hour_utc8,
                        last_observed_utc8 = excluded.last_observed_utc8;
                """, (workflow_name, current_hour, utc8_now))
                learned_items.append(f"Recorded {workflow_name} at {current_hour:02d}:00 UTC+8")

            # Record preference/correction
            if preference_extracted:
                cursor.execute("""
                    INSERT INTO director_habits (habit_category, pattern_description, frequency_count, typical_hour_utc8, last_observed_utc8)
                    VALUES (?, ?, 1, ?, ?)
                    ON CONFLICT(pattern_description) DO UPDATE SET
                        frequency_count = frequency_count + 1,
                        typical_hour_utc8 = excluded.typical_hour_utc8,
                        last_observed_utc8 = excluded.last_observed_utc8;
                """, (category, preference_extracted, current_hour, utc8_now))
                learned_items.append(f"Learned {category}: '{preference_extracted}'")

            # Record interaction episode
            episode_action = tool_clean or ("Learned Directive" if preference_extracted else "Processed Prompt")
            episode_insight = preference_extracted or (f"Observed {workflow_name}" if workflow_name else dir_clean[:80])
            cursor.execute("""
                INSERT INTO interaction_episodes (timestamp_utc8, user_directive, alfred_action, learned_insight)
                VALUES (?, ?, ?, ?)
            """, (utc8_now, dir_clean or f"Action: {tool_clean}", episode_action, episode_insight))

            self.conn.commit()

        # Persist preference to ChromaDB if extracted
        if preference_extracted:
            try:
                self.remember_fact(category, preference_extracted)
            except Exception:
                pass

        return {
            "status": "learned",
            "workflow": workflow_name,
            "preference": preference_extracted,
            "learned_items": learned_items,
            "timestamp_utc8": utc8_now,
        }

    def build_dynamic_director_profile(self) -> str:
        """Summarizes Director Qadir's top learned preferences, recurring habits, recent episodes, and agenda."""
        with self._lock:
            cursor = self.conn.cursor()

            # Top preferences & corrections
            cursor.execute("""
                SELECT pattern_description, frequency_count
                FROM director_habits
                WHERE habit_category IN ('preference', 'correction')
                ORDER BY frequency_count DESC, id DESC
                LIMIT 5
            """)
            pref_rows = cursor.fetchall()

            # Recurring workflow habits
            cursor.execute("""
                SELECT pattern_description, frequency_count, typical_hour_utc8
                FROM director_habits
                WHERE habit_category = 'workflow'
                ORDER BY frequency_count DESC, id DESC
                LIMIT 5
            """)
            workflow_rows = cursor.fetchall()

            # Recent episodes
            cursor.execute("""
                SELECT timestamp_utc8, user_directive, learned_insight
                FROM interaction_episodes
                ORDER BY id DESC
                LIMIT 3
            """)
            episode_rows = cursor.fetchall()

            # Pending agenda
            cursor.execute("""
                SELECT id, task
                FROM tasks
                WHERE status = 'pending'
                ORDER BY id ASC
                LIMIT 5
            """)
            agenda_rows = cursor.fetchall()

            # Top 5 most recently learned facts from manage_semantic_memory / remember_fact
            cursor.execute("""
                SELECT event, details, timestamp
                FROM audit_log
                WHERE event LIKE 'REMEMBER_%'
                ORDER BY id DESC
                LIMIT 5
            """)
            recent_fact_rows = cursor.fetchall()

        lines = [
            f"[DYNAMIC EXECUTIVE MEMORY & LEARNED PROFILE - {get_utc8_now_str()}]:",
            '• Principal: Director Qadir (pronounced "ka-dir")',
            "• Mandatory Timezone: UTC+8 (Philippine Standard Time / Asia/Manila)",
        ]

        if pref_rows:
            lines.append("• Top Learned Preferences & Mandates:")
            for row in pref_rows:
                lines.append(f"  - {row['pattern_description']} (Observed {row['frequency_count']}x)")
        else:
            lines.append("• Top Learned Preferences: Standing by for initial pattern extraction.")

        if recent_fact_rows:
            lines.append("• Recently Studied Knowledge & Semantic Facts (Top 5):")
            for row in recent_fact_rows:
                cat_label = str(row["event"]).replace("REMEMBER_", "").lower()
                lines.append(f"  - [{cat_label} | {row['timestamp']}] {row['details'][:280]}")

        if workflow_rows:
            lines.append("• Recurring Operational Workflows & Typical Hours (UTC+8):")
            for row in workflow_rows:
                hour_str = f"{row['typical_hour_utc8']:02d}:00 UTC+8" if row['typical_hour_utc8'] is not None else "Variable"
                lines.append(f"  - {row['pattern_description']} (Typical Peak: {hour_str}, Frequency: {row['frequency_count']})")

        if episode_rows:
            lines.append("• Recent Interaction Episodes:")
            for row in episode_rows:
                lines.append(f"  - [{row['timestamp_utc8']}] \"{row['user_directive'][:60]}\" -> Insight: {row['learned_insight']}")

        if agenda_rows:
            lines.append("• Current Executive Agenda:")
            for row in agenda_rows:
                lines.append(f"  - Task #{row['id']}: {row['task']}")

        return "\n".join(lines)

    def inspect_learned_habits_and_growth(self, action: str = "summary", habit_note: str = "") -> str:
        """Inspects ALFRED's learned habits, Director preferences, and continuous adaptation metrics.

        Args:
            action: Action to perform: 'summary', 'preferences', 'habits', or 'log_note'.
            habit_note: Custom observation or habit pattern to log when action is 'log_note'.

        Returns:
            Formatted diagnostic report of ALFRED's learning and adaptation growth.
        """
        act = action.strip().lower()

        if act == "log_note":
            if not habit_note.strip():
                return "Error: habit_note cannot be empty when action is 'log_note'."
            self.observe_and_learn_interaction(directive=f"Note: {habit_note.strip()}")
            return f"Logged custom habit note into continuous memory ledger: '{habit_note.strip()}'."

        with self._lock:
            cursor = self.conn.cursor()

            if act == "preferences":
                cursor.execute("""
                    SELECT habit_category, pattern_description, frequency_count, last_observed_utc8
                    FROM director_habits
                    WHERE habit_category IN ('preference', 'correction')
                    ORDER BY frequency_count DESC, id DESC
                """)
                rows = cursor.fetchall()
                if not rows:
                    return "No specific preferences or corrections recorded in the learning ledger yet, Sir."
                lines = [f"Learned Director Preferences & Directives ({len(rows)} entries):"]
                for r in rows:
                    lines.append(f"• [{r['habit_category'].upper()}] {r['pattern_description']} (Observed {r['frequency_count']}x, Last: {r['last_observed_utc8']})")
                return "\n".join(lines)

            if act == "habits":
                cursor.execute("""
                    SELECT pattern_description, frequency_count, typical_hour_utc8, last_observed_utc8
                    FROM director_habits
                    WHERE habit_category = 'workflow'
                    ORDER BY frequency_count DESC, id DESC
                """)
                rows = cursor.fetchall()
                if not rows:
                    return "No operational workflow habits recorded yet, Sir."
                lines = [f"Director Operational Workflow Habits ({len(rows)} tracked):"]
                for r in rows:
                    hour_str = f"{r['typical_hour_utc8']:02d}:00 UTC+8" if r['typical_hour_utc8'] is not None else "N/A"
                    lines.append(f"• {r['pattern_description']} | Typical Peak: {hour_str} | Count: {r['frequency_count']} | Last: {r['last_observed_utc8']}")
                return "\n".join(lines)

            # Default: 'summary'
            cursor.execute("SELECT COUNT(*) AS c FROM director_habits")
            total_habits = cursor.fetchone()["c"]

            cursor.execute("SELECT COUNT(*) AS c FROM interaction_episodes")
            total_episodes = cursor.fetchone()["c"]

            cursor.execute("SELECT COUNT(*) AS c FROM director_habits WHERE habit_category IN ('preference', 'correction')")
            pref_count = cursor.fetchone()["c"]

        profile = self.build_dynamic_director_profile()

        summary = [
            "A.L.F.R.E.D. Continuous Learning & Habit Adaptation Ledger:",
            f"• Total Habits & Patterns Tracked: {total_habits}",
            f"• Total Interaction Episodes Recorded: {total_episodes}",
            f"• Verified Preferences / Mandates: {pref_count}",
            f"• Cognitive Status: Active Autonomous Learning & Real-Time Adaptation Online",
            "",
            profile,
        ]
        return "\n".join(summary)

    def save_visual_ui_memory(
        self,
        element_key: str,
        template_png_path: str,
        width: int,
        height: int,
        aliases: Optional[List[str]] = None,
        app_context: str = "",
        core_png_path: str = "",
        hover_template_png_path: str = "",
        orb_features: str = "",
        hsv_hist: str = "",
        hover_behavior_desc: str = "",
        last_seen_x: int = -1,
        last_seen_y: int = -1,
    ) -> dict:
        """Saves or updates a visual UI template memory record with adaptive inner-core, ORB, and HSV metadata."""
        norm_key = element_key.strip().lower()
        alias_list = [a.strip().lower() for a in (aliases or []) if a.strip()]
        if norm_key not in alias_list:
            alias_list.append(norm_key)
        aliases_json = json.dumps(alias_list)
        updated_utc8 = get_utc8_now_str()

        with self._lock:
            cursor = self.conn.cursor()
            cursor.execute("""
                INSERT INTO visual_ui_memories (
                    element_key, aliases, app_context, template_png_path,
                    core_png_path, hover_template_png_path, width, height,
                    orb_features, hsv_hist, hover_behavior_desc,
                    last_seen_x, last_seen_y, updated_at_utc8
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(element_key) DO UPDATE SET
                    aliases = excluded.aliases,
                    app_context = excluded.app_context,
                    template_png_path = excluded.template_png_path,
                    core_png_path = excluded.core_png_path,
                    hover_template_png_path = excluded.hover_template_png_path,
                    width = excluded.width,
                    height = excluded.height,
                    orb_features = excluded.orb_features,
                    hsv_hist = excluded.hsv_hist,
                    hover_behavior_desc = excluded.hover_behavior_desc,
                    last_seen_x = excluded.last_seen_x,
                    last_seen_y = excluded.last_seen_y,
                    updated_at_utc8 = excluded.updated_at_utc8;
            """, (
                norm_key, aliases_json, app_context, template_png_path,
                core_png_path, hover_template_png_path, width, height,
                orb_features, hsv_hist, hover_behavior_desc,
                last_seen_x, last_seen_y, updated_utc8
            ))
            self.conn.commit()

        return {
            "element_key": norm_key,
            "aliases": alias_list,
            "app_context": app_context,
            "template_png_path": template_png_path,
            "core_png_path": core_png_path,
            "hover_template_png_path": hover_template_png_path,
            "width": width,
            "height": height,
            "orb_features": orb_features,
            "hsv_hist": hsv_hist,
            "hover_behavior_desc": hover_behavior_desc,
            "last_seen_x": last_seen_x,
            "last_seen_y": last_seen_y,
            "updated_at_utc8": updated_utc8,
        }

    def get_visual_ui_memory(self, query_or_name: str) -> Optional[dict]:
        """Retrieves a visual UI template memory by exact key, alias, or fuzzy substring."""
        if not query_or_name:
            return None
        norm_query = query_or_name.strip().lower()

        with self._lock:
            cursor = self.conn.cursor()
            # 1. Exact match on element_key
            cursor.execute("SELECT * FROM visual_ui_memories WHERE element_key = ?", (norm_query,))
            row = cursor.fetchone()
            if row:
                return dict(row)

            # 2. Check all rows for substring or alias matches
            cursor.execute("SELECT * FROM visual_ui_memories ORDER BY updated_at_utc8 DESC")
            rows = cursor.fetchall()
            for r in rows:
                key = r["element_key"].lower()
                if norm_query in key or key in norm_query:
                    return dict(r)
                aliases = json.loads(r["aliases"] or "[]")
                if any(norm_query in a.lower() or a.lower() in norm_query for a in aliases):
                    return dict(r)

        return None

    def list_visual_ui_memories(self) -> List[dict]:
        """Lists all stored visual UI memories ordered by latest update."""
        with self._lock:
            cursor = self.conn.cursor()
            cursor.execute("SELECT * FROM visual_ui_memories ORDER BY updated_at_utc8 DESC")
            return [dict(r) for r in cursor.fetchall()]

    def close(self) -> None:
        """Closes the SQLite database connection."""
        with self._lock:
            if self.conn:
                self.conn.close()
