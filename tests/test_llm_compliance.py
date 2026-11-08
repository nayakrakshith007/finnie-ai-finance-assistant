"""Tests for Phase 1: LLM factory and compliance guard."""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage

from core.llm import build_fake_llm

# ---------------------------------------------------------------------------
# FakeLLM tests — these never touch the network
# ---------------------------------------------------------------------------

class TestBuildFakeLlm:
    def test_returns_base_chat_model(self):
        assert isinstance(build_fake_llm(["hi"]), BaseChatModel)

    def test_responses_returned_in_order(self):
        llm = build_fake_llm(["first", "second"])
        r1 = llm.invoke([HumanMessage(content="q1")])
        r2 = llm.invoke([HumanMessage(content="q2")])
        assert r1.content == "first"
        assert r2.content == "second"

    def test_no_api_key_needed(self):
        """FakeLLM must work without a valid API key — proves no network call."""
        llm = build_fake_llm(["offline ok"])
        result = llm.invoke([HumanMessage(content="test")])
        assert result.content == "offline ok"


# ---------------------------------------------------------------------------
# Compliance tests — config is mocked so no .env required
# ---------------------------------------------------------------------------

@pytest.fixture()
def mock_cfg(monkeypatch):
    cfg = MagicMock()
    cfg.compliance.banned_phrases = [
        "you should buy",
        "you should sell",
        "i recommend buying",
        "i recommend selling",
        "guaranteed return",
        "risk-free profit",
    ]
    cfg.compliance.disclaimer = (
        "For educational purposes only. Not financial advice. "
        "Consult a SEBI-registered advisor before investing."
    )
    monkeypatch.setattr("core.compliance.get_config", lambda: cfg)
    return cfg


class TestCheckAndWrap:
    def test_disclaimer_appended(self, mock_cfg):
        from core.compliance import check_and_wrap
        result = check_and_wrap("SIP is a great wealth-building habit.")
        assert result.endswith(mock_cfg.compliance.disclaimer)

    def test_original_text_preserved(self, mock_cfg):
        from core.compliance import check_and_wrap
        text = "Index funds track the Nifty 50."
        assert text in check_and_wrap(text)

    def test_banned_phrase_raises_value_error(self, mock_cfg):
        from core.compliance import check_and_wrap
        with pytest.raises(ValueError, match="banned phrase"):
            check_and_wrap("You should buy Infosys today.")

    def test_detection_is_case_insensitive(self, mock_cfg):
        from core.compliance import check_and_wrap
        with pytest.raises(ValueError):
            check_and_wrap("YOU SHOULD SELL before the crash.")

    def test_guaranteed_return_blocked(self, mock_cfg):
        from core.compliance import check_and_wrap
        with pytest.raises(ValueError):
            check_and_wrap("This scheme offers a guaranteed return of 15% per year.")

    def test_risk_free_profit_blocked(self, mock_cfg):
        from core.compliance import check_and_wrap
        with pytest.raises(ValueError):
            check_and_wrap("Arbitrage gives a risk-free profit.")

    def test_clean_educational_text_passes(self, mock_cfg):
        from core.compliance import check_and_wrap
        result = check_and_wrap("LTCG tax applies on equity gains above ₹1 lakh.")
        assert "LTCG" in result
        assert mock_cfg.compliance.disclaimer in result

    def test_trailing_whitespace_stripped_before_disclaimer(self, mock_cfg):
        from core.compliance import check_and_wrap
        result = check_and_wrap("PPF has a 15-year lock-in.   ")
        assert result.startswith("PPF has a 15-year lock-in.")

    # ── idempotency ────────────────────────────────────────────────────────────
    # Observed 2026-11-08 in the RAG Lab: the system prompt told the model to add
    # its own disclaimer AND check_and_wrap appended one, so every answer carried
    # two. The prompt instruction was removed, but a prompt rule is a request the
    # model may ignore -- so the guard must also be safe to apply twice.

    def test_disclaimer_not_duplicated_when_model_already_wrote_it(self, mock_cfg):
        from core.compliance import check_and_wrap
        text = f"ELSS has a three-year lock-in.\n\n{mock_cfg.compliance.disclaimer}"
        result = check_and_wrap(text)
        assert result.count("Not financial advice") == 1

    def test_duplicate_detection_survives_reflowed_line_breaks(self, mock_cfg):
        """The model reflows text, so matching must ignore whitespace differences."""
        from core.compliance import check_and_wrap
        reflowed = mock_cfg.compliance.disclaimer.replace(" ", "\n", 3)
        result = check_and_wrap(f"NPS allows an extra 50,000 deduction.\n\n{reflowed}")
        assert result.count("Consult a SEBI-registered advisor") == 1

    def test_differently_worded_model_disclaimer_is_replaced(self, mock_cfg):
        """The real failure case: the model paraphrases, so exact matching misses it."""
        from core.compliance import check_and_wrap
        model_version = (
            "⚠️ This is educational information, not financial advice. "
            "Consult a licensed financial adviser before making any investment decision."
        )
        result = check_and_wrap(f"LTCG is 12.5% above ₹1.25 lakh.\n\n{model_version}")

        # Case-insensitive: the configured disclaimer capitalises "Not financial advice."
        assert result.lower().count("not financial advice") == 1, "exactly one disclaimer survives"
        assert result.endswith(mock_cfg.compliance.disclaimer), "and it is the official one"
        assert "licensed financial adviser" not in result, "the model's version is gone"
        assert "LTCG is 12.5% above ₹1.25 lakh." in result, "the answer itself is untouched"

    def test_mid_answer_mention_is_not_stripped(self, mock_cfg):
        """Only trailing disclaimer paragraphs go; prose mentioning the phrase stays."""
        from core.compliance import check_and_wrap
        body = (
            "Finnie gives educational information, not financial advice, which is why "
            "it explains rules rather than naming funds.\n\nPPF currently pays 7.1%."
        )
        result = check_and_wrap(body)
        assert "which is why" in result
        assert "PPF currently pays 7.1%." in result

    def test_applying_the_guard_twice_changes_nothing(self, mock_cfg):
        from core.compliance import check_and_wrap
        once = check_and_wrap("An index fund tracks a benchmark.")
        assert check_and_wrap(once) == once

    def test_disclaimer_still_appended_when_absent(self, mock_cfg):
        """The idempotency check must not swallow the normal case."""
        from core.compliance import check_and_wrap
        result = check_and_wrap("A sweep-in FD auto-liquidates as needed.")
        assert result.endswith(mock_cfg.compliance.disclaimer)
