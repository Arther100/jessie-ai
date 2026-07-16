"""
Jessie — backend/core/graph.py
The LangGraph StateGraph. Jessie's brain.
Correct architecture: Copilot Caller node (no external API key).
Supervisor → Prompt Coach → RAG Injector → [back to extension for Copilot call]
→ Quality Analyser → Memory Writer
"""

from langgraph.graph import StateGraph, END
from core.state import AgentState
from core.supervisor import supervisor_node
from agents.prompt_coach.node import prompt_coach_node
from agents.rag_injector.node import rag_injector_node
from agents.quality_analyser.node import quality_analyser_node
from agents.memory_writer.node import memory_writer_node


# ── Conditional edge functions ─────────────────────────────────────────────

def should_run_rag(state: AgentState) -> str:
    """
    Skip RAG for trivial tasks (complexity 1-2).
    A typo fix doesn't need codebase context.
    """
    if state.get("complexity_score", 5) <= 2:
        return "skip_rag"
    return "run_rag"


def quality_gate(state: AgentState) -> str:
    """
    Core retry loop.
    Pass → memory writer → deliver.
    Fail → back to prompt coach with feedback (max 2 retries).
    Max retries hit → deliver with warning.
    """
    score   = state.get("quality_score", 0)
    retries = state.get("retry_count", 0)

    if state.get("component_exists"):
        return "pass"                    # component reuse always passes
    if score >= 70:
        return "pass"
    elif retries < 2:
        return "retry"
    else:
        return "max_retries"


# ── Build the graph ────────────────────────────────────────────────────────

def build_jessie_graph():
    graph = StateGraph(AgentState)

    # Register nodes
    graph.add_node("supervisor",       supervisor_node)
    graph.add_node("prompt_coach",     prompt_coach_node)
    graph.add_node("rag_injector",     rag_injector_node)
    graph.add_node("quality_analyser", quality_analyser_node)
    graph.add_node("memory_writer",    memory_writer_node)

    # Entry
    graph.set_entry_point("supervisor")

    # Supervisor → Prompt Coach always
    graph.add_edge("supervisor", "prompt_coach")

    # Prompt Coach → RAG (skip if trivial task)
    graph.add_conditional_edges(
        "prompt_coach",
        should_run_rag,
        {
            "run_rag":  "rag_injector",
            "skip_rag": "quality_analyser",  # goes straight to quality after copilot
        }
    )

    # RAG → pause here. Extension calls Copilot, then POSTs result back
    # via /resume endpoint. Graph receives generated_code in state.
    graph.add_edge("rag_injector", "quality_analyser")

    # Quality gate
    graph.add_conditional_edges(
        "quality_analyser",
        quality_gate,
        {
            "pass":        "memory_writer",
            "retry":       "prompt_coach",    # loop back with feedback
            "max_retries": END,               # deliver with warning
        }
    )

    graph.add_edge("memory_writer", END)

    return graph.compile()


jessie_graph = build_jessie_graph()
