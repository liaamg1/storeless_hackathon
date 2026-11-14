import assert from "node:assert/strict";
import test from "node:test";
import {
  detectUploadKind,
  recommendedOperations,
  selectOperation,
  selectionValid,
  uploadError,
} from "../src/utils/upload.ts";
import { mergeFiles } from "../src/utils/files.ts";
import type { ProcessingFile } from "../src/types/upload.ts";

test("supported extensions are detected case-insensitively without guessing unsupported formats", () => {
  assert.equal(detectUploadKind("slides.PDF"), "pdf");
  assert.equal(detectUploadKind("deck.PPTX"), "pptx");
  assert.equal(detectUploadKind("meeting.MP4"), "video");
  assert.equal(detectUploadKind("macro.pptm"), null);
  assert.equal(detectUploadKind("video.mp4.exe"), null);
});
test("recommended operations use implemented capabilities and satisfy dependencies", () => {
  for (const kind of ["pdf", "pptx", "video"] as const)
    assert.ok(selectionValid(kind, recommendedOperations(kind)));
  assert.ok(recommendedOperations("pdf").includes("pdf_text"));
  assert.ok(recommendedOperations("pptx").includes("slides"));
  assert.ok(recommendedOperations("video").includes("visuals"));
  assert.ok(!recommendedOperations("pdf").includes("storage"));
});
test("dependencies enable the base operation and disabling it clears incompatible choices", () => {
  assert.deepEqual(selectOperation("video", [], "visuals", true), [
    "transcribe",
    "visuals",
  ]);
  assert.deepEqual(
    selectOperation(
      "video",
      ["transcribe", "visuals", "storage"],
      "transcribe",
      false,
    ),
    [],
  );
  assert.deepEqual(selectOperation("pdf", [], "slides", true), [
    "pdf_text",
    "slides",
  ]);
  assert.deepEqual(selectOperation("pdf", ["pdf_text"], "visuals", true), [
    "pdf_text",
  ]);
  assert.ok(!selectionValid("video", ["visuals"]));
  assert.ok(!selectionValid("pdf", ["pdf_text", "storage"]));
});
test("optional visuals and savings can be deselected without disabling transcription", () => {
  const selected = selectOperation(
    "video",
    recommendedOperations("video"),
    "visuals",
    false,
  );
  assert.ok(
    selected.includes("transcribe") &&
      selected.includes("storage") &&
      !selected.includes("visuals"),
  );
  assert.ok(selectionValid("video", selected));
});
test("validation uses fetched byte limits and rejects empty and unsupported files", () => {
  const limits = { pdf: 50, pptx: 50, video: 100 };
  assert.equal(uploadError({ name: "a.pdf", size: 50 }, limits), "");
  assert.match(uploadError({ name: "a.pdf", size: 51 }, limits), /exceeds/);
  assert.match(uploadError({ name: "a.mp4", size: 0 }, limits), /empty/);
  assert.match(uploadError({ name: "a.exe", size: 1 }, limits), /Unsupported/);
  assert.match(uploadError({ name: "a.mp4", size: 1 }, null), /not available/);
});
test("Files uses the whole selected pipeline status, including pending visuals after speech completes", () => {
  const file = {
    id: 1,
    filename: "meeting.mp4",
    size_bytes: 100,
    sha256: "hash",
    uploaded_at: null,
  };
  const video = {
    file_id: 1,
    filename: file.filename,
    size_bytes: 100,
    duration_ms: 1000,
    uploaded_at: null,
    job_id: 2,
    status: "completed" as const,
  };
  const processing: ProcessingFile = {
    file_id: 1,
    filename: file.filename,
    file_type: "video",
    size_bytes: 100,
    operations: ["transcribe", "visuals"],
    status: "queued",
    current_step: "queued",
    error_message: null,
    steps: [
      {
        operation: "transcribe",
        status: "completed",
        current_step: "completed",
        error_message: null,
      },
      {
        operation: "visuals",
        status: "queued",
        current_step: "queued",
        error_message: null,
      },
    ],
  };
  assert.equal(
    mergeFiles([file], [video], [], [processing])[0]?.status,
    "queued",
  );
  assert.equal(
    mergeFiles([file], [video], [], [{ ...processing, status: "failed" }])[0]
      ?.status,
    "failed",
  );
});

test("automatic analysis includes every supported check, including video duplicate detection", () => {
  assert.deepEqual([...recommendedOperations("video")].sort(), [
    "duplicates",
    "storage",
    "transcribe",
    "visuals",
  ]);
  assert.deepEqual([...recommendedOperations("pdf")].sort(), [
    "duplicates",
    "pdf_text",
    "slides",
  ]);
  assert.deepEqual([...recommendedOperations("pptx")].sort(), [
    "duplicates",
    "slides",
  ]);
});

test("duplicate video notice uses actual speech completion even while visuals are processing", async () => {
  const { uploadResultMessage } = await import("../src/utils/upload.ts");
  const file: ProcessingFile = {
    file_id: 4,
    filename: "existing.mp4",
    file_type: "video",
    size_bytes: 100,
    operations: ["transcribe", "visuals"],
    status: "processing",
    current_step: "extracting_visuals",
    error_message: null,
    reused: true,
    steps: [
      {
        operation: "transcribe",
        status: "completed",
        current_step: "completed",
        error_message: null,
      },
      {
        operation: "visuals",
        status: "processing",
        current_step: "extracting_visuals",
        error_message: null,
      },
    ],
  };
  assert.match(uploadResultMessage(file), /Duplicate video detected/);
  assert.match(uploadResultMessage(file), /already transcribed/);
  for (const status of ["queued", "processing"] as const) {
    file.steps[0]!.status = status;
    assert.match(uploadResultMessage(file), /existing job was reused/);
    assert.doesNotMatch(uploadResultMessage(file), /already transcribed\./);
  }
  file.reused = false;
  assert.doesNotMatch(uploadResultMessage(file), /Duplicate/);
});
