from datetime import datetime

from app.models import OrderFacts
from app.policy_facts import load as load_facts
from app.resolvers import resolve_service_credit
from app.seed_accounts_orders_tickets import load as load_base
from app.config import DATA_PACK_XLSX, IST


def _seed(conn):
    load_base(conn, DATA_PACK_XLSX)
    load_facts(conn)


def test_ord_2002_lumenworks_carrier_fault_fixed_credit(conn):
    _seed(conn)
    order = OrderFacts(
        order_id="ORD-2002", account_id="ACCT-002", carrier="RoadRunner",
        status="BOOKED", booked_at=datetime(2026, 8, 16, 4, 30),
        pickup_window_start=datetime(2026, 8, 16, 5, 30),
        pickup_window_end=datetime(2026, 8, 16, 6, 30), pickup_actual_at=None,
        shipment_fee_inr=2400.0, carrier_fault=True, customer_fault=False,
        cancellation_requested_at=None, notes="",
    )
    reference_time = datetime(2026, 8, 16, 11, 0, tzinfo=IST).replace(tzinfo=None)
    decision = resolve_service_credit(conn, order, reference_time)
    assert decision.eligible is True
    assert decision.amount_inr == 300
    assert decision.requires_manager_approval is False
    assert decision.provenance.origin == "account_policy_facts"


def test_unknown_fault_blocks_credit_and_needs_review(conn):
    _seed(conn)
    order = OrderFacts(
        order_id="ORD-9999", account_id="ACCT-003", carrier="RoadRunner",
        status="BOOKED", booked_at=datetime(2026, 8, 16, 4, 0),
        pickup_window_start=datetime(2026, 8, 16, 5, 0),
        pickup_window_end=datetime(2026, 8, 16, 6, 0), pickup_actual_at=None,
        shipment_fee_inr=1000.0, carrier_fault=None, customer_fault=False,
        cancellation_requested_at=None, notes="",
    )
    reference_time = datetime(2026, 8, 16, 11, 0)
    decision = resolve_service_credit(conn, order, reference_time)
    assert decision.eligible is False
    assert decision.needs_review is True


def test_credit_over_1000_requires_manager_approval(conn):
    _seed(conn)
    # The global default formula (min(₹500, 10% of shipment fee)) can never exceed
    # ₹500, so it can never trigger the >₹1,000 guardrail. To test that guardrail
    # for real, insert a synthetic account-level override (ACCT-003 has no existing
    # account_policy_facts rows, so this doesn't collide with the real Northstar/
    # LumenWorks data loaded by policy_facts.load()).
    conn.execute(
        "INSERT INTO account_policy_facts (account_id, scenario, fact_name, "
        "fact_value, source_document, source_section) VALUES "
        "('ACCT-003', 'service_credit', 'credit_amount_inr', '1500', "
        "'Test Override (synthetic)', '§0')"
    )
    conn.commit()
    order = OrderFacts(
        order_id="ORD-8888", account_id="ACCT-003", carrier="RoadRunner",
        status="BOOKED", booked_at=datetime(2026, 8, 16, 1, 0),
        pickup_window_start=datetime(2026, 8, 16, 2, 0),
        pickup_window_end=datetime(2026, 8, 16, 3, 0), pickup_actual_at=None,
        shipment_fee_inr=2000.0, carrier_fault=True, customer_fault=False,
        cancellation_requested_at=None, notes="",
    )
    reference_time = datetime(2026, 8, 16, 11, 0)
    decision = resolve_service_credit(conn, order, reference_time)
    assert decision.eligible is True
    assert decision.amount_inr == 1500.0
    assert decision.requires_manager_approval is True


def test_credit_amount_rounded_to_2dp(conn):
    _seed(conn)
    # Test that the default formula's computed amount (0.10 * shipment_fee_inr)
    # is properly rounded to 2 decimal places. With shipment_fee_inr=333.33,
    # the formula yields 0.10 * 333.33 = 33.333..., which must be rounded to 33.33.
    order = OrderFacts(
        order_id="ORD-7777", account_id="ACCT-004", carrier="RoadRunner",
        status="BOOKED", booked_at=datetime(2026, 8, 16, 4, 30),
        pickup_window_start=datetime(2026, 8, 16, 5, 30),
        pickup_window_end=datetime(2026, 8, 16, 6, 30), pickup_actual_at=None,
        shipment_fee_inr=333.33, carrier_fault=True, customer_fault=False,
        cancellation_requested_at=None, notes="",
    )
    reference_time = datetime(2026, 8, 16, 11, 0, tzinfo=IST).replace(tzinfo=None)
    decision = resolve_service_credit(conn, order, reference_time)
    assert decision.eligible is True
    # 0.10 * 333.33 = 33.333, rounded to 2dp = 33.33
    assert decision.amount_inr == 33.33
    assert decision.requires_manager_approval is False
