-- Context Inbox (PRD sections 21-22): unresolved questions the steward
-- surfaced, waiting for a human to triage. dedupe_key lets a re-scan skip
-- creating a duplicate for an issue that's already an open question.

CREATE TABLE context_questions (
    id TEXT PRIMARY KEY,

    question_type TEXT NOT NULL,
    urgency TEXT NOT NULL DEFAULT 'deferred',

    subject TEXT NOT NULL,
    description TEXT NOT NULL,
    suggested_answer TEXT,

    related_assertion_ids TEXT NOT NULL DEFAULT '[]',
    related_observation_id TEXT REFERENCES context_observations (id) ON DELETE SET NULL,

    status TEXT NOT NULL DEFAULT 'open',
    dedupe_key TEXT NOT NULL,

    created_at TEXT NOT NULL,
    resolved_at TEXT,
    resolution_note TEXT
);

CREATE INDEX idx_context_questions_status ON context_questions (status);
CREATE INDEX idx_context_questions_dedupe_key ON context_questions (dedupe_key);
