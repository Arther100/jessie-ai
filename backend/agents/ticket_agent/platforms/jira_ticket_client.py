"""Jessie v3 — Jira REST API client."""

from __future__ import annotations

import base64
import json
import logging
from typing import Any, Optional
from urllib import error, request

from agents.ticket_agent.platforms.ticket_types import SprintData, Ticket, classify_ticket_complexity

logger = logging.getLogger(__name__)


class JiraTicketClient:
    def __init__(self, token: str, jira_url: str, project_key: str, email: str = ""):
        self.token = token
        self.jira_url = (jira_url or "").rstrip("/")
        self.project_key = project_key
        self.email = email
        if not self.jira_url or not self.project_key:
            raise ValueError("jira_url and jira_project are required")
        self.base = f"{self.jira_url}/rest/api/3"

    def _headers(self) -> dict[str, str]:
        if self.email:
            auth = base64.b64encode(f"{self.email}:{self.token}".encode()).decode()
            return {"Authorization": f"Basic {auth}", "Content-Type": "application/json", "Accept": "application/json"}
        return {"Authorization": f"Bearer {self.token}", "Content-Type": "application/json", "Accept": "application/json"}

    def _request(self, method: str, url: str, body: Any = None) -> Any:
        data = None if body is None else json.dumps(body).encode()
        req = request.Request(url, data=data, headers=self._headers(), method=method)
        try:
            with request.urlopen(req, timeout=45) as resp:
                raw = resp.read().decode()
                return json.loads(raw) if raw else {}
        except error.HTTPError as exc:
            detail = exc.read().decode(errors="replace")[:500]
            raise RuntimeError(f"Jira API {exc.code}: {detail}") from exc

    def get_ticket(self, issue_key: str) -> Ticket:
        data = self._request("GET", f"{self.base}/issue/{issue_key}?expand=changelog,comments")
        return self._map_issue(data)

    def get_sprint_tickets(self, sprint_id: Optional[str] = None) -> SprintData:
        jql = f'project = "{self.project_key}" AND sprint in openSprints() ORDER BY updated DESC'
        if sprint_id:
            jql = f'project = "{self.project_key}" AND sprint = {sprint_id} ORDER BY updated DESC'
        data = self._request("POST", f"{self.base}/search", {"jql": jql, "maxResults": 50})
        tickets = [self._map_issue(i) for i in (data.get("issues") or [])]
        return SprintData(
            id=str(sprint_id or "active"),
            name=f"Sprint {sprint_id}" if sprint_id else "Active Sprint",
            status="active",
            tickets=tickets,
        )

    def update_ticket_status(self, issue_key: str, transition_name: str) -> None:
        transitions = self._request("GET", f"{self.base}/issue/{issue_key}/transitions").get("transitions") or []
        target = None
        wanted = (transition_name or "").lower().replace("_", " ")
        mapping = {"in review": "in review", "done": "done", "todo": "to do", "in progress": "in progress"}
        wanted = mapping.get(wanted, wanted)
        for t in transitions:
            if wanted in (t.get("name") or "").lower():
                target = t
                break
        if not target and transitions:
            target = transitions[0]
        if not target:
            raise RuntimeError(f"No transitions available for {issue_key}")
        self._request("POST", f"{self.base}/issue/{issue_key}/transitions", {"transition": {"id": target["id"]}})

    def add_ticket_comment(self, issue_key: str, comment: str) -> None:
        body = {
            "body": {
                "type": "doc",
                "version": 1,
                "content": [{"type": "paragraph", "content": [{"type": "text", "text": comment}]}],
            }
        }
        self._request("POST", f"{self.base}/issue/{issue_key}/comment", body)

    def link_pr_to_ticket(self, issue_key: str, pr_url: str) -> None:
        self._request(
            "POST",
            f"{self.base}/issue/{issue_key}/remotelink",
            {"object": {"url": pr_url, "title": "Jessie AI Pull Request"}},
        )

    def get_open_tickets(self, assignee: Optional[str] = None) -> list[Ticket]:
        jql = f'project = "{self.project_key}" AND statusCategory != Done'
        if assignee:
            jql += " AND assignee = currentUser()" if assignee in ("@me", "currentUser") else f' AND assignee = "{assignee}"'
        jql += " ORDER BY updated DESC"
        data = self._request("POST", f"{self.base}/search", {"jql": jql, "maxResults": 40})
        return [self._map_issue(i) for i in (data.get("issues") or [])]

    def classify_ticket_complexity(self, ticket: Ticket) -> int:
        return classify_ticket_complexity(ticket)

    def _map_issue(self, data: dict) -> Ticket:
        fields = data.get("fields") or {}
        key = data.get("key") or ""
        labels = fields.get("labels") or []
        issuetype = ((fields.get("issuetype") or {}).get("name") or "task").lower()
        label = "bug" if "bug" in issuetype else "feature" if "story" in issuetype else "task"
        status_name = ((fields.get("status") or {}).get("name") or "").lower()
        status = "done" if status_name in ("done", "closed") else (
            "in_review" if "review" in status_name else (
                "in_progress" if "progress" in status_name else "todo"
            )
        )
        comments = []
        for c in ((fields.get("comment") or {}).get("comments") or []):
            comments.append({
                "author": ((c.get("author") or {}).get("displayName") or ""),
                "body": c.get("body") if isinstance(c.get("body"), str) else json.dumps(c.get("body")),
                "date": c.get("created") or "",
            })
        return Ticket(
            id=key,
            number=key,
            title=fields.get("summary") or "",
            description=str(fields.get("description") or ""),
            acceptance_criteria=str(fields.get("customfield_10000") or ""),
            label=label,
            priority=((fields.get("priority") or {}).get("name") or "medium").lower(),
            status=status,
            assignee=((fields.get("assignee") or {}).get("displayName") or ""),
            reporter=((fields.get("reporter") or {}).get("displayName") or ""),
            comments=comments,
            tags=list(labels),
            created_at=str(fields.get("created") or ""),
            updated_at=str(fields.get("updated") or ""),
            url=f"{self.jira_url}/browse/{key}",
        )
