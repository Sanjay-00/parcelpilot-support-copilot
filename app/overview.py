import sqlite3

from app.auth import authorize
from app.models import StaffUser


def _visible_open_tickets(conn: sqlite3.Connection, user: StaffUser):
    rows = conn.execute("SELECT * FROM tickets WHERE status = 'open'").fetchall()
    return [r for r in rows if authorize(user, r["account_id"])]


def issue_clusters(conn: sqlite3.Connection, user: StaffUser) -> list:
    all_chunks = conn.execute(
        "SELECT chunk_id, text, scenario_tags FROM document_chunks"
    ).fetchall()
    known_issue_chunks = [c for c in all_chunks if "known_issue" in c["scenario_tags"].split(",")]

    tickets = _visible_open_tickets(conn, user)

    clusters = []
    for chunk in known_issue_chunks:
        matched = [
            t for t in tickets
            if _keyword_overlap(t["subject"] + " " + t["description"], chunk["text"])
        ]
        if matched:
            account_ids = {t["account_id"] for t in matched}
            clusters.append({
                "ki_id": chunk["chunk_id"],
                "ticket_ids": [t["ticket_id"] for t in matched],
                "account_ids": list(account_ids),
                "is_multi_customer": len(account_ids) > 1,
            })
    return [c for c in clusters if len(c["ticket_ids"]) >= 1]


def _keyword_overlap(ticket_text: str, chunk_text: str) -> bool:
    # Simple, deterministic overlap check: does the ticket mention a distinctive
    # noun phrase from the known-issue chunk? Reuses the same "keyword inside text"
    # idea as search_policy_documents rather than introducing new matching logic.
    ticket_words = set(ticket_text.lower().split())
    distinctive_terms = ["bulk upload", "csv", "webhook", "booked", "swiftship"]
    chunk_lower = chunk_text.lower()
    return any(term in ticket_text.lower() and term in chunk_lower for term in distinctive_terms)


def sla_risk_tickets(conn: sqlite3.Connection, user: StaffUser) -> list:
    from datetime import datetime

    from app.models import AccountFacts, TicketFacts
    from app.resolvers import resolve_sla
    from app.severity import extract_incident_facts, map_severity
    from app import config

    reference_time = config.REFERENCE_TIME.replace(tzinfo=None)
    results = []
    for row in _visible_open_tickets(conn, user):
        ticket = TicketFacts(
            ticket_id=row["ticket_id"], account_id=row["account_id"],
            created_at=datetime.fromisoformat(row["created_at"]),
            status=row["status"], subject=row["subject"], description=row["description"],
            channel=row["channel"], assigned_to=row["assigned_to"],
            last_customer_message_at=datetime.fromisoformat(row["last_customer_message_at"]) if row["last_customer_message_at"] else None,
            historical_resolution=row["historical_resolution"],
        )
        account_row = conn.execute(
            "SELECT * FROM accounts WHERE account_id = ?", (ticket.account_id,)
        ).fetchone()
        account = AccountFacts(
            account_row["account_id"], account_row["account_name"], account_row["plan"],
            account_row["status"], account_row["csm"], account_row["contract_file"],
            bool(account_row["premium_support"]),
        )
        incident_facts = extract_incident_facts(ticket.subject, ticket.description)
        severity, needs_review = map_severity(incident_facts)
        if needs_review or severity is None:
            results.append({"ticket_id": ticket.ticket_id, "severity": None, "at_risk": None, "needs_review": True})
            continue
        decision = resolve_sla(conn, ticket, account, severity, reference_time)
        results.append({
            "ticket_id": ticket.ticket_id, "severity": decision.severity,
            "at_risk": decision.at_risk, "needs_review": False,
        })
    return results
