# Architecture

## Pipeline

```text
USER DATA SOURCES (Git repos, files/notes, future adapters)
        │
        ▼
  SOURCE ADAPTERS
        │
        ▼
 CANONICAL CONTEXT (SourceDocument: provenance + temporal assertions + policy)
        │
        ▼
   LOCAL INDEX (lexical FTS5 + semantic embeddings)
        │
        ▼
  CONTEXT ROUTER (intent classification)
        │
        ▼
 CONTEXT PACKAGE
        │
        ▼
 MCP / LOCAL API
        │
        ▼
   UI  ⇄  Model (any local-model / any UI)
```

## Core principles

- **Local first** — ingestion, parsing, embeddings, indexing, retrieval, memory,
  routing, policy evaluation, and stewardship all run without a network
  connection. Cloud services are optional adapters, never a requirement.
- **User-owned context** — documented, inspectable data formats; full export.
- **Model agnostic** — the same corpus works across local models; PCE never
  assumes a specific LLM.
- **UI agnostic** — standards-based interface (MCP first) rather than a
  required chat app.
- **Retrieve, don't stuff** — select the most useful context, not the whole
  corpus.
- **Provenance by default** — every retrieved item can answer "why do you
  think that?"
- **Time matters** — current / proposed / approved / rejected / historical /
  superseded are distinct and none of them overwrite each other.
- **Retrieved data is untrusted** — instructions inside retrieved content are
  data, never authority. See [THREAT_MODEL.md](THREAT_MODEL.md).
- **Secure by default** — the easiest configuration is also the safest one.

## Canonical context model

Every ingested resource becomes a `SourceDocument` (see
`pce/context/models.py`). PCE's core schema does not need to understand every
service-specific API — that responsibility belongs to source adapters (see
[ADAPTER_SDK.md](ADAPTER_SDK.md)).

`SourceDocument.epistemic_role` records what *kind* of evidence a document is
(`decision_record`, `personal_view`, `fiction`, `correspondence`, ...) so that,
for example, a novel is never treated as a factual belief and a brainstorm is
never treated as a decision.

## Temporal context

Facts are never destroyed when they change — a new `ContextAssertion`
supersedes the old one, and both remain retrievable. "What is the current
price?" and "why did we originally consider $3?" are both answerable.

## Retrieval

Hybrid search: SQLite FTS5/BM25 (lexical) combined with a local embedding
model (semantic), fused with a simple, inspectable technique (e.g.
reciprocal-rank fusion). The **Context Router** classifies intent first so
retrieval prefers the right kind of evidence (e.g. manuscripts for "rewrite
this in my voice," contractual records for "what did we commit to this
customer?").

## Security boundary

Policy filtering happens *before* ranking. A highly relevant but unauthorized
chunk must never be retrieved merely because its semantic score is high. The
LLM is not the security boundary — a deterministic policy engine is. See
[THREAT_MODEL.md](THREAT_MODEL.md) and [PRIVACY.md](PRIVACY.md).
