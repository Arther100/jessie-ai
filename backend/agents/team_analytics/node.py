"""Jessie v3 — Team analytics persistence + insights."""

from __future__ import annotations

import json
import logging
import sqlite3
from pathlib import Path
from typing import Optional

from gateway.model_router import ModelRouter

logger = logging.getLogger(__name__)
DB_PATH = Path(".jessie/jessie.db")


def _ensure_tables() -> None:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS ticket_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ticket_id TEXT,
                platform TEXT,
                user_id TEXT,
                workspace_id TEXT,
                action TEXT,
                complexity INTEGER,
                quality_score INTEGER,
                pr_created BOOLEAN,
                pr_number INTEGER,
                tokens_used INTEGER,
                cost_estimate REAL,
                duration_seconds INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS sprint_snapshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                workspace_id TEXT,
                sprint_name TEXT,
                health_score INTEGER,
                tickets_total INTEGER,
                tickets_done INTEGER,
                avg_code_quality REAL,
                ci_failure_rate REAL,
                ai_fixed_count INTEGER,
                snapshot_date TEXT,
                report_md TEXT,
                board_json TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        conn.commit()


class TeamAnalytics:
    def __init__(self):
        _ensure_tables()

    def log_ticket_action(self, **kwargs) -> None:
        with sqlite3.connect(DB_PATH) as conn:
            conn.execute(
                """
                INSERT INTO ticket_history
                (ticket_id, platform, user_id, workspace_id, action, complexity, quality_score,
                 pr_created, pr_number, tokens_used, cost_estimate, duration_seconds)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    kwargs.get("ticket_id"),
                    kwargs.get("platform"),
                    kwargs.get("user_id"),
                    kwargs.get("workspace_id"),
                    kwargs.get("action"),
                    kwargs.get("complexity", 0),
                    kwargs.get("quality_score", 0),
                    1 if kwargs.get("pr_created") else 0,
                    kwargs.get("pr_number", 0),
                    kwargs.get("tokens_used", 0),
                    kwargs.get("cost_estimate", 0.0),
                    kwargs.get("duration_seconds", 0),
                ),
            )
            conn.commit()

    def save_sprint_snapshot(self, **kwargs) -> None:
        with sqlite3.connect(DB_PATH) as conn:
            conn.execute(
                """
                INSERT INTO sprint_snapshots
                (workspace_id, sprint_name, health_score, tickets_total, tickets_done,
                 avg_code_quality, ci_failure_rate, ai_fixed_count, snapshot_date, report_md, board_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    kwargs.get("workspace_id"),
                    kwargs.get("sprint_name"),
                    kwargs.get("health_score", 0),
                    kwargs.get("tickets_total", 0),
                    kwargs.get("tickets_done", 0),
                    kwargs.get("avg_code_quality", 0.0),
                    kwargs.get("ci_failure_rate", 0.0),
                    kwargs.get("ai_fixed_count", 0),
                    kwargs.get("snapshot_date"),
                    kwargs.get("report_md", ""),
                    kwargs.get("board_json", ""),
                ),
            )
            conn.commit()

    def get_board(self, workspace_id: str) -> dict:
        with sqlite3.connect(DB_PATH) as conn:
            row = conn.execute(
                """
                SELECT board_json, sprint_name, health_score, created_at
                FROM sprint_snapshots
                WHERE workspace_id = ?
                ORDER BY created_at DESC LIMIT 1
                """,
                (workspace_id,),
            ).fetchone()
        if not row or not row[0]:
            return {"empty": True, "message": "No sprint scanned yet. Click Scan Sprint to analyse your current board."}
        try:
            board = json.loads(row[0])
        except Exception:
            board = {}
        board["sprint_name"] = row[1]
        board["health_score"] = row[2]
        board["scanned_at"] = row[3]
        return board

    def get_ticket_history(self, workspace_id: str) -> list[dict]:
        with sqlite3.connect(DB_PATH) as conn:
            rows = conn.execute(
                """
                SELECT ticket_id, pr_number, quality_score, created_at, cost_estimate, action, platform
                FROM ticket_history
                WHERE workspace_id = ? AND action = 'fix'
                ORDER BY created_at DESC LIMIT 50
                """,
                (workspace_id,),
            ).fetchall()
        return [
            {
                "ticket_id": r[0],
                "pr_number": r[1],
                "quality_score": r[2],
                "date": r[3],
                "cost": r[4],
                "action": r[5],
                "platform": r[6],
                "files_changed": [],
            }
            for r in rows
        ]

    def get_latest_report(self, workspace_id: str) -> str:
        with sqlite3.connect(DB_PATH) as conn:
            row = conn.execute(
                "SELECT report_md FROM sprint_snapshots WHERE workspace_id = ? ORDER BY created_at DESC LIMIT 1",
                (workspace_id,),
            ).fetchone()
        return (row[0] if row else "") or "# No weekly report yet\n\nRun sprint health analysis first.\n"

    def get_team_metrics(self, workspace_id: str, days: int = 30) -> dict:
        with sqlite3.connect(DB_PATH) as conn:
            rows = conn.execute(
                """
                SELECT user_id, quality_score, tokens_used, cost_estimate, pr_created, complexity
                FROM ticket_history
                WHERE workspace_id = ?
                  AND created_at >= datetime('now', ?)
                """,
                (workspace_id, f"-{int(days)} days"),
            ).fetchall()
        if not rows:
            return {
                "total_tickets_fixed": 0,
                "avg_quality_score": 0,
                "quality_trend": [],
                "ci_fixes_by_jessie": 0,
                "tokens_per_ticket": 0,
                "cost_per_ticket": 0,
                "most_common_issues": [],
                "top_contributors": [],
                "ai_vs_human_ratio": 0,
                "time_saved_hours": 0,
            }
        fixed = len(rows)
        avg_q = sum(r[1] or 0 for r in rows) / fixed
        tokens = sum(r[2] or 0 for r in rows) / fixed
        cost = sum(r[3] or 0 for r in rows) / fixed
        prs = sum(1 for r in rows if r[4])
        by_user: dict[str, int] = {}
        for r in rows:
            by_user[r[0] or "anon"] = by_user.get(r[0] or "anon", 0) + 1
        top = sorted([{"user_id": k, "tickets": v} for k, v in by_user.items()], key=lambda x: -x["tickets"])
        return {
            "total_tickets_fixed": fixed,
            "avg_quality_score": round(avg_q, 1),
            "quality_trend": [{"week": "recent", "score": round(avg_q, 1)}],
            "ci_fixes_by_jessie": 0,
            "tokens_per_ticket": round(tokens, 1),
            "cost_per_ticket": round(cost, 4),
            "most_common_issues": [{"type": "bug", "count": fixed}],
            "top_contributors": top,
            "ai_vs_human_ratio": round(prs / max(1, fixed), 2),
            "time_saved_hours": round(fixed * 0.75, 1),
        }

    async def generate_insights(self, metrics: dict, claude_api_key: str = "") -> list[str]:
        if not claude_api_key:
            return [
                f"{metrics.get('total_tickets_fixed', 0)} tickets handled by Jessie in the window.",
                f"Average quality score is {metrics.get('avg_quality_score', 0)}/100.",
                f"Estimated time saved: {metrics.get('time_saved_hours', 0)}h.",
            ]
        router = ModelRouter(api_key=claude_api_key)
        result = await router.call_claude(
            prompt=f"Team metrics JSON:\n{json.dumps(metrics)}\n\nReturn a JSON array of 3-5 short insight strings.",
            complexity_score=2,
            system_prompt="Return ONLY a JSON array of strings. Be specific and actionable.",
        )
        text = (result.get("response") or "").strip()
        try:
            if text.startswith("```"):
                text = text.strip("`")
                text = text.replace("json", "", 1).strip()
            data = json.loads(text)
            if isinstance(data, list):
                return [str(x) for x in data[:5]]
        except Exception:
            pass
        return [text[:300]] if text else []


# ensure on import
_ensure_tables()
