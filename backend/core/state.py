"""
Jessie — backend/core/state.py
Single shared state object that flows through every LangGraph node.
Each node reads from it, does its job, writes back to it.
"""

from typing import TypedDict, List, Optional, NotRequired


class AgentState(TypedDict):
    # ── INPUT (set when request arrives from VS Code extension) ───────────
    original_prompt:    str       # raw developer prompt
    user_id:            str       # developer identifier
    workspace_id:       str       # hash of workspace folder path — project isolation key
    language:           str       # detected from open file
    open_file_content:  str       # currently open file in VS Code
    selected_code:      str       # highlighted code if any
    error_message:      str       # terminal error if any
    complexity_score:   int       # 1-10, set by prompt coach, used by copilot caller

    # ── PROMPT COACH outputs ──────────────────────────────────────────────
    improved_prompt:    str       # rewritten precise prompt
    prompt_diff:        str       # original vs improved — shown in sidebar
    prompt_approved:    bool      # did developer approve the rewrite?

    # ── RAG INJECTOR outputs ──────────────────────────────────────────────
    context_chunks:     List[str] # relevant file snippets from codebase
    component_exists:   bool      # found existing component?
    component_path:     str       # path to existing component if found
    component_usage:    str       # how to use the existing component

    # ── COPILOT CALLER outputs ────────────────────────────────────────────
    generated_code:     str       # raw Copilot output
    model_used:         str       # which Copilot model family was requested

    # ── QUALITY ANALYSER outputs ──────────────────────────────────────────
    quality_score:      int       # 0-100
    quality_feedback:   str       # what failed — fed back to prompt coach on retry
    retry_count:        int       # how many retry loops so far (max 2)

    # ── MEMORY WRITER outputs ─────────────────────────────────────────────
    memory_saved:       bool      # did we save something to memory?
    memory_note:        str       # what was saved — shown in sidebar

    # ── CODE REVIEW ───────────────────────────────────────────────────────
    review_triggered:   bool      # True when a full project review is requested
    review_target_path: str       # absolute path to project folder being reviewed
    review_results:     dict      # raw per-layer results from CodeReviewAgent
    review_report_path: str       # path to the generated .md report

    # ── FINAL OUTPUT (returned to VS Code extension) ──────────────────────
    final_response:     str       # cleaned code + explanation
    status_updates:     List[str] # live progress messages for sidebar/status bar
    request_count:      int       # this user's request count today

    # ── JESSIE v3 TICKET AGENT (optional / NotRequired for v1-v2 compat) ──
    ticket_id:          NotRequired[str]
    ticket_platform:    NotRequired[str]
    ticket_data:        NotRequired[dict]
    ticket_complexity:  NotRequired[int]
    fix_code:           NotRequired[str]
    fix_test:           NotRequired[str]
    branch_name:        NotRequired[str]
    pr_number:          NotRequired[int]
    pr_url:             NotRequired[str]
    ticket_updated:     NotRequired[bool]
    ticket_mode:        NotRequired[bool]
    claude_api_key:     NotRequired[str]  # request-scoped only; never persist
    team_id:            NotRequired[str]  # sha256(api_key)[:16]
    ai_provider:        NotRequired[str]  # anthropic|openai|gemini
