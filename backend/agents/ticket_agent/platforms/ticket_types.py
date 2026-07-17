"""
Jessie v3 — shared ticket board types and client factory.
New module only; does not alter v1/v2 agents.
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any, Optional


@dataclass
class Ticket:
    id: str
    number: str
    title: str
    description: str
    acceptance_criteria: str = ""
    label: str = "task"  # bug|feature|refactor|task
    priority: str = "medium"  # critical|high|medium|low
    status: str = "todo"  # todo|in_progress|in_review|done
    assignee: str = ""
    reporter: str = ""
    comments: list[dict] = field(default_factory=list)
    linked_tickets: list[str] = field(default_factory=list)
    attachments: list[str] = field(default_factory=list)
    estimated_hours: float = 0.0
    sprint: str = ""
    tags: list[str] = field(default_factory=list)
    created_at: str = ""
    updated_at: str = ""
    url: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class SprintData:
    id: str
    name: str
    start_date: str = ""
    end_date: str = ""
    status: str = "active"  # active|closed|future
    tickets: list[Ticket] = field(default_factory=list)
    team_members: list[str] = field(default_factory=list)
    velocity: float = 0.0
    capacity: float = 0.0

    def to_dict(self) -> dict:
        d = asdict(self)
        d["tickets"] = [t.to_dict() if isinstance(t, Ticket) else t for t in self.tickets]
        return d


def parse_ticket_id(ticket_id: str) -> str:
    """Normalize ticket identifiers for platform lookups."""
    raw = (ticket_id or "").strip()
    if not raw:
        raise ValueError("ticket_id is required")
    if raw.upper().startswith("AB#"):
        return raw.split("#", 1)[-1].strip()
    if raw.startswith("#"):
        return raw[1:].strip()
    return raw


def classify_ticket_complexity(ticket: Ticket) -> int:
    """Heuristic 1–10 complexity (no LLM)."""
    score = 3
    desc = (ticket.description or "") + "\n" + (ticket.acceptance_criteria or "")
    if len(desc) > 800:
        score += 2
    elif len(desc) > 300:
        score += 1
    criteria_lines = [ln for ln in (ticket.acceptance_criteria or "").splitlines() if ln.strip()]
    score += min(3, len(criteria_lines) // 2)
    score += min(2, len(ticket.linked_tickets or []))
    label = (ticket.label or "task").lower()
    if label == "bug":
        score -= 1
    elif label == "feature":
        score += 2
    elif label == "refactor":
        score += 1
    if (ticket.priority or "").lower() == "critical":
        score += 1
    return max(1, min(10, score))


def get_ticket_client(platform: str, token: str, **kwargs: Any):
    """Factory for ticket board clients."""
    p = (platform or "").strip().lower()
    if p == "azure":
        from agents.ticket_agent.platforms.azure_ticket_client import AzureTicketClient
        return AzureTicketClient(
            token=token,
            organization=kwargs.get("azure_org") or kwargs.get("organization") or "",
            project=kwargs.get("azure_project") or kwargs.get("project") or "",
        )
    if p == "jira":
        from agents.ticket_agent.platforms.jira_ticket_client import JiraTicketClient
        return JiraTicketClient(
            token=token,
            jira_url=kwargs.get("jira_url") or "",
            project_key=kwargs.get("jira_project") or kwargs.get("project_key") or "",
            email=kwargs.get("jira_email") or kwargs.get("email") or "",
        )
    if p == "github":
        from agents.ticket_agent.platforms.github_issue_client import GitHubIssueClient
        return GitHubIssueClient(token=token, repo=kwargs.get("github_repo") or kwargs.get("repo") or "")
    if p == "linear":
        from agents.ticket_agent.platforms.linear_client import LinearClient
        return LinearClient(token=token, team_id=kwargs.get("linear_team_id") or kwargs.get("team_id") or "")
    raise ValueError(f"Unsupported ticket platform: {platform}")
