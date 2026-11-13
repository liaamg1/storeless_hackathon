BEGIN;
-- NULL retains the behavior of uploads made through the existing feature routes.
ALTER TABLE files ADD COLUMN IF NOT EXISTS processing_options JSONB
    CHECK (processing_options IS NULL OR jsonb_typeof(processing_options) = 'array');
COMMIT;
