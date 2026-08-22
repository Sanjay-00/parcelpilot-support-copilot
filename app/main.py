import json
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

from app import config, conversation, db
from app.actions import confirm_action
from app.agent import run, run_stream
from app.auth import get_user, load as load_users
from app.documents import load as load_docs
from app.overview import issue_clusters, sla_risk_tickets
from app.policy_facts import load as load_facts
from app.seed_accounts_orders_tickets import load as load_base

app = FastAPI(title="ParcelPilot AI Support Operations Copilot")
_HERE = Path(__file__).parent
app.mount("/static", StaticFiles(directory=str(_HERE / "static")), name="static")
templates = Jinja2Templates(directory=str(_HERE / "templates"))


def _get_seeded_connection():
    conn = db.get_connection(config.DB_PATH)
    db.init_schema(conn)
    if conn.execute("SELECT COUNT(*) FROM accounts").fetchone()[0] == 0:
        load_base(conn, config.DATA_PACK_XLSX)
        load_facts(conn)
        load_docs(conn)
        load_users(conn)
    return conn


class InvestigateRequest(BaseModel):
    query: str
    user_id: str
    conversation_id: str | None = None


class ConfirmRequest(BaseModel):
    action_id: str
    user_id: str


@app.get("/", response_class=HTMLResponse)
def index(request: Request):
    return templates.TemplateResponse(request, "index.html")


def _serialize_provenance(prov) -> dict | None:
    if prov is None:
        return None
    return {
        "origin": prov.origin,
        "source_document": prov.source_document,
        "source_section": prov.source_section,
    }


def _serialize_decision(decision) -> dict | None:
    # Structured fields instead of a Python repr string -- the UI needs to
    # render an amount/severity + authority badge, not parse `str(decision)`.
    if decision is None:
        return None
    data: dict = {"kind": type(decision).__name__, "reason": getattr(decision, "reason", None)}
    if hasattr(decision, "allowed"):  # CancellationDecision
        data["allowed"] = decision.allowed
        data["fee_inr"] = decision.fee_inr
    if hasattr(decision, "eligible"):  # CreditDecision
        data["eligible"] = decision.eligible
        data["amount_inr"] = decision.amount_inr
        data["requires_manager_approval"] = decision.requires_manager_approval
    if hasattr(decision, "severity"):  # SLADecision
        data["severity"] = decision.severity
        data["target_minutes"] = decision.target_minutes
        data["elapsed_minutes"] = decision.elapsed_minutes
        data["at_risk"] = decision.at_risk
        data["is_wall_clock_proxy"] = decision.is_wall_clock_proxy
    data["provenance"] = _serialize_provenance(getattr(decision, "provenance", None))
    return data


def _serialize_citations(citations) -> list:
    return [
        {"document_name": c.document_name, "section": c.section, "text": c.text, "status": c.status}
        for c in (citations or [])
    ]


def _serialize_state(state: dict) -> dict:
    data_evidence = state.get("data_evidence") or {}
    account = data_evidence.get("account") or data_evidence.get("account_only")
    order = data_evidence.get("order")
    ticket = data_evidence.get("ticket")
    return {
        "answer_text": state.get("answer_text"),
        "tool_call_log": state.get("tool_call_log", []),
        "decision_status": state.get("decision_status"),
        "policy_decision": _serialize_decision(state.get("policy_decision")),
        "citations": _serialize_citations(state.get("doc_evidence")),
        "context": {
            "account_id": account.account_id if account else None,
            "account_name": account.account_name if account else None,
            "order_id": order.order_id if order else None,
            "ticket_id": ticket.ticket_id if ticket else None,
        },
        "pending_action": state.get("pending_action"),
        "conversation_id": state.get("conversation_id"),
    }


@app.post("/api/investigate")
def investigate(body: InvestigateRequest):
    conn = _get_seeded_connection()
    user = get_user(conn, body.user_id)
    state = run(body.query, user, conn, conversation_id=body.conversation_id)
    return _serialize_state(state)


@app.post("/api/investigate/stream")
def investigate_stream(body: InvestigateRequest):
    # Same underlying agent as /api/investigate, but surfaces each LangGraph
    # node as it genuinely completes (via run_stream) as a Server-Sent Event,
    # so the UI can show real progress instead of one opaque multi-second
    # wait. The final "done" event carries the same shape /api/investigate
    # returns, so existing consumers of that shape aren't affected.
    conn = _get_seeded_connection()
    user = get_user(conn, body.user_id)

    def event_stream():
        for name, payload in run_stream(body.query, user, conn, conversation_id=body.conversation_id):
            if name == "done":
                yield f"event: done\ndata: {json.dumps(_serialize_state(payload))}\n\n"
            else:
                yield f"event: step\ndata: {json.dumps({'node': name, 'label': payload})}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@app.get("/api/conversations")
def list_conversations(user_id: str):
    # Session-scoped only: this reads the same in-memory store agent.py
    # writes to, so the list is lost on process restart along with the
    # conversations themselves. There is no separate persistence layer here.
    convs = conversation.list_for_user(user_id)
    return {
        "conversations": [
            {
                "conversation_id": c.conversation_id,
                "title": c.title or "New conversation",
                "updated_at": c.updated_at,
                "active_account_id": c.active_account_id,
                "active_order_id": c.active_order_id,
                "active_ticket_id": c.active_ticket_id,
            }
            for c in convs
        ]
    }


@app.get("/api/conversations/{conversation_id}")
def get_conversation(conversation_id: str, user_id: str):
    # get() never creates -- a conversation_id that doesn't belong to this
    # user_id simply isn't found, same isolation guarantee as investigate().
    conv = conversation.get(user_id, conversation_id)
    if conv is None:
        return {"conversation_id": conversation_id, "found": False, "turns": []}
    return {
        "conversation_id": conversation_id,
        "found": True,
        "turns": [{"role": t.role, "text": t.text} for t in conv.turns],
    }


@app.get("/api/overview")
def overview(user_id: str):
    conn = _get_seeded_connection()
    user = get_user(conn, user_id)
    return {"clusters": issue_clusters(conn, user), "sla_risk": sla_risk_tickets(conn, user)}


@app.post("/api/actions/confirm")
def confirm(body: ConfirmRequest):
    conn = _get_seeded_connection()
    user = get_user(conn, body.user_id)
    result = confirm_action(conn, body.action_id, user)
    return {"status": result.status}


@app.get("/api/actions")
def list_actions(user_id: str):
    from app.auth import authorize

    conn = _get_seeded_connection()
    user = get_user(conn, user_id)
    rows = conn.execute("SELECT * FROM actions ORDER BY created_at DESC").fetchall()
    visible = [dict(r) for r in rows if authorize(user, r["account_id"])]
    return {"actions": visible}
