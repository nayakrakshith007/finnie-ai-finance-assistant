"""Output compliance guard.

Every response Finnie sends to a user must:
  1. Never recommend a specific trade.
  2. Always close with the educational-use disclaimer from config.yaml.

Agents call `check_and_wrap` before returning any user-facing text.
If a banned phrase is found, raise ValueError so the agent can log it
and return a safe fallback instead of crashing.
"""

from __future__ import annotations

from core.config import get_config
from core.logging_setup import get_logger

log = get_logger(__name__)


def check_and_wrap(text: str) -> str:
    """Block banned phrases and append the compliance disclaimer.

    Args:
        text: Raw LLM output before it reaches the user.

    Returns:
        The same text with the disclaimer appended on a new line.

    Raises:
        ValueError: If the text contains a banned investment-advice phrase.
    """
    cfg = get_config()
    lower = text.lower()

    for phrase in cfg.compliance.banned_phrases:
        if phrase.lower() in lower:
            log.warning("Compliance violation — banned phrase detected: %r", phrase)
            raise ValueError(
                f"Response contains banned phrase: {phrase!r}. "
                "Finnie gives education, not investment advice."
            )

    return f"{text.rstrip()}\n\n{cfg.compliance.disclaimer}"
