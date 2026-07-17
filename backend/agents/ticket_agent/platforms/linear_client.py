"""Jessie v3 — Linear GraphQL client (raw GraphQL; no linear-sdk required)."""

from __future__ import annotations

import json
import logging
from typing import Any, Optional
from urllib import error, request

from agents.ticket_agent.platforms.ticket_types import SprintData, Ticket, classify_ticket_complexity

logger = logging.getLogger(__name__)


class LinearClient:
    def __init__(self, token: str, team_id: str = ""):
        self.token = token
        self.team_id = team_id
        self.url = "https://api.linear.app/graphql"

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": self.token,
            "Content-Type": "application/json",
        }

    def _gql(self, query: str, variables: Optional[dict] = None) -> dict:
        body = {"query": query, "variables": variables or {}}
        req = request.Request(self.url, data=json.dumps(body).encode(), headers=self._headers(), method="POST")
        try:
            with request.urlopen(req, timeout=45) as resp:
                payload = json.loads(resp.read().decode())
        except error.HTTPError as exc:
            detail = exc.read().decode(errors="replace")[:500]
            raise RuntimeError(f"Linear API {exc.code}: {detail}") from exc
        if payload.get("errors"):
            raise RuntimeError(f"Linear GraphQL error: {payload['errors']}")
        return payload.get("data") or {}

    def get_ticket(self, issue_id: str) -> Ticket:
        # Support identifier like ENG-1047 or UUID
        query = """
        query($id: String!) {
          issue(id: $id) {
            id identifier title description priority
            state { name }
            assignee { name }
            creator { name }
            createdAt updatedAt url
            labels { nodes { name } }
            comments { nodes { body createdAt user { name } } }
          }
        }
        """
        data = self._gql(query, {"id": issue_id})
        issue = data.get("issue")
        if not issue:
            # try by identifier filter
            q2 = """
            query($filter: IssueFilter) {
              issues(filter: $filter, first: 1) {
                nodes {
                  id identifier title description priority
                  state { name }
                  assignee { name }
                  creator { name }
                  createdAt updatedAt url
                  labels { nodes { name } }
                  comments { nodes { body createdAt user { name } } }
                }
              }
            }
            """
            data = self._gql(q2, {"filter": {"identifier": {"eq": issue_id}}})
            nodes = ((data.get("issues") or {}).get("nodes") or [])
            issue = nodes[0] if nodes else None
        if not issue:
            raise RuntimeError(f"Linear issue not found: {issue_id}")
        return self._map_issue(issue)

    def get_sprint_tickets(self, cycle_id: Optional[str] = None) -> SprintData:
        if cycle_id:
            query = """
            query($id: String!) {
              cycle(id: $id) {
                id name startsAt endsAt
                issues { nodes {
                  id identifier title description priority
                  state { name } assignee { name } creator { name }
                  createdAt updatedAt url labels { nodes { name } }
                  comments { nodes { body createdAt user { name } } }
                }}
              }
            }
            """
            data = self._gql(query, {"id": cycle_id})
            cycle = data.get("cycle") or {}
        else:
            query = """
            query($teamId: String!) {
              team(id: $teamId) {
                activeCycle {
                  id name startsAt endsAt
                  issues { nodes {
                    id identifier title description priority
                    state { name } assignee { name } creator { name }
                    createdAt updatedAt url labels { nodes { name } }
                    comments { nodes { body createdAt user { name } } }
                  }}
                }
              }
            }
            """
            if not self.team_id:
                raise ValueError("linear_team_id required to fetch active cycle")
            data = self._gql(query, {"teamId": self.team_id})
            cycle = ((data.get("team") or {}).get("activeCycle") or {})
        tickets = [self._map_issue(n) for n in ((cycle.get("issues") or {}).get("nodes") or [])]
        return SprintData(
            id=str(cycle.get("id") or ""),
            name=cycle.get("name") or "Active cycle",
            start_date=str(cycle.get("startsAt") or ""),
            end_date=str(cycle.get("endsAt") or ""),
            status="active",
            tickets=tickets,
        )

    def update_ticket_status(self, issue_id: str, state_name: str) -> None:
        states_q = """
        query($teamId: String!) {
          team(id: $teamId) { states { nodes { id name } } }
        }
        """
        if not self.team_id:
            raise ValueError("linear_team_id required to update status")
        data = self._gql(states_q, {"teamId": self.team_id})
        nodes = ((data.get("team") or {}).get("states") or {}).get("nodes") or []
        wanted = (state_name or "").lower().replace("_", " ")
        mapping = {"in review": "in review", "done": "done", "todo": "todo", "in progress": "in progress"}
        wanted = mapping.get(wanted, wanted)
        state_id = None
        for s in nodes:
            if wanted in (s.get("name") or "").lower():
                state_id = s.get("id")
                break
        if not state_id:
            raise RuntimeError(f"Linear state not found: {state_name}")
        mut = """
        mutation($id: String!, $stateId: String!) {
          issueUpdate(id: $id, input: { stateId: $stateId }) { success }
        }
        """
        self._gql(mut, {"id": issue_id, "stateId": state_id})

    def add_ticket_comment(self, issue_id: str, comment: str) -> None:
        mut = """
        mutation($issueId: String!, $body: String!) {
          commentCreate(input: { issueId: $issueId, body: $body }) { success }
        }
        """
        self._gql(mut, {"issueId": issue_id, "body": comment})

    def link_pr_to_ticket(self, issue_id: str, pr_url: str) -> None:
        mut = """
        mutation($issueId: String!, $url: String!) {
          attachmentCreate(input: { issueId: $issueId, url: $url, title: "Jessie AI PR" }) { success }
        }
        """
        self._gql(mut, {"issueId": issue_id, "url": pr_url})

    def get_open_tickets(self, assignee: Optional[str] = None) -> list[Ticket]:
        query = """
        query($teamId: String!) {
          team(id: $teamId) {
            issues(filter: { state: { type: { nin: ["completed", "canceled"] } } }, first: 40) {
              nodes {
                id identifier title description priority
                state { name } assignee { name } creator { name }
                createdAt updatedAt url labels { nodes { name } }
                comments { nodes { body createdAt user { name } } }
              }
            }
          }
        }
        """
        if not self.team_id:
            raise ValueError("linear_team_id required")
        data = self._gql(query, {"teamId": self.team_id})
        nodes = ((data.get("team") or {}).get("issues") or {}).get("nodes") or []
        tickets = [self._map_issue(n) for n in nodes]
        if assignee:
            tickets = [t for t in tickets if assignee.lower() in (t.assignee or "").lower()]
        return tickets

    def classify_ticket_complexity(self, ticket: Ticket) -> int:
        return classify_ticket_complexity(ticket)

    def _map_issue(self, data: dict) -> Ticket:
        ident = data.get("identifier") or data.get("id") or ""
        state = ((data.get("state") or {}).get("name") or "").lower()
        status = "done" if state in ("done", "completed", "canceled") else (
            "in_review" if "review" in state else (
                "in_progress" if "progress" in state or "started" in state else "todo"
            )
        )
        labels = [n.get("name") for n in ((data.get("labels") or {}).get("nodes") or [])]
        comments = []
        for c in ((data.get("comments") or {}).get("nodes") or []):
            comments.append({
                "author": ((c.get("user") or {}).get("name") or ""),
                "body": c.get("body") or "",
                "date": c.get("createdAt") or "",
            })
        pri = data.get("priority")
        priority = {1: "critical", 2: "high", 3: "medium", 4: "low"}.get(pri, "medium") if isinstance(pri, int) else "medium"
        return Ticket(
            id=ident,
            number=ident,
            title=data.get("title") or "",
            description=data.get("description") or "",
            label="bug" if any("bug" in (l or "").lower() for l in labels) else "task",
            priority=priority,
            status=status,
            assignee=((data.get("assignee") or {}).get("name") or ""),
            reporter=((data.get("creator") or {}).get("name") or ""),
            comments=comments,
            tags=labels,
            created_at=str(data.get("createdAt") or ""),
            updated_at=str(data.get("updatedAt") or ""),
            url=data.get("url") or "",
        )
