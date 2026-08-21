from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class Provenance:
    origin: str            # "account_policy_facts" | "global_default"
    source_document: str
    source_section: str


@dataclass(frozen=True)
class AccountFacts:
    account_id: str
    account_name: str
    plan: str
    status: str
    csm: str | None
    contract_file: str | None
    premium_support: bool


@dataclass(frozen=True)
class OrderFacts:
    order_id: str
    account_id: str
    carrier: str | None
    status: str
    booked_at: datetime
    pickup_window_start: datetime | None
    pickup_window_end: datetime | None
    pickup_actual_at: datetime | None
    shipment_fee_inr: float | None
    carrier_fault: bool | None
    customer_fault: bool | None
    cancellation_requested_at: datetime | None
    notes: str | None


@dataclass(frozen=True)
class TicketFacts:
    ticket_id: str
    account_id: str
    created_at: datetime
    status: str
    subject: str
    description: str
    channel: str | None
    assigned_to: str | None
    last_customer_message_at: datetime | None
    historical_resolution: str | None


@dataclass(frozen=True)
class CancellationDecision:
    allowed: bool
    fee_inr: float | None
    reason: str
    provenance: Provenance


@dataclass(frozen=True)
class CreditDecision:
    eligible: bool
    amount_inr: float | None
    requires_manager_approval: bool
    needs_review: bool
    reason: str
    provenance: Provenance


@dataclass(frozen=True)
class SLADecision:
    severity: str
    target_minutes: int
    elapsed_minutes: float
    at_risk: bool
    is_wall_clock_proxy: bool
    provenance: Provenance


@dataclass(frozen=True)
class Citation:
    document_name: str
    section: str
    text: str
    status: str
    effective_date: str | None
    customer_id: str | None


@dataclass(frozen=True)
class StaffUser:
    user_id: str
    name: str
    role: str                    # "agent" | "manager"
    assigned_account_ids: list
