import json

from app.auth import authorize, get_user, load
from app.seed_accounts_orders_tickets import load as load_base
from app.config import DATA_PACK_XLSX


def test_agent_authorized_for_own_account_only(conn):
    load_base(conn, DATA_PACK_XLSX)
    load(conn)
    arjun = get_user(conn, "arjun_rao")
    assert authorize(arjun, "ACCT-002") is True
    assert authorize(arjun, "ACCT-001") is False


def test_manager_authorized_for_any_account(conn):
    load_base(conn, DATA_PACK_XLSX)
    load(conn)
    manager = get_user(conn, "manager")
    assert authorize(manager, "ACCT-001") is True
    assert authorize(manager, "ACCT-004") is True


def test_get_user_unknown_user_id_raises_value_error(conn):
    load_base(conn, DATA_PACK_XLSX)
    load(conn)
    try:
        get_user(conn, "unknown_user_id")
        assert False, "Expected ValueError to be raised"
    except ValueError as e:
        assert "Unknown user_id: unknown_user_id" in str(e)
