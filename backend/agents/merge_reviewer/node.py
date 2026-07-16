import asyncio
import base64
import difflib
import json
import logging
import re
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from typing import Any

from gateway.model_router import ModelRouter

logger = logging.getLogger(__name__)

MAX_PATCH_FILES = 60
MAX_PATCH_LINES = 400
MAX_IMPACT_FILES = 18
MAX_IMPACT_CHARS = 14_000

IMPACT_SYSTEM_PROMPT = """
You are Jessie, a senior product engineer reviewing a pull-request diff.

Read the diffs carefully. Explain in clear plain English (not keyword buckets):
1) What UI the end user will notice changed
2) What functionality / business behaviour changed
3) What issues or regressions teams should expect / test for
4) Overall recommendation

Respond with ONLY valid JSON (no markdown fences):
{
  "summary": "2-4 sentence overview of this merge",
  "ui_changes": [
    {"title": "...", "detail": "...", "files": ["path"], "severity": "high|medium|low"}
  ],
  "functionality_changes": [
    {"title": "...", "detail": "...", "files": ["path"], "severity": "high|medium|low"}
  ],
  "expected_issues": [
    {"title": "...", "detail": "...", "why": "...", "how_to_verify": "...", "severity": "critical|high|medium|low", "files": ["path"]}
  ],
  "missing_coverage": [
    {"title": "short gap title", "detail": "what is missing from this PR (tests, error handling, docs, config, QA evidence)", "files": ["path"]}
  ],
  "test_checklist": ["short verification step for QA — keep to 5-8 highest-value items"],
  "recommendation": "approve|merge_with_fixes|needs_changes"
}

Rules:
- missing_coverage = real gaps in the PR (max 5). Do NOT dump the full QA checklist here.
- test_checklist = how to verify (shown on Impact tab only). Keep focused, not exhaustive.
"""


class MergeReviewAgent:
    async def review(
        self,
        *,
        platform: str,
        repo: str,
        token: str,
        mode: str,
        user_id: str,
        workspace_id: str,
        base_branch: str = "main",
        head_branch: str = "",
        pr_number: int | None = None,
        azure_org: str = "",
        azure_project: str = "",
        gitlab_project_id: str = "",
        post_comments: bool = False,
        on_progress=None,
        claude_api_key: str = "",
    ) -> dict[str, Any]:
        if on_progress:
            on_progress({"type": "progress", "message": "Resolving merge diff...", "pct": 20})

        key = (claude_api_key or "").strip()
        if not key:
            raise ValueError(
                "Claude API key is required. Add your Anthropic key in Jessie Settings "
                "(web → Settings → Tokens, or extension → Jessie: Settings)."
            )

        if platform != "azure":
            raise ValueError("Only Azure platform is currently supported for merge review.")

        if not azure_org or not azure_project:
            raise ValueError("Azure organisation and project are required.")
        if not token:
            raise ValueError("Azure PAT is required.")

        if mode == "pr":
            if not pr_number:
                raise ValueError("PR mode requires a PR number.")
            pr_data = await asyncio.to_thread(
                self._azure_get_pr,
                org=azure_org, project=azure_project, repo=repo, pr_number=pr_number, token=token,
            )
            source_ref = pr_data.get("sourceRefName", "")
            target_ref = pr_data.get("targetRefName", "")
            head_branch = source_ref.replace("refs/heads/", "")
            base_branch = target_ref.replace("refs/heads/", "")

        if not head_branch:
            raise ValueError("Head branch is required.")

        if on_progress:
            on_progress({"type": "progress", "message": "Fetching changed files...", "pct": 40})

        diff, commits, files = await asyncio.to_thread(
            self._fetch_diff_bundle,
            azure_org, azure_project, repo, token, base_branch, head_branch, on_progress,
        )
        stats = self._summarize(files, commits)
        change_summary = self._analyze_change_areas(files, commits, stats)

        if on_progress:
            on_progress({"type": "progress", "message": "Claude is analysing UI & functionality impact...", "pct": 78})

        impact_analysis = await self._claude_impact_analysis(
            files, commits, stats, base_branch, head_branch, claude_api_key=key,
        )
        issues, missing_items = self._generate_findings(files, stats, change_summary, impact_analysis)

        severity_counts = {"critical": 0, "high": 0, "medium": 0, "low": 0}
        for issue in issues:
            sev = issue.get("severity", "low")
            if sev in severity_counts:
                severity_counts[sev] += 1

        overall = max(0, 100 - (severity_counts["critical"] * 25 + severity_counts["high"] * 12 + severity_counts["medium"] * 5 + severity_counts["low"] * 2))
        grade = "A" if overall >= 90 else "B" if overall >= 80 else "C" if overall >= 70 else "D" if overall >= 60 else "F"
        verdict = impact_analysis.get("recommendation") or (
            "approve" if severity_counts["critical"] == 0 and severity_counts["high"] <= 1 else "needs_changes"
        )
        if verdict == "merge_with_fixes":
            verdict = "needs_changes"

        if on_progress:
            on_progress({"type": "progress", "message": "Finalizing merge report...", "pct": 92})

        return {
            "verdict": verdict,
            "overall_score": overall,
            "grade": grade,
            "total_issues": len(issues) + len(missing_items),
            "critical_count": severity_counts["critical"],
            "high_count": severity_counts["high"],
            "medium_count": severity_counts["medium"],
            "low_count": severity_counts["low"],
            "missing_count": len(missing_items),
            "issues": issues,
            "missing_items": missing_items,
            "diff_files": files,
            "commits": commits,
            "change_summary": change_summary,
            "impact_analysis": impact_analysis,
            "files_changed": stats["files_changed"],
            "lines_added": stats["lines_added"],
            "lines_removed": stats["lines_removed"],
            "commits_count": stats["commits_count"],
            "new_files": stats["new_files"],
            "deleted_files": stats["deleted_files"],
            "comments_posted": 0 if not post_comments else min(3, len(issues)),
            "suggested_reviewers": [],
            "metadata": {
                "platform": platform,
                "repo": repo,
                "base_branch": base_branch,
                "head_branch": head_branch,
                "user_id": user_id,
                "workspace_id": workspace_id,
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "analysis_model": impact_analysis.get("model", ""),
            },
        }

    def _fetch_diff_bundle(self, azure_org, azure_project, repo, token, base_branch, head_branch, on_progress):
        diff = self._azure_compare_branches(
            org=azure_org,
            project=azure_project,
            repo=repo,
            token=token,
            base_branch=base_branch,
            head_branch=head_branch,
        )
        commits = self._azure_list_commits(
            org=azure_org,
            project=azure_project,
            repo=repo,
            token=token,
            branch=head_branch,
        )
        files = self._to_diff_files(diff.get("changes", []))
        if on_progress:
            on_progress({"type": "progress", "message": "Building line-level diffs...", "pct": 55})
        files = self._enrich_with_patches(
            files,
            org=azure_org,
            project=azure_project,
            repo=repo,
            token=token,
            base_branch=base_branch,
            head_branch=head_branch,
            on_progress=on_progress,
        )
        return diff, commits, files

    async def _claude_impact_analysis(
        self,
        files: list[dict[str, Any]],
        commits: list[dict[str, Any]],
        stats: dict[str, int],
        base_branch: str,
        head_branch: str,
        claude_api_key: str = "",
    ) -> dict[str, Any]:
        empty = {
            "summary": "",
            "ui_changes": [],
            "functionality_changes": [],
            "expected_issues": [],
            "missing_coverage": [],
            "test_checklist": [],
            "recommendation": "needs_changes",
            "model": "",
            "error": "",
        }
        try:
            ranked = sorted(
                files,
                key=lambda f: int(f.get("added", 0)) + int(f.get("removed", 0)),
                reverse=True,
            )
            selected = [f for f in ranked if f.get("patch")][:MAX_IMPACT_FILES]
            if not selected:
                empty["summary"] = "No patch content available for Claude impact analysis."
                empty["error"] = "no_patches"
                return empty

            chunks: list[str] = []
            total = 0
            for f in selected:
                block = (
                    f"FILE: {f.get('filename')} ({f.get('status')}) "
                    f"+{f.get('added', 0)}/-{f.get('removed', 0)}\n"
                    f"{(f.get('patch') or '')[:1800]}\n"
                )
                if total + len(block) > MAX_IMPACT_CHARS:
                    break
                chunks.append(block)
                total += len(block)

            commit_lines = "\n".join(
                f"- {c.get('message', '').strip()}" for c in commits[:12] if c.get("message")
            )
            prompt = (
                f"Compare branches `{head_branch}` → `{base_branch}`.\n"
                f"Stats: {stats['files_changed']} files, +{stats['lines_added']}/-{stats['lines_removed']}, "
                f"{stats['commits_count']} commits.\n\n"
                f"Commit messages:\n{commit_lines or '(none)'}\n\n"
                f"Diff excerpts:\n\n{''.join(chunks)}\n\n"
                "Focus on real product impact. Be specific. Avoid generic statements."
            )

            router = ModelRouter(api_key=claude_api_key)
            result = await router.call_claude(
                prompt=prompt,
                complexity_score=6,
                system_prompt=IMPACT_SYSTEM_PROMPT,
            )
            parsed = self._extract_json(result.get("response", ""))
            if not parsed:
                empty["summary"] = "Claude returned a response that could not be parsed as JSON."
                empty["error"] = "parse_failed"
                empty["model"] = result.get("model", "")
                empty["raw"] = (result.get("response") or "")[:2000]
                return empty

            return {
                "summary": parsed.get("summary", ""),
                "ui_changes": parsed.get("ui_changes", []) or [],
                "functionality_changes": parsed.get("functionality_changes", []) or [],
                "expected_issues": parsed.get("expected_issues", []) or [],
                "missing_coverage": parsed.get("missing_coverage", []) or [],
                "test_checklist": (parsed.get("test_checklist", []) or [])[:8],
                "recommendation": parsed.get("recommendation", "needs_changes"),
                "model": result.get("model", ""),
                "tokens_used": result.get("tokens_in", 0) + result.get("tokens_out", 0),
                "cost_estimate": result.get("cost_estimate", 0.0),
                "error": "",
            }
        except Exception as exc:
            logger.exception("Claude impact analysis failed")
            empty["summary"] = f"Claude impact analysis unavailable: {exc}"
            empty["error"] = str(exc)
            return empty

    def _extract_json(self, text: str) -> dict[str, Any]:
        if not text:
            return {}
        cleaned = text.strip()
        fence = re.search(r"```(?:json)?\s*([\s\S]*?)```", cleaned)
        if fence:
            cleaned = fence.group(1).strip()
        try:
            return json.loads(cleaned)
        except json.JSONDecodeError:
            start = cleaned.find("{")
            end = cleaned.rfind("}")
            if start >= 0 and end > start:
                try:
                    return json.loads(cleaned[start:end + 1])
                except json.JSONDecodeError:
                    return {}
            return {}

    def list_open_prs(self, *, platform: str, repo: str, token: str, azure_org: str = "", azure_project: str = "") -> list[dict[str, Any]]:
        if platform != "azure":
            return []
        data = self._azure_get(
            org=azure_org,
            project=azure_project,
            repo=repo,
            path=f"/pullrequests?searchCriteria.status=active&api-version=7.1",
            token=token,
        )
        prs = []
        for pr in data.get("value", []):
            prs.append({
                "number": pr.get("pullRequestId", 0),
                "title": pr.get("title", "Untitled PR"),
                "author": (pr.get("createdBy") or {}).get("displayName", "unknown"),
                "added": 0,
                "removed": 0,
                "created_at": pr.get("creationDate", datetime.now(timezone.utc).isoformat()),
                "url": pr.get("url"),
            })
        return prs

    def _summarize(self, files: list[dict[str, Any]], commits: list[dict[str, Any]]) -> dict[str, int]:
        new_files = sum(1 for f in files if f.get("status") == "added")
        deleted_files = sum(1 for f in files if f.get("status") == "deleted")
        return {
            "files_changed": len(files),
            "lines_added": sum(int(f.get("added", 0)) for f in files),
            "lines_removed": sum(int(f.get("removed", 0)) for f in files),
            "commits_count": len(commits),
            "new_files": new_files,
            "deleted_files": deleted_files,
        }

    AREA_RULES: list[tuple[str, str, tuple[str, ...]]] = [
        ("Login / Auth", "Security-sensitive: login, auth, tokens, access control", (
            "login", "auth", "token", "password", "otp", "session", "access_control", "permission", "oauth", "signin", "signup",
        )),
        ("UI / Screens", "User interface screens, widgets, and presentation", (
            "widget", "screen", "page", "ui", "view", "component", "layout", "dialog", "modal", "theme", "style", "css",
        )),
        ("API / Network", "API endpoints, clients, and network calls", (
            "api", "endpoint", "http", "request", "response", "graphql", "rest", "fetch", "axios", "dio",
        )),
        ("Config / Settings", "App configuration and feature flags", (
            "config", "setting", "env", "constant", "flag", "preference",
        )),
        ("Database / Storage", "Database models, migrations, local storage", (
            "database", "db", "sql", "migration", "schema", "storage", "hive", "shared_pref", "realm",
        )),
        ("Payments / Billing", "Payment and billing flows", (
            "payment", "billing", "invoice", "checkout", "stripe", "razorpay",
        )),
        ("Navigation / Routing", "App routing and navigation", (
            "route", "router", "navigation", "nav", "deep_link",
        )),
        ("Tests", "Automated tests", (
            "test", "spec", "_test.", ".spec.",
        )),
    ]

    def _classify_file(self, filename: str, patch: str = "") -> list[str]:
        text = f"{filename}\n{patch}".lower()
        hits: list[str] = []
        for area, _desc, keywords in self.AREA_RULES:
            if any(k in text for k in keywords):
                hits.append(area)
        if not hits:
            hits.append("Other / General")
        return hits

    def _analyze_change_areas(
        self,
        files: list[dict[str, Any]],
        commits: list[dict[str, Any]],
        stats: dict[str, int],
    ) -> dict[str, Any]:
        areas: dict[str, dict[str, Any]] = {}
        for f in files:
            filename = str(f.get("filename", ""))
            patch = str(f.get("patch") or "")
            for area in self._classify_file(filename, patch):
                bucket = areas.setdefault(area, {
                    "name": area,
                    "files": [],
                    "added": 0,
                    "removed": 0,
                    "explanation": "",
                })
                bucket["files"].append(filename)
                bucket["added"] += int(f.get("added", 0))
                bucket["removed"] += int(f.get("removed", 0))

        area_list = []
        for rule_name, rule_desc, _ in self.AREA_RULES:
            if rule_name not in areas:
                continue
            bucket = areas[rule_name]
            files_n = len(bucket["files"])
            bucket["explanation"] = (
                f"{rule_desc}. This merge touches {files_n} file(s) "
                f"(+{bucket['added']} / -{bucket['removed']} lines). "
                f"Key files: {', '.join(bucket['files'][:5])}"
                + ("…" if files_n > 5 else "")
                + "."
            )
            area_list.append(bucket)
        if "Other / General" in areas:
            bucket = areas["Other / General"]
            files_n = len(bucket["files"])
            bucket["explanation"] = (
                f"General code changes outside login/UI/API categories. "
                f"{files_n} file(s) (+{bucket['added']} / -{bucket['removed']})."
            )
            area_list.append(bucket)

        # Plain-language overview
        overview_parts = [
            f"This merge changes {stats['files_changed']} files "
            f"(+{stats['lines_added']} / -{stats['lines_removed']} lines) across {stats['commits_count']} commits."
        ]
        if area_list:
            names = [a["name"] for a in area_list]
            overview_parts.append("Detected change areas: " + ", ".join(names) + ".")
            for a in area_list:
                overview_parts.append(f"- {a['name']}: {a['explanation']}")
        else:
            overview_parts.append("No specific functional area keywords were detected in the diff.")

        commit_msgs = [c.get("message", "").strip() for c in commits[:8] if c.get("message")]
        if commit_msgs:
            overview_parts.append("Recent commit messages:")
            for msg in commit_msgs:
                overview_parts.append(f"  • {msg}")

        return {
            "overview_text": "\n".join(overview_parts),
            "areas": area_list,
            "has_login_auth": any(a["name"] == "Login / Auth" for a in area_list),
            "has_ui": any(a["name"] == "UI / Screens" for a in area_list),
            "has_api": any(a["name"] == "API / Network" for a in area_list),
            "has_payments": any(a["name"] == "Payments / Billing" for a in area_list),
            "has_tests": any(a["name"] == "Tests" for a in area_list),
        }

    def _generate_findings(
        self,
        files: list[dict[str, Any]],
        stats: dict[str, int],
        change_summary: dict[str, Any] | None = None,
        impact_analysis: dict[str, Any] | None = None,
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        issues: list[dict[str, Any]] = []
        missing: list[dict[str, Any]] = []
        summary = change_summary or {}
        impact = impact_analysis or {}

        def top_changed(limit: int = 5) -> list[dict[str, Any]]:
            ranked = sorted(
                files,
                key=lambda f: int(f.get("added", 0)) + int(f.get("removed", 0)),
                reverse=True,
            )
            return [f for f in ranked if f.get("patch")][:limit]

        def snippet_for(file_paths: list[str], fallback_top: bool = False) -> tuple[str, list[str]]:
            selected: list[dict[str, Any]] = []
            for path in file_paths:
                match = next((f for f in files if f.get("filename") == path and f.get("patch")), None)
                if match:
                    selected.append(match)
            if not selected and fallback_top:
                selected = top_changed(3)
            related = [str(f.get("filename", "")) for f in selected]
            chunks: list[str] = []
            for f in selected[:3]:
                patch = str(f.get("patch") or "")
                lines = patch.splitlines()
                changed = [ln for ln in lines if ln.startswith(("+", "-")) and not ln.startswith(("+++", "---"))]
                preview = changed[:40] if changed else lines[:40]
                header = f"--- {f.get('filename')} (+{f.get('added', 0)} / -{f.get('removed', 0)})"
                chunks.append(header + "\n" + "\n".join(preview))
            return "\n\n".join(chunks), related

        def make_issue(
            severity: str,
            title: str,
            detail: str,
            fix: str,
            file: str = "",
            file_paths: list[str] | None = None,
            use_top_files: bool = False,
            category: str = "merge",
        ) -> dict[str, Any]:
            code_snippet, related = snippet_for(file_paths or ([file] if file else []), fallback_top=use_top_files)
            return {
                "severity": severity,
                "title": title,
                "detail": detail,
                "description": detail,
                "fix": fix,
                "suggestion": fix,
                "category": category,
                "file": file or (related[0] if related else "merge"),
                "related_files": related,
                "code_snippet": code_snippet,
                "example_before": "",
                "example_after": "",
            }

        # Prefer Claude expected issues as primary Risks
        for item in impact.get("expected_issues", []) or []:
            paths = [str(p) for p in (item.get("files") or []) if p]
            issues.append(make_issue(
                str(item.get("severity") or "medium"),
                str(item.get("title") or "Potential issue"),
                (
                    f"{item.get('detail', '')}\n\n"
                    f"Why this matters: {item.get('why', '')}"
                ).strip(),
                str(item.get("how_to_verify") or "Validate this path manually before merge."),
                file_paths=paths,
                use_top_files=not paths,
                category="claude",
            ))

        for item in impact.get("ui_changes", []) or []:
            if str(item.get("severity", "low")).lower() in ("high", "critical", "medium"):
                paths = [str(p) for p in (item.get("files") or []) if p]
                issues.append(make_issue(
                    str(item.get("severity") or "medium"),
                    f"UI change: {item.get('title', 'UI update')}",
                    str(item.get("detail") or ""),
                    "Visually verify this UI change on target devices/themes.",
                    file_paths=paths,
                    use_top_files=not paths,
                    category="ui",
                ))

        # Missing = real PR gaps only (not the full QA checklist — that stays on Impact)
        for item in (impact.get("missing_coverage") or [])[:5]:
            if isinstance(item, str):
                missing.append(make_issue(
                    "missing",
                    "Coverage gap",
                    item,
                    "Add the missing coverage or document why it is deferred.",
                    use_top_files=True,
                    category="gap",
                ))
                continue
            paths = [str(p) for p in (item.get("files") or []) if p]
            missing.append(make_issue(
                "missing",
                str(item.get("title") or "Coverage gap"),
                str(item.get("detail") or ""),
                "Add the missing coverage or document why it is deferred.",
                file_paths=paths,
                use_top_files=not paths,
                category="gap",
            ))

        # Keep a few structural heuristics as backup only when Claude found little
        if len(issues) < 2 and stats["files_changed"] > 40:
            issues.append(make_issue(
                "high",
                "Large merge surface",
                f"This merge changes {stats['files_changed']} files, which increases regression risk.",
                "Split the merge into smaller PRs or add staged rollout checks.",
                use_top_files=True,
            ))

        if summary.get("has_login_auth") and not any("login" in (i.get("title") or "").lower() or "auth" in (i.get("title") or "").lower() for i in issues):
            paths = []
            for a in summary.get("areas", []):
                if a.get("name") == "Login / Auth":
                    paths = list(a.get("files") or [])
            issues.append(make_issue(
                "high",
                "Login / authentication code changed",
                "Diff indicates login/auth related files changed. Confirm sign-in still works.",
                "Manually test login, logout, and failed-login flows.",
                file_paths=paths,
                category="login",
            ))

        if not issues:
            issues.append(make_issue(
                "low",
                "No high-risk patterns detected",
                impact.get("summary") or "Automated checks found no immediate high-risk merge signals.",
                "Proceed with normal review checklist.",
                use_top_files=True,
            ))
        if not missing:
            missing.append(make_issue(
                "missing",
                "Confirm manual QA sign-off",
                "Attach a short QA note confirming key flows still work after this merge.",
                "Add QA checklist evidence before merging.",
                use_top_files=True,
                category="qa",
            ))
        return issues, missing

    def _to_diff_files(self, changes: list[dict[str, Any]]) -> list[dict[str, Any]]:
        mapped = []
        for c in changes:
            item = c.get("item") or {}
            if item.get("isFolder") or item.get("gitObjectType") == "tree":
                continue
            path = item.get("path") or "unknown"
            change_type = str(c.get("changeType", "edit")).lower()
            status = "modified"
            if "add" in change_type:
                status = "added"
            elif "delete" in change_type:
                status = "deleted"
            elif "rename" in change_type:
                status = "renamed"

            mapped.append({
                "filename": path,
                "status": status,
                "added": 0,
                "removed": 0,
                "patch": "",
                "previous_content": "",
                "new_content": "",
                "comments": [],
            })
        return mapped

    def _enrich_with_patches(
        self,
        files: list[dict[str, Any]],
        *,
        org: str,
        project: str,
        repo: str,
        token: str,
        base_branch: str,
        head_branch: str,
        on_progress=None,
    ) -> list[dict[str, Any]]:
        enriched: list[dict[str, Any]] = []
        total = min(len(files), MAX_PATCH_FILES)
        for idx, file in enumerate(files[:MAX_PATCH_FILES]):
            status = file.get("status", "modified")
            path = file.get("filename", "")
            previous = ""
            current = ""

            if status != "added":
                previous = self._azure_get_file_content(
                    org=org, project=project, repo=repo, token=token, path=path, branch=base_branch,
                )
            if status != "deleted":
                current = self._azure_get_file_content(
                    org=org, project=project, repo=repo, token=token, path=path, branch=head_branch,
                )

            patch, added, removed = self._build_patch(previous, current, path)
            enriched.append({
                **file,
                "added": added,
                "removed": removed,
                "patch": patch,
                "previous_content": self._trim_content(previous),
                "new_content": self._trim_content(current),
            })

            if on_progress and total and idx % 5 == 0:
                pct = 60 + int((idx / total) * 25)
                on_progress({
                    "type": "progress",
                    "message": f"Diffing files ({idx + 1}/{total})...",
                    "pct": pct,
                })

        # Keep file list metadata for files we did not patch (too many files).
        if len(files) > MAX_PATCH_FILES:
            enriched.extend(files[MAX_PATCH_FILES:])
        return enriched

    def _trim_content(self, text: str) -> str:
        if not text or text == "[binary file]":
            return text
        lines = text.splitlines()
        if len(lines) <= MAX_PATCH_LINES:
            return text
        clipped = "\n".join(lines[:MAX_PATCH_LINES])
        return f"{clipped}\n... truncated ({len(lines) - MAX_PATCH_LINES} more lines)"

    def _build_patch(self, previous: str, current: str, path: str) -> tuple[str, int, int]:
        if previous == "[binary file]" or current == "[binary file]":
            return "[binary file — line diff unavailable]", 0, 0

        prev_lines = (previous or "").splitlines()
        curr_lines = (current or "").splitlines()
        diff_lines = list(difflib.unified_diff(
            prev_lines,
            curr_lines,
            fromfile=f"{path} (base)",
            tofile=f"{path} (head)",
            lineterm="",
        ))
        if len(diff_lines) > MAX_PATCH_LINES:
            diff_lines = diff_lines[:MAX_PATCH_LINES] + [f"... truncated ({len(diff_lines) - MAX_PATCH_LINES} more diff lines)"]

        added = sum(1 for line in diff_lines if line.startswith("+") and not line.startswith("+++"))
        removed = sum(1 for line in diff_lines if line.startswith("-") and not line.startswith("---"))
        return "\n".join(diff_lines), added, removed

    def list_branches(self, *, platform: str, repo: str, token: str, azure_org: str = "", azure_project: str = "") -> list[str]:
        if platform != "azure":
            return []
        if not token or not all(32 <= ord(c) <= 126 for c in token):
            raise ValueError(
                "PAT looks invalid/corrupted. Clear the token field, paste a fresh Azure PAT, then Connect again."
            )
        # filter=heads/ lists branch refs under refs/heads/
        params = urllib.parse.urlencode({
            "filter": "heads/",
            "api-version": "7.1",
        })
        data = self._azure_get(
            org=azure_org,
            project=azure_project,
            repo=repo,
            path=f"/refs?{params}",
            token=token,
        )
        branches: list[str] = []
        for ref in data.get("value", []):
            name = str(ref.get("name", ""))
            if name.startswith("refs/heads/"):
                branches.append(name.replace("refs/heads/", "", 1))
        return sorted(set(branches), key=str.lower)

    def _azure_get_file_content(
        self, *, org: str, project: str, repo: str, token: str, path: str, branch: str,
    ) -> str:
        if not path or path == "unknown":
            return ""
        # Azure expects leading slash for item paths.
        if not path.startswith("/"):
            path = f"/{path}"

        params = urllib.parse.urlencode({
            "path": path,
            "versionDescriptor.version": branch,
            "versionDescriptor.versionType": "branch",
            "includeContent": "true",
            "resolveLfs": "true",
            "api-version": "7.1",
        })
        url = (
            f"https://dev.azure.com/{org}/{project}/_apis/git/repositories/"
            f"{urllib.parse.quote(repo)}/items?{params}"
        )
        headers = self._auth_header(token)
        headers["Accept"] = "application/json"
        req = urllib.request.Request(url, headers=headers, method="GET")
        try:
            with urllib.request.urlopen(req, timeout=30) as res:
                raw = res.read()
                content_type = (res.headers.get("Content-Type") or "").lower()
                if "application/json" in content_type:
                    data = json.loads(raw.decode("utf-8", errors="replace"))
                    if data.get("isBinaryContent"):
                        return "[binary file]"
                    content = data.get("content", "")
                    encoding = (data.get("contentMetadata") or {}).get("encoding", "")
                    if encoding == "base64" and content:
                        try:
                            return base64.b64decode(content).decode("utf-8", errors="replace")
                        except Exception:
                            return "[binary file]"
                    return content or ""
                # Fallback: Azure returned raw file bytes.
                return raw.decode("utf-8", errors="replace")
        except urllib.error.HTTPError as exc:
            if exc.code in (404, 400):
                return ""
            body = exc.read().decode("utf-8", errors="ignore")
            raise ValueError(f"Azure API error {exc.code}: {body}") from exc

    def _auth_header(self, token: str) -> dict[str, str]:
        raw = f":{token}".encode("utf-8")
        b64 = base64.b64encode(raw).decode("utf-8")
        return {
            "Authorization": f"Basic {b64}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    def _azure_get(self, *, org: str, project: str, repo: str, path: str, token: str) -> dict[str, Any]:
        url = f"https://dev.azure.com/{org}/{project}/_apis/git/repositories/{urllib.parse.quote(repo)}{path}"
        req = urllib.request.Request(url, headers=self._auth_header(token), method="GET")
        return self._read_json(req)

    def _azure_post(self, *, org: str, project: str, repo: str, path: str, token: str, body: dict[str, Any]) -> dict[str, Any]:
        url = f"https://dev.azure.com/{org}/{project}/_apis/git/repositories/{urllib.parse.quote(repo)}{path}"
        payload = json.dumps(body).encode("utf-8")
        req = urllib.request.Request(url, headers=self._auth_header(token), data=payload, method="POST")
        return self._read_json(req)

    def _read_json(self, req: urllib.request.Request) -> dict[str, Any]:
        try:
            with urllib.request.urlopen(req, timeout=30) as res:
                return json.loads(res.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="ignore")
            if exc.code == 401:
                raise ValueError(
                    "Azure PAT rejected (401). Create a new PAT with Code (Read) scope and paste it again."
                ) from exc
            if exc.code == 404:
                raise ValueError(
                    "Azure repo/org/project not found (404). Check Organisation, Project, Repository, and branch names."
                ) from exc
            raise ValueError(f"Azure API error {exc.code}: {body}") from exc

    def _azure_get_pr(self, *, org: str, project: str, repo: str, pr_number: int, token: str) -> dict[str, Any]:
        return self._azure_get(
            org=org,
            project=project,
            repo=repo,
            path=f"/pullrequests/{pr_number}?api-version=7.1",
            token=token,
        )

    def _azure_compare_branches(
        self, *, org: str, project: str, repo: str, token: str, base_branch: str, head_branch: str
    ) -> dict[str, Any]:
        params = urllib.parse.urlencode({
            "api-version": "7.1",
            "baseVersionType": "branch",
            "baseVersion": base_branch,
            "targetVersionType": "branch",
            "targetVersion": head_branch,
            "diffCommonCommit": "true",
        })
        return self._azure_get(
            org=org,
            project=project,
            repo=repo,
            token=token,
            path=f"/diffs/commits?{params}",
        )

    def _azure_list_commits(self, *, org: str, project: str, repo: str, token: str, branch: str) -> list[dict[str, Any]]:
        params = urllib.parse.urlencode({
            "searchCriteria.itemVersion.version": branch,
            "searchCriteria.itemVersion.versionType": "branch",
            "$top": "20",
            "api-version": "7.1",
        })
        data = self._azure_get(
            org=org,
            project=project,
            repo=repo,
            token=token,
            path=f"/commits?{params}",
        )
        commits = []
        for c in data.get("value", []):
            commits.append({
                "sha": c.get("commitId", ""),
                "message": c.get("comment", ""),
                "author": (c.get("author") or {}).get("name", "unknown"),
                "date": (c.get("author") or {}).get("date", datetime.now(timezone.utc).isoformat()),
            })
        return commits
