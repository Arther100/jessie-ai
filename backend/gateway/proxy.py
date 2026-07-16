"""
Jessie — backend/gateway/proxy.py
Main gateway orchestrator — the invisible middleware layer.

process_request() is an async generator.  Every layer yields a status dict
that the /proxy SSE endpoint forwards to the VS Code extension in real time.
The final yield is always a "result" or "error" dict.

Layer order:
  1. Quota     — block if user's daily limit is exhausted
  2. Cache     — return instantly if a semantically similar prompt was seen
  3. Prepare   — run Jessie's LangGraph nodes (Prompt Coach + RAG Injector)
  4. Queue     — wait for a concurrency slot (max 5 simultaneous Claude calls)
  5. Claude    — call the right model tier via ModelRouter
  6. Quality   — run Quality Analyser + Memory Writer nodes (auto retry ×2)
  7. Cache write — store result for future cache hits

Failure policy (every layer):
  - Non-fatal errors are caught and logged; the pipeline continues
    with the best available data (graceful degradation).
  - Fatal errors (quota exceeded, queue timeout, API error) yield an
    "error" event and return immediately.
  - The developer ALWAYS gets a response — Jessie never blocks Claude Code.
"""

import asyncio
import logging
from typing import AsyncGenerator

from gateway.semantic_cache import SemanticCache
from gateway.quota import QuotaManager, QuotaExceeded
from gateway.queue import JessieQueue, QueueTimeout
from gateway.model_router import ModelRouter

from core.supervisor import supervisor_node
from core.state import AgentState
from agents.prompt_coach.node import prompt_coach_node
from agents.rag_injector.node import rag_injector_node
from agents.quality_analyser.node import quality_analyser_node
from agents.memory_writer.node import memory_writer_node

logger = logging.getLogger(__name__)

# Singleton queue — shared across all concurrent requests
_queue = JessieQueue()


# ── SSE event builders ─────────────────────────────────────────────────────

def _status(message: str) -> dict:
    return {"type": "status", "message": message}


def _result(
    response:      str,
    model:         str,
    cache_hit:     bool,
    quality_score: int,
    tokens_saved:  int,
    cost_estimate: float = 0.0,
    memory_note:   str   = "",
) -> dict:
    return {
        "type":          "result",
        "response":      response,
        "model":         model,
        "cache_hit":     cache_hit,
        "quality_score": quality_score,
        "tokens_saved":  tokens_saved,
        "cost_estimate": cost_estimate,
        "memory_note":   memory_note,
    }


def _error(message: str, code: str = "error") -> dict:
    return {"type": "error", "code": code, "message": message}


# ── Initial state builder ──────────────────────────────────────────────────

def _make_state(
    prompt:            str,
    user_id:           str,
    workspace_id:      str,
    language:          str,
    open_file_content: str,
    selected_code:     str,
    error_message:     str,
) -> AgentState:
    return {
        "original_prompt":   prompt,
        "user_id":           user_id,
        "workspace_id":      workspace_id,
        "language":          language,
        "open_file_content": open_file_content,
        "selected_code":     selected_code,
        "error_message":     error_message,
        "improved_prompt":   "",
        "prompt_diff":       "",
        "prompt_approved":   True,   # auto-approved in gateway mode
        "context_chunks":    [],
        "component_exists":  False,
        "component_path":    "",
        "component_usage":   "",
        "generated_code":    "",
        "model_used":        "",
        "complexity_score":  5,
        "quality_score":     0,
        "quality_feedback":  "",
        "retry_count":       0,
        "memory_saved":      False,
        "memory_note":       "",
        "final_response":    "",
        "status_updates":    [],
        "request_count":     0,
    }


# ── Main gateway pipeline ──────────────────────────────────────────────────

async def process_request(
    prompt:            str,
    user_id:           str,
    workspace_id:      str,
    language:          str = "",
    open_file_content: str = "",
    selected_code:     str = "",
    error_message:     str = "",
    priority:          int = 0,
) -> AsyncGenerator[dict, None]:
    """
    Async generator — yields status dicts, then one final result/error dict.

    The FastAPI /proxy endpoint iterates this and forwards each event as an
    SSE frame so the VS Code extension can update the status bar in real time.

    Args:
        prompt:            Raw developer prompt from Claude Code chat.
        user_id:           From jessie.userId VS Code setting.
        workspace_id:      MD5 hash of workspace folder path (project isolation).
        language:          Language ID of the active editor file.
        open_file_content: First 3 000 chars of the active file.
        selected_code:     Highlighted text in the editor, if any.
        error_message:     Terminal error text, if any.
        priority:          0=normal, 1=senior dev (skips queue ahead of 0).
    """

    # ── Layer 1: Quota ──────────────────────────────────────────────────────
    yield _status("$(loading~spin) Jessie — checking quota...")
    quota = None
    try:
        quota = QuotaManager(user_id=user_id, workspace_id=workspace_id)
        if not quota.is_allowed():
            yield _error(
                f"Daily request limit reached for '{user_id}' "
                f"({quota.remaining()} remaining). Resets at midnight UTC.",
                code="quota_exceeded",
            )
            return
    except QuotaExceeded as exc:
        yield _error(str(exc), code="quota_exceeded")
        return
    except Exception as exc:
        logger.warning(f"Quota check failed — allowing through: {exc}")

    # ── Layer 2: Semantic Cache ─────────────────────────────────────────────
    yield _status("$(loading~spin) Jessie — checking cache...")
    cache = None
    try:
        cache = SemanticCache(workspace_id=workspace_id)
        cached = cache.search_similar(prompt)
        if cached is not None:
            saved = len(prompt) // 4 + len(cached) // 4
            yield _status(
                f"$(sparkle) Jessie — cache hit! saved ~{saved} tokens"
            )
            yield _result(
                response=cached,
                model="cache",
                cache_hit=True,
                quality_score=100,
                tokens_saved=saved,
            )
            return
    except Exception as exc:
        logger.warning(f"Cache lookup failed — continuing: {exc}")

    # ── Layer 3: LangGraph Prepare (Prompt Coach + RAG Injector) ───────────
    yield _status("$(loading~spin) Jessie — coaching prompt...")
    state = _make_state(
        prompt, user_id, workspace_id,
        language, open_file_content, selected_code, error_message,
    )

    try:
        state = supervisor_node(state)
        state = prompt_coach_node(state)

        if state.get("complexity_score", 5) > 2:
            yield _status(
                "$(loading~spin) Jessie — scanning codebase for context..."
            )
            state = rag_injector_node(state)

        # Forward any status updates from the nodes
        for msg in state.get("status_updates", []):
            yield _status(msg)

        # Component reuse — skip Claude entirely
        if state.get("component_exists"):
            reuse_code = state.get("generated_code", "")
            tokens_saved = len(reuse_code) // 4
            yield _status(
                f"$(sparkle) Jessie — reusing existing component "
                f"(saved ~{tokens_saved} tokens)"
            )
            yield _result(
                response=reuse_code,
                model="project-memory",
                cache_hit=False,
                quality_score=100,
                tokens_saved=tokens_saved,
            )
            return

    except Exception as exc:
        logger.error(f"LangGraph prepare failed — using raw prompt: {exc}")
        yield _status(
            "$(warning) Jessie — prompt coaching failed, using raw prompt"
        )
        state["improved_prompt"]  = prompt
        state["complexity_score"] = 5
        state["context_chunks"]   = []

    improved_prompt  = state.get("improved_prompt", prompt) or prompt
    complexity       = state.get("complexity_score", 5)
    context_chunks   = state.get("context_chunks", [])
    tier_label       = (
        "Haiku"  if complexity <= 3 else
        "Sonnet" if complexity <= 7 else
        "Opus"
    )

    # ── Layer 4 + 5: Queue + Claude API call ────────────────────────────────
    queue_status = _queue.get_queue_status()
    if queue_status["waiting"] > 0:
        pos  = queue_status["waiting"] + 1
        wait = _queue.estimated_wait_seconds()
        yield _status(
            f"$(loading~spin) Jessie — position {pos} in queue "
            f"(~{wait}s wait)..."
        )

    yield _status(
        f"$(loading~spin) Jessie — calling Claude "
        f"({tier_label}, complexity {complexity}/10)..."
    )

    router = None
    claude_result = None
    total_cost = 0.0

    try:
        router = ModelRouter()

        async def _call_claude():
            return await router.call_claude(
                prompt=improved_prompt,
                complexity_score=complexity,
                context_chunks=context_chunks,
            )

        claude_result = await _queue.enqueue(
            request_fn=_call_claude,
            user_id=user_id,
            priority=priority,
        )
        total_cost += claude_result.get("cost_estimate", 0.0)

    except QueueTimeout:
        yield _error(
            "Request timed out waiting in queue (5-minute limit). "
            "Try again or ask your team lead for priority access.",
            code="queue_timeout",
        )
        return
    except Exception as exc:
        logger.error(f"Claude API call failed: {exc}")
        yield _error(f"Claude API error: {exc}", code="api_error")
        return

    generated_code = claude_result["response"]
    model_used     = claude_result["model"]
    tokens_in      = claude_result.get("tokens_in", 0)

    # ── Layer 6: Quality Analyser + Memory Writer (auto retry ×2) ──────────
    yield _status("$(loading~spin) Jessie — quality checking output...")

    state["generated_code"] = generated_code
    state["model_used"]     = model_used
    final_response          = generated_code
    quality_score           = 0

    for attempt in range(3):
        try:
            state        = quality_analyser_node(state)
            quality_score = state.get("quality_score", 0)

            if quality_score >= 70 or attempt >= 2:
                # Pass — run memory writer and exit loop
                state          = memory_writer_node(state)
                final_response = state.get("final_response", generated_code)
                break

            # Below threshold — retry with failure feedback
            feedback = state.get("quality_feedback", "low quality output")
            yield _status(
                f"$(loading~spin) Jessie — quality {quality_score}/100, "
                f"retrying ({attempt + 1}/2)..."
            )
            retry_prompt = (
                f"{improved_prompt}\n\n"
                f"[Fix required: {feedback}. "
                f"Previous attempt scored {quality_score}/100.]"
            )
            try:
                async def _retry():
                    return await router.call_claude(
                        prompt=retry_prompt,
                        complexity_score=complexity,
                        context_chunks=context_chunks,
                    )

                retry_result = await _queue.enqueue(
                    request_fn=_retry,
                    user_id=user_id,
                    priority=priority,
                )
                generated_code          = retry_result["response"]
                total_cost             += retry_result.get("cost_estimate", 0.0)
                state["generated_code"] = generated_code
                state["retry_count"]    = attempt + 1

            except Exception as exc:
                logger.warning(f"Retry Claude call failed: {exc}")
                break  # use what we have

        except Exception as exc:
            logger.error(f"Quality check failed (non-fatal): {exc}")
            final_response = generated_code
            quality_score  = 0
            break

    # ── Layer 7: Store in semantic cache ────────────────────────────────────
    if cache is not None:
        try:
            cache.embed_and_store(
                prompt=prompt,
                response=final_response,
                user_id=user_id,
                workspace_id=workspace_id,
            )
        except Exception as exc:
            logger.warning(f"Cache write failed (non-fatal): {exc}")

    # Consume quota only after a successful real Claude call
    if quota is not None:
        try:
            quota.consume()
        except Exception as exc:
            logger.warning(f"Quota consume failed (non-fatal): {exc}")

    # Final status bar message
    suffix = (
        f"score: {quality_score}/100, model: {tier_label}, "
        f"cost: ${total_cost:.4f}"
    )
    yield _status(f"$(sparkle) Jessie — done ({suffix})")

    memory_note = state.get("memory_note", "")
    yield _result(
        response=final_response,
        model=model_used,
        cache_hit=False,
        quality_score=quality_score,
        tokens_saved=tokens_in,
        cost_estimate=round(total_cost, 5),
        memory_note=memory_note,
    )
