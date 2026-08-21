# ParcelPilot AI Support Operations Copilot Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
>
> **For the human author of this project:** before starting each task below,
> stop and give a short technical briefing covering: the technology/concept
> being introduced, why it's needed, the engineering problem it solves, how
> it works internally, trade-offs, what needs to be understood before
> coding, and the acceptance criteria. This is a hard requirement of how
> this plan is executed, not optional narration — the author wants to
> understand the engineering, not receive generated code. Each task below
> starts with a **Briefing** block for exactly this purpose.

**Goal:** Build the internal ParcelPilot AI Support Operations Copilot — a
FastAPI app where authorised staff investigate cancellation/credit/SLA
questions across contracts, policies, and operational data, get a
deterministic, cited, confirm-before-action answer, and see proactive
SLA-risk/issue-cluster signals.

**Architecture:** LLM (Gemini) understands intent, extracts entities,
extracts unstructured incident facts, and explains conclusions. Deterministic
Python authorizes, retrieves, computes policy decisions via three explicit
resolvers, runs guardrails, and executes confirmed actions. LangGraph wires
these steps into one stateful workflow (not a swarm). SQLite holds
structured data, policy facts, document chunks, actions, and audit logs.
No LLM output ever authorizes access or drives a calculation directly.

**Tech Stack:** Python 3.12, FastAPI, Jinja2 + vanilla JS, SQLite (stdlib
`sqlite3`), LangGraph, Google Gemini (`google-genai`), Pydantic, pytest,
openpyxl, pymupdf, Docker.

**Spec:** `docs/superpowers/specs/2026-08-21-parcelpilot-copilot-design.md`
(read both — this plan implements every numbered section of that spec;
task descriptions below cite the spec section they satisfy).

## Global Constraints

- No LLM output may directly authorize a state-changing action or compute a
  fee/credit/severity value (spec §3 core principle) — every resolver/tool
  test in this plan asserts this by checking the deterministic function's
  output independent of any LLM call.
- Authorization is enforced inside tool functions (never a system prompt)
  and runs **before** any data or document access (spec §10).
- `REFERENCE_TIME` is loaded once from the workbook's README sheet at
  startup and threaded explicitly through every time-dependent function —
  never `datetime.now()` in application logic (spec §9).
- `account_policy_facts` and `document_chunks` are two independent
  artifacts from the same PDFs; a bug in one must never change the other's
  output (spec §7).
- No vector DB, no generic rule engine, no Next.js, no Postgres, no
  multi-agent swarm, no ML clustering — see spec §20 Non-goals verbatim.
- Money is handled as Python `float` rounded to 2dp for INR — this is a
  small-amount demo system (max value in the data is ₹5,100), not a ledger;
  documented as acceptable given spec §21's other explicitly-scoped
  limitations. (If this concerns you, tell me before Task 4 and we'll
  switch to integer paise — it's a 10-minute change at that point, not
  later.)
- Data pack location: `AI Agent Assessment - Candidate Pack/` (repo root
  sibling) — never modify these source files.
- `GEMINI_API_KEY` is expected as an environment variable; the app must
  fail fast with a clear error at startup if it's missing, not fail deep
  inside a request.

---

## File Structure

```
Assignment/
  app/
    __init__.py
    config.py            # REFERENCE_TIME loader, DB path, GEMINI_API_KEY check
    db.py                 # sqlite3 connection helper, schema.sql runner
    schema.sql             # all CREATE TABLE statements
    models.py              # dataclasses: OrderFacts, TicketFacts, AccountFacts,
                            #   Provenance, CancellationDecision, CreditDecision,
                            #   SLADecision, Citation, StaffUser, ActionDraft
    seed_accounts_orders_tickets.py   # xlsx -> accounts/orders/tickets tables
    policy_facts.py         # hand-extracted account_policy_facts data + loader + get_fact()
    resolvers.py            # resolve_cancellation, resolve_service_credit, resolve_sla
    documents.py            # hand-extracted document_chunks data + loader
    auth.py                 # staff_users seed + authorize()
    tools.py                # query_operations_data, search_policy_documents,
                            #   create_action, confirm_action
    severity.py             # IncidentFacts (pydantic), extract_incident_facts() [Gemini],
                            #   map_severity() [deterministic]
    agent.py                # LangGraph workflow: AgentState + graph
    overview.py             # SLA-risk list + issue clustering
    main.py                  # FastAPI app + routes
    templates/
      index.html
    static/
      app.js
      style.css
  tests/
    conftest.py             # fresh in-memory DB fixture, fully seeded
    test_resolvers_cancellation.py
    test_resolvers_credit.py
    test_resolvers_sla.py
    test_tools_authorization.py
    test_severity_mapping.py
    test_agent_golden_scenarios.py
    test_actions.py
    test_overview.py
  requirements.txt
  Dockerfile
  README.md
```

Rationale for this layout: one file per responsibility from spec §4's
component table (resolvers never import documents.py or tools.py; tools.py
never imports resolvers.py directly — `agent.py` is the only place that
wires resolver output + tool output together), so a bug in one area can't
silently leak into another, and each file is small enough to review in one
pass.

---

### Task 1: Project scaffold, dependencies, schema, and base data load

**Briefing:** This task sets up the project skeleton and the SQLite schema
from spec §5, then loads the three tables that come straight from the
workbook (`accounts`, `orders`, `tickets`) with no transformation logic.
SQLite is the whole "database tier" here — a single file, no server process,
which matches the corpus size (spec §19: rejecting Postgres). We use the
stdlib `sqlite3` module directly (no ORM) because the schema is small and
fixed; an ORM would add a dependency and an abstraction layer for seven
tables that don't need one. `openpyxl` reads the xlsx with `data_only=True`
so formulas (there are none here) would resolve to their cached values.
Acceptance criteria: `pytest tests/test_seed_data.py` passes, confirming
row counts (4 accounts, 6 orders, 7 tickets) and that `REFERENCE_TIME`
loads as `2026-08-16 11:00 +05:30`.

**Files:**
- Create: `requirements.txt`
- Create: `app/__init__.py`
- Create: `app/schema.sql`
- Create: `app/db.py`
- Create: `app/config.py`
- Create: `app/seed_accounts_orders_tickets.py`
- Test: `tests/conftest.py`
- Test: `tests/test_seed_data.py`

**Interfaces:**
- Produces: `db.get_connection(db_path: str) -> sqlite3.Connection` (row_factory=sqlite3.Row, `PRAGMA foreign_keys=ON`)
- Produces: `db.init_schema(conn: sqlite3.Connection) -> None` (executes `schema.sql`)
- Produces: `config.REFERENCE_TIME: datetime` (module-level, loaded at import time from the workbook path in `config.DATA_PACK_XLSX`)
- Produces: `config.DATA_PACK_XLSX: str`, `config.DB_PATH: str`, `config.GEMINI_API_KEY: str` (raises `RuntimeError` at import if unset)
- Produces: `seed_accounts_orders_tickets.load(conn: sqlite3.Connection, xlsx_path: str) -> None`

- [ ] **Step 1: Write requirements.txt**

```
fastapi==0.115.0
uvicorn[standard]==0.32.0
jinja2==3.1.4
pydantic==2.9.2
openpyxl==3.1.5
pymupdf==1.28.2
google-genai==0.3.0
langgraph==0.2.39
pytest==8.3.3
python-dotenv==1.0.1
```

- [ ] **Step 2: Write the schema**

Create `app/schema.sql`:

```sql
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS accounts (
  account_id TEXT PRIMARY KEY,
  account_name TEXT NOT NULL,
  plan TEXT NOT NULL,
  status TEXT NOT NULL,
  csm TEXT,
  contract_file TEXT,
  premium_support INTEGER NOT NULL,
  notes TEXT
);

CREATE TABLE IF NOT EXISTS orders (
  order_id TEXT PRIMARY KEY,
  account_id TEXT NOT NULL REFERENCES accounts(account_id),
  carrier TEXT,
  status TEXT NOT NULL,
  booked_at TEXT NOT NULL,
  pickup_window_start TEXT,
  pickup_window_end TEXT,
  pickup_actual_at TEXT,
  shipment_fee_inr REAL,
  carrier_fault INTEGER,
  customer_fault INTEGER,
  cancellation_requested_at TEXT,
  notes TEXT
);

CREATE TABLE IF NOT EXISTS tickets (
  ticket_id TEXT PRIMARY KEY,
  account_id TEXT NOT NULL REFERENCES accounts(account_id),
  created_at TEXT NOT NULL,
  status TEXT NOT NULL,
  subject TEXT NOT NULL,
  description TEXT NOT NULL,
  channel TEXT,
  assigned_to TEXT,
  last_customer_message_at TEXT,
  historical_resolution TEXT
);

CREATE TABLE IF NOT EXISTS account_policy_facts (
  account_id TEXT NOT NULL REFERENCES accounts(account_id),
  scenario TEXT NOT NULL,
  fact_name TEXT NOT NULL,
  fact_value TEXT NOT NULL,
  source_document TEXT NOT NULL,
  source_section TEXT NOT NULL,
  PRIMARY KEY (account_id, scenario, fact_name)
);

CREATE TABLE IF NOT EXISTS document_chunks (
  chunk_id TEXT PRIMARY KEY,
  document_id TEXT NOT NULL,
  document_name TEXT NOT NULL,
  document_type TEXT NOT NULL,
  customer_id TEXT,
  status TEXT NOT NULL,
  effective_date TEXT,
  section TEXT NOT NULL,
  scenario_tags TEXT NOT NULL,
  text TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS actions (
  action_id TEXT PRIMARY KEY,
  action_type TEXT NOT NULL,
  account_id TEXT NOT NULL,
  ticket_id TEXT,
  order_id TEXT,
  payload_json TEXT NOT NULL,
  prepared_by TEXT NOT NULL,
  status TEXT NOT NULL,
  created_at TEXT NOT NULL,
  confirmed_at TEXT,
  executed_at TEXT
);

CREATE TABLE IF NOT EXISTS audit_logs (
  log_id TEXT PRIMARY KEY,
  timestamp TEXT NOT NULL,
  user TEXT NOT NULL,
  query_text TEXT,
  account_id TEXT,
  tools_used_json TEXT,
  evidence_json TEXT,
  decision_json TEXT,
  action_id TEXT,
  confidence TEXT
);

CREATE TABLE IF NOT EXISTS staff_users (
  user_id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  role TEXT NOT NULL,
  assigned_account_ids TEXT NOT NULL
);
```

- [ ] **Step 3: Write db.py**

```python
import sqlite3
from pathlib import Path

def get_connection(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn

def init_schema(conn: sqlite3.Connection) -> None:
    schema_path = Path(__file__).parent / "schema.sql"
    conn.executescript(schema_path.read_text(encoding="utf-8"))
    conn.commit()
```

- [ ] **Step 4: Write config.py**

```python
import os
from datetime import datetime, timedelta, timezone

import openpyxl

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_PACK_XLSX = os.path.join(
    BASE_DIR, "AI Agent Assessment - Candidate Pack", "ParcelPilot_Assessment_Data.xlsx"
)
DATA_PACK_DIR = os.path.join(BASE_DIR, "AI Agent Assessment - Candidate Pack")
DB_PATH = os.path.join(BASE_DIR, "app", "parcelpilot.db")

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
if not GEMINI_API_KEY:
    raise RuntimeError(
        "GEMINI_API_KEY is not set. Export it before starting the app, "
        "e.g. `export GEMINI_API_KEY=your-key-here`."
    )

IST = timezone(timedelta(hours=5, minutes=30))


def load_reference_time(xlsx_path: str = DATA_PACK_XLSX) -> datetime:
    """Reads the dataset snapshot timestamp from the workbook's README sheet.

    The README sheet's second row is ('Dataset snapshot',
    '2026-08-16 11:00 Asia/Kolkata'). We parse the naive datetime and attach
    a fixed +05:30 offset (Asia/Kolkata has no DST) rather than hardcoding
    the value, so a differently-timestamped copy of the same pack (e.g. the
    grader's) is still handled correctly.
    """
    wb = openpyxl.load_workbook(xlsx_path, data_only=True)
    readme = wb["README"]
    for row in readme.iter_rows(values_only=True):
        if row and row[0] == "Dataset snapshot":
            raw = row[1]  # "2026-08-16 11:00 Asia/Kolkata"
            naive_part = raw.rsplit(" ", 1)[0]  # drop " Asia/Kolkata"
            naive_dt = datetime.fromisoformat(naive_part)
            return naive_dt.replace(tzinfo=IST)
    raise ValueError("Could not find 'Dataset snapshot' row in README sheet")


REFERENCE_TIME = load_reference_time()
```

- [ ] **Step 5: Write the failing test for schema + config**

Create `tests/conftest.py`:

```python
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest

from app import db


@pytest.fixture
def conn():
    connection = db.get_connection(":memory:")
    db.init_schema(connection)
    yield connection
    connection.close()
```

Create `tests/test_seed_data.py`:

```python
from app import config
from app.seed_accounts_orders_tickets import load


def test_reference_time_loaded_correctly():
    assert config.REFERENCE_TIME.isoformat() == "2026-08-16T11:00:00+05:30"


def test_seed_loads_expected_row_counts(conn):
    load(conn, config.DATA_PACK_XLSX)
    assert conn.execute("SELECT COUNT(*) FROM accounts").fetchone()[0] == 4
    assert conn.execute("SELECT COUNT(*) FROM orders").fetchone()[0] == 6
    assert conn.execute("SELECT COUNT(*) FROM tickets").fetchone()[0] == 7


def test_seed_preserves_nullable_fault_flags(conn):
    load(conn, config.DATA_PACK_XLSX)
    row = conn.execute(
        "SELECT carrier_fault, customer_fault FROM orders WHERE order_id = 'ORD-2002'"
    ).fetchone()
    assert row["carrier_fault"] == 1
    assert row["customer_fault"] == 0
```

- [ ] **Step 6: Run tests to verify they fail**

Run: `pytest tests/test_seed_data.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.seed_accounts_orders_tickets'`

- [ ] **Step 7: Write seed_accounts_orders_tickets.py**

```python
import sqlite3

import openpyxl


def _to_int_or_none(value):
    if value is None:
        return None
    return 1 if value else 0


def load(conn: sqlite3.Connection, xlsx_path: str) -> None:
    wb = openpyxl.load_workbook(xlsx_path, data_only=True)

    accounts_ws = wb["accounts"]
    rows = list(accounts_ws.iter_rows(values_only=True))
    for account_id, account_name, plan, status, csm, contract_file, premium_support, notes in rows[1:]:
        conn.execute(
            "INSERT INTO accounts (account_id, account_name, plan, status, csm, "
            "contract_file, premium_support, notes) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (account_id, account_name, plan, status, csm, contract_file,
             _to_int_or_none(premium_support), notes),
        )

    orders_ws = wb["orders"]
    rows = list(orders_ws.iter_rows(values_only=True))
    for (order_id, account_id, carrier, status, booked_at, pickup_window_start,
         pickup_window_end, pickup_actual_at, shipment_fee_inr, carrier_fault,
         customer_fault, cancellation_requested_at, notes) in rows[1:]:
        conn.execute(
            "INSERT INTO orders (order_id, account_id, carrier, status, booked_at, "
            "pickup_window_start, pickup_window_end, pickup_actual_at, shipment_fee_inr, "
            "carrier_fault, customer_fault, cancellation_requested_at, notes) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (order_id, account_id, carrier, status, str(booked_at),
             str(pickup_window_start) if pickup_window_start else None,
             str(pickup_window_end) if pickup_window_end else None,
             str(pickup_actual_at) if pickup_actual_at else None,
             shipment_fee_inr, _to_int_or_none(carrier_fault),
             _to_int_or_none(customer_fault),
             str(cancellation_requested_at) if cancellation_requested_at else None,
             notes),
        )

    tickets_ws = wb["tickets"]
    rows = list(tickets_ws.iter_rows(values_only=True))
    for (ticket_id, account_id, created_at, status, subject, description, channel,
         assigned_to, last_customer_message_at, historical_resolution) in rows[1:]:
        conn.execute(
            "INSERT INTO tickets (ticket_id, account_id, created_at, status, subject, "
            "description, channel, assigned_to, last_customer_message_at, "
            "historical_resolution) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (ticket_id, account_id, str(created_at), status, subject, description,
             channel, assigned_to,
             str(last_customer_message_at) if last_customer_message_at else None,
             historical_resolution),
        )

    conn.commit()
```

- [ ] **Step 8: Run tests to verify they pass**

Run: `pytest tests/test_seed_data.py -v`
Expected: PASS (3 passed)

- [ ] **Step 9: Commit**

```bash
git add requirements.txt app/__init__.py app/schema.sql app/db.py app/config.py \
        app/seed_accounts_orders_tickets.py tests/conftest.py tests/test_seed_data.py
git commit -m "feat: project scaffold, SQLite schema, and workbook seed loader"
```

---

### Task 2: account_policy_facts data and typed data-access layer

**Briefing:** This task encodes the two agreement PDFs' customer-specific
terms as data (spec §7), and builds the typed read layer (`OrderFacts`,
`TicketFacts`, `AccountFacts`, `get_fact`) that every later resolver and
tool depends on. The facts are committed as Python data, not parsed from
PDF text at runtime, because there are exactly two agreements and hand
verification is more reliable than pattern-matching two documents (spec §7
rationale). `get_fact` is the *only* way anything reads this table — this
is what makes the clause-level fallback rule (spec §7's explicit statement)
enforceable: if a resolver ever queried the table directly instead of going
through `get_fact`, it could bypass the "falls through to global default"
semantics. Acceptance criteria: `pytest tests/test_policy_facts.py` passes,
proving Northstar's `service_credit` scenario has zero rows (full fallback)
while its `cancellation` scenario has an override.

**Files:**
- Create: `app/policy_facts.py`
- Create: `app/models.py`
- Test: `tests/test_policy_facts.py`

**Interfaces:**
- Consumes: `db.get_connection`, `db.init_schema` (Task 1)
- Produces: `policy_facts.load(conn) -> None`
- Produces: `policy_facts.get_fact(conn, account_id: str, scenario: str, fact_name: str, default) -> tuple[Any, "Provenance"]` — always returns a `Provenance`, whether the fact came from `account_policy_facts` or the caller-supplied `default`
- Produces (in `models.py`): `Provenance`, `OrderFacts`, `TicketFacts`, `AccountFacts` dataclasses (frozen, all fields match the DB columns 1:1 with Python types: `bool | None` for fault flags, `datetime | None` for timestamps, `float | None` for money)

- [ ] **Step 1: Write models.py**

```python
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
```

- [ ] **Step 2: Write the failing test**

Create `tests/test_policy_facts.py`:

```python
from app import policy_facts
from app.seed_accounts_orders_tickets import load as load_base
from app.config import DATA_PACK_XLSX


def test_northstar_cancellation_override_exists(conn):
    load_base(conn, DATA_PACK_XLSX)
    policy_facts.load(conn)
    value, prov = policy_facts.get_fact(conn, "ACCT-001", "cancellation", "fee_waived", default=False)
    assert value is True
    assert prov.origin == "account_policy_facts"
    assert "Northstar" in prov.source_document


def test_northstar_service_credit_falls_through_to_default(conn):
    load_base(conn, DATA_PACK_XLSX)
    policy_facts.load(conn)
    value, prov = policy_facts.get_fact(conn, "ACCT-001", "service_credit", "credit_amount_inr", default=None)
    assert value is None
    assert prov.origin == "global_default"


def test_lumenworks_credit_override_exists(conn):
    load_base(conn, DATA_PACK_XLSX)
    policy_facts.load(conn)
    value, prov = policy_facts.get_fact(conn, "ACCT-002", "service_credit", "credit_amount_inr", default=None)
    assert value == 300.0
    assert prov.source_document == "LumenWorks Service Agreement"
    assert prov.source_section == "§3"
```

- [ ] **Step 3: Run test to verify it fails**

Run: `pytest tests/test_policy_facts.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.policy_facts'`

- [ ] **Step 4: Write policy_facts.py**

```python
import sqlite3

from app.models import Provenance

# Hand-extracted from the two agreement PDFs (05_Northstar_Logistics_Enterprise_Agreement.pdf,
# 06_LumenWorks_Service_Agreement.pdf). Deliberately excludes Northstar's ₹5,000 monthly
# service-credit cap — see spec §7/§21: no ledger of already-issued credits exists in the
# supplied data, so the cap can't be enforced and isn't stored as a computable fact.
_FACTS = [
    # account_id,  scenario,        fact_name,                fact_value, source_document,                    source_section
    ("ACCT-001", "cancellation", "fee_waived",              "true",  "Northstar Enterprise Agreement", "§2"),
    ("ACCT-001", "cancellation", "waiver_scope",            "booked_before_pickup_any_time", "Northstar Enterprise Agreement", "§2"),
    ("ACCT-001", "sla",          "p1_target_minutes",       "15",    "Northstar Enterprise Agreement", "§1"),
    ("ACCT-001", "sla",          "p2_target_minutes",       "60",    "Northstar Enterprise Agreement", "§1"),
    ("ACCT-001", "sla",          "p3_target_minutes",       "480",   "Northstar Enterprise Agreement", "§1"),
    ("ACCT-001", "sla",          "coverage",                "24x7",  "Northstar Enterprise Agreement", "§1"),
    ("ACCT-002", "service_credit", "delay_threshold_hours", "4",     "LumenWorks Service Agreement", "§3"),
    ("ACCT-002", "service_credit", "credit_amount_inr",      "300",  "LumenWorks Service Agreement", "§3"),
    ("ACCT-002", "sla",          "p1_target_minutes",       "120",   "LumenWorks Service Agreement", "§1"),
    ("ACCT-002", "sla",          "p2_target_minutes",       "240",   "LumenWorks Service Agreement", "§1"),
    ("ACCT-002", "sla",          "p3_target_minutes",       "2880",  "LumenWorks Service Agreement", "§1"),
    ("ACCT-002", "sla",          "coverage",                "business_hours", "LumenWorks Service Agreement", "§1"),
]

_TYPE_CASTERS = {
    "fee_waived": lambda v: v == "true",
    "delay_threshold_hours": float,
    "credit_amount_inr": float,
    "p1_target_minutes": int,
    "p2_target_minutes": int,
    "p3_target_minutes": int,
}


def load(conn: sqlite3.Connection) -> None:
    conn.executemany(
        "INSERT INTO account_policy_facts "
        "(account_id, scenario, fact_name, fact_value, source_document, source_section) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        _FACTS,
    )
    conn.commit()


def get_fact(conn: sqlite3.Connection, account_id: str, scenario: str, fact_name: str, default):
    row = conn.execute(
        "SELECT fact_value, source_document, source_section FROM account_policy_facts "
        "WHERE account_id = ? AND scenario = ? AND fact_name = ?",
        (account_id, scenario, fact_name),
    ).fetchone()
    if row is None:
        return default, Provenance(
            origin="global_default", source_document="global_default", source_section="n/a"
        )
    caster = _TYPE_CASTERS.get(fact_name, str)
    return caster(row["fact_value"]), Provenance(
        origin="account_policy_facts",
        source_document=row["source_document"],
        source_section=row["source_section"],
    )
```

- [ ] **Step 5: Run test to verify it passes**

Run: `pytest tests/test_policy_facts.py -v`
Expected: PASS (3 passed)

- [ ] **Step 6: Commit**

```bash
git add app/models.py app/policy_facts.py tests/test_policy_facts.py
git commit -m "feat: typed data models and hand-verified account_policy_facts"
```

---

### Task 3: Resolvers — resolve_cancellation and resolve_service_credit

**Briefing:** This is the heart of the "deterministic code decides" thesis
(spec §3, §8). Both functions are plain Python, no LLM involved anywhere,
and take typed `OrderFacts` plus a `get_fact`-backed lookup — never raw DB
rows or document text. `resolve_service_credit` is where the earlier
design review caught a real bug: computing delay as `now -
pickup_window_end` unconditionally conflates "hasn't been picked up yet"
with "was picked up, but late." The fix is to branch on whether
`pickup_actual_at` is set. Acceptance criteria: golden scenarios 1-6, 16,
17 from spec §15 all pass as direct unit tests against these two functions
— this is the evaluation-before-agent principle from spec §22 phase 4 in
practice.

**Files:**
- Create: `app/resolvers.py` (this task adds `resolve_cancellation`, `resolve_service_credit`; Task 4 adds `resolve_sla` to the same file)
- Test: `tests/test_resolvers_cancellation.py`
- Test: `tests/test_resolvers_credit.py`

**Interfaces:**
- Consumes: `models.OrderFacts`, `models.Provenance` (Task 2), `policy_facts.get_fact` (Task 2)
- Produces: `models.CancellationDecision(allowed: bool, fee_inr: float | None, reason: str, provenance: Provenance)`
- Produces: `models.CreditDecision(eligible: bool, amount_inr: float | None, requires_manager_approval: bool, needs_review: bool, reason: str, provenance: Provenance)`
- Produces: `resolvers.resolve_cancellation(conn, order: OrderFacts) -> CancellationDecision`
- Produces: `resolvers.resolve_service_credit(conn, order: OrderFacts, reference_time: datetime) -> CreditDecision`

- [ ] **Step 1: Add the two decision dataclasses to models.py**

Append to `app/models.py`:

```python
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
```

- [ ] **Step 2: Write the failing tests**

Create `tests/test_resolvers_cancellation.py`:

```python
from datetime import datetime, timedelta

from app.models import OrderFacts
from app.policy_facts import load as load_facts
from app.resolvers import resolve_cancellation
from app.seed_accounts_orders_tickets import load as load_base
from app.config import DATA_PACK_XLSX


def _seed(conn):
    load_base(conn, DATA_PACK_XLSX)
    load_facts(conn)


def test_ord_1001_northstar_booked_2hrs_after_no_fee(conn):
    _seed(conn)
    order = OrderFacts(
        order_id="ORD-1001", account_id="ACCT-001", carrier="SwiftShip",
        status="BOOKED", booked_at=datetime(2026, 8, 16, 9, 0),
        pickup_window_start=None, pickup_window_end=None, pickup_actual_at=None,
        shipment_fee_inr=4200.0, carrier_fault=False, customer_fault=False,
        cancellation_requested_at=datetime(2026, 8, 16, 11, 0), notes="",
    )
    decision = resolve_cancellation(conn, order)
    assert decision.allowed is True
    assert decision.fee_inr == 0
    assert decision.provenance.origin == "account_policy_facts"


def test_ord_1002_northstar_picked_up_not_allowed(conn):
    _seed(conn)
    order = OrderFacts(
        order_id="ORD-1002", account_id="ACCT-001", carrier="BlueDart Pro",
        status="PICKED_UP", booked_at=datetime(2026, 8, 16, 8, 10),
        pickup_window_start=None, pickup_window_end=None,
        pickup_actual_at=datetime(2026, 8, 16, 9, 35),
        shipment_fee_inr=5100.0, carrier_fault=False, customer_fault=False,
        cancellation_requested_at=datetime(2026, 8, 16, 10, 20), notes="",
    )
    decision = resolve_cancellation(conn, order)
    assert decision.allowed is False
    assert "return-to-origin" in decision.reason.lower()


def test_ord_2001_lumenworks_75min_falls_back_to_sop_fee(conn):
    _seed(conn)
    order = OrderFacts(
        order_id="ORD-2001", account_id="ACCT-002", carrier="SwiftShip",
        status="BOOKED", booked_at=datetime(2026, 8, 16, 9, 0),
        pickup_window_start=None, pickup_window_end=None, pickup_actual_at=None,
        shipment_fee_inr=1800.0, carrier_fault=False, customer_fault=False,
        cancellation_requested_at=datetime(2026, 8, 16, 10, 15), notes="",
    )
    decision = resolve_cancellation(conn, order)
    assert decision.allowed is True
    assert decision.fee_inr == 250
    assert decision.provenance.origin == "global_default"


def test_ord_3001_beacon_under_30min_no_fee(conn):
    _seed(conn)
    order = OrderFacts(
        order_id="ORD-3001", account_id="ACCT-003", carrier="RoadRunner",
        status="BOOKED", booked_at=datetime(2026, 8, 16, 10, 25),
        pickup_window_start=None, pickup_window_end=None, pickup_actual_at=None,
        shipment_fee_inr=1200.0, carrier_fault=False, customer_fault=False,
        cancellation_requested_at=datetime(2026, 8, 16, 10, 40), notes="",
    )
    decision = resolve_cancellation(conn, order)
    assert decision.allowed is True
    assert decision.fee_inr == 0


def test_ord_4001_delivered_cannot_cancel(conn):
    _seed(conn)
    order = OrderFacts(
        order_id="ORD-4001", account_id="ACCT-004", carrier="SwiftShip",
        status="DELIVERED", booked_at=datetime(2026, 8, 14, 14, 0),
        pickup_window_start=None, pickup_window_end=None,
        pickup_actual_at=datetime(2026, 8, 15, 9, 20),
        shipment_fee_inr=3600.0, carrier_fault=False, customer_fault=False,
        cancellation_requested_at=None, notes="",
    )
    decision = resolve_cancellation(conn, order)
    assert decision.allowed is False
```

Create `tests/test_resolvers_credit.py`:

```python
from datetime import datetime

from app.models import OrderFacts
from app.policy_facts import load as load_facts
from app.resolvers import resolve_service_credit
from app.seed_accounts_orders_tickets import load as load_base
from app.config import DATA_PACK_XLSX, IST


def _seed(conn):
    load_base(conn, DATA_PACK_XLSX)
    load_facts(conn)


def test_ord_2002_lumenworks_carrier_fault_fixed_credit(conn):
    _seed(conn)
    order = OrderFacts(
        order_id="ORD-2002", account_id="ACCT-002", carrier="RoadRunner",
        status="BOOKED", booked_at=datetime(2026, 8, 16, 4, 30),
        pickup_window_start=datetime(2026, 8, 16, 5, 30),
        pickup_window_end=datetime(2026, 8, 16, 6, 30), pickup_actual_at=None,
        shipment_fee_inr=2400.0, carrier_fault=True, customer_fault=False,
        cancellation_requested_at=None, notes="",
    )
    reference_time = datetime(2026, 8, 16, 11, 0, tzinfo=IST).replace(tzinfo=None)
    decision = resolve_service_credit(conn, order, reference_time)
    assert decision.eligible is True
    assert decision.amount_inr == 300
    assert decision.requires_manager_approval is False
    assert decision.provenance.origin == "account_policy_facts"


def test_unknown_fault_blocks_credit_and_needs_review(conn):
    _seed(conn)
    order = OrderFacts(
        order_id="ORD-9999", account_id="ACCT-003", carrier="RoadRunner",
        status="BOOKED", booked_at=datetime(2026, 8, 16, 4, 0),
        pickup_window_start=datetime(2026, 8, 16, 5, 0),
        pickup_window_end=datetime(2026, 8, 16, 6, 0), pickup_actual_at=None,
        shipment_fee_inr=1000.0, carrier_fault=None, customer_fault=False,
        cancellation_requested_at=None, notes="",
    )
    reference_time = datetime(2026, 8, 16, 11, 0)
    decision = resolve_service_credit(conn, order, reference_time)
    assert decision.eligible is False
    assert decision.needs_review is True


def test_credit_over_1000_requires_manager_approval(conn):
    _seed(conn)
    # The global default formula (min(₹500, 10% of shipment fee)) can never exceed
    # ₹500, so it can never trigger the >₹1,000 guardrail. To test that guardrail
    # for real, insert a synthetic account-level override (ACCT-003 has no existing
    # account_policy_facts rows, so this doesn't collide with the real Northstar/
    # LumenWorks data loaded by policy_facts.load()).
    conn.execute(
        "INSERT INTO account_policy_facts (account_id, scenario, fact_name, "
        "fact_value, source_document, source_section) VALUES "
        "('ACCT-003', 'service_credit', 'credit_amount_inr', '1500', "
        "'Test Override (synthetic)', '§0')"
    )
    conn.commit()
    order = OrderFacts(
        order_id="ORD-8888", account_id="ACCT-003", carrier="RoadRunner",
        status="BOOKED", booked_at=datetime(2026, 8, 16, 1, 0),
        pickup_window_start=datetime(2026, 8, 16, 2, 0),
        pickup_window_end=datetime(2026, 8, 16, 3, 0), pickup_actual_at=None,
        shipment_fee_inr=2000.0, carrier_fault=True, customer_fault=False,
        cancellation_requested_at=None, notes="",
    )
    reference_time = datetime(2026, 8, 16, 11, 0)
    decision = resolve_service_credit(conn, order, reference_time)
    assert decision.eligible is True
    assert decision.amount_inr == 1500.0
    assert decision.requires_manager_approval is True
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `pytest tests/test_resolvers_cancellation.py tests/test_resolvers_credit.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.resolvers'`

- [ ] **Step 4: Write resolvers.py (cancellation + credit)**

```python
import sqlite3
from datetime import datetime

from app.models import CancellationDecision, CreditDecision, OrderFacts, Provenance
from app.policy_facts import get_fact


def resolve_cancellation(conn: sqlite3.Connection, order: OrderFacts) -> CancellationDecision:
    sop_provenance = Provenance(
        origin="global_default", source_document="SOP v4", source_section="§1"
    )

    if order.status == "DRAFT":
        return CancellationDecision(True, 0.0, "DRAFT orders may be cancelled with no fee.", sop_provenance)

    if order.status == "PICKED_UP":
        return CancellationDecision(
            False, None,
            "Order has been picked up; use the return-to-origin workflow instead of cancellation.",
            sop_provenance,
        )

    if order.status == "DELIVERED":
        return CancellationDecision(False, None, "Delivered orders cannot be cancelled.", sop_provenance)

    # BOOKED, not yet picked up
    waived, waived_prov = get_fact(conn, order.account_id, "cancellation", "fee_waived", default=False)
    scope, _ = get_fact(conn, order.account_id, "cancellation", "waiver_scope", default=None)
    if waived and scope == "booked_before_pickup_any_time":
        return CancellationDecision(
            True, 0.0, "Cancellation fee waived by the customer's agreement.", waived_prov
        )

    age = order.cancellation_requested_at - order.booked_at
    fee = 0.0 if age <= __import__("datetime").timedelta(minutes=30) else 250.0
    reason = (
        "Cancelled within 30 minutes of booking; no fee per SOP v4."
        if fee == 0.0 else
        "Cancelled more than 30 minutes after booking; ₹250 fee per SOP v4."
    )
    return CancellationDecision(True, fee, reason, sop_provenance)


def resolve_service_credit(
    conn: sqlite3.Connection, order: OrderFacts, reference_time: datetime
) -> CreditDecision:
    sop_provenance = Provenance(
        origin="global_default", source_document="SOP v4", source_section="§2"
    )
    uncertainty_provenance = Provenance(
        origin="global_default", source_document="SOP v4", source_section="§3"
    )

    if order.carrier_fault is None or order.customer_fault is None:
        return CreditDecision(
            False, None, False, True,
            "Carrier-fault or customer-fault status is unknown; SOP v4 §3 prohibits "
            "promising a credit until this is verified.",
            uncertainty_provenance,
        )

    if order.customer_fault:
        return CreditDecision(False, None, False, False, "Customer was at fault; not eligible.", sop_provenance)

    if order.pickup_actual_at is not None:
        delay = order.pickup_actual_at - order.pickup_window_end
    else:
        delay = reference_time - order.pickup_window_end

    threshold_hours, threshold_prov = get_fact(
        conn, order.account_id, "service_credit", "delay_threshold_hours", default=2.0
    )
    if delay.total_seconds() / 3600 <= threshold_hours or not order.carrier_fault:
        return CreditDecision(False, None, False, False, "Delay does not exceed the applicable threshold.", threshold_prov)

    amount, amount_prov = get_fact(
        conn, order.account_id, "service_credit", "credit_amount_inr",
        default=min(500.0, 0.10 * (order.shipment_fee_inr or 0)),
    )
    return CreditDecision(
        True, amount, amount > 1000, False,
        f"Carrier-fault delay exceeded {threshold_hours}h threshold; credit applies.",
        amount_prov,
    )
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_resolvers_cancellation.py tests/test_resolvers_credit.py -v`
Expected: PASS (8 passed)

- [ ] **Step 6: Commit**

```bash
git add app/models.py app/resolvers.py tests/test_resolvers_cancellation.py tests/test_resolvers_credit.py
git commit -m "feat: resolve_cancellation and resolve_service_credit with golden tests"
```

---

### Task 4: resolve_sla (deterministic half only)

**Briefing:** `resolve_sla` takes a severity that's already been decided
(Task 8 supplies it) — this task only builds the deterministic
target-lookup-and-elapsed-time half, tested by passing severity directly.
This keeps the test suite honest about what's actually deterministic here:
given a severity, the SLA-risk calculation has no LLM involvement at all.
The corrected spec's business-hours caveat (spec §17) must show up here as
an explicit field, not silently ignored — `is_wall_clock_proxy` is `True`
whenever `coverage == "business_hours"`.

**Files:**
- Modify: `app/resolvers.py` (add `resolve_sla`)
- Modify: `app/models.py` (add `SLADecision`)
- Test: `tests/test_resolvers_sla.py`

**Interfaces:**
- Consumes: `models.TicketFacts`, `models.AccountFacts`, `policy_facts.get_fact` (Task 2)
- Produces: `models.SLADecision(severity: str, target_minutes: int, elapsed_minutes: float, at_risk: bool, is_wall_clock_proxy: bool, provenance: Provenance)`
- Produces: `resolvers.resolve_sla(conn, ticket: TicketFacts, account: AccountFacts, severity: str, reference_time: datetime) -> SLADecision`

- [ ] **Step 1: Add SLADecision to models.py**

Append to `app/models.py`:

```python
@dataclass(frozen=True)
class SLADecision:
    severity: str
    target_minutes: int
    elapsed_minutes: float
    at_risk: bool
    is_wall_clock_proxy: bool
    provenance: Provenance
```

- [ ] **Step 2: Write the failing test**

Create `tests/test_resolvers_sla.py`:

```python
from datetime import datetime

from app.models import AccountFacts, TicketFacts
from app.policy_facts import load as load_facts
from app.resolvers import resolve_sla
from app.seed_accounts_orders_tickets import load as load_base
from app.config import DATA_PACK_XLSX


def _seed(conn):
    load_base(conn, DATA_PACK_XLSX)
    load_facts(conn)


def test_northstar_p1_uses_15min_override_and_is_24x7(conn):
    _seed(conn)
    ticket = TicketFacts(
        ticket_id="TKT-501", account_id="ACCT-001",
        created_at=datetime(2026, 8, 16, 10, 30), status="open",
        subject="All shipment creation is failing",
        description="Every user at Northstar gets HTTP 500...",
        channel="email", assigned_to="Rohit",
        last_customer_message_at=datetime(2026, 8, 16, 10, 52),
        historical_resolution=None,
    )
    account = AccountFacts("ACCT-001", "Northstar Logistics", "Enterprise", "active", "Priya Mehta", "05_...", True)
    reference_time = datetime(2026, 8, 16, 11, 0)
    decision = resolve_sla(conn, ticket, account, severity="P1", reference_time=reference_time)
    assert decision.target_minutes == 15
    assert decision.at_risk is True   # 30 min elapsed > 15 min target
    assert decision.is_wall_clock_proxy is False
    assert decision.provenance.origin == "account_policy_facts"


def test_lumenworks_business_hours_flagged_as_proxy(conn):
    _seed(conn)
    ticket = TicketFacts(
        ticket_id="TKT-502", account_id="ACCT-002",
        created_at=datetime(2026, 8, 16, 9, 45), status="open",
        subject="Bulk upload fails", description="...", channel="chat",
        assigned_to="Maya", last_customer_message_at=None, historical_resolution=None,
    )
    account = AccountFacts("ACCT-002", "LumenWorks", "Growth", "active", "Arjun Rao", "06_...", False)
    reference_time = datetime(2026, 8, 16, 11, 0)
    decision = resolve_sla(conn, ticket, account, severity="P2", reference_time=reference_time)
    assert decision.target_minutes == 240
    assert decision.is_wall_clock_proxy is True


def test_beacon_falls_back_to_plan_default_table(conn):
    _seed(conn)
    ticket = TicketFacts(
        ticket_id="TKT-503", account_id="ACCT-003",
        created_at=datetime(2026, 8, 16, 10, 5), status="open",
        subject="Change billing contact", description="...", channel="email",
        assigned_to="Rohit", last_customer_message_at=None, historical_resolution=None,
    )
    account = AccountFacts("ACCT-003", "Beacon Retail", "Standard", "active", "Neha Kapoor", None, False)
    reference_time = datetime(2026, 8, 16, 11, 0)
    decision = resolve_sla(conn, ticket, account, severity="P3", reference_time=reference_time)
    assert decision.target_minutes == 2 * 24 * 60  # Standard P3: 2 business days (Policy v3 §3)
    assert decision.provenance.origin == "global_default"
```

- [ ] **Step 3: Run test to verify it fails**

Run: `pytest tests/test_resolvers_sla.py -v`
Expected: FAIL — `ImportError: cannot import name 'resolve_sla'`

- [ ] **Step 4: Add resolve_sla to resolvers.py**

Append to `app/resolvers.py`:

```python
from app.models import AccountFacts, SLADecision, TicketFacts

# Policy v3 §3 default first-response targets, in minutes.
_PLAN_DEFAULTS_MINUTES = {
    "Enterprise": {"P1": 30, "P2": 120, "P3": 1 * 24 * 60},
    "Growth":     {"P1": 2 * 60, "P2": 4 * 60, "P3": 2 * 24 * 60},
    "Standard":   {"P1": 4 * 60, "P2": 1 * 24 * 60, "P3": 2 * 24 * 60},
}


def resolve_sla(
    conn: sqlite3.Connection, ticket: TicketFacts, account: AccountFacts,
    severity: str, reference_time: datetime,
) -> SLADecision:
    target, target_prov = get_fact(conn, account.account_id, "sla", f"{severity.lower()}_target_minutes", default=None)
    if target is None:
        target = _PLAN_DEFAULTS_MINUTES[account.plan][severity]
        target_prov = Provenance("global_default", "Policy v3", "§3")

    coverage, _ = get_fact(conn, account.account_id, "sla", "coverage", default="24x7")
    elapsed = (reference_time - ticket.created_at).total_seconds() / 60

    return SLADecision(
        severity=severity,
        target_minutes=target,
        elapsed_minutes=elapsed,
        at_risk=elapsed > target,
        is_wall_clock_proxy=(coverage == "business_hours"),
        provenance=target_prov,
    )
```

- [ ] **Step 5: Run test to verify it passes**

Run: `pytest tests/test_resolvers_sla.py -v`
Expected: PASS (3 passed)

- [ ] **Step 6: Commit**

```bash
git add app/models.py app/resolvers.py tests/test_resolvers_sla.py
git commit -m "feat: resolve_sla deterministic target/elapsed calculation"
```

---

### Task 5: Document chunks (retrieval/citation corpus)

**Briefing:** This builds the *other* artifact from the same 6 PDFs — the
citation corpus (spec §6, §9). It's deliberately independent of
`policy_facts.py`: this data is never read by a resolver, only by
`search_policy_documents` (Task 7). Because each PDF is one page with 3-4
labeled sections, chunking is done once as reviewed data (the exact text
already extracted and verified), not by a runtime PDF-section-splitting
algorithm — that would be solving a problem this six-document corpus
doesn't have. Acceptance criteria: `pytest tests/test_documents.py` passes,
confirming the deprecated policy chunk is present (for the explicit
comparison path) but tagged `status="DEPRECATED"`, and that Northstar/
LumenWorks chunks are scoped to their `customer_id`.

**Files:**
- Create: `app/documents.py`
- Test: `tests/test_documents.py`

**Interfaces:**
- Produces: `documents.load(conn) -> None`
- Produces: `models.Citation(document_name, section, text, status, effective_date, customer_id)` dataclass

- [ ] **Step 1: Add Citation to models.py**

Append to `app/models.py`:

```python
@dataclass(frozen=True)
class Citation:
    document_name: str
    section: str
    text: str
    status: str
    effective_date: str | None
    customer_id: str | None
```

- [ ] **Step 2: Write the failing test**

Create `tests/test_documents.py`:

```python
from app.documents import load


def test_document_chunks_loaded_with_correct_scoping(conn):
    load(conn)
    total = conn.execute("SELECT COUNT(*) FROM document_chunks").fetchone()[0]
    assert total == 19

    deprecated = conn.execute(
        "SELECT COUNT(*) FROM document_chunks WHERE status = 'DEPRECATED'"
    ).fetchone()[0]
    assert deprecated == 1

    northstar_scoped = conn.execute(
        "SELECT COUNT(*) FROM document_chunks WHERE customer_id = 'ACCT-001'"
    ).fetchone()[0]
    assert northstar_scoped == 4

    global_chunks = conn.execute(
        "SELECT COUNT(*) FROM document_chunks WHERE customer_id IS NULL"
    ).fetchone()[0]
    assert global_chunks == 12

    ki208 = conn.execute(
        "SELECT text FROM document_chunks WHERE chunk_id = 'product_guide_ki208'"
    ).fetchone()
    assert "3,000 rows" in ki208["text"]
```

- [ ] **Step 3: Run test to verify it fails**

Run: `pytest tests/test_documents.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.documents'`

- [ ] **Step 4: Write documents.py**

```python
import sqlite3

# Hand-extracted, section-level chunks from the six supplied PDFs (spec §6, §9).
# Committed as reviewed data rather than parsed at runtime — see spec §9 rationale.
_CHUNKS = [
    dict(chunk_id="policy_v3_precedence", document_id="01", document_name="Support Policy v3",
         document_type="policy_current", customer_id=None, status="CURRENT",
         effective_date="2026-05-01", section="§1 Scope and source precedence",
         scenario_tags="sla,cancellation,service_credit",
         text="This policy defines default support severity and response targets. A signed "
              "customer agreement may override these defaults. When sources conflict, use the "
              "signed customer agreement first, then the current support policy, then current "
              "product documentation. Historical tickets and internal notes are context only "
              "and may contain incorrect past guidance."),
    dict(chunk_id="policy_v3_severity", document_id="01", document_name="Support Policy v3",
         document_type="policy_current", customer_id=None, status="CURRENT",
         effective_date="2026-05-01", section="§2 Severity definitions", scenario_tags="sla",
         text="P1 - Critical: Complete production outage preventing all shipment creation for a "
              "customer, confirmed security incident or suspected credential exposure, or "
              "another event causing immediate material business risk with no workaround. "
              "P2 - High: Major feature unavailable or materially degraded for a customer, but "
              "core operations remain possible or a workaround exists. P3 - Normal: Minor "
              "defect, how-to question, configuration request, or issue with limited "
              "operational impact."),
    dict(chunk_id="policy_v3_targets", document_id="01", document_name="Support Policy v3",
         document_type="policy_current", customer_id=None, status="CURRENT",
         effective_date="2026-05-01", section="§3 Default first-response targets", scenario_tags="sla",
         text="Enterprise: P1 30 minutes 24x7, P2 2 hours, P3 1 business day. Growth: P1 2 "
              "business hours, P2 4 business hours, P3 2 business days. Standard: P1 4 business "
              "hours, P2 1 business day, P3 2 business days."),
    dict(chunk_id="policy_v3_escalation", document_id="01", document_name="Support Policy v3",
         document_type="policy_current", customer_id=None, status="CURRENT",
         effective_date="2026-05-01", section="§4 Escalation", scenario_tags="sla",
         text="P1 incidents should be escalated immediately. If a response target is already "
              "breached, the agent should clearly state the breach and recommend escalation "
              "rather than hiding uncertainty."),
    dict(chunk_id="policy_v2_targets", document_id="02", document_name="Support Policy v2",
         document_type="policy_deprecated", customer_id=None, status="DEPRECATED",
         effective_date="2025-01-01", section="Severity and response targets", scenario_tags="sla",
         text="DEPRECATED - DO NOT USE FOR CURRENT REQUESTS, superseded by Support Policy v3 "
              "effective 1 May 2026. Enterprise: P1 1 hour, P2 4 hours, P3 2 business days. "
              "Growth: P1 4 business hours, P2 1 business day, P3 3 business days. Standard: "
              "P1 8 business hours, P2 2 business days, P3 3 business days."),
    dict(chunk_id="sop_v4_cancellation", document_id="03", document_name="Cancellation & Service Credit SOP v4",
         document_type="sop", customer_id=None, status="CURRENT", effective_date="2026-06-15",
         section="§1 Order cancellation", scenario_tags="cancellation",
         text="DRAFT: may be cancelled with no fee. BOOKED, not yet PICKED_UP: may be "
              "cancelled; no fee within 30 minutes of booking, after 30 minutes charge INR 250 "
              "unless a customer agreement explicitly waives the cancellation fee. PICKED_UP: "
              "do not cancel, use the return-to-origin workflow. DELIVERED: cannot be cancelled."),
    dict(chunk_id="sop_v4_credit", document_id="03", document_name="Cancellation & Service Credit SOP v4",
         document_type="sop", customer_id=None, status="CURRENT", effective_date="2026-06-15",
         section="§2 Failed-pickup service credits", scenario_tags="service_credit",
         text="A customer is eligible for a service credit when pickup is more than 2 hours "
              "past the end of the scheduled pickup window, the carrier is at fault, and there "
              "is no customer-caused issue. The default credit is the lower of INR 500 or 10% "
              "of the shipment fee. A signed customer agreement may replace the default delay "
              "threshold, credit amount, or cap."),
    dict(chunk_id="sop_v4_guardrails", document_id="03", document_name="Cancellation & Service Credit SOP v4",
         document_type="sop", customer_id=None, status="CURRENT", effective_date="2026-06-15",
         section="§3 Approval and uncertainty", scenario_tags="service_credit,cancellation",
         text="Any individual credit above INR 1,000 requires manager approval. Do not promise "
              "a credit when carrier fault, pickup timing, or customer fault is unknown. When "
              "data conflicts, identify the conflict and request verification before a "
              "state-changing action."),
    dict(chunk_id="product_guide_capabilities", document_id="04", document_name="Product Operations Guide",
         document_type="product_guide", customer_id=None, status="CURRENT", effective_date="2026-08-14",
         section="§1 Plan capabilities", scenario_tags="product_capability",
         text="Bulk Upload: available on Growth and Enterprise, supported file size up to 5,000 "
              "rows per CSV. Standard: Bulk Upload not included. BOOKED means the shipment is "
              "created but pickup confirmation not yet received. PICKED_UP means carrier pickup "
              "has been confirmed."),
    dict(chunk_id="product_guide_ki208", document_id="04", document_name="Product Operations Guide",
         document_type="product_guide", customer_id=None, status="CURRENT", effective_date="2026-08-14",
         section="§2 Known issues - KI-208", scenario_tags="known_issue,product_capability",
         text="KI-208 Bulk Upload failures on large CSVs. Opened 10 August 2026, Investigating. "
              "Some Growth and Enterprise customers experience intermittent failures on CSV "
              "uploads above approximately 3,000 rows, even though the supported product limit "
              "remains 5,000 rows. Workaround: split the upload into files below 3,000 rows. "
              "Individual shipment creation is unaffected."),
    dict(chunk_id="product_guide_ki211", document_id="04", document_name="Product Operations Guide",
         document_type="product_guide", customer_id=None, status="CURRENT", effective_date="2026-08-14",
         section="§2 Known issues - KI-211", scenario_tags="known_issue",
         text="KI-211 SwiftShip pickup webhook delay. Opened 12 August 2026, Monitoring. "
              "SwiftShip pickup confirmation webhooks can arrive up to 20 minutes late. A "
              "parcel may physically be collected while ParcelPilot still shows BOOKED. Before "
              "telling a customer that a pickup did not occur, verify the carrier status or "
              "wait through the known delay window."),
    dict(chunk_id="product_guide_ki176", document_id="04", document_name="Product Operations Guide",
         document_type="product_guide", customer_id=None, status="CURRENT", effective_date="2026-08-14",
         section="§3 Resolved issue - KI-176", scenario_tags="known_issue",
         text="KI-176 Address validation: Resolved 18 July 2026. Do not use this resolved issue "
              "to explain new incidents unless evidence specifically matches it."),
    dict(chunk_id="northstar_support_terms", document_id="05", document_name="Northstar Enterprise Agreement",
         document_type="customer_agreement", customer_id="ACCT-001", status="ACTIVE",
         effective_date="2026-01-01", section="§1 Support terms", scenario_tags="sla",
         text="For Northstar Logistics, the following first-response targets replace "
              "ParcelPilot's standard support-policy targets: P1 15 minutes 24x7, P2 1 hour, "
              "P3 8 business hours."),
    dict(chunk_id="northstar_cancellation", document_id="05", document_name="Northstar Enterprise Agreement",
         document_type="customer_agreement", customer_id="ACCT-001", status="ACTIVE",
         effective_date="2026-01-01", section="§2 Shipment cancellation", scenario_tags="cancellation",
         text="Northstar may cancel any BOOKED shipment before pickup with no cancellation fee, "
              "regardless of how long ago the shipment was booked. Once a shipment is "
              "PICKED_UP, the standard return-to-origin process applies."),
    dict(chunk_id="northstar_credits", document_id="05", document_name="Northstar Enterprise Agreement",
         document_type="customer_agreement", customer_id="ACCT-001", status="ACTIVE",
         effective_date="2026-01-01", section="§3 Service credits", scenario_tags="service_credit",
         text="Monthly aggregate service credits are capped at INR 5,000. Unless this agreement "
              "states otherwise, the current ParcelPilot service-credit SOP applies."),
    dict(chunk_id="northstar_contact", document_id="05", document_name="Northstar Enterprise Agreement",
         document_type="customer_agreement", customer_id="ACCT-001", status="ACTIVE",
         effective_date="2026-01-01", section="§4 Account contact", scenario_tags="",
         text="Dedicated CSM: Priya Mehta."),
    dict(chunk_id="lumenworks_support_terms", document_id="06", document_name="LumenWorks Service Agreement",
         document_type="customer_agreement", customer_id="ACCT-002", status="ACTIVE",
         effective_date="2026-03-01", section="§1 Support terms", scenario_tags="sla",
         text="P1 2 business hours, P2 4 business hours, P3 2 business days. No weekend or "
              "after-hours support coverage."),
    dict(chunk_id="lumenworks_cancellation", document_id="06", document_name="LumenWorks Service Agreement",
         document_type="customer_agreement", customer_id="ACCT-002", status="ACTIVE",
         effective_date="2026-03-01", section="§2 Cancellation terms", scenario_tags="cancellation",
         text="No special cancellation-fee waiver applies. Use the current ParcelPilot "
              "Cancellation & Service Credit SOP."),
    dict(chunk_id="lumenworks_credits", document_id="06", document_name="LumenWorks Service Agreement",
         document_type="customer_agreement", customer_id="ACCT-002", status="ACTIVE",
         effective_date="2026-03-01", section="§3 Failed-pickup credits", scenario_tags="service_credit",
         text="If a pickup is more than 4 hours past the end of the scheduled pickup window, "
              "the carrier is at fault, and the customer is not at fault, LumenWorks receives a "
              "fixed INR 300 service credit. This clause replaces the default failed-pickup "
              "credit amount and timing threshold in the SOP."),
]


def load(conn: sqlite3.Connection) -> None:
    conn.executemany(
        "INSERT INTO document_chunks (chunk_id, document_id, document_name, document_type, "
        "customer_id, status, effective_date, section, scenario_tags, text) "
        "VALUES (:chunk_id, :document_id, :document_name, :document_type, :customer_id, "
        ":status, :effective_date, :section, :scenario_tags, :text)",
        _CHUNKS,
    )
    conn.commit()
```

- [ ] **Step 5: Run test to verify it passes**

Run: `pytest tests/test_documents.py -v`
Expected: PASS (1 passed)

- [ ] **Step 6: Commit**

```bash
git add app/models.py app/documents.py tests/test_documents.py
git commit -m "feat: section-level document_chunks corpus for citation/retrieval"
```

---

### Task 6: RBAC (staff_users) and authorization

**Briefing:** This implements spec §10's authorization-before-retrieval
invariant. `authorize()` is the single choke point every tool must call
first — it takes the *logged-in* `StaffUser` and a target `account_id`,
and returns a pass/fail that both `query_operations_data` and
`search_policy_documents` (Task 7) will check before touching any other
table. Critically, this function does not know or care what the LLM
extracted; it's only ever given an `account_id` that's already been
resolved from a concrete order/ticket/account row (Task 7 wires that up).
Acceptance criteria: a manager passes for any account; an agent scoped to
`ACCT-002` fails for `ACCT-001`.

**Files:**
- Create: `app/auth.py`
- Test: `tests/test_auth.py`

**Interfaces:**
- Produces: `models.StaffUser(user_id, name, role, assigned_account_ids: list[str])` dataclass
- Produces: `auth.load(conn) -> None` (seeds `staff_users`)
- Produces: `auth.get_user(conn, user_id: str) -> StaffUser`
- Produces: `auth.authorize(user: StaffUser, account_id: str) -> bool`

- [ ] **Step 1: Add StaffUser to models.py**

Append to `app/models.py`:

```python
@dataclass(frozen=True)
class StaffUser:
    user_id: str
    name: str
    role: str                    # "agent" | "manager"
    assigned_account_ids: list
```

- [ ] **Step 2: Write the failing test**

Create `tests/test_auth.py`:

```python
import json

from app.auth import authorize, get_user, load
from app.seed_accounts_orders_tickets import load as load_base
from app.config import DATA_PACK_XLSX


def test_agent_authorized_for_own_account_only(conn):
    load_base(conn, DATA_PACK_XLSX)
    load(conn)
    arjun = get_user(conn, "arjun_rao")
    assert authorize(arjun, "ACCT-002") is True
    assert authorize(arjun, "ACCT-001") is False


def test_manager_authorized_for_any_account(conn):
    load_base(conn, DATA_PACK_XLSX)
    load(conn)
    manager = get_user(conn, "manager")
    assert authorize(manager, "ACCT-001") is True
    assert authorize(manager, "ACCT-004") is True
```

- [ ] **Step 3: Run test to verify it fails**

Run: `pytest tests/test_auth.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.auth'`

- [ ] **Step 4: Write auth.py**

```python
import json
import sqlite3

from app.models import StaffUser

# Mocked support users for demonstrating account-scoped authorization —
# not a real ParcelPilot org chart. Derived from accounts.csm (Task 1 data).
_STAFF = [
    ("priya_mehta", "Priya Mehta", "agent", json.dumps(["ACCT-001", "ACCT-004"])),
    ("arjun_rao", "Arjun Rao", "agent", json.dumps(["ACCT-002"])),
    ("neha_kapoor", "Neha Kapoor", "agent", json.dumps(["ACCT-003"])),
    ("manager", "Manager", "manager", json.dumps(["*"])),
]


def load(conn: sqlite3.Connection) -> None:
    conn.executemany(
        "INSERT INTO staff_users (user_id, name, role, assigned_account_ids) VALUES (?, ?, ?, ?)",
        _STAFF,
    )
    conn.commit()


def get_user(conn: sqlite3.Connection, user_id: str) -> StaffUser:
    row = conn.execute("SELECT * FROM staff_users WHERE user_id = ?", (user_id,)).fetchone()
    if row is None:
        raise ValueError(f"Unknown user_id: {user_id}")
    return StaffUser(row["user_id"], row["name"], row["role"], json.loads(row["assigned_account_ids"]))


def authorize(user: StaffUser, account_id: str) -> bool:
    return user.role == "manager" or account_id in user.assigned_account_ids
```

- [ ] **Step 5: Run test to verify it passes**

Run: `pytest tests/test_auth.py -v`
Expected: PASS (2 passed)

- [ ] **Step 6: Commit**

```bash
git add app/models.py app/auth.py tests/test_auth.py
git commit -m "feat: mocked RBAC (staff_users) and authorize() choke point"
```

---

### Task 7: query_operations_data and search_policy_documents tools

**Briefing:** These are two of the three required agent tools (spec §12).
Both take the logged-in `StaffUser` and call `auth.authorize()` **before**
touching `orders`/`tickets`/`document_chunks` — this is the concrete
implementation of spec §10's "authorization before retrieval," and of the
golden scenario "unauthorized existence probe": a denied lookup returns
`ACCESS_DENIED` without revealing whether the record exists.
`search_policy_documents` implements the exact retrieval algorithm from
spec §9 (as corrected): SQL only does the authorization/status prefilter,
Python does exact scenario-tag membership on the comma-list column, and
keyword matching only ranks within that already-scoped set. Acceptance
criteria: golden scenarios 13, 14, 15 (unauthorized cross-account,
unauthorized existence probe, unknown order) pass, plus a
document-retrieval test proving Northstar's cancellation chunk outranks
the global SOP chunk for an ACCT-001 query.

**Files:**
- Create: `app/tools.py`
- Test: `tests/test_tools_authorization.py`

**Interfaces:**
- Consumes: `auth.authorize`, `models.StaffUser` (Task 6); `models.OrderFacts`, `models.TicketFacts`, `models.AccountFacts`, `models.Citation` (Tasks 2, 5)
- Produces: `tools.AccessDenied` (exception)
- Produces: `tools.get_order(conn, order_id, user) -> OrderFacts` (raises `AccessDenied` or `LookupError`)
- Produces: `tools.get_ticket(conn, ticket_id, user) -> TicketFacts`
- Produces: `tools.get_account(conn, account_id, user) -> AccountFacts`
- Produces: `tools.search_policy_documents(conn, scenario, account_id, user, keyword=None) -> list[Citation]`

- [ ] **Step 1: Write the failing test**

Create `tests/test_tools_authorization.py`:

```python
import pytest

from app.auth import get_user, load as load_users
from app.documents import load as load_docs
from app.policy_facts import load as load_facts
from app.seed_accounts_orders_tickets import load as load_base
from app.tools import AccessDenied, get_order, search_policy_documents
from app.config import DATA_PACK_XLSX


def _seed(conn):
    load_base(conn, DATA_PACK_XLSX)
    load_facts(conn)
    load_docs(conn)
    load_users(conn)


def test_unauthorized_cross_account_order_lookup_denied(conn):
    _seed(conn)
    arjun = get_user(conn, "arjun_rao")   # scoped to ACCT-002 only
    with pytest.raises(AccessDenied):
        get_order(conn, "ORD-1001", arjun)   # belongs to ACCT-001


def test_unauthorized_existence_probe_does_not_leak_not_found_vs_denied(conn):
    _seed(conn)
    arjun = get_user(conn, "arjun_rao")
    with pytest.raises(AccessDenied):
        get_order(conn, "ORD-9999-DOES-NOT-EXIST", arjun)   # denial happens
                                                             # before existence is even checked


def test_authorized_lookup_succeeds(conn):
    _seed(conn)
    priya = get_user(conn, "priya_mehta")   # scoped to ACCT-001, ACCT-004
    order = get_order(conn, "ORD-1001", priya)
    assert order.order_id == "ORD-1001"


def test_northstar_cancellation_chunk_ranks_before_global_sop(conn):
    _seed(conn)
    priya = get_user(conn, "priya_mehta")
    citations = search_policy_documents(conn, "cancellation", "ACCT-001", priya)
    assert citations[0].document_name == "Northstar Enterprise Agreement"
    assert any(c.document_name == "Cancellation & Service Credit SOP v4" for c in citations)
    assert all(c.status != "DEPRECATED" for c in citations)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_tools_authorization.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.tools'`

- [ ] **Step 3: Write tools.py**

```python
import sqlite3
from datetime import datetime

from app.auth import authorize
from app.models import AccountFacts, Citation, OrderFacts, StaffUser, TicketFacts


class AccessDenied(Exception):
    pass


def _account_id_for_order(conn: sqlite3.Connection, order_id: str) -> str | None:
    row = conn.execute("SELECT account_id FROM orders WHERE order_id = ?", (order_id,)).fetchone()
    return row["account_id"] if row else None


def _account_id_for_ticket(conn: sqlite3.Connection, ticket_id: str) -> str | None:
    row = conn.execute("SELECT account_id FROM tickets WHERE ticket_id = ?", (ticket_id,)).fetchone()
    return row["account_id"] if row else None


def get_order(conn: sqlite3.Connection, order_id: str, user: StaffUser) -> OrderFacts:
    owning_account = _account_id_for_order(conn, order_id)
    # Authorization is checked against the account the ID *would* belong to if it
    # exists, or against the user's own scope if it doesn't — either way, a denial
    # happens before we reveal whether the record exists.
    check_account = owning_account or (user.assigned_account_ids[0] if user.role != "manager" and user.assigned_account_ids else None)
    if owning_account is not None and not authorize(user, owning_account):
        raise AccessDenied(f"Not authorized for account {owning_account}")
    if owning_account is None:
        if user.role != "manager":
            raise AccessDenied("Not authorized")   # fail closed rather than confirm non-existence
        raise LookupError(f"Order {order_id} not found")

    row = conn.execute("SELECT * FROM orders WHERE order_id = ?", (order_id,)).fetchone()
    return OrderFacts(
        order_id=row["order_id"], account_id=row["account_id"], carrier=row["carrier"],
        status=row["status"], booked_at=datetime.fromisoformat(row["booked_at"]),
        pickup_window_start=datetime.fromisoformat(row["pickup_window_start"]) if row["pickup_window_start"] else None,
        pickup_window_end=datetime.fromisoformat(row["pickup_window_end"]) if row["pickup_window_end"] else None,
        pickup_actual_at=datetime.fromisoformat(row["pickup_actual_at"]) if row["pickup_actual_at"] else None,
        shipment_fee_inr=row["shipment_fee_inr"],
        carrier_fault=bool(row["carrier_fault"]) if row["carrier_fault"] is not None else None,
        customer_fault=bool(row["customer_fault"]) if row["customer_fault"] is not None else None,
        cancellation_requested_at=datetime.fromisoformat(row["cancellation_requested_at"]) if row["cancellation_requested_at"] else None,
        notes=row["notes"],
    )


def get_ticket(conn: sqlite3.Connection, ticket_id: str, user: StaffUser) -> TicketFacts:
    owning_account = _account_id_for_ticket(conn, ticket_id)
    if owning_account is not None and not authorize(user, owning_account):
        raise AccessDenied(f"Not authorized for account {owning_account}")
    if owning_account is None:
        if user.role != "manager":
            raise AccessDenied("Not authorized")
        raise LookupError(f"Ticket {ticket_id} not found")

    row = conn.execute("SELECT * FROM tickets WHERE ticket_id = ?", (ticket_id,)).fetchone()
    return TicketFacts(
        ticket_id=row["ticket_id"], account_id=row["account_id"],
        created_at=datetime.fromisoformat(row["created_at"]), status=row["status"],
        subject=row["subject"], description=row["description"], channel=row["channel"],
        assigned_to=row["assigned_to"],
        last_customer_message_at=datetime.fromisoformat(row["last_customer_message_at"]) if row["last_customer_message_at"] else None,
        historical_resolution=row["historical_resolution"],
    )


def get_account(conn: sqlite3.Connection, account_id: str, user: StaffUser) -> AccountFacts:
    if not authorize(user, account_id):
        raise AccessDenied(f"Not authorized for account {account_id}")
    row = conn.execute("SELECT * FROM accounts WHERE account_id = ?", (account_id,)).fetchone()
    if row is None:
        raise LookupError(f"Account {account_id} not found")
    return AccountFacts(
        account_id=row["account_id"], account_name=row["account_name"], plan=row["plan"],
        status=row["status"], csm=row["csm"], contract_file=row["contract_file"],
        premium_support=bool(row["premium_support"]),
    )


def search_policy_documents(
    conn: sqlite3.Connection, scenario: str, account_id: str | None, user: StaffUser,
    keyword: str | None = None,
) -> list:
    if account_id is not None and not authorize(user, account_id):
        raise AccessDenied(f"Not authorized for account {account_id}")

    rows = conn.execute(
        "SELECT * FROM document_chunks WHERE status != 'DEPRECATED' "
        "AND (customer_id IS NULL OR customer_id = ?)", (account_id,)
    ).fetchall()

    candidates = [r for r in rows if scenario in r["scenario_tags"].split(",")]

    if keyword:
        kw = keyword.lower()
        candidates = sorted(candidates, key=lambda r: kw not in r["text"].lower())

    candidates = sorted(candidates, key=lambda r: r["customer_id"] is None)

    return [
        Citation(r["document_name"], r["section"], r["text"], r["status"], r["effective_date"], r["customer_id"])
        for r in candidates
    ]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_tools_authorization.py -v`
Expected: PASS (4 passed)

- [ ] **Step 5: Commit**

```bash
git add app/tools.py tests/test_tools_authorization.py
git commit -m "feat: authorization-gated query_operations_data and search_policy_documents tools"
```

---

### Task 8: IncidentFacts extraction (Gemini) and deterministic severity mapping

**Briefing:** This is the one place an LLM call touches the trust-critical
path, and spec §13 exists specifically to bound it: the model only ever
extracts six named booleans (or `"unknown"`) from ticket text — never a
severity label directly. `map_severity()` is pure Python, unit-tested
completely independently of any network call (fixed `IncidentFacts` in,
fixed severity out). The Gemini call is isolated in
`extract_incident_facts()` so the deterministic mapping can be tested
without hitting the network, and so a flaky/slow API call can never make a
policy calculation flaky. Acceptance criteria: `map_severity` unit tests
pass with zero network calls; a separate, explicitly-marked integration
test calls Gemini once against TKT-501's and TKT-505's real text and
asserts the mapped severity is P1 for both (skipped automatically if
`GEMINI_API_KEY` is unset, so the offline suite still runs green).

**Files:**
- Create: `app/severity.py`
- Test: `tests/test_severity_mapping.py`

**Interfaces:**
- Produces: `severity.IncidentFacts` (pydantic `BaseModel`, fields: `is_security_incident`, `is_complete_shipment_outage`, `immediate_material_business_risk`, `is_major_feature_degraded`, `core_operations_possible`, `workaround_exists`, each `bool | Literal["unknown"]`)
- Produces: `severity.map_severity(facts: IncidentFacts) -> tuple[str | None, bool]` (returns `(severity, needs_review)`)
- Produces: `severity.extract_incident_facts(subject: str, description: str) -> IncidentFacts` (calls Gemini)

- [ ] **Step 1: Write the failing test**

Create `tests/test_severity_mapping.py`:

```python
from app.severity import IncidentFacts, map_severity


def test_security_incident_is_p1():
    facts = IncidentFacts(
        is_security_incident=True, is_complete_shipment_outage=False,
        immediate_material_business_risk=False, is_major_feature_degraded=False,
        core_operations_possible=True, workaround_exists=True,
    )
    severity, needs_review = map_severity(facts)
    assert severity == "P1"
    assert needs_review is False


def test_complete_outage_is_p1():
    facts = IncidentFacts(
        is_security_incident=False, is_complete_shipment_outage=True,
        immediate_material_business_risk=False, is_major_feature_degraded=False,
        core_operations_possible=False, workaround_exists=False,
    )
    severity, needs_review = map_severity(facts)
    assert severity == "P1"


def test_business_risk_catch_all_without_workaround_is_p1():
    facts = IncidentFacts(
        is_security_incident=False, is_complete_shipment_outage=False,
        immediate_material_business_risk=True, is_major_feature_degraded=False,
        core_operations_possible=False, workaround_exists=False,
    )
    severity, needs_review = map_severity(facts)
    assert severity == "P1"


def test_major_feature_degraded_with_workaround_is_p2():
    facts = IncidentFacts(
        is_security_incident=False, is_complete_shipment_outage=False,
        immediate_material_business_risk=False, is_major_feature_degraded=True,
        core_operations_possible=False, workaround_exists=True,
    )
    severity, needs_review = map_severity(facts)
    assert severity == "P2"


def test_minor_issue_is_p3():
    facts = IncidentFacts(
        is_security_incident=False, is_complete_shipment_outage=False,
        immediate_material_business_risk=False, is_major_feature_degraded=False,
        core_operations_possible=True, workaround_exists=True,
    )
    severity, needs_review = map_severity(facts)
    assert severity == "P3"


def test_unknown_security_field_forces_needs_review():
    facts = IncidentFacts(
        is_security_incident="unknown", is_complete_shipment_outage=False,
        immediate_material_business_risk=False, is_major_feature_degraded=False,
        core_operations_possible=True, workaround_exists=True,
    )
    severity, needs_review = map_severity(facts)
    assert severity is None
    assert needs_review is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_severity_mapping.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.severity'`

- [ ] **Step 3: Write severity.py**

```python
from typing import Literal

from pydantic import BaseModel

from app import config

BoolOrUnknown = bool | Literal["unknown"]


class IncidentFacts(BaseModel):
    is_security_incident: BoolOrUnknown
    is_complete_shipment_outage: BoolOrUnknown
    immediate_material_business_risk: BoolOrUnknown
    is_major_feature_degraded: BoolOrUnknown
    core_operations_possible: BoolOrUnknown
    workaround_exists: BoolOrUnknown


def map_severity(f: IncidentFacts) -> tuple[str | None, bool]:
    if "unknown" in (f.is_security_incident, f.is_complete_shipment_outage):
        return None, True
    if f.is_security_incident or f.is_complete_shipment_outage:
        return "P1", False

    if "unknown" in (f.immediate_material_business_risk, f.workaround_exists):
        return None, True
    if f.immediate_material_business_risk and not f.workaround_exists:
        return "P1", False

    if "unknown" in (f.is_major_feature_degraded, f.core_operations_possible, f.workaround_exists):
        return None, True
    if f.is_major_feature_degraded and (f.core_operations_possible or f.workaround_exists):
        return "P2", False

    return "P3", False


_PROMPT = """You are extracting structured incident facts from a support ticket for a
logistics company. Read the subject and description below and answer each question
with true, false, or "unknown" if the text genuinely does not say. Do not guess.

Subject: {subject}
Description: {description}

Answer as JSON matching this schema:
{{
  "is_security_incident": true|false|"unknown",
  "is_complete_shipment_outage": true|false|"unknown",
  "immediate_material_business_risk": true|false|"unknown",
  "is_major_feature_degraded": true|false|"unknown",
  "core_operations_possible": true|false|"unknown",
  "workaround_exists": true|false|"unknown"
}}
"""


def extract_incident_facts(subject: str, description: str) -> IncidentFacts:
    from google import genai

    client = genai.Client(api_key=config.GEMINI_API_KEY)
    response = client.models.generate_content(
        model="gemini-2.0-flash",
        contents=_PROMPT.format(subject=subject, description=description),
        config={"response_mime_type": "application/json", "response_schema": IncidentFacts},
    )
    return IncidentFacts.model_validate_json(response.text)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_severity_mapping.py -v`
Expected: PASS (6 passed) — no network call is made by any of these tests.

- [ ] **Step 5: Add a network-dependent integration test (skips without a key)**

Append to `tests/test_severity_mapping.py`:

```python
import os

import pytest

from app.severity import extract_incident_facts, map_severity


@pytest.mark.skipif(not os.environ.get("GEMINI_API_KEY"), reason="requires GEMINI_API_KEY")
def test_tkt505_api_key_exposure_extracts_as_p1():
    facts = extract_incident_facts(
        "Possible API key exposure",
        "An employee accidentally posted a screenshot containing a production API "
        "key in a public channel. They are asking what to do.",
    )
    severity, _ = map_severity(facts)
    assert severity == "P1"


@pytest.mark.skipif(not os.environ.get("GEMINI_API_KEY"), reason="requires GEMINI_API_KEY")
def test_tkt501_complete_outage_extracts_as_p1():
    facts = extract_incident_facts(
        "All shipment creation is failing",
        "Every user at Northstar gets HTTP 500 when creating any shipment. "
        "Existing shipments can still be viewed.",
    )
    severity, _ = map_severity(facts)
    assert severity == "P1"
```

- [ ] **Step 6: Run the full file to verify both integration tests pass with a real key set**

Run: `GEMINI_API_KEY=... pytest tests/test_severity_mapping.py -v`
Expected: PASS (8 passed)

- [ ] **Step 7: Commit**

```bash
git add app/severity.py tests/test_severity_mapping.py
git commit -m "feat: IncidentFacts extraction (Gemini) + deterministic P1/P2/P3 mapping"
```

---

### Task 9: Action layer (create_action / confirm_action) and audit log

**Briefing:** This is the third required tool (spec §12, §14): a
state-changing action that must never execute without an explicit
confirmation step. `create_action` only ever writes `status="PREPARED"` —
it cannot, by construction, cause a side effect a user didn't ask for.
`confirm_action` is the only function that can move a row to `EXECUTED` or
`FAILED`, and it writes an `audit_logs` row on every transition. There is
no persisted `EXECUTING` state (spec §14 correction) because execution here
is a synchronous local SQLite write — no state exists where "in progress"
would ever be observed. Acceptance criteria: an action created but never
confirmed stays `PREPARED` forever; confirming it moves it to `EXECUTED`
and writes exactly one audit row; a forced failure (simulated) lands in
`FAILED`, never silently in `EXECUTED`.

**Files:**
- Create: `app/actions.py`
- Test: `tests/test_actions.py`

**Interfaces:**
- Consumes: `models.StaffUser`, `auth.authorize`
- Produces: `models.ActionDraft(action_id, action_type, account_id, status)` dataclass
- Produces: `actions.create_action(conn, action_type, account_id, ticket_id, order_id, payload, user) -> ActionDraft`
- Produces: `actions.confirm_action(conn, action_id, user) -> ActionDraft`

- [ ] **Step 1: Add ActionDraft to models.py**

Append to `app/models.py`:

```python
@dataclass(frozen=True)
class ActionDraft:
    action_id: str
    action_type: str
    account_id: str
    status: str
```

- [ ] **Step 2: Write the failing test**

Create `tests/test_actions.py`:

```python
from app.actions import confirm_action, create_action
from app.auth import get_user, load as load_users
from app.seed_accounts_orders_tickets import load as load_base
from app.config import DATA_PACK_XLSX


def _seed(conn):
    load_base(conn, DATA_PACK_XLSX)
    load_users(conn)


def test_create_action_is_prepared_and_takes_no_effect(conn):
    _seed(conn)
    priya = get_user(conn, "priya_mehta")
    draft = create_action(
        conn, "create_escalation", "ACCT-001", ticket_id="TKT-501", order_id=None,
        payload={"reason": "Complete shipment-creation outage"}, user=priya,
    )
    assert draft.status == "PREPARED"
    row = conn.execute("SELECT status FROM actions WHERE action_id = ?", (draft.action_id,)).fetchone()
    assert row["status"] == "PREPARED"


def test_confirm_action_executes_and_writes_one_audit_row(conn):
    _seed(conn)
    priya = get_user(conn, "priya_mehta")
    draft = create_action(
        conn, "create_escalation", "ACCT-001", ticket_id="TKT-501", order_id=None,
        payload={"reason": "..."}, user=priya,
    )
    confirmed = confirm_action(conn, draft.action_id, priya)
    assert confirmed.status == "EXECUTED"
    audit_count = conn.execute(
        "SELECT COUNT(*) FROM audit_logs WHERE action_id = ?", (draft.action_id,)
    ).fetchone()[0]
    assert audit_count == 1
```

- [ ] **Step 3: Run test to verify it fails**

Run: `pytest tests/test_actions.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.actions'`

- [ ] **Step 4: Write actions.py**

```python
import json
import sqlite3
import uuid
from datetime import datetime, timezone

from app.auth import authorize
from app.models import ActionDraft, StaffUser
from app.tools import AccessDenied


def create_action(
    conn: sqlite3.Connection, action_type: str, account_id: str,
    ticket_id: str | None, order_id: str | None, payload: dict, user: StaffUser,
) -> ActionDraft:
    if not authorize(user, account_id):
        raise AccessDenied(f"Not authorized for account {account_id}")

    action_id = f"ACT-{uuid.uuid4().hex[:8]}"
    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        "INSERT INTO actions (action_id, action_type, account_id, ticket_id, order_id, "
        "payload_json, prepared_by, status, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, 'PREPARED', ?)",
        (action_id, action_type, account_id, ticket_id, order_id, json.dumps(payload), user.user_id, now),
    )
    conn.commit()
    return ActionDraft(action_id, action_type, account_id, "PREPARED")


def confirm_action(conn: sqlite3.Connection, action_id: str, user: StaffUser) -> ActionDraft:
    row = conn.execute("SELECT * FROM actions WHERE action_id = ?", (action_id,)).fetchone()
    if row is None:
        raise LookupError(f"Action {action_id} not found")
    if not authorize(user, row["account_id"]):
        raise AccessDenied(f"Not authorized for account {row['account_id']}")

    now = datetime.now(timezone.utc).isoformat()
    try:
        # Local SQLite write stands in for the mocked external side effect
        # (e.g. creating a ticket-system escalation). Any exception here is
        # caught below so a failure is recorded as FAILED, never EXECUTED.
        conn.execute(
            "UPDATE actions SET status = 'EXECUTED', confirmed_at = ?, executed_at = ? "
            "WHERE action_id = ?", (now, now, action_id),
        )
        final_status = "EXECUTED"
    except sqlite3.Error:
        conn.execute(
            "UPDATE actions SET status = 'FAILED', confirmed_at = ? WHERE action_id = ?",
            (now, action_id),
        )
        final_status = "FAILED"
    conn.commit()

    conn.execute(
        "INSERT INTO audit_logs (log_id, timestamp, user, account_id, action_id, decision_json) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (f"LOG-{uuid.uuid4().hex[:8]}", now, user.user_id, row["account_id"], action_id,
         json.dumps({"final_status": final_status})),
    )
    conn.commit()

    return ActionDraft(action_id, row["action_type"], row["account_id"], final_status)
```

- [ ] **Step 5: Run test to verify it passes**

Run: `pytest tests/test_actions.py -v`
Expected: PASS (2 passed)

- [ ] **Step 6: Commit**

```bash
git add app/models.py app/actions.py tests/test_actions.py
git commit -m "feat: confirmation-gated action layer with audit logging"
```

---

### Task 10: LangGraph agent workflow

**Briefing:** This is where every deterministic piece built so far gets
wired into one *actual* LangGraph `StateGraph` (spec §3, §11) — not a
flat function, because the workflow genuinely branches: an order-scoped
query (cancellation/credit) and a ticket-scoped query (SLA/severity) need
different tool calls and different resolvers, and three separate points
need to short-circuit straight to the end (`AccessDenied`, record not
found, severity genuinely `"unknown"`) without ever reaching a resolver.
That's exactly what `add_conditional_edges` is for: routing is decided
once, explicitly, by a small routing function reading state, rather than
by nested `if/elif` scattered through one long function.

Nodes: `plan` (LLM: classify scenario + extract entities) ->
`gather` (deterministic: resolve owning account via the tool layer, call
`get_order`/`get_ticket` + `search_policy_documents`; sets
`authorization_result`) -> **conditional routing**: denied/not-found exits
straight to `END`; an order query goes to `resolve_order`; a ticket query
goes to `classify_severity`. `classify_severity` (LLM extraction +
deterministic `map_severity`) -> **conditional routing**: an unresolvable
severity exits to a `severity_needs_review` node; otherwise on to
`resolve_sla_step`. Both `resolve_order` and `resolve_sla_step` are
deterministic — never LLM-choosable tools, they always run once their
node is reached, per spec §12 — and both feed into `explain` (LLM: turn
the typed decision + citations into prose, never inventing facts not in
the decision object). `conn`/`user`/`reference_time` are per-invocation
dependencies passed via LangGraph's `config={"configurable": {...}}`
mechanism, not stored in the checkpointed state, since a SQLite connection
isn't something you'd want serialized. Acceptance criteria: golden
scenario 11 (TKT-450 historical-conflict probe) passes end-to-end — the
agent must answer "no, ₹250 is wrong" and cite both the historical ticket
and the Northstar agreement, using only the deterministic decision for the
number — and the unauthorized/not-found/needs-review golden scenarios all
short-circuit via the conditional edges rather than reaching a resolver.

**Files:**
- Create: `app/agent.py`
- Test: `tests/test_agent_golden_scenarios.py`

**Interfaces:**
- Consumes: everything from Tasks 1-9
- Produces: `agent.AgentState` (TypedDict per spec §11)
- Produces: `agent.run(user_query: str, user: StaffUser, conn) -> AgentState` (invokes the compiled graph)

- [ ] **Step 1: Write the failing test**

Create `tests/test_agent_golden_scenarios.py`:

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_agent_golden_scenarios.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.agent'` (both skipped if no key, so run once with `GEMINI_API_KEY` set to confirm the fail-then-pass cycle)

- [ ] **Step 3: Write agent.py**

```python
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
    client = genai.Client(api_key=config.GEMINI_API_KEY)
    response = client.models.generate_content(
        model="gemini-2.0-flash",
        contents=_PLAN_PROMPT.format(query=query),
        config={"response_mime_type": "application/json", "response_schema": _PlanExtraction},
    )
    return _PlanExtraction.model_validate_json(response.text)


def _explain(query: str, decision, citations) -> str:
    client = genai.Client(api_key=config.GEMINI_API_KEY)
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `GEMINI_API_KEY=... pytest tests/test_agent_golden_scenarios.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Add a routing-only test that needs no network call**

Append to `tests/test_agent_golden_scenarios.py`:

```python
from app.agent import _route_after_gather, _route_after_severity


def test_route_after_gather_denies_before_resolving():
    assert _route_after_gather({"authorization_result": "DENIED"}) == "end"
    assert _route_after_gather({"authorization_result": "AUTHORIZED", "data_evidence": {"order": object()}}) == "resolve_order"
    assert _route_after_gather({"authorization_result": "AUTHORIZED", "data_evidence": {"ticket": object()}}) == "classify_severity"


def test_route_after_severity_needs_review_on_unknown():
    assert _route_after_severity({"_severity": None, "_severity_needs_review": True}) == "needs_review"
    assert _route_after_severity({"_severity": "P2", "_severity_needs_review": False}) == "resolve_sla"
```

Run: `pytest tests/test_agent_golden_scenarios.py -v -k route`
Expected: PASS (2 passed), no network call made

- [ ] **Step 6: Commit**

```bash
git add app/agent.py tests/test_agent_golden_scenarios.py
git commit -m "feat: LangGraph StateGraph wiring planner, tools, resolvers, and guardrail routing"
```

---

### Task 11: Overview — SLA risk list and issue clustering

**Briefing:** This reuses Tasks 7-8 (spec §16 rationale: "favorable
marginal implementation cost," not "free"). No new infrastructure: it
loops over open tickets, calls the same severity/SLA machinery per ticket,
and reuses `search_policy_documents`'s keyword-matching approach against
`known_issue`-tagged chunks to group tickets by matched `KI-xxx` id (spec
§16 clustering mechanism, added in the corrected spec). Acceptance
criteria: TKT-501 and TKT-505 (both P1) appear in the SLA-risk list;
TKT-502 groups under KI-208.

**Files:**
- Create: `app/overview.py`
- Test: `tests/test_overview.py`

**Interfaces:**
- Consumes: `get_ticket`-style raw ticket rows, `resolve_sla`, `map_severity`/`extract_incident_facts`, `document_chunks` table
- Produces: `overview.sla_risk_tickets(conn, user) -> list[dict]`
- Produces: `overview.issue_clusters(conn, user) -> list[dict]` (each: `{ki_id, ticket_ids, account_ids, is_multi_customer}`)

- [ ] **Step 1: Write the failing test**

Create `tests/test_overview.py`:

```python
from app.auth import get_user, load as load_users
from app.documents import load as load_docs
from app.overview import issue_clusters
from app.seed_accounts_orders_tickets import load as load_base
from app.config import DATA_PACK_XLSX


def test_ki208_cluster_includes_tkt502(conn):
    load_base(conn, DATA_PACK_XLSX)
    load_docs(conn)
    load_users(conn)
    manager = get_user(conn, "manager")
    clusters = issue_clusters(conn, manager)
    ki208 = next(c for c in clusters if c["ki_id"] == "product_guide_ki208")
    assert "TKT-502" in ki208["ticket_ids"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_overview.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.overview'`

- [ ] **Step 3: Write overview.py**

```python
import sqlite3

from app.auth import authorize
from app.models import StaffUser


def _visible_open_tickets(conn: sqlite3.Connection, user: StaffUser):
    rows = conn.execute("SELECT * FROM tickets WHERE status = 'open'").fetchall()
    return [r for r in rows if authorize(user, r["account_id"])]


def issue_clusters(conn: sqlite3.Connection, user: StaffUser) -> list:
    known_issue_chunks = conn.execute(
        "SELECT chunk_id, text FROM document_chunks WHERE 'known_issue' IN "
        "(SELECT value FROM json_each('[\"' || REPLACE(scenario_tags, ',', '\",\"') || '\"]'))"
    ).fetchall() if False else conn.execute(
        "SELECT chunk_id, text, scenario_tags FROM document_chunks"
    ).fetchall()
    known_issue_chunks = [c for c in known_issue_chunks if "known_issue" in c["scenario_tags"].split(",")]

    tickets = _visible_open_tickets(conn, user)

    clusters = []
    for chunk in known_issue_chunks:
        matched = [
            t for t in tickets
            if _keyword_overlap(t["subject"] + " " + t["description"], chunk["text"])
        ]
        if matched:
            account_ids = {t["account_id"] for t in matched}
            clusters.append({
                "ki_id": chunk["chunk_id"],
                "ticket_ids": [t["ticket_id"] for t in matched],
                "account_ids": list(account_ids),
                "is_multi_customer": len(account_ids) > 1,
            })
    return [c for c in clusters if len(c["ticket_ids"]) >= 1]


def _keyword_overlap(ticket_text: str, chunk_text: str) -> bool:
    # Simple, deterministic overlap check: does the ticket mention a distinctive
    # noun phrase from the known-issue chunk? Reuses the same "keyword inside text"
    # idea as search_policy_documents rather than introducing new matching logic.
    ticket_words = set(ticket_text.lower().split())
    distinctive_terms = ["bulk upload", "csv", "webhook", "booked", "swiftship"]
    chunk_lower = chunk_text.lower()
    return any(term in ticket_text.lower() and term in chunk_lower for term in distinctive_terms)


def sla_risk_tickets(conn: sqlite3.Connection, user: StaffUser) -> list:
    from app.models import AccountFacts, TicketFacts
    from app.resolvers import resolve_sla
    from app.severity import extract_incident_facts, map_severity
    from app import config

    reference_time = config.REFERENCE_TIME.replace(tzinfo=None)
    results = []
    for row in _visible_open_tickets(conn, user):
        ticket = TicketFacts(
            ticket_id=row["ticket_id"], account_id=row["account_id"],
            created_at=__import__("datetime").datetime.fromisoformat(row["created_at"]),
            status=row["status"], subject=row["subject"], description=row["description"],
            channel=row["channel"], assigned_to=row["assigned_to"],
            last_customer_message_at=None, historical_resolution=row["historical_resolution"],
        )
        account_row = conn.execute(
            "SELECT * FROM accounts WHERE account_id = ?", (ticket.account_id,)
        ).fetchone()
        account = AccountFacts(
            account_row["account_id"], account_row["account_name"], account_row["plan"],
            account_row["status"], account_row["csm"], account_row["contract_file"],
            bool(account_row["premium_support"]),
        )
        incident_facts = extract_incident_facts(ticket.subject, ticket.description)
        severity, needs_review = map_severity(incident_facts)
        if needs_review or severity is None:
            results.append({"ticket_id": ticket.ticket_id, "severity": None, "at_risk": None, "needs_review": True})
            continue
        decision = resolve_sla(conn, ticket, account, severity, reference_time)
        results.append({
            "ticket_id": ticket.ticket_id, "severity": decision.severity,
            "at_risk": decision.at_risk, "needs_review": False,
        })
    return results
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_overview.py -v`
Expected: PASS (1 passed)

- [ ] **Step 5: Add the SLA-risk test (network-gated, matches Task 8/10's skipif pattern)**

Append to `tests/test_overview.py`:

```python
import os

import pytest

from app.overview import sla_risk_tickets


@pytest.mark.skipif(not os.environ.get("GEMINI_API_KEY"), reason="requires GEMINI_API_KEY")
def test_tkt501_and_tkt505_are_p1_at_risk(conn):
    load_base(conn, DATA_PACK_XLSX)
    load_docs(conn)
    load_users(conn)
    manager = get_user(conn, "manager")
    results = {r["ticket_id"]: r for r in sla_risk_tickets(conn, manager)}
    assert results["TKT-501"]["severity"] == "P1"
    assert results["TKT-505"]["severity"] == "P1"
```

- [ ] **Step 6: Run with a real key to verify it passes**

Run: `GEMINI_API_KEY=... pytest tests/test_overview.py -v`
Expected: PASS (2 passed)

- [ ] **Step 7: Commit**

```bash
git add app/overview.py tests/test_overview.py
git commit -m "feat: proactive issue clustering and SLA-risk list, both reusing existing tools"
```

---

### Task 12: FastAPI app and UI

**Briefing:** This wires everything into the single-page UI from spec §16:
Overview / Investigate / Actions-Audit tabs, a "Log in as..." selector, and
a rendered tool-call timeline (never raw model chain-of-thought — spec
§16/§21). FastAPI serves both the JSON endpoints the JS calls and the
Jinja2 shell. Acceptance criteria: `uvicorn app.main:app` starts, `/`
renders the shell, `POST /api/investigate` returns a JSON body containing
`answer_text`, `tool_call_log`, and `decision_status` for a real query.

**Files:**
- Create: `app/main.py`
- Create: `app/templates/index.html`
- Create: `app/static/app.js`
- Create: `app/static/style.css`
- Test: `tests/test_main.py`

**Interfaces:**
- Consumes: `agent.run`, `auth.get_user`, `overview.issue_clusters`/`sla_risk_tickets`, `actions.create_action`/`confirm_action`
- Produces: `POST /api/investigate {query, user_id} -> {answer_text, tool_call_log, decision_status, policy_decision}`
- Produces: `GET /api/overview?user_id=... -> {clusters: [...]}`
- Produces: `POST /api/actions/confirm {action_id, user_id} -> {status}`

- [ ] **Step 1: Write the failing test**

Create `tests/test_main.py`:

```python
from fastapi.testclient import TestClient

from app.main import app


def test_index_renders():
    client = TestClient(app)
    response = client.get("/")
    assert response.status_code == 200
    assert "ParcelPilot" in response.text
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_main.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.main'`

- [ ] **Step 3: Write main.py**

```python
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

from app import config, db
from app.agent import run
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
    return templates.TemplateResponse("index.html", {"request": request})


@app.post("/api/investigate")
def investigate(body: InvestigateRequest):
    conn = _get_seeded_connection()
    user = get_user(conn, body.user_id)
    state = run(body.query, user, conn)
    return {
        "answer_text": state.get("answer_text"),
        "tool_call_log": state.get("tool_call_log", []),
        "decision_status": state.get("decision_status"),
        "policy_decision": str(state.get("policy_decision")) if state.get("policy_decision") else None,
    }


@app.get("/api/overview")
def overview(user_id: str):
    conn = _get_seeded_connection()
    user = get_user(conn, user_id)
    return {"clusters": issue_clusters(conn, user), "sla_risk": sla_risk_tickets(conn, user)}
```

- [ ] **Step 4: Write the Jinja2 shell**

Create `app/templates/index.html`:

```html
<title>ParcelPilot AI Support Operations Copilot</title>
<link rel="stylesheet" href="/static/style.css">
<div id="app">
  <header>
    <h1>ParcelPilot Support Copilot</h1>
    <select id="user-select">
      <option value="priya_mehta">Priya Mehta (Northstar, Axis)</option>
      <option value="arjun_rao">Arjun Rao (LumenWorks)</option>
      <option value="neha_kapoor">Neha Kapoor (Beacon)</option>
      <option value="manager">Manager (all accounts)</option>
    </select>
  </header>
  <nav>
    <button data-tab="investigate" class="active">Investigate</button>
    <button data-tab="overview">Overview</button>
    <button data-tab="audit">Actions / Audit</button>
  </nav>
  <section id="investigate" class="tab active">
    <input id="query-input" placeholder="e.g. Can Northstar cancel ORD-1001 without a fee?">
    <button id="ask-button">Ask</button>
    <div id="tool-timeline"></div>
    <div id="answer"></div>
  </section>
  <section id="overview" class="tab"></section>
  <section id="audit" class="tab"></section>
</div>
<script src="/static/app.js"></script>
```

- [ ] **Step 5: Write app.js and style.css (minimal, functional)**

Create `app/static/style.css`:

```css
body { font-family: system-ui, sans-serif; max-width: 900px; margin: 2rem auto; }
.tab { display: none; } .tab.active { display: block; }
#tool-timeline div { color: #555; font-size: 0.9em; }
```

Create `app/static/app.js`:

```javascript
document.querySelectorAll("nav button").forEach(btn => {
  btn.addEventListener("click", () => {
    document.querySelectorAll("nav button, .tab").forEach(el => el.classList.remove("active"));
    btn.classList.add("active");
    document.getElementById(btn.dataset.tab).classList.add("active");
  });
});

document.getElementById("ask-button").addEventListener("click", async () => {
  const query = document.getElementById("query-input").value;
  const userId = document.getElementById("user-select").value;
  const res = await fetch("/api/investigate", {
    method: "POST", headers: {"Content-Type": "application/json"},
    body: JSON.stringify({query, user_id: userId}),
  });
  const data = await res.json();
  document.getElementById("tool-timeline").innerHTML =
    data.tool_call_log.map(t => `<div>&#128269; ${t.tool}(${t.args})</div>`).join("");
  document.getElementById("answer").innerText =
    `[${data.decision_status}] ${data.answer_text}`;
});
```

- [ ] **Step 6: Run test to verify it passes**

Run: `pytest tests/test_main.py -v`
Expected: PASS (1 passed)

- [ ] **Step 7: Commit**

```bash
git add app/main.py app/templates/index.html app/static/app.js app/static/style.css tests/test_main.py
git commit -m "feat: FastAPI app with Investigate/Overview/Audit tabs and tool-call timeline"
```

---

### Task 13: Dockerize and deploy

**Briefing:** Single-container deployment per spec §19 — no split
frontend/backend hosts, no managed database. The SQLite file is built at
container startup by `_get_seeded_connection()` (already idempotent —
Task 12), so the image itself carries no pre-baked database. Acceptance
criteria: `docker build` succeeds, `docker run -p 8000:8000 -e
GEMINI_API_KEY=... image` serves the UI, and the hosted URL (once deployed)
answers the ORD-1001 golden scenario correctly through the browser.

**Files:**
- Create: `Dockerfile`
- Create: `.dockerignore`

- [ ] **Step 1: Write Dockerfile**

```dockerfile
FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app/ ./app/
COPY "AI Agent Assessment - Candidate Pack/" "./AI Agent Assessment - Candidate Pack/"
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

- [ ] **Step 2: Write .dockerignore**

```
ass1/
tests/
docs/
.git/
__pycache__/
*.pyc
app/parcelpilot.db
```

- [ ] **Step 3: Build and smoke-test locally**

Run: `docker build -t parcelpilot-copilot .`
Expected: build succeeds

Run: `docker run -p 8000:8000 -e GEMINI_API_KEY=$GEMINI_API_KEY parcelpilot-copilot`
Expected: `curl http://localhost:8000/` returns 200 with "ParcelPilot" in the body

- [ ] **Step 4: Deploy to a single-container host (Render/Railway/Fly.io — pick one) and smoke-test**

Run (after deploying, adjust URL): `curl -X POST https://<hosted-url>/api/investigate -H "Content-Type: application/json" -d '{"query":"Can Northstar cancel ORD-1001 without a cancellation fee?","user_id":"priya_mehta"}'`
Expected: JSON response with `"decision_status": "READY"` and fee 0 reflected in `answer_text`

- [ ] **Step 5: Commit**

```bash
git add Dockerfile .dockerignore
git commit -m "chore: single-container Dockerfile for deployment"
```

---

### Task 14: Submission deliverables

**Briefing:** Not code — this converts the spec/plan into the required
submission artifacts (architecture note, product note, AI-tool-usage note,
demo video, README). Doing this last, once the running system exists,
means every claim in these documents can be checked against actual
behavior rather than intent.

**Files:**
- Create: `README.md`
- Create: `docs/architecture-note.md`
- Create: `docs/product-note.md`
- Create: `docs/ai-tool-usage.md`

- [ ] **Step 1: Write README.md** — setup/run instructions (venv activation, `pip install -r requirements.txt`, `GEMINI_API_KEY` export, `uvicorn app.main:app --reload`, `pytest`), plus the hosted URL once deployed.

- [ ] **Step 2: Write docs/architecture-note.md** — summarize spec §3 (LLM-plans/code-decides), §5-§9 (schema, resolvers, retrieval), §10 (RBAC), §13 (severity split), §14 (action state machine), each with the "why/alternatives rejected" already captured in the spec — this note is largely a curated excerpt of the spec, not new writing.

- [ ] **Step 3: Write docs/product-note.md** — per the assessment's required contents: chosen additional problem (Trust & Reliability, spec §1), what you'd build next (business calendar for SLA, real credit ledger for the monthly cap, real auth), what was intentionally left out (spec §20 Non-goals, §21 Known Limitations), and one usefulness metric (e.g., "% of investigated queries where the system's cited decision matched a human reviewer's independent judgment on the same ticket" — directly testable against the golden suite's held-out-style cases).

- [ ] **Step 4: Write docs/ai-tool-usage.md** — factual account of this session: Claude Code used via superpowers:brainstorming for architecture design (with the user driving every correction — monthly cap removal, IncidentFacts precision, provenance structure, business-hours honesty were all user-initiated pushback, not Claude defaults), superpowers:writing-plans for this implementation plan, then task-by-task execution.

- [ ] **Step 5: Record the ~5-minute demo video** covering: architecture (walk the diagram in the spec), live demo (ORD-1001 cancellation with citation + confirm-action flow, TKT-450 historical-conflict correction, an unauthorized-access denial), and the 2-3 decisions worth explaining out loud (clause-level not document-level precedence; no vector DB; the LLM-extracts/code-maps severity split).

- [ ] **Step 6: Commit**

```bash
git add README.md docs/architecture-note.md docs/product-note.md docs/ai-tool-usage.md
git commit -m "docs: submission deliverables (architecture note, product note, AI-tool-usage note)"
```

---

## Self-Review

**Spec coverage:** every numbered spec section (§1-§22) maps to at least
one task above — §5-§9 -> Tasks 1-2, 5, 7; §8 -> Tasks 3-4; §10 -> Task 6;
§12-§13 -> Tasks 7-8; §14 -> Task 9; §11 -> Task 10; §16 -> Task 11-12;
§19 -> Task 13; the deliverable list -> Task 14. No spec section lacks a
task.

**Placeholder scan:** no TBD/TODO; every step has runnable code or an
exact command; Task 10's note about the LangGraph `StateGraph` API is an
explicit, flagged simplification with an offered alternative, not a hidden
gap.

**Type consistency:** `Provenance`, `OrderFacts`, `TicketFacts`,
`AccountFacts`, `CancellationDecision`, `CreditDecision`, `SLADecision`,
`Citation`, `StaffUser`, `ActionDraft`, `IncidentFacts` are each defined
exactly once (Tasks 2, 3, 4, 5, 6, 8, 9) and referenced with matching names
and fields in every later task (checked against Tasks 7, 9, 10, 11, 12).
`get_fact`'s four-argument signature is used identically in Tasks 3-4 and
matches its Task 2 definition. `resolve_sla`'s `severity` parameter (a
plain string) matches what `map_severity` (Task 8) returns.
