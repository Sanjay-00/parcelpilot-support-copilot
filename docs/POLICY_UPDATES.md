# Updating Policies and Adding Vendors

This is the operational runbook for the two things that will actually
happen to a live deployment of this system: an existing policy changes,
or a new vendor/account joins. At the current scale (6 documents, a
handful of accounts), this is a manual, git-based process -- edit the
source files, run the tests, push, redeploy. That's a deliberate choice
at this scale, not a placeholder; see the last section of this document
for how the same problem is handled once that stops being true.

## Case A: an existing policy changes

Example: Support Policy v3 is superseded by v4 with a new SLA target.

1. **`app/documents.py`** -- mark the old chunk's `status` as
   `"DEPRECATED"` (see `policy_v2_targets` for the existing precedent from
   the v2 -> v3 transition). Add a new chunk for the new version:
   new `chunk_id`, `document_name`, `status: "CURRENT"`, new
   `effective_date`, and the actual new text.
2. **`app/policy_config.py`** -- if the change affects a number the
   resolvers actually compute with (a fee, a threshold, an SLA target),
   update the corresponding field and bump `CURRENT.effective_date`. If
   it's an account-specific override instead of a global default, edit
   `app/policy_facts.py`'s `_FACTS` list instead.
3. **Run the drift test**: `pytest tests/test_policy_config_drift.py -v`.
   This mechanically extracts the number from the new chunk text and
   checks it against the config -- it exists specifically to catch the
   case where step 1 and step 2 are updated inconsistently.
4. **Update any resolver test that hardcodes the old expected value**
   (e.g. in `tests/test_resolvers_sla.py`). This is a deliberate manual
   step: a real policy change legitimately changes what "correct" means,
   and that should be a conscious edit, not an automated bulk replace.
5. `pytest` (full suite), then `git commit` and `git push origin main`.

## Case B: a new vendor/account joins

This touches different files, since it's new *data*, not just new
*policy text*.

1. **The account itself** -- accounts/orders/tickets are seeded from
   `ParcelPilot_Assessment_Data.xlsx`. A new customer needs a new row
   there (or in `app/seed_accounts_orders_tickets.py` if not maintaining
   it via the spreadsheet).
2. **Their contract terms** -- if they have account-specific numbers
   (like Northstar's or LumenWorks' overrides), add them to
   `app/policy_facts.py`'s `_FACTS`, keyed to their new `account_id`.
   `app/policy_config.py` (the global defaults) usually doesn't change
   at all -- the new account just falls back to it wherever it has no
   override, the same as every existing account.
3. **Their agreement document** -- new chunk(s) in `app/documents.py`,
   scoped with their `customer_id` so `list_candidate_chunks`/
   `search_policy_documents` only ever surface it for their own account.
   No change needed to the authorization/scoping logic itself.
4. Test, commit, push -- same as Case A.

## What happens on deploy (Render)

Render is connected to this GitHub repo, so a push to `main` triggers an
automatic rebuild and redeploy -- no separate manual deploy step. Because
the SQLite database is entirely *derived* from checked-in source (the
workbook plus `documents.py`/`policy_facts.py`/`policy_config.py`), every
redeploy starts from an empty DB and reseeds fresh from whatever was just
pushed (see `_get_seeded_connection` in `app/main.py`) -- there's no
separate migration step, and no risk of stale data lingering from before
the change.

**Caveat worth knowing:** Render's free tier uses ephemeral disk, so any
redeploy -- not just a policy-driven one -- also wipes accumulated
actions, audit logs, and in-memory conversation history from whatever
usage happened before it. Fine for a demo; a real production deployment
would need a persistent volume or an external database so a routine
redeploy doesn't erase the audit trail (see `docs/PRODUCT_NOTE.md`,
"What I would build next").

## What changes at real scale

This manual-but-mechanically-checked process is correct at 6 documents
and stops being correct somewhere well before 10,000. `docs/SCALE.md`'s
"Keeping policy config in sync as the document set changes" section
covers that transition in full: why plain RAG doesn't solve the
computation half of this problem, how batch changes get triaged instead
of reviewed one by one, and why the tool that catches drift at scale has
to diff at the *fact* level rather than the *text* level once a single
document rewrite can no longer be told apart from a thousand harmless
wording changes just by reading it.
