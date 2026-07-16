"""
Jessie — backend/core/supervisor.py
First node on every request. Sets up state, detects language,
injects retry feedback into prompt on loop-back.
"""

import hashlib
from core.state import AgentState


def supervisor_node(state: AgentState) -> AgentState:
    updates = {}

    # Auto-generate workspace_id from folder path if missing
    if not state.get("workspace_id"):
        raw = state.get("open_file_content", "unknown")[:50]
        updates["workspace_id"] = hashlib.md5(raw.encode()).hexdigest()[:12]

    # Initialise counters on fresh request
    if "retry_count" not in state:
        updates["retry_count"] = 0
    if "status_updates" not in state:
        updates["status_updates"] = []

    # Detect language from file content
    if not state.get("language"):
        updates["language"] = _detect_language(state.get("open_file_content", ""))

    # Default complexity
    if not state.get("complexity_score"):
        updates["complexity_score"] = 5

    # On retry — inject failure feedback into original prompt
    if state.get("retry_count", 0) > 0 and state.get("quality_feedback"):
        updates["original_prompt"] = (
            f"{state['original_prompt']}\n\n"
            f"[Previous attempt failed: {state['quality_feedback']}. Fix this specifically.]"
        )

    # Add status update
    status = list(state.get("status_updates", []))
    status.append("🚀 Jessie started — analysing your request...")
    updates["status_updates"] = status

    return {**state, **updates}


def _detect_language(content: str) -> str:
    checks = {
        "typescript": ["import React", "useState", ": string", ": number", "interface "],
        "python":     ["def ", "import ", "class ", "print(", "async def"],
        "java":       ["public class", "void main", "System.out"],
        "go":         ["func ", "package ", ":= ", "fmt."],
        "rust":       ["fn ", "let mut", "impl ", "use std"],
        "css":        ["{", ":", "px", "rem", "rgba"],
    }
    for lang, signals in checks.items():
        if sum(1 for s in signals if s in content) >= 2:
            return lang
    return "unknown"
