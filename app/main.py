import json
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

from app import config, db
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


class ConfirmRequest(BaseModel):
    action_id: str
    user_id: str


@app.get("/", response_class=HTMLResponse)
def index(request: Request):
    return templates.TemplateResponse(request, "index.html")


@app.post("/api/investigate")
def investigate(body: InvestigateRequest):
    conn = _get_seeded_connection()
    user = get_user(conn, body.user_id)
    state = run(body.query, user, conn)
    return _serialize_state(state)


def _serialize_state(state: dict) -> dict:
    return {
        "answer_text": state.get("answer_text"),
        "tool_call_log": state.get("tool_call_log", []),
        "decision_status": state.get("decision_status"),
        "policy_decision": str(state.get("policy_decision")) if state.get("policy_decision") else None,
    }


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
        for name, payload in run_stream(body.query, user, conn):
            if name == "done":
                yield f"event: done\ndata: {json.dumps(_serialize_state(payload))}\n\n"
            else:
                yield f"event: step\ndata: {json.dumps({'node': name, 'label': payload})}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


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
