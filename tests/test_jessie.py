"""
Jessie — tests/test_jessie.py
Core tests. Run: pytest tests/ -v
"""
import sys
sys.path.insert(0, 'backend')

import pytest
from agents.prompt_coach.node import _classify_complexity, _score_prompt
from agents.quality_analyser.node import quality_analyser_node
from memory.store import MemoryStore


# ── Prompt Coach tests ─────────────────────────────────────────────────────

def test_trivial_complexity():
    assert _classify_complexity("rename variable x to user_count") <= 2

def test_complex_complexity():
    assert _classify_complexity("redesign the entire authentication system with OAuth") >= 8

def test_vague_prompt_scores_low():
    assert _score_prompt("fix") < 5

def test_detailed_prompt_scores_high():
    p = "In auth.py, the login function raises a KeyError when email is missing. Fix the validation only."
    assert _score_prompt(p) >= 6


# ── Quality Analyser tests ─────────────────────────────────────────────────

BASE = {
    "original_prompt": "fix login", "improved_prompt": "fix login",
    "user_id": "test", "workspace_id": "ws_test",
    "language": "python", "open_file_content": "",
    "selected_code": "", "error_message": "",
    "complexity_score": 4, "context_chunks": [],
    "component_exists": False, "component_path": "",
    "component_usage": "", "model_used": "copilot",
    "prompt_diff": "", "prompt_approved": True,
    "quality_score": 0, "quality_feedback": "",
    "retry_count": 0, "memory_saved": False,
    "memory_note": "", "final_response": "",
    "status_updates": [], "request_count": 0,
}

def test_empty_code_scores_low():
    state = {**BASE, "generated_code": ""}
    result = quality_analyser_node(state)
    assert result["quality_score"] < 70

def test_good_python_scores_high():
    code = '''
def login(email: str, password: str) -> dict:
    """Authenticate user and return token."""
    try:
        user = db.get_user(email)
        if not user:
            raise ValueError("User not found")
        token = generate_token(user.id)
        return {"token": token}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
'''
    state = {**BASE, "generated_code": code}
    result = quality_analyser_node(state)
    assert result["quality_score"] >= 70

def test_component_reuse_always_passes():
    state = {**BASE, "generated_code": "import Button", "component_exists": True}
    result = quality_analyser_node(state)
    assert result["quality_score"] == 100


# ── Memory isolation tests ─────────────────────────────────────────────────

def test_project_memory_isolation():
    """Workspace A data must not appear in workspace B."""
    store = MemoryStore()
    store.write_project("ws_A", "component:button", {"path": "Button.tsx"})

    assert store.read_project("ws_A", "component:button") is not None
    assert store.read_project("ws_B", "component:button") is None

def test_memory_fallback_order():
    """Project > User > Team — most specific wins."""
    store = MemoryStore()
    store.write_team("rules", {"level": "team"})
    store.write_user("user_1", "rules", {"level": "user"})
    store.write_project("ws_1", "rules", {"level": "project"})

    result = store.read_with_fallback("ws_1", "user_1", "rules")
    assert result["level"] == "project"

    result2 = store.read_with_fallback("ws_unknown", "user_1", "rules")
    assert result2["level"] == "user"

    result3 = store.read_with_fallback("ws_unknown", "user_unknown", "rules")
    assert result3["level"] == "team"

def test_request_count():
    store = MemoryStore()
    store.increment_request_count("test_user_count")
    store.increment_request_count("test_user_count")
    assert store.get_request_count("test_user_count") >= 2
