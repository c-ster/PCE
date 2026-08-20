-- Context assertions (PRD section 12) and the append-only event history
-- (section 14). Superseding an assertion never deletes the old row — it
-- sets status='superseded' and closes valid_until, so both "what's true
-- now" and "what did we used to think" stay answerable (section 13).

CREATE TABLE context_assertions (
    id TEXT PRIMARY KEY,

    subject TEXT NOT NULL,
    predicate TEXT NOT NULL,
    value TEXT NOT NULL,

    status TEXT NOT NULL DEFAULT 'proposed',
    importance REAL NOT NULL DEFAULT 0.5,
    confidence REAL NOT NULL DEFAULT 0.5,

    valid_from TEXT NOT NULL,
    valid_until TEXT,
    last_confirmed_at TEXT,

    source TEXT REFERENCES source_documents (id) ON DELETE SET NULL,

    supersedes TEXT REFERENCES context_assertions (id) ON DELETE SET NULL,
    superseded_by TEXT REFERENCES context_assertions (id) ON DELETE SET NULL,

    created_at TEXT NOT NULL
);

CREATE INDEX idx_context_assertions_subject_predicate ON context_assertions (subject, predicate);
CREATE INDEX idx_context_assertions_superseded_by ON context_assertions (superseded_by);

CREATE TABLE context_events (
    id TEXT PRIMARY KEY,

    event_type TEXT NOT NULL,
    subject TEXT NOT NULL,
    assertion_id TEXT REFERENCES context_assertions (id) ON DELETE SET NULL,
    description TEXT NOT NULL,

    occurred_at TEXT NOT NULL,
    recorded_at TEXT NOT NULL,

    source TEXT REFERENCES source_documents (id) ON DELETE SET NULL
);

CREATE INDEX idx_context_events_subject ON context_events (subject);
CREATE INDEX idx_context_events_assertion_id ON context_events (assertion_id);
