BEGIN;

-- Remove only the original synthetic rows. Stored files or extracted pages
-- identify user data and must be preserved even when a filename matches a seed.
DELETE FROM files
WHERE storage_path IS NULL
  AND (filename, size_bytes, sha256) IN (
      ('training.pdf', 12000000, repeat('a', 64)),
      ('training (1).pdf', 12000000, repeat('a', 64)),
      ('architecture.pdf', 8000000, repeat('b', 64))
  )
  AND NOT EXISTS (SELECT 1 FROM document_pages WHERE file_id = files.id);

COMMIT;
