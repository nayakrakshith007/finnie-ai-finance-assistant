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

    body = _strip_model_disclaimer(text.rstrip())
    return f"{body}\n\n{cfg.compliance.disclaimer}"


# A model-written disclaimer is recognised by this phrase rather than by matching the
# official text. Exact matching proved useless in practice: the model paraphrases and
# reflows, so "...Consult a licensed financial adviser..." never equals the configured
# "...Finnie cannot know your full circumstances. Consult...". Observed 2026-11-08,
# where every answer carried two near-identical disclaimers.
_DISCLAIMER_MARKER = "not financial advice"


def _strip_model_disclaimer(body: str) -> str:
    """Remove a trailing disclaimer the model wrote itself, if any.

    Compliance owns the disclaimer, so the guard normalises rather than tolerates:
    any trailing disclaimer-shaped paragraph is dropped and the official one is
    appended in its place. That guarantees exactly one, with the exact wording
    legal signed off on, however the model phrased its own.

    Only *trailing* paragraphs are considered. A mid-answer mention such as
    "this is educational information, not financial advice, so..." is part of the
    explanation and is left alone.
    """
    paragraphs = body.split("\n\n")
    while paragraphs and _DISCLAIMER_MARKER in paragraphs[-1].lower():
        dropped = paragraphs.pop()
        log.debug("Stripped model-written disclaimer before appending official one: %r", dropped[:80])
    return "\n\n".join(paragraphs).rstrip()
