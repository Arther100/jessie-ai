"""Jessie v3 — Sprint health intelligence."""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any


class SprintIntelligence:
    async def analyse_sprint_health(
        self,
        sprint_data: dict,
        review_history: list[dict] | None = None,
        merge_history: list[dict] | None = None,
        classified: list[dict] | None = None,
        ci_failure_rate: float = 0.0,
    ) -> dict:
        tickets = sprint_data.get("tickets") or classified or []
        total = len(tickets) or int(sprint_data.get("total_tickets") or 0) or 1
        done = [t for t in tickets if (t.get("status") or "") == "done"]
        remaining = [t for t in tickets if (t.get("status") or "") != "done"]
        days_remaining = 0
        end = sprint_data.get("end_date") or ""
        try:
            if end:
                days_remaining = max(0, (datetime.fromisoformat(end[:10]).date() - date.today()).days)
        except Exception:
            days_remaining = 0

        avg_quality = 0.0
        if review_history:
            scores = [float(r.get("overall_score") or r.get("quality_score") or 0) for r in review_history]
            avg_quality = sum(scores) / max(1, len(scores))

        blockers = self.detect_blockers(remaining)
        stale = [b for b in blockers if b.get("days_inactive", 0) >= 2]
        auto_count = len([t for t in (classified or tickets) if t.get("category") == "auto_fix"])

        completion_pct = round(100.0 * len(done) / total, 1)
        projected = completion_pct
        if days_remaining == 0 and remaining:
            projected = completion_pct
        health = 100
        health -= min(40, len(remaining) * 3)
        health -= min(20, len(blockers) * 5)
        health -= int(min(20, ci_failure_rate * 20))
        if avg_quality:
            health = int(0.7 * health + 0.3 * avg_quality)
        health = max(0, min(100, health))
        grade = "A" if health >= 90 else "B" if health >= 80 else "C" if health >= 70 else "D" if health >= 60 else "F"
        at_risk = health < 70 or (days_remaining <= 2 and len(remaining) > 3)
        recs = []
        if auto_count:
            recs.append(f"Let Jessie auto-fix {auto_count} tickets to recover capacity.")
        if blockers:
            recs.append("Unblock stale in-progress tickets first.")
        if ci_failure_rate > 0.2:
            recs.append("Enable Jessie CI auto-fix for lint/test failures.")
        if not recs:
            recs.append("Sprint looks healthy — keep focusing on remaining high-priority work.")

        return {
            "health_score": health,
            "health_grade": grade,
            "at_risk": at_risk,
            "days_remaining": days_remaining,
            "tickets_remaining": len(remaining),
            "projected_completion_pct": projected,
            "blockers": blockers,
            "stale_tickets": stale,
            "avg_code_quality": round(avg_quality, 1),
            "ci_failure_rate": ci_failure_rate,
            "recommendations": recs,
            "ai_can_recover": auto_count > 0,
            "auto_fixable_count": auto_count,
            "sprint": sprint_data.get("name") or sprint_data.get("sprint") or "",
        }

    def detect_blockers(self, tickets: list[dict]) -> list[dict]:
        out = []
        now = datetime.now(timezone.utc)
        for t in tickets:
            if (t.get("status") or "") not in ("in_progress", "todo", "in_review"):
                continue
            updated = t.get("updated_at") or ""
            days = 0
            try:
                dt = datetime.fromisoformat(updated.replace("Z", "+00:00"))
                days = max(0, (now - dt).days)
            except Exception:
                days = 0
            reason = ""
            if days >= 2 and (t.get("status") or "") == "in_progress":
                reason = f"No updates for {days} days"
            comments = t.get("comments") or []
            if comments:
                last = str(comments[-1].get("body") or "").lower()
                if any(q in last for q in ("?", "blocked", "waiting", "need clarification")):
                    reason = reason or "Latest comment looks like an unanswered question"
            if reason:
                out.append({
                    "ticket_id": t.get("id"),
                    "blocked_days": days,
                    "days_inactive": days,
                    "reason": reason,
                    "title": t.get("title"),
                })
        return out

    def generate_weekly_report(
        self,
        sprint_data: dict,
        health: dict,
        team_usage: dict | None = None,
        review_history: list[dict] | None = None,
    ) -> str:
        name = sprint_data.get("name") or health.get("sprint") or "Sprint"
        week = date.today().isoformat()
        reviews = len(review_history or [])
        ai_fixed = int((team_usage or {}).get("total_tickets_fixed") or health.get("auto_fixable_count") or 0)
        hours = float((team_usage or {}).get("time_saved_hours") or 0)
        lines = [
            f"# Jessie Weekly Sprint Report",
            f"**Week of {week} · {name}**",
            "",
            f"## Sprint Health: {health.get('health_grade')} ({health.get('health_score')}/100)",
            "",
            "## Highlights",
            f"- {health.get('tickets_remaining', 0)} tickets remaining",
            f"- {ai_fixed} tickets auto-fixable / fixed by Jessie AI",
            f"- Average code quality: {health.get('avg_code_quality', 0)}/100",
            f"- CI/CD failure rate: {round(float(health.get('ci_failure_rate') or 0) * 100, 1)}%",
            "",
            "## At Risk",
        ]
        for b in (health.get("blockers") or [])[:8]:
            lines.append(f"- {b.get('ticket_id')}: {b.get('reason')}")
        if not health.get("blockers"):
            lines.append("- None detected")
        lines += [
            "",
            "## AI Impact This Week",
            f"- Tickets auto-fixed: {ai_fixed}",
            f"- PRs reviewed: {reviews}",
            f"- Estimated hours saved: {hours}h",
            "",
            "## Recommendations",
        ]
        for i, r in enumerate(health.get("recommendations") or [], 1):
            lines.append(f"{i}. {r}")
        return "\n".join(lines) + "\n"
