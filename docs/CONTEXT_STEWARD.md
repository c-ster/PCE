# Context Steward

The steward actively maintains context quality without becoming intrusive. It
detects ambiguity, conflicts, staleness, supersession, high-value missing
context, recurring themes, and uncertain status.

**Implemented, in `pce/steward/scan.py`:** only what's mechanically
detectable without an LLM — **conflicts** (two or more assertions still
"current" for the same subject+predicate that were never linked by
supersession — a real, unresolved conflict, not a guess) and **staleness**
(a current assertion nobody's reconfirmed in N days, section 18). Ambiguity,
recurring themes, and "high-value missing context" would need real semantic
reasoning this build doesn't have; rather than fake that with a heuristic
that would just be guessing, they're deliberately not attempted yet.

## Context health

Important assertions track `importance`, `confidence`, `last_confirmed_at`,
`freshness_half_life`, `conflict_count`, and `usage_count`. Facts age at
different rates — a writing preference may stay useful for years while a
project deadline goes stale in weeks. Freshness is a signal, not proof that a
fact became false.

`ContextAssertion` (section 12) already carries `importance`, `confidence`,
and `last_confirmed_at`. `freshness_half_life`/`conflict_count`/`usage_count`
aren't tracked yet — staleness scanning uses a flat day threshold
(`pce context review --staleness-days N`, default 90) instead.

## Clarification hierarchy

In order, cheapest first:

1. infer silently;
2. infer and offer quick confirmation;
3. propose a prewritten clarification;
4. ask an open-ended question (last resort).

Suggested answer first, always — e.g. "I think $3 remains the working price,
but it hasn't been finalized" with `Correct / Now final / Price changed / No
longer relevant`, rather than an open question.

**Implemented** at level 3 (propose a prewritten clarification), not yet 1
or 2: every `ContextQuestion` the scan produces already carries a
`suggested_answer` — for conflicts, the more recently recorded value,
since recency is the one honest signal available without an LLM; for
staleness, "still true as of today?". `pce context answer <id> --note ...`
(optionally `--reconfirm`, which also marks the related assertion
reconfirmed) is how a human picks from — or overrides — that suggestion.
Level 4 (an open-ended question) never happens automatically; there's no
generative model wired in to ask one.

## Context Inbox

Unresolved questions are triaged as immediate (could materially change the
current output), deferred (worth resolving later), or silent (not worth
surfacing). Normal conversation surfaces at most one optional context check;
the rest wait in the Context Inbox for review in minutes, not administration
as a hobby. Target: at least 80% of surfaced questions are answerable with a
single suggested option.

**Implemented** in `pce/steward/questions.py`: `pce context review` runs
the scan and shows the resulting inbox; `pce context inbox` just lists what's
already there (no scan) — matching "review in minutes," not a fresh scan
every time you peek. Re-scanning is idempotent: a conflict or staleness
issue that's already an open question isn't duplicated
(`QuestionRepository.create_if_new`, keyed on a dedupe signature). `pce
context answer/defer/dismiss` resolve one; `pce context stats` shows
counts by status. Exposed over MCP as `get_context_questions` (read-only),
`get_context_review` (scans then lists), and
`answer_context_question`/`defer_context_question`/`dismiss_context_question`.

## Observations vs. facts

Patterns the steward notices (e.g. "your recent writing increasingly frames
privacy as an ownership issue") start as a `ContextObservation`
(proposed/accepted/rejected/expired), never as a `Fact`. Only accepted
observations become durable context.

## Memory governance

The model may propose memory; it must never silently promote inferred
information into authoritative durable memory. Every suggested memory is
presented with `Save / Edit / Don't save`.

**Implemented** in `pce/memory/observations.py`: a `ContextObservation`
starts `proposed` and stays inert — `pce memory accept` ("Save") is what
actually creates the durable `ContextAssertion`; `pce memory edit` ("Edit")
changes the proposal's text while it's still proposed; `pce memory reject`
("Don't save") resolves it with no durable trace at all. Exposed over MCP
as `accept_observation`/`reject_observation`, and `search_memory` searches
current assertions by substring match. An unreviewed proposed observation
also surfaces in `pce context inbox` (via `scan_unreviewed_observations`),
but nothing yet *generates* an observation's content automatically from
noticing a pattern in a document — that would need real semantic
reasoning; today an observation's text is written explicitly, by a human
via `pce memory propose` or a model via the equivalent MCP call.
