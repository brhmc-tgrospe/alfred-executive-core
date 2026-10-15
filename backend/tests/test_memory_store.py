"""Unit tests for backend/memory/memory_store.py."""

import sqlite3
import threading
from backend.memory.memory_store import MemoryStore


def test_sqlite_wal_and_custom_paths(tmp_path):
    db_file = str(tmp_path / "test_alfred.db")
    chroma_dir = str(tmp_path / "test_chroma")

    store = MemoryStore(db_path=db_file, chroma_dir=chroma_dir)

    # Verify WAL journal mode
    cursor = store.conn.cursor()
    cursor.execute("PRAGMA journal_mode;")
    mode = cursor.fetchone()[0]
    assert mode.lower() == "wal"

    store.close()


def test_manage_executive_briefing(tmp_path):
    db_file = str(tmp_path / "test_briefing.db")
    chroma_dir = str(tmp_path / "test_chroma")

    store = MemoryStore(db_path=db_file, chroma_dir=chroma_dir)

    # 1. Initially empty
    listing = store.manage_executive_briefing("list")
    assert "no pending tasks" in listing.lower()

    # 2. Add task
    res = store.manage_executive_briefing("add", "Review Wayne Enterprises quarterly filings")
    assert "logged to executive agenda" in res.lower()

    # 3. List task
    listing = store.manage_executive_briefing("list")
    assert "Review Wayne Enterprises quarterly filings" in listing

    # 4. Complete task
    comp = store.manage_executive_briefing("complete", "Review Wayne")
    assert "marked as completed" in comp.lower()

    # 5. List should be empty again
    listing2 = store.manage_executive_briefing("list")
    assert "no pending tasks" in listing2.lower()

    store.close()


def test_remember_and_recall_fact(tmp_path):
    db_file = str(tmp_path / "test_semantic.db")
    chroma_dir = str(tmp_path / "test_chroma")

    store = MemoryStore(db_path=db_file, chroma_dir=chroma_dir)

    # Store fact
    store.remember_fact(
        category="preference",
        content="The Director prefers English Breakfast tea, served precisely at 07:00.",
    )

    # Recall context
    recalled = store.recall_context("What tea does the Director drink?")
    assert "English Breakfast" in recalled

    store.close()


def test_thread_safety(tmp_path):
    db_file = str(tmp_path / "test_concurrency.db")
    chroma_dir = str(tmp_path / "test_chroma")

    store = MemoryStore(db_path=db_file, chroma_dir=chroma_dir)

    def worker(i: int):
        store.manage_executive_briefing("add", f"Concurrent task {i}")

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(10)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    listing = store.manage_executive_briefing("list")
    assert listing.count("Concurrent task") == 10

    store.close()
