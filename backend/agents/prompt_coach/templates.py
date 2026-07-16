"""
Jessie — backend/agents/prompt_coach/templates.py
Output constraint templates per language.
Appended to every improved prompt so Copilot knows
exactly what format and scope your team expects.
"""

TEMPLATES = {
    "python": (
        "Output requirements:\n"
        "- Return only the modified function or class — not the entire file\n"
        "- Follow PEP8 style\n"
        "- Add a docstring if none exists\n"
        "- Do not change logic outside the task scope\n"
        "- List any new imports separately at the top"
    ),
    "typescript": (
        "Output requirements:\n"
        "- Return only the modified component or function\n"
        "- Use TypeScript types — no 'any'\n"
        "- Functional components only — no class components\n"
        "- Do not change existing imports unless adding a new one\n"
        "- Export only what was already exported"
    ),
    "java": (
        "Output requirements:\n"
        "- Return only the modified method or class\n"
        "- Follow standard Java naming conventions\n"
        "- Add Javadoc comment if missing\n"
        "- Do not change access modifiers unless required by the task"
    ),
    "go": (
        "Output requirements:\n"
        "- Return only the modified function\n"
        "- Handle all errors explicitly — no panic\n"
        "- Follow Go idioms and naming conventions\n"
        "- Add godoc comment if missing"
    ),
    "rust": (
        "Output requirements:\n"
        "- Return only the modified function\n"
        "- No unwrap() — handle Results and Options properly\n"
        "- Follow Rust naming conventions\n"
        "- Minimise unnecessary clones"
    ),
    "unknown": (
        "Output requirements:\n"
        "- Return only the code that needs to change\n"
        "- Keep the same style as the surrounding code\n"
        "- Add a brief comment explaining what changed and why"
    ),
}


def get_template(language: str) -> str:
    return TEMPLATES.get(language, TEMPLATES["unknown"])
