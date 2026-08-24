import sqlite3
from datetime import datetime

from app.auth import authorize
from app.models import AccountFacts, Citation, OrderFacts, StaffUser, TicketFacts


class AccessDenied(Exception):
    pass


def _account_id_for_order(conn: sqlite3.Connection, order_id: str) -> str | None:
    row = conn.execute("SELECT account_id FROM orders WHERE order_id = ?", (order_id,)).fetchone()
    return row["account_id"] if row else None


def _account_id_for_ticket(conn: sqlite3.Connection, ticket_id: str) -> str | None:
    row = conn.execute("SELECT account_id FROM tickets WHERE ticket_id = ?", (ticket_id,)).fetchone()
    return row["account_id"] if row else None


def get_order(conn: sqlite3.Connection, order_id: str, user: StaffUser) -> OrderFacts:
    owning_account = _account_id_for_order(conn, order_id)
    # Authorization is checked against the account the ID *would* belong to if it
    # exists; if it doesn't exist, a non-manager is denied outright (never told
    # "not found," which would itself leak that the ID doesn't exist for other
    # accounts) — either way, a denial happens before we reveal whether the
    # record exists.
    if owning_account is not None and not authorize(user, owning_account):
        raise AccessDenied("Not authorized")
    if owning_account is None:
        if user.role != "manager":
            raise AccessDenied("Not authorized")   # fail closed rather than confirm non-existence
        raise LookupError(f"Order {order_id} not found")

    row = conn.execute("SELECT * FROM orders WHERE order_id = ?", (order_id,)).fetchone()
    return OrderFacts(
        order_id=row["order_id"], account_id=row["account_id"], carrier=row["carrier"],
        status=row["status"], booked_at=datetime.fromisoformat(row["booked_at"]),
        pickup_window_start=datetime.fromisoformat(row["pickup_window_start"]) if row["pickup_window_start"] else None,
        pickup_window_end=datetime.fromisoformat(row["pickup_window_end"]) if row["pickup_window_end"] else None,
        pickup_actual_at=datetime.fromisoformat(row["pickup_actual_at"]) if row["pickup_actual_at"] else None,
        shipment_fee_inr=row["shipment_fee_inr"],
        carrier_fault=bool(row["carrier_fault"]) if row["carrier_fault"] is not None else None,
        customer_fault=bool(row["customer_fault"]) if row["customer_fault"] is not None else None,
        cancellation_requested_at=datetime.fromisoformat(row["cancellation_requested_at"]) if row["cancellation_requested_at"] else None,
        notes=row["notes"],
    )


def get_ticket(conn: sqlite3.Connection, ticket_id: str, user: StaffUser) -> TicketFacts:
    owning_account = _account_id_for_ticket(conn, ticket_id)
    if owning_account is not None and not authorize(user, owning_account):
        raise AccessDenied("Not authorized")
    if owning_account is None:
        if user.role != "manager":
            raise AccessDenied("Not authorized")
        raise LookupError(f"Ticket {ticket_id} not found")

    row = conn.execute("SELECT * FROM tickets WHERE ticket_id = ?", (ticket_id,)).fetchone()
    return TicketFacts(
        ticket_id=row["ticket_id"], account_id=row["account_id"],
        created_at=datetime.fromisoformat(row["created_at"]), status=row["status"],
        subject=row["subject"], description=row["description"], channel=row["channel"],
        assigned_to=row["assigned_to"],
        last_customer_message_at=datetime.fromisoformat(row["last_customer_message_at"]) if row["last_customer_message_at"] else None,
        historical_resolution=row["historical_resolution"],
    )


def get_account(conn: sqlite3.Connection, account_id: str, user: StaffUser) -> AccountFacts:
    if not authorize(user, account_id):
        raise AccessDenied(f"Not authorized for account {account_id}")
    row = conn.execute("SELECT * FROM accounts WHERE account_id = ?", (account_id,)).fetchone()
    if row is None:
        raise LookupError(f"Account {account_id} not found")
    return AccountFacts(
        account_id=row["account_id"], account_name=row["account_name"], plan=row["plan"],
        status=row["status"], csm=row["csm"], contract_file=row["contract_file"],
        premium_support=bool(row["premium_support"]),
    )


def _authorized_chunk_rows(conn: sqlite3.Connection, account_id: str | None):
    # Deprecated documents are excluded unconditionally, and a chunk scoped to
    # another customer never comes back for this account_id -- this is the one
    # place both search_policy_documents and list_candidate_chunks pull rows
    # from, so that guarantee can't drift between the two retrieval paths.
    return conn.execute(
        "SELECT * FROM document_chunks WHERE status != 'DEPRECATED' "
        "AND (customer_id IS NULL OR customer_id = ?)", (account_id,)
    ).fetchall()


def list_candidate_chunks(
    conn: sqlite3.Connection, account_id: str | None, user: StaffUser,
) -> list[Citation]:
    """Every authorized, non-deprecated chunk for account_id (or the global,
    non-customer-specific corpus if account_id is None) -- unranked and not
    filtered by keyword. This is the raw candidate set agent.py hands to an LLM
    for relevance selection on a general_inquiry question. Access control and
    deprecation-exclusion happen here, in the data layer, exactly as in
    search_policy_documents: the LLM only ever sees chunks already authorized
    for this user/account, it never decides which accounts it can see."""
    if account_id is not None and not authorize(user, account_id):
        raise AccessDenied(f"Not authorized for account {account_id}")

    rows = sorted(_authorized_chunk_rows(conn, account_id), key=lambda r: r["customer_id"] is None)
    return [
        Citation(r["chunk_id"], r["document_name"], r["section"], r["text"],
                 r["status"], r["effective_date"], r["customer_id"])
        for r in rows
    ]


def search_policy_documents(
    conn: sqlite3.Connection, scenario: str | None, account_id: str | None, user: StaffUser,
    keyword: str | None = None,
) -> list[Citation]:
    """scenario=None means "search the whole corpus" (any document type: policy,
    SOP, product guide, known issues, agreements), ranked by keyword relevance
    instead of gated by a fixed scenario tag -- this is what general/unclassified
    support questions (e.g. "is bulk upload supported?", "known issue with
    webhooks?") use, so the reasoning surface isn't limited to the handful of
    scenario tags the deterministic resolvers happen to use. Kept as the
    deterministic fallback agent.py falls back to when LLM-based chunk
    selection (list_candidate_chunks + an LLM call) fails or is unavailable.
    """
    if account_id is not None and not authorize(user, account_id):
        raise AccessDenied(f"Not authorized for account {account_id}")

    rows = _authorized_chunk_rows(conn, account_id)

    if scenario is not None:
        candidates = [r for r in rows if scenario in r["scenario_tags"].split(",")]
    else:
        candidates = list(rows)

    # len(w) > 2 drops short filler words, but a short alphanumeric code like
    # "p1" is meaningful and must survive -- the same rule _extract_keywords
    # in agent.py applies before the keyword string ever reaches here.
    words = (
        [w for w in keyword.lower().split() if len(w) > 2 or any(ch.isdigit() for ch in w)]
        if keyword else []
    )

    if scenario is None:
        # No scenario tag to narrow the corpus, so relevance is the only filter.
        # A single keyword hit is too weak a bar here: generic words like
        # "policy" or "shipment" appear in nearly every chunk regardless of
        # topic, which let a completely out-of-corpus question (e.g. cargo
        # insurance) return unrelated citations instead of "no evidence."
        # Require at least two distinct keyword hits on the same chunk.
        if len(words) < 2:
            return []
        candidates = [
            r for r in candidates
            if sum(w in r["text"].lower() for w in words) >= 2
        ]

    if words:
        candidates = sorted(candidates, key=lambda r: -sum(w in r["text"].lower() for w in words))

    candidates = sorted(candidates, key=lambda r: r["customer_id"] is None)

    return [
        Citation(r["chunk_id"], r["document_name"], r["section"], r["text"],
                 r["status"], r["effective_date"], r["customer_id"])
        for r in candidates
    ]
