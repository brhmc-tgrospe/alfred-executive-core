"""A.L.F.R.E.D. Dual-Layer Memory Store.

Combines SQLite (WAL mode, thread-safe) for structured tasks and logs
with ChromaDB for long-term semantic context and preference memory.
Exposes strict type-hinted functions compatible with Gemini tool declarations.
Uses a fast, zero-dependency offline embedding model to eliminate cloud download stalls.
"""

from __future__ import annotations

import os
import sqlite3
import threading
import uuid
from typing import Optional, List
import numpy as np

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
        self._lock = threading.Lock()

        # Connect with WAL mode and thread safety
        self.conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self._init_sqlite()

        # 2. Initialize ChromaDB Vector Store
        if chroma_dir is None:
            base_dir = os.path.dirname(os.path.abspath(__file__))
            chroma_dir = os.path.join(base_dir, "chroma_data")
        self.chroma_dir = chroma_dir
        self.embedding_fn = embedding_function or FastLocalEmbeddingFunction()
        self.chroma_client = None
        self.facts_collection = None
        self._init_chroma()

    def _init_sqlite(self) -> None:
        """Configures SQLite WAL journal mode and required tables."""
        with self._lock:
            cursor = self.conn.cursor()
            cursor.execute("PRAGMA journal_mode=WAL;")
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS tasks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    task TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'pending',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS audit_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    event TEXT NOT NULL,
                    details TEXT,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """)
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
                cursor.execute("INSERT INTO tasks (task, status) VALUES (?, 'pending')", (task_item.strip(),))
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
                "INSERT INTO audit_log (event, details) VALUES (?, ?)",
                (f"REMEMBER_{category.upper()}", content),
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

    def close(self) -> None:
        """Closes the SQLite database connection."""
        with self._lock:
            if self.conn:
                self.conn.close()
