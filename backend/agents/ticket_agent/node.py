"""
Jessie v3 — Ticket Agent.
Reads tickets, generates fixes via ModelRouter + quality gate, opens PRs.
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any, Callable, Optional

from agents.quality_analyser.node import quality_analyser_node
from agents.ticket_agent.platforms.ticket_types import (
    Ticket,
    classify_ticket_complexity,
    get_ticket_client,
    parse_ticket_id,
)
from core.state import AgentState
from gateway.model_router import ModelRouter

logger = logging.getLogger(__name__)

FIX_SYSTEM = """You are a senior software engineer. Fix the ticket completely.
Return ONLY valid JSON (no markdown fences):
{
  "fix": "production-ready code for the primary change",
  "test": "unit test code",
  "files_changed": ["relative/path.py"],
  "explanation": "what changed and why"
}
Rules: fix ONLY what the ticket describes; match existing style; no placeholders."""


class TicketAgent:
    async def read_ticket(self, ticket_id: str, platform: str, token: str, **kwargs) -> Ticket:
        number = parse_ticket_id(ticket_id)
        client = get_ticket_client(platform, token, **kwargs)
        return client.get_ticket(number)

    async def generate_fix(
        self,
        ticket: Ticket,
        *,
        claude_api_key: str,
        workspace_id: str = "",
        language: str = "python",
        context_chunks: Optional[list[str]] = None,
        on_progress: Optional[Callable[[dict], None]] = None,
        provider: str = "anthropic",
    ) -> dict:
        complexity = classify_ticket_complexity(ticket)
        if not (claude_api_key or "").strip():
            raise ValueError("API key is required to generate a ticket fix.")
        comments = "\n".join(
            f"- {c.get('author', '')}: {c.get('body', '')[:400]}" for c in (ticket.comments or [])[:8]
        )
        prompt = (
            f"Ticket: {ticket.id} — {ticket.title}\n"
            f"Label: {ticket.label} | Priority: {ticket.priority}\n"
            f"Description:\n{ticket.description}\n\n"
            f"Acceptance criteria:\n{ticket.acceptance_criteria or '(none)'}\n\n"
            f"Team comments:\n{comments or '(none)'}\n\n"
            f"Language context: {language}\n"
            "Return JSON with fix, test, files_changed, explanation."
        )

        def emit(msg: str, pct: int):
            if on_progress:
                on_progress({"type": "progress", "message": msg, "pct": pct})

        emit(f"Generating fix (complexity {complexity}/10)...", 45)
        router = ModelRouter(api_key=claude_api_key, provider=provider or "anthropic")
        best: dict[str, Any] = {}
        best_score = 0
        tokens = 0
        cost = 0.0

        for attempt in range(3):
            result = await router.call_claude(
                prompt=prompt if attempt == 0 else (
                    prompt + f"\n\nPrevious attempt scored {best_score}/100. "
                    f"Feedback: improve concreteness and error handling.\n"
                    f"Previous JSON:\n{json.dumps(best)[:2000]}"
                ),
                complexity_score=complexity,
                system_prompt=FIX_SYSTEM,
                context_chunks=context_chunks or [],
            )
            tokens += int(result.get("tokens_in", 0) + result.get("tokens_out", 0))
            cost += float(result.get("cost_estimate", 0) or 0)
            parsed = self._extract_json(result.get("response", ""))
            if not parsed:
                continue
            # Reuse quality analyser on generated fix code
            qa_state: AgentState = {
                "original_prompt": ticket.title,
                "user_id": "ticket_agent",
                "workspace_id": workspace_id,
                "language": language,
                "open_file_content": "",
                "selected_code": "",
                "error_message": "",
                "complexity_score": complexity,
                "improved_prompt": "",
                "prompt_diff": "",
                "prompt_approved": True,
                "context_chunks": context_chunks or [],
                "component_exists": False,
                "component_path": "",
                "component_usage": "",
                "generated_code": str(parsed.get("fix") or ""),
                "model_used": result.get("model", ""),
                "quality_score": 0,
                "quality_feedback": "",
                "retry_count": attempt,
                "memory_saved": False,
                "memory_note": "",
                "review_triggered": False,
                "review_target_path": "",
                "review_results": {},
                "review_report_path": "",
                "final_response": "",
                "status_updates": [],
                "request_count": 0,
            }
            scored = quality_analyser_node(qa_state)
            score = int(scored.get("quality_score") or 0)
            emit(f"Quality check: {score}/100 (attempt {attempt + 1})...", 55 + attempt * 5)
            if score >= best_score:
                best_score = score
                best = {
                    **parsed,
                    "quality_score": score,
                    "quality_feedback": scored.get("quality_feedback", ""),
                    "complexity": complexity,
                    "tokens_used": tokens,
                    "cost_estimate": round(cost, 5),
                    "model": result.get("model", ""),
                }
            if score >= 70:
                break

        if not best:
            raise RuntimeError("Claude did not return a parseable fix JSON")
        if best_score < 50:
            best["rejected"] = True
            best["reject_reason"] = (
                f"Jessie couldn't generate a confident fix (score {best_score}/100 after retries)."
            )
        return best

    async def create_branch_and_pr(
        self,
        ticket: Ticket,
        fix_result: dict,
        workspace_path: str,
        *,
        platform: str,
        token: str,
        github_repo: str = "",
        base_branch: str = "",
        on_progress: Optional[Callable[[dict], None]] = None,
    ) -> dict:
        if fix_result.get("rejected"):
            raise RuntimeError(fix_result.get("reject_reason") or "Fix rejected by quality gate")

        def emit(msg: str, pct: int):
            if on_progress:
                on_progress({"type": "progress", "message": msg, "pct": pct})

        try:
            import git  # GitPython
        except ImportError as exc:
            raise RuntimeError("GitPython is required for PR creation. pip install GitPython") from exc

        root = Path(workspace_path).resolve()
        if not (root / ".git").exists():
            raise RuntimeError(f"Not a git repository: {root}")

        repo = git.Repo(str(root))
        if repo.is_dirty(untracked_files=True):
            raise RuntimeError(
                "You have uncommitted changes. Stash or commit them before Jessie creates a branch."
            )

        slug = re.sub(r"[^a-z0-9]+", "", ticket.id.lower().replace("#", ""))
        branch = f"jessie/fix-{slug or 'ticket'}"
        existing = {h.name for h in repo.heads}
        if branch in existing:
            n = 2
            while f"{branch}-{n}" in existing:
                n += 1
            branch = f"{branch}-{n}"

        emit(f"Creating branch {branch}...", 75)
        # Never checkout main/master for commits — create new branch from current HEAD
        current = repo.active_branch.name if not repo.head.is_detached else "HEAD"
        if current in ("main", "master"):
            repo.git.checkout("-b", branch)
        else:
            repo.git.checkout("-b", branch)

        written = []
        for rel in fix_result.get("files_changed") or []:
            path = root / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            # If file missing, write fix as new; if exists, append a Jessie fix block for safety
            if path.exists():
                # Prefer writing generated snippet into a sibling .jessie_fix file when we cannot safely patch
                patch_path = path.with_suffix(path.suffix + ".jessie_fix")
                patch_path.write_text(str(fix_result.get("fix") or ""), encoding="utf-8")
                repo.index.add([str(patch_path.relative_to(root))])
                written.append(str(patch_path.relative_to(root)))
            else:
                path.write_text(str(fix_result.get("fix") or ""), encoding="utf-8")
                repo.index.add([rel])
                written.append(rel)

        test_code = fix_result.get("test") or ""
        if test_code:
            test_rel = f"tests/jessie_fix_{slug or 'ticket'}.py"
            test_path = root / test_rel
            test_path.parent.mkdir(parents=True, exist_ok=True)
            test_path.write_text(str(test_code), encoding="utf-8")
            repo.index.add([test_rel])
            written.append(test_rel)

        if not written:
            raise RuntimeError("No files to commit from fix result")

        msg = (
            f"fix({ticket.id}): {ticket.title}\n\n"
            f"Fixes {ticket.id}\n"
            f"Generated by Jessie AI\n\n"
            f"{fix_result.get('explanation') or ''}"
        )
        repo.index.commit(msg)
        try:
            repo.remotes.origin.push(branch)
        except Exception as exc:
            logger.warning("Push failed: %s", exc)
            return {
                "branch_name": branch,
                "pr_number": 0,
                "pr_url": "",
                "files_changed": written,
                "push_error": str(exc),
                "manual_hint": f"Push manually: git push -u origin {branch}",
            }

        emit("Opening pull request...", 88)
        base = base_branch or self._detect_base(repo)
        pr_title = f"fix({ticket.id}): {ticket.title}"
        pr_body = self._pr_body(ticket, fix_result, written)
        pr_number = 0
        pr_url = ""
        if (platform or "").lower() == "github" and github_repo and token:
            from agents.ticket_agent.platforms.github_issue_client import GitHubIssueClient
            gh = GitHubIssueClient(token=token, repo=github_repo)
            pr = gh.create_pull_request(title=pr_title, body=pr_body, head=branch, base=base)
            pr_number = int(pr.get("number") or 0)
            pr_url = pr.get("html_url") or ""
        else:
            pr_url = ""
            return {
                "branch_name": branch,
                "pr_number": 0,
                "pr_url": "",
                "files_changed": written,
                "pr_title": pr_title,
                "pr_body": pr_body,
                "manual_hint": "Create PR manually from the pushed branch (non-GitHub platform or missing repo).",
            }

        return {
            "branch_name": branch,
            "pr_number": pr_number,
            "pr_url": pr_url,
            "files_changed": written,
            "base_branch": base,
        }

    async def update_ticket_board(
        self,
        ticket: Ticket,
        *,
        platform: str,
        token: str,
        pr_url: str,
        branch_name: str,
        quality_score: int,
        files_changed: list[str],
        **kwargs,
    ) -> None:
        client = get_ticket_client(platform, token, **kwargs)
        try:
            client.update_ticket_status(ticket.number, "in_review")
        except Exception as exc:
            logger.warning("Status update failed: %s", exc)
        comment = (
            f"⚡ Jessie AI generated a fix for this ticket.\n\n"
            f"PR opened: {pr_url or '(pending)'}\n"
            f"Branch: {branch_name}\n"
            f"Quality score: {quality_score}/100\n\n"
            f"Files changed:\n" + "\n".join(f"- {f}" for f in files_changed) + "\n\n"
            "Please review and merge to close this ticket."
        )
        try:
            client.add_ticket_comment(ticket.number, comment)
        except Exception as exc:
            logger.warning("Comment failed: %s", exc)
        try:
            if hasattr(client, "link_pr_to_ticket"):
                if (platform or "").lower() == "github":
                    # GitHub helper expects pr number — extract if present
                    m = re.search(r"/pull/(\d+)", pr_url or "")
                    if m:
                        client.link_pr_to_ticket(ticket.number, m.group(1))
                else:
                    client.link_pr_to_ticket(ticket.number, pr_url, f"Jessie PR for {ticket.id}")
        except TypeError:
            try:
                client.link_pr_to_ticket(ticket.number, pr_url)
            except Exception as exc:
                logger.warning("PR link failed: %s", exc)
        except Exception as exc:
            logger.warning("PR link failed: %s", exc)

    def _detect_base(self, repo) -> str:
        names = {h.name for h in repo.heads}
        if "main" in names:
            return "main"
        if "develop" in names:
            return "develop"
        if "master" in names:
            return "master"
        return repo.active_branch.name

    def _pr_body(self, ticket: Ticket, fix_result: dict, files: list[str]) -> str:
        return (
            f"## {ticket.id} — {ticket.title}\n\n"
            f"### What was changed\n{fix_result.get('explanation') or ''}\n\n"
            f"### Files modified\n" + "\n".join(f"- `{f}`" for f in files) + "\n\n"
            f"### Tests added\n```\n{(fix_result.get('test') or '')[:2000]}\n```\n\n"
            f"### Acceptance criteria\n{ticket.acceptance_criteria or '(none)'}\n\n"
            f"### Quality score\n{fix_result.get('quality_score', 0)}/100 — reviewed by Jessie AI\n\n"
            f"Closes {ticket.id}\n"
        )

    def _extract_json(self, text: str) -> Optional[dict]:
        if not text:
            return None
        raw = text.strip()
        if raw.startswith("```"):
            raw = re.sub(r"^```(?:json)?\s*", "", raw)
            raw = re.sub(r"\s*```$", "", raw)
        try:
            return json.loads(raw)
        except Exception:
            m = re.search(r"\{[\s\S]*\}", raw)
            if not m:
                return None
            try:
                return json.loads(m.group(0))
            except Exception:
                return None


async def ticket_agent_node(state: AgentState) -> AgentState:
    """LangGraph-compatible node — runs only when ticket_mode is set by /tickets APIs."""
    if not state.get("ticket_mode"):
        return state
    agent = TicketAgent()
    status = list(state.get("status_updates") or [])
    status.append("🎫 Ticket Agent — starting…")
    ticket_data = state.get("ticket_data") or {}
    ticket = Ticket(**{k: ticket_data.get(k, getattr(Ticket, k, "") if False else ticket_data.get(k)) for k in Ticket.__dataclass_fields__}) if ticket_data.get("id") else None
    # Prefer reconstructing safely
    if ticket_data.get("id"):
        ticket = Ticket(
            id=ticket_data.get("id", ""),
            number=ticket_data.get("number", ""),
            title=ticket_data.get("title", ""),
            description=ticket_data.get("description", ""),
            acceptance_criteria=ticket_data.get("acceptance_criteria", ""),
            label=ticket_data.get("label", "task"),
            priority=ticket_data.get("priority", "medium"),
            status=ticket_data.get("status", "todo"),
            assignee=ticket_data.get("assignee", ""),
            reporter=ticket_data.get("reporter", ""),
            comments=ticket_data.get("comments") or [],
            linked_tickets=ticket_data.get("linked_tickets") or [],
            attachments=ticket_data.get("attachments") or [],
            estimated_hours=float(ticket_data.get("estimated_hours") or 0),
            sprint=ticket_data.get("sprint", ""),
            tags=ticket_data.get("tags") or [],
            created_at=ticket_data.get("created_at", ""),
            updated_at=ticket_data.get("updated_at", ""),
            url=ticket_data.get("url", ""),
        )
    else:
        return {**state, "status_updates": status + ["Ticket Agent skipped — no ticket_data"]}

    key = state.get("claude_api_key") or ""
    fix = await agent.generate_fix(
        ticket,
        claude_api_key=key,
        workspace_id=state.get("workspace_id") or "",
        language=state.get("language") or "python",
        context_chunks=list(state.get("context_chunks") or []),
    )
    status.append(f"Fix quality {fix.get('quality_score', 0)}/100")
    return {
        **state,
        "fix_code": str(fix.get("fix") or ""),
        "fix_test": str(fix.get("test") or ""),
        "ticket_complexity": int(fix.get("complexity") or 0),
        "quality_score": int(fix.get("quality_score") or 0),
        "generated_code": str(fix.get("fix") or ""),
        "status_updates": status,
        "ticket_data": {**ticket.to_dict(), "fix_result": fix},
    }
