"""Jessie v3 — Sprint Scanner agent (classify tickets for AI fixability)."""

from __future__ import annotations

import json
import logging
import re
from datetime import date, datetime
from typing import Any, Callable, Optional

from agents.ticket_agent.platforms.ticket_types import SprintData, Ticket, get_ticket_client
from gateway.model_router import ModelRouter

logger = logging.getLogger(__name__)

CLASSIFY_SYSTEM = """Classify this ticket for AI fixability. Return ONLY JSON:
{
  "can_fix": true,
  "confidence": 0,
  "reason": "",
  "complexity": 1,
  "estimated_minutes": 30,
  "risks": [],
  "category": "auto_fix"
}
category must be one of: auto_fix | ai_assist | human_only
Rules:
auto_fix (confidence > 80): clear bugs, small refactors, missing tests, typos, small well-defined features
ai_assist (50-80): needs investigation, many files, unclear requirements, external deps
human_only (<50): UX/design, business ambiguity, security-critical, infra/DevOps, needs PM
"""


class SprintScanner:
    async def scan_sprint(
        self,
        platform: str,
        token: str,
        workspace_id: str = "",
        claude_api_key: str = "",
        sprint_name: Optional[str] = None,
        on_progress: Optional[Callable[[dict], None]] = None,
        **kwargs,
    ) -> dict:
        def emit(msg: str, pct: int):
            if on_progress:
                on_progress({"type": "progress", "message": msg, "pct": pct})

        emit("Fetching sprint tickets...", 20)
        client = get_ticket_client(platform, token, **kwargs)
        sprint: SprintData = client.get_sprint_tickets(sprint_name)
        classified = []
        total = max(1, len(sprint.tickets))
        emit(f"Classifying {len(sprint.tickets)} tickets...", 40)
        for i, t in enumerate(sprint.tickets):
            item = await self.classify_ticket(t, claude_api_key=claude_api_key)
            classified.append({**t.to_dict(), **item})
            emit(f"Classified {i + 1}/{len(sprint.tickets)}…", 40 + int(40 * (i + 1) / total))
        report = self.generate_sprint_report(classified, sprint)
        report["workspace_id"] = workspace_id
        return report

    async def classify_ticket(self, ticket: Ticket, claude_api_key: str = "") -> dict:
        # Heuristic fallback when no key (tests / offline)
        if not (claude_api_key or "").strip():
            return self._heuristic(ticket)
        try:
            router = ModelRouter(api_key=claude_api_key)
            prompt = (
                f"Ticket: {ticket.title}\nDescription: {ticket.description[:2000]}\n"
                f"Label: {ticket.label}\nPriority: {ticket.priority}\n"
                f"Acceptance: {ticket.acceptance_criteria[:1000]}"
            )
            result = await router.call_claude(prompt=prompt, complexity_score=2, system_prompt=CLASSIFY_SYSTEM)
            parsed = self._extract_json(result.get("response", ""))
            if parsed:
                cat = parsed.get("category") or "ai_assist"
                conf = int(parsed.get("confidence") or 0)
                if cat not in ("auto_fix", "ai_assist", "human_only"):
                    cat = "auto_fix" if conf > 80 else "ai_assist" if conf >= 50 else "human_only"
                parsed["category"] = cat
                parsed["confidence"] = conf
                return parsed
        except Exception as exc:
            logger.warning("classify_ticket LLM failed: %s", exc)
        return self._heuristic(ticket)

    def generate_sprint_report(self, classified_tickets: list[dict], sprint_data: SprintData) -> dict:
        auto = [t for t in classified_tickets if t.get("category") == "auto_fix"]
        assist = [t for t in classified_tickets if t.get("category") == "ai_assist"]
        human = [t for t in classified_tickets if t.get("category") == "human_only"]
        minutes = sum(int(t.get("estimated_minutes") or 0) for t in auto)
        hours = round(minutes / 60.0, 1)
        remaining = [t for t in classified_tickets if (t.get("status") or "") != "done"]
        at_risk = False
        risk_reason = ""
        try:
            end = datetime.fromisoformat((sprint_data.end_date or "")[:10]) if sprint_data.end_date else None
            start = datetime.fromisoformat((sprint_data.start_date or "")[:10]) if sprint_data.start_date else None
            if end:
                remaining_days = max(0, (end.date() - date.today()).days)
                sprint_days = max(1, (end.date() - (start.date() if start else end.date())).days or 14)
                avg_velocity = (sprint_data.velocity or 0) / sprint_days
                if avg_velocity > 0:
                    projected = len(remaining) / avg_velocity
                    if projected > remaining_days:
                        at_risk = True
                        risk_reason = (
                            f"Projected {projected:.1f} days of work with {remaining_days} days left "
                            f"({len(remaining)} open tickets)."
                        )
        except Exception:
            pass
        actions = []
        if auto:
            actions.append(f"Run Jessie Fix on {len(auto)} auto-fixable tickets to save ~{hours}h.")
        if at_risk:
            actions.append("Prioritize blockers and move low-value work out of the sprint.")
        if human:
            actions.append(f"Schedule clarification for {len(human)} human-only tickets.")
        return {
            "sprint": sprint_data.name,
            "sprint_id": sprint_data.id,
            "start_date": sprint_data.start_date,
            "end_date": sprint_data.end_date,
            "total_tickets": len(classified_tickets),
            "total": len(classified_tickets),
            "auto_fixable": auto,
            "ai_assist": assist,
            "human_only": human,
            "estimated_ai_savings_hours": hours,
            "estimated_hours_saved": hours,
            "sprint_at_risk": at_risk,
            "risk_reason": risk_reason,
            "recommended_actions": actions,
            "classified": classified_tickets,
        }

    def _heuristic(self, ticket: Ticket) -> dict:
        label = (ticket.label or "").lower()
        desc = (ticket.description or "").lower()
        conf = 55
        cat = "ai_assist"
        if label == "bug" and any(k in desc for k in ("error", "exception", "500", "traceback", "null", "undefined")):
            conf, cat = 85, "auto_fix"
        elif label in ("task",) and "test" in desc:
            conf, cat = 82, "auto_fix"
        elif label == "feature" and len(ticket.description or "") > 600:
            conf, cat = 45, "human_only"
        elif "security" in desc or "infra" in desc or "deploy" in desc:
            conf, cat = 30, "human_only"
        return {
            "can_fix": cat == "auto_fix",
            "confidence": conf,
            "reason": "Heuristic classification (no Claude key or LLM fallback)",
            "complexity": 4 if cat == "auto_fix" else 7,
            "estimated_minutes": 25 if cat == "auto_fix" else 90,
            "risks": [],
            "category": cat,
        }

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
