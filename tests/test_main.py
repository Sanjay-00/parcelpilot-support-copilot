from fastapi.testclient import TestClient

from app.main import app


def test_index_renders():
    client = TestClient(app)
    response = client.get("/")
    assert response.status_code == 200
    assert "ParcelPilot" in response.text


def test_confirm_action_endpoint_executes_a_prepared_action(monkeypatch):
    # Confirming an action doesn't need Gemini at all, so this test runs
    # unconditionally (no skipif) -- create_action/confirm_action are pure
    # deterministic code per Task 9. main.py's endpoint normally opens its
    # own connection via _get_seeded_connection() against a persistent,
    # file-backed DB_PATH; we monkeypatch that one function so this test can
    # supply an isolated in-memory connection instead, while still exercising
    # the real HTTP route end-to-end through TestClient.
    import app.main as main_module
    from app import db
    from app.actions import create_action
    from app.auth import get_user as _get_user, load as _load_users
    from app.config import DATA_PACK_XLSX
    from app.seed_accounts_orders_tickets import load as _load_base

    conn = db.get_connection(":memory:")
    db.init_schema(conn)
    _load_base(conn, DATA_PACK_XLSX)
    _load_users(conn)
    priya = _get_user(conn, "priya_mehta")
    draft = create_action(
        conn, "create_escalation", "ACCT-001", ticket_id="TKT-501", order_id=None,
        payload={"reason": "test"}, user=priya,
    )

    monkeypatch.setattr(main_module, "_get_seeded_connection", lambda: conn)

    client = TestClient(app)
    response = client.post(
        "/api/actions/confirm", json={"action_id": draft.action_id, "user_id": "priya_mehta"}
    )
    assert response.status_code == 200
    assert response.json()["status"] == "EXECUTED"


def test_investigate_stream_endpoint_emits_step_and_done_events(monkeypatch):
    # Confirms the SSE endpoint's framing without needing a real Gemini call:
    # both LLM-touching functions are mocked, so this exercises the real
    # LangGraph node sequence and the real HTTP/SSE plumbing, deterministically.
    from unittest.mock import patch

    import app.main as main_module
    from app import db
    from app.agent import _PlanExtraction
    from app.auth import load as _load_users
    from app.config import DATA_PACK_XLSX
    from app.policy_facts import load as _load_facts
    from app.seed_accounts_orders_tickets import load as _load_base

    conn = db.get_connection(":memory:")
    db.init_schema(conn)
    _load_base(conn, DATA_PACK_XLSX)
    _load_facts(conn)
    _load_users(conn)
    monkeypatch.setattr(main_module, "_get_seeded_connection", lambda: conn)

    with patch(
        "app.agent._plan",
        return_value=_PlanExtraction(scenario="cancellation", order_id="ORD-1001", ticket_id=None),
    ), patch("app.agent._explain", return_value="Mocked answer."):
        client = TestClient(app)
        response = client.post(
            "/api/investigate/stream",
            json={"query": "Can Northstar cancel ORD-1001?", "user_id": "priya_mehta"},
        )

    assert response.status_code == 200
    assert "text/event-stream" in response.headers["content-type"]
    body = response.text
    assert body.count("event: step") == 4  # plan, gather, resolve_order, explain
    assert '"fee_inr": 0.0' in body  # Northstar's agreement override, not the SOP default
    assert "event: done" in body
    assert "Mocked answer." in body
    assert "Understanding your question" in body


def test_list_actions_endpoint_scopes_by_authorization(monkeypatch):
    import app.main as main_module
    from app import db
    from app.actions import create_action
    from app.auth import get_user as _get_user, load as _load_users
    from app.config import DATA_PACK_XLSX
    from app.seed_accounts_orders_tickets import load as _load_base

    conn = db.get_connection(":memory:")
    db.init_schema(conn)
    _load_base(conn, DATA_PACK_XLSX)
    _load_users(conn)
    priya = _get_user(conn, "priya_mehta")  # scoped to ACCT-001, ACCT-004
    create_action(
        conn, "create_escalation", "ACCT-001", ticket_id="TKT-501", order_id=None,
        payload={"reason": "test"}, user=priya,
    )

    monkeypatch.setattr(main_module, "_get_seeded_connection", lambda: conn)
    client = TestClient(app)

    visible = client.get("/api/actions", params={"user_id": "priya_mehta"})
    assert visible.status_code == 200
    assert len(visible.json()["actions"]) == 1

    not_visible = client.get("/api/actions", params={"user_id": "arjun_rao"})  # scoped to ACCT-002 only
    assert not_visible.status_code == 200
    assert len(not_visible.json()["actions"]) == 0


def test_conversations_list_and_get_are_scoped_per_user(monkeypatch):
    import app.main as main_module
    from app import conversation, db
    from app.auth import load as _load_users
    from app.config import DATA_PACK_XLSX
    from app.seed_accounts_orders_tickets import load as _load_base

    conn = db.get_connection(":memory:")
    db.init_schema(conn)
    _load_base(conn, DATA_PACK_XLSX)
    _load_users(conn)
    monkeypatch.setattr(main_module, "_get_seeded_connection", lambda: conn)

    cid = conversation.new_conversation_id()
    conv = conversation.get_or_create("priya_mehta", cid)
    conversation.append_turn(conv, "user", "What are Northstar's cancellation fees?")
    conversation.append_turn(conv, "assistant", "Some answer.")

    client = TestClient(app)

    listed = client.get("/api/conversations", params={"user_id": "priya_mehta"})
    assert listed.status_code == 200
    convs = listed.json()["conversations"]
    assert any(c["conversation_id"] == cid for c in convs)
    assert next(c for c in convs if c["conversation_id"] == cid)["title"] == "What are Northstar's cancellation fees?"

    # A different user's listing must not include priya's conversation.
    other_listed = client.get("/api/conversations", params={"user_id": "arjun_rao"})
    assert not any(c["conversation_id"] == cid for c in other_listed.json()["conversations"])

    fetched = client.get(f"/api/conversations/{cid}", params={"user_id": "priya_mehta"})
    assert fetched.status_code == 200
    body = fetched.json()
    assert body["found"] is True
    assert len(body["turns"]) == 2

    # arjun_rao guessing priya's conversation_id must not retrieve her turns.
    forged = client.get(f"/api/conversations/{cid}", params={"user_id": "arjun_rao"})
    assert forged.json()["found"] is False


import os

import pytest


@pytest.mark.skipif(not os.environ.get("GEMINI_API_KEY"), reason="requires GEMINI_API_KEY")
def test_investigate_endpoint_returns_expected_shape():
    client = TestClient(app)
    response = client.post(
        "/api/investigate",
        json={"query": "Can Northstar cancel ORD-1001 without a cancellation fee?", "user_id": "priya_mehta"},
    )
    assert response.status_code == 200
    data = response.json()
    assert "answer_text" in data
    assert "tool_call_log" in data
    assert "decision_status" in data
