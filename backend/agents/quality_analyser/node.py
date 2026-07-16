"""
Jessie — backend/agents/quality_analyser/node.py
Quality Analyser:
Scores Copilot's generated code 0-100 against a rubric.
Sets quality_score and quality_feedback.
The conditional edge in graph.py reads these to decide:
pass → memory_writer, retry → prompt_coach, max → END.
"""

from core.state import AgentState

RUBRIC = {
    "has_real_code":      20,
    "no_placeholders":    15,
    "has_error_handling": 15,
    "matches_language":   15,
    "correct_scope":      15,
    "has_explanation":    10,
    "no_full_file_dump":  10,
}

LANGUAGE_SIGNALS = {
    "python":     ["def ", "import ", "class ", "    "],
    "typescript": ["const ", "interface ", ": string", "=>", "React"],
    "java":       ["public ", "void ", "class ", "System."],
    "go":         ["func ", "package ", ":= ", "fmt."],
    "rust":       ["fn ", "let ", "impl ", "use "],
}

ERROR_HANDLING = {
    "python":     ["try:", "except", "raise"],
    "typescript": ["try {", "catch", "?."],
    "java":       ["try {", "catch (", "throws "],
    "go":         ["if err != nil", "return err"],
    "rust":       ["Result<", "Err(", "?"],
}


def quality_analyser_node(state: AgentState) -> AgentState:
    code     = state.get("generated_code", "")
    language = state.get("language", "unknown")
    retries  = state.get("retry_count", 0)
    status   = list(state.get("status_updates", []))

    # Component reuse always passes — no need to score
    if state.get("component_exists"):
        status.append("✅ Quality check — component reuse, score 100/100")
        return {**state, "quality_score": 100, "quality_feedback": "", "status_updates": status}

    status.append("🔎 Quality Analyser — checking Copilot output...")

    score, failures = 0, []

    if _has_real_code(code):
        score += RUBRIC["has_real_code"]
    else:
        failures.append("Response contains no actual code — only explanation text")

    if _no_placeholders(code):
        score += RUBRIC["no_placeholders"]
    else:
        failures.append("Code contains TODO, placeholder, or NotImplemented stubs")

    if _has_error_handling(code, language):
        score += RUBRIC["has_error_handling"]
    else:
        failures.append(f"Missing error handling for {language}")

    if _matches_language(code, language):
        score += RUBRIC["matches_language"]
    else:
        failures.append(f"Code does not appear to be valid {language}")

    if _correct_scope(code):
        score += RUBRIC["correct_scope"]
    else:
        failures.append("Response may have changed things outside the task scope")

    if _has_explanation(code):
        score += RUBRIC["has_explanation"]
    else:
        failures.append("No comment or explanation included with the code")

    if _no_full_file_dump(code):
        score += RUBRIC["no_full_file_dump"]
    else:
        failures.append("Response returned the entire file — should return only changed parts")

    feedback = "; ".join(failures)

    if score >= 70:
        status.append(f"✅ Quality score: {score}/100 — delivering")
    elif retries < 2:
        status.append(f"⚠️  Quality score: {score}/100 — retrying with feedback (attempt {retries+1}/2)")
    else:
        status.append(f"⚠️  Quality score: {score}/100 — max retries reached, delivering with warning")

    return {
        **state,
        "quality_score":    score,
        "quality_feedback": feedback,
        "retry_count":      retries + (1 if score < 70 else 0),
        "status_updates":   status,
    }


def _has_real_code(code: str) -> bool:
    indicators = ["def ", "class ", "function ", "const ", "var ", "let ",
                  "import ", "return ", "=>", "if ", "for ", "{"]
    return any(i in code for i in indicators)

def _no_placeholders(code: str) -> bool:
    bad = ["TODO", "FIXME", "placeholder", "raise NotImplementedError",
           "// implement", "/* TODO", "pass  #"]
    return not any(b.lower() in code.lower() for b in bad)

def _has_error_handling(code: str, language: str) -> bool:
    # Skip for trivial tasks
    if len(code) < 100:
        return True
    signals = ERROR_HANDLING.get(language, [])
    if not signals:
        return True
    return any(s in code for s in signals)

def _matches_language(code: str, language: str) -> bool:
    signals = LANGUAGE_SIGNALS.get(language, [])
    if not signals:
        return True
    return any(s in code for s in signals)

def _correct_scope(code: str) -> bool:
    return len(code) < 4000

def _has_explanation(code: str) -> bool:
    return any(c in code for c in ["#", "//", '"""', "/*", "<!--"])

def _no_full_file_dump(code: str) -> bool:
    return len(code.splitlines()) < 150
