"""LLM client factory for Finnie.

Uses LangChain's ecosystem so agents get a standard BaseChatModel interface:
  - ChatOpenAI          — the production adapter (OpenAI behind BaseChatModel)
  - InMemoryRateLimiter — smooth traffic, prevents burst
  - BaseCallbackHandler — cost metering per call, zero extra config
  - FakeListChatModel   — deterministic offline testing (no API key needed)

Provider switch later? Swap ChatOpenAI for ChatAnthropic / ChatGemini.
The agents never see the difference — they only know BaseChatModel.
"""

from __future__ import annotations

from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.language_models import BaseChatModel
from langchain_core.language_models.fake_chat_models import FakeListChatModel
from langchain_core.outputs import LLMResult
from langchain_core.rate_limiters import InMemoryRateLimiter
from langchain_openai import ChatOpenAI

from core.logging_setup import get_logger

log = get_logger(__name__)

# USD cost per 1,000 tokens — update when OpenAI changes pricing.
_COST_PER_1K: dict[str, dict[str, float]] = {
    "gpt-4o":      {"input": 0.005,   "output": 0.015},
    "gpt-4o-mini": {"input": 0.00015, "output": 0.0006},
}

# Built lazily on first call so config is already loaded before we read it.
_rate_limiter: InMemoryRateLimiter | None = None


def _get_rate_limiter() -> InMemoryRateLimiter:
    global _rate_limiter
    if _rate_limiter is None:
        from core.config import get_config
        cfg = get_config()
        rps = cfg.rate_limit.requests_per_minute / 60.0
        _rate_limiter = InMemoryRateLimiter(requests_per_second=rps)
    return _rate_limiter


class CostMeterCallback(BaseCallbackHandler):
    """Fires after every LLM response and logs tokens + estimated cost."""

    def on_llm_end(self, response: LLMResult, **kwargs: object) -> None:
        usage = (response.llm_output or {}).get("token_usage", {})
        if not usage:
            return
        prompt_tok = usage.get("prompt_tokens", 0)
        compl_tok = usage.get("completion_tokens", 0)
        model = (response.llm_output or {}).get("model_name", "")

        # Match on prefix so "gpt-4o-mini-2024-07-18" → gpt-4o-mini pricing.
        pricing = next(
            (v for k, v in _COST_PER_1K.items() if model.startswith(k)),
            _COST_PER_1K["gpt-4o"],
        )
        cost = prompt_tok / 1000 * pricing["input"] + compl_tok / 1000 * pricing["output"]
        log.debug(
            "LLM | model=%s prompt=%d completion=%d cost=$%.6f",
            model, prompt_tok, compl_tok, cost,
        )


def build_llm(model: str | None = None, *, streaming: bool = False) -> BaseChatModel:
    """Return a production ChatOpenAI with rate limiting and cost metering.

    Args:
        model: Override the model from config.yaml llm.model.
        streaming: Enable token-by-token streaming (for Streamlit live output).

    Returns:
        A BaseChatModel ready to drop into any LangGraph node.
    """
    from core.config import get_config
    cfg = get_config()
    model_name = model or cfg.llm.model

    return ChatOpenAI(
        model=model_name,
        api_key=cfg.secrets.openai_api_key,
        temperature=cfg.llm.temperature,
        max_tokens=cfg.llm.max_tokens,
        timeout=cfg.llm.timeout_seconds,
        max_retries=cfg.llm.max_retries,
        streaming=streaming,
        rate_limiter=_get_rate_limiter(),
        callbacks=[CostMeterCallback()],
    )


def build_router_llm() -> BaseChatModel:
    """Return the cheap mini model used for routing decisions only."""
    return build_llm(model="gpt-4o-mini")


def build_fake_llm(responses: list[str]) -> BaseChatModel:
    """Return a deterministic fake LLM for offline testing.

    Cycles through `responses` in order. When exhausted, repeats the last entry.
    Never touches the network, so no OPENAI_API_KEY is needed.

    Args:
        responses: Pre-canned reply strings returned in sequence.

    Returns:
        A BaseChatModel that works offline and in CI.
    """
    return FakeListChatModel(responses=responses)
