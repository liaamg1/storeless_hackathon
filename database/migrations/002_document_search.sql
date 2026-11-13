BEGIN;

-- Index existing text as well as future uploads; no PDF reprocessing is needed.
-- The explicit configuration must match the expression used in search queries.
CREATE INDEX IF NOT EXISTS idx_document_pages_fts
ON document_pages USING GIN (to_tsvector('simple', extracted_text));

COMMIT;
