"""
Jessie — gateway/auth_headers.py
Extract BYOK credentials from request headers.
API keys are NEVER logged or persisted — only hashed for team isolation.
"""

from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass
from typing import Optional

from fastapi import Header, HTTPException, Request

logger = logging.getLogger(__name__)


def get_team_id(api_key: str) -> str:
    """SHA256 of API key → team identifier. Never store the key itself."""
    return hashlib.sha256((api_key or "").encode("utf-8")).hexdigest()[:16]


@dataclass
class JessieAuth:
    api_key: str
    provider: str
    user_id: str
    workspace_id: str
    team_id: str


def extract_auth_from_headers(
    *,
    api_key: Optional[str],
    provider: Optional[str],
    user_id: Optional[str],
    workspace_id: Optional[str],
    require_key: bool = True,
) -> JessieAuth:
    key = (api_key or "").strip()
    prov = (provider or "anthropic").strip().lower() or "anthropic"
    if prov not in ("anthropic", "openai", "gemini"):
        prov = "anthropic"
    uid = (user_id or "").strip() or "anon"
    wid = (workspace_id or "").strip() or "default"

    if require_key and not key:
        raise HTTPException(
            status_code=401,
            detail={
                "error": "api_key_required",
                "message": "Include your Claude API key in the X-Claude-API-Key header.",
                "help": "Get a key at console.anthropic.com",
            },
        )

    team = get_team_id(key) if key else "anonymous"
    return JessieAuth(
        api_key=key,
        provider=prov,
        user_id=uid,
        workspace_id=wid,
        team_id=team,
    )


async def require_jessie_auth(
    request: Request,
    x_claude_api_key: Optional[str] = Header(None, alias="X-Claude-API-Key"),
    x_ai_provider: Optional[str] = Header(None, alias="X-AI-Provider"),
    x_user_id: Optional[str] = Header(None, alias="X-User-Id"),
    x_workspace_id: Optional[str] = Header(None, alias="X-Workspace-Id"),
) -> JessieAuth:
    """FastAPI dependency — reads BYOK headers. Never logs the key."""
    # Also accept body fallbacks for gradual migration (prefer headers)
    return extract_auth_from_headers(
        api_key=x_claude_api_key,
        provider=x_ai_provider,
        user_id=x_user_id,
        workspace_id=x_workspace_id,
        require_key=True,
    )


def auth_from_request(request: Request, require_key: bool = True) -> JessieAuth:
    """Sync helper for SSE endpoints that take Request directly."""
    return extract_auth_from_headers(
        api_key=request.headers.get("X-Claude-API-Key") or request.headers.get("x-claude-api-key"),
        provider=request.headers.get("X-AI-Provider") or request.headers.get("x-ai-provider"),
        user_id=request.headers.get("X-User-Id") or request.headers.get("x-user-id"),
        workspace_id=request.headers.get("X-Workspace-Id") or request.headers.get("x-workspace-id"),
        require_key=require_key,
    )
