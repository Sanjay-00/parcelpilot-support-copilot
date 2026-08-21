import sqlite3

from app.models import Provenance

# Hand-extracted from the two agreement PDFs (05_Northstar_Logistics_Enterprise_Agreement.pdf,
# 06_LumenWorks_Service_Agreement.pdf). Deliberately excludes Northstar's ₹5,000 monthly
# service-credit cap — see spec §7/§21: no ledger of already-issued credits exists in the
# supplied data, so the cap can't be enforced and isn't stored as a computable fact.
_FACTS = [
    # account_id,  scenario,        fact_name,                fact_value, source_document,                    source_section
    ("ACCT-001", "cancellation", "fee_waived",              "true",  "Northstar Enterprise Agreement", "§2"),
    ("ACCT-001", "cancellation", "waiver_scope",            "booked_before_pickup_any_time", "Northstar Enterprise Agreement", "§2"),
    ("ACCT-001", "sla",          "p1_target_minutes",       "15",    "Northstar Enterprise Agreement", "§1"),
    ("ACCT-001", "sla",          "p2_target_minutes",       "60",    "Northstar Enterprise Agreement", "§1"),
    ("ACCT-001", "sla",          "p3_target_minutes",       "480",   "Northstar Enterprise Agreement", "§1"),
    ("ACCT-001", "sla",          "coverage",                "24x7",  "Northstar Enterprise Agreement", "§1"),
    ("ACCT-002", "service_credit", "delay_threshold_hours", "4",     "LumenWorks Service Agreement", "§3"),
    ("ACCT-002", "service_credit", "credit_amount_inr",      "300",  "LumenWorks Service Agreement", "§3"),
    ("ACCT-002", "sla",          "p1_target_minutes",       "120",   "LumenWorks Service Agreement", "§1"),
    ("ACCT-002", "sla",          "p2_target_minutes",       "240",   "LumenWorks Service Agreement", "§1"),
    ("ACCT-002", "sla",          "p3_target_minutes",       "2880",  "LumenWorks Service Agreement", "§1"),
    ("ACCT-002", "sla",          "coverage",                "business_hours", "LumenWorks Service Agreement", "§1"),
]

_TYPE_CASTERS = {
    "fee_waived": lambda v: v == "true",
    "delay_threshold_hours": float,
    "credit_amount_inr": float,
    "p1_target_minutes": int,
    "p2_target_minutes": int,
    "p3_target_minutes": int,
}


def load(conn: sqlite3.Connection) -> None:
    conn.executemany(
        "INSERT INTO account_policy_facts "
        "(account_id, scenario, fact_name, fact_value, source_document, source_section) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        _FACTS,
    )
    conn.commit()


def get_fact(conn: sqlite3.Connection, account_id: str, scenario: str, fact_name: str, default):
    row = conn.execute(
        "SELECT fact_value, source_document, source_section FROM account_policy_facts "
        "WHERE account_id = ? AND scenario = ? AND fact_name = ?",
        (account_id, scenario, fact_name),
    ).fetchone()
    if row is None:
        return default, Provenance(
            origin="global_default", source_document="global_default", source_section="n/a"
        )
    caster = _TYPE_CASTERS.get(fact_name, str)
    return caster(row["fact_value"]), Provenance(
        origin="account_policy_facts",
        source_document=row["source_document"],
        source_section=row["source_section"],
    )
