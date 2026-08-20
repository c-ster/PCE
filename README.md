# Personal Context Engine (PCE)

Open-source, local-first context and memory layer for personal AI.

PCE builds a durable, private, model-independent representation of an individual's
documents, projects, decisions, writing, conversations, intellectual influences,
preferences, relationships, memories, and changing priorities — and sits between
that context and whatever LLM or interface the user chooses.

> Own your context. Choose your model. Keep your history.

PCE is not itself an LLM. A user should be able to replace one local model with
another, or one UI with another, without rebuilding their personal context.

## Status

Foundational build-out, tracking [PRD v0.1](docs/ARCHITECTURE.md). Current slice:

- `SourceDocument` canonical model with epistemic roles and sensitivity levels
- SQLite persistence with an explicit migration runner
- A local file adapter and a git adapter (Markdown/text), both enforcing
  approved source roots
- A CLI (`pce init` / `source` / `repo` / `sync` / `classify` / `compartment` /
  `index` / `search` / `policy explain` / `doctor`) wired to everything below;
  commands for subsystems that don't exist yet say so explicitly instead of
  pretending to work
- Hybrid retrieval: SQLite FTS5 (lexical) + a placeholder embedding provider
  (semantic), fused with reciprocal rank fusion
- A deterministic policy engine enforced *before* ranking, not filtered out
  of results afterward: `UNKNOWN` sensitivity is excluded from search by
  default (fails closed), and a document scoped to a compartment the caller
  wasn't granted never surfaces, however relevant
- A local MCP server (`pce serve-mcp`, stdio transport) exposing
  `search_context` and `read_source` to any MCP-compatible client (Jan,
  Claude Desktop/Code, Open WebUI, a bare `mcp` client). The access scope is
  fixed by whoever starts the server, not something the connecting model can
  widen via tool arguments.
- `ContextAssertion`s (`pce assertion`): durable claims that survive being
  superseded — superseding one never deletes the old row, it closes its
  `valid_until` and links `superseded_by`, so "what's the current price" and
  "why did we originally consider $3" are both answerable. Paired with an
  append-only `ContextEvent` log (`SOURCE_SUPERSEDED`, `DECISION_MADE`,
  `DECISION_REVERSED`, ...).

Not yet implemented: a real local embedding model, context router, context
steward, memory governance (`search_memory` exists as an honest stub). See
[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for the full design and
[docs/PRIVACY.md](docs/PRIVACY.md) / [docs/THREAT_MODEL.md](docs/THREAT_MODEL.md)
for the security posture.

> **Caveat:** there's no authentication/session concept yet — `pce search`'s
> and `pce serve-mcp`'s `--compartment`/`--include-unclassified` flags are
> how *you* declare what a given search or server session can see, not a
> barrier against another local user.

## Install

New to the command line, or just want the simplest path? See
**[docs/GETTING_STARTED.md](docs/GETTING_STARTED.md)** — a no-jargon,
step-by-step guide. It uses [`install.sh`](install.sh), a plain-text script
you can read before running (deliberately not a `curl | bash` one-liner —
that's a bad habit to encourage on a privacy tool).

For development:

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

## Try it

```bash
pce init --compartment PERSONAL
pce source add examples/synthetic_profile
pce repo add .
pce source list
pce index
pce search "concise technical explanations preference" --include-unclassified
pce classify <document-id> --sensitivity public --compartment PERSONAL
pce policy explain <document-id> --compartment PERSONAL

pce assertion add --subject "project:nightingale" --predicate status --value proposed
pce assertion add --subject "project:nightingale" --predicate status --value approved \
  --status approved --supersedes <id-from-above>
pce assertion list                                  # current state only
pce assertion history "project:nightingale" status  # full chain, including superseded

pce doctor
```

Newly ingested documents default to `sensitivity: unknown`, which `pce
search` excludes by default (PRD section 27: unknown fails closed) — pass
`--include-unclassified` to see them, or `pce classify` them first.

`pce --help` lists every command. `PCE_HOME` overrides the capsule location
(defaults to `~/.pce`) — handy for trying PCE without touching your real
capsule.

## Connecting a local model

`pce serve-mcp` starts a stdio MCP server. Point any MCP-compatible client
at it — for example, in Jan's or Claude Desktop's MCP config:

```json
{
  "mcpServers": {
    "pce": {
      "command": "pce",
      "args": ["serve-mcp", "--include-unclassified"]
    }
  }
}
```

Drop `--include-unclassified` once you've classified what you want visible
(see `pce classify` above) — leaving it off is the fail-closed default.
`search_context` and `read_source` are available; `search_memory` is a
placeholder until durable memory exists.

Or use the library directly:

```python
from pathlib import Path
from pce.adapters.local_file import LocalFileAdapter
from pce.context.db import connect

adapter = LocalFileAdapter(approved_roots=[Path("examples/synthetic_profile")])
docs = list(adapter.sync())

conn = connect(Path(".pce-demo.sqlite3"))
from pce.context.repository import SourceDocumentRepository
repo = SourceDocumentRepository(conn)
for doc in docs:
    repo.upsert(doc)

print(repo.list())
```

## Repository layout

```text
pce/
├── adapters/     # SourceAdapter implementations (local file, git, ...)
├── context/      # SourceDocument, ContextAssertion, ContextEvent, SQLite persistence
├── retrieval/    # hybrid lexical + semantic search
├── memory/       # durable memory + governance
├── steward/      # context health, conflicts, staleness detection
├── router/       # intent classification before retrieval
├── policy/       # sensitivity/compartment access control
├── providers/    # LLM / embedding / reranker provider interfaces
├── mcp/          # local MCP server (search_context, read_source, search_memory)
└── cli/          # pce command-line interface
```

## License

Apache License 2.0 — see [LICENSE](LICENSE).
