import pytest

from app.auth import get_user, load as load_users
from app.documents import load as load_docs
from app.policy_facts import load as load_facts
from app.seed_accounts_orders_tickets import load as load_base
from app.tools import AccessDenied, get_order, get_ticket, get_account, search_policy_documents
from app.config import DATA_PACK_XLSX


def _seed(conn):
    load_base(conn, DATA_PACK_XLSX)
    load_facts(conn)
    load_docs(conn)
    load_users(conn)


def test_unauthorized_cross_account_order_lookup_denied(conn):
    _seed(conn)
    arjun = get_user(conn, "arjun_rao")   # scoped to ACCT-002 only
    with pytest.raises(AccessDenied):
        get_order(conn, "ORD-1001", arjun)   # belongs to ACCT-001


def test_unauthorized_existence_probe_does_not_leak_not_found_vs_denied(conn):
    _seed(conn)
    arjun = get_user(conn, "arjun_rao")
    with pytest.raises(AccessDenied):
        get_order(conn, "ORD-9999-DOES-NOT-EXIST", arjun)   # denial happens
                                                             # before existence is even checked


def test_authorized_lookup_succeeds(conn):
    _seed(conn)
    priya = get_user(conn, "priya_mehta")   # scoped to ACCT-001, ACCT-004
    order = get_order(conn, "ORD-1001", priya)
    assert order.order_id == "ORD-1001"


def test_northstar_cancellation_chunk_ranks_before_global_sop(conn):
    _seed(conn)
    priya = get_user(conn, "priya_mehta")
    citations = search_policy_documents(conn, "cancellation", "ACCT-001", priya)
    assert citations[0].document_name == "Northstar Enterprise Agreement"
    assert any(c.document_name == "Cancellation & Service Credit SOP v4" for c in citations)
    assert all(c.status != "DEPRECATED" for c in citations)


def test_unauthorized_cross_account_ticket_lookup_denied(conn):
    _seed(conn)
    arjun = get_user(conn, "arjun_rao")   # scoped to ACCT-002 only
    with pytest.raises(AccessDenied):
        get_ticket(conn, "TKT-501", arjun)   # belongs to ACCT-001


def test_unauthorized_nonexistent_ticket_denial_same_message_as_cross_account(conn):
    _seed(conn)
    arjun = get_user(conn, "arjun_rao")
    # Get error messages for both cases - they must be identical to prevent information leakage
    with pytest.raises(AccessDenied) as exc_cross_account:
        get_ticket(conn, "TKT-501", arjun)   # real ticket in ACCT-001
    with pytest.raises(AccessDenied) as exc_nonexistent:
        get_ticket(conn, "TKT-9999-DOES-NOT-EXIST", arjun)
    # Messages must be identical to prevent existence probing
    assert str(exc_cross_account.value) == str(exc_nonexistent.value)


def test_authorized_ticket_lookup_succeeds(conn):
    _seed(conn)
    priya = get_user(conn, "priya_mehta")   # scoped to ACCT-001, ACCT-004
    ticket = get_ticket(conn, "TKT-501", priya)
    assert ticket.ticket_id == "TKT-501"


def test_unauthorized_account_lookup_denied(conn):
    _seed(conn)
    arjun = get_user(conn, "arjun_rao")   # scoped to ACCT-002 only
    with pytest.raises(AccessDenied):
        get_account(conn, "ACCT-001", arjun)


def test_authorized_account_lookup_succeeds(conn):
    _seed(conn)
    priya = get_user(conn, "priya_mehta")   # scoped to ACCT-001, ACCT-004
    account = get_account(conn, "ACCT-001", priya)
    assert account.account_id == "ACCT-001"


def test_unauthorized_search_policy_documents_denied(conn):
    _seed(conn)
    arjun = get_user(conn, "arjun_rao")   # scoped to ACCT-002 only
    with pytest.raises(AccessDenied):
        search_policy_documents(conn, "cancellation", "ACCT-001", arjun)


def test_order_exception_message_identical_for_cross_account_and_nonexistent(conn):
    """Regression test: verify that get_order raises AccessDenied with identical messages
    for both (a) a real order in another account and (b) a nonexistent order.
    This prevents callers from distinguishing existence via exception message."""
    _seed(conn)
    arjun = get_user(conn, "arjun_rao")
    with pytest.raises(AccessDenied) as exc_cross_account:
        get_order(conn, "ORD-1001", arjun)   # real order in ACCT-001
    with pytest.raises(AccessDenied) as exc_nonexistent:
        get_order(conn, "ORD-9999-DOES-NOT-EXIST", arjun)
    # Messages must be identical to prevent existence probing
    assert str(exc_cross_account.value) == str(exc_nonexistent.value)
