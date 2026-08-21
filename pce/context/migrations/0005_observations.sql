-- Durable memory governance (PRD sections 24-25). An observation is a
-- candidate the model proposed noticing — never silently promoted.
-- Accepting one creates a ContextAssertion (the actual durable memory);
-- rejecting or letting it expire leaves no durable trace at all.

CREATE TABLE context_observations (
    id TEXT PRIMARY KEY,

    subject TEXT NOT NULL,
    description TEXT NOT NULL,

    status TEXT NOT NULL DEFAULT 'proposed',
    confidence REAL NOT NULL DEFAULT 0.5,

    source TEXT REFERENCES source_documents (id) ON DELETE SET NULL,
    resulting_assertion_id TEXT REFERENCES context_assertions (id) ON DELETE SET NULL,

    created_at TEXT NOT NULL,
    resolved_at TEXT
);

CREATE INDEX idx_context_observations_status ON context_observations (status);
