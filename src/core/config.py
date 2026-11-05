"""Typed configuration for Finnie.

Design rules this module exists to enforce:

1. Secrets come from the environment (`.env`), never from `config.yaml`.
2. Behaviour comes from `config.yaml`, never from hardcoded literals in `src/`.
3. Nothing else in the codebase reads YAML or `os.environ`. Everything calls
   `get_config()` and gets a typed, validated object back.
4. Config is loaded once and cached. A process should never see two different
   configs.

The pydantic models below are the schema -- they are the contract. Your job is
the loader at the bottom.
"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal

import yaml
from dotenv import load_dotenv
from pydantic import BaseModel, Field, field_validator

# Project root = two levels up from this file (src/core/config.py -> project root).
PROJECT_ROOT = Path(__file__).resolve().parents[2]
CONFIG_PATH = PROJECT_ROOT / "config.yaml"

# Env vars that map onto config fields. Key = env var, value = dotted config path.
# Double underscore in the env var name means "nested", e.g. FINNIE_LLM__MODEL.
ENV_PREFIX = "FINNIE_"


# --------------------------------------------------------------------------- #
# Schema
# --------------------------------------------------------------------------- #

class AppConfig(BaseModel):
    name: str = "Finnie"
    environment: Literal["development", "production"] = "development"


class LLMConfig(BaseModel):
    provider: Literal["openai"] = "openai"
    model: str = "gpt-4o"
    router_model: str = "gpt-4o-mini"
    temperature: float = Field(0.2, ge=0.0, le=2.0)
    max_tokens: int = Field(1200, gt=0)
    timeout_seconds: int = Field(60, gt=0)
    max_retries: int = Field(3, ge=0)


class RateLimitConfig(BaseModel):
    requests_per_minute: int = Field(60, gt=0)
    tokens_per_minute: int = Field(150_000, gt=0)


class RAGConfig(BaseModel):
    embedding_model: str
    embedding_dim: int = Field(384, gt=0)
    chunk_size: int = Field(800, gt=0)
    chunk_overlap: int = Field(100, ge=0)
    top_k: int = Field(4, gt=0)
    relevance_threshold: float = Field(0.35, ge=0.0, le=1.0)
    index_dir: Path
    knowledge_base_dir: Path

    @field_validator("chunk_overlap")
    @classmethod
    def overlap_must_be_smaller_than_chunk(cls, v: int, info: Any) -> int:
        chunk_size = info.data.get("chunk_size")
        if chunk_size is not None and v >= chunk_size:
            raise ValueError(
                f"chunk_overlap ({v}) must be smaller than chunk_size ({chunk_size}); "
                "otherwise chunking never advances and you get infinite duplicates"
            )
        return v


class MarketConfig(BaseModel):
    primary_source: str = "yfinance"
    fallback_source: str = "alpha_vantage"
    cache_ttl_minutes: int = Field(30, gt=0)
    cache_dir: Path
    default_tickers: list[str] = []


class PortfolioConfig(BaseModel):
    concentration_warning_pct: float = Field(25.0, gt=0, le=100)
    risk_weights: dict[str, int] = {}


class RiskProfile(BaseModel):
    expected_return: float
    volatility: float


class GoalsConfig(BaseModel):
    inflation_rate: float = Field(0.06, ge=0.0, le=1.0)
    risk_profiles: dict[str, RiskProfile] = {}


class MemoryConfig(BaseModel):
    max_recent_messages: int = Field(10, gt=0)
    summarise_after_turns: int = Field(10, gt=0)


class ComplianceConfig(BaseModel):
    disclaimer: str
    banned_phrases: list[str] = []


class LoggingConfig(BaseModel):
    level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    format: str
    file: Path | None = None


class Secrets(BaseModel):
    """Populated from the environment only. Never from YAML."""

    openai_api_key: str
    alpha_vantage_api_key: str | None = None


class Config(BaseModel):
    app: AppConfig
    llm: LLMConfig
    rate_limit: RateLimitConfig
    rag: RAGConfig
    market: MarketConfig
    portfolio: PortfolioConfig
    goals: GoalsConfig
    memory: MemoryConfig
    compliance: ComplianceConfig
    logging: LoggingConfig
    secrets: Secrets

    def resolve(self, p: Path) -> Path:
        """Turn a config-relative path into an absolute one."""
        return p if p.is_absolute() else PROJECT_ROOT / p


# --------------------------------------------------------------------------- #
# Loader
# --------------------------------------------------------------------------- #


def _apply_env_overrides(raw: dict[str, Any]) -> dict[str, Any]:
    """Overlay FINNIE_* environment variables onto the raw YAML dict."""

    for key, value in os.environ.items():
        if not key.startswith(ENV_PREFIX):
            continue

        env_key = key[len(ENV_PREFIX):].lower()

        # FINNIE_LOG_LEVEL → ["logging", "level"]  (special case — no __ in name)
        # Everything else: double __ = one level of nesting
        path = ["logging", "level"] if env_key == "log_level" else env_key.split("__")

        current = raw
        for part in path[:-1]:
            # Create intermediate dicts if absent or if YAML had a scalar there
            if part not in current or not isinstance(current[part], dict):
                current[part] = {}
            current = current[part]

        current[path[-1]] = value  # always a string; Pydantic coerces later

    return raw






def load_config(path: Path | None = None) -> Config:
    """
    Load application configuration from YAML and environment variables.

    Execution order:
        1. Load .env into os.environ.
        2. Read the YAML configuration file.
        3. Apply FINNIE_* environment overrides.
        4. Collect required and optional API keys.
        5. Validate and return the Pydantic Config object.
    """

    # --------------------------------------------------------
    # STEP 1: Load environment variables from .env
    # --------------------------------------------------------
    # PROJECT_ROOT / ".env" constructs the absolute path to .env.
    #
    # load_dotenv() loads variables into os.environ.
    # By default, it does NOT overwrite existing environment variables.
    # This means system environment variables take precedence over .env.
    load_dotenv(PROJECT_ROOT / ".env")

    # --------------------------------------------------------
    # STEP 2: Read the YAML configuration file
    # --------------------------------------------------------
    # If a custom path is provided, use it.
    # Otherwise, use the default CONFIG_PATH.
    config_path = Path(path) if path is not None else CONFIG_PATH

    # Check whether the configuration file exists.
    # Raise a helpful error if it is missing.
    if not config_path.is_file():
        raise FileNotFoundError(
            f"Configuration file not found: {config_path}. "
            "Please create config.yaml using the provided configuration "
            "template before starting the application."
        )

    # Open the YAML file and safely convert its contents into a dictionary.
    with config_path.open("r", encoding="utf-8") as file:
        raw: dict[str, Any] = yaml.safe_load(file) or {}

    # --------------------------------------------------------
    # STEP 3: Apply environment variable overrides
    # --------------------------------------------------------
    # FINNIE_LLM__MODEL overrides raw["llm"]["model"].
    # FINNIE_LOG_LEVEL overrides raw["logging"]["level"].
    raw = _apply_env_overrides(raw)

    # --------------------------------------------------------
    # STEP 4: Collect API secrets from environment variables
    # --------------------------------------------------------

    # Required API key:
    # The application cannot start without the OpenAI API key.
    openai_api_key = os.environ.get("OPENAI_API_KEY")

    # Check whether the key is missing or contains only whitespace.
    if not openai_api_key or not openai_api_key.strip():
        raise RuntimeError(
            "Missing required environment variable: OPENAI_API_KEY. "
            "Please add it to your .env file. "
            "Refer to .env.example for the required format."
        )

    # Optional API key:
    # Alpha Vantage is optional, so None is acceptable if unavailable.
    alpha_vantage_api_key = os.environ.get("ALPHA_VANTAGE_API_KEY")

    # Store both API keys inside the secrets section.
    raw["secrets"] = {
        "openai_api_key": openai_api_key,
        "alpha_vantage_api_key": alpha_vantage_api_key or None,
    }

    # --------------------------------------------------------
    # STEP 5: Validate and return the Config object
    # --------------------------------------------------------
    # Pydantic validates the complete configuration:
    # - Required fields
    # - Data types
    # - Nested configuration models
    # - Default values
    #
    # ValidationError is intentionally not caught.
    # Invalid configuration should stop application startup.
    return Config(**raw)



@lru_cache(maxsize=1)
def get_config() -> Config:
    """The only config accessor the rest of the codebase should use.

    `lru_cache` makes this a lazily-initialised singleton: the YAML is parsed on
    first call and reused thereafter. Call `get_config.cache_clear()` in tests
    that need a fresh load.
    """
    return load_config()
