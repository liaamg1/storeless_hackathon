-- Match transcript text with the same configuration used for PDF search.
-- Expression indexes also cover transcripts stored before this migration.
CREATE INDEX IF NOT EXISTS idx_transcript_segments_fts
ON transcript_segments USING GIN (to_tsvector('simple', text));
