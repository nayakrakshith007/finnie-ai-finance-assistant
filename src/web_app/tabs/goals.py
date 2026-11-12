"""Goals tab (PRD §6.5a, FR-013, FR-063, FR-064).

Layout:
  1. Goal inputs — up to 3 goals, each with name / type / target / horizon
  2. Work out the plan button
  3. Per-goal result cards — SIP, Investment vs Returns chart, CA note
  4. Holistic summary — total monthly SIP, goal table, 80C benefit, priority order
  5. Goal chat — follow-up Q&A

All calculations are pure-function (no LLM). The CA layer (financial instrument
recommendation, tax angle, 80C eligibility) comes from `goals/instruments.py`.
"""

from __future__ import annotations

import pandas as pd
import streamlit as st

from core.config import load_config
from goals.instruments import recommend as recommend_instrument
from goals.projections import (
    allocation_template,
    blended_return,
    equity_was_capped,
    inflation_adjusted_target,
    projection_series,
    required_monthly_sip,
)
from web_app import session
from web_app.charts import goal_projection_area
from web_app.formatting import format_inr, format_inr_compact, format_pct

# ── constants ─────────────────────────────────────────────────────────────────

GOAL_TYPE_LABELS = {
    "general":    "General / Custom",
    "emergency":  "Emergency Fund",
    "home":       "Home / Property",
    "education":  "Education / Children",
    "retirement": "Retirement",
}

MAX_GOALS = 5


# ── compute helper ─────────────────────────────────────────────────────────────

def _compute_goal(
    target: float,
    horizon: float,
    goal_type: str,
    risk: str,
) -> dict:
    """Compute one goal — pure maths + CA layer, zero LLM cost."""
    cfg = load_config()
    inflation = cfg.goals.inflation_rate
    alloc = allocation_template(risk, horizon)
    rate = blended_return(alloc)
    adjusted = inflation_adjusted_target(target, inflation, horizon)
    sip = required_monthly_sip(adjusted, rate, horizon)
    ca_rec = recommend_instrument(horizon, goal_type, risk)
    # Monthly projection series for the chart
    proj = _monthly_projection(sip, rate, horizon)
    return {
        "target_amount": target,
        "horizon_years": horizon,
        "goal_type": goal_type,
        "risk_appetite": risk,
        "assumed_return": rate,
        "assumed_inflation": inflation,
        "inflation_adjusted_target": adjusted,
        "required_monthly_sip": sip,
        "allocation": alloc,
        "equity_capped": equity_was_capped(risk, horizon),
        "projection": proj,
        "ca_instrument": ca_rec.vehicle,
        "ca_note": ca_rec.ca_note,
        "ca_tax_note": ca_rec.tax_note,
        "ca_80c": ca_rec.sec_80c,
    }


def _monthly_projection(sip: float, annual_rate: float, horizon_years: float) -> list[dict]:
    """Month-by-month corpus split into contributions and growth."""
    monthly_rate = annual_rate / 12
    months = int(horizon_years * 12)
    points = [{"month": 0, "value": 0.0, "contributed": 0.0, "growth": 0.0}]
    corpus = 0.0
    for m in range(1, months + 1):
        corpus = corpus * (1 + monthly_rate) + sip
        contributed = round(sip * m, 2)
        growth = round(corpus - contributed, 2)
        points.append({
            "month": m,
            "value": round(corpus, 2),
            "contributed": contributed,
            "growth": max(growth, 0.0),
        })
    return points


def _monthly_proj_to_yearly(monthly_proj: list[dict]) -> list[dict]:
    """Downsample monthly projection to yearly points for the area chart."""
    # goal_projection_area expects dicts with key "year"
    yearly = []
    for pt in monthly_proj:
        m = pt["month"]
        if m % 12 == 0:
            yearly.append({
                "year": m // 12,
                "value": pt["value"],
                "contributed": pt["contributed"],
                "growth": pt["growth"],
            })
    return yearly


# ── main render ────────────────────────────────────────────────────────────────

def render() -> None:
    if "goals" not in st.session_state:
        st.session_state.goals = []

    _render_goals_input()

    asked = st.button("Work out the plan", type="primary")
    if asked:
        goals = st.session_state.goals
        if not goals:
            st.warning("Add at least one goal first.")
            return
        risk = (st.session_state.get("user_profile") or {}).get("risk_appetite", "moderate")
        with st.spinner("Crunching the numbers…"):
            results = []
            for g in goals:
                if g.get("target_amount") and g.get("horizon_years"):
                    results.append({
                        "name": g.get("name") or GOAL_TYPE_LABELS.get(g["goal_type"], "Goal"),
                        **_compute_goal(
                            float(g["target_amount"]),
                            float(g["horizon_years"]),
                            g.get("goal_type", "general"),
                            risk,
                        ),
                    })
            st.session_state.goal_results = results

    results = st.session_state.get("goal_results")
    if not results:
        st.info("Add your goals above, then press **Work out the plan**.")
        return

    # ── per-goal cards ────────────────────────────────────────────────────────
    st.divider()
    for plan in results:
        _render_goal_card(plan)

    # ── holistic summary ──────────────────────────────────────────────────────
    if len(results) > 1:
        st.divider()
        _render_holistic_summary(results)

    # ── goal chat ─────────────────────────────────────────────────────────────
    _render_goal_chat()


# ── input section ──────────────────────────────────────────────────────────────

def _render_goals_input() -> None:
    goals = st.session_state.goals
    to_remove = None

    if goals:
        for i, g in enumerate(goals):
            st.markdown(f"**Goal {i + 1}**")
            r1, r2, r3, r4, r5 = st.columns([2, 1.5, 1.5, 1, 0.5])
            g["name"] = r1.text_input(
                "Name", value=g.get("name", ""), key=f"g_name_{i}",
                placeholder="e.g. Emergency fund",
            )
            g["goal_type"] = r2.selectbox(
                "Type", list(GOAL_TYPE_LABELS.keys()),
                format_func=lambda k: GOAL_TYPE_LABELS[k],
                index=list(GOAL_TYPE_LABELS.keys()).index(g.get("goal_type", "general")),
                key=f"g_type_{i}",
            )
            g["target_amount"] = r3.number_input(
                "Target (₹)", min_value=10_000, max_value=100_00_00_000,
                value=int(g.get("target_amount", 5_00_000)), step=50_000,
                key=f"g_target_{i}",
            )
            g["horizon_years"] = r4.number_input(
                "Years", min_value=1, max_value=50,
                value=int(g.get("horizon_years", 5)), key=f"g_horizon_{i}",
            )
            if r5.button("✕", key=f"g_remove_{i}", help="Remove"):
                to_remove = i

    if to_remove is not None:
        st.session_state.goals.pop(to_remove)
        st.rerun()

    if len(goals) < MAX_GOALS:
        if st.button("＋ Add goal"):
            st.session_state.goals.append({
                "name": "", "goal_type": "general",
                "target_amount": 5_00_000, "horizon_years": 5,
            })
            st.rerun()
    else:
        st.caption(f"Maximum {MAX_GOALS} goals.")


# ── per-goal card ──────────────────────────────────────────────────────────────

def _render_goal_card(plan: dict) -> None:
    name = plan.get("name") or GOAL_TYPE_LABELS.get(plan["goal_type"], "Goal")
    horizon = plan["horizon_years"]
    sip = plan["required_monthly_sip"]
    adjusted = plan["inflation_adjusted_target"]

    with st.expander(
        f"**{name}** — {format_inr(sip)}/month over {int(horizon)} years",
        expanded=True,
    ):
        c1, c2, c3 = st.columns(3)
        c1.metric("Monthly SIP", format_inr(sip))
        c2.metric("Inflation-adjusted target", format_inr_compact(adjusted))
        c3.metric(
            "Financial Instrument",
            plan.get("ca_instrument", "—"),
            help="Category, not a specific fund. See CA note below.",
        )

        if plan.get("equity_capped"):
            st.warning("Equity exposure capped — horizon is too short for full equity allocation.")

        # Investment vs Returns chart (monthly granularity)
        monthly_proj = plan.get("projection") or []
        if monthly_proj:
            yearly = _monthly_proj_to_yearly(monthly_proj)
            if yearly:
                fig = goal_projection_area(yearly, target=adjusted)
                fig.update_layout(
                    title=dict(text=f"{name} — Investment vs Returns", font_size=14),
                    xaxis_title="Years from now",
                )
                st.plotly_chart(fig, use_container_width=True)

        st.caption(
            f"Assumed return: **{format_pct(plan['assumed_return'] * 100, places=1)}** · "
            f"Inflation: **{format_pct(plan['assumed_inflation'] * 100, places=0)}** · "
            f"Real return: **{format_pct((plan['assumed_return'] - plan['assumed_inflation']) * 100, places=1)}**"
        )

        st.markdown(f"**📋 CA note** — {plan.get('ca_note', '')}")
        st.caption(f"**Tax** — {plan.get('ca_tax_note', '')}")
        if plan.get("ca_80c"):
            st.info("**Section 80C eligible** — this instrument type qualifies under 80C (up to ₹1.5L/yr).")

    st.caption(
        "⚠️ Projections assume constant returns and inflation. Actual results will differ. "
        "Educational information only — not financial advice."
    )


# ── holistic summary ───────────────────────────────────────────────────────────

def _render_holistic_summary(results: list[dict]) -> None:
    st.markdown("#### 📊 Holistic Summary")
    st.caption("A CA's first question: 'Can you actually fund all of this?'")

    total_sip = sum(r.get("required_monthly_sip", 0) for r in results)
    types_in_plan = [r.get("goal_type", "general") for r in results]
    has_emergency = "emergency" in types_in_plan

    if not has_emergency:
        st.warning(
            "**No emergency fund in this plan.** "
            "Every plan starts with 6 months of expenses in a liquid fund — "
            "it protects the other goals from an unexpected event."
        )

    st.metric(
        "Total monthly investment (all goals)",
        format_inr(total_sip),
        help="Sum of all required SIPs.",
    )

    rows = []
    eligible_goals = []
    for r in results:
        name = r.get("name") or GOAL_TYPE_LABELS.get(r["goal_type"], "Goal")
        rows.append({
            "Goal": name,
            "Horizon": f"{int(r['horizon_years'])}y",
            "Target": format_inr_compact(r["target_amount"]),
            "Monthly SIP": format_inr(r["required_monthly_sip"]),
            "Financial Instrument": r.get("ca_instrument", "—"),
            "80C": "✓" if r.get("ca_80c") else "—",
        })
        if r.get("ca_80c"):
            eligible_goals.append(name)

    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

    if eligible_goals:
        st.info(
            f"**Section 80C opportunity** — {', '.join(eligible_goals)} "
            f"{'is' if len(eligible_goals) == 1 else 'are'} commonly funded with "
            "80C-eligible instruments (ELSS, PPF, NPS). Aggregate ceiling: "
            "₹1.5L/yr — worth ₹46,800/yr at the 30% slab + 4% cess."
        )

    st.markdown("**CA's view on priority (shortest horizon first):**")
    for r in sorted(results, key=lambda x: x.get("horizon_years", 99)):
        name = r.get("name") or GOAL_TYPE_LABELS.get(r["goal_type"], "Goal")
        flag = "✅" if r.get("goal_type") == "emergency" else "•"
        st.markdown(
            f"{flag} **{name}** ({int(r['horizon_years'])}yr) — "
            f"{format_inr(r['required_monthly_sip'])}/mo in {r.get('ca_instrument', '—')}"
        )

    st.caption(
        "Fund each goal in its own bucket. A disrupted short-term goal "
        "forces you to redeem long-term equity at the worst time."
    )


# ── goal chat ──────────────────────────────────────────────────────────────────

def _render_goal_chat() -> None:
    st.divider()
    st.markdown("##### 💬 Ask about this plan")
    st.caption(
        '"What if I increase the SIP by ₹2,000?", "explain the allocation", '
        '"what does ELSS mean?", "is a home loan better than saving the full amount?"'
    )

    goal_chat = st.session_state.setdefault("goal_chat_messages", [])

    for msg in goal_chat:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])
            if msg["role"] == "assistant":
                from web_app.tabs.chat import render_trace as _rt, render_sources as _rs
                _rt(msg.get("trace") or [])
                _rs(msg.get("sources") or [])

    with st.form("goal_chat_form", clear_on_submit=True):
        follow_up = st.text_input(
            "Ask a follow-up…",
            placeholder="e.g. What if I step up the SIP by 10% each year?",
            label_visibility="collapsed",
        )
        sent = st.form_submit_button("Send", use_container_width=True, type="primary")

    if sent and follow_up:
        goal_chat.append({"role": "user", "content": follow_up})
        with st.spinner("Thinking…"):
            turn = session.run_turn(follow_up, record_in_chat=False)
        goal_chat.append({
            "role": "assistant",
            "content": turn.get("answer", ""),
            "trace": turn.get("trace") or [],
            "sources": turn.get("sources") or [],
        })
        st.rerun()
