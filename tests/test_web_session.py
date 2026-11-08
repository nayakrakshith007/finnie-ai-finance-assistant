"""Tests for the UI's message contract (PRD §6.5a).

Why this file exists
--------------------
On 2026-11-08 every chat turn crashed with `KeyError: 'content'`. `run_turn`
produced a result keyed `answer` and spread it into the transcript with
`{"role": "assistant", **result}`; `chat.render()` read `message["content"]`,
which was never there. 585 tests passed throughout, because not one of them
rendered a tab.

Streamlit pages are awkward to unit test and mostly not worth it — but the
*contract between two modules* is not a Streamlit problem, it is an ordinary
interface that happened to live in UI code. So the message shape is built by two
plain functions, and these tests hold the producer and the consumer to the same
keys. That is the part that broke, and it is now the part that is checked.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from web_app.session import assistant_message, user_message

RESULT = {
    "answer": "A SIP is a monthly investment into a mutual fund.",
    "sources": [{"title": "What is a SIP", "url": "https://example.com"}],
    "trace": [{"agent": "finance_qa", "status": "ok", "latency_ms": 12.0, "detail": "ran"}],
    "latency": 1.5,
    "error": None,
}


def test_a_user_message_has_a_role_and_content():
    message = user_message("What is a SIP?")
    assert message["role"] == "user"
    assert message["content"] == "What is a SIP?"


def test_an_assistant_message_puts_the_answer_under_content():
    """The specific bug: the answer arrived as `answer`, the renderer read
    `content`, and nothing in between noticed."""
    message = assistant_message(RESULT)
    assert message["role"] == "assistant"
    assert message["content"] == RESULT["answer"]


def test_an_assistant_message_carries_its_sources_and_trace():
    message = assistant_message(RESULT)
    assert message["sources"] == RESULT["sources"]
    assert message["trace"] == RESULT["trace"]
    assert message["latency"] == 1.5


def test_a_degraded_result_still_produces_a_renderable_message():
    """A turn that failed must still render: the renderer indexes `content`
    unconditionally, so an empty result cannot be allowed to omit it."""
    message = assistant_message({})
    assert message["content"] == ""
    assert message["sources"] == []
    assert message["trace"] == []


def test_none_sources_become_an_empty_list_not_none():
    """`for s in None` is the next crash along."""
    message = assistant_message({"answer": "x", "sources": None, "trace": None})
    assert message["sources"] == []
    assert message["trace"] == []


# ── producer and consumer agree ────────────────────────────────────────────────


def _keys_read_by(path: Path, variable: str) -> set[str]:
    """Every string key read as `variable[...]` or `variable.get(...)` in a file.

    Parsed rather than grepped so a key inside a comment or a docstring cannot
    produce a false positive.
    """
    tree = ast.parse(path.read_text(encoding="utf-8"))
    keys: set[str] = set()

    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Subscript)
            and isinstance(node.value, ast.Name)
            and node.value.id == variable
            and isinstance(node.slice, ast.Constant)
            and isinstance(node.slice.value, str)
        ):
            keys.add(node.slice.value)
        elif (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "get"
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id == variable
            and node.args
            and isinstance(node.args[0], ast.Constant)
            and isinstance(node.args[0].value, str)
        ):
            keys.add(node.args[0].value)
    return keys


def test_the_chat_renderer_reads_only_keys_the_producer_writes():
    """The assertion that would have caught the KeyError before the browser did."""
    chat_py = Path(__file__).resolve().parents[1] / "src" / "web_app" / "tabs" / "chat.py"
    read = _keys_read_by(chat_py, "message")
    produced = set(assistant_message(RESULT)) | set(user_message("q"))

    missing = read - produced
    assert not missing, f"chat.py reads {sorted(missing)}, which no message carries"


@pytest.mark.parametrize("key", ["role", "content"])
def test_both_message_kinds_carry_the_keys_the_renderer_always_indexes(key):
    """`role` and `content` are read unconditionally for every message, so both
    kinds must have them — a user message with no `content` crashes the same way."""
    assert key in user_message("q")
    assert key in assistant_message(RESULT)
