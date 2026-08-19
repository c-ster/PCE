# Contributing

Thanks for your interest in Personal Context Engine.

## Ground rules

- **No personal corpora.** Never commit real documents, emails, conversations,
  or personal data from yourself or anyone else. Tests and examples use
  fabricated people, companies, and content only — see `examples/`.
- **Local-first stays local-first.** Core functionality (ingestion, parsing,
  embeddings, indexing, retrieval, memory, routing, policy, stewardship) must
  keep working with no network connection. Cloud integrations are optional
  adapters.
- **Security is architectural.** Don't rely on prompt instructions to enforce
  access control — see [docs/THREAT_MODEL.md](docs/THREAT_MODEL.md).
- **Boring dependencies.** Prefer small, inspectable, well-understood
  libraries over large orchestration frameworks (see
  [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)).

## Development setup

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
pytest
```

## Adding an adapter

New sources should be implemented as adapters against
`pce.adapters.base.SourceAdapter` rather than by extending the core schema.
See [docs/ADAPTER_SDK.md](docs/ADAPTER_SDK.md).

## Reporting security issues

Please do not open a public issue for a security vulnerability — see
[SECURITY.md](SECURITY.md).
