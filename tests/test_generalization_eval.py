"""Generalization evaluation suite: ~15-20 natural-language questions the
system was NOT built against (none of these are the two illustrative
examples from the assessment PDF -- "Can Northstar cancel ORD-1001" /
"3 hours late, carrier fault, service credit"). Every question here uses
real records from the supplied data pack (accounts, orders, tickets) but
phrasing and record choices are deliberately unseen, to check the system
reasons over the corpus rather than pattern-matching the brief's examples.

Runs against a live Gemini model end-to-end (skipped without a real key,
same convention as the rest of the suite) -- unlike the deterministic unit
tests, these assertions are intentionally loose (decision_status, whether a
resolver ran, which document showed up) rather than exact wording, because
live LLM phrasing varies run to run. The point is coverage and "did the
system do something sane," not exact-string matching.
"""

import os

import pytest

from app.agent import run
from app.auth import get_user, load as load_users
from app.documents import load as load_docs
from app.policy_facts import load as load_facts
from app.seed_accounts_orders_tickets import load as load_base
from app.config import DATA_PACK_XLSX

pytestmark = pytest.mark.skipif(
    not os.environ.get("GEMINI_API_KEY"), reason="requires GEMINI_API_KEY"
)


def _seed(conn):
    load_base(conn, DATA_PACK_XLSX)
    load_facts(conn)
    load_docs(conn)
    load_users(conn)


def _run(conn, user_id, query, conversation_id=None):
    _seed(conn)
    user = get_user(conn, user_id)
    return run(query, user, conn, conversation_id=conversation_id)


# --- Product documentation -------------------------------------------------

def test_eval_product_capability_bulk_upload_on_standard_plan(conn):
    # Beacon Retail (ACCT-003) is on the Standard plan, which per the product
    # guide does NOT include Bulk Upload -- unlike the two illustrative
    # examples, this specifically exercises the negative case.
    state = _run(conn, "neha_kapoor", "Does our plan include the bulk upload feature?")
    assert state["decision_status"] in ("READY", "NEEDS_REVIEW")
    assert any(c.document_name == "Product Operations Guide" for c in state.get("doc_evidence", []))


def test_eval_product_meaning_of_booked_status(conn):
    state = _run(conn, "priya_mehta", "What does it mean when an order shows the BOOKED status?")
    assert state["decision_status"] == "READY"
    assert any(c.document_name == "Product Operations Guide" for c in state.get("doc_evidence", []))


# --- Known issues ------------------------------------------------------------

def test_eval_known_issue_csv_upload_failure(conn):
    state = _run(
        conn, "arjun_rao",
        "We're seeing intermittent failures uploading a CSV with about 4,000 rows. Is this a known problem?",
    )
    assert state["decision_status"] == "READY"
    assert any("KI-208" in c.text for c in state.get("doc_evidence", []))


def test_eval_known_issue_webhook_delay(conn):
    state = _run(
        conn, "priya_mehta",
        "A driver says they already picked up ORD-1001 but the system still shows it as BOOKED. What's going on?",
    )
    assert state["decision_status"] == "READY"
    assert any("KI-211" in c.text or "webhook" in c.text.lower() for c in state.get("doc_evidence", []))


# --- Agreements ---------------------------------------------------------------

def test_eval_agreement_northstar_support_hours(conn):
    state = _run(conn, "priya_mehta", "Does Northstar get 24/7 support coverage?")
    assert state["decision_status"] == "READY"
    assert any(c.document_name == "Northstar Enterprise Agreement" for c in state.get("doc_evidence", []))


def test_eval_agreement_axis_labs_no_special_contract(conn):
    # Axis Labs (ACCT-004) has no dedicated agreement PDF -- must fall back
    # to the general policy/SOP rather than fabricating contract terms.
    state = _run(conn, "priya_mehta", "What cancellation terms apply to Axis Labs?")
    assert state["decision_status"] == "READY"
    assert not any(c.document_name == "Northstar Enterprise Agreement" for c in state.get("doc_evidence", []))
    assert not any(c.document_name == "LumenWorks Service Agreement" for c in state.get("doc_evidence", []))


# --- SOP / policy (global, no account) ----------------------------------------

def test_eval_global_policy_p1_vs_p2_definition(conn):
    state = _run(conn, "manager", "What's the difference between a P1 and a P2 ticket?")
    assert state["decision_status"] == "READY"
    assert any(c.document_name == "Support Policy v3" for c in state.get("doc_evidence", []))


def test_eval_global_policy_deprecated_not_used_as_current(conn):
    state = _run(conn, "manager", "What are the current P1 response time targets for Enterprise customers?")
    assert state["decision_status"] == "READY"
    assert not any(c.status == "DEPRECATED" for c in state.get("doc_evidence", []))


# --- Historical tickets (context only, may be wrong) ---------------------------

def test_eval_historical_ticket_conflict_flagged_not_trusted(conn):
    state = _run(
        conn, "priya_mehta",
        "A previous ticket said Northstar pays a 250 rupee cancellation fee after 30 minutes for ORD-1001. Confirm that's correct.",
    )
    assert state["decision_status"] == "READY"
    assert state["policy_decision"].fee_inr == 0  # agreement waiver wins, not the historical claim


# --- Order investigation --------------------------------------------------------

def test_eval_order_investigation_service_credit_unseen_order(conn):
    # ORD-2002: RoadRunner, carrier_fault=True, no pickup yet, well past
    # LumenWorks' 4h contract threshold as of the reference time.
    state = _run(conn, "arjun_rao", "Is LumenWorks owed a credit for the delayed pickup on ORD-2002?")
    assert state["decision_status"] == "READY"
    assert state["policy_decision"].eligible is True


def test_eval_order_investigation_delivered_cannot_cancel(conn):
    # ORD-4001 (Axis Labs) is already DELIVERED -- an unseen order/status
    # combination for the cancellation resolver.
    state = _run(conn, "priya_mehta", "Can we still cancel ORD-4001 for Axis Labs?")
    assert state["decision_status"] == "READY"
    assert state["policy_decision"].allowed is False


# --- Multi-source (order + account + agreement + resolver) ---------------------

def test_eval_multi_source_northstar_second_order_no_waiver_scope_confusion(conn):
    # ORD-1002 is already PICKED_UP -- exercises the waiver-doesn't-apply
    # branch (Northstar's fee waiver is BOOKED-only) with an unseen order.
    state = _run(conn, "priya_mehta", "Can Northstar cancel ORD-1002 right now?")
    assert state["decision_status"] == "READY"
    assert state["policy_decision"].allowed is False


# --- Ambiguous questions ---------------------------------------------------------

def test_eval_ambiguous_followup_with_no_prior_context(conn):
    state = _run(conn, "priya_mehta", "What about the other shipment we were discussing?")
    assert state["decision_status"] == "NEEDS_REVIEW"


# --- Missing-information questions ------------------------------------------------

def test_eval_missing_information_credit_question_with_no_order(conn):
    # With no order named, this can't compute a specific credit decision --
    # the system explains LumenWorks' general eligibility rule (account-only
    # policy answer, same pattern as the cancellation-fee case) rather than
    # fabricating an amount. No resolver runs.
    state = _run(conn, "arjun_rao", "Should we issue a credit for the late pickup?")
    assert state.get("policy_decision") is None


def test_eval_off_topic_question_is_declined_not_guessed(conn):
    state = _run(conn, "priya_mehta", "What's the weather like today?")
    assert state["decision_status"] == "NEEDS_REVIEW"
    assert state.get("policy_decision") is None


# --- Conversational follow-ups ----------------------------------------------------

def test_eval_conversational_followup_resolves_pronoun(conn):
    conv_id = "eval-followup-pronoun"
    _run(conn, "priya_mehta", "What's the status of ORD-1002?", conversation_id=conv_id)
    user = get_user(conn, "priya_mehta")
    second = run("Can we cancel it instead?", user, conn, conversation_id=conv_id)
    assert second["decision_status"] == "READY"
    assert second["policy_decision"].allowed is False  # ORD-1002 is PICKED_UP


# --- Contextual actions ------------------------------------------------------------

def test_eval_contextual_action_escalate_after_investigation(conn):
    conv_id = "eval-contextual-action"
    _run(conn, "priya_mehta", "Why is TKT-505 urgent?", conversation_id=conv_id)
    user = get_user(conn, "priya_mehta")
    second = run("Please escalate this to a manager", user, conn, conversation_id=conv_id)
    assert second["decision_status"] == "AWAITING_CONFIRMATION"
    assert second.get("pending_action") is not None
    row = conn.execute(
        "SELECT status FROM actions WHERE action_id = ?", (second["pending_action"]["action_id"],)
    ).fetchone()
    assert row["status"] == "PREPARED"  # never auto-executed


# --- Source conflicts: assertions are on the deterministic resolver's OUTPUT,
# not on live-model wording, so a false/conflicting claim in the conversation
# provably never changes the actual decision. ----------------------------------

def test_eval_conflict_agreement_beats_sop_for_sla_target(conn):
    # Agreement vs SOP, on a DIFFERENT resolver (SLA target, not cancellation
    # fee) than the existing agreement-vs-historical case below -- Northstar's
    # agreement sets P1 at 15 minutes; the global Enterprise SOP default is 30.
    state = _run(conn, "priya_mehta", "How urgent is TKT-501, and what's the response target?")
    assert state["decision_status"] == "READY"
    assert state["policy_decision"].target_minutes == 15
    assert state["policy_decision"].provenance.source_document == "Northstar Enterprise Agreement"


def test_eval_conflict_current_policy_beats_invented_claim_no_agreement(conn):
    # Current policy vs a claimed-but-false number, for an account with NO
    # special agreement (Beacon/ACCT-003) -- proves the SOP default itself is
    # trusted over an invented figure, independent of any contract override.
    # ORD-3001 was cancelled 15 minutes after booking (within the 30-minute
    # free-cancellation window), so the correct SOP-default fee is 0 -- the
    # invented "half fee" claim must not change that.
    state = _run(
        conn, "neha_kapoor",
        "I heard Beacon only pays half the usual fee if we cancel now -- what's the "
        "actual cancellation fee for ORD-3001?",
    )
    assert state["decision_status"] == "READY"
    assert state["policy_decision"].fee_inr == 0
    assert state["policy_decision"].provenance.origin == "global_default"


def test_eval_conflict_agreement_beats_real_historical_ticket_record(conn):
    # Agreement vs historical ticket, using the ACTUAL historical_resolution
    # DB field on a real closed ticket (TKT-450: "Agent told customer a INR
    # 250 cancellation fee applied after 30 minutes") -- not a claim invented
    # in the query text. Exercises the real ticket-lookup -> historical-note
    # code path end-to-end, distinct from the query-text-only case below.
    state = _run(conn, "priya_mehta", "Was the fee mentioned in TKT-450 still correct for Northstar today?")
    assert state["decision_status"] == "READY"
    ticket_ctx = state["data_evidence"].get("ticket_context")
    assert ticket_ctx is not None and ticket_ctx.ticket_id == "TKT-450"
    assert any(c.document_name == "Northstar Enterprise Agreement" for c in state.get("doc_evidence", []))


def test_eval_conflict_three_way_agreement_sop_and_historical_ticket(conn):
    # Three sources referenced at once: LumenWorks' agreement (fixed INR 300
    # credit), the general SOP default (a different formula), and a false
    # number attributed to a real historical ticket (TKT-451) -- the
    # agreement must still win over both.
    state = _run(
        conn, "arjun_rao",
        "TKT-451 mentioned something about credits before, and I also thought the "
        "standard policy gives a flat 500 rupees -- what's the actual credit for "
        "the delayed pickup on ORD-2002?",
    )
    assert state["decision_status"] == "READY"
    assert state["policy_decision"].amount_inr == 300
    assert state["policy_decision"].provenance.origin == "account_policy_facts"


# --- Evidence sufficiency threshold: weak/no relevant evidence must yield
# uncertainty, never a confident fabricated answer. ------------------------------

def test_eval_evidence_threshold_out_of_corpus_topic_needs_review(conn):
    # A plausible-sounding support question about a topic that genuinely does
    # not appear anywhere in the 6-document corpus.
    state = _run(
        conn, "neha_kapoor",
        "What's ParcelPilot's policy on insuring high-value electronics shipments against theft?",
    )
    assert state["decision_status"] == "NEEDS_REVIEW"
    assert state.get("doc_evidence", []) == []
    assert state.get("policy_decision") is None


# --- Adversarial conversation ----------------------------------------------------

def test_eval_adversarial_pronoun_with_account_but_no_order_context(conn):
    # Turn 1 establishes account context ONLY (no order/ticket) -- turn 2's
    # "it" has no order/ticket antecedent. This is genuinely ambiguous input
    # (does "it" mean "my Northstar account's cancellation terms in general"
    # or an unnamed specific order?), and the live planner's classification
    # of it varies run to run: sometimes it asks for clarification
    # (NEEDS_REVIEW), sometimes it treats "it" as the already-active account
    # and gives Northstar's general cancellation policy (READY, no resolver).
    # Both are honest answers. The one outcome that would be a real defect --
    # inventing a specific order and computing a fabricated fee for it --
    # never happens either way, which is what this asserts.
    conv_id = "eval-adversarial-pronoun"
    _run(conn, "priya_mehta", "Does Northstar get 24/7 support coverage?", conversation_id=conv_id)
    user = get_user(conn, "priya_mehta")
    second = run("Can I cancel it without a fee?", user, conn, conversation_id=conv_id)
    assert second["decision_status"] in ("NEEDS_REVIEW", "READY")
    assert second.get("policy_decision") is None  # never a fabricated order-specific fee


def test_eval_adversarial_scenario_switch_same_order(conn):
    # Same order, scenario switches cancellation -> service_credit between
    # turns -- must not carry over the wrong decision type.
    conv_id = "eval-adversarial-scenario-switch"
    _run(conn, "priya_mehta", "Can Northstar cancel ORD-1001 without a fee?", conversation_id=conv_id)
    user = get_user(conn, "priya_mehta")
    second = run("What about a service credit for that same order?", user, conn, conversation_id=conv_id)
    assert second["decision_status"] == "READY"
    assert hasattr(second["policy_decision"], "eligible")  # CreditDecision, not CancellationDecision


def test_eval_adversarial_account_switch_mid_conversation(conn):
    # Priya is scoped to both Northstar and Axis Labs -- turn 2 explicitly
    # switches customer; citations must switch with it, not stay on Northstar.
    conv_id = "eval-adversarial-account-switch"
    _run(conn, "priya_mehta", "Can Northstar cancel ORD-1001 without a fee?", conversation_id=conv_id)
    user = get_user(conn, "priya_mehta")
    second = run("What about Axis Labs' cancellation policy instead?", user, conn, conversation_id=conv_id)
    assert second["decision_status"] == "READY"
    assert not any(c.document_name == "Northstar Enterprise Agreement" for c in second.get("doc_evidence", []))


def test_eval_ambiguous_account_confirmation_resumes_original_scenario(conn):
    # Found via live use, not designed test-first: Priya (scoped to both
    # Northstar and Axis) asks a service_credit question with no account
    # named, correctly gets asked "which account?", then replies with a bare
    # account-name confirmation that carries no topic information of its own
    # ("yes its about northstar only"). The follow-up must resume the
    # ORIGINAL service_credit question, not reclassify from the content-free
    # confirmation alone -- a real live failure showed this reclassifying to
    # "sla" and answering an unrelated question about response-time targets
    # instead of the customer's actual reimbursement question.
    conv_id = "eval-ambiguous-account-confirmation"
    first = _run(
        conn, "priya_mehta",
        "custom pickup was 1 hour late, do we need to give any reimbursememnt to him?",
        conversation_id=conv_id,
    )
    assert first["decision_status"] == "NEEDS_REVIEW"
    assert "which account" in first["answer_text"].lower()

    user = get_user(conn, "priya_mehta")
    second = run("yes its about northstar only", user, conn, conversation_id=conv_id)
    assert second.get("detected_scenario") == "service_credit"
    assert any(t["tool"] == "search_policy_documents" and t["args"] == "service_credit" for t in second.get("tool_call_log", []))


def test_eval_adversarial_insufficient_information_vague_request(conn):
    # Arjun is scoped to exactly one account (LumenWorks) -- per the
    # already-established single-account auto-resolve behavior, a vague
    # question with no order still resolves to his one account and gets a
    # general policy explanation, rather than being rejected outright. The
    # invariant that matters is that no resolver runs (no fabricated
    # decision for a nonexistent order), not that the system refuses to answer.
    state = _run(conn, "arjun_rao", "Can they get their money back?")
    assert state.get("policy_decision") is None


def test_eval_adversarial_hypothetical_question_no_real_order(conn):
    # Conditional/hypothetical phrasing, no real order referenced -- must
    # explain the general rule, not fabricate a decision for a nonexistent order.
    state = _run(
        conn, "arjun_rao",
        "If a pickup were 5 hours late due to carrier fault, would LumenWorks normally get a credit?",
    )
    assert state["decision_status"] == "READY"
    assert state.get("policy_decision") is None
    assert any(c.document_name == "LumenWorks Service Agreement" for c in state.get("doc_evidence", []))


def test_eval_adversarial_conflicting_claim_mid_conversation(conn):
    # Turn 1 establishes a real, computed credit decision; turn 2 asserts a
    # conflicting number as if it were fact -- the re-affirmed/corrected
    # decision must still be the deterministic one, not the asserted one.
    conv_id = "eval-adversarial-conflicting-claim"
    _run(conn, "arjun_rao", "Is LumenWorks owed a credit for the delayed pickup on ORD-2002?", conversation_id=conv_id)
    user = get_user(conn, "arjun_rao")
    second = run("Actually I read it should be a flat 500 rupee credit, right?", user, conn, conversation_id=conv_id)
    assert second["decision_status"] == "READY"
    assert second["policy_decision"].amount_inr == 300


def test_eval_adversarial_action_request_cold_start_no_context(conn):
    state = _run(conn, "priya_mehta", "Please escalate this issue", conversation_id="eval-cold-action")
    assert state["decision_status"] == "NEEDS_REVIEW"
    assert state.get("pending_action") is None


# --- Paraphrase robustness (LLM-based general_inquiry retrieval) -----------

def test_eval_paraphrase_defeats_keyword_overlap_but_llm_selection_finds_it(conn):
    # search_policy_documents' keyword-overlap ranking requires >=2 literal
    # shared words with a chunk's text. This question shares only one word
    # ("pickup") with the LumenWorks credit clause's text -- "refund" for
    # "credit", "courier" for "carrier", "dropped the ball on" for "at
    # fault" -- so pure keyword search would score it below the >=2
    # threshold and return nothing, even though the clause directly answers
    # the question. This is the specific failure mode LLM-based chunk
    # selection (app.agent._search_general_inquiry) exists to fix.
    state = _run(
        conn, "arjun_rao",
        "Do we get any money back if the courier dropped the ball on pickup timing?",
    )
    assert state["decision_status"] == "READY"
    assert any(
        c.document_name in ("LumenWorks Service Agreement", "Cancellation & Service Credit SOP v4")
        for c in state.get("doc_evidence", [])
    )
