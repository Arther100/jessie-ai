"""
Jessie v3 — Ticket / Sprint / Analytics API (new router; additive).
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from datetime import date
from typing import Any, Optional

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from agents.sprint_intelligence.node import SprintIntelligence
from agents.sprint_scanner.node import SprintScanner
from agents.team_analytics.node import TeamAnalytics
from agents.ticket_agent.node import TicketAgent
from agents.ticket_agent.platforms.ticket_types import Ticket
from gateway.auth_headers import auth_from_request, extract_auth_from_headers, get_team_id
from gateway.quota import QuotaManager

logger = logging.getLogger(__name__)
ticket_router = APIRouter()

QUOTA_FIX = 8
QUOTA_SCAN = 3
QUOTA_HEALTH = 4


class TicketFixRequest(BaseModel):
    ticket_id: str
    platform: str
    platform_token: str
    workspace_id: str
    workspace_path: str = "."
    user_id: str
    claude_api_key: str = ""
    azure_org: str = ""
    azure_project: str = ""
    jira_url: str = ""
    jira_project: str = ""
    jira_email: str = ""
    github_repo: str = ""
    linear_team_id: str = ""
    language: str = "python"
    mock_ticket: Optional[dict] = None  # for local/dev without platform


class SprintScanRequest(BaseModel):
    platform: str
    token: str = ""
    platform_token: str = ""
    workspace_id: str
    user_id: str = "anon"
    claude_api_key: str = ""
    sprint_name: str = ""
    azure_org: str = ""
    azure_project: str = ""
    jira_url: str = ""
    jira_project: str = ""
    jira_email: str = ""
    github_repo: str = ""
    linear_team_id: str = ""
    mock_tickets: Optional[list[dict]] = None


class SprintHealthRequest(BaseModel):
    platform: str = "github"
    token: str = ""
    platform_token: str = ""
    workspace_id: str
    user_id: str = "anon"
    claude_api_key: str = ""
    azure_org: str = ""
    azure_project: str = ""
    jira_url: str = ""
    jira_project: str = ""
    github_repo: str = ""
    linear_team_id: str = ""


def _platform_kwargs(req: Any) -> dict:
    return {
        "azure_org": getattr(req, "azure_org", ""),
        "azure_project": getattr(req, "azure_project", ""),
        "jira_url": getattr(req, "jira_url", ""),
        "jira_project": getattr(req, "jira_project", ""),
        "jira_email": getattr(req, "jira_email", ""),
        "github_repo": getattr(req, "github_repo", ""),
        "linear_team_id": getattr(req, "linear_team_id", ""),
    }


def _sse(event: dict) -> str:
    return f"data: {json.dumps(event)}\n\n"


@ticket_router.post("/fix")
async def fix_ticket(req: TicketFixRequest, request: Request):
    auth = auth_from_request(request, require_key=False)
    api_key = (auth.api_key or req.claude_api_key or "").strip()
    if not api_key and not req.mock_ticket:
        extract_auth_from_headers(
            api_key="", provider=None, user_id=None, workspace_id=None, require_key=True,
        )
    user_id = auth.user_id if auth.user_id != "anon" else req.user_id
    workspace_id = auth.workspace_id if auth.workspace_id != "default" else req.workspace_id
    team_id = get_team_id(api_key) if api_key else "default"
    provider = auth.provider if auth.api_key else "anthropic"

    async def _generate():
        queue: asyncio.Queue = asyncio.Queue()

        def on_progress(event: dict):
            queue.put_nowait(event)

        async def _run():
            start = time.monotonic()
            try:
                if not api_key and not req.mock_ticket:
                    await queue.put({
                        "type": "error",
                        "code": "api_key_required",
                        "message": "Include your Claude API key in the X-Claude-API-Key header.",
                    })
                    return
                quota = QuotaManager(user_id=user_id, workspace_id=workspace_id, team_id=team_id)
                if quota.remaining() < QUOTA_FIX:
                    await queue.put({"type": "error", "code": "quota_insufficient", "message": f"Need {QUOTA_FIX} credits."})
                    return

                agent = TicketAgent()
                analytics = TeamAnalytics()

                if req.mock_ticket:
                    on_progress({"type": "progress", "message": f"Using mock ticket {req.ticket_id}...", "pct": 10})
                    t = req.mock_ticket
                    ticket = Ticket(
                        id=t.get("id") or req.ticket_id,
                        number=t.get("number") or req.ticket_id,
                        title=t.get("title") or "",
                        description=t.get("description") or "",
                        acceptance_criteria=t.get("acceptance_criteria") or "",
                        label=t.get("label") or "bug",
                        priority=t.get("priority") or "high",
                        status=t.get("status") or "todo",
                        comments=t.get("comments") or [],
                    )
                else:
                    on_progress({"type": "progress", "message": f"Reading ticket {req.ticket_id}...", "pct": 10})
                    if not api_key:
                        await queue.put({
                            "type": "error",
                            "code": "api_key_required",
                            "message": "API key is required for ticket fixes.",
                        })
                        return
                    ticket = await agent.read_ticket(
                        req.ticket_id, req.platform, req.platform_token, **_platform_kwargs(req)
                    )

                on_progress({"type": "progress", "message": "Scanning codebase for context...", "pct": 25})
                if not api_key:
                    await queue.put({
                        "type": "error",
                        "code": "api_key_required",
                        "message": "API key is required to generate a fix.",
                    })
                    return

                fix = await agent.generate_fix(
                    ticket,
                    claude_api_key=api_key,
                    workspace_id=workspace_id,
                    language=req.language,
                    on_progress=on_progress,
                    provider=provider,
                )

                if fix.get("rejected") or int(fix.get("quality_score") or 0) < 50:
                    await queue.put({
                        "type": "complete",
                        "ticket_id": ticket.id,
                        "rejected": True,
                        "quality_score": fix.get("quality_score", 0),
                        "fix_code": fix.get("fix", ""),
                        "fix_test": fix.get("test", ""),
                        "message": fix.get("reject_reason") or "Quality too low to open PR",
                        "files_changed": fix.get("files_changed") or [],
                        "tokens_used": fix.get("tokens_used", 0),
                        "cost_estimate": fix.get("cost_estimate", 0),
                    })
                    return

                pr = {"branch_name": "", "pr_number": 0, "pr_url": "", "files_changed": fix.get("files_changed") or []}
                try:
                    on_progress({"type": "progress", "message": "Creating branch & PR...", "pct": 75})
                    pr = await agent.create_branch_and_pr(
                        ticket,
                        fix,
                        req.workspace_path,
                        platform=req.platform,
                        token=req.platform_token,
                        github_repo=req.github_repo,
                        on_progress=on_progress,
                    )
                    on_progress({"type": "progress", "message": "Updating ticket board...", "pct": 95})
                    if not req.mock_ticket:
                        await agent.update_ticket_board(
                            ticket,
                            platform=req.platform,
                            token=req.platform_token,
                            pr_url=pr.get("pr_url") or "",
                            branch_name=pr.get("branch_name") or "",
                            quality_score=int(fix.get("quality_score") or 0),
                            files_changed=pr.get("files_changed") or [],
                            **_platform_kwargs(req),
                        )
                except Exception as git_exc:
                    logger.warning("Git/PR step: %s", git_exc)
                    pr["git_error"] = str(git_exc)

                duration = time.monotonic() - start
                for _ in range(QUOTA_FIX):
                    try:
                        quota.consume()
                    except Exception:
                        break
                analytics.log_ticket_action(
                    ticket_id=ticket.id,
                    platform=req.platform,
                    user_id=req.user_id,
                    workspace_id=req.workspace_id,
                    action="fix",
                    complexity=fix.get("complexity", 0),
                    quality_score=fix.get("quality_score", 0),
                    pr_created=bool(pr.get("pr_number")),
                    pr_number=pr.get("pr_number") or 0,
                    tokens_used=fix.get("tokens_used", 0),
                    cost_estimate=fix.get("cost_estimate", 0),
                    duration_seconds=int(duration),
                )
                await queue.put({
                    "type": "complete",
                    "ticket_id": ticket.id,
                    "branch": pr.get("branch_name"),
                    "pr_number": pr.get("pr_number") or 0,
                    "pr_url": pr.get("pr_url") or "",
                    "quality_score": fix.get("quality_score", 0),
                    "files_changed": pr.get("files_changed") or fix.get("files_changed") or [],
                    "explanation": fix.get("explanation", ""),
                    "fix_code": fix.get("fix", ""),
                    "fix_test": fix.get("test", ""),
                    "tokens_used": fix.get("tokens_used", 0),
                    "cost_estimate": fix.get("cost_estimate", 0),
                    "git_error": pr.get("git_error") or pr.get("push_error") or "",
                    "manual_hint": pr.get("manual_hint") or "",
                    "duration_seconds": round(duration, 1),
                })
            except Exception as exc:
                logger.exception("ticket fix failed")
                await queue.put({"type": "error", "code": "ticket_fix_failed", "message": str(exc)})
            finally:
                await queue.put(None)

        asyncio.create_task(_run())
        while True:
            event = await queue.get()
            if event is None:
                break
            yield _sse(event)
        yield "data: [DONE]\n\n"

    return StreamingResponse(_generate(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@ticket_router.post("/scan-sprint")
async def scan_sprint(req: SprintScanRequest):
    async def _generate():
        queue: asyncio.Queue = asyncio.Queue()

        def on_progress(event: dict):
            queue.put_nowait(event)

        async def _run():
            try:
                token = req.platform_token or req.token
                scanner = SprintScanner()
                analytics = TeamAnalytics()
                if req.mock_tickets is not None:
                    on_progress({"type": "progress", "message": "Classifying mock tickets...", "pct": 40})
                    classified = []
                    for t in req.mock_tickets:
                        ticket = Ticket(
                            id=t.get("id", ""),
                            number=t.get("number", ""),
                            title=t.get("title", ""),
                            description=t.get("description", ""),
                            acceptance_criteria=t.get("acceptance_criteria", ""),
                            label=t.get("label", "task"),
                            priority=t.get("priority", "medium"),
                            status=t.get("status", "todo"),
                        )
                        item = await scanner.classify_ticket(ticket, claude_api_key=req.claude_api_key)
                        classified.append({**ticket.to_dict(), **item})
                    from agents.ticket_agent.platforms.ticket_types import SprintData
                    sprint = SprintData(id="mock", name="Mock Sprint", tickets=[])
                    report = scanner.generate_sprint_report(classified, sprint)
                else:
                    report = await scanner.scan_sprint(
                        platform=req.platform,
                        token=token,
                        workspace_id=req.workspace_id,
                        claude_api_key=req.claude_api_key,
                        sprint_name=req.sprint_name or None,
                        on_progress=on_progress,
                        **_platform_kwargs(req),
                    )
                intel = SprintIntelligence()
                health = await intel.analyse_sprint_health(
                    {"name": report.get("sprint"), "end_date": report.get("end_date"), "tickets": report.get("classified") or []},
                    classified=report.get("classified") or [],
                )
                report_md = intel.generate_weekly_report({"name": report.get("sprint")}, health, analytics.get_team_metrics(req.workspace_id))
                analytics.save_sprint_snapshot(
                    workspace_id=req.workspace_id,
                    sprint_name=report.get("sprint"),
                    health_score=health.get("health_score", 0),
                    tickets_total=report.get("total", 0),
                    tickets_done=0,
                    avg_code_quality=health.get("avg_code_quality", 0),
                    ci_failure_rate=0,
                    ai_fixed_count=len(report.get("auto_fixable") or []),
                    snapshot_date=date.today().isoformat(),
                    report_md=report_md,
                    board_json=json.dumps({**report, "health": health}),
                )
                analytics.log_ticket_action(
                    ticket_id="sprint",
                    platform=req.platform,
                    user_id=req.user_id,
                    workspace_id=req.workspace_id,
                    action="scan",
                )
                await queue.put({"type": "complete", **report, "health": health})
            except Exception as exc:
                logger.exception("sprint scan failed")
                await queue.put({"type": "error", "code": "sprint_scan_failed", "message": str(exc)})
            finally:
                await queue.put(None)

        asyncio.create_task(_run())
        while True:
            event = await queue.get()
            if event is None:
                break
            yield _sse(event)
        yield "data: [DONE]\n\n"

    return StreamingResponse(_generate(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@ticket_router.get("/board/{workspace_id}")
async def ticket_board(workspace_id: str):
    return TeamAnalytics().get_board(workspace_id)


@ticket_router.get("/history/{workspace_id}")
async def ticket_history(workspace_id: str):
    return TeamAnalytics().get_ticket_history(workspace_id)


# ── Separate v3 mounts: /sprint and /analytics ─────────────────────────────
sprint_router = APIRouter()
analytics_router = APIRouter()


@sprint_router.post("/health")
async def sprint_health(req: SprintHealthRequest):
    analytics = TeamAnalytics()
    board = analytics.get_board(req.workspace_id)
    if board.get("empty"):
        return {"empty": True, "message": board.get("message")}
    health = board.get("health") or {}
    if not health:
        intel = SprintIntelligence()
        health = await intel.analyse_sprint_health(board, classified=board.get("classified") or [])
    return health


@sprint_router.get("/weekly-report/{workspace_id}")
async def weekly_report(workspace_id: str):
    return {"markdown": TeamAnalytics().get_latest_report(workspace_id)}


@analytics_router.get("/team/{workspace_id}")
async def team_metrics(workspace_id: str, days: int = 30):
    return TeamAnalytics().get_team_metrics(workspace_id, days=days)


@analytics_router.get("/insights/{workspace_id}")
async def team_insights(workspace_id: str, claude_api_key: str = ""):
    analytics = TeamAnalytics()
    metrics = analytics.get_team_metrics(workspace_id)
    insights = await analytics.generate_insights(metrics, claude_api_key=claude_api_key)
    return {"insights": insights, "metrics": metrics}
