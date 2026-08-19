-- Bookkeeping for the CLI: which adapter-managed roots have been registered,
-- which documents came from which registered source, and the set of
-- user-defined compartments (section 28). None of this is part of the
-- canonical SourceDocument schema (section 8) — it's how `pce source`,
-- `pce repo`, `pce sync`, and `pce compartment` track state.

CREATE TABLE registered_sources (
    id TEXT PRIMARY KEY,
    kind TEXT NOT NULL CHECK (kind IN ('local_file', 'git')),
    path TEXT NOT NULL,
    added_at TEXT NOT NULL,
    UNIQUE (kind, path)
);

CREATE TABLE registered_source_documents (
    registered_source_id TEXT NOT NULL REFERENCES registered_sources (id) ON DELETE CASCADE,
    document_id TEXT NOT NULL REFERENCES source_documents (id) ON DELETE CASCADE,
    PRIMARY KEY (registered_source_id, document_id)
);

CREATE TABLE compartments (
    name TEXT PRIMARY KEY,
    created_at TEXT NOT NULL
);
