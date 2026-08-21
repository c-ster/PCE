# Context Steward

The steward actively maintains context quality without becoming intrusive. It
detects ambiguity, conflicts, staleness, supersession, high-value missing
context, recurring themes, and uncertain status.

## Context health

Important assertions track `importance`, `confidence`, `last_confirmed_at`,
`freshness_half_life`, `conflict_count`, and `usage_count`. Facts age at
different rates — a writing preference may stay useful for years while a
project deadline goes stale in weeks. Freshness is a signal, not proof that a
fact became false.

## Clarification hierarchy

In order, cheapest first:

1. infer silently;
2. infer and offer quick confirmation;
3. propose a prewritten clarification;
4. ask an open-ended question (last resort).

Suggested answer first, always — e.g. "I think $3 remains the working price,
but it hasn't been finalized" with `Correct / Now final / Price changed / No
longer relevant`, rather than an open question.

## Context Inbox

Unresolved questions are triaged as immediate (could materially change the
current output), deferred (worth resolving later), or silent (not worth
surfacing). Normal conversation surfaces at most one optional context check;
the rest wait in the Context Inbox for review in minutes, not administration
as a hobby. Target: at least 80% of surfaced questions are answerable with a
single suggested option.

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
current assertions by substring match. Nothing here yet *generates*
observations automatically — that's Context Steward pattern-detection
work, not yet built; today an observation is proposed explicitly via
`pce memory propose` or the equivalent MCP call.
