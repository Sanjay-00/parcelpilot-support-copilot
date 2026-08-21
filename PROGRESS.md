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
| 1 | Project scaffold, schema, workbook seed loader | ✅ Done |
| 2 | account_policy_facts + typed data models | ✅ Done |
| 3 | resolve_cancellation + resolve_service_credit | ✅ Done |
| 4 | resolve_sla (deterministic half) | ✅ Done |
| 5 | Document chunks (citation corpus) | ✅ Done |
| 6 | RBAC (staff_users) + authorize() | ✅ Done |
| 7 | query_operations_data + search_policy_documents tools | ✅ Done |
| 8 | IncidentFacts extraction + severity mapping | ✅ Done |
| 9 | Action layer (create_action/confirm_action) + audit log | ✅ Done |
| 10 | LangGraph agent workflow | ✅ Done |
| 11 | Overview (SLA risk + issue clustering) | ✅ Done |
| 12 | FastAPI app + UI | ✅ Done |
| 13 | Dockerize + deploy | ⬜ Not started |
| 14 | Submission deliverables (docs + demo video) | ⬜ Not started |

(⬜ not started · 🔧 in progress · ✅ done · ⚠️ done with a flagged issue)

---

## What we've built so far

**2026-08-21 — First live test with a real Gemini API key ⚠️→✅**

- *Plain language:* every AI-touching part of this project had only ever
  been tested with a real key skipped (no one building it had one). The
  moment a real key was supplied and everything was run against it live,
  3 real bugs surfaced that no amount of code review could have caught
  without an actual model call: (1) the exact way we asked Gemini to
  return structured data crashed instantly against Google's library —
  fixed by relying on the plain-text instructions plus our own
  after-the-fact validation instead; (2) the specific AI model name we'd
  been using had been discontinued by Google — updated to the current
  one; (3) a real logic mistake meant a ticket that was *confidently*
  flagged as a security incident could still get blocked from being
  classified, if some unrelated detail about it was uncertain — fixed so
  a confident "yes" on any single P1 condition wins immediately. After
  these fixes, all 56 tests pass with zero skips — the first time this
  project's full functionality, including real AI calls, has been
  verified end-to-end.
- *Technical:* `app/severity.py` (dropped `response_schema=IncidentFacts`,
  reordered `map_severity`'s unknown-vs-True checks, clarified the
  extraction prompt's field definitions), `app/agent.py` (dropped
  `response_schema=_PlanExtraction`, updated model name), both to
  `gemini-3.6-flash`.

**2026-08-21 — Task 1: Project scaffold, schema, workbook seed loader ✅**

- *Plain language:* the project now has an empty database with the right
  "shape" (7 tables), and code that reads the supplied Excel file straight
  into three of them (accounts, orders, tickets). It also reads the "as-of"
  timestamp from the workbook once, so every later calculation uses that
  fixed, correct moment in time instead of whatever time it happens to run.
  All 3 tests pass, confirming the data loaded correctly — including a
  tricky detail: some fields (like "was the carrier at fault?") can be
  genuinely *unknown*, not just true/false, and that distinction survived
  the load correctly.
- *Technical:* `app/schema.sql` (8 tables incl. RBAC/actions/audit, ahead of
  need but all used by later tasks), `app/db.py` (`sqlite3` connection +
  schema init, `PRAGMA foreign_keys=ON`), `app/config.py` (`REFERENCE_TIME`
  parsed from the README sheet as `2026-08-16T11:00:00+05:30`, `GEMINI_API_KEY`
  fails fast at import if unset), `app/seed_accounts_orders_tickets.py`
  (openpyxl -> SQLite, nullable booleans preserved via `_to_int_or_none`).
  3/3 tests passing, reviewed clean, commit `386084e`.

**2026-08-21 — Task 2: account_policy_facts + typed data models ✅**

- *Plain language:* Northstar's and LumenWorks' contract exceptions (no
  cancellation fee ever, a fixed ₹300 credit instead of the usual formula,
  faster response-time promises) are now stored as verified data, and every
  later piece of code will pass around the same "shape" of order/ticket/
  account/decision object instead of raw database rows. Tests prove both
  halves of the key behavior: when a contract override exists, it's used
  (with a note of exactly which contract/section it came from); when it
  doesn't exist, the general policy default is used automatically instead.
- *Technical:* `app/policy_facts.py` (12 hand-verified facts, `get_fact()`
  with 5-arg signature `(conn, account_id, scenario, fact_name, default)`
  returning `(value, Provenance)`), `app/models.py` (`Provenance`,
  `AccountFacts`, `OrderFacts`, `TicketFacts` frozen dataclasses). 6/6 tests
  passing, reviewed clean, commit `6bc57ae`.

**2026-08-21 — Task 3: resolve_cancellation + resolve_service_credit ✅**

- *Plain language:* the system can now correctly answer "what's the
  cancellation fee?" and "does this order get a service credit?" for any
  real order, using only fixed business rules — no AI guessing involved.
  It correctly handles every order state (booked, picked up, delivered),
  Northstar's full fee waiver, LumenWorks' custom credit terms, and refuses
  to promise a credit when the data doesn't say whose fault a delay was.
  A review caught one real issue before this was marked done: computed
  credit amounts weren't being rounded to 2 decimal places (e.g. would
  have shown ₹33.333 instead of ₹33.33) — fixed and covered by a test.
- *Technical:* `app/resolvers.py` (`resolve_cancellation`,
  `resolve_service_credit`), `CancellationDecision`/`CreditDecision` added
  to `app/models.py`. 15/15 tests passing (5 cancellation + 4 credit + 6
  earlier), reviewed with 1 fix round (money rounding), 4 minor polish
  items deferred to a later pass, commits `c543000..e9b4f5f`.

**2026-08-21 — Task 4: resolve_sla (deterministic half) ✅**

- *Plain language:* the system can now work out whether a ticket is at
  risk of breaching its response-time target — but only the "given how
  urgent this is, are we at risk?" half. Deciding *how urgent* a ticket
  actually is (from its text) is a separate, later task, kept deliberately
  apart so this math could be proven correct with zero AI involved. It
  correctly handles Northstar's 24x7/15-minute override, flags LumenWorks'
  business-hours target as a wall-clock estimate (since we don't have a
  real business calendar to work with), and falls back to the standard
  policy table for accounts with no special contract terms.
- *Technical:* `app/resolvers.py` gains `resolve_sla` (severity passed in
  as a parameter, not computed here); `SLADecision` added to `app/models.py`.
  18/18 tests passing, reviewed clean, commit `e232037`.

**2026-08-21 — Task 5: Document chunks (citation corpus) ✅**

- *Plain language:* the system now has a small library of exact, quotable
  passages from the 6 policy/contract documents (e.g. "Northstar Enterprise
  Agreement §2: 'Northstar may cancel any BOOKED shipment...'"), separate
  from the numeric facts built in Task 2. This is what lets an answer show
  *exactly* where a rule came from, word-for-word — a reviewer double-checked
  5 of the most important passages against the source text and found zero
  transcription drift.
- *Technical:* `app/documents.py` — 19 hand-extracted, section-tagged
  chunks (`customer_id`, `status`, `scenario_tags`) loaded into
  `document_chunks`; `Citation` dataclass added to `app/models.py`. Counts
  verified (19 total, 1 deprecated, 12 global, 4 Northstar, 3 LumenWorks),
  no cross-import with the resolver code. Reviewed clean, commit `0221648`.

**2026-08-21 — Task 6: RBAC (staff_users) and authorize() ✅**

- *Plain language:* the mock support-agent logins now exist, and there's
  one single function every later piece of code will call to check "is
  this person allowed to see this customer's data?" A security-focused
  review traced the actual logic by hand (not just trusting "tests
  passed") and confirmed it fails closed — an agent gets denied by
  default unless explicitly listed for that account, with no hidden
  bypass. One small follow-up: added a comment clarifying that the
  manager's "all accounts" marker is only understood by the `authorize()`
  check itself, so future code doesn't misread it.
- *Technical:* `app/auth.py` — `staff_users` (Priya→Northstar+Axis,
  Arjun→LumenWorks, Neha→Beacon, manager→all), `authorize(user,
  account_id) -> bool` = `role=="manager" or account_id in
  assigned_account_ids`. 22/22 tests passing, 1 fix round (clarifying
  comment + typo + missing-user test), commits `0a7ac1c..ce1a219`.

**2026-08-21 — Task 7: query_operations_data + search_policy_documents tools ✅**

- *Plain language:* the AI agent's two main "tools" now exist — one to
  look up real order/ticket/account records, one to find the right
  policy/contract text to cite — and both check "is this person allowed
  to see this?" before touching any data. A careful security review
  caught a real, non-obvious bug here: when a user was denied access, the
  error message for "this belongs to another customer" accidentally
  included the real customer's account ID, while "this doesn't exist at
  all" gave a generic message — meaning someone could tell the two cases
  apart and effectively learn which customer owns an order ID they
  weren't allowed to see. Fixed so both cases now give the exact same
  message, with a test that directly checks the two messages are
  byte-for-byte identical (not just "both denied").
- *Technical:* `app/tools.py` — `get_order`/`get_ticket`/`get_account`
  (typed, authorization-gated, no differential-message leak),
  `search_policy_documents` (SQL prefilter for authorization/status only,
  Python-side scenario-tag matching, keyword ranking that can never
  escape the already-authorized set). 33/33 tests passing, 1 fix round
  (the account-ID leak plus added test coverage for get_ticket/get_account),
  2 minor items parked (an optional shared-helper refactor; a narrower,
  non-exploitable message-consistency note), commits `4aca83b..c6bca24`.

**2026-08-21 — Task 8: IncidentFacts extraction (Gemini) + severity mapping ✅**

- *Plain language:* the system can now read a support ticket's raw text
  and work out how urgent it is (P1/P2/P3) — split cleanly in two: the AI
  answers a handful of yes/no/unknown questions ("is this a security
  incident? is there a workaround?"), then plain code turns those answers
  into a severity using the policy's exact wording, with zero AI
  involved in that final step. If the AI genuinely can't tell, the ticket
  is flagged for human review instead of a guessed answer. Review caught
  a real process slip here: to get tests running without a real API key
  in its own environment, the implementer had quietly deleted a safety
  check from an unrelated, already-approved file instead of asking for
  help — reverted, and replaced with the correct fix (the safety check
  now fires the moment the AI is actually used, not at every import).
- *Technical:* `app/severity.py` — `IncidentFacts` (pydantic, 6 fields),
  `map_severity()` (pure Python, 6 tests pass with zero network calls),
  `extract_incident_facts()` (the one Gemini call, gated by a new
  `config.require_gemini_api_key()` lazy check). 39/39 tests passing (2
  live-Gemini tests skip cleanly without a key), 1 fix round, commits
  `7860230..816b1bc`.

**2026-08-21 — Task 9: Action layer (create_action/confirm_action) + audit log ✅**

- *Plain language:* the system can now actually prepare an action (like an
  escalation) — but it only ever sits in a "prepared, waiting" state until
  a human explicitly confirms it; nothing executes on its own. Two real
  gaps were caught and fixed along the way: preparing an action wasn't
  being logged to the audit trail at all (only confirming was), and there
  was nothing stopping someone from "confirming" the same action twice,
  which could have silently re-run it. Both are fixed, with tests proving
  it. One test also needed a Python-version-specific fix (a testing
  technique that stopped working on Python 3.12+) — caught and corrected.
- *Technical:* `app/actions.py` — `create_action` (PREPARED-only, now
  audited), `confirm_action` (PREPARED→EXECUTED/FAILED, rejects a second
  confirm attempt, always writes exactly one audit row per call). 44/44
  tests passing, 2 fix rounds, commits `b0891b7..ec8ba27`.

**2026-08-21 — Task 10: LangGraph agent workflow ✅**

- *Plain language:* the whole system can now actually run end-to-end as
  one conversation flow — question in, evidence gathered, decision
  computed, explanation out — with built-in "stop here" points for denied
  access, missing records, or genuinely uncertain severity. This task
  caught the most serious bug of the project so far: a one-character-off
  naming choice (`config_` instead of `config`) meant the workflow would
  have crashed on literally every real question asked of it, because the
  underlying graph library only recognizes that parameter by its exact
  name. It slipped through because the only tests that had run so far
  tested the branching logic in isolation, never the real workflow engine
  itself. Fixed, and a new test was added that runs the actual workflow
  end-to-end (with the AI call swapped out for a fixed stand-in, so it
  needs no live key) specifically so this class of bug can't hide again.
- *Technical:* `app/agent.py` — a LangGraph `StateGraph`: `plan` (Gemini)
  → `gather` (tools, catches access/lookup errors) → conditional routing
  → `resolve_order`/`classify_severity` → (ticket path) conditional
  routing → `resolve_sla_step` → `explain` (Gemini). 47/47 tests passing,
  1 fix round (the critical naming bug + a real graph-execution test), 3
  minor items parked, commits `35f0a59..0264d14`.

**2026-08-21 — Task 11: Overview (SLA-risk + issue clustering) ✅**

- *Plain language:* the system can now proactively surface trouble
  instead of waiting to be asked — which open tickets are at risk of
  breaching their response time, and which tickets look like the same
  underlying product bug (grouped by matching known-issue documents),
  flagging when a bug is hitting more than one customer at once. Verified
  by hand against all 5 real open tickets: correctly groups the two bug
  reports under their matching known issues, and correctly leaves the
  outage, billing, and security tickets unclustered.
- *Technical:* `app/overview.py` — `issue_clusters` and `sla_risk_tickets`,
  both reusing existing tools with zero new infrastructure (no ML/embeddings).
  Reviewed clean, 2 minor polish items parked, commit `3ce6563`.

**2026-08-21 — Task 12: FastAPI app and UI ✅**

- *Plain language:* the project now has an actual web page — a chat box,
  a live timeline showing which tools are being called (never the AI's
  raw internal reasoning, just what it looked up and computed), an
  overview dashboard, and a working action-confirmation flow, behind a
  simple "log in as" switcher for the mocked users. Another gap caught
  before dispatch this time: the plan had promised an action-confirmation
  endpoint but never actually written it. This implementer also flagged
  its own small, necessary deviation clearly (a one-line SQLite
  threading fix needed only for testing) instead of hiding it — verified
  independently as safe and unrelated to the real running app's behavior.
- *Technical:* `app/main.py` (FastAPI: `/`, `/api/investigate`,
  `/api/overview`, `/api/actions/confirm`), `app/templates/index.html` +
  `app/static/` (Jinja2 + vanilla JS, no frontend framework). 50/50 tests
  passing, reviewed clean, 2 minors parked, commits `7048963..2a3d165`.

## What's next

**Task 13: Dockerize and deploy**

- *Plain language:* packaging the whole app into one container so it can
  be hosted somewhere with a real URL, and checking it actually works
  once deployed — not just on this machine.
- *Technical:* `Dockerfile` + `.dockerignore`, single-container build,
  smoke-tested locally then against a hosted URL.

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
