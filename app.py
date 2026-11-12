"""Finnie — Streamlit entry point (PRD §6.5a).

    streamlit run app.py

This file is deliberately thin: page config, the sidebar, the always-on
disclaimer banner, and four `st.tabs` that each delegate to a module in
`src/web_app/tabs/`. No business logic, no arithmetic, no prompt text.

Why the entry point stays at the repository root (PRD §7.5 / D3, resolved here)
------------------------------------------------------------------------------
Streamlit Cloud asks for a main file path and the documented local command is
`streamlit run app.py`, so a root entry point is the least surprising thing for
anyone who clones this. The *implementation* lives in `src/web_app/`, which is
what `src/web_app/` being empty was previously hiding. One file at the root, the
code in the package, and the Dockerfile and the deploy config agree.

What this file must never do
----------------------------
Import `core.compliance`. The disclaimer is appended by a terminal graph node
(PRD §7.5 / D1), and a second application here would double it — the exact defect
found live on 2026-11-08. Two tests in `tests/test_graph.py` assert that this
file does not call the guard.
"""

from __future__ import annotations

import sys
from pathlib import Path

# src/ on the path before any Finnie import. One import convention everywhere:
# `from core.x import ...`, never `src.core.x`.
sys.path.insert(0, str(Path(__file__).parent / "src"))

import streamlit as st  # noqa: E402

st.set_page_config(
    page_title="Finnie — AI Finance Assistant",
    page_icon="💰",
    layout="wide",
    initial_sidebar_state="expanded",
)

from web_app import session  # noqa: E402
from web_app.auth import create_user, verify_user  # noqa: E402

# ── Streamlit Cloud: inject secrets into os.environ before config loads ────────
# On Streamlit Cloud, secrets live in st.secrets (not a .env file).
# load_config() reads os.environ, so we bridge them here. The try/except
# means local dev with a .env file still works without a secrets.toml.
import os as _os  # noqa: E402
try:
    for _k, _v in st.secrets.items():
        if isinstance(_v, str):
            _os.environ.setdefault(_k, _v)
except Exception:  # noqa: BLE001 - no secrets file in local dev
    pass
from web_app.formatting import format_inr_compact  # noqa: E402
from web_app.profile_wizard import is_profile_complete, render as render_wizard  # noqa: E402
from web_app.session import KNOWLEDGE_LEVELS, RISK_LEVELS  # noqa: E402
from web_app.tabs import chat, goals, market, news, portfolio, tax  # noqa: E402


# ── authentication gate ────────────────────────────────────────────────────────
#
# Runs on every Streamlit rerun before any other UI. If the user is not logged
# in, we show the login/signup form and call st.stop() to prevent the main app
# from rendering. Once authenticated, `st.session_state.user_id` and
# `st.session_state.username` are set and the gate passes on every subsequent
# rerun until the user logs out (which deletes those keys).


def _login_gate() -> None:
    """Render the login/signup UI. Returns only when the user is authenticated."""
    if st.session_state.get("authenticated"):
        return

    st.markdown("## 💰 Finnie — AI Finance Assistant")
    st.caption("Personal finance education for Indian investors. Sign in to save your history.")
    st.divider()

    login_tab, signup_tab = st.tabs(["🔑 Log in", "✨ Sign up"])

    with login_tab:
        with st.form("login_form"):
            username = st.text_input("Username")
            password = st.text_input("Password", type="password")
            submitted = st.form_submit_button("Log in", use_container_width=True)

        if submitted:
            if not username or not password:
                st.error("Please enter both username and password.")
            else:
                user = verify_user(username, password)
                if user is None:
                    st.error("Incorrect username or password.")
                else:
                    _set_authenticated(user)
                    st.rerun()

    with signup_tab:
        with st.form("signup_form"):
            new_username = st.text_input("Choose a username")
            new_password = st.text_input("Choose a password", type="password")
            confirm = st.text_input("Confirm password", type="password")
            knowledge = st.selectbox(
                "Finance knowledge level",
                options=list(KNOWLEDGE_LEVELS),
                help="Finnie adjusts explanations to your level.",
            )
            submitted_signup = st.form_submit_button("Create account", use_container_width=True)

        if submitted_signup:
            if not new_username or not new_password:
                st.error("Username and password are required.")
            elif new_password != confirm:
                st.error("Passwords do not match.")
            elif len(new_password) < 6:
                st.error("Password must be at least 6 characters.")
            else:
                user = create_user(
                    new_username,
                    new_password,
                    knowledge_level=knowledge,
                )
                if user is None:
                    st.error(f"Username '{new_username}' is already taken. Please choose another.")
                else:
                    _set_authenticated(user)
                    st.success(f"Welcome, {user['username']}! Your account has been created.")
                    st.rerun()

    st.stop()


def _set_authenticated(user: dict) -> None:
    """Write auth state and load any previous conversation from the checkpointer."""
    st.session_state.authenticated = True
    st.session_state.user_id = user["id"]
    st.session_state.username = user["username"]
    # Seed sidebar widgets from the saved profile before init_session runs.
    st.session_state.profile_risk = user.get("risk_appetite", "moderate")
    st.session_state.profile_horizon = user.get("horizon_years", 10)
    st.session_state.profile_knowledge = user.get("knowledge_level", "beginner")
    # Load financial profile fields so sync_profile() can pass them to agents.
    st.session_state.financial_profile = {
        k: user.get(k, "")
        for k in (
            "age_range", "life_stage", "employment_type", "monthly_investable",
            "emergency_fund_months", "debt_band", "insurance_status",
            "tax_regime", "investment_experience", "primary_goal", "loss_behaviour",
        )
    }


@st.cache_resource(show_spinner="Building knowledge-base index (first run only, ~60s)…")
def _ensure_index() -> None:
    """Build the Chroma index if it doesn't exist yet.

    On Streamlit Cloud there is no pre-built index — this runs once after the
    first deploy and is a no-op on every subsequent request (cache_resource
    persists for the lifetime of the server process).

    All imports are inside the try block: importing rag.vector_store triggers
    get_logger → load_config at module level, which raises if OPENAI_API_KEY
    is absent. The except catches that and lets the app start anyway (RAG
    answers will be empty until the key is configured).
    """
    try:
        import sys
        from pathlib import Path as _Path
        sys.path.insert(0, str(_Path(__file__).parent / "src"))
        from core.config import load_config as _load_config
        from rag.vector_store import collection_count, get_or_create_collection
        from rag.vector_store import get_client as _get_chroma

        cfg = _load_config()
        client = _get_chroma(cfg.resolve(cfg.rag.index_dir))
        col = get_or_create_collection(client)
        if collection_count(col) > 0:
            return  # already indexed
        sys.path.insert(0, str(_Path(__file__).parent / "scripts"))
        from build_index import build as _build  # type: ignore[import]
        _build(rebuild=False)
    except Exception:  # noqa: BLE001 - index failure must not crash the app
        pass


_ensure_index()
_login_gate()

# ── profile wizard gate ────────────────────────────────────────────────────────
#
# After the user logs in for the first time (age_range is empty), show the
# 3-page MCQ wizard. It calls st.stop() until the user finishes or skips.
# `profile_wizard_done` and `profile_wizard_skipped` are session-only flags;
# on the next login the check re-runs against the DB record.

_user_id = st.session_state.get("user_id")
if _user_id and not st.session_state.get("profile_wizard_done") and not st.session_state.get("profile_wizard_skipped"):
    _fp = st.session_state.get("financial_profile") or {}
    if not _fp.get("age_range"):
        # Also check DB in case session_state is stale
        from web_app.auth import get_user as _get_user
        _db_user = _get_user(_user_id)
        if _db_user and not is_profile_complete(_db_user):
            render_wizard(_user_id)
        else:
            st.session_state.profile_wizard_done = True
    else:
        st.session_state.profile_wizard_done = True

# ── main app ───────────────────────────────────────────────────────────────────

session.init_session()
# After init, restore previous conversation from the checkpointer (if any).
if not st.session_state.get("history_loaded"):
    session.load_user_history()
    st.session_state.history_loaded = True

# Before the tabs run, from the values the widgets stored last time. The widgets
# themselves are created at the bottom of this file — see why there.
session.sync_profile()


# ── the always-on banner (§6.5a) ───────────────────────────────────────────────

st.warning(
    "**Educational information only — not financial advice.** Finnie explains how "
    "things work and what the numbers say. It never recommends a trade, and it "
    "cannot know your full circumstances.",
    icon="⚠️",
)


# ── tabs ───────────────────────────────────────────────────────────────────────

chat_tab, portfolio_tab, market_tab, goals_tab, news_tab, tax_tab = st.tabs(
    ["💬 Chat", "📊 Portfolio", "📈 Market", "🎯 Goals", "📰 News", "🧾 Tax"]
)

with chat_tab:
    chat.render()

with portfolio_tab:
    portfolio.render()

with market_tab:
    market.render()

with goals_tab:
    goals.render()

with news_tab:
    news.render()

with tax_tab:
    tax.render()


# ── sidebar, rendered last ─────────────────────────────────────────────────────
#
# `with st.sidebar:` places content in the sidebar wherever it appears in the
# script, so the *position in the file* is free — and it has to be last. The
# session meter counts a turn that one of the tabs above has just run; rendered
# first, it read the counters before that turn happened and showed "Turns 0"
# directly beneath a freshly generated answer. Spotted in the browser on
# 2026-11-08.
#
# The profile widgets can safely be created down here: the tabs read
# `st.session_state.profile_*`, which holds whatever the widget stored on the
# previous interaction, and `init_session()` seeds the defaults.

with st.sidebar:
    username = st.session_state.get("username", "")
    st.markdown(f"## 💰 Finnie")
    st.caption(f"Logged in as **{username}**" if username else "AI finance assistant.")

    if st.button("Log out", use_container_width=True):
        # Persist any profile changes before clearing session.
        from web_app.auth import update_user_profile
        user_id = st.session_state.get("user_id")
        if user_id:
            update_user_profile(
                user_id,
                risk_appetite=st.session_state.get("profile_risk", "moderate"),
                horizon_years=int(st.session_state.get("profile_horizon", 10)),
                knowledge_level=st.session_state.get("profile_knowledge", "beginner"),
            )
        for key in list(st.session_state.keys()):
            del st.session_state[key]
        st.rerun()

    st.divider()
    st.markdown("##### Your profile")
    st.select_slider(
        "Risk appetite",
        options=list(RISK_LEVELS),
        key="profile_risk",
        help="Sets the assumed return the Goal agent plans with.",
    )
    st.number_input("Horizon (years)", min_value=1, max_value=50, step=1, key="profile_horizon")
    st.selectbox("Knowledge level", options=list(KNOWLEDGE_LEVELS), key="profile_knowledge")
    session.sync_profile()

    # Persist profile changes to the DB so they survive a logout/login cycle.
    _user_id = st.session_state.get("user_id")
    if _user_id:
        from web_app.auth import update_user_profile
        update_user_profile(
            _user_id,
            risk_appetite=st.session_state.profile_risk,
            horizon_years=int(st.session_state.profile_horizon),
            knowledge_level=st.session_state.profile_knowledge,
        )

    st.divider()
    st.markdown("##### This session")
    usage = session.session_usage()
    left, right = st.columns(2)
    left.metric("Turns", usage["turns"])
    right.metric("Avg latency", f"{usage['avg_latency']:.1f}s" if usage["turns"] else "—")

    if usage["tokens"]:
        left, right = st.columns(2)
        left.metric("Tokens", f"{usage['tokens']:,}")
        right.metric("Est. cost", f"${usage['cost_usd']:.4f}")
    else:
        st.caption("Token meter starts after the first answer.")

    if st.button("Clear conversation", use_container_width=True):
        session.clear_conversation()
        for key in ("portfolio_result", "market_result", "goal_result", "goal_inputs"):
            st.session_state.pop(key, None)
        st.rerun()

    holdings = session.holdings()
    if holdings:
        total = session.analysis().get("total_value")
        st.caption(
            f"{len(holdings)} holdings saved"
            + (f" · {format_inr_compact(total)}" if total else "")
        )

    st.divider()
    st.caption(
        "Prices come from yfinance (Yahoo), which redistributes the exchange feed "
        "with a delay of roughly 15 minutes. Fit for learning, not for trading."
    )
