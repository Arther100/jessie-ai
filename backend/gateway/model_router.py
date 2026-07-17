"""
Jessie — backend/gateway/model_router.py
Multi-provider AI router (Anthropic / OpenAI / Gemini).

API keys are passed per-request (BYOK). Never stored.
Local-dev fallback: ANTHROPIC_API_KEY from env only when api_key is empty.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any, Optional

from dotenv import load_dotenv

load_dotenv(Path(".jessie/.env"))

logger = logging.getLogger(__name__)

DEFAULT_SYSTEM = (
    "You are an expert software engineer embedded inside a developer's IDE. "
    "Write clean, production-ready code with proper error handling. "
    "Include brief inline comments for non-obvious logic only. "
    "Return only the code or explanation that was asked for — "
    "do not dump the entire file unless explicitly requested. "
    "Match the language, style, and framework already present in any provided context."
)

_CHARS_PER_TOKEN = 4
_CACHE_TOKEN_THRESHOLD = 1024

# Anthropic models (legacy MODELS alias kept for callers)
MODELS = {
    "tier1": "claude-haiku-4-5-20251001",
    "tier2": "claude-sonnet-4-6",
    "tier3": "claude-opus-4-8",
}

PROVIDERS = {
    "anthropic": {
        "tier1": "claude-haiku-4-5-20251001",
        "tier2": "claude-sonnet-4-6",
        "tier3": "claude-opus-4-8",
        "labels": {"tier1": "Haiku", "tier2": "Sonnet", "tier3": "Opus"},
        "cost_in": {"tier1": 0.00025, "tier2": 0.003, "tier3": 0.015},
        "cost_out": {"tier1": 0.00125, "tier2": 0.015, "tier3": 0.075},
    },
    "openai": {
        "tier1": "gpt-4o-mini",
        "tier2": "gpt-4o",
        "tier3": "o1",
        "labels": {"tier1": "GPT-4o-mini", "tier2": "GPT-4o", "tier3": "o1"},
        "cost_in": {"tier1": 0.00015, "tier2": 0.0025, "tier3": 0.015},
        "cost_out": {"tier1": 0.0006, "tier2": 0.01, "tier3": 0.06},
    },
    "gemini": {
        "tier1": "gemini-1.5-flash",
        "tier2": "gemini-1.5-pro",
        "tier3": "gemini-1.5-pro",
        "labels": {"tier1": "Flash", "tier2": "Pro", "tier3": "Pro"},
        "cost_in": {"tier1": 0.000075, "tier2": 0.00125, "tier3": 0.00125},
        "cost_out": {"tier1": 0.0003, "tier2": 0.005, "tier3": 0.005},
    },
}

TIER_LABELS = {"tier1": "Haiku", "tier2": "Sonnet", "tier3": "Opus"}
COST_INPUT_PER_1K = {"tier1": 0.00025, "tier2": 0.003, "tier3": 0.015}
COST_OUTPUT_PER_1K = {"tier1": 0.00125, "tier2": 0.015, "tier3": 0.075}


def complexity_to_tier(complexity: int) -> str:
    if complexity <= 3:
        return "tier1"
    if complexity <= 7:
        return "tier2"
    return "tier3"


def resolve_api_key(api_key: Optional[str] = None) -> str:
    """Prefer request key; local-dev fallback to env (never log the value)."""
    key = (api_key or "").strip() or (os.getenv("ANTHROPIC_API_KEY") or "").strip()
    if not key:
        raise ValueError(
            "API key is required. Pass X-Claude-API-Key header, "
            "or set ANTHROPIC_API_KEY for local development only."
        )
    return key


class ModelRouter:
    """
    Routes each request to the right model tier for the chosen provider.
    Construct with (api_key, provider=...). Key is held only for this request.
    """

    def __init__(self, api_key: Optional[str] = None, provider: str = "anthropic"):
        self._provider = (provider or "anthropic").strip().lower()
        if self._provider not in PROVIDERS:
            self._provider = "anthropic"
        self._api_key = resolve_api_key(api_key)
        self._client = None
        self._anthropic = None
        if self._provider == "anthropic":
            try:
                import anthropic as _anthropic
                self._client = _anthropic.AsyncAnthropic(api_key=self._api_key)
                self._anthropic = _anthropic
            except ImportError as exc:
                raise ImportError("anthropic package not installed. Run: pip install anthropic") from exc

    async def call_claude(
        self,
        prompt: str,
        complexity_score: int,
        system_prompt: Optional[str] = None,
        context_chunks: Optional[list] = None,
    ) -> dict:
        """Backward-compatible name — routes via configured provider."""
        return await self.route_and_call(
            prompt=prompt,
            complexity_score=complexity_score,
            system_prompt=system_prompt,
            context_chunks=context_chunks,
        )

    async def route_and_call(
        self,
        prompt: str,
        complexity_score: int,
        system_prompt: Optional[str] = None,
        context_chunks: Optional[list] = None,
        api_key: Optional[str] = None,
        provider: Optional[str] = None,
    ) -> dict:
        prov = (provider or self._provider).lower()
        key = resolve_api_key(api_key or self._api_key)
        tier = complexity_to_tier(complexity_score)
        cfg = PROVIDERS.get(prov) or PROVIDERS["anthropic"]
        model = cfg[tier]
        sys = system_prompt or DEFAULT_SYSTEM
        context_str = "\n\n".join(context_chunks) if context_chunks else ""

        logger.info("AI call provider=%s tier=%s model=%s complexity=%s", prov, tier, model, complexity_score)

        if prov == "openai":
            return await self._call_openai(prompt, sys, context_str, model, tier, cfg, key)
        if prov == "gemini":
            return await self._call_gemini(prompt, sys, context_str, model, tier, cfg, key)
        return await self._call_anthropic(prompt, sys, context_str, model, tier, cfg, key)

    async def verify_key(self) -> dict:
        """Minimal test call for /verify."""
        result = await self.route_and_call(
            prompt="Say OK",
            complexity_score=1,
            system_prompt="Reply with exactly: OK",
        )
        return {
            "valid": True,
            "provider": self._provider,
            "model": result.get("model", ""),
            "message": "API key is valid ✓",
        }

    async def _call_anthropic(
        self, prompt: str, sys: str, context_str: str, model: str, tier: str, cfg: dict, key: str,
    ) -> dict:
        import anthropic as _anthropic
        client = self._client if (self._client and key == self._api_key) else _anthropic.AsyncAnthropic(api_key=key)
        system_block = [{"type": "text", "text": sys, "cache_control": {"type": "ephemeral"}}]
        messages = self._build_messages(prompt, context_str)
        try:
            response = await client.messages.create(
                model=model,
                max_tokens=4096,
                system=system_block,
                messages=messages,
                extra_headers={"anthropic-beta": "prompt-caching-2024-07-31"},
            )
        except _anthropic.APIError as exc:
            logger.error("Anthropic API error: %s", type(exc).__name__)
            raise

        content = response.content[0].text if response.content else ""
        tokens_in = response.usage.input_tokens
        tokens_out = response.usage.output_tokens
        cache_read = getattr(response.usage, "cache_read_input_tokens", 0)
        cost = (tokens_in / 1000) * cfg["cost_in"][tier] + (tokens_out / 1000) * cfg["cost_out"][tier]
        return {
            "response": content,
            "model": model,
            "tier": tier,
            "tier_label": cfg["labels"][tier],
            "tokens_in": tokens_in,
            "tokens_out": tokens_out,
            "cache_hit": cache_read > 0,
            "cache_tokens": cache_read,
            "cost_estimate": round(cost, 5),
            "provider": "anthropic",
        }

    async def _call_openai(
        self, prompt: str, sys: str, context_str: str, model: str, tier: str, cfg: dict, key: str,
    ) -> dict:
        try:
            from openai import AsyncOpenAI
        except ImportError as exc:
            raise ImportError("openai package not installed. Run: pip install openai") from exc

        client = AsyncOpenAI(api_key=key)
        user = f"{context_str}\n\n{prompt}" if context_str else prompt
        kwargs: dict[str, Any] = {
            "model": model,
            "messages": [
                {"role": "system", "content": sys},
                {"role": "user", "content": user},
            ],
        }
        if not model.startswith("o1"):
            kwargs["max_tokens"] = 4096
        try:
            response = await client.chat.completions.create(**kwargs)
        except Exception as exc:
            logger.error("OpenAI API error: %s", type(exc).__name__)
            raise

        content = (response.choices[0].message.content if response.choices else "") or ""
        usage = response.usage
        tokens_in = getattr(usage, "prompt_tokens", 0) or 0
        tokens_out = getattr(usage, "completion_tokens", 0) or 0
        cost = (tokens_in / 1000) * cfg["cost_in"][tier] + (tokens_out / 1000) * cfg["cost_out"][tier]
        return {
            "response": content,
            "model": model,
            "tier": tier,
            "tier_label": cfg["labels"][tier],
            "tokens_in": tokens_in,
            "tokens_out": tokens_out,
            "cache_hit": False,
            "cache_tokens": 0,
            "cost_estimate": round(cost, 5),
            "provider": "openai",
        }

    async def _call_gemini(
        self, prompt: str, sys: str, context_str: str, model: str, tier: str, cfg: dict, key: str,
    ) -> dict:
        try:
            import google.generativeai as genai
        except ImportError as exc:
            raise ImportError("google-generativeai not installed. Run: pip install google-generativeai") from exc

        genai.configure(api_key=key)
        gmodel = genai.GenerativeModel(model, system_instruction=sys)
        user = f"{context_str}\n\n{prompt}" if context_str else prompt
        try:
            response = await gmodel.generate_content_async(user)
        except Exception as exc:
            logger.error("Gemini API error: %s", type(exc).__name__)
            raise

        content = getattr(response, "text", None) or ""
        tokens_in = max(1, len(user) // _CHARS_PER_TOKEN)
        tokens_out = max(1, len(content) // _CHARS_PER_TOKEN)
        cost = (tokens_in / 1000) * cfg["cost_in"][tier] + (tokens_out / 1000) * cfg["cost_out"][tier]
        return {
            "response": content,
            "model": model,
            "tier": tier,
            "tier_label": cfg["labels"][tier],
            "tokens_in": tokens_in,
            "tokens_out": tokens_out,
            "cache_hit": False,
            "cache_tokens": 0,
            "cost_estimate": round(cost, 5),
            "provider": "gemini",
        }

    def _estimate_tokens(self, text: str) -> int:
        return len(text) // _CHARS_PER_TOKEN

    def _build_messages(self, prompt: str, context_str: str) -> list:
        if context_str and self._estimate_tokens(context_str) > _CACHE_TOKEN_THRESHOLD:
            return [{
                "role": "user",
                "content": [
                    {"type": "text", "text": context_str, "cache_control": {"type": "ephemeral"}},
                    {"type": "text", "text": prompt},
                ],
            }]
        full = f"{context_str}\n\n{prompt}" if context_str else prompt
        return [{"role": "user", "content": full}]

    def _tier(self, complexity: int) -> str:
        return complexity_to_tier(complexity)
