"""Logging configuration.

One rule for the rest of this project: **no `print()` anywhere in `src/`.**

`print` has no severity, no timestamp, no source module and no off switch.
When the router sends a tax question to the portfolio agent in week three, the
line you want in your terminal is:

    2026-11-04 18:02:11 | DEBUG    | src.workflow.router | classified -> portfolio (conf 0.41)

...and `print` cannot give you that.

Every module gets its logger the same way:

    from src.core.logging_setup import get_logger
    log = get_logger(__name__)

Using `__name__` means the logger is named after the module path, so the
hierarchy is automatic and you can later silence one noisy subsystem
(`logging.getLogger("src.rag").setLevel("WARNING")`) without touching it.
"""

from __future__ import annotations

import logging
import sys

_CONFIGURED = False


def setup_logging(level: str | None = None) -> None:
    """Configure the root logger once for the whole process.

    Safe to call multiple times — the _CONFIGURED guard makes every call
    after the first a no-op. This matters in Streamlit, which re-executes
    the entire script on every user interaction; without the guard, each
    interaction would add a duplicate handler and log lines would multiply.

    Args:
        level: Optional override for the log level (e.g. "DEBUG").
               When given, wins over whatever config.yaml says.
               Useful in tests: setup_logging("DEBUG") for verbose output.
    """
    global _CONFIGURED
    if _CONFIGURED:
        return

    # Deferred import — avoids a circular dependency.
    # config.py may call get_logger() during its own initialisation;
    # a top-level import here would create a cycle that crashes at startup.
    from core.config import get_config
    cfg = get_config()

    # level argument wins over config; config wins over Python's default WARNING.
    effective_level = level or cfg.logging.level
    fmt = logging.Formatter(cfg.logging.format)

    root = logging.getLogger()
    root.setLevel(effective_level)

    # ── StreamHandler — always present ────────────────────────────────────
    # Writes to sys.stdout so pytest captures it correctly
    # (pytest captures stdout, not stderr, by default).
    sh = logging.StreamHandler(sys.stdout)
    sh.setLevel(effective_level)
    sh.setFormatter(fmt)
    root.addHandler(sh)

    # ── FileHandler — optional, only if config.yaml sets logging.file ─────
    if cfg.logging.file:
        log_path = cfg.resolve(cfg.logging.file)
        # mkdir so the app doesn't crash if the logs/ directory doesn't exist yet.
        log_path.parent.mkdir(parents=True, exist_ok=True)
        # encoding="utf-8" is mandatory on Windows — the default cp1252 raises
        # on a rupee sign (₹) or an em dash in a compliance disclaimer string.
        fh = logging.FileHandler(log_path, encoding="utf-8")
        fh.setLevel(effective_level)
        fh.setFormatter(fmt)
        root.addHandler(fh)

    # ── Quiet noisy third-party libraries ─────────────────────────────────
    # At DEBUG, httpx and openai flood the terminal with HTTP wire logs.
    # Pin them to WARNING so your own DEBUG output stays readable.
    for noisy in ("httpx", "httpcore", "openai", "urllib3",
                  "sentence_transformers", "yfinance"):
        logging.getLogger(noisy).setLevel(logging.WARNING)

    _CONFIGURED = True


def get_logger(name: str) -> logging.Logger:
    """Return a module-named logger, configuring logging on first use.

    Usage in every src/ module:
        from src.core.logging_setup import get_logger
        log = get_logger(__name__)

    Using __name__ names the logger after its module path
    (e.g. "src.agents.portfolio"), which gives a free hierarchy:
    you can silence one noisy subsystem later without touching its code.

    Args:
        name: Typically __name__ from the calling module.

    Returns:
        A configured logging.Logger instance.
    """
    if not _CONFIGURED:
        setup_logging()
    return logging.getLogger(name)
