"""
Jessie — backend/api/review.py
FastAPI router for code review endpoints.

POST /review/start  → SSE stream of progress + final result
GET  /review/history/{workspace_id}  → list of past reviews

Mount in api/main.py:
    from api.review import review_router
    app.include_router(review_router, prefix="/review")
"""

import asyncio
import json
import logging
import sqlite3
import time
from datetime import date
from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from agents.code_reviewer.node     import CodeReviewAgent
from agents.code_reviewer.scorer   import ReviewScorer
from agents.code_reviewer.reporter import MarkdownReporter
from gateway.auth_headers import auth_from_request, extract_auth_from_headers, get_team_id
from gateway.quota import QuotaManager, QuotaExceeded
from memory.store import DB_PATH

logger       = logging.getLogger(__name__)
review_router = APIRouter()

REVIEW_QUOTA_COST = 10   # a full review consumes 10 daily requests


def _flatten_ui_issues(results: dict) -> list[dict]:
    issues: list[dict] = []
    for layer in ("frontend", "backend", "database"):
        for cat, data in (results.get(layer) or {}).get("categories", {}).items():
            for iss in data.get("issues") or []:
                before = iss.get("example_before") or ""
                after = iss.get("example_after") or ""
                snippet = ""
                if before or after:
                    snippet = f"- {before}\n+ {after}".strip()
                issues.append({
                    "severity": iss.get("severity", "medium"),
                    "title": iss.get("title", "Issue"),
                    "detail": iss.get("detail", ""),
                    "description": iss.get("detail", ""),
                    "fix": iss.get("fix", ""),
                    "suggestion": iss.get("fix", ""),
                    "file": iss.get("file", ""),
                    "category": cat,
                    "layer": layer,
                    "rule": iss.get("rule", ""),
                    "line": iss.get("line", 0),
                    "example_before": before,
                    "example_after": after,
                    "code_snippet": snippet,
                })
    return issues


def _missing_from_impact(impact: dict) -> list[dict]:
    missing: list[dict] = []
    for item in impact.get("missing") or []:
        if isinstance(item, str):
            missing.append({
                "severity": "missing",
                "title": "Coverage gap",
                "detail": item,
                "description": item,
                "fix": "Add the missing coverage or document why it is deferred.",
                "file": "",
            })
            continue
        missing.append({
            "severity": "missing",
            "title": item.get("title") or "Coverage gap",
            "detail": item.get("detail") or "",
            "description": item.get("detail") or "",
            "fix": "Add the missing coverage or document why it is deferred.",
            "file": item.get("file") or "",
        })
    return missing[:5]


def _impact_markdown(impact: dict) -> str:
    if not impact:
        return ""
    lines = [
        "",
        "## Claude Impact Analysis",
        impact.get("summary") or "No summary.",
        "",
        "### Must change",
    ]
    for item in impact.get("must_change") or []:
        lines.append(
            f"- **[{item.get('severity', 'medium')}] {item.get('title', '')}** "
            f"(`{item.get('file', '')}`): {item.get('detail', '')}"
        )
        if item.get("fix"):
            lines.append(f"  - Fix: {item['fix']}")
    lines.append("")
    lines.append("### Missing")
    for item in impact.get("missing") or []:
        if isinstance(item, str):
            lines.append(f"- {item}")
        else:
            lines.append(f"- **{item.get('title', '')}** (`{item.get('file', '')}`): {item.get('detail', '')}")
    lines.append("")
    lines.append("### File-by-file changes")
    for item in impact.get("file_changes") or []:
        lines.append(f"- `{item.get('file', '')}`")
        for ch in item.get("changes") or []:
            lines.append(f"  - {ch}")
    lines.append("")
    lines.append("### Test checklist")
    for c in impact.get("test_checklist") or []:
        lines.append(f"- [ ] {c}")
    return "\n".join(lines)


# ── Review history table ───────────────────────────────────────────────────

def _ensure_review_table():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS review_history (
                id             INTEGER PRIMARY KEY AUTOINCREMENT,
                workspace_id   TEXT,
                user_id        TEXT,
                date           TEXT,
                overall_score  INTEGER,
                frontend_score INTEGER,
                backend_score  INTEGER,
                db_score       INTEGER,
                total_issues   INTEGER,
                critical_count INTEGER,
                report_path    TEXT,
                tokens_used    INTEGER,
                cost_estimate  REAL,
                created_at     TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.commit()


def _save_history(
    workspace_id: str, user_id: str, scores: dict,
    report_path: str, tokens: int, cost: float,
):
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            """
            INSERT INTO review_history
              (workspace_id, user_id, date, overall_score, frontend_score,
               backend_score, db_score, total_issues, critical_count,
               report_path, tokens_used, cost_estimate)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                workspace_id, user_id, date.today().isoformat(),
                scores.get("overall", 0),
                scores.get("frontend", {}).get("score", 0),
                scores.get("backend",  {}).get("score", 0),
                scores.get("database", {}).get("score", 0),
                scores.get("total_issues", 0),
                scores.get("severity_counts", {}).get("critical", 0),
                report_path, tokens, cost,
            ),
        )
        conn.commit()


_ensure_review_table()


# ── Request model ──────────────────────────────────────────────────────────

class ReviewRequest(BaseModel):
    user_id:      str
    workspace_id: str
    triggered_by: str = "command_palette"
    # Anthropic Claude API key (required — each user supplies their own)
    claude_api_key: str = ""
    # Azure Git mode (preferred for web)
    azure_url:    str = ""
    token:        str = ""
    branch:       str = ""
    # Local path mode (optional fallback)
    project_path: str = ""


# ── POST /review/start ─────────────────────────────────────────────────────

@review_router.post("/start")
async def start_review(req: ReviewRequest, request: Request):
    """
    SSE stream. Requires X-Claude-API-Key (or body claude_api_key for legacy clients).
    """
    auth = auth_from_request(request, require_key=False)
    api_key = (auth.api_key or req.claude_api_key or "").strip()
    if not api_key:
        extract_auth_from_headers(
            api_key="", provider=None, user_id=None, workspace_id=None, require_key=True,
        )

    user_id = auth.user_id if auth.user_id != "anon" else req.user_id
    workspace_id = auth.workspace_id if auth.workspace_id != "default" else req.workspace_id
    team_id = get_team_id(api_key)
    provider = auth.provider if auth.api_key else "anthropic"

    async def _generate():
        queue: asyncio.Queue = asyncio.Queue()

        def on_progress(event: dict):
            queue.put_nowait(event)

        async def _run():
            start_time = time.monotonic()
            temp_root = None
            project_path = (req.project_path or "").strip()
            try:
                if not api_key:
                    await queue.put({
                        "type": "error",
                        "code": "api_key_required",
                        "message": "Include your Claude API key in the X-Claude-API-Key header.",
                    })
                    return

                # ── Quota check ──────────────────────────────────────────────
                quota = QuotaManager(user_id=user_id, workspace_id=workspace_id, team_id=team_id)
                remaining = quota.remaining()
                if remaining < REVIEW_QUOTA_COST:
                    await queue.put({
                        "type":    "error",
                        "code":    "quota_insufficient",
                        "message": (
                            f"A project review costs {REVIEW_QUOTA_COST} daily requests. "
                            f"You have {remaining} remaining today. "
                            "Resets at midnight UTC."
                        ),
                    })
                    return

                # ── Resolve project folder (Azure clone or local path) ───────
                if req.azure_url.strip() and req.token.strip() and req.branch.strip():
                    from api.azure_git import clone_azure_branch, cleanup_clone

                    on_progress({"type": "progress", "message": "Connecting to Azure DevOps...", "pct": 5})
                    project_path, temp_root = await asyncio.to_thread(
                        clone_azure_branch,
                        azure_url=req.azure_url,
                        token=req.token,
                        branch=req.branch,
                        on_progress=on_progress,
                    )
                elif not project_path:
                    await queue.put({
                        "type": "error",
                        "code": "missing_source",
                        "message": "Provide Azure Git URL + PAT + branch (or a local project_path).",
                    })
                    return

                # ── Run the review ───────────────────────────────────────────
                agent   = CodeReviewAgent()
                results = await agent.review_project(
                    folder_path = project_path,
                    user_id     = user_id,
                    on_progress = on_progress,
                    claude_api_key = api_key,
                    provider = provider,
                )

                on_progress({"type": "progress", "message": "Calculating scores...", "pct": 95})

                scorer = ReviewScorer()
                scores = scorer.calculate_scores(
                    results.get("frontend", {}),
                    results.get("backend",  {}),
                    results.get("database", {}),
                )

                impact = results.get("impact_analysis") or {}
                issues = _flatten_ui_issues(results)
                missing_items = _missing_from_impact(impact)

                on_progress({"type": "progress", "message": "Generating report...", "pct": 98})

                meta      = results.get("meta", {})
                duration  = time.monotonic() - start_time
                reporter  = MarkdownReporter()
                report_label = (
                    f"{req.azure_url.strip()}@{req.branch.strip()}"
                    if req.azure_url.strip() else project_path
                )
                report_md = reporter.generate(
                    scores       = scores,
                    raw_results  = results,
                    project_path = report_label,
                    triggered_by = req.triggered_by,
                    model_used   = "claude-sonnet-4-6",
                    duration_s   = duration,
                    total_files  = meta.get("total_files", 0),
                    tokens_used  = meta.get("tokens_used", 0),
                    cost         = meta.get("cost_estimate", 0.0),
                )
                # Append Claude impact to markdown report
                report_md += _impact_markdown(impact)
                # Persist reports under Jessie workspace so Azure temp clones survive cleanup
                persist_root = str(Path(".jessie").resolve()) if temp_root else project_path
                report_path = reporter.save(report_md, persist_root)

                # ── Consume quota (10 credits for a full review) ─────────────
                try:
                    for _ in range(REVIEW_QUOTA_COST):
                        quota.consume()
                except QuotaExceeded:
                    pass  # consumed as many as available

                # ── Persist to review_history ────────────────────────────────
                _save_history(
                    workspace_id = req.workspace_id,
                    user_id      = req.user_id,
                    scores       = scores,
                    report_path  = report_path,
                    tokens       = meta.get("tokens_used", 0),
                    cost         = meta.get("cost_estimate", 0.0),
                )

                sev = scores.get("severity_counts", {})
                await queue.put({
                    "type":             "complete",
                    "overall_score":    scores["overall"],
                    "grade":            scores["grade"],
                    "frontend_score":   scores.get("frontend", {}).get("score", 0),
                    "backend_score":    scores.get("backend",  {}).get("score", 0),
                    "db_score":         scores.get("database", {}).get("score", 0),
                    "has_frontend":     scores.get("has_frontend", False),
                    "has_backend":      scores.get("has_backend", False),
                    "has_database":     scores.get("has_database", False),
                    "total_issues":     scores.get("total_issues", 0),
                    "critical_count":   sev.get("critical", 0),
                    "high_count":       sev.get("high", 0),
                    "medium_count":     sev.get("medium", 0),
                    "low_count":        sev.get("low", 0),
                    "missing_count":    len(missing_items),
                    "report_path":      report_path,
                    "duration_seconds": round(duration, 1),
                    "total_files":      meta.get("total_files", 0),
                    "tokens_used":      meta.get("tokens_used", 0),
                    "cost_estimate":    meta.get("cost_estimate", 0.0),
                    "branch":           req.branch or "",
                    "azure_url":        req.azure_url or "",
                    "issues":           issues,
                    "missing_items":    missing_items,
                    "impact_analysis":  impact,
                    "priority_fixes":   scores.get("priority_fixes", []),
                    "is_flutter":       bool(meta.get("is_flutter")),
                })

            except Exception as exc:
                logger.exception("Review pipeline failed")
                await queue.put({"type": "error", "code": "review_failed", "message": str(exc)})
            finally:
                if temp_root is not None:
                    from api.azure_git import cleanup_clone
                    cleanup_clone(temp_root)
                await queue.put(None)   # sentinel — tells _generate to stop

        asyncio.create_task(_run())

        while True:
            event = await queue.get()
            if event is None:
                break
            yield f"data: {json.dumps(event)}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(
        _generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ── GET /review/history/{workspace_id} ────────────────────────────────────

@review_router.get("/history/{workspace_id}")
async def review_history(workspace_id: str):
    """Last 20 reviews for this workspace."""
    with sqlite3.connect(DB_PATH) as conn:
        rows = conn.execute(
            """
            SELECT date, overall_score, frontend_score, backend_score,
                   db_score, total_issues, critical_count, report_path,
                   tokens_used, cost_estimate, created_at
            FROM review_history
            WHERE workspace_id = ?
            ORDER BY created_at DESC
            LIMIT 20
            """,
            (workspace_id,),
        ).fetchall()

    return [
        {
            "date":           r[0],
            "overall_score":  r[1],
            "frontend_score": r[2],
            "backend_score":  r[3],
            "db_score":       r[4],
            "total_issues":   r[5],
            "critical_count": r[6],
            "report_path":    r[7],
            "tokens_used":    r[8],
            "cost_estimate":  r[9],
            "created_at":     r[10],
        }
        for r in rows
    ]
