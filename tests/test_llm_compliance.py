"""Tests for Phase 1: LLM factory and compliance guard."""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage

from src.core.llm import build_fake_llm

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
    monkeypatch.setattr("src.core.compliance.get_config", lambda: cfg)
    return cfg


class TestCheckAndWrap:
    def test_disclaimer_appended(self, mock_cfg):
        from src.core.compliance import check_and_wrap
        result = check_and_wrap("SIP is a great wealth-building habit.")
        assert result.endswith(mock_cfg.compliance.disclaimer)

    def test_original_text_preserved(self, mock_cfg):
        from src.core.compliance import check_and_wrap
        text = "Index funds track the Nifty 50."
        assert text in check_and_wrap(text)

    def test_banned_phrase_raises_value_error(self, mock_cfg):
        from src.core.compliance import check_and_wrap
        with pytest.raises(ValueError, match="banned phrase"):
            check_and_wrap("You should buy Infosys today.")

    def test_detection_is_case_insensitive(self, mock_cfg):
        from src.core.compliance import check_and_wrap
        with pytest.raises(ValueError):
            check_and_wrap("YOU SHOULD SELL before the crash.")

    def test_guaranteed_return_blocked(self, mock_cfg):
        from src.core.compliance import check_and_wrap
        with pytest.raises(ValueError):
            check_and_wrap("This scheme offers a guaranteed return of 15% per year.")

    def test_risk_free_profit_blocked(self, mock_cfg):
        from src.core.compliance import check_and_wrap
        with pytest.raises(ValueError):
            check_and_wrap("Arbitrage gives a risk-free profit.")

    def test_clean_educational_text_passes(self, mock_cfg):
        from src.core.compliance import check_and_wrap
        result = check_and_wrap("LTCG tax applies on equity gains above ₹1 lakh.")
        assert "LTCG" in result
        assert mock_cfg.compliance.disclaimer in result

    def test_trailing_whitespace_stripped_before_disclaimer(self, mock_cfg):
        from src.core.compliance import check_and_wrap
        result = check_and_wrap("PPF has a 15-year lock-in.   ")
        assert result.startswith("PPF has a 15-year lock-in.")
