"""
Jessie — backend/agents/memory_writer/node.py
Memory Writer — only runs when quality gate passes (score >= 70).
1. Detect if a new component was created → save to project memory
2. Save successful prompt pattern → user memory
3. Build final_response for the VS Code sidebar
"""

import re
from core.state import AgentState
from memory.store import MemoryStore


def memory_writer_node(state: AgentState) -> AgentState:
    code         = state.get("generated_code", "")
    prompt       = state.get("improved_prompt", state.get("original_prompt", ""))
    workspace_id = state.get("workspace_id", "")
    user_id      = state.get("user_id", "anonymous")
    team_id      = state.get("team_id", "default") or "default"
    language     = state.get("language", "unknown")
    quality      = state.get("quality_score", 0)
    model        = state.get("model_used", "copilot")
    req_count    = state.get("request_count", 0)
    status       = list(state.get("status_updates", []))

    memory       = MemoryStore()
    memory_saved = False
    memory_note  = ""

    # ── Save new component to project memory ──────────────────────────────
    if not state.get("component_exists"):
        component_name = _detect_new_component(code, language)
        if component_name:
            path  = _guess_path(component_name, language)
            usage = _extract_usage(code, component_name)
            memory.write_project(
                workspace_id=workspace_id,
                topic=f"component:{component_name.lower()}",
                value={
                    "name":       component_name,
                    "path":       path,
                    "language":   language,
                    "usage":      usage,
                    "created_by": user_id,
                },
                team_id=team_id,
            )
            memory_saved = True
            memory_note  = (
                f"✅ Saved '{component_name}' to project memory. "
                f"Next time anyone asks for this, Jessie will reuse it automatically."
            )
            status.append(f"💾 Memory — saved new component: {component_name}")

    # ── Save successful prompt to user memory ─────────────────────────────
    memory.write_user(
        user_id=user_id,
        topic="last_successful_prompt",
        value={"prompt": prompt, "language": language, "quality": quality, "model": model},
        team_id=team_id,
    )

    # ── Log request count ─────────────────────────────────────────────────
    memory.increment_request_count(user_id, team_id=team_id)
    new_count = memory.get_request_count(user_id, team_id=team_id)

    # ── Build final response ──────────────────────────────────────────────
    warning = ""
    if quality < 70:
        warning = "\n\n⚠️  Note: This output scored below Jessie's quality threshold after 2 retries. Review carefully."

    final_response = f"{code}{warning}"
    status.append("🎉 Done — result delivered")

    return {
        **state,
        "final_response": final_response,
        "memory_saved":   memory_saved,
        "memory_note":    memory_note,
        "request_count":  new_count,
        "status_updates": status,
    }


def _detect_new_component(code: str, language: str) -> str:
    if language in ("typescript", "javascript"):
        m = re.search(r'(?:export\s+(?:default\s+)?(?:function|const))\s+([A-Z][a-zA-Z]+)', code)
        if m:
            return m.group(1)
    if language == "python":
        m = re.search(r'class\s+([A-Z][a-zA-Z]+)', code)
        if m:
            return m.group(1)
    return ""


def _guess_path(name: str, language: str) -> str:
    ext = {"typescript": "tsx", "javascript": "jsx", "python": "py"}.get(language, "txt")
    return f"components/{name}.{ext}"


def _extract_usage(code: str, name: str) -> str:
    for line in code.split("\n"):
        if name in line and "export" not in line and len(line) < 80:
            return line.strip()
    return f"<{name} />"
