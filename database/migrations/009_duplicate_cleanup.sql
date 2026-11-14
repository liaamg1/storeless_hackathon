BEGIN;
ALTER TABLE files ADD COLUMN IF NOT EXISTS duplicate_of INTEGER REFERENCES files(id) ON DELETE RESTRICT;
ALTER TABLE files ADD COLUMN IF NOT EXISTS original_removed_at TIMESTAMPTZ;
CREATE TABLE IF NOT EXISTS duplicate_resolutions (
    id UUID PRIMARY KEY,
    sha256 TEXT NOT NULL,
    file_size_bytes BIGINT NOT NULL,
    keeper_id INTEGER NOT NULL REFERENCES files(id) ON DELETE RESTRICT,
    removed_ids JSONB NOT NULL,
    staged_files JSONB NOT NULL,
    status TEXT NOT NULL CHECK(status IN ('pending_purge','resolved')),
    removed_bytes BIGINT NOT NULL DEFAULT 0 CHECK(removed_bytes>=0),
    measurement_complete BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    completed_at TIMESTAMPTZ
);
COMMIT;
