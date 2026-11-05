"""Phase 0 acceptance tests.

These are your specification. They fail right now (NotImplementedError) and pass
when `config.py` and `logging_setup.py` are correctly implemented. Do not edit
them to make them pass -- that is cheating yourself out of the exercise.

Run them with:   pytest tests/test_config.py -v
"""

from __future__ import annotations

import logging
from pathlib import Path

import pytest

from src.core import config as config_mod
from src.core.config import PROJECT_ROOT, Config, get_config, load_config
from src.core.logging_setup import get_logger, setup_logging


@pytest.fixture(autouse=True)
def _fake_key(monkeypatch):
    """Every test gets a dummy key, so none of them need your real one."""
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-not-a-real-key")
    get_config.cache_clear()
    yield
    get_config.cache_clear()


# --------------------------------------------------------------------------- #
# load_config
# --------------------------------------------------------------------------- #

def test_loads_and_validates_real_config():
    cfg = load_config()
    assert isinstance(cfg, Config)
    assert cfg.llm.model == "gpt-4o"
    assert cfg.llm.router_model == "gpt-4o-mini"
    assert cfg.rag.embedding_dim == 384
    assert "educational" in cfg.compliance.disclaimer.lower()


def test_secrets_come_from_environment_not_yaml():
    cfg = load_config()
    assert cfg.secrets.openai_api_key == "sk-test-not-a-real-key"
    # The YAML must not contain the key anywhere.
    assert "OPENAI_API_KEY" not in (PROJECT_ROOT / "config.yaml").read_text()


def test_missing_required_key_fails_fast(monkeypatch):
    # Stop .env from quietly re-supplying the key we are deleting.
    monkeypatch.setattr(config_mod, "load_dotenv", lambda *a, **k: None)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="OPENAI_API_KEY"):
        load_config()


def test_missing_config_file_raises_useful_error(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_config(tmp_path / "nope.yaml")


# --------------------------------------------------------------------------- #
# Environment overrides
# --------------------------------------------------------------------------- #

def test_nested_env_override(monkeypatch):
    monkeypatch.setenv("FINNIE_LLM__MODEL", "gpt-4o-mini")
    assert load_config().llm.model == "gpt-4o-mini"


def test_env_override_is_type_coerced(monkeypatch):
    """Env vars are strings; pydantic must coerce them to the declared type."""
    monkeypatch.setenv("FINNIE_RAG__TOP_K", "7")
    cfg = load_config()
    assert cfg.rag.top_k == 7
    assert isinstance(cfg.rag.top_k, int)


def test_friendly_log_level_override(monkeypatch):
    monkeypatch.setenv("FINNIE_LOG_LEVEL", "DEBUG")
    assert load_config().logging.level == "DEBUG"


def test_invalid_override_is_rejected(monkeypatch):
    """A bad value must blow up at startup, not silently pass through."""
    monkeypatch.setenv("FINNIE_LLM__TEMPERATURE", "99")  # ge=0, le=2
    with pytest.raises(Exception):  # pydantic.ValidationError
        load_config()


# --------------------------------------------------------------------------- #
# Caching & paths
# --------------------------------------------------------------------------- #

def test_get_config_is_cached():
    assert get_config() is get_config()


def test_resolve_makes_paths_absolute():
    cfg = load_config()
    resolved = cfg.resolve(cfg.rag.index_dir)
    assert resolved.is_absolute()
    assert resolved == PROJECT_ROOT / "data" / "indexes"


def test_resolve_leaves_absolute_paths_alone():
    cfg = load_config()
    absolute = Path(PROJECT_ROOT / "somewhere")
    assert cfg.resolve(absolute) == absolute


# --------------------------------------------------------------------------- #
# Logging
# --------------------------------------------------------------------------- #

def test_setup_logging_is_idempotent():
    """The Streamlit duplicate-handler bug, caught by a test."""
    root = logging.getLogger()
    for h in root.handlers[:]:
        root.removeHandler(h)
    config_mod_flag_reset()

    setup_logging()
    first = len(logging.getLogger().handlers)
    setup_logging()
    setup_logging()
    assert len(logging.getLogger().handlers) == first, (
        "setup_logging() added handlers on a repeat call -- every log line will "
        "now print multiple times"
    )


def test_get_logger_is_named_after_module():
    log = get_logger("src.rag.retriever")
    assert log.name == "src.rag.retriever"
    assert isinstance(log, logging.Logger)


def test_noisy_libraries_are_quietened():
    setup_logging()
    assert logging.getLogger("httpx").level >= logging.WARNING


def config_mod_flag_reset() -> None:
    """Reset the one-shot guard so the idempotency test starts clean."""
    import src.core.logging_setup as ls

    ls._CONFIGURED = False
