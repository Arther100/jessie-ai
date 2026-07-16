"""
Jessie — backend/agents/code_reviewer/reporter.py
Generates the full Markdown review report and saves it to /reviews.
"""

from datetime import datetime
from pathlib import Path

SEVERITY_EMOJI = {"critical": "🔴", "high": "🟡", "medium": "🔵", "low": "⚪"}
LAYER_EMOJI    = {"frontend": "🎨", "backend": "⚙️", "database": "🗄️"}
GRADE_DESC     = {"A": "Excellent", "B": "Good", "C": "Needs improvement",
                  "D": "Poor", "F": "Critical issues"}

_LAYER_CATS = {
    "frontend": [
        "security", "performance", "accessibility",
        "structure", "hardcoded_config", "dead_code", "advanced_flows",
    ],
    "backend": [
        "security", "performance", "error_handling", "api_design",
        "structure", "hardcoded_config", "dead_code", "advanced_flows",
    ],
    "database": [
        "security", "performance", "schema_design",
        "migrations", "transactions",
        "hardcoded_config", "dead_code", "advanced_flows",
    ],
}


def _grade(score: int) -> str:
    if score >= 90: return "A"
    if score >= 80: return "B"
    if score >= 70: return "C"
    if score >= 60: return "D"
    return "F"


def _lang(filename: str) -> str:
    return {
        ".py": "python", ".ts": "typescript", ".tsx": "typescript",
        ".js": "javascript", ".jsx": "javascript", ".go": "go",
        ".java": "java", ".rs": "rust", ".sql": "sql", ".cs": "csharp",
    }.get(Path(filename).suffix.lower(), "")


class MarkdownReporter:

    def generate(
        self,
        scores:       dict,
        raw_results:  dict,
        project_path: str,
        triggered_by: str,
        model_used:   str,
        duration_s:   float,
        total_files:  int,
        tokens_used:  int,
        cost:         float,
    ) -> str:
        project_name = Path(project_path).name
        now   = datetime.now().strftime("%Y-%m-%d %H:%M")
        lines = []

        # ── Header ──────────────────────────────────────────────────────────
        lines += [
            "# 🔍 Jessie Code Review Report",
            f"**Project:** `{project_name}`  ",
            f"**Reviewed:** {now}  ",
            f"**Triggered by:** {triggered_by}  ",
            f"**Model:** {model_used}  ",
            "",
            "---",
            "",
        ]

        # ── Score table ──────────────────────────────────────────────────────
        overall = scores["overall"]
        grade   = scores["grade"]
        lines += [
            f"## 📊 Overall Score: {overall}/100 ({grade} — {GRADE_DESC.get(grade, '')})",
            "",
            "| Layer | Score | Grade | Issues |",
            "|-------|-------|-------|--------|",
        ]
        for layer in ("frontend", "backend", "database"):
            if not scores.get(f"has_{layer}"):
                continue
            ld     = scores.get(layer, {})
            emoji  = LAYER_EMOJI.get(layer, "")
            lscore = ld.get("score", 0)
            lgrade = ld.get("grade", "—")
            lcount = ld.get("issue_count", 0)
            lines.append(f"| {emoji} {layer.capitalize()} | {lscore}/100 | {lgrade} | {lcount} issues |")
        lines += ["", "---", ""]

        # ── Priority fixes ───────────────────────────────────────────────────
        priority = scores.get("priority_fixes", [])
        if priority:
            lines += ["## 🚨 Priority Fixes (Top 5)", "", "These must be addressed first:", ""]
            for i, iss in enumerate(priority, 1):
                sev    = iss.get("severity", "low")
                emoji2 = SEVERITY_EMOJI.get(sev, "⚪")
                file_  = iss.get("file", "unknown")
                line_  = iss.get("line", 0)
                loc    = f"{file_}:{line_}" if line_ else file_
                title  = iss.get("title", "Issue")
                detail = iss.get("detail", "")
                fix    = iss.get("fix", "")
                before = iss.get("example_before", "")
                after  = iss.get("example_after", "")

                lines += [f"{i}. **{emoji2} [{sev.upper()}] {title} — `{loc}`**"]
                if detail:
                    lines += [f"   > {detail}", ""]
                if fix:
                    lines += [f"   **Fix:** {fix}", ""]
                if before or after:
                    lang = _lang(file_)
                    lines += [f"   ```{lang}"]
                    if before:
                        lines += ["   # Before (problematic)"] + [f"   {l}" for l in before.splitlines()]
                    if after:
                        lines += ["   # After (fixed)"] + [f"   {l}" for l in after.splitlines()]
                    lines += ["   ```", ""]
        lines += ["---", ""]

        # ── Per-layer sections ───────────────────────────────────────────────
        for layer, cats in _LAYER_CATS.items():
            if not scores.get(f"has_{layer}"):
                continue
            raw_layer    = raw_results.get(layer, {})
            layer_scores = scores.get(layer, {})
            emoji        = LAYER_EMOJI.get(layer, "")
            lscore       = layer_scores.get("score", 0)
            lgrade       = layer_scores.get("grade", "—")

            lines += [f"## {emoji} {layer.capitalize()} Review — {lscore}/100 ({lgrade})", ""]

            for cat in cats:
                cat_data = raw_layer.get("categories", {}).get(cat)
                if not cat_data:
                    continue
                cscore    = cat_data.get("score", 0)
                cgrade    = _grade(cscore)
                issues    = cat_data.get("issues", [])
                cat_title = cat.replace("_", " ").title()

                lines += [f"### {cat_title} — {cscore}/100 ({cgrade})", ""]

                if not issues:
                    lines += ["✅ No issues found.", ""]
                    continue

                for iss in issues:
                    sev    = iss.get("severity", "low")
                    emoji2 = SEVERITY_EMOJI.get(sev, "⚪")
                    file_  = iss.get("file", "unknown")
                    line_  = iss.get("line", 0)
                    loc    = f"`{file_}:{line_}`" if line_ else f"`{file_}`"
                    title  = iss.get("title", "Issue")
                    rule   = iss.get("rule", "")
                    detail = iss.get("detail", "")
                    fix    = iss.get("fix", "")
                    before = iss.get("example_before", "")
                    after  = iss.get("example_after", "")
                    rule_s = f" `{rule}`" if rule else ""

                    lines += [f"#### {emoji2} [{sev.upper()}]{rule_s} {title} — {loc}", ""]
                    if detail:
                        lines += [detail, ""]
                    if fix:
                        lines += [f"**Fix:** {fix}", ""]
                    if before or after:
                        lang = _lang(file_)
                        lines += [f"```{lang}"]
                        if before:
                            lines += ["# Before (problematic)"] + before.splitlines()
                        if after:
                            lines += ["# After (fixed)"] + after.splitlines()
                        lines += ["```", ""]

            lines += ["---", ""]

        # ── What to do next ──────────────────────────────────────────────────
        all_issues = []
        for layer in ("frontend", "backend", "database"):
            for cat, data in raw_results.get(layer, {}).get("categories", {}).items():
                for iss in data.get("issues", []):
                    all_issues.append({**iss, "_layer": layer, "_cat": cat})

        critical_high = [i for i in all_issues if i.get("severity") in ("critical", "high")]
        medium_issues = [i for i in all_issues if i.get("severity") == "medium"]
        low_issues    = [i for i in all_issues if i.get("severity") == "low"]

        lines += ["## 📈 What To Do Next", ""]

        if critical_high:
            lines += ["### Fix This Week (Critical + High)", ""]
            for iss in critical_high:
                file_ = iss.get("file", "unknown")
                line_ = iss.get("line", 0)
                loc   = f"{file_}:{line_}" if line_ else file_
                lines.append(f"- [ ] **{iss.get('title', 'Issue')}** — `{loc}`")
            lines.append("")

        if medium_issues:
            lines += ["### Fix This Sprint (Medium)", ""]
            for iss in medium_issues:
                file_ = iss.get("file", "unknown")
                line_ = iss.get("line", 0)
                loc   = f"{file_}:{line_}" if line_ else file_
                lines.append(f"- [ ] {iss.get('title', 'Issue')} — `{loc}`")
            lines.append("")

        if low_issues:
            lines += ["### Backlog (Low)", ""]
            for iss in low_issues:
                file_ = iss.get("file", "unknown")
                line_ = iss.get("line", 0)
                loc   = f"{file_}:{line_}" if line_ else file_
                lines.append(f"- [ ] {iss.get('title', 'Issue')} — `{loc}`")
            lines.append("")

        lines += ["---", ""]

        # ── Issue summary table ──────────────────────────────────────────────
        sev_total = scores.get("severity_counts", {})
        fe_sev    = scores.get("frontend",  {}).get("severity_counts", {})
        be_sev    = scores.get("backend",   {}).get("severity_counts", {})
        db_sev    = scores.get("database",  {}).get("severity_counts", {})

        lines += [
            "## 🔢 Issue Summary",
            "",
            "| Severity | Frontend | Backend | Database | Total |",
            "|----------|----------|---------|----------|-------|",
        ]
        for sev in ("critical", "high", "medium", "low"):
            emoji2 = SEVERITY_EMOJI.get(sev, "⚪")
            lines.append(
                f"| {emoji2} {sev.capitalize()} "
                f"| {fe_sev.get(sev, 0)} "
                f"| {be_sev.get(sev, 0)} "
                f"| {db_sev.get(sev, 0)} "
                f"| {sev_total.get(sev, 0)} |"
            )
        lines.append(
            f"| **Total** "
            f"| **{scores.get('frontend',{}).get('issue_count',0)}** "
            f"| **{scores.get('backend',{}).get('issue_count',0)}** "
            f"| **{scores.get('database',{}).get('issue_count',0)}** "
            f"| **{scores.get('total_issues',0)}** |"
        )
        lines += ["", "---", ""]

        # ── Footer ───────────────────────────────────────────────────────────
        dur = f"{duration_s:.0f}s"
        lines += [
            "*Generated by Jessie AI Code Review Agent*  ",
            f"*Review took {dur} · {total_files} files scanned*  ",
            f"*{tokens_used:,} tokens used · Est. cost ${cost:.4f}*  ",
        ]

        return "\n".join(lines)

    def save(self, report_str: str, project_path: str) -> str:
        """Save to {project_path}/reviews/review_{YYYY-MM-DD_HH-MM}.md"""
        reviews_dir = Path(project_path) / "reviews"
        try:
            reviews_dir.mkdir(parents=True, exist_ok=True)
        except OSError:
            reviews_dir = Path(project_path)   # fallback: project root

        fname = datetime.now().strftime("review_%Y-%m-%d_%H-%M.md")
        path  = reviews_dir / fname
        path.write_text(report_str, encoding="utf-8")
        return str(path)
