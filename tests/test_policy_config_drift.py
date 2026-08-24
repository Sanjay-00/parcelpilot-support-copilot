"""Drift-detection tests: app/policy_config.py's numbers are hand-transcribed
from the same source documents as the citation chunks in app/documents.py --
these two are NOT connected at runtime (see docs/SCALE.md, "Keeping policy
config in sync"), so nothing stops someone updating one and forgetting the
other. These tests extract the numbers straight out of the chunk text and
assert they match the config, which is the cheapest mechanical check that
would have caught it if that ever happened.

This is deliberately test-only logic: parsing policy numbers out of prose is
exactly the kind of fragile extraction this system refuses to do at
answer-time (see app/resolvers.py's design). Here it only has to run in CI,
not survive an adversarial user, and a broken parser just fails the test
loudly instead of silently answering a support question wrong.
"""

import re

from app.documents import _CHUNKS
from app.policy_config import CURRENT


def _chunk_text(chunk_id: str) -> str:
    for chunk in _CHUNKS:
        if chunk["chunk_id"] == chunk_id:
            return chunk["text"]
    raise AssertionError(f"no such chunk_id in app/documents.py: {chunk_id!r}")


def test_cancellation_fee_and_grace_period_match_sop_text():
    text = _chunk_text("sop_v4_cancellation")
    grace = int(re.search(r"no fee within (\d+) minutes", text).group(1))
    fee = float(re.search(r"charge INR (\d+)", text).group(1))

    assert grace == CURRENT.cancellation.grace_minutes
    assert fee == CURRENT.cancellation.fee_inr


def test_service_credit_defaults_match_sop_text():
    text = _chunk_text("sop_v4_credit")
    threshold_hours = float(re.search(r"more than (\d+) hours", text).group(1))
    cap_inr = float(re.search(r"lower of INR (\d+)", text).group(1))
    percent = float(re.search(r"or (\d+)% of the shipment fee", text).group(1)) / 100

    assert threshold_hours == CURRENT.service_credit.default_delay_threshold_hours
    assert cap_inr == CURRENT.service_credit.default_credit_cap_inr
    assert percent == CURRENT.service_credit.default_credit_percent


def test_manager_approval_threshold_matches_sop_text():
    text = _chunk_text("sop_v4_guardrails")
    threshold = float(re.search(r"above INR ([\d,]+)", text).group(1).replace(",", ""))

    assert threshold == CURRENT.service_credit.manager_approval_threshold_inr


_UNIT_TO_MINUTES = {
    "minute": 1, "minutes": 1,
    "business hour": 60, "business hours": 60, "hour": 60, "hours": 60,
    "business day": 1440, "day": 1440,
}


def test_sla_default_targets_match_policy_text():
    # e.g. "Enterprise: P1 30 minutes 24x7, P2 2 hours, P3 1 business day.
    # Growth: P1 2 business hours, ... Standard: ...."
    text = _chunk_text("policy_v3_targets")

    for plan in ("Enterprise", "Growth", "Standard"):
        block = re.search(rf"{plan}: (.*?)(?:\. [A-Z][a-z]+:|\.$)", text).group(1)
        for severity in ("P1", "P2", "P3"):
            match = re.search(
                rf"{severity} (\d+) (business hours|business day|hours|hour|minutes|minute|days|day)",
                block,
            )
            value, unit = int(match.group(1)), match.group(2)
            minutes = value * _UNIT_TO_MINUTES[unit]
            assert minutes == CURRENT.sla.targets_minutes[plan][severity], (
                f"{plan} {severity}: document says {value} {unit} ({minutes} min), "
                f"config says {CURRENT.sla.targets_minutes[plan][severity]} min"
            )
