from datetime import datetime

from app.models import AccountFacts, TicketFacts
from app.policy_facts import load as load_facts
from app.resolvers import resolve_sla
from app.seed_accounts_orders_tickets import load as load_base
from app.config import DATA_PACK_XLSX


def _seed(conn):
    load_base(conn, DATA_PACK_XLSX)
    load_facts(conn)


def test_northstar_p1_uses_15min_override_and_is_24x7(conn):
    _seed(conn)
    ticket = TicketFacts(
        ticket_id="TKT-501", account_id="ACCT-001",
        created_at=datetime(2026, 8, 16, 10, 30), status="open",
        subject="All shipment creation is failing",
        description="Every user at Northstar gets HTTP 500...",
        channel="email", assigned_to="Rohit",
        last_customer_message_at=datetime(2026, 8, 16, 10, 52),
        historical_resolution=None,
    )
    account = AccountFacts("ACCT-001", "Northstar Logistics", "Enterprise", "active", "Priya Mehta", "05_...", True)
    reference_time = datetime(2026, 8, 16, 11, 0)
    decision = resolve_sla(conn, ticket, account, severity="P1", reference_time=reference_time)
    assert decision.target_minutes == 15
    assert decision.at_risk is True   # 30 min elapsed > 15 min target
    assert decision.is_wall_clock_proxy is False
    assert decision.provenance.origin == "account_policy_facts"


def test_lumenworks_business_hours_flagged_as_proxy(conn):
    _seed(conn)
    ticket = TicketFacts(
        ticket_id="TKT-502", account_id="ACCT-002",
        created_at=datetime(2026, 8, 16, 9, 45), status="open",
        subject="Bulk upload fails", description="...", channel="chat",
        assigned_to="Maya", last_customer_message_at=None, historical_resolution=None,
    )
    account = AccountFacts("ACCT-002", "LumenWorks", "Growth", "active", "Arjun Rao", "06_...", False)
    reference_time = datetime(2026, 8, 16, 11, 0)
    decision = resolve_sla(conn, ticket, account, severity="P2", reference_time=reference_time)
    assert decision.target_minutes == 240
    assert decision.is_wall_clock_proxy is True


def test_beacon_falls_back_to_plan_default_table(conn):
    _seed(conn)
    ticket = TicketFacts(
        ticket_id="TKT-503", account_id="ACCT-003",
        created_at=datetime(2026, 8, 16, 10, 5), status="open",
        subject="Change billing contact", description="...", channel="email",
        assigned_to="Rohit", last_customer_message_at=None, historical_resolution=None,
    )
    account = AccountFacts("ACCT-003", "Beacon Retail", "Standard", "active", "Neha Kapoor", None, False)
    reference_time = datetime(2026, 8, 16, 11, 0)
    decision = resolve_sla(conn, ticket, account, severity="P3", reference_time=reference_time)
    assert decision.target_minutes == 2 * 24 * 60  # Standard P3: 2 business days (Policy v3 §3)
    assert decision.provenance.origin == "global_default"
