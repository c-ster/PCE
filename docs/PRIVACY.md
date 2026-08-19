# Privacy Contract

Core PCE:

- no telemetry by default;
- no document-content telemetry;
- no cloud inference requirement;
- no cloud embedding requirement;
- no cloud account requirement;
- no silent external connections;
- no public network binding by default;
- no credentials stored in plaintext;
- no hidden data export.

Every adapter that performs network activity must disclose it (network
behavior, permissions, credential requirements — see
[ADAPTER_SDK.md](ADAPTER_SDK.md)).

## Where your data lives

The private capsule defaults to `~/.pce/` (config, database, indexes, sources,
cache, memory, logs). This directory is never committed to the public code
repository (`.pce/` is git-ignored).

## Sensitivity and compartments

Every `SourceDocument` carries a `sensitivity` level (`PUBLIC`, `PRIVATE`,
`INTERNAL`, `CONFIDENTIAL`, `RESTRICTED`, `UNKNOWN`) and zero or more user-
defined `compartments` (e.g. `PERSONAL`, `WRITING`, `CLIENT_A`). `UNKNOWN`
fails closed: an unclassified source is never silently exposed. See
[THREAT_MODEL.md](THREAT_MODEL.md) for how this is enforced.

## Local file safety

PCE never grants the model arbitrary filesystem access. Users explicitly
approve source roots (e.g. `~/PCE/Sources/Writing`); the model can search
indexed material under those roots and nothing else.
