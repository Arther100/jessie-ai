"""
Jessie — backend/gateway/model_router.py
Direct Claude API caller with automatic model tier selection and prompt caching.

Replaces the vscode.lm / Copilot call for the gateway (Claude Code) flow.
Prefer a per-user Anthropic API key from Settings / request body.
Falls back to ANTHROPIC_API_KEY in backend/.jessie/.env only when no user
key is supplied (gateway demos). Code Review and Merge Review require a
user key.

Model tiers (driven by complexity_score from Prompt Coach):
  Tier 1  complexity 1–3   claude-haiku-4-5-20251001   fast, cheap
  Tier 2  complexity 4–7   claude-sonnet-4-6            standard
  Tier 3  complexity 8–10  claude-opus-4-8              most capable

Prompt caching (Anthropic beta):
  - System prompt always gets cache_control=ephemeral (saves ~90% on repeats)
  - Context chunks > 1024 tokens also get cache_control=ephemeral
  - cache_read_input_tokens in usage signals a cache hit

Cost estimates ($/1k tokens, input / output):
  Haiku:  $0.00025 / $0.00125
  Sonnet: $0.003   / $0.015
  Opus:   $0.015   / $0.075
"""

import os
import logging
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv

load_dotenv(Path(".jessie/.env"))

logger = logging.getLogger(__name__)

# ── Model registry ─────────────────────────────────────────────────────────

MODELS = {
    "tier1": "claude-haiku-4-5-20251001",
    "tier2": "claude-sonnet-4-6",
    "tier3": "claude-opus-4-8",
}

COST_INPUT_PER_1K = {
    "tier1": 0.00025,
    "tier2": 0.003,
    "tier3": 0.015,
}

COST_OUTPUT_PER_1K = {
    "tier1": 0.00125,
    "tier2": 0.015,
    "tier3": 0.075,
}

TIER_LABELS = {
    "tier1": "Haiku",
    "tier2": "Sonnet",
    "tier3": "Opus",
}

DEFAULT_SYSTEM = (
    "You are an expert software engineer embedded inside a developer's IDE. "
    "Write clean, production-ready code with proper error handling. "
    "Include brief inline comments for non-obvious logic only. "
    "Return only the code or explanation that was asked for — "
    "do not dump the entire file unless explicitly requested. "
    "Match the language, style, and framework already present in any provided context."
)

# Rough estimate: 1 token ≈ 4 characters
_CHARS_PER_TOKEN = 4
_CACHE_TOKEN_THRESHOLD = 1024


class ModelRouter:
    """
    Routes each request to the right Claude model tier and applies
    Anthropic prompt caching to minimise cost on repeated context.

    Prefer a per-user `api_key` (from Settings / request body).
    Falls back to ANTHROPIC_API_KEY in backend/.jessie/.env only when
    no user key is provided (e.g. shared gateway demos).
    """

    def __init__(self, api_key: Optional[str] = None):
        key = (api_key or "").strip() or (os.getenv("ANTHROPIC_API_KEY") or "").strip()
        if not key:
            raise ValueError(
                "Claude API key is required.\n"
                "Add your Anthropic key in Jessie Settings (web) or Jessie: Settings (extension),\n"
                "or set ANTHROPIC_API_KEY in backend/.jessie/.env for a shared server key."
            )
        if not key.startswith("sk-ant-") and not key.startswith("sk-"):
            logger.warning("Claude API key does not look like a standard Anthropic key (sk-ant-...)")
        try:
            import anthropic as _anthropic
            self._client = _anthropic.AsyncAnthropic(api_key=key)
            self._anthropic = _anthropic
        except ImportError:
            raise ImportError(
                "anthropic package not installed.\n"
                "Run: pip install anthropic"
            )

    # ── Public API ─────────────────────────────────────────────────────────

    async def call_claude(
        self,
        prompt: str,
        complexity_score: int,
        system_prompt: Optional[str] = None,
        context_chunks: Optional[list] = None,
    ) -> dict:
        """
        Call Claude with the tier matching complexity_score.
        Applies prompt caching to the system prompt and any long context.

        Args:
            prompt:           The (Jessie-improved) developer prompt.
            complexity_score: 1–10 from Prompt Coach; drives tier selection.
            system_prompt:    Override the default system prompt if needed.
            context_chunks:   RAG file snippets from the codebase.

        Returns a dict:
            {
              "response":      str,    # Claude's text output
              "model":         str,    # full model ID used
              "tier":          str,    # "tier1" / "tier2" / "tier3"
              "tier_label":    str,    # "Haiku" / "Sonnet" / "Opus"
              "tokens_in":     int,
              "tokens_out":    int,
              "cache_hit":     bool,   # True if cache_read_input_tokens > 0
              "cache_tokens":  int,    # how many tokens were served from cache
              "cost_estimate": float,  # USD, rounded to 5 decimal places
            }
        """
        tier  = self._tier(complexity_score)
        model = MODELS[tier]
        sys   = system_prompt or DEFAULT_SYSTEM

        # System prompt always cached (large, repeated on every request)
        system_block = [
            {
                "type": "text",
                "text": sys,
                "cache_control": {"type": "ephemeral"},
            }
        ]

        # Build user message — optionally split context + prompt for caching
        context_str = "\n\n".join(context_chunks) if context_chunks else ""
        messages    = self._build_messages(prompt, context_str)

        logger.info(
            f"Claude call  tier={tier} model={model} "
            f"complexity={complexity_score}"
        )

        try:
            response = await self._client.messages.create(
                model=model,
                max_tokens=4096,
                system=system_block,
                messages=messages,
                extra_headers={"anthropic-beta": "prompt-caching-2024-07-31"},
            )
        except self._anthropic.APIError as exc:
            logger.error(f"Claude API error: {exc}")
            raise

        content     = response.content[0].text if response.content else ""
        tokens_in   = response.usage.input_tokens
        tokens_out  = response.usage.output_tokens
        cache_read  = getattr(response.usage, "cache_read_input_tokens", 0)
        cache_hit   = cache_read > 0

        cost = (
            (tokens_in  / 1000) * COST_INPUT_PER_1K[tier] +
            (tokens_out / 1000) * COST_OUTPUT_PER_1K[tier]
        )

        logger.info(
            f"Claude done  model={model} in={tokens_in} out={tokens_out} "
            f"cache_hit={cache_hit} cache_tokens={cache_read} "
            f"cost=${cost:.5f}"
        )

        return {
            "response":      content,
            "model":         model,
            "tier":          tier,
            "tier_label":    TIER_LABELS[tier],
            "tokens_in":     tokens_in,
            "tokens_out":    tokens_out,
            "cache_hit":     cache_hit,
            "cache_tokens":  cache_read,
            "cost_estimate": round(cost, 5),
        }

    # ── Private helpers ────────────────────────────────────────────────────

    def _tier(self, complexity: int) -> str:
        if complexity <= 3:
            return "tier1"
        elif complexity <= 7:
            return "tier2"
        else:
            return "tier3"

    def _estimate_tokens(self, text: str) -> int:
        return len(text) // _CHARS_PER_TOKEN

    def _build_messages(self, prompt: str, context_str: str) -> list:
        """
        If context is large (> 1024 tokens), split it into a separate
        content block with cache_control so it is cached independently
        of the (shorter, changing) prompt.
        """
        if context_str and self._estimate_tokens(context_str) > _CACHE_TOKEN_THRESHOLD:
            # Two content blocks: cacheable context + live prompt
            return [{
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": context_str,
                        "cache_control": {"type": "ephemeral"},
                    },
                    {
                        "type": "text",
                        "text": prompt,
                    },
                ],
            }]

        # Single block — context short enough to include inline
        full = f"{context_str}\n\n{prompt}" if context_str else prompt
        return [{"role": "user", "content": full}]
