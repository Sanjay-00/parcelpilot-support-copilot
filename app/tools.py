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
        raise AccessDenied(f"Not authorized for account {owning_account}")
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
        raise AccessDenied(f"Not authorized for account {owning_account}")
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


def search_policy_documents(
    conn: sqlite3.Connection, scenario: str, account_id: str | None, user: StaffUser,
    keyword: str | None = None,
) -> list:
    if account_id is not None and not authorize(user, account_id):
        raise AccessDenied(f"Not authorized for account {account_id}")

    rows = conn.execute(
        "SELECT * FROM document_chunks WHERE status != 'DEPRECATED' "
        "AND (customer_id IS NULL OR customer_id = ?)", (account_id,)
    ).fetchall()

    candidates = [r for r in rows if scenario in r["scenario_tags"].split(",")]

    if keyword:
        kw = keyword.lower()
        candidates = sorted(candidates, key=lambda r: kw not in r["text"].lower())

    candidates = sorted(candidates, key=lambda r: r["customer_id"] is None)

    return [
        Citation(r["document_name"], r["section"], r["text"], r["status"], r["effective_date"], r["customer_id"])
        for r in candidates
    ]
