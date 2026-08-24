# Architecture Note: ParcelPilot Support Copilot

## Agent design

The agent is a LangGraph `StateGraph`: `plan` (Gemini classifies the query and extracts entities), then `gather` (deterministic tool selection and execution, authorization-gated), then conditional routing, then a domain resolver when one applies, then `explain` (Gemini writes the answer from already-computed evidence, never from its own arithmetic or policy judgment).

```mermaid
flowchart TD
    start(["User query"]) --> plan["plan node\nGemini classifies scenario, extracts entities,\nresolves follow-up references from conversation memory"]
    plan --> gather["gather node\nauthorization check, then the matching tool call"]

    gather -->|"denied, not found,\nambiguous, or off-topic"| review(["needs review\n(clarify or escalate)"])
    gather -->|"order found"| resolveOrder["resolve_order node\ncancellation or service credit resolver"]
    gather -->|"ticket found, SLA question"| severity["classify_severity node\nGemini extracts incident facts"]
    gather -->|"general question\n(product, known issue, agreement, policy)"| explain
    gather -->|"action request"| prepare["create_action\nprepared, not executed"]

    severity -->|"confident severity"| resolveSla["resolve_sla node"]
    severity -->|"genuinely uncertain"| review

    resolveOrder --> explain["explain node\nGemini writes the answer\nfrom the computed decision plus citations"]
    resolveSla --> explain

    explain --> answer(["Answer with citations and provenance"])
    prepare --> confirm(["Awaiting explicit user confirmation"])
    confirm -->|"confirmed"| executed(["Action executed and audited"])
```

**Scenario classification is only used when a specialized deterministic resolver is required. It is not the definition of the chatbot's reasoning surface.** The planner classifies into `cancellation`, `service_credit`, or `sla` only when the question maps to one of those three specific calculations. Every other legitimate support question (product capability, known issues, agreement terms, general SOP or policy, ticket investigation that is not about SLA timing) falls into a single `general_inquiry` route that searches the entire authorized document corpus by keyword relevance rather than a fixed tag. `general_inquiry` is intentionally not further subdivided into per-topic categories such as `product_question` or `known_issue_question`: adding a named bucket per topic would just move the same overfitting problem up one level. The taxonomy stays fixed at one bucket per thing the system must *compute*, plus one general bucket for everything it must *retrieve and explain*.

Tool selection happens via this bounded LLM classification followed by deterministic Python routing, not open-ended function-calling with an iterative plan/act/observe loop. This is a deliberate choice, not an oversight. The system's trust boundary is that the LLM only reads, plans, and explains, while plain, unit-tested Python decides fees, credits, severity, authorization, and action execution. An iterative tool-calling loop would let the model influence which deterministic step runs and in what sequence, with less structural guarantee that every branch stays authorization-checked and resolver-backed. The bounded classification keeps that guarantee mechanical rather than relying on prompt discipline. This satisfies the requirement that the agent choose between at least three distinct tools (document retrieval, structured data lookup/calculation, state-changing action). See `tests/test_agent_golden_scenarios.py::test_materially_different_requests_select_different_bounded_capabilities`, which proves three materially different natural-language requests each select a disjoint tool set.

## Tool design

Three tool categories, all authorization-gated in `app/tools.py` (never in the model's instructions):

1. **Document retrieval.** `search_policy_documents(conn, scenario, account_id, user, keyword=None)`. `scenario` narrows by tag when a resolver needs precision. `scenario=None` (the `general_inquiry` path) uses `_search_general_inquiry` in `app/agent.py`: it fetches the authorized, non-deprecated candidate set via `list_candidate_chunks` and asks the model to select which of those (already-authorized) chunks are actually relevant, falling back to `search_policy_documents`'s keyword-overlap ranking if the model call fails or returns something invalid. See "Document and structured-data handling" below for why and how this is bounded. Deprecated documents are always excluded. Account-specific chunks rank above global defaults.
2. **Structured data lookup and calculation.** `get_order`, `get_ticket`, `get_account` (authorization-gated reads) plus `resolve_cancellation`, `resolve_service_credit`, `resolve_sla` (pure functions, zero AI involvement, unit-tested independently of any model call).
3. **State-changing action.** `create_action` (PREPARED only, audited) and `confirm_action` (PREPARED to EXECUTED, rejects a second confirmation, always audited). The agent can only ever prepare an action; nothing reaches EXECUTED without an explicit, separate user confirmation call.

## Document and structured-data handling

Documents are hand-chunked at the section level (`app/documents.py`, 19 chunks from the 6 supplied PDFs) rather than parsed at runtime. The corpus is small and fixed, so committing reviewed chunks avoids a whole class of extraction-accuracy bugs at negligible cost. Structured data (accounts, orders, tickets) loads from the supplied workbook into SQLite (`app/seed_accounts_orders_tickets.py`). Contract-specific overrides are hand-verified facts (`app/policy_facts.py`) keyed by `(account_id, scenario, fact_name)`, falling back to the general policy default when no override exists.

**Why `general_inquiry` retrieval is LLM-based selection, not keyword search, and why that's still not "vector RAG."** Keyword-overlap ranking requires literal shared words between the question and a chunk's text (`sum(w in r["text"].lower() for w in words) >= 2`). That structurally misses a paraphrase: "do we get money back" never matches a chunk that only ever says "service credit," "courier" never matches "carrier." At this corpus size (a few dozen chunks per account at most), the fix doesn't need embeddings or a vector index -- the whole authorized candidate set fits in one prompt, so `_select_chunks_llm` (`app/agent.py`) just asks the model to judge relevance directly against the text it can already see. This is deliberately bounded, not open-ended retrieval: `list_candidate_chunks` (`app/tools.py`) does authorization and deprecation-filtering in SQL *before* the model ever sees a chunk -- the model is choosing which of an already-authorized set to surface, never which accounts or documents it's allowed to look at -- and every returned `chunk_id` is validated against that same authorized set, so a hallucinated id can never smuggle in unauthorized text. If the model call fails, times out, or returns malformed JSON, retrieval falls back to the deterministic keyword search rather than surfacing an error or silently returning no evidence. This stops being the right approach once the candidate set stops fitting comfortably in one prompt (see `docs/SCALE.md` Tier 2, where hybrid lexical+vector search with a reranker becomes the right move) -- it is a corpus-size-appropriate middle step between pure keyword overlap and a real vector index, not a permanent architecture.

## Source reliability and conflict handling

```mermaid
flowchart TD
    q(["Support question"]) --> agreement{"Does a signed\ncustomer agreement\ncover this?"}
    agreement -->|yes| useAgreement["Use the agreement clause\n(highest authority)"]
    agreement -->|no| policy{"Does the current\npolicy or SOP\ncover this?"}
    policy -->|yes| usePolicy["Use the current policy/SOP default"]
    policy -->|no| productDoc{"Covered by current\nproduct documentation?"}
    productDoc -->|yes| useProduct["Use current product documentation"]
    productDoc -->|no| review(["No authoritative source found:\nescalate to human review"])

    historical["Historical ticket resolutions"] -.->|"context only,\nnever authoritative"| useAgreement
    historical -.-> usePolicy
    historical -.-> useProduct

    deprecated["Deprecated documents"] -.->|"excluded unconditionally\nfrom every retrieval path"| review
```

- **Precedence**: signed customer agreement, then current support policy/SOP, then current product documentation, then historical tickets (context only).
- **Deprecated documents** are excluded from every retrieval path unconditionally.
- **Historical ticket resolutions** are threaded into the explanation prompt as a structurally separate block, explicitly labeled as context only that may be outdated or wrong and must never be treated as current policy. They are kept out of the `citations` list so they can never rank or read as an authoritative source.
- **Genuine uncertainty** (for example, carrier-fault status unknown) refuses to guess and routes to human review rather than picking a plausible answer.
- **Prompt injection**: user text is delimited and the model is told not to follow instructions embedded in it, but this is hardening, not the real security boundary. The real boundary is `authorize()` and the deterministic resolvers, which never take LLM output as authority for access control or calculations.

## Major technical trade-offs

- **Bounded classification over open-ended tool-calling** (see Agent design). Trust guarantees are chosen over apparent agentic sophistication.
- **Hand-chunked static corpus over runtime PDF parsing or vector search.** Appropriate at this corpus size (6 documents); would need to change if the corpus grew significantly.
- **LLM-based relevance selection over the authorized candidate set, not keyword overlap, for `general_inquiry`.** Chosen over keyword search because keyword overlap cannot match a paraphrase, and over a vector index because the whole candidate set already fits in one prompt at this size. Deterministic keyword search is kept as the fallback path, not replaced, so a model outage degrades retrieval quality rather than breaking it.
- **In-memory, per-process conversation state** (`app/conversation.py`). The simplest correct thing for a single-process deployment; documented as needing a shared store such as Redis if deployed multi-process.
