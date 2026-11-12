"""Financial profile onboarding wizard (3-page MCQ).

Shown once after the first login, when `age_range` is empty in the DB.
Collects 11 CA-style questions that personalise every agent's response —
risk appetite from revealed loss behaviour, monthly investable budget for
SIP feasibility warnings, emergency fund status for portfolio prioritisation,
tax regime for ELSS vs NPS suggestions, and so on.

Design rules
------------
- Skippable: "Skip for now" exits without writing to DB; the wizard re-appears
  next login until completed. Users who skip see the same app, just without
  personalisation beyond the sidebar controls.
- 3 pages of 3-4 questions each so it never feels overwhelming.
- Loss behaviour (Q9 on page 3) overwrites `risk_appetite` in the DB because
  revealed preference under loss is more reliable than a self-label.
- Nothing here imports `core.compliance` or touches `graph_state` directly.
  It writes to the DB; `session.sync_profile()` picks up the new fields on the
  next rerun.
"""

from __future__ import annotations

import streamlit as st

# ── answer option maps ─────────────────────────────────────────────────────────
# (display label → stored value)

AGE_OPTIONS: dict[str, str] = {
    "Under 25": "under_25",
    "25–35": "25_35",
    "35–45": "35_45",
    "45–55": "45_55",
    "55+": "55_plus",
}

LIFE_OPTIONS: dict[str, str] = {
    "Single, no dependents": "single_no_dep",
    "Married, no children": "married_no_kids",
    "Married with children": "married_kids",
    "Single parent": "single_parent",
    "Near retirement (within 5 years)": "near_retirement",
}

EMPLOYMENT_OPTIONS: dict[str, str] = {
    "Salaried — private sector": "salaried_private",
    "Salaried — government / PSU": "salaried_govt",
    "Self-employed / freelancer": "self_employed",
    "Business owner": "business_owner",
    "Student / not yet earning": "student",
}

INCOME_OPTIONS: dict[str, str] = {
    "Under ₹30,000 / month": "under_30k",
    "₹30,000–₹75,000 / month": "30k_75k",
    "₹75,000–₹1.5 lakh / month": "75k_1_5l",
    "₹1.5–₹3 lakh / month": "1_5l_3l",
    "Above ₹3 lakh / month": "above_3l",
}

INVESTABLE_OPTIONS: dict[str, str] = {
    "Under ₹5,000": "under_5k",
    "₹5,000–₹15,000": "5k_15k",
    "₹15,000–₹50,000": "15k_50k",
    "₹50,000–₹1 lakh": "50k_1l",
    "Above ₹1 lakh": "above_1l",
}

EMERGENCY_OPTIONS: dict[str, str] = {
    "None / under 1 month": "none",
    "1–3 months": "1_to_3",
    "3–6 months (CA-recommended minimum)": "3_to_6",
    "More than 6 months": "above_6",
}

DEBT_OPTIONS: dict[str, str] = {
    "None": "none",
    "Under ₹5 lakh (personal loan / credit card)": "under_5l",
    "₹5–₹25 lakh": "5l_25l",
    "₹25 lakh–₹1 crore (typically home loan)": "25l_1cr",
    "Above ₹1 crore": "above_1cr",
}

INSURANCE_OPTIONS: dict[str, str] = {
    "No life or health insurance": "none",
    "Health insurance only": "health_only",
    "Both — term life plan + health insurance ✓": "term_and_health",
    "ULIPs or endowment policies only": "ulip_only",
}

LOSS_OPTIONS: dict[str, str] = {
    "Sell everything — I cannot afford to lose this money": "sell_all",
    "Sell some — I'd reduce exposure to stop the bleeding": "sell_some",
    "Hold — market cycles, I'll wait it out": "hold",
    "Buy more — it's a discount": "buy_more",
}

EXPERIENCE_OPTIONS: dict[str, str] = {
    "FD, savings account, PPF only — never invested in markets": "fd_only",
    "Some experience — SIPs or mutual funds, 1–3 years": "some_mf",
    "Comfortable — direct equity, ETFs, 3+ years": "comfortable_equity",
    "Active investor — I research and manage my own portfolio": "active_investor",
}

GOAL_OPTIONS: dict[str, str] = {
    "Build an emergency fund": "emergency_fund",
    "Buy a home / pay down home loan": "home",
    "Save for child's education": "education",
    "Retire early / build retirement corpus": "retirement",
    "General wealth creation / FIRE": "wealth_creation",
}

TAX_OPTIONS: dict[str, str] = {
    "I haven't used my ₹1.5 lakh 80C limit yet": "old_unused_80c",
    "I use 80C (ELSS, PPF, LIC) but haven't explored further": "old_uses_80c",
    "I actively use 80C, 80D, NPS, HRA — full optimisation": "old_optimised",
    "I'm on the new tax regime (opted out of deductions)": "new_regime",
}

# Loss behaviour → risk appetite mapping
_LOSS_TO_RISK: dict[str, str] = {
    "sell_all": "conservative",
    "sell_some": "conservative",
    "hold": "moderate",
    "buy_more": "aggressive",
}


# ── public helpers ─────────────────────────────────────────────────────────────


def is_profile_complete(user: dict) -> bool:
    """True when the onboarding wizard has been completed at least once."""
    return bool(user.get("age_range"))


# ── rendering ──────────────────────────────────────────────────────────────────


def render(user_id: str) -> None:
    """Render the wizard. Calls `st.stop()` until the user finishes or skips."""

    step = st.session_state.get("wizard_step", 1)

    st.markdown("## 💰 Finnie — Let's personalise your experience")
    st.caption(
        "A CA collects this before advising. These 11 questions let Finnie give "
        "you relevant guidance instead of generic answers. Takes about 90 seconds."
    )

    progress_labels = ["About you", "Financial health", "Goals & behaviour"]
    st.progress(step / 3, text=f"Step {step} of 3 — {progress_labels[step - 1]}")
    st.divider()

    if step == 1:
        _page_1()
    elif step == 2:
        _page_2()
    elif step == 3:
        _page_3(user_id)

    st.divider()
    if st.button("Skip for now — I'll set this up later", use_container_width=False):
        st.session_state.profile_wizard_skipped = True
        st.rerun()

    st.stop()


# ── pages ──────────────────────────────────────────────────────────────────────


def _radio(label: str, options: dict[str, str], key: str, help: str = "") -> None:
    """Render a radio group from a {display: value} dict."""
    st.radio(label, list(options.keys()), key=key, help=help)


def _page_1() -> None:
    st.markdown("### 👤 About you")
    with st.form("wizard_p1"):
        _radio(
            "**Q1.** Your age range",
            AGE_OPTIONS,
            key="wiz_age",
            help="Time horizon and compounding runway depend on this.",
        )
        _radio(
            "**Q2.** Your life stage",
            LIFE_OPTIONS,
            key="wiz_life",
            help="Dependents change your emergency fund size and insurance needs.",
        )
        _radio(
            "**Q3.** Employment type",
            EMPLOYMENT_OPTIONS,
            key="wiz_employment",
            help="Govt employees have a pension — that's already a 'bond' in their retirement plan.",
        )
        _radio(
            "**Q4.** Monthly household take-home income",
            INCOME_OPTIONS,
            key="wiz_income",
        )
        if st.form_submit_button("Next → Financial health", use_container_width=True, type="primary"):
            st.session_state.wizard_step = 2
            st.rerun()


def _page_2() -> None:
    st.markdown("### 🏦 Your financial health")
    with st.form("wizard_p2"):
        _radio(
            "**Q5.** How much can you invest monthly? (after all expenses and EMIs)",
            INVESTABLE_OPTIONS,
            key="wiz_investable",
            help="If the required SIP exceeds this, Finnie will flag it.",
        )
        _radio(
            "**Q6.** Emergency fund — how many months of expenses do you have saved?",
            EMERGENCY_OPTIONS,
            key="wiz_emergency",
            help="A CA won't recommend equity SIPs until you have 3–6 months covered.",
        )
        _radio(
            "**Q7.** Total outstanding loans and debt",
            DEBT_OPTIONS,
            key="wiz_debt",
            help="High-interest debt (>12%) mathematically beats most SIP returns.",
        )
        _radio(
            "**Q8.** Insurance coverage",
            INSURANCE_OPTIONS,
            key="wiz_insurance",
            help="ULIPs mix insurance and investment poorly. A CA's first observation is often 'surrender the ULIP, get a term plan + SIP.'",
        )
        if st.form_submit_button("Next → Goals & behaviour", use_container_width=True, type="primary"):
            st.session_state.wizard_step = 3
            st.rerun()


def _page_3(user_id: str) -> None:
    st.markdown("### 🎯 Goals & investment behaviour")
    with st.form("wizard_p3"):
        _radio(
            "**Q9.** If your portfolio drops 25% in 3 months, you would:",
            LOSS_OPTIONS,
            key="wiz_loss",
            help="This is the actual risk tolerance test. Behaviour under loss is more reliable than a self-label.",
        )
        _radio(
            "**Q10.** Your investment experience",
            EXPERIENCE_OPTIONS,
            key="wiz_experience",
            help="Adjusts how Finnie explains things — a beginner gets plain language, an active investor gets asset class weights.",
        )
        _radio(
            "**Q11.** Your biggest financial goal in the next 10 years",
            GOAL_OPTIONS,
            key="wiz_goal",
        )
        _radio(
            "**Q12.** Tax planning status",
            TAX_OPTIONS,
            key="wiz_tax",
            help="If you're on the old regime with unused 80C, Finnie will suggest ELSS as your equity SIP vehicle — same return as an index fund, saves up to ₹46,800/year at the 30% bracket.",
        )
        if st.form_submit_button("✅ Complete profile", use_container_width=True, type="primary"):
            _save(user_id)
            st.session_state.wizard_step = 1
            st.session_state.profile_wizard_done = True
            st.success("Profile saved! Finnie will now give you personalised guidance.")
            st.rerun()


def _save(user_id: str) -> None:
    """Write all wizard answers to the DB and update session state."""
    from web_app.auth import update_user_financial_profile

    # Map display labels back to stored values using the option dicts
    def _val(key: str, options: dict[str, str]) -> str:
        label = st.session_state.get(key, "")
        return options.get(label, label)

    age = _val("wiz_age", AGE_OPTIONS)
    life = _val("wiz_life", LIFE_OPTIONS)
    emp = _val("wiz_employment", EMPLOYMENT_OPTIONS)
    investable = _val("wiz_investable", INVESTABLE_OPTIONS)
    emergency = _val("wiz_emergency", EMERGENCY_OPTIONS)
    debt = _val("wiz_debt", DEBT_OPTIONS)
    insurance = _val("wiz_insurance", INSURANCE_OPTIONS)
    tax = _val("wiz_tax", TAX_OPTIONS)
    experience = _val("wiz_experience", EXPERIENCE_OPTIONS)
    goal = _val("wiz_goal", GOAL_OPTIONS)
    loss = _val("wiz_loss", LOSS_OPTIONS)
    risk = _LOSS_TO_RISK.get(loss, "moderate")

    update_user_financial_profile(
        user_id,
        age_range=age,
        life_stage=life,
        employment_type=emp,
        monthly_investable=investable,
        emergency_fund_months=emergency,
        debt_band=debt,
        insurance_status=insurance,
        tax_regime=tax,
        investment_experience=experience,
        primary_goal=goal,
        loss_behaviour=loss,
        risk_appetite=risk,
    )

    # Update session state so sidebar and sync_profile pick up the new risk
    st.session_state.profile_risk = risk
    fp = st.session_state.get("financial_profile") or {}
    fp.update({
        "age_range": age, "life_stage": life, "employment_type": emp,
        "monthly_investable": investable, "emergency_fund_months": emergency,
        "debt_band": debt, "insurance_status": insurance, "tax_regime": tax,
        "investment_experience": experience, "primary_goal": goal,
        "loss_behaviour": loss,
    })
    st.session_state.financial_profile = fp
