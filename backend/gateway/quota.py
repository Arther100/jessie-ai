"""
Jessie — backend/gateway/quota.py
Per-member daily request quota enforcer.

Uses the existing SQLite DB at .jessie/jessie.db (same file as MemoryStore).
Adds one new table: quota_limits — for per-user overrides by team leads.
Reuses the existing request_log table for counting daily usage.

Default limit: 50 requests per user per day, reset at midnight UTC.

Usage:
    quota = QuotaManager("vijay", "abc123workspace")
    if not quota.is_allowed():
        raise QuotaExceeded(...)
    ... do work ...
    quota.consume()

Team lead override:
    quota.set_limit("junior_dev", 20)   # cap junior to 20/day
    quota.set_limit("senior_dev", 100)  # give senior more headroom
"""

import sqlite3
import logging
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import List, Dict

logger = logging.getLogger(__name__)

DB_PATH = Path(".jessie/jessie.db")
DEFAULT_DAILY_LIMIT = 50


class QuotaExceeded(Exception):
    """
    Raised when a user's daily request quota is exhausted.
    Carries reset_time (ISO 8601 UTC) so the caller can tell the user
    exactly when their quota refreshes.
    """
    def __init__(self, message: str, reset_time: str):
        super().__init__(message)
        self.reset_time = reset_time


class QuotaManager:
    """
    Enforces per-member daily limits stored in .jessie/jessie.db.

    All reads/writes use the shared SQLite file so the quota state
    survives backend restarts and is visible across all gateway instances.
    """

    def __init__(self, user_id: str, workspace_id: str):
        self.user_id     = user_id
        self.workspace_id = workspace_id
        self._ensure_table()

    # ── Core API ───────────────────────────────────────────────────────────

    def is_allowed(self) -> bool:
        """Returns True if the user has not yet reached their daily limit."""
        return self._used_today() < self._limit()

    def remaining(self) -> int:
        """How many requests the user has left today (never negative)."""
        return max(0, self._limit() - self._used_today())

    def consume(self) -> None:
        """
        Log one request against the user's daily quota.
        Must be called AFTER the request completes successfully so that
        failed/cached requests do not consume quota.
        Raises QuotaExceeded if the limit was already reached.
        """
        if not self.is_allowed():
            midnight_utc = datetime.now(timezone.utc).replace(
                hour=0, minute=0, second=0, microsecond=0
            ) + timedelta(days=1)
            raise QuotaExceeded(
                f"Daily limit of {self._limit()} requests reached for "
                f"'{self.user_id}'. Resets at midnight UTC.",
                reset_time=midnight_utc.isoformat(),
            )

        today = date.today().isoformat()
        with sqlite3.connect(DB_PATH) as conn:
            conn.execute(
                """
                INSERT INTO request_log (user_id, date, count)
                VALUES (?, ?, 1)
                ON CONFLICT(user_id, date) DO UPDATE SET count = count + 1
                """,
                (self.user_id, today),
            )
            conn.commit()

        logger.info(
            f"Quota consumed: user={self.user_id} "
            f"used={self._used_today()} limit={self._limit()}"
        )

    def get_team_usage(self) -> List[Dict]:
        """
        Return all team members' usage for today.
        Useful for a team dashboard or admin endpoint.

        Returns a list of dicts:
            [{"user_id": str, "used": int, "limit": int, "remaining": int}]
        """
        today = date.today().isoformat()
        with sqlite3.connect(DB_PATH) as conn:
            usage_rows = conn.execute(
                "SELECT user_id, count FROM request_log WHERE date=?",
                (today,),
            ).fetchall()
            limit_rows = conn.execute(
                "SELECT user_id, daily_limit FROM quota_limits"
            ).fetchall()

        limit_map = {r[0]: r[1] for r in limit_rows}
        return [
            {
                "user_id":   row[0],
                "used":      row[1],
                "limit":     limit_map.get(row[0], DEFAULT_DAILY_LIMIT),
                "remaining": max(
                    0, limit_map.get(row[0], DEFAULT_DAILY_LIMIT) - row[1]
                ),
            }
            for row in usage_rows
        ]

    def set_limit(self, user_id: str, limit: int) -> None:
        """
        Team lead override — set a custom daily limit for a specific user.
        Persists in quota_limits table. Takes effect on the next request.
        """
        with sqlite3.connect(DB_PATH) as conn:
            conn.execute(
                """
                INSERT INTO quota_limits (user_id, daily_limit)
                VALUES (?, ?)
                ON CONFLICT(user_id) DO UPDATE SET
                    daily_limit = excluded.daily_limit
                """,
                (user_id, limit),
            )
            conn.commit()
        logger.info(f"Quota override set: user={user_id} new_limit={limit}")

    # ── Private helpers ────────────────────────────────────────────────────

    def _used_today(self) -> int:
        today = date.today().isoformat()
        with sqlite3.connect(DB_PATH) as conn:
            row = conn.execute(
                "SELECT count FROM request_log WHERE user_id=? AND date=?",
                (self.user_id, today),
            ).fetchone()
        return row[0] if row else 0

    def _limit(self) -> int:
        with sqlite3.connect(DB_PATH) as conn:
            row = conn.execute(
                "SELECT daily_limit FROM quota_limits WHERE user_id=?",
                (self.user_id,),
            ).fetchone()
        return row[0] if row else DEFAULT_DAILY_LIMIT

    def _ensure_table(self) -> None:
        """Create quota_limits table if it doesn't exist yet."""
        DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(DB_PATH) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS quota_limits (
                    user_id     TEXT PRIMARY KEY,
                    daily_limit INTEGER NOT NULL DEFAULT 50
                )
                """
            )
            conn.commit()
