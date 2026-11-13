CREATE TABLE IF NOT EXISTS files (
    id SERIAL PRIMARY KEY,
    filename TEXT NOT NULL,
    size_bytes BIGINT NOT NULL,
    sha256 TEXT NOT NULL,
    uploaded_at TIMESTAMPTZ DEFAULT NOW()
);

BEGIN;

ALTER TABLE files ADD COLUMN IF NOT EXISTS storage_path TEXT;

CREATE TABLE IF NOT EXISTS document_pages (
    id SERIAL PRIMARY KEY,
    file_id INTEGER NOT NULL REFERENCES files(id) ON DELETE CASCADE,
    page_number INTEGER NOT NULL CHECK (page_number >= 1),
    extracted_text TEXT NOT NULL,
    UNIQUE (file_id, page_number)
);

COMMIT;

BEGIN;

-- Index existing text as well as future uploads; no PDF reprocessing is needed.
-- The explicit configuration must match the expression used in search queries.
CREATE INDEX IF NOT EXISTS idx_document_pages_fts
ON document_pages USING GIN (to_tsvector('simple', extracted_text));

COMMIT;

BEGIN;

ALTER TABLE files ADD COLUMN IF NOT EXISTS file_type TEXT;
ALTER TABLE files ADD COLUMN IF NOT EXISTS duration_ms BIGINT CHECK (duration_ms >= 0);
ALTER TABLE files ADD COLUMN IF NOT EXISTS transcript_language TEXT;

CREATE TABLE IF NOT EXISTS processing_jobs (
    id SERIAL PRIMARY KEY,
    file_id INTEGER NOT NULL REFERENCES files(id) ON DELETE CASCADE,
    job_type TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'queued'
        CHECK (status IN ('queued', 'processing', 'completed', 'failed')),
    current_step TEXT NOT NULL DEFAULT 'queued',
    error_message TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    UNIQUE (file_id, job_type)
);
CREATE INDEX IF NOT EXISTS idx_processing_jobs_queue ON processing_jobs (status, id);

CREATE TABLE IF NOT EXISTS transcript_segments (
    id SERIAL PRIMARY KEY,
    file_id INTEGER NOT NULL REFERENCES files(id) ON DELETE CASCADE,
    start_ms BIGINT NOT NULL CHECK (start_ms >= 0),
    end_ms BIGINT NOT NULL CHECK (end_ms >= start_ms),
    text TEXT NOT NULL,
    speaker TEXT
);
CREATE INDEX IF NOT EXISTS idx_transcript_segments_file_time
ON transcript_segments (file_id, start_ms, end_ms, id);

COMMIT;
