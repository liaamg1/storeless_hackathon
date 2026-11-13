import assert from "node:assert/strict";
import test from "node:test";
import {
  fileType,
  filterFiles,
  mergeFiles,
  fileDestination,
  formatDate,
} from "../src/utils/files.ts";

const base = { sha256: "abc", uploaded_at: "2026-11-13T10:00:00Z" };
const raw = [
  { ...base, id: 1, filename: "Architecture.PDF", size_bytes: 100 },
  { ...base, id: 2, filename: "Meeting.MP4", size_bytes: 300 },
  { ...base, id: 3, filename: "Notes.pdf", size_bytes: 200, uploaded_at: null },
  { ...base, id: 4, filename: "Pending.mp4", size_bytes: 400 },
];
const videos = [
  {
    file_id: 2,
    filename: "Meeting.MP4",
    size_bytes: 300,
    duration_ms: 1000,
    uploaded_at: base.uploaded_at,
    job_id: 9,
    status: "completed" as const,
  },
];
const files = mergeFiles(raw, videos);

test("type and status come from extensions and actual video records", () => {
  assert.equal(fileType("Architecture.PDF"), "pdf");
  assert.equal(fileType("Meeting.MP4"), "video");
  assert.equal(files[0]?.status, "available");
  assert.equal(files[1]?.status, "completed");
  assert.equal(files[3]?.status, "unknown");
});
test("combines trimmed case-insensitive filename, type and status filters", () => {
  assert.deepEqual(
    filterFiles(files, "  MEET  ", "video", "completed", "name").map(
      (f) => f.id,
    ),
    [2],
  );
  assert.deepEqual(filterFiles(files, "", "pdf", "completed", "name"), []);
  assert.deepEqual(
    filterFiles(files, "", "video", "unknown", "name").map((f) => f.id),
    [4],
  );
});
test("supports ascending and descending name and size sorting without changing the source", () => {
  assert.deepEqual(
    filterFiles(files, "", "all", "all", "size").map((f) => f.id),
    [4, 2, 3, 1],
  );
  assert.deepEqual(
    filterFiles(files, "", "all", "all", "size-asc").map((f) => f.id),
    [1, 3, 2, 4],
  );
  assert.deepEqual(
    filterFiles(files, "", "all", "all", "name").map((f) => f.id),
    [1, 2, 3, 4],
  );
  assert.deepEqual(
    filterFiles(files, "", "all", "all", "name-desc").map((f) => f.id),
    [4, 3, 2, 1],
  );
  assert.deepEqual(
    files.map((f) => f.id),
    [1, 2, 3, 4],
  );
});
test("dates with missing values and equal timestamps have stable ordering", () => {
  assert.deepEqual(
    filterFiles(files, "", "all", "all", "newest").map((f) => f.id),
    [1, 2, 4, 3],
  );
  assert.deepEqual(
    filterFiles(files, "", "all", "all", "oldest").map((f) => f.id),
    [3, 1, 2, 4],
  );
  assert.equal(formatDate(null), "Unknown date");
  assert.equal(formatDate("not a date"), "Unknown date");
});
test("long names stay searchable and correct file IDs are used for deep links", () => {
  const longFile = {
    ...files[0]!,
    filename: "architecture-".repeat(100) + ".pdf",
  };
  assert.equal(
    filterFiles([longFile], "architecture-", "pdf", "all", "newest").length,
    1,
  );
  assert.deepEqual(fileDestination(files[1]!), {
    name: "transcription",
    query: { file: "2" },
  });
  assert.deepEqual(fileDestination(longFile), {
    name: "extract",
    query: { file: "1" },
  });
});
