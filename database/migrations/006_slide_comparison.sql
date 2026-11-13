BEGIN;
-- Existing extracted page text and file relationships remain intact.
ALTER TABLE document_pages ADD COLUMN IF NOT EXISTS image_path TEXT;
ALTER TABLE document_pages ADD COLUMN IF NOT EXISTS thumbnail_path TEXT;
ALTER TABLE document_pages ADD COLUMN IF NOT EXISTS content_hash CHAR(64);
ALTER TABLE document_pages ADD COLUMN IF NOT EXISTS perceptual_hash CHAR(16);
ALTER TABLE document_pages ADD COLUMN IF NOT EXISTS slide_processed_at TIMESTAMPTZ;
CREATE INDEX IF NOT EXISTS idx_document_pages_slide_content_hash
ON document_pages (content_hash) WHERE content_hash IS NOT NULL;
COMMIT;
