-- Chunks are the retrieval unit: a slice of a SourceDocument's text, plus
-- whatever embedding has been computed for it. Not part of the canonical
-- SourceDocument schema (section 8) — this is the local index (section 16).
--
-- source_content_hash lets `pce index` skip re-chunking/re-embedding a
-- document whose content hasn't changed since it was last indexed
-- (section 45, "incremental indexing").

CREATE TABLE context_chunks (
    id TEXT PRIMARY KEY,
    document_id TEXT NOT NULL REFERENCES source_documents (id) ON DELETE CASCADE,
    sequence INTEGER NOT NULL,
    text TEXT NOT NULL,
    source_content_hash TEXT NOT NULL,

    embedding TEXT,             -- JSON-encoded float array; NULL until embedded
    embedding_model TEXT,
    embedding_dims INTEGER,

    created_at TEXT NOT NULL,

    UNIQUE (document_id, sequence)
);

CREATE INDEX idx_context_chunks_document_id ON context_chunks (document_id);

-- External-content FTS5 index over chunk text, kept in sync via triggers so
-- lexical search never needs a separate rebuild step.
CREATE VIRTUAL TABLE context_chunks_fts USING fts5(
    text,
    content = 'context_chunks',
    content_rowid = 'rowid'
);

CREATE TRIGGER context_chunks_ai AFTER INSERT ON context_chunks BEGIN
    INSERT INTO context_chunks_fts (rowid, text) VALUES (new.rowid, new.text);
END;

CREATE TRIGGER context_chunks_ad AFTER DELETE ON context_chunks BEGIN
    INSERT INTO context_chunks_fts (context_chunks_fts, rowid, text) VALUES ('delete', old.rowid, old.text);
END;

CREATE TRIGGER context_chunks_au AFTER UPDATE ON context_chunks BEGIN
    INSERT INTO context_chunks_fts (context_chunks_fts, rowid, text) VALUES ('delete', old.rowid, old.text);
    INSERT INTO context_chunks_fts (rowid, text) VALUES (new.rowid, new.text);
END;
