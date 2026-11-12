"""Persona test — 3 users with different finance knowledge levels.

Tests two things:
1. Each persona gets answers tailored to their knowledge level
   (the system prompt uses `knowledge_level` from `user_profile`).
2. Conversation history PERSISTS across simulated logins: each persona
   is run in two separate graph invocations with the same `thread_id`,
   and the second invocation can reference what was said in the first.

Run from the project root with:
    python scripts/test_personas.py

Requires a valid OPENAI_API_KEY in .env or the environment.
The checkpointer writes to data/memory.db.
"""

from __future__ import annotations

import sys
import textwrap
from pathlib import Path

# One import convention: src/ is the root.
sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

from dotenv import load_dotenv

load_dotenv()

from langchain_core.messages import HumanMessage  # noqa: E402
from web_app.auth import create_user, verify_user  # noqa: E402
from workflow.graph import build_production_graph  # noqa: E402
from workflow.state import UserProfile  # noqa: E402

# ── persona definitions ────────────────────────────────────────────────────────

PERSONAS = [
    {
        "username": "persona_priya",
        "password": "priya_pass_1",
        "profile": UserProfile(
            risk_appetite="conservative",
            horizon_years=5,
            knowledge_level="beginner",
        ),
        "description": "Priya — first-time investor, complete beginner",
        "session_1": [
            "What is a mutual fund?",
            "Is it safe to invest in one?",
        ],
        "session_2": [
            "You just explained mutual funds to me. What is the safest type for a beginner?",
        ],
    },
    {
        "username": "persona_raj",
        "password": "raj_pass_1",
        "profile": UserProfile(
            risk_appetite="moderate",
            horizon_years=15,
            knowledge_level="intermediate",
        ),
        "description": "Raj — knows SIP and mutual funds, wants to build a ₹1 Cr corpus",
        "session_1": [
            "I want to build a corpus of ₹1 crore in 15 years. How much SIP should I start?",
            "What is the CAGR assumption you used?",
        ],
        "session_2": [
            "Earlier you told me a monthly SIP amount for ₹1 Cr. If my goal is ₹2 Cr instead, how does the SIP change?",
        ],
    },
    {
        "username": "persona_vikram",
        "password": "vikram_pass_1",
        "profile": UserProfile(
            risk_appetite="aggressive",
            horizon_years=3,
            knowledge_level="advanced",
        ),
        "description": "Vikram — experienced investor, asks about LTCG tax optimisation",
        "session_1": [
            "What is the LTCG tax rate on equity mutual funds after July 2024?",
            "If I have ₹2 lakh gains this year, how much tax do I owe?",
        ],
        "session_2": [
            "In our previous conversation you explained LTCG tax. What is the STCG rate for the same equity funds?",
        ],
    },
]

# ── helpers ────────────────────────────────────────────────────────────────────

DIVIDER = "─" * 72


def _ensure_user(persona: dict) -> str:
    """Create the user if they don't exist; return their UUID."""
    user = verify_user(persona["username"], persona["password"])
    if user is None:
        user = create_user(
            persona["username"],
            persona["password"],
            risk_appetite=persona["profile"]["risk_appetite"],
            horizon_years=persona["profile"]["horizon_years"],
            knowledge_level=persona["profile"]["knowledge_level"],
        )
        if user is None:
            raise RuntimeError(f"Could not create user {persona['username']!r}")
        print(f"  Created user: {user['username']} (id={user['id'][:8]}…)")
    else:
        print(f"  Existing user: {user['username']} (id={user['id'][:8]}…)")
    return user["id"]


def _run_session(graph, thread_id: str, profile: UserProfile, questions: list[str]) -> None:
    """Run a list of questions through the graph as a single session."""
    config = {"configurable": {"thread_id": thread_id}}
    for q in questions:
        print(f"\n  Q: {q}")
        state = graph.invoke(
            {
                "messages": [HumanMessage(content=q)],
                "user_profile": dict(profile),
                "agent_trace": None,  # None resets trace for this turn
            },
            config=config,
        )
        answer = str(state["messages"][-1].content)
        # Print first 400 chars so the output is readable
        short = textwrap.fill(answer[:400] + ("…" if len(answer) > 400 else ""), width=68)
        print(f"  A: {short}")


def _count_turns(graph, thread_id: str) -> int:
    """Return the number of human messages saved in the checkpoint."""
    config = {"configurable": {"thread_id": thread_id}}
    try:
        snapshot = graph.get_state(config)
        if not snapshot or not snapshot.values:
            return 0
        messages = snapshot.values.get("messages") or []
        return sum(1 for m in messages if isinstance(m, HumanMessage))
    except Exception:
        return -1  # checkpointer unavailable


# ── main ───────────────────────────────────────────────────────────────────────


def main() -> None:
    print("\n" + DIVIDER)
    print("  FINNIE — PERSONA TEST")
    print(DIVIDER)

    print("\nBuilding graph with SQLite checkpointer…")
    graph = build_production_graph()
    print("Graph ready.\n")

    for persona in PERSONAS:
        print(DIVIDER)
        print(f"  PERSONA: {persona['description']}")
        print(DIVIDER)

        thread_id = _ensure_user(persona)

        # ── Session 1 ──────────────────────────────────────────────────────────
        print(f"\n  [Session 1] — {len(persona['session_1'])} question(s)")
        _run_session(graph, thread_id, persona["profile"], persona["session_1"])

        turns_after_s1 = _count_turns(graph, thread_id)
        print(f"\n  Checkpoint: {turns_after_s1} human turn(s) saved after Session 1.")

        # ── Session 2 (same thread_id = same user, new "login") ───────────────
        print(f"\n  [Session 2] — {len(persona['session_2'])} question(s) referencing Session 1")
        _run_session(graph, thread_id, persona["profile"], persona["session_2"])

        turns_after_s2 = _count_turns(graph, thread_id)
        print(f"\n  Checkpoint: {turns_after_s2} human turn(s) saved after Session 2.")

        expected = len(persona["session_1"]) + len(persona["session_2"])
        status = "✅ PASS" if turns_after_s2 == expected else f"❌ FAIL (expected {expected})"
        print(f"  Persistence check: {status}")
        print()

    print(DIVIDER)
    print("  All personas tested. See data/memory.db for the stored checkpoints.")
    print(DIVIDER + "\n")


if __name__ == "__main__":
    main()
