"""Jessie v3 — Documentation agent (docstrings, changelog, env example)."""

from __future__ import annotations

import re
from datetime import date
from pathlib import Path
from typing import Optional

from gateway.model_router import ModelRouter


class DocumentationAgent:
    async def find_missing_docs(self, diff: str, workspace_path: str) -> list[dict]:
        findings = []
        root = Path(workspace_path)
        # New env vars in diff
        for m in re.finditer(r"(?:os\.getenv|process\.env\.|ENV\[)[(\"']([A-Z0-9_]+)", diff or ""):
            findings.append({"type": "env_var", "file": ".env.example", "line": 0, "description": f"New env var {m.group(1)}"})
        # Python defs without following docstring in changed hunks
        for m in re.finditer(r"^\+\s*def\s+(\w+)\(", diff or "", re.M):
            findings.append({"type": "docstring", "file": "", "line": 0, "description": f"New function {m.group(1)} may need docstring"})
        # Changelog presence
        if "CHANGELOG" not in (diff or "") and ("feature" in (diff or "").lower() or "fix" in (diff or "").lower()):
            if not (root / "CHANGELOG.md").exists():
                findings.append({"type": "changelog", "file": "CHANGELOG.md", "line": 0, "description": "CHANGELOG.md missing"})
        return findings

    async def generate_docstring(self, function_code: str, language: str, claude_api_key: str) -> str:
        if not claude_api_key:
            return '"""TODO: document this function."""'
        router = ModelRouter(api_key=claude_api_key)
        style = "Google style" if language == "python" else "JSDoc"
        result = await router.call_claude(
            prompt=f"Write a {style} docstring for:\n\n{function_code[:4000]}\n\nReturn only the docstring text.",
            complexity_score=2,
            system_prompt="Return only the docstring, no fences.",
        )
        return (result.get("response") or "").strip()

    async def update_changelog(self, ticket: dict, fix_result: dict, workspace_path: str) -> str:
        path = Path(workspace_path) / "CHANGELOG.md"
        entry = f"- {ticket.get('title')} ({ticket.get('id')}) — {fix_result.get('explanation') or 'Jessie AI fix'}\n"
        if path.exists():
            text = path.read_text(encoding="utf-8")
            if "## [Unreleased]" in text:
                text = text.replace("## [Unreleased]", f"## [Unreleased]\n### Fixed\n{entry}", 1)
            else:
                text = f"## [Unreleased]\n### Fixed\n{entry}\n" + text
        else:
            text = f"# Changelog\n\n## [Unreleased]\n### Fixed\n{entry}"
        path.write_text(text, encoding="utf-8")
        return str(path)

    async def update_readme(self, ticket: dict, workspace_path: str) -> str:
        if (ticket.get("label") or "") == "bug":
            return ""
        path = Path(workspace_path) / "README.md"
        if not path.exists():
            return ""
        text = path.read_text(encoding="utf-8")
        note = f"\n\n<!-- Jessie v3: {ticket.get('id')} — {ticket.get('title')} ({date.today().isoformat()}) -->\n"
        if note.strip() in text:
            return str(path)
        path.write_text(text.rstrip() + note, encoding="utf-8")
        return str(path)

    async def update_env_example(self, new_vars: list[str], workspace_path: str, descriptions: Optional[dict] = None) -> str:
        path = Path(workspace_path) / ".env.example"
        existing = path.read_text(encoding="utf-8") if path.exists() else ""
        lines = []
        for var in new_vars:
            if var in existing:
                continue
            desc = (descriptions or {}).get(var, "Set by Jessie Doc Agent")
            lines.append(f"# {desc}\n{var}=your_value_here\n")
        if not lines:
            return str(path)
        path.write_text((existing.rstrip() + "\n\n" if existing else "") + "\n".join(lines), encoding="utf-8")
        return str(path)
