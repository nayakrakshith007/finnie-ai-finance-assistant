"""User authentication — sign-up, login, profile persistence.

SQLite-backed, no external auth dependency. Passwords stored as
PBKDF2-SHA256 (100 000 iterations) with a per-user random salt.

The `users.db` lives in the project's `data/` directory alongside the
ChromaDB index and the router query file. Each user gets a UUID that becomes
their LangGraph `thread_id`, so the checkpointer's history is namespaced per
user automatically.
"""

from __future__ import annotations

import hashlib
import secrets
import sqlite3
import uuid
from pathlib import Path
from typing import TypedDict

_DB_PATH = Path(__file__).parents[2] / "data" / "users.db"


class UserRecord(TypedDict, total=False):
    id: str
    username: str
    risk_appetite: str
    horizon_years: int
    knowledge_level: str
    topics_discussed: str  # comma-separated agent names seen across all sessions
    # Financial profile (collected via onboarding wizard)
    age_range: str           # "under_25" | "25_35" | "35_45" | "45_55" | "55_plus"
    life_stage: str          # "single_no_dep" | "married_no_kids" | "married_kids" | "single_parent" | "near_retirement"
    employment_type: str     # "salaried_private" | "salaried_govt" | "self_employed" | "business_owner" | "student"
    monthly_investable: str  # "under_5k" | "5k_15k" | "15k_50k" | "50k_1l" | "above_1l"
    emergency_fund_months: str  # "none" | "1_to_3" | "3_to_6" | "above_6"
    debt_band: str           # "none" | "under_5l" | "5l_25l" | "25l_1cr" | "above_1cr"
    insurance_status: str    # "none" | "health_only" | "term_and_health" | "ulip_only"
    tax_regime: str          # "old_unused_80c" | "old_uses_80c" | "old_optimised" | "new_regime"
    investment_experience: str  # "fd_only" | "some_mf" | "comfortable_equity" | "active_investor"
    primary_goal: str        # "emergency_fund" | "home" | "education" | "retirement" | "wealth_creation"
    loss_behaviour: str      # "sell_all" | "sell_some" | "hold" | "buy_more"


# ── DB setup ──────────────────────────────────────────────────────────────────


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(str(_DB_PATH), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    """Create the users table if it does not exist. Idempotent."""
    with _connect() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id              TEXT PRIMARY KEY,
                username        TEXT UNIQUE NOT NULL,
                password_hash   TEXT NOT NULL,
                salt            TEXT NOT NULL,
                risk_appetite   TEXT NOT NULL DEFAULT 'moderate',
                horizon_years   INTEGER NOT NULL DEFAULT 10,
                knowledge_level TEXT NOT NULL DEFAULT 'beginner',
                topics_discussed TEXT NOT NULL DEFAULT '',
                created_at      TEXT NOT NULL DEFAULT (datetime('now'))
            )
        """)
        # Migrations: each ALTER TABLE is idempotent (ignored if column already exists).
        _migrations = [
            "ALTER TABLE users ADD COLUMN topics_discussed TEXT NOT NULL DEFAULT ''",
            "ALTER TABLE users ADD COLUMN age_range TEXT NOT NULL DEFAULT ''",
            "ALTER TABLE users ADD COLUMN life_stage TEXT NOT NULL DEFAULT ''",
            "ALTER TABLE users ADD COLUMN employment_type TEXT NOT NULL DEFAULT ''",
            "ALTER TABLE users ADD COLUMN monthly_investable TEXT NOT NULL DEFAULT ''",
            "ALTER TABLE users ADD COLUMN emergency_fund_months TEXT NOT NULL DEFAULT ''",
            "ALTER TABLE users ADD COLUMN debt_band TEXT NOT NULL DEFAULT ''",
            "ALTER TABLE users ADD COLUMN insurance_status TEXT NOT NULL DEFAULT ''",
            "ALTER TABLE users ADD COLUMN tax_regime TEXT NOT NULL DEFAULT ''",
            "ALTER TABLE users ADD COLUMN investment_experience TEXT NOT NULL DEFAULT ''",
            "ALTER TABLE users ADD COLUMN primary_goal TEXT NOT NULL DEFAULT ''",
            "ALTER TABLE users ADD COLUMN loss_behaviour TEXT NOT NULL DEFAULT ''",
        ]
        for _sql in _migrations:
            try:
                conn.execute(_sql)
            except Exception:  # noqa: BLE001 - column already exists
                pass
        conn.commit()


# ── password hashing ──────────────────────────────────────────────────────────


def _hash_password(password: str, salt: str) -> str:
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 100_000)
    return dk.hex()


def _new_salt() -> str:
    return secrets.token_hex(16)


# ── public API ────────────────────────────────────────────────────────────────


def create_user(
    username: str,
    password: str,
    *,
    risk_appetite: str = "moderate",
    horizon_years: int = 10,
    knowledge_level: str = "beginner",
) -> UserRecord | None:
    """Create a new user. Returns the user record, or None if username is taken."""
    init_db()
    salt = _new_salt()
    pw_hash = _hash_password(password, salt)
    user_id = str(uuid.uuid4())

    try:
        with _connect() as conn:
            conn.execute(
                """
                INSERT INTO users (id, username, password_hash, salt,
                                   risk_appetite, horizon_years, knowledge_level)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (user_id, username.strip(), pw_hash, salt,
                 risk_appetite, horizon_years, knowledge_level),
            )
            conn.commit()
    except sqlite3.IntegrityError:
        return None  # username already taken

    return UserRecord(
        id=user_id,
        username=username.strip(),
        risk_appetite=risk_appetite,
        horizon_years=horizon_years,
        knowledge_level=knowledge_level,
        topics_discussed="",
    )


def verify_user(username: str, password: str) -> UserRecord | None:
    """Verify credentials. Returns the user record on success, None on failure."""
    init_db()
    with _connect() as conn:
        row = conn.execute(
            "SELECT * FROM users WHERE username = ?", (username.strip(),)
        ).fetchone()

    if row is None:
        return None

    expected = _hash_password(password, row["salt"])
    if not secrets.compare_digest(expected, row["password_hash"]):
        return None

    return _row_to_record(row)


def get_user(user_id: str) -> UserRecord | None:
    """Fetch a user record by id."""
    init_db()
    with _connect() as conn:
        row = conn.execute(
            "SELECT * FROM users WHERE id = ?", (user_id,)
        ).fetchone()

    if row is None:
        return None

    return _row_to_record(row)


def _row_to_record(row: sqlite3.Row) -> UserRecord:
    """Convert a DB row to a UserRecord, tolerating missing columns from older schemas."""
    keys = row.keys()
    def _col(name: str, default: str = "") -> str:
        return row[name] if name in keys else default

    return UserRecord(
        id=row["id"],
        username=row["username"],
        risk_appetite=row["risk_appetite"],
        horizon_years=row["horizon_years"],
        knowledge_level=row["knowledge_level"],
        topics_discussed=_col("topics_discussed"),
        age_range=_col("age_range"),
        life_stage=_col("life_stage"),
        employment_type=_col("employment_type"),
        monthly_investable=_col("monthly_investable"),
        emergency_fund_months=_col("emergency_fund_months"),
        debt_band=_col("debt_band"),
        insurance_status=_col("insurance_status"),
        tax_regime=_col("tax_regime"),
        investment_experience=_col("investment_experience"),
        primary_goal=_col("primary_goal"),
        loss_behaviour=_col("loss_behaviour"),
    )


def update_user_profile(
    user_id: str,
    *,
    risk_appetite: str,
    horizon_years: int,
    knowledge_level: str,
) -> None:
    """Persist profile changes made in the sidebar."""
    init_db()
    with _connect() as conn:
        conn.execute(
            """
            UPDATE users
            SET risk_appetite=?, horizon_years=?, knowledge_level=?
            WHERE id=?
            """,
            (risk_appetite, horizon_years, knowledge_level, user_id),
        )
        conn.commit()


def update_user_financial_profile(
    user_id: str,
    *,
    age_range: str,
    life_stage: str,
    employment_type: str,
    monthly_investable: str,
    emergency_fund_months: str,
    debt_band: str,
    insurance_status: str,
    tax_regime: str,
    investment_experience: str,
    primary_goal: str,
    loss_behaviour: str,
    risk_appetite: str,
) -> None:
    """Persist the financial profile collected by the onboarding wizard."""
    init_db()
    with _connect() as conn:
        conn.execute(
            """
            UPDATE users
            SET age_range=?, life_stage=?, employment_type=?, monthly_investable=?,
                emergency_fund_months=?, debt_band=?, insurance_status=?,
                tax_regime=?, investment_experience=?, primary_goal=?,
                loss_behaviour=?, risk_appetite=?
            WHERE id=?
            """,
            (age_range, life_stage, employment_type, monthly_investable,
             emergency_fund_months, debt_band, insurance_status,
             tax_regime, investment_experience, primary_goal,
             loss_behaviour, risk_appetite, user_id),
        )
        conn.commit()


def update_user_topics(user_id: str, new_agents: list[str]) -> None:
    """Merge newly seen agent names into the user's cumulative topics_discussed set.

    Stored as a comma-separated string so it survives as plain text in SQLite.
    No LLM call: topic names come from the agent trace, which is deterministic.
    """
    if not new_agents:
        return
    init_db()
    with _connect() as conn:
        row = conn.execute(
            "SELECT topics_discussed FROM users WHERE id = ?", (user_id,)
        ).fetchone()
        if row is None:
            return
        existing_raw = row["topics_discussed"] if "topics_discussed" in row.keys() else ""
        existing = set(t.strip() for t in existing_raw.split(",") if t.strip())
        merged = existing | set(new_agents)
        conn.execute(
            "UPDATE users SET topics_discussed = ? WHERE id = ?",
            (",".join(sorted(merged)), user_id),
        )
        conn.commit()
