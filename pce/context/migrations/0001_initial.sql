CREATE TABLE source_documents (
    id TEXT PRIMARY KEY,

    source_type TEXT NOT NULL,
    source_system TEXT NOT NULL,
    source_ref TEXT NOT NULL,
    source_version TEXT,

    title TEXT,
    author TEXT,
    authorship TEXT,

    created_at_source TEXT,
    updated_at_source TEXT,
    ingested_at TEXT NOT NULL,

    domains TEXT NOT NULL DEFAULT '[]',
    projects TEXT NOT NULL DEFAULT '[]',
    organizations TEXT NOT NULL DEFAULT '[]',

    epistemic_role TEXT NOT NULL DEFAULT 'unknown',
    authority TEXT,
    status TEXT NOT NULL DEFAULT 'active',

    sensitivity TEXT NOT NULL DEFAULT 'unknown',
    compartments TEXT NOT NULL DEFAULT '[]',

    voice_sample INTEGER NOT NULL DEFAULT 0,
    fiction INTEGER NOT NULL DEFAULT 0,

    content_hash TEXT NOT NULL,
    parser_version TEXT NOT NULL,
    chunking_version TEXT NOT NULL,
    embedding_generation TEXT,

    UNIQUE (source_system, source_ref)
);

CREATE INDEX idx_source_documents_epistemic_role ON source_documents (epistemic_role);
CREATE INDEX idx_source_documents_sensitivity ON source_documents (sensitivity);
