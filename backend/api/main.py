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
import time
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, RedirectResponse, StreamingResponse
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
from gateway.auth_headers import auth_from_request
from gateway.model_router import ModelRouter
from api.review import review_router
from api.merge_review import merge_router
from api.webhooks import webhook_router
from api.fs_browse import fs_router
from api.tickets import ticket_router, sprint_router, analytics_router

app = FastAPI(title="Jessie API", version="3.0.0")

_allowed = [
    "http://localhost:3000",
    "http://localhost:3001",
    "https://*.vercel.app",
    "vscode-webview://*",
    os.getenv("ALLOWED_ORIGIN", ""),
]
_ALLOWED_ORIGINS = [o for o in _allowed if o]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_ALLOWED_ORIGINS,
    allow_origin_regex=r"https://.*\.vercel\.app",
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def https_redirect_middleware(request: Request, call_next):
    """In production, prefer HTTPS (Railway terminates TLS; honor X-Forwarded-Proto)."""
    debug = os.getenv("JESSIE_DEBUG", "").lower() in ("1", "true", "yes")
    if not debug and os.getenv("RAILWAY_ENVIRONMENT"):
        proto = request.headers.get("x-forwarded-proto", request.url.scheme)
        if proto == "http":
            url = request.url.replace(scheme="https")
            return RedirectResponse(str(url), status_code=308)
    return await call_next(request)


# /verify rate limit: max 3 attempts per IP per hour
_VERIFY_ATTEMPTS: dict[str, list[float]] = defaultdict(list)
_VERIFY_MAX = 3
_VERIFY_WINDOW = 3600


def _check_verify_rate_limit(ip: str) -> bool:
    now = time.time()
    window = _VERIFY_ATTEMPTS[ip]
    _VERIFY_ATTEMPTS[ip] = [t for t in window if now - t < _VERIFY_WINDOW]
    if len(_VERIFY_ATTEMPTS[ip]) >= _VERIFY_MAX:
        return False
    _VERIFY_ATTEMPTS[ip].append(now)
    return True


app.include_router(review_router,  prefix="/review")
app.include_router(merge_router,   prefix="/merge")
app.include_router(webhook_router, prefix="/webhook")
app.include_router(fs_router,      prefix="/fs")
# Jessie v3 — DevOps intelligence (additive)
app.include_router(ticket_router,     prefix="/tickets")
app.include_router(sprint_router,     prefix="/sprint")
app.include_router(analytics_router,  prefix="/analytics")


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
async def prepare(req: PrepareRequest, request: Request):
    """
    Phase 1: Prompt Coach + RAG Injector.
    Requires X-Claude-API-Key (for team isolation) + X-User-Id + X-Workspace-Id.
    """
    auth = auth_from_request(request, require_key=True)
    state: AgentState = _base_state(req, auth.team_id, auth.provider, auth.api_key)
    if auth.user_id and auth.user_id != "anon":
        state["user_id"] = auth.user_id
    if auth.workspace_id and auth.workspace_id != "default":
        state["workspace_id"] = auth.workspace_id

    state = supervisor_node(state)
    state = prompt_coach_node(state)

    if state["complexity_score"] > 2:
        state = rag_injector_node(state)

    return PrepareResponse(
        improved_prompt  = state.get("improved_prompt", req.prompt),
        prompt_diff      = state.get("prompt_diff", ""),
        context_chunks   = state.get("context_chunks", []),
        complexity_score = state.get("complexity_score", 5),
        component_exists = state.get("component_exists", False),
        component_path   = state.get("component_path", ""),
        generated_code   = state.get("generated_code", ""),
        status_updates   = state.get("status_updates", []),
    )


# ── /resume endpoint ───────────────────────────────────────────────────────

@app.post("/resume", response_model=ResumeResponse)
async def resume(req: ResumeRequest, request: Request):
    """
    Phase 2: Quality Analyser + Memory Writer.
    """
    auth = auth_from_request(request, require_key=True)
    state: AgentState = {
        "original_prompt":   req.improved_prompt,
        "improved_prompt":   req.improved_prompt,
        "prompt_diff":       req.prompt_diff,
        "user_id":           auth.user_id or req.user_id,
        "workspace_id":      auth.workspace_id or req.workspace_id,
        "team_id":           auth.team_id,
        "ai_provider":       auth.provider,
        "claude_api_key":    auth.api_key,
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
    user_id:           str = ""
    workspace_id:      str = ""
    language:          Optional[str] = ""
    open_file_content: Optional[str] = ""
    selected_code:     Optional[str] = ""
    error_message:     Optional[str] = ""
    priority:          Optional[int] = 0


@app.post("/proxy")
async def proxy(req: ProxyRequest, request: Request):
    """Full gateway pipeline streamed as Server-Sent Events. Requires BYOK headers."""
    auth = auth_from_request(request, require_key=True)
    user_id = auth.user_id if auth.user_id != "anon" else (req.user_id or "anon")
    workspace_id = auth.workspace_id if auth.workspace_id != "default" else (req.workspace_id or "default")

    async def _generate():
        try:
            async for event in process_request(
                prompt            = req.prompt,
                user_id           = user_id,
                workspace_id      = workspace_id,
                language          = req.language or "",
                open_file_content = req.open_file_content or "",
                selected_code     = req.selected_code or "",
                error_message     = req.error_message or "",
                priority          = req.priority or 0,
                api_key           = auth.api_key,
                provider          = auth.provider,
                team_id           = auth.team_id,
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
            "X-Accel-Buffering": "no",
        },
    )


# ── /verify — validate BYOK API key (setup wizard) ─────────────────────────

@app.post("/verify")
async def verify_api_key(request: Request):
    """
    Minimal provider test call. Rate-limited: 3 attempts per IP per hour.
    Never stores the key.
    """
    client_ip = (
        request.headers.get("x-forwarded-for", "").split(",")[0].strip()
        or (request.client.host if request.client else "unknown")
    )
    if not _check_verify_rate_limit(client_ip):
        return JSONResponse(
            status_code=429,
            content={
                "valid": False,
                "error": "rate_limited",
                "message": "Too many verify attempts. Max 3 per hour. Try again later.",
            },
        )

    try:
        auth = auth_from_request(request, require_key=True)
    except Exception as exc:
        from fastapi import HTTPException
        if isinstance(exc, HTTPException):
            return JSONResponse(status_code=exc.status_code, content=exc.detail)
        raise

    try:
        router = ModelRouter(api_key=auth.api_key, provider=auth.provider)
        result = await router.verify_key()
        return result
    except Exception:
        # Never echo key material in errors
        return JSONResponse(
            status_code=401,
            content={
                "valid": False,
                "error": "invalid_key",
                "message": (
                    "API key rejected by Anthropic. Check your key at console.anthropic.com"
                    if auth.provider == "anthropic"
                    else f"API key rejected by {auth.provider.title()}. Check your key."
                ),
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
    return {"status": "ok", "version": "3.0.0"}


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

def _base_state(req: PrepareRequest, team_id: str = "default", provider: str = "anthropic", api_key: str = "") -> AgentState:
    return {
        "original_prompt":   req.prompt,
        "user_id":           req.user_id,
        "workspace_id":      req.workspace_id or "",
        "team_id":           team_id,
        "ai_provider":       provider,
        "claude_api_key":    api_key,
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
