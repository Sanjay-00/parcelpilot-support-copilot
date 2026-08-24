import sqlite3
from datetime import datetime, timedelta

from app.models import (
    AccountFacts, CancellationDecision, CreditDecision, OrderFacts, Provenance, SLADecision, TicketFacts
)
from app.policy_config import CURRENT as POLICY
from app.policy_facts import get_fact


def resolve_cancellation(conn: sqlite3.Connection, order: OrderFacts) -> CancellationDecision:
    sop_provenance = Provenance(
        origin="global_default",
        source_document=POLICY.cancellation.source_document,
        source_section=POLICY.cancellation.source_section,
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
    grace = POLICY.cancellation.grace_minutes
    fee = 0.0 if age <= timedelta(minutes=grace) else POLICY.cancellation.fee_inr
    reason = (
        f"Cancelled within {grace} minutes of booking; no fee per SOP v4."
        if fee == 0.0 else
        f"Cancelled more than {grace} minutes after booking; ₹{fee:g} fee per SOP v4."
    )
    return CancellationDecision(True, fee, reason, sop_provenance)


def resolve_service_credit(
    conn: sqlite3.Connection, order: OrderFacts, reference_time: datetime
) -> CreditDecision:
    sop_provenance = Provenance(
        origin="global_default",
        source_document=POLICY.service_credit.source_document,
        source_section=POLICY.service_credit.source_section,
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
        conn, order.account_id, "service_credit", "delay_threshold_hours",
        default=POLICY.service_credit.default_delay_threshold_hours,
    )
    if delay.total_seconds() / 3600 <= threshold_hours or not order.carrier_fault:
        return CreditDecision(False, None, False, False, "Delay does not exceed the applicable threshold.", threshold_prov)

    amount, amount_prov = get_fact(
        conn, order.account_id, "service_credit", "credit_amount_inr",
        default=min(
            POLICY.service_credit.default_credit_cap_inr,
            POLICY.service_credit.default_credit_percent * (order.shipment_fee_inr or 0),
        ),
    )
    amount = round(amount, 2)
    return CreditDecision(
        True, amount, amount > POLICY.service_credit.manager_approval_threshold_inr, False,
        f"Carrier-fault delay exceeded {threshold_hours}h threshold; credit applies.",
        amount_prov,
    )


def resolve_sla(
    conn: sqlite3.Connection, ticket: TicketFacts, account: AccountFacts,
    severity: str, reference_time: datetime,
) -> SLADecision:
    target, target_prov = get_fact(conn, account.account_id, "sla", f"{severity.lower()}_target_minutes", default=None)
    if target is None:
        target = POLICY.sla.targets_minutes[account.plan][severity]
        target_prov = Provenance("global_default", POLICY.sla.source_document, POLICY.sla.source_section)

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
