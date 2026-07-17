import asyncio
import json
import logging
import sqlite3
import time
from datetime import date
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from agents.merge_reviewer.node import MergeReviewAgent
from gateway.auth_headers import auth_from_request, extract_auth_from_headers, get_team_id
from memory.store import DB_PATH

logger = logging.getLogger(__name__)
merge_router = APIRouter()


def _ensure_merge_table() -> None:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS merge_review_history (
                id             INTEGER PRIMARY KEY AUTOINCREMENT,
                workspace_id   TEXT,
                user_id        TEXT,
                date           TEXT,
                verdict        TEXT,
                overall_score  INTEGER,
                total_issues   INTEGER,
                critical_count INTEGER,
                report_path    TEXT,
                tokens_used    INTEGER,
                cost_estimate  REAL,
                created_at     TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        conn.commit()


_ensure_merge_table()


class MergeReviewRequest(BaseModel):
    platform: str
    user_id: str
    workspace_id: str
    repo: str = ""
    token: str = ""
    azure_org: str = ""
    azure_project: str = ""
    gitlab_project_id: str = ""
    mode: str = "branch"
    pr_number: int | None = None
    base_branch: str = "main"
    head_branch: str = ""
    from_sha: str = ""
    to_sha: str = ""
    post_comments: bool = False
    repo_path: str = ""
    triggered_by: str = "web"
    # Anthropic Claude API key (required — each user supplies their own)
    claude_api_key: str = ""


def _save_merge_history(*, workspace_id: str, user_id: str, result: dict, report_path: str, tokens_used: int = 0, cost: float = 0.0) -> int:
    with sqlite3.connect(DB_PATH) as conn:
        cur = conn.execute(
            """
            INSERT INTO merge_review_history
                (workspace_id, user_id, date, verdict, overall_score, total_issues,
                 critical_count, report_path, tokens_used, cost_estimate)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                workspace_id,
                user_id,
                date.today().isoformat(),
                result.get("verdict", "needs_changes"),
                result.get("overall_score", 0),
                result.get("total_issues", 0),
                result.get("critical_count", 0),
                report_path,
                tokens_used,
                cost,
            ),
        )
        conn.commit()
        return int(cur.lastrowid)


def _write_merge_markdown(req: MergeReviewRequest, result: dict) -> str:
    reviews_dir = Path.cwd().parent / "reviews" / "merge"
    reviews_dir.mkdir(parents=True, exist_ok=True)
    report_name = f"merge-{req.workspace_id or 'workspace'}-{int(time.time())}.md"
    report_path = reviews_dir / report_name

    summary = result.get("change_summary") or {}
    impact = result.get("impact_analysis") or {}
    lines = [
        "# Jessie Merge Review",
        "",
        f"- Platform: {req.platform}",
        f"- Repository: {req.repo}",
        f"- Base branch: {result.get('metadata', {}).get('base_branch', req.base_branch)}",
        f"- Head branch: {result.get('metadata', {}).get('head_branch', req.head_branch)}",
        f"- Verdict: {result.get('verdict', 'needs_changes')}",
        f"- Overall score: {result.get('overall_score', 0)} ({result.get('grade', 'F')})",
        "",
        "## Claude Impact Analysis",
        impact.get("summary") or "No Claude summary available.",
        "",
        "### UI changes users will notice",
    ]
    for item in impact.get("ui_changes", []) or []:
        lines.append(f"- **{item.get('title', 'UI change')}** ({item.get('severity', 'medium')}): {item.get('detail', '')}")
        if item.get("files"):
            lines.append(f"  - Files: {', '.join(item.get('files') or [])}")
    lines.append("")
    lines.append("### Functionality / behaviour changes")
    for item in impact.get("functionality_changes", []) or []:
        lines.append(f"- **{item.get('title', 'Functionality change')}** ({item.get('severity', 'medium')}): {item.get('detail', '')}")
        if item.get("files"):
            lines.append(f"  - Files: {', '.join(item.get('files') or [])}")
    lines.append("")
    lines.append("### Issues you may face")
    for item in impact.get("expected_issues", []) or []:
        lines.append(f"- **{item.get('title', 'Issue')}** ({item.get('severity', 'medium')})")
        lines.append(f"  - What: {item.get('detail', '')}")
        lines.append(f"  - Why: {item.get('why', '')}")
        lines.append(f"  - Verify: {item.get('how_to_verify', '')}")
    lines.append("")
    lines.append("### Test checklist")
    for check in impact.get("test_checklist", []) or []:
        lines.append(f"- [ ] {check}")
    lines.append("")
    lines.append("## Risks")
    for issue in result.get("issues", []):
        lines.append(f"### [{issue.get('severity', 'low').upper()}] {issue.get('title', 'Issue')}")
        lines.append(issue.get("detail") or issue.get("description", ""))
        lines.append(f"Fix: {issue.get('fix') or issue.get('suggestion', '')}")
        if issue.get("code_snippet"):
            lines.append("```diff")
            lines.append(issue["code_snippet"])
            lines.append("```")
        lines.append("")

    lines.append("## Missing")
    for issue in result.get("missing_items", []):
        lines.append(f"### {issue.get('title', 'Missing')}")
        lines.append(issue.get("detail") or issue.get("description", ""))
        lines.append(f"Fix: {issue.get('fix') or issue.get('suggestion', '')}")
        if issue.get("code_snippet"):
            lines.append("```diff")
            lines.append(issue["code_snippet"])
            lines.append("```")
        lines.append("")

    lines.append("## Changed Files")
    for f in result.get("diff_files", []):
        lines.append(
            f"- `{f.get('filename', 'unknown')}` ({f.get('status', 'modified')}) "
            f"+{f.get('added', 0)} -{f.get('removed', 0)}"
        )

    report_path.write_text("\n".join(lines), encoding="utf-8")
    return str(report_path)


class AzureConnectRequest(BaseModel):
    platform: str
    repo: str
    token: str
    azure_org: str = ""
    azure_project: str = ""
    gitlab_project_id: str = ""


@merge_router.post("/open-prs")
async def open_prs(req: AzureConnectRequest):
    try:
        agent = MergeReviewAgent()
        prs = await asyncio.to_thread(
            agent.list_open_prs,
            platform=req.platform,
            repo=req.repo,
            token=req.token,
            azure_org=req.azure_org,
            azure_project=req.azure_project,
        )
        return {"prs": prs}
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@merge_router.post("/branches")
async def list_branches(req: AzureConnectRequest):
    try:
        agent = MergeReviewAgent()
        branches = await asyncio.to_thread(
            agent.list_branches,
            platform=req.platform,
            repo=req.repo,
            token=req.token,
            azure_org=req.azure_org,
            azure_project=req.azure_project,
        )
        return {"branches": branches}
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


# Keep GET for compatibility, but prefer POST (token not in URL).
@merge_router.get("/open-prs")
async def open_prs_get(
    platform: str = Query(...),
    repo: str = Query(...),
    token: str = Query(...),
    azure_org: str = Query(""),
    azure_project: str = Query(""),
):
    return await open_prs(AzureConnectRequest(
        platform=platform, repo=repo, token=token,
        azure_org=azure_org, azure_project=azure_project,
    ))


@merge_router.get("/branches")
async def list_branches_get(
    platform: str = Query(...),
    repo: str = Query(...),
    token: str = Query(...),
    azure_org: str = Query(""),
    azure_project: str = Query(""),
):
    return await list_branches(AzureConnectRequest(
        platform=platform, repo=repo, token=token,
        azure_org=azure_org, azure_project=azure_project,
    ))

@merge_router.post("/review")
async def review_merge(req: MergeReviewRequest, request: Request):
    auth = auth_from_request(request, require_key=False)
    api_key = (auth.api_key or req.claude_api_key or "").strip()
    if not api_key:
        extract_auth_from_headers(
            api_key="", provider=None, user_id=None, workspace_id=None, require_key=True,
        )
    user_id = auth.user_id if auth.user_id != "anon" else req.user_id
    workspace_id = auth.workspace_id if auth.workspace_id != "default" else req.workspace_id
    provider = auth.provider if auth.api_key else "anthropic"

    async def _generate():
        queue: asyncio.Queue = asyncio.Queue()

        def on_progress(event: dict):
            queue.put_nowait(event)

        async def _run():
            start = time.monotonic()
            try:
                if not api_key:
                    await queue.put({
                        "type": "error",
                        "code": "api_key_required",
                        "message": "Include your Claude API key in the X-Claude-API-Key header.",
                    })
                    return

                agent = MergeReviewAgent()
                result = await agent.review(
                    platform=req.platform,
                    repo=req.repo,
                    token=req.token,
                    mode=req.mode,
                    user_id=user_id,
                    workspace_id=workspace_id,
                    base_branch=req.base_branch,
                    head_branch=req.head_branch,
                    pr_number=req.pr_number,
                    azure_org=req.azure_org,
                    azure_project=req.azure_project,
                    gitlab_project_id=req.gitlab_project_id,
                    post_comments=req.post_comments,
                    on_progress=on_progress,
                    claude_api_key=api_key,
                    provider=provider,
                )
                report_path = _write_merge_markdown(req, result)
                review_id = _save_merge_history(
                    workspace_id=req.workspace_id,
                    user_id=req.user_id,
                    result=result,
                    report_path=report_path,
                )
                duration = time.monotonic() - start
                result["report_path"] = report_path
                result["duration_seconds"] = round(duration, 1)
                result["review_id"] = review_id
                await queue.put({"type": "complete", **result})
            except Exception as exc:
                logger.exception("Merge review failed")
                await queue.put({"type": "error", "code": "merge_review_failed", "message": str(exc)})
            finally:
                await queue.put(None)

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


@merge_router.get("/history/{workspace_id}")
async def merge_history(workspace_id: str):
    with sqlite3.connect(DB_PATH) as conn:
        rows = conn.execute(
            """
            SELECT date, verdict, overall_score, total_issues, critical_count, report_path,
                   cost_estimate, created_at
            FROM merge_review_history
            WHERE workspace_id = ?
            ORDER BY created_at DESC
            LIMIT 20
            """,
            (workspace_id,),
        ).fetchall()
    return [
        {
            "date": r[0],
            "verdict": r[1],
            "overall_score": r[2],
            "total_issues": r[3],
            "critical_count": r[4],
            "report_path": r[5],
            "cost_estimate": r[6],
            "created_at": r[7],
        }
        for r in rows
    ]
