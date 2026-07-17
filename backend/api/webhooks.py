"""
Jessie — backend/api/webhooks.py
CI/CD webhook receivers for GitHub, Azure DevOps, and GitLab.

All endpoints return 200 immediately and run the review in the background
so that the platform's webhook timeout is never exceeded.

Mount in api/main.py:
    from api.webhooks import webhook_router
    app.include_router(webhook_router, prefix="/webhook")

Add to .jessie/.env:
    WEBHOOK_SECRET=<random 32-char string>
    GITHUB_TOKEN=<pat for posting comments>
"""

import asyncio
import hashlib
import hmac
import json
import logging
import os
from typing import Any

from fastapi import APIRouter, HTTPException, Request

logger         = logging.getLogger(__name__)
webhook_router = APIRouter()

WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET", "")
GITHUB_TOKEN   = os.getenv("GITHUB_TOKEN", "")


# ── Helpers ────────────────────────────────────────────────────────────────

def _verify_github_sig(body: bytes, sig_header: str) -> bool:
    if not WEBHOOK_SECRET or not sig_header:
        return True  # skip validation if no secret configured
    expected = "sha256=" + hmac.new(
        WEBHOOK_SECRET.encode(), body, hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(expected, sig_header)


async def _run_background_review(params: dict[str, Any]) -> None:
    """
    Full merge review pipeline without SSE streaming.
    Posts result as a PR comment on the originating platform.
    """
    try:
        from agents.merge_reviewer.node import MergeReviewAgent  # type: ignore
        agent = MergeReviewAgent()
        result = await agent.review(
            platform      = params["platform"],
            repo          = params["repo"],
            token         = params["token"],
            mode          = "pr",
            pr_number     = params.get("pr_number"),
            base_branch   = params.get("base_branch", "main"),
            head_branch   = params.get("head_branch", ""),
            user_id       = "webhook",
            workspace_id  = "webhook",
            post_comments = True,
            on_progress   = lambda e: None,
        )
        logger.info(
            "Webhook review complete: repo=%s pr=%s verdict=%s",
            params.get("repo"), params.get("pr_number"), result.get("verdict"),
        )
    except Exception:
        logger.exception("Background webhook review failed for %s", params.get("repo"))


# ── GET /webhook/test ─────────────────────────────────────────────────────

@webhook_router.get("/test")
async def webhook_test():
    """Smoke-test endpoint. Returns 200 with Jessie version."""
    return {"status": "ok", "version": "1.0.0"}


# ── POST /webhook/github ──────────────────────────────────────────────────

@webhook_router.post("/github")
async def webhook_github(request: Request):
    """
    Receives GitHub webhook payloads.
    Validates X-Hub-Signature-256.
    Triggers a merge review on pull_request opened/synchronize.
    """
    body = await request.body()
    sig  = request.headers.get("X-Hub-Signature-256", "")

    if not _verify_github_sig(body, sig):
        raise HTTPException(status_code=401, detail="Invalid signature")

    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON")

    event = request.headers.get("X-GitHub-Event", "")
    action = payload.get("action", "")

    if event == "ping":
        return {"message": "pong", "version": "1.0.0"}

    if event == "pull_request" and action in ("opened", "synchronize", "reopened"):
        pr   = payload.get("pull_request", {})
        repo = payload.get("repository", {}).get("full_name", "")
        asyncio.create_task(_run_background_review({
            "platform":    "github",
            "repo":        repo,
            "token":       GITHUB_TOKEN,
            "pr_number":   pr.get("number"),
            "base_branch": pr.get("base", {}).get("ref", "main"),
            "head_branch": pr.get("head", {}).get("ref", ""),
            "author":      pr.get("user", {}).get("login", ""),
        }))
        logger.info("GitHub webhook — queued review for %s PR #%s", repo, pr.get("number"))

    return {"accepted": True}


# ── POST /webhook/azure ────────────────────────────────────────────────────

@webhook_router.post("/azure")
async def webhook_azure(request: Request):
    """
    Receives Azure DevOps service hook payloads.
    Triggers a merge review on git.pullrequest.created/updated.
    """
    try:
        payload = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON")

    event_type = payload.get("eventType", "")

    if event_type in ("git.pullrequest.created", "git.pullrequest.updated"):
        resource = payload.get("resource", {})
        repo     = resource.get("repository", {}).get("name", "")
        pr_id    = resource.get("pullRequestId")
        base_ref = resource.get("targetRefName", "refs/heads/main").replace("refs/heads/", "")
        head_ref = resource.get("sourceRefName", "").replace("refs/heads/", "")

        asyncio.create_task(_run_background_review({
            "platform":    "azure",
            "repo":        repo,
            "token":       os.getenv("AZURE_TOKEN", ""),
            "pr_number":   pr_id,
            "base_branch": base_ref,
            "head_branch": head_ref,
        }))
        logger.info("Azure webhook — queued review for %s PR #%s", repo, pr_id)

    return {"accepted": True}


# ── POST /webhook/gitlab ───────────────────────────────────────────────────

@webhook_router.post("/gitlab")
async def webhook_gitlab(request: Request):
    """
    Receives GitLab webhook payloads.
    Triggers a merge review on merge_request events.
    """
    try:
        payload = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON")

    if payload.get("object_kind") == "merge_request":
        mr     = payload.get("object_attributes", {})
        action = mr.get("action", "")

        if action in ("open", "update", "reopen"):
            project_id = payload.get("project", {}).get("id", "")
            mr_iid     = mr.get("iid")
            source_ref = mr.get("source_branch", "")
            target_ref = mr.get("target_branch", "main")

            asyncio.create_task(_run_background_review({
                "platform":          "gitlab",
                "repo":              str(project_id),
                "token":             os.getenv("GITLAB_TOKEN", ""),
                "pr_number":         mr_iid,
                "base_branch":       target_ref,
                "head_branch":       source_ref,
                "gitlab_project_id": str(project_id),
            }))
            logger.info("GitLab webhook — queued review for project %s MR !%s", project_id, mr_iid)

    return {"accepted": True}


# ── Jessie v3 — CI/CD failure webhooks (additive) ──────────────────────────

@webhook_router.post("/github/actions")
async def webhook_github_actions(request: Request):
    try:
        payload = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON")

    if payload.get("action") != "completed":
        return {"accepted": True, "skipped": True}
    run = payload.get("workflow_run") or {}
    if run.get("conclusion") != "failure":
        return {"accepted": True, "skipped": True}

    asyncio.create_task(_run_cicd_fix({
        "platform": "github",
        "repo": (payload.get("repository") or {}).get("full_name", ""),
        "branch": run.get("head_branch", ""),
        "workflow": run.get("name", ""),
        "run_id": run.get("id"),
        "logs": f"Workflow {run.get('name')} failed on {run.get('head_branch')}",
        "job_name": run.get("name", ""),
        "failed_step": "workflow_run",
    }))
    return {"accepted": True}


@webhook_router.post("/azure/pipelines")
async def webhook_azure_pipelines(request: Request):
    try:
        payload = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON")

    resource = payload.get("resource") or payload
    result = (resource.get("result") or resource.get("status") or "").lower()
    if result not in ("failed", "failure"):
        return {"accepted": True, "skipped": True}

    repo = ""
    if isinstance(resource.get("repository"), dict):
        repo = str(resource.get("repository", {}).get("name") or "")
    definition = resource.get("definition") if isinstance(resource.get("definition"), dict) else {}
    asyncio.create_task(_run_cicd_fix({
        "platform": "azure",
        "repo": repo,
        "branch": resource.get("sourceBranch", ""),
        "workflow": definition.get("name", "pipeline"),
        "run_id": resource.get("id"),
        "logs": f"Azure pipeline failed: {resource.get('id')}",
        "job_name": "azure-pipelines",
        "failed_step": "pipeline",
    }))
    return {"accepted": True}


@webhook_router.post("/gitlab/pipeline")
async def webhook_gitlab_pipeline(request: Request):
    try:
        payload = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON")

    attrs = payload.get("object_attributes") or payload
    status = attrs.get("status", "")
    if status != "failed":
        return {"accepted": True, "skipped": True}

    asyncio.create_task(_run_cicd_fix({
        "platform": "gitlab",
        "repo": str((payload.get("project") or {}).get("path_with_namespace") or ""),
        "branch": attrs.get("ref", ""),
        "workflow": "gitlab-pipeline",
        "run_id": attrs.get("id"),
        "logs": f"GitLab pipeline {attrs.get('id')} failed",
        "job_name": "pipeline",
        "failed_step": "pipeline",
    }))
    return {"accepted": True}


async def _run_cicd_fix(meta: dict):
    try:
        from agents.cicd_agent.node import CICDAgent
        agent = CICDAgent()
        key = os.getenv("ANTHROPIC_API_KEY", "")
        info = await agent.classify_failure(
            logs=str(meta.get("logs") or "")[:10000],
            failed_step=str(meta.get("failed_step") or ""),
            job_name=str(meta.get("job_name") or ""),
            claude_api_key=key,
        )
        comment = agent.generate_pr_comment(info, None, bool(info.get("fixable_by_ai")))
        logger.info(
            "CICD webhook classified %s fixable=%s — %s",
            meta.get("platform"),
            info.get("fixable_by_ai"),
            info.get("summary"),
        )
        logger.info("PR comment draft: %s", comment[:200])
    except Exception:
        logger.exception("CICD webhook handler failed")
