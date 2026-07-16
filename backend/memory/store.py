"""
Jessie — backend/memory/store.py
3-layer isolated memory store.
Layer 1 — project:{workspace_id}:{topic}   → scoped to one project
Layer 2 — user:{user_id}:{topic}           → personal per developer
Layer 3 — team:global:{topic}              → universal rules only
Auto-initialises SQLite on first use. Zero setup commands.
"""

import sqlite3
import json
from pathlib import Path
from typing import Optional, Dict
from datetime import date

DB_PATH = Path(".jessie/jessie.db")


class MemoryStore:
    def __init__(self):
        self._ensure_db()

    # ── Layer 1: Project ───────────────────────────────────────────────────

    def write_project(self, workspace_id: str, topic: str, value: Dict):
        self._write(f"project:{workspace_id}:{topic}", value)

    def read_project(self, workspace_id: str, topic: str) -> Optional[Dict]:
        return self._read(f"project:{workspace_id}:{topic}")

    def search_project(self, workspace_id: str, prefix: str):
        return self._search(f"project:{workspace_id}:{prefix}")

    # ── Layer 2: User ──────────────────────────────────────────────────────

    def write_user(self, user_id: str, topic: str, value: Dict):
        self._write(f"user:{user_id}:{topic}", value)

    def read_user(self, user_id: str, topic: str) -> Optional[Dict]:
        return self._read(f"user:{user_id}:{topic}")

    # ── Layer 3: Team (universal only) ────────────────────────────────────

    def write_team(self, topic: str, value: Dict):
        self._write(f"team:global:{topic}", value)

    def read_team(self, topic: str) -> Optional[Dict]:
        return self._read(f"team:global:{topic}")

    # ── Read with fallback (Project → User → Team) ─────────────────────────

    def read_with_fallback(self, workspace_id: str, user_id: str, topic: str) -> Optional[Dict]:
        return (
            self.read_project(workspace_id, topic) or
            self.read_user(user_id, topic) or
            self.read_team(topic)
        )

    # ── Request count tracking (replaces token tracking in Phase 1) ────────

    def increment_request_count(self, user_id: str):
        today = date.today().isoformat()
        with sqlite3.connect(DB_PATH) as conn:
            conn.execute("""
                INSERT INTO request_log (user_id, date, count)
                VALUES (?, ?, 1)
                ON CONFLICT(user_id, date) DO UPDATE SET count = count + 1
            """, (user_id, today))
            conn.commit()

    def get_request_count(self, user_id: str) -> int:
        today = date.today().isoformat()
        with sqlite3.connect(DB_PATH) as conn:
            row = conn.execute(
                "SELECT count FROM request_log WHERE user_id=? AND date=?",
                (user_id, today)
            ).fetchone()
        return row[0] if row else 0

    # ── SQLite internals ───────────────────────────────────────────────────

    def _write(self, key: str, value: Dict):
        with sqlite3.connect(DB_PATH) as conn:
            conn.execute("""
                INSERT INTO memory (key, value, updated_at)
                VALUES (?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(key) DO UPDATE SET
                    value=excluded.value,
                    updated_at=CURRENT_TIMESTAMP
            """, (key, json.dumps(value)))
            conn.commit()

    def _read(self, key: str) -> Optional[Dict]:
        with sqlite3.connect(DB_PATH) as conn:
            row = conn.execute(
                "SELECT value FROM memory WHERE key=?", (key,)
            ).fetchone()
        return json.loads(row[0]) if row else None

    def _search(self, prefix: str):
        with sqlite3.connect(DB_PATH) as conn:
            rows = conn.execute(
                "SELECT key, value FROM memory WHERE key LIKE ?", (f"{prefix}%",)
            ).fetchall()
        return [{"key": r[0], "value": json.loads(r[1])} for r in rows]

    def _ensure_db(self):
        """Auto-initialises on first use. No setup command needed."""
        DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(DB_PATH) as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS memory (
                    key        TEXT PRIMARY KEY,
                    value      TEXT NOT NULL,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
                CREATE TABLE IF NOT EXISTS request_log (
                    user_id TEXT,
                    date    TEXT,
                    count   INTEGER DEFAULT 0,
                    PRIMARY KEY (user_id, date)
                );
            """)
            conn.commit()
