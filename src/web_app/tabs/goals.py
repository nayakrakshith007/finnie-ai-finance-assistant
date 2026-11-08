"""Goals tab (PRD §6.5a, FR-013, FR-063, FR-064).

Layout: inputs in three columns, then the required-SIP metric, the
inflation-adjusted target, the projection area chart, and the allocation table.

Two things this tab is careful about.

**The assumption is never off-screen.** The required SIP is arithmetic on an
assumed return from `config.yaml`, so the assumed return and inflation sit
directly under the metric that depends on them. A projection whose assumption the
reader has to go looking for is a forecast, and this agent must never produce
one.

**The sidebar's risk appetite drives the answer.** That is FR-064's acceptance
criterion, so the caption under the SIP says which profile produced it — making
the connection visible rather than leaving the user to wonder why the number
changed when they moved a slider in a different part of the screen.
"""

from __future__ import annotations

import pandas as pd
import streamlit as st

from web_app import session
from web_app.charts import goal_projection_area
from web_app.formatting import format_inr, format_inr_compact, format_pct
from web_app.tabs.chat import render_trace

PRESETS = {
    "Custom": None,
    "Emergency fund (₹3 lakh, 2 years)": (3_00_000, 2),
    "House deposit (₹25 lakh, 7 years)": (25_00_000, 7),
    "Child's education (₹50 lakh, 15 years)": (50_00_000, 15),
    "Retirement (₹2 crore, 25 years)": (2_00_00_000, 25),
}


def render() -> None:
    preset = st.selectbox("Start from", list(PRESETS), index=0)
    if PRESETS[preset]:
        default_amount, default_years = PRESETS[preset]
    else:
        default_amount, default_years = 10_00_000, int(st.session_state.profile_horizon)

    left, middle, right = st.columns(3)
    target = left.number_input(
        "Target amount (₹)",
        min_value=10_000,
        max_value=100_00_00_000,
        value=default_amount,
        step=50_000,
        help="In today's money. Finnie inflates it to the money of the goal year.",
    )
    horizon = middle.number_input(
        "Horizon (years)", min_value=1, max_value=50, value=default_years, step=1
    )
    existing = right.number_input(
        "Already saved (₹)", min_value=0, max_value=100_00_00_000, value=0, step=50_000,
        help="Shown for context. The required SIP below is for the whole target.",
    )

    # Button-only, for the same reason as the Market tab: `st.tabs` runs every
    # tab's body on every rerun, so anything that acts without a click spends
    # money for someone who never opened this tab. It also means a stale plan is
    # shown rather than silently recomputed when a number changes — so the
    # caption below says which inputs the figures belong to.
    asked = st.button("Work out the plan", type="primary")
    if asked:
        with st.spinner("Working out the plan…"):
            st.session_state.goal_result = session.run_turn(
                f"I need {int(target)} rupees in {int(horizon)} years",
                record_in_chat=False,
            )
            st.session_state.goal_inputs = (target, horizon)
    elif "goal_result" not in st.session_state:
        st.info("Set a target and a horizon, then press **Work out the plan**.")
        return

    stale_for = st.session_state.get("goal_inputs")
    if stale_for and stale_for != (target, horizon):
        st.warning(
            f"These figures are for {format_inr_compact(stale_for[0])} over "
            f"{int(stale_for[1])} years. Press **Work out the plan** to use the "
            "values above."
        )

    result = st.session_state.get("goal_result") or {}
    plan = session.goal_params()
    if not plan.get("required_monthly_sip"):
        st.warning(result.get("answer") or "I could not work that out.")
        return

    left, middle, right = st.columns(3)
    left.metric(
        "Monthly SIP needed",
        format_inr(plan["required_monthly_sip"]),
        help="Sized against the inflation-adjusted target, not today's figure.",
    )
    middle.metric(
        "Inflation-adjusted target",
        format_inr_compact(plan["inflation_adjusted_target"]),
        help=f"{format_inr_compact(target)} of today's money, in {int(horizon)} years",
    )
    right.metric(
        "If inflation were ignored",
        format_inr(plan["required_monthly_sip_nominal"]),
        help="The gap between these two is what inflation costs this plan.",
    )

    st.caption(
        f"Assumes a **{format_pct(plan['assumed_return'] * 100, places=0)}** average annual "
        f"return (your *{plan['risk_appetite']}* profile, set in the sidebar) and "
        f"**{format_pct(plan['assumed_inflation'] * 100, places=0)}** inflation — a real "
        f"return of {format_pct(plan['real_return'] * 100)}. "
        "These are assumptions for the arithmetic, not predictions."
    )

    if existing:
        st.info(
            f"You already have {format_inr_compact(existing)}. The SIP above is for the "
            "whole target; growing what you have reduces what you need to add."
        )

    st.plotly_chart(
        goal_projection_area(plan.get("projection") or [], target=plan["inflation_adjusted_target"]),
        use_container_width=True,
    )

    allocation = plan.get("allocation") or {}
    if allocation:
        st.markdown("##### Starting allocation template")
        st.caption(
            "A commonly used starting point for this horizon and risk appetite — "
            "not a recommendation of what to hold."
        )
        frame = pd.DataFrame(
            [{"Exposure": name, "Share": format_pct(share)} for name, share in allocation.items()]
        )
        st.dataframe(frame, use_container_width=True, hide_index=True)
        if plan.get("equity_capped"):
            st.warning(
                "Equity is capped below your risk appetite because the horizon is "
                "short — there would be no time to recover from a bad run."
            )

    if result.get("answer"):
        st.markdown("##### What this means")
        st.markdown(result["answer"])
        render_trace(result.get("trace") or [])
