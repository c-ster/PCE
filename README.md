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
- A CLI (`pce init` / `source` / `repo` / `sync` / `compartment` / `index` /
  `search` / `doctor`) wired to everything below; commands for subsystems
  that don't exist yet say so explicitly instead of pretending to work
- Hybrid retrieval: SQLite FTS5 (lexical) + a placeholder embedding provider
  (semantic), fused with reciprocal rank fusion. **Not policy-filtered yet —
  see the caveat below.**

Not yet implemented: a real local embedding model, context router, context
steward, memory governance, policy/compartment **enforcement** (compartments
can be defined but nothing restricts search by them yet), MCP server. See
[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for the full design and
[docs/PRIVACY.md](docs/PRIVACY.md) / [docs/THREAT_MODEL.md](docs/THREAT_MODEL.md)
for the security posture.

> **Caveat:** `pce search` does not yet enforce sensitivity or compartment
> scope (section 29, "policy before ranking"). It will surface anything
> that's been indexed, regardless of how sensitive it's marked. Don't treat
> it as access-controlled until the policy layer lands.

## Install (development)

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
pce search "concise technical explanations preference"
pce doctor
```

`pce --help` lists every command. `PCE_HOME` overrides the capsule location
(defaults to `~/.pce`) — handy for trying PCE without touching your real
capsule.

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
├── context/      # SourceDocument model, SQLite persistence
├── retrieval/    # hybrid lexical + semantic search
├── memory/       # durable memory + governance
├── steward/      # context health, conflicts, staleness detection
├── router/       # intent classification before retrieval
├── policy/       # sensitivity/compartment access control
├── providers/    # LLM / embedding / reranker provider interfaces
├── mcp/          # local MCP server
└── cli/          # pce command-line interface
```

## License

Apache License 2.0 — see [LICENSE](LICENSE).
