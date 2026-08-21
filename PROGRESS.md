# ParcelPilot AI Support Copilot — Progress

This file is the single place to check "what are we building, what's done,
what's next" — in plain language first, technical detail second. It gets
updated after every task.

Full detail lives in:
- Design spec: `docs/superpowers/specs/2026-08-21-parcelpilot-copilot-design.md`
- Implementation plan: `docs/superpowers/plans/2026-08-21-parcelpilot-copilot-implementation.md`

---

## What we're building (plain language)

A hiring-assessment project for CalQuity: an internal tool for ParcelPilot
(a fictional logistics company)'s support team. A support agent types a
question like "Can Northstar cancel ORD-1001 without a fee?" and the system:

1. Figures out who/what the question is about (which customer, which order/ticket).
2. Checks the agent is actually allowed to see that customer's data.
3. Looks up the real order/ticket record and the relevant policy/contract text.
4. Works out the actual answer using fixed business rules (never guessed by
   the AI) — e.g. "this customer's contract waives the fee."
5. Explains the answer in plain English, citing exactly where the rule came from.
6. If the agent wants to take an action (like escalating the ticket), the
   system prepares it but never does it until the agent explicitly confirms.

The key idea we keep coming back to: **the AI only reads, plans, and
explains — it never decides a fee, a credit amount, or who's allowed to see
what. Plain Python code decides those things, and that code is unit-tested.**

## What we're building (technical summary)

FastAPI backend, SQLite for all data (accounts/orders/tickets from the
supplied Excel workbook, plus hand-verified customer-contract facts and
hand-chunked policy documents), three deterministic "resolver" functions
(cancellation / service credit / SLA severity) that encode the actual SOP
rules, a LangGraph `StateGraph` that routes a query through
authorization -> data/document retrieval -> the right resolver ->
an LLM (Gemini) explanation step, and a minimal FastAPI + vanilla-JS UI.
Full architecture reasoning is in the design spec linked above.

---

## Status

| # | Task | Status |
|---|------|--------|
| 1 | Project scaffold, schema, workbook seed loader | ⬜ Not started |
| 2 | account_policy_facts + typed data models | ⬜ Not started |
| 3 | resolve_cancellation + resolve_service_credit | ⬜ Not started |
| 4 | resolve_sla (deterministic half) | ⬜ Not started |
| 5 | Document chunks (citation corpus) | ⬜ Not started |
| 6 | RBAC (staff_users) + authorize() | ⬜ Not started |
| 7 | query_operations_data + search_policy_documents tools | ⬜ Not started |
| 8 | IncidentFacts extraction + severity mapping | ⬜ Not started |
| 9 | Action layer (create_action/confirm_action) + audit log | ⬜ Not started |
| 10 | LangGraph agent workflow | ⬜ Not started |
| 11 | Overview (SLA risk + issue clustering) | ⬜ Not started |
| 12 | FastAPI app + UI | ⬜ Not started |
| 13 | Dockerize + deploy | ⬜ Not started |
| 14 | Submission deliverables (docs + demo video) | ⬜ Not started |

(⬜ not started · 🔧 in progress · ✅ done · ⚠️ done with a flagged issue)

---

## What we've built so far

_(nothing yet — about to start Task 1)_

## What's next

**Task 1: Project scaffold, schema, workbook seed loader**

- *Plain language:* set up the empty project, create the database tables
  (empty at first), and write the code that reads the supplied Excel file
  (accounts/orders/tickets) into those tables. Also reads the "as-of" time
  from the workbook so every later calculation uses a fixed, correct
  reference point instead of "right now."
- *Technical:* `app/schema.sql`, `app/db.py`, `app/config.py` (including
  `REFERENCE_TIME` parsed from the README sheet), `app/seed_accounts_orders_tickets.py`,
  plus pytest tests confirming row counts and the reference time.

---

## Glossary (grows as we go)

- **Resolver** — a plain Python function that encodes one business rule
  (e.g. "what's the cancellation fee?") with no AI involved. Fully
  unit-tested, so we can prove it's right independent of any model call.
- **Provenance** — every computed decision records *which* document/section
  it came from (a specific contract clause, or the general policy default),
  so an answer can always be traced back to its source.
- **Clause-level precedence** — a customer's contract only overrides the
  *specific* rule it mentions (e.g. cancellation fee); anything it doesn't
  mention falls back to the general policy automatically.
- **RBAC (Role-Based Access Control)** — each mock support agent is only
  allowed to see the customers assigned to them; a manager role sees everyone.
  Enforced in the code that reads data, not just by asking the AI nicely.
- **LangGraph `StateGraph`** — a way of wiring several steps (nodes) together
  with explicit branching rules (edges), so the workflow can take different
  paths depending on what's found (e.g. "if access is denied, stop here
  instead of continuing to compute an answer").
