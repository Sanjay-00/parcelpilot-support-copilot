from typing import TypedDict

from google import genai
from langgraph.graph import END, START, StateGraph
from pydantic import BaseModel

from app import config
from app.models import StaffUser
from app.resolvers import resolve_cancellation, resolve_service_credit, resolve_sla
from app.severity import extract_incident_facts, map_severity
from app.tools import AccessDenied, get_account, get_order, get_ticket, search_policy_documents


class AgentState(TypedDict, total=False):
    user_query: str
    detected_scenario: str | None
    entities: dict
    authorization_result: str
    doc_evidence: list
    data_evidence: dict
    incident_facts: object
    policy_decision: object
    decision_status: str
    tool_call_log: list
    answer_text: str
    _severity: str | None
    _severity_needs_review: bool


class _PlanExtraction(BaseModel):
    scenario: str   # "cancellation" | "service_credit" | "sla"
    order_id: str | None = None
    ticket_id: str | None = None


_PLAN_PROMPT = """Classify this support query and extract any order/ticket ID mentioned.
scenario must be exactly one of: cancellation, service_credit, sla.

Query: {query}

Answer as JSON: {{"scenario": "...", "order_id": "ORD-..." or null, "ticket_id": "TKT-..." or null}}
"""


def _plan(query: str) -> _PlanExtraction:
    client = genai.Client(api_key=config.require_gemini_api_key())
    response = client.models.generate_content(
        model="gemini-2.0-flash",
        contents=_PLAN_PROMPT.format(query=query),
        config={"response_mime_type": "application/json", "response_schema": _PlanExtraction},
    )
    return _PlanExtraction.model_validate_json(response.text)


def _explain(query: str, decision, citations) -> str:
    client = genai.Client(api_key=config.require_gemini_api_key())
    citation_text = "\n".join(f"- {c.document_name} {c.section}: {c.text}" for c in citations)
    prompt = (
        f"A support agent asked: {query}\n\n"
        f"The deterministic decision (already computed, do not recompute or contradict "
        f"any number in it) is: {decision}\n\n"
        f"Supporting evidence:\n{citation_text}\n\n"
        f"Write a short, direct answer citing the relevant source(s) by name and section. "
        f"If the decision's provenance shows an account-specific override, explain that it "
        f"takes precedence over the general policy/SOP."
    )
    response = client.models.generate_content(model="gemini-2.0-flash", contents=prompt)
    return response.text


def plan_node(state: AgentState) -> dict:
    plan = _plan(state["user_query"])
    return {
        "detected_scenario": plan.scenario,
        "entities": {"order_id": plan.order_id, "ticket_id": plan.ticket_id},
    }


def gather_node(state: AgentState, config_: dict) -> dict:
    conn = config_["configurable"]["conn"]
    user = config_["configurable"]["user"]
    entities = state["entities"]
    tool_log = list(state.get("tool_call_log", []))

    try:
        if entities.get("order_id"):
            order = get_order(conn, entities["order_id"], user)
            account = get_account(conn, order.account_id, user)
            citations = search_policy_documents(conn, state["detected_scenario"], order.account_id, user)
            tool_log += [
                {"tool": "get_order", "args": entities["order_id"]},
                {"tool": "search_policy_documents", "args": state["detected_scenario"]},
            ]
            return {
                "data_evidence": {"order": order, "account": account},
                "doc_evidence": citations, "tool_call_log": tool_log,
                "authorization_result": "AUTHORIZED",
            }
        elif entities.get("ticket_id"):
            ticket = get_ticket(conn, entities["ticket_id"], user)
            account = get_account(conn, ticket.account_id, user)
            citations = search_policy_documents(conn, "sla", ticket.account_id, user)
            tool_log += [{"tool": "get_ticket", "args": entities["ticket_id"]}]
            return {
                "data_evidence": {"ticket": ticket, "account": account},
                "doc_evidence": citations, "tool_call_log": tool_log,
                "authorization_result": "AUTHORIZED",
            }
        else:
            return {
                "authorization_result": "N/A", "decision_status": "NEEDS_REVIEW",
                "answer_text": "I couldn't identify an order or ticket in this query.",
            }
    except AccessDenied:
        return {
            "authorization_result": "DENIED", "decision_status": "NEEDS_REVIEW",
            "answer_text": "Access denied for this account.",
        }
    except LookupError:
        return {
            "authorization_result": "NOT_FOUND", "decision_status": "NEEDS_REVIEW",
            "answer_text": "That record could not be found.",
        }


def _route_after_gather(state: AgentState) -> str:
    if state.get("authorization_result") in ("DENIED", "NOT_FOUND", "N/A"):
        return "end"
    if "order" in state.get("data_evidence", {}):
        return "resolve_order"
    return "classify_severity"


def resolve_order_node(state: AgentState, config_: dict) -> dict:
    conn = config_["configurable"]["conn"]
    reference_time = config_["configurable"]["reference_time"]
    order = state["data_evidence"]["order"]
    if state["detected_scenario"] == "cancellation":
        decision = resolve_cancellation(conn, order)
    else:
        decision = resolve_service_credit(conn, order, reference_time)
    return {
        "policy_decision": decision,
        "decision_status": "NEEDS_REVIEW" if getattr(decision, "needs_review", False) else "READY",
    }


def classify_severity_node(state: AgentState) -> dict:
    ticket = state["data_evidence"]["ticket"]
    incident_facts = extract_incident_facts(ticket.subject, ticket.description)
    severity, needs_review = map_severity(incident_facts)
    return {"incident_facts": incident_facts, "_severity": severity, "_severity_needs_review": needs_review}


def _route_after_severity(state: AgentState) -> str:
    if state.get("_severity_needs_review") or state.get("_severity") is None:
        return "needs_review"
    return "resolve_sla"


def severity_needs_review_node(state: AgentState) -> dict:
    return {
        "decision_status": "NEEDS_REVIEW",
        "answer_text": (
            "I can't confidently classify this ticket's severity from the available "
            "text — recommend human review before responding."
        ),
    }


def resolve_sla_node(state: AgentState, config_: dict) -> dict:
    conn = config_["configurable"]["conn"]
    reference_time = config_["configurable"]["reference_time"]
    ticket = state["data_evidence"]["ticket"]
    account = state["data_evidence"]["account"]
    decision = resolve_sla(conn, ticket, account, state["_severity"], reference_time)
    return {"policy_decision": decision, "decision_status": "READY"}


def explain_node(state: AgentState) -> dict:
    decision = state.get("policy_decision")
    if decision is None:
        return {}
    citations = state.get("doc_evidence", [])
    return {"answer_text": _explain(state["user_query"], decision, citations)}


def build_graph():
    graph = StateGraph(AgentState)
    graph.add_node("plan", plan_node)
    graph.add_node("gather", gather_node)
    graph.add_node("resolve_order", resolve_order_node)
    graph.add_node("classify_severity", classify_severity_node)
    graph.add_node("resolve_sla_step", resolve_sla_node)
    graph.add_node("severity_needs_review", severity_needs_review_node)
    graph.add_node("explain", explain_node)

    graph.add_edge(START, "plan")
    graph.add_edge("plan", "gather")
    graph.add_conditional_edges(
        "gather", _route_after_gather,
        {"end": END, "resolve_order": "resolve_order", "classify_severity": "classify_severity"},
    )
    graph.add_edge("resolve_order", "explain")
    graph.add_conditional_edges(
        "classify_severity", _route_after_severity,
        {"needs_review": "severity_needs_review", "resolve_sla": "resolve_sla_step"},
    )
    graph.add_edge("resolve_sla_step", "explain")
    graph.add_edge("explain", END)
    graph.add_edge("severity_needs_review", END)
    return graph.compile()


_COMPILED_GRAPH = build_graph()


def run(user_query: str, user: StaffUser, conn) -> AgentState:
    initial_state: AgentState = {"user_query": user_query, "tool_call_log": []}
    return _COMPILED_GRAPH.invoke(
        initial_state,
        config={"configurable": {
            "conn": conn, "user": user,
            "reference_time": config.REFERENCE_TIME.replace(tzinfo=None),
        }},
    )
