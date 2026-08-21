from app.actions import confirm_action, create_action
from app.auth import get_user, load as load_users
from app.seed_accounts_orders_tickets import load as load_base
from app.config import DATA_PACK_XLSX


def _seed(conn):
    load_base(conn, DATA_PACK_XLSX)
    load_users(conn)


def test_create_action_is_prepared_and_takes_no_effect(conn):
    _seed(conn)
    priya = get_user(conn, "priya_mehta")
    draft = create_action(
        conn, "create_escalation", "ACCT-001", ticket_id="TKT-501", order_id=None,
        payload={"reason": "Complete shipment-creation outage"}, user=priya,
    )
    assert draft.status == "PREPARED"
    row = conn.execute("SELECT status FROM actions WHERE action_id = ?", (draft.action_id,)).fetchone()
    assert row["status"] == "PREPARED"


def test_confirm_action_executes_and_writes_one_audit_row(conn):
    _seed(conn)
    priya = get_user(conn, "priya_mehta")
    draft = create_action(
        conn, "create_escalation", "ACCT-001", ticket_id="TKT-501", order_id=None,
        payload={"reason": "..."}, user=priya,
    )
    confirmed = confirm_action(conn, draft.action_id, priya)
    assert confirmed.status == "EXECUTED"
    audit_count = conn.execute(
        "SELECT COUNT(*) FROM audit_logs WHERE action_id = ?", (draft.action_id,)
    ).fetchone()[0]
    assert audit_count == 2


def test_confirm_action_records_failed_not_executed_on_db_error():
    # Simulates the mocked external side effect failing (e.g. a real ticket-system
    # escalation call would raise here in production) by making exactly the
    # EXECUTED-update statement fail, while everything else on the connection
    # still works normally. Proves confirm_action's try/except actually routes
    # a failure to FAILED instead of silently reporting EXECUTED.
    #
    # Uses a fresh, purpose-built connection (not the shared `conn` fixture)
    # via subclassing sqlite3.Connection, rather than patch.object on the
    # class -- Python 3.12+ does not allow patching methods directly on
    # sqlite3.Connection (it's an immutable/static type), so subclassing is
    # the supported way to override its behavior.
    import sqlite3

    from app import db

    class FlakyConnection(sqlite3.Connection):
        def execute(self, sql, parameters=()):
            if sql.startswith("UPDATE actions SET status = 'EXECUTED'"):
                raise sqlite3.OperationalError("simulated failure")
            return super().execute(sql, parameters)

    conn = sqlite3.connect(":memory:", factory=FlakyConnection)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    db.init_schema(conn)
    _seed(conn)

    priya = get_user(conn, "priya_mehta")
    draft = create_action(
        conn, "create_escalation", "ACCT-001", ticket_id="TKT-501", order_id=None,
        payload={"reason": "..."}, user=priya,
    )

    result = confirm_action(conn, draft.action_id, priya)

    assert result.status == "FAILED"
    row = conn.execute("SELECT status FROM actions WHERE action_id = ?", (draft.action_id,)).fetchone()
    assert row["status"] == "FAILED"
    audit_rows = conn.execute(
        "SELECT decision_json FROM audit_logs WHERE action_id = ? ORDER BY timestamp", (draft.action_id,)
    ).fetchall()
    assert len(audit_rows) == 2
    assert "FAILED" in audit_rows[1]["decision_json"]


def test_create_action_writes_one_audit_log_row(conn):
    _seed(conn)
    priya = get_user(conn, "priya_mehta")
    draft = create_action(
        conn, "create_escalation", "ACCT-001", ticket_id="TKT-501", order_id=None,
        payload={"reason": "..."}, user=priya,
    )
    assert draft.status == "PREPARED"
    audit_count = conn.execute(
        "SELECT COUNT(*) FROM audit_logs WHERE action_id = ?", (draft.action_id,)
    ).fetchone()[0]
    assert audit_count == 1


def test_confirm_action_raises_on_second_call(conn):
    _seed(conn)
    priya = get_user(conn, "priya_mehta")
    draft = create_action(
        conn, "create_escalation", "ACCT-001", ticket_id="TKT-501", order_id=None,
        payload={"reason": "..."}, user=priya,
    )
    confirmed = confirm_action(conn, draft.action_id, priya)
    assert confirmed.status == "EXECUTED"

    try:
        confirm_action(conn, draft.action_id, priya)
        assert False, "Expected ValueError on second confirm"
    except ValueError as e:
        assert "already EXECUTED" in str(e)

    audit_count = conn.execute(
        "SELECT COUNT(*) FROM audit_logs WHERE action_id = ?", (draft.action_id,)
    ).fetchone()[0]
    assert audit_count == 2
