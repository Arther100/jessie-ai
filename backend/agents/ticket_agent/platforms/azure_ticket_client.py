"""Jessie v3 — Azure DevOps Work Items client."""

from __future__ import annotations

import base64
import json
import logging
from typing import Any, Optional
from urllib import error, parse, request

from agents.ticket_agent.platforms.ticket_types import (
    SprintData,
    Ticket,
    classify_ticket_complexity,
)

logger = logging.getLogger(__name__)

_STATUS_TO_AZURE = {
    "todo": "To Do",
    "in_progress": "Active",
    "in_review": "In Review",
    "done": "Closed",
}


class AzureTicketClient:
    def __init__(self, token: str, organization: str, project: str):
        self.token = token
        self.organization = organization.strip()
        self.project = project.strip()
        if not self.organization or not self.project:
            raise ValueError("azure_org and azure_project are required")
        self.base = f"https://dev.azure.com/{parse.quote(self.organization)}/{parse.quote(self.project)}"

    def _headers(self) -> dict[str, str]:
        auth = base64.b64encode((":" + self.token).encode()).decode()
        return {
            "Authorization": f"Basic {auth}",
            "Content-Type": "application/json",
            "Accept": "application/json",
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
            raise RuntimeError(f"Azure DevOps API {exc.code}: {detail}") from exc

    def get_ticket(self, work_item_id: str | int) -> Ticket:
        url = f"{self.base}/_apis/wit/workitems/{work_item_id}?$expand=all&api-version=7.1"
        data = self._request("GET", url)
        return self._map_work_item(data)

    def get_sprint_tickets(self, sprint_name: Optional[str] = None) -> SprintData:
        iter_url = f"{self.base}/_apis/work/teamsettings/iterations?api-version=7.1&$timeframe=current"
        iterations = self._request("GET", iter_url).get("value") or []
        current = None
        if sprint_name:
            for it in iterations:
                if (it.get("name") or "").lower() == sprint_name.lower():
                    current = it
                    break
        if current is None and iterations:
            current = iterations[0]
        if current is None:
            return SprintData(id="", name=sprint_name or "No sprint", tickets=[])

        path = current.get("path") or current.get("name")
        wiql = {
            "query": (
                "SELECT [System.Id] FROM WorkItems "
                f"WHERE [System.IterationPath] UNDER '{path}' "
                "ORDER BY [System.ChangedDate] DESC"
            )
        }
        wiql_url = f"{self.base}/_apis/wit/wiql?api-version=7.1"
        result = self._request("POST", wiql_url, wiql)
        ids = [str(x.get("id")) for x in (result.get("workItems") or []) if x.get("id")]
        tickets = []
        for wid in ids[:50]:
            try:
                tickets.append(self.get_ticket(wid))
            except Exception as exc:
                logger.warning("Failed to load work item %s: %s", wid, exc)
        attrs = current.get("attributes") or {}
        return SprintData(
            id=str(current.get("id") or current.get("name") or ""),
            name=current.get("name") or "Sprint",
            start_date=str(attrs.get("startDate") or ""),
            end_date=str(attrs.get("finishDate") or ""),
            status="active",
            tickets=tickets,
        )

    def update_ticket_status(self, ticket_id: str, new_status: str) -> None:
        azure_state = _STATUS_TO_AZURE.get(new_status, new_status)
        url = f"{self.base}/_apis/wit/workitems/{ticket_id}?api-version=7.1"
        body = [{"op": "add", "path": "/fields/System.State", "value": azure_state}]
        headers = self._headers()
        headers["Content-Type"] = "application/json-patch+json"
        data = json.dumps(body).encode()
        req = request.Request(url, data=data, headers=headers, method="PATCH")
        with request.urlopen(req, timeout=45) as resp:
            resp.read()

    def add_ticket_comment(self, ticket_id: str, comment: str) -> None:
        url = f"{self.base}/_apis/wit/workitems/{ticket_id}/comments?api-version=7.1-preview.3"
        self._request("POST", url, {"text": comment})

    def link_pr_to_ticket(self, ticket_id: str, pr_url: str, pr_title: str = "") -> None:
        url = f"{self.base}/_apis/wit/workitems/{ticket_id}?api-version=7.1"
        body = [{
            "op": "add",
            "path": "/relations/-",
            "value": {
                "rel": "Hyperlink",
                "url": pr_url,
                "attributes": {"comment": pr_title or "Jessie AI PR"},
            },
        }]
        headers = self._headers()
        headers["Content-Type"] = "application/json-patch+json"
        data = json.dumps(body).encode()
        req = request.Request(url, data=data, headers=headers, method="PATCH")
        with request.urlopen(req, timeout=45) as resp:
            resp.read()

    def get_open_tickets(self, assignee: Optional[str] = None) -> list[Ticket]:
        clause = "[System.State] <> 'Closed' AND [System.State] <> 'Done'"
        if assignee:
            clause += f" AND [System.AssignedTo] = '{assignee}'"
        wiql = {"query": f"SELECT [System.Id] FROM WorkItems WHERE {clause} ORDER BY [System.ChangedDate] DESC"}
        result = self._request("POST", f"{self.base}/_apis/wit/wiql?api-version=7.1", wiql)
        ids = [str(x.get("id")) for x in (result.get("workItems") or [])[:40]]
        out = []
        for wid in ids:
            try:
                out.append(self.get_ticket(wid))
            except Exception:
                continue
        return out

    def classify_ticket_complexity(self, ticket: Ticket) -> int:
        return classify_ticket_complexity(ticket)

    def _map_work_item(self, data: dict) -> Ticket:
        fields = data.get("fields") or {}
        wid = str(data.get("id") or "")
        wtype = (fields.get("System.WorkItemType") or "Task").lower()
        label = "bug" if "bug" in wtype else "feature" if "story" in wtype or "feature" in wtype else "task"
        state = (fields.get("System.State") or "").lower()
        status = "done" if state in ("closed", "done", "resolved") else (
            "in_review" if "review" in state else (
                "in_progress" if state in ("active", "doing", "committed") else "todo"
            )
        )
        assignee = ""
        assigned = fields.get("System.AssignedTo")
        if isinstance(assigned, dict):
            assignee = assigned.get("displayName") or assigned.get("uniqueName") or ""
        elif isinstance(assigned, str):
            assignee = assigned
        comments = []
        for rel in data.get("relations") or []:
            if "Comment" in (rel.get("rel") or ""):
                comments.append({"author": "", "body": rel.get("url", ""), "date": ""})
        return Ticket(
            id=f"AB#{wid}",
            number=wid,
            title=fields.get("System.Title") or "",
            description=fields.get("System.Description") or fields.get("Microsoft.VSTS.TCM.ReproSteps") or "",
            acceptance_criteria=fields.get("Microsoft.VSTS.Common.AcceptanceCriteria") or "",
            label=label,
            priority=(fields.get("Microsoft.VSTS.Common.Priority") and str(fields.get("Microsoft.VSTS.Common.Priority"))) or "medium",
            status=status,
            assignee=assignee,
            reporter=(fields.get("System.CreatedBy") or {}).get("displayName", "") if isinstance(fields.get("System.CreatedBy"), dict) else "",
            comments=comments,
            sprint=fields.get("System.IterationPath") or "",
            tags=list(fields.get("System.Tags", "").split("; ")) if fields.get("System.Tags") else [],
            created_at=str(fields.get("System.CreatedDate") or ""),
            updated_at=str(fields.get("System.ChangedDate") or ""),
            url=f"{self.base}/_workitems/edit/{wid}",
        )
