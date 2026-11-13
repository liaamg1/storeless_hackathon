BEGIN;
CREATE TABLE IF NOT EXISTS video_frames (
    id SERIAL PRIMARY KEY,
    file_id INTEGER NOT NULL REFERENCES files(id) ON DELETE CASCADE,
    start_ms BIGINT NOT NULL CHECK (start_ms >= 0),
    end_ms BIGINT NOT NULL CHECK (end_ms > start_ms),
    image_path TEXT NOT NULL,
    image_hash CHAR(16) NOT NULL,
    size_bytes BIGINT NOT NULL CHECK (size_bytes > 0),
    UNIQUE(file_id, start_ms)
);
COMMIT;
