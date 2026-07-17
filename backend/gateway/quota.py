"""
Jessie — backend/gateway/quota.py
Per-member daily request quota enforcer.

Quota key: team_id + user_id + date (NOT the raw API key).
team_id = sha256(api_key)[:16] from auth_headers.get_team_id().

Default limit: 200 Jessie requests per user per day (not Claude tokens).
Claude token usage is controlled by the user's own provider rate limits.
"""

import sqlite3
import logging
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import List, Dict

logger = logging.getLogger(__name__)

DB_PATH = Path(".jessie/jessie.db")
MAX_REQUESTS_PER_DAY_DEFAULT = 200
DEFAULT_DAILY_LIMIT = MAX_REQUESTS_PER_DAY_DEFAULT


class QuotaExceeded(Exception):
    def __init__(self, message: str, reset_time: str):
        super().__init__(message)
        self.reset_time = reset_time


class QuotaManager:
    """
    Enforces per-member daily limits scoped by team_id (API key hash).
    """

    def __init__(self, user_id: str, workspace_id: str, team_id: str = "default"):
        self.user_id = user_id
        self.workspace_id = workspace_id
        self.team_id = team_id or "default"
        self._quota_key = f"{self.team_id}:{self.user_id}"
        self._ensure_table()

    def is_allowed(self) -> bool:
        return self._used_today() < self._limit()

    def remaining(self) -> int:
        return max(0, self._limit() - self._used_today())

    def consume(self) -> None:
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
                (self._quota_key, today),
            )
            conn.commit()

        logger.info(
            "Quota consumed: team=%s user=%s used=%s limit=%s",
            self.team_id, self.user_id, self._used_today(), self._limit(),
        )

    def get_team_usage(self) -> List[Dict]:
        today = date.today().isoformat()
        prefix = f"{self.team_id}:"
        with sqlite3.connect(DB_PATH) as conn:
            usage_rows = conn.execute(
                "SELECT user_id, count FROM request_log WHERE date=?",
                (today,),
            ).fetchall()
            limit_rows = conn.execute(
                "SELECT user_id, daily_limit FROM quota_limits"
            ).fetchall()

        limit_map = {r[0]: r[1] for r in limit_rows}
        result = []
        for row in usage_rows:
            full_key = row[0]
            if not full_key.startswith(prefix):
                continue
            uid = full_key[len(prefix):]
            lim = limit_map.get(full_key, limit_map.get(uid, DEFAULT_DAILY_LIMIT))
            result.append({
                "user_id": uid,
                "used": row[1],
                "limit": lim,
                "remaining": max(0, lim - row[1]),
            })
        return result

    def set_limit(self, user_id: str, limit: int) -> None:
        key = f"{self.team_id}:{user_id}"
        with sqlite3.connect(DB_PATH) as conn:
            conn.execute(
                """
                INSERT INTO quota_limits (user_id, daily_limit)
                VALUES (?, ?)
                ON CONFLICT(user_id) DO UPDATE SET
                    daily_limit = excluded.daily_limit
                """,
                (key, limit),
            )
            conn.commit()
        logger.info("Quota override set: team=%s user=%s new_limit=%s", self.team_id, user_id, limit)

    def _used_today(self) -> int:
        today = date.today().isoformat()
        with sqlite3.connect(DB_PATH) as conn:
            row = conn.execute(
                "SELECT count FROM request_log WHERE user_id=? AND date=?",
                (self._quota_key, today),
            ).fetchone()
        return row[0] if row else 0

    def _limit(self) -> int:
        with sqlite3.connect(DB_PATH) as conn:
            row = conn.execute(
                "SELECT daily_limit FROM quota_limits WHERE user_id=?",
                (self._quota_key,),
            ).fetchone()
        return row[0] if row else DEFAULT_DAILY_LIMIT

    def _ensure_table(self) -> None:
        DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(DB_PATH) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS quota_limits (
                    user_id     TEXT PRIMARY KEY,
                    daily_limit INTEGER NOT NULL DEFAULT 200
                )
                """
            )
            conn.commit()
