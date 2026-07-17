"""Jessie v3 smoke tests — mock tickets, no live platforms required."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from agents.ticket_agent.platforms.ticket_types import Ticket, classify_ticket_complexity
from agents.sprint_scanner.node import SprintScanner
from agents.ticket_agent.node import TicketAgent


def _mock_ticket(**overrides) -> Ticket:
    base = dict(
        id="TEST#001",
        number="001",
        title="Fix login returning 500 error",
        description=(
            "When user submits login form with valid credentials, API returns 500. "
            "Error in console: KeyError 'email'"
        ),
        acceptance_criteria="Login works with valid credentials. Returns 200 with JWT token.",
        label="bug",
        priority="high",
        status="todo",
        comments=[{"author": "qa", "body": "Repro on staging", "date": "2026-07-01"}],
    )
    base.update(overrides)
    return Ticket(**base)


def test_complexity_heuristic():
    t = _mock_ticket()
    score = classify_ticket_complexity(t)
    assert 1 <= score <= 10


@pytest.mark.asyncio
async def test_sprint_scanner_classifies_five_mocks():
    scanner = SprintScanner()
    tickets = [
        _mock_ticket(id="T1", title="Fix KeyError email", label="bug"),
        _mock_ticket(id="T2", title="Add dark mode toggle", label="feature", description="x" * 700),
        _mock_ticket(id="T3", title="Add unit test for auth", label="task", description="missing unit test for login"),
        _mock_ticket(id="T4", title="Rotate production secrets", label="task", description="security infra deploy"),
        _mock_ticket(id="T5", title="Typo in README", label="task", description="fix typo in docs"),
    ]
    results = []
    for t in tickets:
        results.append(await scanner.classify_ticket(t, claude_api_key=""))
    assert len(results) == 5
    assert all("category" in r and "confidence" in r for r in results)
    cats = {r["category"] for r in results}
    assert cats & {"auto_fix", "ai_assist", "human_only"}


@pytest.mark.asyncio
async def test_generate_fix_requires_key_or_fails_cleanly():
    agent = TicketAgent()
    t = _mock_ticket()
    with pytest.raises(Exception):
        await agent.generate_fix(t, claude_api_key="")
