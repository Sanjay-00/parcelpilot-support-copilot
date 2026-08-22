# Product Note

*Draft: review before submitting. The metric and the "what's next" priorities are judgment calls that should reflect your own view, not just mine.*

## Additional client problem addressed

Both are substantively addressed, but **Trust and Reliability** is the primary one. It is woven through the whole system rather than bolted on.

- Every computed decision carries a `Provenance` (which document/section it came from, or "global default").
- Source precedence is enforced in code, not just prompted: signed agreement, then current policy/SOP, then product docs, then historical tickets. Deprecated documents are excluded from retrieval unconditionally.
- Historical ticket resolutions are structurally kept separate from authoritative citations and explicitly labeled as context only that may be wrong. Tests verify that a false or conflicting number in a historical ticket, or asserted by the user, never changes the actual decision.
- Genuine uncertainty (for example, carrier-fault unknown) refuses to guess and routes to human review rather than picking a plausible answer.
- A generalization evaluation suite (`tests/test_generalization_eval.py`) specifically tests source conflicts (agreement versus SOP, current policy versus historical ticket, three-way conflicts) and confirms the deterministic resolver's output, not just the LLM's wording, is correct in each case.

**Proactive Issue Detection** (Problem 1) is also implemented: SLA-risk surfacing and known-issue ticket clustering in `app/overview.py`, reusing the same tools rather than new infrastructure, but it is the lighter of the two.

## What I would build next, in priority order

1. **Enforce the credit cap and other numeric limits that need a ledger.** Northstar's monthly aggregate service-credit cap is explicitly not enforced today; there is no ledger of already-issued credits in the supplied data to check against. This is a real correctness gap for a production system, not a nice-to-have.
2. **A real business-hours calendar for SLA targets.** LumenWorks' SLA is defined in business hours, but `resolve_sla` currently uses wall-clock time as a documented proxy (flagged via `is_wall_clock_proxy` on the decision). Without a calendar, an at-risk flag near a weekend or holiday boundary can be wrong in either direction.
3. **Persistent, shared conversation state.** Currently in-memory and per-process (`app/conversation.py`). Fine for this deployment, wrong for anything running more than one worker process.
4. **Notification and paging integration for P1s and SLA breaches**, so the proactive-detection view actually reaches someone instead of requiring a human to check the Overview tab.
5. **Broaden retrieval as the corpus grows.** The hand-chunked, keyword-ranked document search is the right choice at 19 chunks across 6 documents. It would need to become embedding-based if the real document set were 10 to 100 times larger.

## What I intentionally left out

- **Hosted deployment and Docker.** Treated as a separate follow-up task.
- **Real authentication.** Login is a mocked user switcher, per the assessment's explicit allowance to mock authentication, account context, and user roles.
- **Vector or semantic search.** Deliberate, not a shortcut. See the Architecture Note's trade-offs section.
- **The Northstar monthly credit cap** (see above; needs a ledger this data pack does not provide).
- **A true business-hours SLA calendar** (see above).

## One metric

**The percentage of investigated queries that resolve to READY (not NEEDS_REVIEW) and pass a manual spot audit for zero unsupported or incorrect claims.**

A single "answer rate" metric alone would reward confident but wrong answers, which is exactly the failure mode the brief calls out: a confidently incorrect answer or action would quickly reduce adoption. Pairing coverage with an audited-accuracy gate makes the metric honest about the actual risk. A system that answers less but is never wrong is more useful to a support-ops team than one that answers everything.
