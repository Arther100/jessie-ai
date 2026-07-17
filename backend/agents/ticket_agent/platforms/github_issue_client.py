"""Jessie v3 — GitHub Issues client."""

from __future__ import annotations

import json
import logging
from typing import Any, Optional
from urllib import error, request

from agents.ticket_agent.platforms.ticket_types import SprintData, Ticket, classify_ticket_complexity

logger = logging.getLogger(__name__)


class GitHubIssueClient:
    def __init__(self, token: str, repo: str):
        self.token = token
        self.repo = (repo or "").strip()
        if "/" not in self.repo:
            raise ValueError("github_repo must be owner/name")
        self.base = f"https://api.github.com/repos/{self.repo}"

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.token}",
            "Accept": "application/vnd.github+json",
            "Content-Type": "application/json",
            "X-GitHub-Api-Version": "2022-11-28",
        }

    def _request(self, method: str, url: str, body: Any = None) -> Any:
        data = None if body is None else json.dumps(body).encode()
        req = request.Request(url, data=data, headers=self._headers(), method=method)
        try:
            with request.urlopen(req, timeout=45) as resp:
                raw = resp.read().decode()
                return json.loads(raw) if raw else {}
        except error.HTTPError as exc:
            detail = exc.read().decode(errors="replace")[:500]
            raise RuntimeError(f"GitHub API {exc.code}: {detail}") from exc

    def get_ticket(self, issue_number: str | int) -> Ticket:
        data = self._request("GET", f"{self.base}/issues/{issue_number}")
        comments = self._request("GET", f"{self.base}/issues/{issue_number}/comments")
        if not isinstance(comments, list):
            comments = []
        return self._map_issue(data, comments)

    def get_sprint_tickets(self, milestone: Optional[str] = None) -> SprintData:
        milestones = self._request("GET", f"{self.base}/milestones?state=open")
        if not isinstance(milestones, list):
            milestones = []
        current = None
        if milestone:
            for m in milestones:
                if str(m.get("title")) == milestone or str(m.get("number")) == str(milestone):
                    current = m
                    break
        if current is None and milestones:
            current = milestones[0]
        if current is None:
            issues = self._request("GET", f"{self.base}/issues?state=open&per_page=40")
            tickets = [self._map_issue(i, []) for i in (issues if isinstance(issues, list) else []) if "pull_request" not in i]
            return SprintData(id="", name="Open issues", status="active", tickets=tickets)
        mid = current.get("number")
        issues = self._request("GET", f"{self.base}/issues?milestone={mid}&state=all&per_page=50")
        tickets = [self._map_issue(i, []) for i in (issues if isinstance(issues, list) else []) if "pull_request" not in i]
        return SprintData(
            id=str(mid),
            name=current.get("title") or f"Milestone {mid}",
            end_date=str(current.get("due_on") or ""),
            status="active",
            tickets=tickets,
        )

    def update_ticket_status(self, issue_number: str | int, status: str) -> None:
        if status == "done":
            self._request("PATCH", f"{self.base}/issues/{issue_number}", {"state": "closed"})
            return
        if status == "in_review":
            data = self._request("GET", f"{self.base}/issues/{issue_number}")
            labels = [x.get("name") for x in (data.get("labels") or []) if isinstance(x, dict)]
            if "in-review" not in labels:
                labels.append("in-review")
            self._request("PATCH", f"{self.base}/issues/{issue_number}", {"labels": labels, "state": "open"})
            return
        self._request("PATCH", f"{self.base}/issues/{issue_number}", {"state": "open"})

    def add_ticket_comment(self, issue_number: str | int, comment: str) -> None:
        self._request("POST", f"{self.base}/issues/{issue_number}/comments", {"body": comment})

    def link_pr_to_ticket(self, issue_number: str | int, pr_number: str | int) -> None:
        self.add_ticket_comment(issue_number, f"Linked PR: #{pr_number}")

    def get_open_tickets(self, assignee: Optional[str] = None) -> list[Ticket]:
        url = f"{self.base}/issues?state=open&per_page=40"
        if assignee:
            url += f"&assignee={assignee}"
        issues = self._request("GET", url)
        return [self._map_issue(i, []) for i in (issues if isinstance(issues, list) else []) if "pull_request" not in i]

    def classify_ticket_complexity(self, ticket: Ticket) -> int:
        return classify_ticket_complexity(ticket)

    def create_pull_request(self, title: str, body: str, head: str, base: str = "main") -> dict:
        return self._request(
            "POST",
            f"{self.base}/pulls",
            {"title": title, "body": body, "head": head, "base": base},
        )

    def _map_issue(self, data: dict, comments: list | None = None) -> Ticket:
        number = str(data.get("number") or "")
        labels = [x.get("name") for x in (data.get("labels") or []) if isinstance(x, dict)]
        label = "bug" if any("bug" in (l or "").lower() for l in labels) else (
            "feature" if any(x in " ".join(labels).lower() for x in ("feature", "enhancement")) else "task"
        )
        status = "done" if data.get("state") == "closed" else (
            "in_review" if "in-review" in labels else "todo"
        )
        mapped_comments = []
        for c in comments or []:
            mapped_comments.append({
                "author": ((c.get("user") or {}).get("login") or ""),
                "body": c.get("body") or "",
                "date": c.get("created_at") or "",
            })
        milestone = data.get("milestone") or {}
        return Ticket(
            id=f"#{number}",
            number=number,
            title=data.get("title") or "",
            description=data.get("body") or "",
            label=label,
            priority="high" if "priority:high" in labels or "critical" in labels else "medium",
            status=status,
            assignee=((data.get("assignee") or {}).get("login") or ""),
            reporter=((data.get("user") or {}).get("login") or ""),
            comments=mapped_comments,
            sprint=milestone.get("title") or "",
            tags=labels,
            created_at=str(data.get("created_at") or ""),
            updated_at=str(data.get("updated_at") or ""),
            url=data.get("html_url") or "",
        )
