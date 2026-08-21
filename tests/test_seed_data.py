from app import config
from app.seed_accounts_orders_tickets import load


def test_reference_time_loaded_correctly():
    assert config.REFERENCE_TIME.isoformat() == "2026-08-16T11:00:00+05:30"


def test_seed_loads_expected_row_counts(conn):
    load(conn, config.DATA_PACK_XLSX)
    assert conn.execute("SELECT COUNT(*) FROM accounts").fetchone()[0] == 4
    assert conn.execute("SELECT COUNT(*) FROM orders").fetchone()[0] == 6
    assert conn.execute("SELECT COUNT(*) FROM tickets").fetchone()[0] == 7


def test_seed_preserves_nullable_fault_flags(conn):
    load(conn, config.DATA_PACK_XLSX)
    row = conn.execute(
        "SELECT carrier_fault, customer_fault FROM orders WHERE order_id = 'ORD-2002'"
    ).fetchone()
    assert row["carrier_fault"] == 1
    assert row["customer_fault"] == 0
