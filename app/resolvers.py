import sqlite3
from datetime import datetime

from app.models import (
    AccountFacts, CancellationDecision, CreditDecision, OrderFacts, Provenance, SLADecision, TicketFacts
)
from app.policy_facts import get_fact


def resolve_cancellation(conn: sqlite3.Connection, order: OrderFacts) -> CancellationDecision:
    sop_provenance = Provenance(
        origin="global_default", source_document="SOP v4", source_section="§1"
    )

    if order.status == "DRAFT":
        return CancellationDecision(True, 0.0, "DRAFT orders may be cancelled with no fee.", sop_provenance)

    if order.status == "PICKED_UP":
        return CancellationDecision(
            False, None,
            "Order has been picked up; use the return-to-origin workflow instead of cancellation.",
            sop_provenance,
        )

    if order.status == "DELIVERED":
        return CancellationDecision(False, None, "Delivered orders cannot be cancelled.", sop_provenance)

    # BOOKED, not yet picked up
    waived, waived_prov = get_fact(conn, order.account_id, "cancellation", "fee_waived", default=False)
    scope, _ = get_fact(conn, order.account_id, "cancellation", "waiver_scope", default=None)
    if waived and scope == "booked_before_pickup_any_time":
        return CancellationDecision(
            True, 0.0, "Cancellation fee waived by the customer's agreement.", waived_prov
        )

    age = order.cancellation_requested_at - order.booked_at
    fee = 0.0 if age <= __import__("datetime").timedelta(minutes=30) else 250.0
    reason = (
        "Cancelled within 30 minutes of booking; no fee per SOP v4."
        if fee == 0.0 else
        "Cancelled more than 30 minutes after booking; ₹250 fee per SOP v4."
    )
    return CancellationDecision(True, fee, reason, sop_provenance)


def resolve_service_credit(
    conn: sqlite3.Connection, order: OrderFacts, reference_time: datetime
) -> CreditDecision:
    sop_provenance = Provenance(
        origin="global_default", source_document="SOP v4", source_section="§2"
    )
    uncertainty_provenance = Provenance(
        origin="global_default", source_document="SOP v4", source_section="§3"
    )

    if order.carrier_fault is None or order.customer_fault is None:
        return CreditDecision(
            False, None, False, True,
            "Carrier-fault or customer-fault status is unknown; SOP v4 §3 prohibits "
            "promising a credit until this is verified.",
            uncertainty_provenance,
        )

    if order.customer_fault:
        return CreditDecision(False, None, False, False, "Customer was at fault; not eligible.", sop_provenance)

    if order.pickup_actual_at is not None:
        delay = order.pickup_actual_at - order.pickup_window_end
    else:
        delay = reference_time - order.pickup_window_end

    threshold_hours, threshold_prov = get_fact(
        conn, order.account_id, "service_credit", "delay_threshold_hours", default=2.0
    )
    if delay.total_seconds() / 3600 <= threshold_hours or not order.carrier_fault:
        return CreditDecision(False, None, False, False, "Delay does not exceed the applicable threshold.", threshold_prov)

    amount, amount_prov = get_fact(
        conn, order.account_id, "service_credit", "credit_amount_inr",
        default=min(500.0, 0.10 * (order.shipment_fee_inr or 0)),
    )
    amount = round(amount, 2)
    return CreditDecision(
        True, amount, amount > 1000, False,
        f"Carrier-fault delay exceeded {threshold_hours}h threshold; credit applies.",
        amount_prov,
    )


# Policy v3 §3 default first-response targets, in minutes.
_PLAN_DEFAULTS_MINUTES = {
    "Enterprise": {"P1": 30, "P2": 120, "P3": 1 * 24 * 60},
    "Growth":     {"P1": 2 * 60, "P2": 4 * 60, "P3": 2 * 24 * 60},
    "Standard":   {"P1": 4 * 60, "P2": 1 * 24 * 60, "P3": 2 * 24 * 60},
}


def resolve_sla(
    conn: sqlite3.Connection, ticket: TicketFacts, account: AccountFacts,
    severity: str, reference_time: datetime,
) -> SLADecision:
    target, target_prov = get_fact(conn, account.account_id, "sla", f"{severity.lower()}_target_minutes", default=None)
    if target is None:
        target = _PLAN_DEFAULTS_MINUTES[account.plan][severity]
        target_prov = Provenance("global_default", "Policy v3", "§3")

    coverage, _ = get_fact(conn, account.account_id, "sla", "coverage", default="24x7")
    elapsed = (reference_time - ticket.created_at).total_seconds() / 60

    return SLADecision(
        severity=severity,
        target_minutes=target,
        elapsed_minutes=elapsed,
        at_risk=elapsed > target,
        is_wall_clock_proxy=(coverage == "business_hours"),
        provenance=target_prov,
    )
