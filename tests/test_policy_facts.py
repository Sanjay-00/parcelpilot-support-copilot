from app import policy_facts
from app.seed_accounts_orders_tickets import load as load_base
from app.config import DATA_PACK_XLSX


def test_northstar_cancellation_override_exists(conn):
    load_base(conn, DATA_PACK_XLSX)
    policy_facts.load(conn)
    value, prov = policy_facts.get_fact(conn, "ACCT-001", "cancellation", "fee_waived", default=False)
    assert value is True
    assert prov.origin == "account_policy_facts"
    assert "Northstar" in prov.source_document


def test_northstar_service_credit_falls_through_to_default(conn):
    load_base(conn, DATA_PACK_XLSX)
    policy_facts.load(conn)
    value, prov = policy_facts.get_fact(conn, "ACCT-001", "service_credit", "credit_amount_inr", default=None)
    assert value is None
    assert prov.origin == "global_default"


def test_lumenworks_credit_override_exists(conn):
    load_base(conn, DATA_PACK_XLSX)
    policy_facts.load(conn)
    value, prov = policy_facts.get_fact(conn, "ACCT-002", "service_credit", "credit_amount_inr", default=None)
    assert value == 300.0
    assert prov.source_document == "LumenWorks Service Agreement"
    assert prov.source_section == "§3"
