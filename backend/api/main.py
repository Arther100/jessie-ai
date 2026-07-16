"""
Jessie — backend/api/main.py

Two-phase API to work with vscode.lm (Copilot runs in the extension):

POST /prepare  — runs Prompt Coach + RAG Injector
               — returns improved_prompt + context + complexity_score
               — extension shows prompt diff, waits for developer approval
               — extension calls Copilot with approved prompt
               — extension POSTs Copilot output back

POST /resume   — runs Quality Analyser + Memory Writer
               — returns final_response + status_updates + quality_score

GET  /health   — liveness check
GET  /requests/{user_id} — request count for today
"""

import json
import os
import sqlite3
from datetime import date, timedelta
from pathlib import Path
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import List, Optional
from core.state import AgentState
from core.supervisor import supervisor_node
from agents.prompt_coach.node import prompt_coach_node
from agents.rag_injector.node import rag_injector_node
from agents.quality_analyser.node import quality_analyser_node
from agents.memory_writer.node import memory_writer_node
from memory.store import MemoryStore, DB_PATH
from gateway.proxy import process_request
from api.review import review_router
from api.merge_review import merge_router
from api.webhooks import webhook_router
from api.fs_browse import fs_router

app = FastAPI(title="Jessie API", version="1.0.0")

_ALLOWED_ORIGINS = [
    "http://localhost:3000",
    "http://localhost:3001",
    "https://*.vercel.app",
    "vscode-webview://*",
    os.getenv("ALLOWED_ORIGIN", "http://localhost:3000"),
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_ALLOWED_ORIGINS,
    allow_origin_regex=r"https://.*\.vercel\.app",
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(review_router,  prefix="/review")
app.include_router(merge_router,   prefix="/merge")
app.include_router(webhook_router, prefix="/webhook")
app.include_router(fs_router,      prefix="/fs")


# ── Request / Response models ──────────────────────────────────────────────

class PrepareRequest(BaseModel):
    prompt:             str
    user_id:            str
    workspace_id:       Optional[str] = ""
    language:           Optional[str] = ""
    open_file_content:  Optional[str] = ""
    selected_code:      Optional[str] = ""
    error_message:      Optional[str] = ""


class PrepareResponse(BaseModel):
    improved_prompt:    str
    prompt_diff:        str               # shown to developer for approval
    context_chunks:     List[str]
    complexity_score:   int               # 1-10 → extension picks Copilot model
    component_exists:   bool
    component_path:     str
    generated_code:     str               # set only if component_exists=True
    status_updates:     List[str]


class ResumeRequest(BaseModel):
    # Everything from PrepareResponse
    improved_prompt:    str
    prompt_diff:        str
    context_chunks:     List[str]
    complexity_score:   int
    component_exists:   bool
    component_path:     str
    # What Copilot returned
    generated_code:     str
    model_used:         str
    # Original context
    user_id:            str
    workspace_id:       str
    language:           str
    open_file_content:  Optional[str] = ""
    selected_code:      Optional[str] = ""
    error_message:      Optional[str] = ""
    retry_count:        Optional[int] = 0
    quality_feedback:   Optional[str] = ""


class ResumeResponse(BaseModel):
    final_response:     str
    quality_score:      int
    memory_saved:       bool
    memory_note:        str
    request_count:      int
    status_updates:     List[str]
    needs_retry:        bool              # True → extension should call Copilot again
    retry_prompt:       str              # improved prompt for retry


# ── /prepare endpoint ──────────────────────────────────────────────────────

@app.post("/prepare", response_model=PrepareResponse)
async def prepare(req: PrepareRequest):
    """
    Phase 1: Prompt Coach + RAG Injector.
    Returns improved prompt for developer approval.
    Extension calls Copilot after approval, then calls /resume.
    """
    state: AgentState = _base_state(req)

    # Run supervisor → prompt coach → rag injector
    state = supervisor_node(state)
    state = prompt_coach_node(state)

    # If trivial (complexity <= 2) skip RAG
    if state["complexity_score"] > 2:
        state = rag_injector_node(state)

    return PrepareResponse(
        improved_prompt  = state.get("improved_prompt", req.prompt),
        prompt_diff      = state.get("prompt_diff", ""),
        context_chunks   = state.get("context_chunks", []),
        complexity_score = state.get("complexity_score", 5),
        component_exists = state.get("component_exists", False),
        component_path   = state.get("component_path", ""),
        generated_code   = state.get("generated_code", ""),  # set if component reuse
        status_updates   = state.get("status_updates", []),
    )


# ── /resume endpoint ───────────────────────────────────────────────────────

@app.post("/resume", response_model=ResumeResponse)
async def resume(req: ResumeRequest):
    """
    Phase 2: Quality Analyser + Memory Writer.
    Receives Copilot's output from the extension.
    Returns final response or retry instruction.
    """
    state: AgentState = {
        "original_prompt":   req.improved_prompt,
        "improved_prompt":   req.improved_prompt,
        "prompt_diff":       req.prompt_diff,
        "user_id":           req.user_id,
        "workspace_id":      req.workspace_id,
        "language":          req.language,
        "open_file_content": req.open_file_content or "",
        "selected_code":     req.selected_code or "",
        "error_message":     req.error_message or "",
        "complexity_score":  req.complexity_score,
        "context_chunks":    req.context_chunks,
        "component_exists":  req.component_exists,
        "component_path":    req.component_path,
        "component_usage":   "",
        "generated_code":    req.generated_code,
        "model_used":        req.model_used,
        "quality_score":     0,
        "quality_feedback":  req.quality_feedback or "",
        "retry_count":       req.retry_count or 0,
        "memory_saved":      False,
        "memory_note":       "",
        "final_response":    "",
        "status_updates":    [],
        "request_count":     0,
        "prompt_approved":   True,
    }

    state = quality_analyser_node(state)
    needs_retry = state["quality_score"] < 70 and state["retry_count"] <= 2

    if not needs_retry:
        state = memory_writer_node(state)

    return ResumeResponse(
        final_response  = state.get("final_response", state.get("generated_code", "")),
        quality_score   = state["quality_score"],
        memory_saved    = state.get("memory_saved", False),
        memory_note     = state.get("memory_note", ""),
        request_count   = state.get("request_count", 0),
        status_updates  = state.get("status_updates", []),
        needs_retry     = needs_retry,
        retry_prompt    = (
            f"{req.improved_prompt}\n\n"
            f"[Fix required: {state.get('quality_feedback', '')}]"
        ) if needs_retry else "",
    )


# ── /proxy endpoint (gateway — Claude Code invisible middleware) ───────────

class ProxyRequest(BaseModel):
    prompt:            str
    user_id:           str
    workspace_id:      str
    language:          Optional[str] = ""
    open_file_content: Optional[str] = ""
    selected_code:     Optional[str] = ""
    error_message:     Optional[str] = ""
    priority:          Optional[int] = 0   # 0=normal, 1=senior dev


@app.post("/proxy")
async def proxy(req: ProxyRequest):
    """
    Full gateway pipeline streamed as Server-Sent Events.

    Each SSE frame is one JSON object on a  data: ...  line.
    Frame types:
      {"type": "status",  "message": "..."}          ← live status bar update
      {"type": "result",  "response": "...", ...}    ← final answer
      {"type": "error",   "code": "...", "message": "..."}

    The stream ends with  data: [DONE]
    """
    async def _generate():
        try:
            async for event in process_request(
                prompt            = req.prompt,
                user_id           = req.user_id,
                workspace_id      = req.workspace_id,
                language          = req.language or "",
                open_file_content = req.open_file_content or "",
                selected_code     = req.selected_code or "",
                error_message     = req.error_message or "",
                priority          = req.priority or 0,
            ):
                yield f"data: {json.dumps(event)}\n\n"
        except Exception as exc:
            err = {"type": "error", "code": "internal", "message": str(exc)}
            yield f"data: {json.dumps(err)}\n\n"
        finally:
            yield "data: [DONE]\n\n"

    return StreamingResponse(
        _generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",   # disable nginx buffering if proxied
        },
    )


# ── /team/usage ────────────────────────────────────────────────────────────

@app.get("/team/usage")
async def team_usage(workspace_id: str = "", user_id: str = "admin"):
    """Return today's request usage for all team members."""
    from gateway.quota import QuotaManager
    qm = QuotaManager(user_id=user_id, workspace_id=workspace_id)
    return {"date": __import__("datetime").date.today().isoformat(),
            "usage": qm.get_team_usage()}


# ── /health ────────────────────────────────────────────────────────────────

@app.get("/health")
async def health():
    return {"status": "ok", "version": "1.0.0"}


# ── /reports ───────────────────────────────────────────────────────────────

@app.get("/reports/file")
async def get_report_file(path: str):
    """Return raw markdown for a report path saved by Jessie."""
    from fastapi import HTTPException
    from fastapi.responses import PlainTextResponse

    report = Path(path)
    # Only allow files under known report roots for safety.
    allowed_roots = [
        (Path.cwd().parent / "reviews").resolve(),
        (Path.cwd() / "reviews").resolve(),
        Path("reviews").resolve(),
    ]
    try:
        resolved = report.resolve()
    except OSError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if not any(str(resolved).startswith(str(root)) for root in allowed_roots):
        # Still allow absolute paths under the Jessie workspace reviews folder.
        if "reviews" not in str(resolved).replace("\\", "/"):
            raise HTTPException(status_code=403, detail="Report path not allowed")

    if not resolved.is_file():
        raise HTTPException(status_code=404, detail=f"Report file not found: {path}")

    return PlainTextResponse(
        resolved.read_text(encoding="utf-8", errors="replace"),
        media_type="text/markdown; charset=utf-8",
    )


@app.get("/reports/{review_id}")
async def get_report(review_id: int):
    """Return markdown content + metadata for a report by ID."""
    with sqlite3.connect(DB_PATH) as conn:
        # Try code review first
        row = conn.execute(
            "SELECT id, workspace_id, user_id, date, overall_score, frontend_score, "
            "backend_score, db_score, total_issues, critical_count, report_path, "
            "tokens_used, cost_estimate, created_at FROM review_history WHERE id=?",
            (review_id,),
        ).fetchone()
        review_type = "code_review"

        if not row:
            # Try merge review
            try:
                row = conn.execute(
                    "SELECT id, workspace_id, user_id, date, overall_score, 0, 0, 0, "
                    "total_issues, critical_count, report_path, tokens_used, cost_estimate, "
                    "created_at FROM merge_review_history WHERE id=?",
                    (review_id,),
                ).fetchone()
                review_type = "merge_review"
            except sqlite3.OperationalError:
                row = None

    if not row:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail=f"Review {review_id} not found")

    report_path = row[10]
    try:
        markdown_content = Path(report_path).read_text(encoding="utf-8")
    except OSError:
        markdown_content = f"*Report file not found at: {report_path}*"

    return {
        "id":   row[0],
        "type": review_type,
        "metadata": {
            "workspace_id":   row[1],
            "user_id":        row[2],
            "date":           row[3],
            "overall_score":  row[4],
            "frontend_score": row[5],
            "backend_score":  row[6],
            "db_score":       row[7],
            "total_issues":   row[8],
            "critical_count": row[9],
            "report_path":    row[10],
            "tokens_used":    row[11],
            "cost_estimate":  row[12],
            "created_at":     row[13],
        },
        "markdown_content": markdown_content,
    }


# ── /dashboard/stats ──────────────────────────────────────────────────────

@app.get("/dashboard/stats")
async def dashboard_stats():
    """Summary data for the web dashboard."""
    today      = date.today()
    week_ago   = (today - timedelta(days=7)).isoformat()
    month_ago  = (today - timedelta(days=30)).isoformat()
    today_str  = today.isoformat()

    with sqlite3.connect(DB_PATH) as conn:
        # Reviews this week
        total_week = conn.execute(
            "SELECT COUNT(*) FROM review_history WHERE date >= ?", (week_ago,)
        ).fetchone()[0]

        # Average score this week
        avg_row = conn.execute(
            "SELECT AVG(overall_score) FROM review_history WHERE date >= ?", (week_ago,)
        ).fetchone()
        avg_score = round(avg_row[0] or 0, 1)

        # Critical issues this week
        crit_row = conn.execute(
            "SELECT SUM(critical_count) FROM review_history WHERE date >= ?", (week_ago,)
        ).fetchone()
        critical_total = int(crit_row[0] or 0)

        # Active members today
        active_row = conn.execute(
            "SELECT COUNT(DISTINCT user_id) FROM request_log WHERE date = ?", (today_str,)
        ).fetchone()
        active_members = active_row[0]

        # Score trend last 30 days
        trend_rows = conn.execute(
            """
            SELECT date,
                   AVG(overall_score)  as avg_score,
                   AVG(frontend_score) as frontend,
                   AVG(backend_score)  as backend,
                   AVG(db_score)       as database
            FROM review_history
            WHERE date >= ?
            GROUP BY date
            ORDER BY date ASC
            """,
            (month_ago,),
        ).fetchall()
        score_trend = [
            {
                "date":      r[0],
                "avg_score": round(r[1] or 0, 1),
                "frontend":  round(r[2] or 0, 1),
                "backend":   round(r[3] or 0, 1),
                "database":  round(r[4] or 0, 1),
            }
            for r in trend_rows
        ]

        # Recent 10 reviews
        recent_rows = conn.execute(
            """
            SELECT id, date, overall_score, frontend_score, backend_score,
                   db_score, total_issues, critical_count, report_path
            FROM review_history
            ORDER BY created_at DESC
            LIMIT 10
            """,
        ).fetchall()
        recent = [
            {
                "id":            r[0],
                "type":          "code_review",
                "date":          r[1],
                "project":       Path(r[8]).parents[1].name if r[8] else "Unknown",
                "overall_score": r[2],
                "grade":         ("A" if r[2] >= 90 else "B" if r[2] >= 80 else
                                  "C" if r[2] >= 70 else "D" if r[2] >= 60 else "F"),
                "total_issues":  r[6],
                "critical_count":r[7],
            }
            for r in recent_rows
        ]

    return {
        "reviews_this_week":       total_week,
        "avg_score_this_week":     avg_score,
        "critical_issues_this_week": critical_total,
        "active_members_today":    active_members,
        "score_trend":             score_trend,
        "recent_reviews":          recent,
    }


# ── PUT /team/quota/{user_id} ─────────────────────────────────────────────

class QuotaUpdate(BaseModel):
    daily_limit: int


@app.put("/team/quota/{user_id}")
async def update_quota(user_id: str, body: QuotaUpdate, x_user_id: str = ""):
    """Update daily limit for a team member. Only team leads may call this."""
    from gateway.quota import QuotaManager
    qm = QuotaManager(user_id=x_user_id or "admin", workspace_id="")
    qm.set_limit(user_id, body.daily_limit)
    return {"user_id": user_id, "new_limit": body.daily_limit}


@app.get("/requests/{user_id}")
async def get_requests(user_id: str):
    memory = MemoryStore()
    return {
        "user_id":       user_id,
        "requests_today": memory.get_request_count(user_id),
    }


# ── Helpers ────────────────────────────────────────────────────────────────

def _base_state(req: PrepareRequest) -> AgentState:
    return {
        "original_prompt":   req.prompt,
        "user_id":           req.user_id,
        "workspace_id":      req.workspace_id or "",
        "language":          req.language or "",
        "open_file_content": req.open_file_content or "",
        "selected_code":     req.selected_code or "",
        "error_message":     req.error_message or "",
        "improved_prompt":   "",
        "prompt_diff":       "",
        "prompt_approved":   False,
        "context_chunks":    [],
        "component_exists":  False,
        "component_path":    "",
        "component_usage":   "",
        "generated_code":    "",
        "model_used":        "",
        "complexity_score":  5,
        "quality_score":     0,
        "quality_feedback":  "",
        "retry_count":       0,
        "memory_saved":      False,
        "memory_note":       "",
        "final_response":    "",
        "status_updates":    [],
        "request_count":     0,
    }
