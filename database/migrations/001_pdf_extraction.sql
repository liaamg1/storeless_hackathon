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
