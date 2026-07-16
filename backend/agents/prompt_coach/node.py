"""
Jessie — backend/agents/prompt_coach/node.py
Prompt Coach:
1. Score prompt quality
2. Classify complexity (1-10) → drives Copilot model selection
3. Auto-collect VS Code context (file, selected code, error)
4. Rewrite into precise, context-rich prompt
5. Build prompt_diff for developer approval in sidebar
6. Emit live status updates
"""

from core.state import AgentState
from agents.prompt_coach.templates import get_template
from memory.store import MemoryStore


def prompt_coach_node(state: AgentState) -> AgentState:
    prompt       = state.get("original_prompt", "").strip()
    language     = state.get("language", "unknown")
    open_file    = state.get("open_file_content", "")
    selected     = state.get("selected_code", "")
    error        = state.get("error_message", "")
    user_id      = state.get("user_id", "anonymous")
    retry_feedback = state.get("quality_feedback", "")

    status = list(state.get("status_updates", []))
    status.append("✍️  Prompt Coach — analysing your prompt...")

    # Classify complexity
    complexity = _classify_complexity(prompt)

    # Score prompt quality
    quality = _score_prompt(prompt)

    # Check user memory for their patterns
    memory = MemoryStore()
    user_patterns = memory.read_user(user_id, "prompt_patterns") or {}

    # If good prompt and not a retry — minimal rewrite
    if quality >= 7 and not retry_feedback:
        improved = _add_constraints(prompt, language, get_template(language))
        diff = ""
        status.append(f"✅ Prompt quality good ({quality}/10) — adding output constraints")
    else:
        improved = _rewrite(
            prompt, language, open_file, selected, error,
            retry_feedback, get_template(language)
        )
        diff = _build_diff(prompt, improved)
        status.append(f"✍️  Prompt rewritten (quality was {quality}/10) — awaiting your approval")

    return {
        **state,
        "improved_prompt":  improved,
        "prompt_diff":      diff,
        "complexity_score": complexity,
        "prompt_approved":  False,       # extension sets this to True after approval
        "status_updates":   status,
    }


# ── Complexity classifier ──────────────────────────────────────────────────

def _classify_complexity(prompt: str) -> int:
    """
    1-3  → trivial  → fast Copilot model
    4-7  → medium   → standard Copilot model
    8-10 → complex  → most capable Copilot model
    """
    p = prompt.lower()
    score = 3

    # Trivial signals
    if any(w in p for w in ["rename", "typo", "comment", "indent", "format", "spell"]):
        return 1
    if any(w in p for w in ["import", "variable", "semicolon", "bracket"]):
        return 2

    # Medium signals
    if any(w in p for w in ["function", "method", "class", "fix", "bug", "error"]):
        score = max(score, 4)
    if any(w in p for w in ["test", "api", "endpoint", "hook", "component"]):
        score = max(score, 5)
    if any(w in p for w in ["refactor", "optimise", "optimize", "debug", "async"]):
        score = max(score, 6)

    # Complex signals
    if any(w in p for w in ["architecture", "design", "system", "security", "auth"]):
        score = max(score, 8)
    if any(w in p for w in ["migrate", "rewrite", "entire", "all files", "database"]):
        score = max(score, 9)
    if any(w in p for w in ["scale", "performance audit", "cve", "penetration"]):
        score = max(score, 10)

    # Length as complexity signal
    if len(prompt) > 300:  score = max(score, 6)
    if len(prompt) > 700:  score = max(score, 8)

    return min(score, 10)


# ── Prompt quality scorer ──────────────────────────────────────────────────

def _score_prompt(prompt: str) -> int:
    import re
    score = 2
    p = prompt.lower()
    if len(prompt) > 40:   score += 1
    if len(prompt) > 100:  score += 1
    if any(w in p for w in ["function", "class", "file", "error", "return"]):  score += 1
    if any(w in p for w in ["should", "must", "expected", "only", "without"]):  score += 1
    if "```" in prompt:    score += 1
    if any(w in p for w in ["don't", "except", "not ", "avoid"]):  score += 1
    if re.search(r'\.\w{2,4}\b', prompt):  score += 1  # references a specific file (e.g. auth.py)
    return min(score, 10)


# ── Rewriter ───────────────────────────────────────────────────────────────

def _rewrite(prompt, language, open_file, selected, error, retry_feedback, template):
    parts = []

    if language and language != "unknown":
        parts.append(f"Language: {language}")

    if selected:
        parts.append(f"Developer has selected this code:\n```\n{selected[:600]}\n```")
    elif open_file:
        parts.append(f"Context from open file:\n```\n{open_file[:400]}\n```")

    if error:
        parts.append(f"Terminal error: {error}")

    parts.append(f"Task: {prompt}")

    if retry_feedback:
        parts.append(
            f"IMPORTANT — previous attempt failed because: {retry_feedback}. "
            f"Fix this exact issue in the new output."
        )

    parts.append(template)
    return "\n\n".join(parts)


def _add_constraints(prompt, language, template):
    return f"{prompt}\n\n{template}"


def _build_diff(original, improved):
    return (
        f"**Original:**\n{original}\n\n"
        f"**Jessie improved:**\n{improved}\n\n"
        f"*Added: language context, file context, output constraints, scope limits*"
    )
