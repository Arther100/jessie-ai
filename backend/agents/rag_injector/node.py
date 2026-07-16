"""
Jessie — backend/agents/rag_injector/node.py
RAG Injector:
1. Check project memory — does this component already exist?
   YES → return reuse instruction, skip Copilot call entirely
   NO  → semantic search codebase, inject relevant file chunks
2. Fully scoped to workspace_id — zero cross-project leakage
"""

import re
from core.state import AgentState
from memory.store import MemoryStore
from agents.rag_injector.indexer import CodebaseIndexer


def rag_injector_node(state: AgentState) -> AgentState:
    prompt       = state.get("improved_prompt", state.get("original_prompt", ""))
    workspace_id = state.get("workspace_id", "")
    open_file    = state.get("open_file_content", "")
    user_id      = state.get("user_id", "anonymous")

    status = list(state.get("status_updates", []))
    status.append("🔍 RAG Injector — checking project memory...")

    memory  = MemoryStore()
    indexer = CodebaseIndexer(workspace_id=workspace_id)

    # ── Step 1: Check if component already exists in THIS project ─────────
    component_name = _extract_component_name(prompt)

    if component_name:
        existing = memory.read_project(
            workspace_id=workspace_id,
            topic=f"component:{component_name.lower()}",
        )
        if existing:
            status.append(
                f"♻️  Found existing component: {component_name} "
                f"at {existing.get('path', '?')} — reusing, skipping Copilot"
            )
            return {
                **state,
                "component_exists": True,
                "component_path":   existing.get("path", ""),
                "component_usage":  existing.get("usage", ""),
                "context_chunks":   [],
                "generated_code":   _reuse_message(component_name, existing),
                "status_updates":   status,
            }

    # ── Step 2: Semantic search for relevant codebase files ───────────────
    status.append("📂 RAG Injector — scanning codebase for context...")
    indexer.build_if_stale()

    query  = f"{prompt}\n{open_file[:200]}"
    chunks = indexer.search(query=query, top_k=4)

    formatted = []
    for chunk in chunks:
        formatted.append(f"--- {chunk['file']} ---\n{chunk['content']}")

    if formatted:
        status.append(f"📎 Injected {len(formatted)} relevant file(s) as context")
    else:
        status.append("📂 No existing context found — Copilot will generate fresh")

    return {
        **state,
        "component_exists": False,
        "component_path":   "",
        "component_usage":  "",
        "context_chunks":   formatted,
        "status_updates":   status,
    }


def _extract_component_name(prompt: str) -> str:
    """Extract a likely component name from the prompt."""
    # PascalCase words — likely React/TS components
    matches = re.findall(
        r'\b([A-Z][a-zA-Z]+'
        r'(?:Card|Button|Modal|Form|List|Table|Nav|Header|Footer'
        r'|Input|Select|Dropdown|Badge|Alert|Toast|Panel|Widget)?)\b',
        prompt
    )
    if matches:
        return matches[0]

    # "a X component" pattern
    match = re.search(r'\ba\s+(\w+)\s+component', prompt, re.IGNORECASE)
    if match:
        return match.group(1).capitalize()

    # "create/add X" pattern
    match = re.search(r'\b(?:create|add|make|build)\s+(?:a\s+)?(\w+)', prompt, re.IGNORECASE)
    if match:
        name = match.group(1).capitalize()
        if len(name) > 3:
            return name

    return ""


def _reuse_message(name: str, existing: dict) -> str:
    path  = existing.get("path", "unknown")
    usage = existing.get("usage", f"<{name} />")
    return (
        f"// ✅ Jessie found existing component — no need to recreate\n\n"
        f"// Component: {name}\n"
        f"// Location:  {path}\n\n"
        f"// Import it:\n"
        f"import {{ {name} }} from '{path.replace('.tsx', '').replace('.ts', '')}';\n\n"
        f"// Use it:\n"
        f"{usage}"
    )
