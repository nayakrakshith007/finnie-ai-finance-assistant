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

import threading
from typing import ClassVar

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
    """Fires after every LLM response, logging and accumulating tokens and cost.

    Totals are kept on the class, not the instance, because `build_llm` creates a
    fresh callback per client and the number that matters is what this *process*
    has spent. The API allowance is of unknown size (NFR-02a), so the person
    demonstrating Finnie should be able to watch the meter rather than find out
    afterwards — it is surfaced in the sidebar (FR-075).

    Guarded by a lock: Streamlit runs each rerun in its own thread, and two
    agents in a composed turn can finish close enough together to interleave a
    read-modify-write on the totals.
    """

    _lock: ClassVar[threading.Lock] = threading.Lock()
    _prompt_tokens: ClassVar[int] = 0
    _completion_tokens: ClassVar[int] = 0
    _cost_usd: ClassVar[float] = 0.0
    _calls: ClassVar[int] = 0

    @classmethod
    def session_totals(cls) -> dict[str, float | int]:
        """What this process has spent so far."""
        with cls._lock:
            return {
                "calls": cls._calls,
                "prompt_tokens": cls._prompt_tokens,
                "completion_tokens": cls._completion_tokens,
                "total_tokens": cls._prompt_tokens + cls._completion_tokens,
                "total_cost_usd": round(cls._cost_usd, 6),
            }

    @classmethod
    def reset(cls) -> None:
        """Zero the totals. For tests, and for a 'clear session' action."""
        with cls._lock:
            cls._prompt_tokens = cls._completion_tokens = cls._calls = 0
            cls._cost_usd = 0.0

    def on_llm_end(self, response: LLMResult, **kwargs: object) -> None:
        usage = (response.llm_output or {}).get("token_usage", {})
        if not usage:
            return
        prompt_tok = usage.get("prompt_tokens", 0)
        compl_tok = usage.get("completion_tokens", 0)
        model = (response.llm_output or {}).get("model_name", "")

        # Match on prefix so "gpt-4o-mini-2024-07-18" → gpt-4o-mini pricing, and
        # LONGEST KEY FIRST, which is the whole point: "gpt-4o-mini" starts with
        # "gpt-4o", so iterating in dict order charged every router call at the
        # full gpt-4o rate — a 33x over-estimate on the highest-frequency call in
        # the app, which is the worst possible place to be wrong about cost.
        # Unknown models fall back to the dearest price: over-estimating spend is
        # the safe direction when the allowance is of unknown size (NFR-02a).
        pricing = next(
            (
                v
                for k, v in sorted(_COST_PER_1K.items(), key=lambda kv: -len(kv[0]))
                if model.startswith(k)
            ),
            _COST_PER_1K["gpt-4o"],
        )
        cost = prompt_tok / 1000 * pricing["input"] + compl_tok / 1000 * pricing["output"]

        cls = type(self)
        with cls._lock:
            cls._calls += 1
            cls._prompt_tokens += prompt_tok
            cls._completion_tokens += compl_tok
            cls._cost_usd += cost

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
