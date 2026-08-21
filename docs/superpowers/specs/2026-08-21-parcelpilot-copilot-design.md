# ParcelPilot AI Support Operations Copilot — Design Specification

Status: draft, pending review
Date: 2026-08-21
Scope: CalQuity AI Engineer hiring assessment — ParcelPilot Customer Support

## 1. Problem statement

ParcelPilot's 20-person support team resolves customer requests (cancellations,
service credits, SLA questions, product issues) by manually reconciling five
inconsistent sources: a current support policy, a deprecated support policy,
a cancellation/service-credit SOP, a product/known-issues guide, per-customer
enterprise agreements, and historical ticket notes that may themselves be
wrong. The assessment requires a system that automates this reconciliation
for **authorised internal ParcelPilot staff**, while:

- treating sources as having different authority (signed customer agreement >
  current SOP/policy > product docs > historical tickets, and this precedence
  operates **per clause/scenario, not per document**),
- enforcing account-level access scoping in the tool/data layer, not via
  prompt instructions,
- supporting multi-step, multi-tool investigations,
- requiring explicit human confirmation before any state-changing action,
- generalising to held-out accounts/orders/tickets from the same pack rather
  than hard-coding the example IDs.

The chosen additional client problem is **Trust & Reliability**. Proactive
issue detection is included as a lightweight secondary feature that reuses
the same infrastructure, not as a second primary pillar.

## 2. Product scope

**In scope:** internal ops copilot ("Investigate" NL chat + "Overview"
proactive signals + "Actions/Audit" trail) for authorised ParcelPilot staff,
built only from the supplied data pack (`01`–`06` PDFs +
`ParcelPilot_Assessment_Data.xlsx`).

**Out of scope:** customer-facing chatbot, real authentication, real
carrier/ticketing system integration, any data not present in or derivable
from the supplied pack.

**Core architectural principle** (the thesis the whole design defends):

> The LLM understands intent, plans which evidence is needed, extracts
> genuinely unstructured facts from free text, and explains conclusions in
> natural language. It never authorizes access, never performs the business
> calculation, and never triggers a state change. Deterministic Python code
> retrieves records, resolves policy, runs guardrails, and executes actions.
> No LLM output may directly authorize a state-changing action. No retrieved
> document chunk may directly modify a policy decision.

## 3. Architecture

```
                     Natural-language query
                              |
                              v
                      Query Planner (LLM)
              intent, scenario, entities (account/order/ticket)
                              |
                              v
                 Authorization (deterministic, BEFORE any tool runs)
                 resolve+validate account_id against current_user scope
                              |
                 -------------+-------------
                 |                         |
                 v                         v
       query_operations_data      search_policy_documents
         (SQLite, typed facts)      (chunks, citations only)
                 |                         |
                 v                         v
          OrderFacts/TicketFacts/     Evidence (citations,
          AccountFacts                 source + section)
                 |                         |
                 +------------+------------+
                              v
                Policy Resolution (deterministic)
        resolve_cancellation / resolve_service_credit / resolve_sla
             reads account_policy_facts via get_fact(...)
                              |
                              v
                     Guardrails (deterministic)
        unknown-fault block, >₹1,000 approval, conflict -> NEEDS_REVIEW
                              |
                              v
                    Decision object (typed)
                              |
                              v
                   LLM explanation (cites evidence)
                              |
                              v
                 Human confirmation (UI, explicit)
                              |
                              v
                   create_action / confirm_action
                        (SQLite, audited)
```

A parallel, much smaller path reuses `query_operations_data` and the same
resolvers to populate the **Overview** tab (SLA-risk tickets, known-issue
clusters) — it is not a separate architecture, just a scheduled/on-demand
read over the same tables.

**Why LangGraph:** the workflow above is a small number of ordered/branching
steps with state carried between them (detected entities, evidence,
decision, pending action) — exactly what a stateful graph models, and it's
a framework the developer already has real experience with. **Rejected:**
a generic multi-agent framework (no need for multiple independent agents —
this is one workflow with tool calls, not a swarm); a hand-rolled loop was
considered and rejected only because LangGraph is already known, not
because hand-rolling is wrong in principle.

## 4. Component responsibilities

| Component | Responsibility | Must NOT do |
|---|---|---|
| Query Planner (LLM) | classify scenario, extract entities, decide which tools are needed | authorize access, compute fees/credits/SLA, decide actions |
| Authorization | resolve requested account against `current_user`, fail closed | trust LLM-extracted account_id without validation |
| `query_operations_data` | typed, account-scoped reads/joins over SQLite | expose arbitrary SQL to the LLM |
| `search_policy_documents` | return citable text chunks, scoped by account+scenario+status | influence the numeric/decision outcome |
| Resolvers (`resolve_*`) | deterministic policy math per scenario, reading `account_policy_facts` | read document chunk text |
| Guardrails | unknown-data block, approval threshold, conflict -> NEEDS_REVIEW | be bypassable by high LLM confidence |
| Action layer | prepared -> confirmed -> executed/failed, audited | execute without explicit user confirmation |
| LLM explanation | turn the decision object + evidence into prose with citations | introduce facts not present in the decision object |
| UI | render tool-call timeline, evidence, decision, confirmation | display hidden model reasoning/chain-of-thought |

## 5. SQLite schema

```sql
-- verbatim from the supplied workbook
CREATE TABLE accounts (
  account_id TEXT PRIMARY KEY,
  account_name TEXT, plan TEXT, status TEXT, csm TEXT,
  contract_file TEXT, premium_support INTEGER, notes TEXT
);

CREATE TABLE orders (
  order_id TEXT PRIMARY KEY,
  account_id TEXT REFERENCES accounts(account_id),
  carrier TEXT, status TEXT,
  booked_at TEXT, pickup_window_start TEXT, pickup_window_end TEXT,
  pickup_actual_at TEXT, shipment_fee_inr REAL,
  carrier_fault INTEGER, customer_fault INTEGER,   -- nullable: 0/1/NULL = unknown
  cancellation_requested_at TEXT, notes TEXT
);

CREATE TABLE tickets (
  ticket_id TEXT PRIMARY KEY,
  account_id TEXT REFERENCES accounts(account_id),
  created_at TEXT, status TEXT, subject TEXT, description TEXT,
  channel TEXT, assigned_to TEXT, last_customer_message_at TEXT,
  historical_resolution TEXT   -- context only, may be wrong; never authoritative
);

-- derived once from the two agreement PDFs, hand-verified, checked into the repo
CREATE TABLE account_policy_facts (
  account_id TEXT REFERENCES accounts(account_id),
  scenario TEXT,           -- cancellation | service_credit | sla
  fact_name TEXT,
  fact_value TEXT,         -- stored as text, cast at read time
  source_document TEXT,
  source_section TEXT,
  PRIMARY KEY (account_id, scenario, fact_name)
);

-- ingestion artifact, citation-only, never read by resolvers
CREATE TABLE document_chunks (
  chunk_id TEXT PRIMARY KEY,
  document_id TEXT, document_name TEXT, document_type TEXT,
  customer_id TEXT,        -- NULL for global documents
  status TEXT,             -- CURRENT | DEPRECATED | ACTIVE
  effective_date TEXT,
  section TEXT,
  scenario_tags TEXT,      -- comma list
  text TEXT
);

CREATE TABLE actions (
  action_id TEXT PRIMARY KEY,
  action_type TEXT,        -- create_escalation | update_ticket | create_followup
  account_id TEXT, ticket_id TEXT, order_id TEXT,
  payload_json TEXT,
  prepared_by TEXT,
  status TEXT,             -- PREPARED | REJECTED | CONFIRMED | EXECUTED | FAILED
  created_at TEXT, confirmed_at TEXT, executed_at TEXT
);

CREATE TABLE audit_logs (
  log_id TEXT PRIMARY KEY, timestamp TEXT, user TEXT, query_text TEXT,
  account_id TEXT, tools_used_json TEXT, evidence_json TEXT,
  decision_json TEXT, action_id TEXT, confidence TEXT
);

-- mocked RBAC, explicitly labeled as such in the UI/README
CREATE TABLE staff_users (
  user_id TEXT PRIMARY KEY, name TEXT, role TEXT,   -- agent | manager
  assigned_account_ids TEXT   -- JSON list, or "*" for manager
);
```

`staff_users` seed data: Priya Mehta (ACCT-001, ACCT-004), Arjun Rao
(ACCT-002), Neha Kapoor (ACCT-003) — derived from `accounts.csm` — plus one
`manager` row with `"*"`. Documented in the README as mocked, not a real
ParcelPilot org chart.

## 6. Document chunk schema

One chunk per numbered section of each PDF (each source document is a single
page with 3-4 numbered sections, so this yields ~20-25 chunks total).
`scenario_tags` vocabulary: `cancellation`, `service_credit`, `sla`,
`product_capability`, `known_issue`, `security`. Global policy/SOP/product
docs get `customer_id = NULL`; the two agreements get their `ACCT-00x` id.
`status` mirrors each document's own stated status (`CURRENT`, `DEPRECATED`,
`ACTIVE`). Chunks are produced once at ingestion time from the PDFs and
committed as data (or regenerated by a small, reviewed script) — never
parsed at request time.

## 7. Account policy facts schema

See §5. Example rows derived from the two agreements:

```
ACCT-001, cancellation,    fee_waived,              true,  Northstar Enterprise Agreement, §2
ACCT-001, cancellation,    waiver_scope,             booked_before_pickup_any_time, Northstar Enterprise Agreement, §2
ACCT-001, service_credit,  monthly_cap_inr,          5000,  Northstar Enterprise Agreement, §3
ACCT-001, sla,             p1_target_minutes,        15,    Northstar Enterprise Agreement, §1
ACCT-001, sla,             p2_target_minutes,        60,    Northstar Enterprise Agreement, §1
ACCT-001, sla,             p3_target_minutes,        480,   Northstar Enterprise Agreement, §1
ACCT-001, sla,             coverage,                 24x7,  Northstar Enterprise Agreement, §1
ACCT-002, service_credit,  delay_threshold_hours,    4,     LumenWorks Service Agreement, §3
ACCT-002, service_credit,  credit_amount_inr,        300,   LumenWorks Service Agreement, §3
ACCT-002, sla,             p1_target_minutes,        120,   LumenWorks Service Agreement, §1
ACCT-002, sla,             p2_target_minutes,        240,   LumenWorks Service Agreement, §1
ACCT-002, sla,             p3_target_minutes,        2880,  LumenWorks Service Agreement, §1
ACCT-002, sla,             coverage,                 business_hours, LumenWorks Service Agreement, §1
```
ACCT-003 and ACCT-004 have no rows — resolvers fall through to global
defaults, which is the correct behaviour for the grader's held-out accounts
too, since any new account with no override row behaves identically.

`get_fact(account_id, scenario, fact_name, default)` is the only way
resolvers read this table.

**Rationale:** normalized long form (not wide columns) so each fact keeps
its own `source_document`/`source_section` — this is what actually
substantiates the "clause-level, not document-level" precedence claim.
Rejected: a generic rule DSL with condition strings (only 3 scenarios and 2
customers exist; an interpreter would add a failure surface with no
matching problem to solve).

## 8. Resolver contracts

```python
@dataclass
class CancellationDecision:
    allowed: bool
    fee_inr: float | None
    reason: str
    source: str            # "account_policy_facts" | "SOP v4"

@dataclass
class CreditDecision:
    eligible: bool
    amount_inr: float | None
    requires_manager_approval: bool
    needs_review: bool
    reason: str
    source: str

@dataclass
class SLADecision:
    severity: str           # P1 | P2 | P3
    target_minutes: int
    elapsed_minutes: float
    at_risk: bool
    is_first_response_proxy: bool = True   # see §17 limitation
    source: str

def resolve_cancellation(order: OrderFacts, account_id: str) -> CancellationDecision: ...
def resolve_service_credit(order: OrderFacts, account_id: str, reference_time: datetime) -> CreditDecision: ...
def resolve_sla(ticket: TicketFacts, account: AccountFacts, incident: IncidentFacts, reference_time: datetime) -> SLADecision: ...
```

`resolve_cancellation` logic (from SOP v4 §1 + agreement overrides):
`DRAFT` -> allowed, fee 0. `PICKED_UP`/`DELIVERED` -> not allowed (use
return-to-origin / cannot cancel). `BOOKED`, not picked up -> check
`get_fact(account_id, "cancellation", "fee_waived")`; if true and scope
matches, fee 0; else fee 0 if `cancellation_requested_at - booked_at <= 30min`
else 250.

`resolve_service_credit` logic (SOP v4 §2 + agreement overrides): if
`carrier_fault` or `customer_fault` is `NULL` -> `needs_review=True`,
`eligible=False`, reason "fault unknown, cannot promise a credit per SOP".
If `customer_fault` -> not eligible. Delay = `pickup_actual_at -
pickup_window_end` if `pickup_actual_at` is set, else `reference_time -
pickup_window_end` (explicitly distinguishing "delivered late" from "still
not picked up as of the reference time" — this was the bug flagged and
fixed in review). Threshold = `get_fact(..., "delay_threshold_hours", default=2)`.
If delay <= threshold or not `carrier_fault` -> not eligible. Else amount =
`get_fact(..., "credit_amount_inr", default=min(500, 0.10*shipment_fee_inr))`;
`requires_manager_approval = amount > 1000`.

`resolve_sla` logic: severity comes from `IncidentFacts` (§13) mapped per
Policy v3 §2's exact P1/P2/P3 definitions. Target minutes from
`get_fact(..., "p{n}_target_minutes")` falling back to the plan-tier default
table in Policy v3 §3. Elapsed = `reference_time - ticket.created_at`.
Flagged explicitly as a proxy (§17) since no first-response timestamp
exists in the data.

## 9. Retrieval algorithm

```
search_policy_documents(scenario, account_id, keyword=None, current_user):
    assert current_user is authorized for account_id            # never trust caller
    candidates = document_chunks WHERE status != 'DEPRECATED'
                 AND (customer_id IS NULL OR customer_id == account_id)
                 AND scenario IN scenario_tags
    if keyword:
        candidates = rank(candidates, by=text_contains(keyword))  # ranks WITHIN
                                                                    # candidates, never escapes
                                                                    # the authorized/scenario set
    order: customer-specific chunks before global chunks
    return candidates as Citation[document, section, text, status, effective_date]
```

A separate, explicitly-invoked `compare_with_deprecated_policy(account_id,
current_user)` path exists only for a user literally asking to compare
against v2; its output is always labeled "historical, non-authoritative" and
is never passed into a resolver.

**Rationale for no embeddings:** ~20-25 short, clearly-sectioned chunks
across 6 documents; exact identifiers (`ORD-1001`, `KI-208`) matter more
than semantic recall. Metadata + keyword retrieval is fully deterministic,
auditable ("this chunk was returned because it's tagged `cancellation` and
scoped to ACCT-001"), and needs no embedding-API dependency during a live
demo. Rejected: pgvector/Chroma — solves a scale problem this 6-document
corpus doesn't have; can be swapped in later behind the same
`search_policy_documents` interface if the corpus grows.

## 10. Authorization model

```
1. LLM extracts a candidate account_id/order_id/ticket_id from the query.
2. Deterministic code resolves the actual owning account_id for any
   order_id/ticket_id (never trusts an LLM-asserted account_id in isolation).
3. Check current_user.assigned_account_ids (or "*" for manager).
4. If not authorized: return ACCESS_DENIED and STOP — no tool executes,
   and existence is not confirmed or denied (an agent authorized only for
   ACCT-002 asking "does ORD-1001 exist?" gets ACCESS_DENIED, not "not
   found" and not the record).
5. Only on success do query_operations_data / search_policy_documents run.
```
Enforced inside the tool functions themselves (they take `current_user` and
raise/return denial before touching SQLite), not by a system prompt.

## 11. LangGraph state shape

```python
class AgentState(TypedDict):
    user_query: str
    current_user: StaffUser
    detected_scenario: str | None
    entities: dict                    # {account_id, order_id, ticket_id}
    authorization_result: str         # AUTHORIZED | DENIED
    doc_evidence: list[Citation]
    data_evidence: dict                # OrderFacts | TicketFacts | AccountFacts
    incident_facts: IncidentFacts | None
    policy_decision: CancellationDecision | CreditDecision | SLADecision | None
    confidence: str                    # HIGH | MEDIUM | LOW
    decision_status: str               # READY | NEEDS_REVIEW
    tool_call_log: list[dict]          # rendered in the UI timeline
    pending_action: ActionDraft | None
    answer_text: str
```

## 12. Tool contracts

```python
def query_operations_data(operation: str, params: dict, current_user: StaffUser) -> AccountFacts | OrderFacts | TicketFacts | list[...]:
    # operations: get_account, get_order, get_ticket, get_account_orders,
    #             get_account_tickets, compute_pickup_delay, list_sla_risk_tickets
    ...

def search_policy_documents(scenario: str, account_id: str | None, keyword: str | None, current_user: StaffUser) -> list[Citation]:
    ...

def create_action(action_type: str, payload: dict, current_user: StaffUser) -> ActionDraft:   # status=PREPARED
    ...

def confirm_action(action_id: str, current_user: StaffUser) -> ActionResult:                  # PREPARED->CONFIRMED->EXECUTED|FAILED
    ...
```
`resolve_cancellation`/`resolve_service_credit`/`resolve_sla` are called by
the graph orchestration directly, not exposed as agent-choosable tools —
once both evidence sources are gathered for a decision-bearing query, policy
resolution always runs; it is not something the LLM opts into.

## 13. IncidentFacts extraction contract

```python
class IncidentFacts(BaseModel):
    is_security_incident: bool | Literal["unknown"]
    is_complete_outage: bool | Literal["unknown"]
    is_major_feature_degraded: bool | Literal["unknown"]
    workaround_exists: bool | Literal["unknown"]
```
The LLM extracts this from `ticket.subject` + `ticket.description` only
(never asked to infer facts already in SQLite, e.g. order status). Validated
against this strict schema before use. Deterministic mapping (Policy v3
§2): `is_security_incident` or `is_complete_outage` -> P1; else
`is_major_feature_degraded` -> P2; else P3. Any required field `"unknown"`
with no safe default -> `decision_status = NEEDS_REVIEW` instead of guessing.

**Rationale:** keyword/regex classification was rejected because it won't
generalise to differently-worded held-out tickets; the LLM does the
inherently linguistic step (does this text describe an outage?), while the
P1/P2/P3 mapping — the actual policy application — stays 100% deterministic
and unit-testable given fixed booleans.

## 14. Action state machine

```
PREPARED -> REJECTED
PREPARED -> CONFIRMED -> EXECUTED
PREPARED -> CONFIRMED -> FAILED
```
No persisted `EXECUTING` state: execution is synchronous against local
SQLite, so no state exists where "in progress" would ever be observed.
`FAILED` exists so a write exception can't be silently recorded as
`EXECUTED`. Every transition writes an `audit_logs` row. Nothing reaches
`EXECUTED` without a UI-triggered `confirm_action` call.

## 15. Golden evaluation strategy

Implemented as `pytest` cases **before** the LangGraph workflow is wired up,
run directly against the resolvers/tools so failures point at the exact
deterministic function, not "the agent seems wrong." At minimum:

1. ORD-1001 Northstar cancellation -> fee 0 (override)
2. ORD-1002 Northstar PICKED_UP -> not allowed, return-to-origin
3. ORD-2001 LumenWorks 75min -> fee 250 (SOP default, no waiver)
4. ORD-2002 LumenWorks carrier fault -> credit 300 (override)
5. ORD-3001 Beacon <30min -> fee 0 (SOP default)
6. ORD-4001 DELIVERED -> not allowed
7. TKT-505 Axis API key exposure -> P1
8. TKT-501 Northstar outage -> P1, 15-min SLA (override)
9. TKT-502 LumenWorks bulk upload -> within 5,000-row limit, KI-208 workaround given, not "3,000-row limit"
10. TKT-504 Northstar BOOKED-after-pickup -> matches KI-211, hold/verify
11. TKT-450 historical-conflict probe -> "₹250?" answered No, agreement overrides, both sources cited
12. TKT-451 historical-conflict probe -> "3,000-row limit?" answered No, 5,000 is the real limit
13. unauthorized cross-account query -> ACCESS_DENIED
14. unauthorized existence probe -> ACCESS_DENIED, not "not found"
15. unknown order/account id -> NOT_FOUND, no hallucinated answer
16. missing carrier_fault/customer_fault -> NEEDS_REVIEW, no promised credit
17. synthetic credit amount > ₹1,000 -> eligible + `requires_manager_approval=True`
18. explicit "what does the deprecated policy say" -> served only via the comparison path, labeled historical

Tests assert on the typed decision object fields (severity, fee_inr,
amount_inr, source, decision_status), not on LLM prose.

## 16. UI information architecture

Single page, FastAPI + Jinja2 + vanilla JS, tabs (no routing):

- **Overview** — SLA-risk tickets, open P1/P2s, known-issue clusters (reads
  the same `query_operations_data`/`resolve_sla` used by Investigate).
- **Investigate** — chat input; live tool-call timeline ("🔍
  search_policy_documents(cancellation, ACCT-001)"); evidence/citation
  cards with source+section; decision card (fee/credit/severity +
  confidence + `decision_status`); confirm-action modal when an action is
  proposed.
- **Actions / Audit** — table of prepared/confirmed/executed/failed
  actions with the full audit trail.
- Top-right "Log in as: Priya Mehta / Arjun Rao / Neha Kapoor / Manager"
  selector (mocked auth).

The UI shows tool execution and evidence, never raw model chain-of-thought.

## 17. Failure / uncertainty handling

- `confidence` (HIGH/MEDIUM/LOW, evidence completeness) is **distinct**
  from `decision_status` (READY/NEEDS_REVIEW, whether a human must act
  first). Low confidence alone does not imply `NEEDS_REVIEW`, and high
  confidence never overrides a guardrail that forces `NEEDS_REVIEW`.
- Known data limitation: the workbook has no first-agent-response
  timestamp, only `created_at` and `last_customer_message_at` (the
  customer's message, not the agent's). `resolve_sla` therefore computes
  and **explicitly labels** an "SLA risk proxy" (ticket age vs. target),
  and does not claim to measure true first-response compliance. This is
  documented, not silently assumed.
- Business-hours vs 24x7 targets are distinguished by `coverage`, but no
  full business-calendar engine is built (see Non-goals) — business hours
  are approximated as a fixed daily window, documented as a simplification.
- Unknown fault data, monetary approval thresholds, and detected source
  conflicts all route to `NEEDS_REVIEW` per the SOP's own explicit
  guardrail text (§2 SOP: don't promise a credit with unknown fault; >₹1,000
  needs manager approval; identify conflicts and request verification
  before a state-changing action) — these are not invented heuristics.

## 18. Security considerations

- Access control enforced in `query_operations_data`/
  `search_policy_documents`/action tools, never via system-prompt
  instruction.
- Fail closed: authorization runs before any tool call; a denied request
  produces `ACCESS_DENIED` and no further evidence is gathered.
- Existence is not leaked to unauthorized callers (a denied lookup for a
  real record looks identical to one for a nonexistent record).
- State-changing actions require an explicit, UI-triggered confirmation
  step; nothing executes on LLM assertion alone.
- RBAC is explicitly documented as mocked for the assessment, not a
  real ParcelPilot access model.

## 19. Deployment architecture

Single FastAPI process serving the API + Jinja2/JS UI, SQLite file on local
disk (seeded from the workbook + hand-verified `account_policy_facts` +
ingested `document_chunks` at startup or via a one-time build script), one
Docker image, one host (Render/Railway/Fly.io — whichever gives the
simplest single-container deploy). No separate DB service, no separate
frontend host. **Rejected:** Postgres/pgvector + Vercel + Railway split —
three moving services for a corpus this size is added failure surface with
no corresponding benefit; the trade-off is documented in the architecture
note as a deliberate scale-appropriate choice, not a limitation.

## 20. Explicit non-goals

- No customer-facing chatbot in this submission.
- No real authentication/SSO — mocked user switcher only.
- No vector database / embeddings.
- No generic rule DSL or rule-condition interpreter.
- No full business-hours/holiday calendar engine.
- No multi-agent swarm — one stateful LangGraph workflow.
- No ML-based anomaly detection for the proactive Overview tab — signal
  rules only (P1/P2 open + at-risk, repeated issue signature, known-issue
  match).
- No fine-tuning, no Kubernetes, no message queue/task runner.

## 21. Known limitations

- SLA is a risk **proxy** (ticket age vs. target), not verified
  first-response compliance, because the data doesn't include a
  first-response timestamp.
- Business-hours targets use a fixed approximate daily window rather than a
  real business calendar.
- `account_policy_facts` are hand-extracted from the two agreement PDFs at
  build time and committed as data, not parsed live — correct for this
  6-document corpus, but would need a real extraction+review pipeline at
  scale.
- Severity extraction (`IncidentFacts`) is LLM-based and therefore
  probabilistic on the input text, even though the P1/P2/P3 mapping itself
  is deterministic; low-quality ticket text can still produce `"unknown"`
  fields, which is handled via `NEEDS_REVIEW`, not silently guessed.

## 22. Implementation phases

0. Confirm this spec (no code).
1. SQLite schema + load `accounts`/`orders`/`tickets` from the workbook.
2. `account_policy_facts` — hand-extract from the two agreements, load, review.
3. Resolvers (`resolve_cancellation`, `resolve_service_credit`, `resolve_sla`) as plain Python + typed dataclasses.
4. Golden evaluation suite (pytest) against the resolvers directly — must pass before any agent code exists.
5. Document ingestion — chunk the 6 PDFs by section, tag metadata, load `document_chunks`.
6. `query_operations_data` / `search_policy_documents` tools with authorization enforcement + RBAC (`staff_users`).
7. `IncidentFacts` extraction + severity mapping, tested against ticket golden cases.
8. LangGraph workflow wiring the planner, tools, resolvers, guardrails, and explanation step.
9. Action layer (`create_action`/`confirm_action`) + audit log, with confirmation-gated execution.
10. Overview proactive signals (reuses steps 6-7).
11. UI (FastAPI + Jinja2 + vanilla JS): Investigate, Overview, Actions/Audit tabs, tool-call timeline.
12. Dockerize, deploy single container, smoke-test hosted URL against the full golden suite.
13. Architecture note, product note, AI-tool-usage note, demo video.
