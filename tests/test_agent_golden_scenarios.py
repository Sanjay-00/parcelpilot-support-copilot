import os

import pytest

from app.agent import run
from app.auth import get_user, load as load_users
from app.documents import load as load_docs
from app.policy_facts import load as load_facts
from app.seed_accounts_orders_tickets import load as load_base
from app.config import DATA_PACK_XLSX, REFERENCE_TIME


def _seed(conn):
    load_base(conn, DATA_PACK_XLSX)
    load_facts(conn)
    load_docs(conn)
    load_users(conn)


@pytest.mark.skipif(not os.environ.get("GEMINI_API_KEY"), reason="requires GEMINI_API_KEY")
def test_northstar_historical_conflict_uses_agreement_not_historical_note(conn):
    _seed(conn)
    priya = get_user(conn, "priya_mehta")
    state = run(
        "A previous ticket said Northstar pays a ₹250 cancellation fee after 30 "
        "minutes for ORD-1001. Is that right?",
        priya, conn,
    )
    assert state["policy_decision"].fee_inr == 0
    assert state["policy_decision"].provenance.origin == "account_policy_facts"
    assert "northstar" in state["answer_text"].lower()
    assert "250" in state["answer_text"]   # cites the historical/conflicting number while correcting it


@pytest.mark.skipif(not os.environ.get("GEMINI_API_KEY"), reason="requires GEMINI_API_KEY")
def test_ord1001_cancellation_end_to_end(conn):
    _seed(conn)
    priya = get_user(conn, "priya_mehta")
    state = run("Can Northstar cancel ORD-1001 without a cancellation fee?", priya, conn)
    assert state["policy_decision"].allowed is True
    assert state["policy_decision"].fee_inr == 0
    assert state["decision_status"] == "READY"


from app.agent import _route_after_gather, _route_after_severity


def test_route_after_gather_denies_before_resolving():
    assert _route_after_gather({"authorization_result": "DENIED"}) == "end"
    assert _route_after_gather({"authorization_result": "AUTHORIZED", "data_evidence": {"order": object()}}) == "resolve_order"
    assert _route_after_gather({"authorization_result": "AUTHORIZED", "data_evidence": {"ticket": object()}}) == "classify_severity"


def test_route_after_severity_needs_review_on_unknown():
    assert _route_after_severity({"_severity": None, "_severity_needs_review": True}) == "needs_review"
    assert _route_after_severity({"_severity": "P2", "_severity_needs_review": False}) == "resolve_sla"


from unittest.mock import patch

from app.agent import _PlanExtraction


def test_graph_executes_end_to_end_and_denies_unauthorized_access(conn):
    _seed(conn)
    arjun = get_user(conn, "arjun_rao")  # scoped to ACCT-002 only
    with patch(
        "app.agent._plan",
        return_value=_PlanExtraction(scenario="cancellation", order_id="ORD-1001", ticket_id=None),
    ):
        state = run("some query text", arjun, conn)  # ORD-1001 belongs to ACCT-001

    assert state["decision_status"] == "NEEDS_REVIEW"
    assert state["authorization_result"] == "DENIED"
    assert state.get("policy_decision") is None
