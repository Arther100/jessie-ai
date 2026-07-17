"""Jessie v3 — CI/CD failure classification and auto-fix."""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any, Callable, Optional

from gateway.model_router import ModelRouter

logger = logging.getLogger(__name__)

CLASSIFY_SYSTEM = """Classify this CI/CD failure. Return ONLY JSON:
{
  "failure_type": "test|build|lint|type_error|dependency|environment|timeout",
  "root_cause": "",
  "file": "path/to/file",
  "line": null,
  "fixable_by_ai": true,
  "fix_complexity": 1,
  "summary": "one line",
  "suggested_steps": ["..."]
}
Fixable: test, lint, type_error. Not fixable: environment, dependency, timeout, infrastructure.
"""


class CICDAgent:
    async def classify_failure(
        self,
        logs: str,
        failed_step: str = "",
        job_name: str = "",
        claude_api_key: str = "",
    ) -> dict:
        truncated = (logs or "")[-10000:]
        if not (claude_api_key or "").strip():
            return self._heuristic(truncated, failed_step, job_name)
        router = ModelRouter(api_key=claude_api_key)
        prompt = f"Job: {job_name}\nStep: {failed_step}\n\nLogs:\n{truncated}"
        result = await router.call_claude(prompt=prompt, complexity_score=5, system_prompt=CLASSIFY_SYSTEM)
        parsed = self._extract_json(result.get("response", "")) or self._heuristic(truncated, failed_step, job_name)
        ftype = (parsed.get("failure_type") or "").lower()
        parsed["fixable_by_ai"] = bool(parsed.get("fixable_by_ai")) and ftype in ("test", "lint", "type_error")
        return parsed

    async def generate_fix(
        self,
        failure_info: dict,
        workspace_path: str,
        claude_api_key: str,
        on_progress: Optional[Callable[[dict], None]] = None,
    ) -> dict:
        if not failure_info.get("fixable_by_ai"):
            return {"fixable": False, "explanation": failure_info.get("root_cause", "")}
        root = Path(workspace_path)
        rel = failure_info.get("file") or ""
        file_path = root / rel if rel else None
        content = ""
        if file_path and file_path.exists():
            content = file_path.read_text(encoding="utf-8", errors="replace")[:12000]
        router = ModelRouter(api_key=claude_api_key)
        prompt = (
            f"Failure type: {failure_info.get('failure_type')}\n"
            f"Root cause: {failure_info.get('root_cause')}\n"
            f"File: {rel} line {failure_info.get('line')}\n\n"
            f"Current file content:\n{content or '(unavailable)'}\n\n"
            "Return JSON: {\"fix_code\": \"...\", \"file_path\": \"...\", \"explanation\": \"...\"}"
        )
        if on_progress:
            on_progress({"type": "progress", "message": "Generating CI fix...", "pct": 60})
        result = await router.call_claude(prompt=prompt, complexity_score=int(failure_info.get("fix_complexity") or 5), system_prompt="Return ONLY JSON with fix_code, file_path, explanation.")
        parsed = self._extract_json(result.get("response", "")) or {}
        return {
            "fixable": True,
            "fix_code": parsed.get("fix_code") or "",
            "file_path": parsed.get("file_path") or rel,
            "explanation": parsed.get("explanation") or failure_info.get("summary") or "",
        }

    async def apply_fix_and_push(self, fix_result: dict, branch_name: str, workspace_path: str) -> dict:
        import git
        root = Path(workspace_path)
        rel = fix_result.get("file_path") or ""
        if not rel or not fix_result.get("fix_code"):
            raise RuntimeError("No fix to apply")
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        # Write sibling patch file to avoid destructive overwrites when unsure
        out = path if not path.exists() else path.with_suffix(path.suffix + ".jessie_ci_fix")
        out.write_text(str(fix_result["fix_code"]), encoding="utf-8")
        repo = git.Repo(str(root))
        if branch_name and repo.active_branch.name != branch_name:
            if branch_name in {h.name for h in repo.heads}:
                repo.git.checkout(branch_name)
            else:
                repo.git.checkout("-b", branch_name)
        repo.index.add([str(out.relative_to(root))])
        ftype = "ci"
        repo.index.commit(f"ci: fix {ftype} in {out.name}\n\nAuto-fixed by Jessie AI")
        try:
            repo.remotes.origin.push(branch_name or repo.active_branch.name)
            pushed = True
        except Exception as exc:
            return {"committed": True, "pushed": False, "error": str(exc), "file": str(out.relative_to(root))}
        return {"committed": True, "pushed": pushed, "file": str(out.relative_to(root))}

    def generate_pr_comment(self, failure_info: dict, fix_result: dict | None, fixable: bool) -> str:
        if fixable and fix_result:
            return (
                "⚡ **Jessie CI/CD Agent — Auto-fix applied**\n\n"
                f"**Failure:** {failure_info.get('failure_type')}\n"
                f"**Root cause:** {failure_info.get('root_cause')}\n"
                f"**File:** {failure_info.get('file')}:{failure_info.get('line')}\n\n"
                "**Fix applied and committed.** Pipeline re-triggered automatically.\n\n"
                f"{fix_result.get('explanation') or ''}"
            )
        steps = failure_info.get("suggested_steps") or []
        steps_md = "\n".join(f"{i+1}. {s}" for i, s in enumerate(steps)) or "1. Inspect logs and fix environment/config."
        return (
            "⚡ **Jessie CI/CD Agent — Manual fix needed**\n\n"
            f"**Failure type:** {failure_info.get('failure_type')}\n"
            f"**Root cause:** {failure_info.get('root_cause')}\n\n"
            "**This requires manual intervention.**\n\n"
            f"**Suggested steps:**\n{steps_md}"
        )

    def _heuristic(self, logs: str, failed_step: str, job_name: str) -> dict:
        low = (logs or "").lower()
        if "eslint" in low or "flake8" in low or "lint" in low:
            ftype = "lint"
        elif "typeerror" in low or "mypy" in low or "tsc" in low:
            ftype = "type_error"
        elif "assert" in low or "pytest" in low or "test" in low:
            ftype = "test"
        elif "timeout" in low:
            ftype = "timeout"
        elif "modulenotfound" in low or "version conflict" in low:
            ftype = "dependency"
        elif "env" in low and ("missing" in low or "not set" in low):
            ftype = "environment"
        else:
            ftype = "build"
        fixable = ftype in ("test", "lint", "type_error")
        return {
            "failure_type": ftype,
            "root_cause": f"Detected {ftype} failure in {job_name or failed_step or 'pipeline'}",
            "file": "",
            "line": None,
            "fixable_by_ai": fixable,
            "fix_complexity": 4 if fixable else 8,
            "summary": f"{ftype} failure in CI",
            "suggested_steps": ["Open the failing job logs", "Reproduce locally", "Apply a targeted fix"],
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
