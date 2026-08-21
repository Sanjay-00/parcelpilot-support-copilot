from datetime import datetime, timedelta

from app.models import OrderFacts
from app.policy_facts import load as load_facts
from app.resolvers import resolve_cancellation
from app.seed_accounts_orders_tickets import load as load_base
from app.config import DATA_PACK_XLSX


def _seed(conn):
    load_base(conn, DATA_PACK_XLSX)
    load_facts(conn)


def test_ord_1001_northstar_booked_2hrs_after_no_fee(conn):
    _seed(conn)
    order = OrderFacts(
        order_id="ORD-1001", account_id="ACCT-001", carrier="SwiftShip",
        status="BOOKED", booked_at=datetime(2026, 8, 16, 9, 0),
        pickup_window_start=None, pickup_window_end=None, pickup_actual_at=None,
        shipment_fee_inr=4200.0, carrier_fault=False, customer_fault=False,
        cancellation_requested_at=datetime(2026, 8, 16, 11, 0), notes="",
    )
    decision = resolve_cancellation(conn, order)
    assert decision.allowed is True
    assert decision.fee_inr == 0
    assert decision.provenance.origin == "account_policy_facts"


def test_ord_1002_northstar_picked_up_not_allowed(conn):
    _seed(conn)
    order = OrderFacts(
        order_id="ORD-1002", account_id="ACCT-001", carrier="BlueDart Pro",
        status="PICKED_UP", booked_at=datetime(2026, 8, 16, 8, 10),
        pickup_window_start=None, pickup_window_end=None,
        pickup_actual_at=datetime(2026, 8, 16, 9, 35),
        shipment_fee_inr=5100.0, carrier_fault=False, customer_fault=False,
        cancellation_requested_at=datetime(2026, 8, 16, 10, 20), notes="",
    )
    decision = resolve_cancellation(conn, order)
    assert decision.allowed is False
    assert "return-to-origin" in decision.reason.lower()


def test_ord_2001_lumenworks_75min_falls_back_to_sop_fee(conn):
    _seed(conn)
    order = OrderFacts(
        order_id="ORD-2001", account_id="ACCT-002", carrier="SwiftShip",
        status="BOOKED", booked_at=datetime(2026, 8, 16, 9, 0),
        pickup_window_start=None, pickup_window_end=None, pickup_actual_at=None,
        shipment_fee_inr=1800.0, carrier_fault=False, customer_fault=False,
        cancellation_requested_at=datetime(2026, 8, 16, 10, 15), notes="",
    )
    decision = resolve_cancellation(conn, order)
    assert decision.allowed is True
    assert decision.fee_inr == 250
    assert decision.provenance.origin == "global_default"


def test_ord_3001_beacon_under_30min_no_fee(conn):
    _seed(conn)
    order = OrderFacts(
        order_id="ORD-3001", account_id="ACCT-003", carrier="RoadRunner",
        status="BOOKED", booked_at=datetime(2026, 8, 16, 10, 25),
        pickup_window_start=None, pickup_window_end=None, pickup_actual_at=None,
        shipment_fee_inr=1200.0, carrier_fault=False, customer_fault=False,
        cancellation_requested_at=datetime(2026, 8, 16, 10, 40), notes="",
    )
    decision = resolve_cancellation(conn, order)
    assert decision.allowed is True
    assert decision.fee_inr == 0


def test_ord_4001_delivered_cannot_cancel(conn):
    _seed(conn)
    order = OrderFacts(
        order_id="ORD-4001", account_id="ACCT-004", carrier="SwiftShip",
        status="DELIVERED", booked_at=datetime(2026, 8, 14, 14, 0),
        pickup_window_start=None, pickup_window_end=None,
        pickup_actual_at=datetime(2026, 8, 15, 9, 20),
        shipment_fee_inr=3600.0, carrier_fault=False, customer_fault=False,
        cancellation_requested_at=None, notes="",
    )
    decision = resolve_cancellation(conn, order)
    assert decision.allowed is False
