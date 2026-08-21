import json
import sqlite3
import uuid
from datetime import datetime, timezone

from app.auth import authorize
from app.models import ActionDraft, StaffUser
from app.tools import AccessDenied


def create_action(
    conn: sqlite3.Connection, action_type: str, account_id: str,
    ticket_id: str | None, order_id: str | None, payload: dict, user: StaffUser,
) -> ActionDraft:
    if not authorize(user, account_id):
        raise AccessDenied(f"Not authorized for account {account_id}")

    action_id = f"ACT-{uuid.uuid4().hex[:8]}"
    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        "INSERT INTO actions (action_id, action_type, account_id, ticket_id, order_id, "
        "payload_json, prepared_by, status, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, 'PREPARED', ?)",
        (action_id, action_type, account_id, ticket_id, order_id, json.dumps(payload), user.user_id, now),
    )
    conn.commit()
    return ActionDraft(action_id, action_type, account_id, "PREPARED")


def confirm_action(conn: sqlite3.Connection, action_id: str, user: StaffUser) -> ActionDraft:
    row = conn.execute("SELECT * FROM actions WHERE action_id = ?", (action_id,)).fetchone()
    if row is None:
        raise LookupError(f"Action {action_id} not found")
    if not authorize(user, row["account_id"]):
        raise AccessDenied(f"Not authorized for account {row['account_id']}")

    now = datetime.now(timezone.utc).isoformat()
    try:
        # Local SQLite write stands in for the mocked external side effect
        # (e.g. creating a ticket-system escalation). Any exception here is
        # caught below so a failure is recorded as FAILED, never EXECUTED.
        conn.execute(
            "UPDATE actions SET status = 'EXECUTED', confirmed_at = ?, executed_at = ? "
            "WHERE action_id = ?", (now, now, action_id),
        )
        final_status = "EXECUTED"
    except sqlite3.Error:
        conn.execute(
            "UPDATE actions SET status = 'FAILED', confirmed_at = ? WHERE action_id = ?",
            (now, action_id),
        )
        final_status = "FAILED"
    conn.commit()

    conn.execute(
        "INSERT INTO audit_logs (log_id, timestamp, user, account_id, action_id, decision_json) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (f"LOG-{uuid.uuid4().hex[:8]}", now, user.user_id, row["account_id"], action_id,
         json.dumps({"final_status": final_status})),
    )
    conn.commit()

    return ActionDraft(action_id, row["action_type"], row["account_id"], final_status)
