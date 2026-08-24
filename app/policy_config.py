from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True)
class CancellationPolicy:
    grace_minutes: int
    fee_inr: float
    source_document: str
    source_section: str


@dataclass(frozen=True)
class ServiceCreditPolicy:
    default_delay_threshold_hours: float
    default_credit_cap_inr: float
    default_credit_percent: float
    manager_approval_threshold_inr: float
    source_document: str
    source_section: str


@dataclass(frozen=True)
class SLAPolicy:
    # {plan: {severity: minutes}}
    targets_minutes: dict
    source_document: str
    source_section: str


@dataclass(frozen=True)
class GlobalPolicyConfig:
    effective_date: date
    cancellation: CancellationPolicy
    service_credit: ServiceCreditPolicy
    sla: SLAPolicy


# These numbers were previously literal constants scattered across
# app/resolvers.py. They are hand-transcribed from the same two source
# documents as the citation chunks in app/documents.py -- moving them here
# doesn't make them auto-update when a policy changes (see docs/SCALE.md,
# "Keeping policy config in sync at scale" for why that's a deliberate
# choice, not a gap), but it does make "what does the system currently
# compute with" a single, versioned, greppable place instead of buried
# arithmetic, and it lets tests/test_policy_config_drift.py catch the most
# common real failure mode: this file and the document chunk text
# describing the same rule silently disagreeing after only one of them
# gets updated.
#
# If ParcelPilot ships a new SOP/policy version, update the corresponding
# fields here (bumping effective_date), update the matching chunk(s) in
# app/documents.py, mark the old chunk DEPRECATED, and re-run
# tests/test_policy_config_drift.py to confirm the two didn't drift apart.
CURRENT = GlobalPolicyConfig(
    effective_date=date(2026, 6, 15),
    cancellation=CancellationPolicy(
        grace_minutes=30,
        fee_inr=250.0,
        source_document="Cancellation & Service Credit SOP v4",
        source_section="§1 Order cancellation",
    ),
    service_credit=ServiceCreditPolicy(
        default_delay_threshold_hours=2.0,
        default_credit_cap_inr=500.0,
        default_credit_percent=0.10,
        manager_approval_threshold_inr=1000.0,
        source_document="Cancellation & Service Credit SOP v4",
        source_section="§2 Failed-pickup service credits",
    ),
    sla=SLAPolicy(
        targets_minutes={
            "Enterprise": {"P1": 30, "P2": 2 * 60, "P3": 1 * 24 * 60},
            "Growth": {"P1": 2 * 60, "P2": 4 * 60, "P3": 2 * 24 * 60},
            "Standard": {"P1": 4 * 60, "P2": 1 * 24 * 60, "P3": 2 * 24 * 60},
        },
        source_document="Support Policy v3",
        source_section="§3 Default first-response targets",
    ),
)
